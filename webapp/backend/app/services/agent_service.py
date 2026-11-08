"""对话导购业务层：用户输入 -> 动作（tool / reply）-> 工具执行 -> 回复。

协议（与 docs/实验五/10-5.4-对话Agent训练规范.md 一致）：
  * v3：{"action":"tool","tool":...,"arguments":{...},"say":"..."} 或 {"action":"reply","text":"..."}
  * v2 兼容：模型只输出 {"tool":"text_search","arguments":{...}} 时按 tool 动作处理

三档降级，保证前端永远有响应：
  1. 模型输出合法动作 -> 走对应工具（或直接回话）；
  2. 模型不可用 -> rule_parse 生成 text_search 动作；
  3. 工具失败 -> 模板化错误文案，不抛 500。

第二轮点评：工具返回商品后，把字段回喂给模型写 60-120 字说明；失败则用模板拼。
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import re
import sys
import threading
import time
from typing import Any, Callable

from ..config import REPO_ROOT, Settings
from ..errors import ApiError, ErrorCode

logger = logging.getLogger("shopvision.agent")

_CATEGORIES = ["鞋", "水杯", "包", "男装", "运动服", "女装", "手机壳", "厨房用品", "家居用品"]

# 仓库根 scripts/agent 以独立包名加载：webapp/backend/scripts 是同名包，
# 直接 `import scripts.agent` 会命中它（且一旦被导入就缓存进 sys.modules），必然失败。
_AGENT_PKG = "sv_agent_pkg"

# 点评/回复里出现“具体价格断言”或“销量断言”就算编造：199元 / ¥19.9 / 5000+人买过
_PRICE_CLAIM = re.compile(
    r"(\d+(?:\.\d+)?\s*元)|([¥￥]\s*\d)|((?:售价|价格)\s*[为是:：]?\s*\d)|(\d+\s*折)"
    r"|((?:销量|已售|已有)\s*\d)|(\d+\s*[+万多]?\s*人(?:买|付款|购买|好评))"
)

# 会话内存上限：30 分钟不活跃即过期，超过 500 段淘汰最久未用
_SESSION_TTL = 30 * 60
_MAX_SESSIONS = 500

_SAFE_FALLBACK = (
    "这个我需要查一下商品库才能回答。"
    "可以补充品类或颜色，或者直接上传一张图片，我来检索。"
)

# 助手把主语说反（“能/可以/帮我找点什么吗”）：凡“帮我+动作”都改成“帮你”
_OWNER_FIX = re.compile(r"帮我(?=找|推荐|看看|搜|查|挑|选|来|试)")

# 查询规范化：模型常把量词/客套话原样带进 query（“找一双白色运动鞋”）
_POLITE_PREFIX = re.compile(
    r"^(?:帮我|帮忙|请|麻烦|给我|我想|我要|想要|有没有|有|找一下|搜一下|找|搜|看看|推荐|来)\s*"
)
_MEASURE_PREFIX = re.compile(
    r"^(?:一|两|二|三|四|五|六|七|八|九|十|\d+)\s*(?:双|个|件|款|只|条|瓶|套|张|台|袋|盒|支|把)\s*"
)
_COUNT_PATTERN = re.compile(r"(\d{1,2})\s*(?:个|件|款|双|只|条|瓶|套|张|台|袋|盒|支|把)")


def _normalize_query(raw: str) -> tuple[str, int | None]:
    """去掉客套话/量词，并抽出「N 个」里的数量（作为 top_k）。"""
    text = (raw or "").strip()
    count: int | None = None

    match = _COUNT_PATTERN.search(text)
    if match:
        count = int(match.group(1))
        text = (text[: match.start()] + text[match.end() :]).strip(" ，,。；;")

    for _ in range(3):  # “帮我找一下一双…” 这种叠着来，剥几层
        stripped = _POLITE_PREFIX.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    text = _MEASURE_PREFIX.sub("", text).strip(" ，,。；;")
    return re.sub(r"\s+", " ", text).strip(), count


def _agent_module(name: str) -> Any:
    """按独立包名加载仓库根 scripts/agent/<name>.py。"""
    if _AGENT_PKG not in sys.modules:
        pkg_dir = REPO_ROOT / "scripts" / "agent"
        spec = importlib.util.spec_from_file_location(
            _AGENT_PKG,
            pkg_dir / "__init__.py",
            submodule_search_locations=[str(pkg_dir)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载 Agent 脚本包：{pkg_dir}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_AGENT_PKG] = module
        spec.loader.exec_module(module)
    return importlib.import_module(f"{_AGENT_PKG}.{name}")


def _default_search(**kwargs: Any) -> dict[str, Any]:
    """白名单工具：HTTP 调本机 /api/v1/text（与 5.3 的 tools.text_search 同一契约）。"""
    tools = _agent_module("tools")
    return tools.text_search(**kwargs)


class AgentService:
    """进程内单例：持有意图模型、工具路由与模板回复。"""

    def __init__(
        self,
        settings: Settings,
        search_fn: Callable[..., dict] | None = None,
        match_service: Any | None = None,
    ) -> None:
        self.settings = settings
        self._search = search_fn or _default_search
        self._match = match_service
        self._parser = None
        self._state = "cold"  # cold | loading | ready | failed
        self._reason = ""
        self._lock = threading.Lock()
        self._multi_turn = False
        self._system_prompt = ""
        self._sessions: dict[str, list[dict]] = {}
        self._summaries: dict[str, list[str]] = {}
        self._slots: dict[str, dict[str, Any]] = {}
        self._seen: dict[str, float] = {}
        self._session_lock = threading.Lock()

    # ---------- 模型预热 ----------

    def warmup(self) -> None:
        """后台线程加载模型；失败只记日志，不阻塞启动。"""
        if not self.settings.agent_warmup:
            logger.info("SHOPVISION_AGENT_WARMUP=false，跳过模型预热（全部走规则模式）")
            return
        thread = threading.Thread(target=self._load_model, name="agent-warmup", daemon=True)
        thread.start()

    def _load_model(self) -> bool:
        with self._lock:
            if self._state in ("ready", "failed", "loading"):
                return self._state == "ready"
            self._state = "loading"
        try:
            IntentParser = _agent_module("intent_parser").IntentParser

            base = self.settings.agent_model or self._guess_model_path()
            adapter = self.settings.agent_adapter or self._guess_adapter_path()
            parser = IntentParser(
                base,
                adapter,
                no_4bit=self.settings.agent_no_4bit,
                max_new_tokens=self.settings.agent_max_new_tokens,
            )
            if not parser._ensure_model():
                raise RuntimeError("IntentParser 加载失败（详见日志）")
            self._parser = parser
            self._state = "ready"

            # v4 适配器：多轮 + 「检索结果：」注入；v3/v2：单轮
            intent_parser = _agent_module("intent_parser")
            self._multi_turn = "v4" in str(adapter or "")
            self._system_prompt = (
                intent_parser.V4_SYSTEM_PROMPT
                if self._multi_turn
                else intent_parser.V3_SYSTEM_PROMPT
            )
            logger.info(
                "agent 意图模型就绪：%s（adapter=%s，多轮=%s）",
                base,
                adapter or "无",
                self._multi_turn,
            )
            return True
        except Exception as exc:  # noqa: BLE001 - 模型问题不能拖垮服务
            self._state = "failed"
            self._reason = f"{type(exc).__name__}: {exc}"
            logger.warning("agent 意图模型不可用，后续走规则降级：%s", self._reason)
            return False

    def _guess_model_path(self) -> str:
        default = (
            REPO_ROOT / "models" / "models"
            / "Qwen--Qwen3-4B-Instruct-2507" / "snapshots" / "master"
        )
        if default.is_dir():
            return str(default)
        return "Qwen/Qwen3-4B-Instruct-2507"

    def _guess_adapter_path(self) -> str | None:
        """按优先级自动选适配器：v4（多轮）> v3（单轮对话）> v2（仅检索）。"""
        for name in ("lora_adapter_v4", "lora_adapter_v3", "lora_adapter_v2"):
            candidate = REPO_ROOT / "dist" / name
            if candidate.is_dir():
                return str(candidate)
        return None

    # ---------- 对外能力 ----------

    def status(self) -> dict[str, Any]:
        return {"state": self._state, "reason": self._reason}

    # ---------- 多轮会话记忆 ----------

    def _history(self, session_id: str | None) -> list[dict]:
        if not session_id:
            return []
        with self._session_lock:
            return list(self._sessions.get(session_id) or [])

    def _remember(self, session_id: str | None, messages: list[dict]) -> None:
        """只保留最近 6 轮（12 条），并把用户原话累积成“早前对话”摘要。"""
        if not session_id:
            return
        with self._session_lock:
            history = (self._sessions.get(session_id) or []) + messages
            trimmed = history[-8:]
            # 截断可能把某轮从中间切开：丢掉开头的非 user 消息，保证历史从用户话开始
            while trimmed and trimmed[0].get("role") != "user":
                trimmed.pop(0)
            self._sessions[session_id] = trimmed

            # B1 规则摘要：只记用户原话（不含注入的检索结果），最多 6 句
            spoken = self._summaries.get(session_id) or []
            for message in messages:
                if message.get("role") != "user":
                    continue
                content = str(message.get("content") or "").strip()
                if not content or content.startswith("检索结果："):
                    continue
                content = content[:40]
                if content not in spoken:
                    spoken.append(content)
            self._summaries[session_id] = spoken[-6:]
            self._seen[session_id] = time.time()

    def _summary_line(self, session_id: str | None) -> str:
        if not session_id:
            return ""
        with self._session_lock:
            spoken = self._summaries.get(session_id) or []
        if not spoken:
            return ""
        return "早前用户说过：" + "；".join(spoken)

    def _merge_query(
        self, session_id: str | None, category: str | None, query: str
    ) -> str:
        """同类目下把上一轮的查询拼进来（模型常只给“白色”，单独检索太泛）。"""
        if not session_id:
            return query
        with self._session_lock:
            slot = dict(self._slots.get(session_id) or {})
        previous = str(slot.get("query") or "")
        if not previous or slot.get("category") != category:
            return query
        if query in previous:
            return previous
        if previous in query:
            return query
        return f"{previous} {query}"

    def _store_slot(self, session_id: str | None, category: str | None, query: str) -> None:
        if not session_id:
            return
        with self._session_lock:
            self._slots[session_id] = {"category": category, "query": query}

    def _slot_category(self, session_id: str | None) -> str | None:
        """图搜这类没有 category 参数的工具，要靠槽位把类目传给下一轮。"""
        if not session_id:
            return None
        with self._session_lock:
            category = (self._slots.get(session_id) or {}).get("category")
        return str(category) if category in _CATEGORIES else None

    def drop_session(self, session_id: str | None) -> bool:
        """显式清空一段会话（前端点“清空”时调用），立刻释放内存。"""
        if not session_id:
            return False
        with self._session_lock:
            existed = session_id in self._seen
            self._sessions.pop(session_id, None)
            self._summaries.pop(session_id, None)
            self._slots.pop(session_id, None)
            self._seen.pop(session_id, None)
            return existed

    def _gc(self) -> None:
        """防止内存无限增长：先清过期会话，再按 LRU 淘汰超量会话。"""
        now = time.time()
        with self._session_lock:
            expired = [
                sid for sid, seen in self._seen.items() if now - seen > _SESSION_TTL
            ]
            for sid in expired:
                self._sessions.pop(sid, None)
                self._summaries.pop(sid, None)
                self._slots.pop(sid, None)
                self._seen.pop(sid, None)

            excess = len(self._seen) - _MAX_SESSIONS
            if excess > 0:
                oldest = sorted(self._seen.items(), key=lambda item: item[1])[:excess]
                for sid, _ in oldest:
                    self._sessions.pop(sid, None)
                    self._summaries.pop(sid, None)
                    self._slots.pop(sid, None)
                    self._seen.pop(sid, None)

    def chat(self, message: str, session_id: str | None = None) -> dict[str, Any]:
        """一句话 -> 动作 -> 工具 -> 回复；带 session_id 时按多轮处理。"""
        text = (message or "").strip()
        if not text:
            raise ApiError(ErrorCode.BAD_REQUEST, "请输入想找的商品")
        limit = self.settings.agent_max_message_len
        if len(text) > limit:
            raise ApiError(ErrorCode.BAD_REQUEST, f"消息过长（最多 {limit} 字）")

        self._gc()
        history = self._history(session_id)
        system_prompt = self._system_prompt or _agent_module("intent_parser").V3_SYSTEM_PROMPT
        # B1：把用户说过的话作为一行摘要追加到 system，长对话不至于全忘
        summary = self._summary_line(session_id)
        if summary:
            system_prompt = f"{system_prompt}\n\n{summary}"
        messages = (
            [{"role": "system", "content": system_prompt}]
            + history
            + [{"role": "user", "content": text}]
        )

        action, thinking = self._decide(text, messages)

        # 模型选择直接回答：不检索
        if action.get("action") == "reply":
            reply = self._guard_reply(action["text"])
            thinking.append("直接回答（未检索）")
            self._remember(
                session_id,
                [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": _dump({"action": "reply", "text": reply})},
                ],
            )
            return {
                "reply": reply,
                "thinking": thinking,
                "tool_calls": [],
                "items": [],
                "say": None,
            }

        tool = action.get("tool") or "text_search"
        arguments = self._sanitize_tool(tool, action.get("arguments") or {})
        # 模型没给类目时，用上一轮槽位兜底（图搜场景模型拿不到 category）
        if (
            tool == "text_search"
            and self._multi_turn
            and not arguments.get("category")
        ):
            slot_category = self._slot_category(session_id)
            if slot_category:
                arguments["category"] = slot_category
                thinking.append(f"沿用上一轮类目：{slot_category}")
        if tool == "text_search" and self._multi_turn:
            merged = self._merge_query(
                session_id, arguments.get("category"), arguments["query"]
            )
            if merged and merged != arguments["query"]:
                thinking.append(f"继承上一轮查询：{merged}")
                arguments["query"] = merged
        thinking.append(f"调用工具：{tool}({_brief(arguments)})")

        result, error = self._run_tool(tool, arguments)
        say = action.get("say")
        if error:
            reply = f"没办成：{error}。换个说法，或者直接上传一张图给我看看。"
            self._remember(
                session_id,
                [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": _dump({"action": "reply", "text": reply})},
                ],
            )
            return {
                "reply": reply,
                "thinking": thinking,
                "tool_calls": [{"name": tool, "arguments": arguments}],
                "items": [],
                "say": say,
            }

        if tool == "text_search":
            self._store_slot(session_id, arguments.get("category"), arguments["query"])

        items = result.get("items") or []
        reply = self._render_tool_result(tool, result, items, text, messages, arguments, say)
        top_k = int(arguments.get("top_k") or self.settings.agent_tool_top_k)

        # 多轮上下文：user -> 工具调用 -> 检索结果 -> 回复（与训练数据同构）
        tool_payload: dict[str, Any] = {
            "action": "tool",
            "tool": tool,
            "arguments": arguments,
        }
        if say:
            tool_payload["say"] = say

        if items:
            turns = [
                {"role": "user", "content": text},
                {"role": "assistant", "content": _dump(tool_payload)},
                {"role": "user", "content": _result_message(items)},
                {"role": "assistant", "content": _dump({"action": "reply", "text": reply})},
            ]
        else:
            # 类目/详情这类没有商品结果的工具：不留工具轮，保持 user/assistant 交替
            turns = [
                {"role": "user", "content": text},
                {"role": "assistant", "content": _dump({"action": "reply", "text": reply})},
            ]
        self._remember(session_id, turns)

        return {
            "reply": reply,
            "thinking": thinking,
            "tool_calls": [{"name": tool, "arguments": arguments}],
            "items": items[:top_k],
            "say": say,
        }

    # ---------- 动作决策 ----------

    def _decide(
        self, text: str, messages: list[dict] | None = None
    ) -> tuple[dict[str, Any], list[str]]:
        """让模型决定调工具还是直接回答；不可用时退回规则动作。"""
        intent_parser = _agent_module("intent_parser")

        if self._state == "ready" and self._parser is not None:
            try:
                if (
                    self._multi_turn
                    and messages
                    and hasattr(self._parser, "parse_action_messages")
                ):
                    action = self._parser.parse_action_messages(messages)
                else:
                    action = self._parser.parse_action(text)
                return action, [f"动作：{action['action']}（微调模型）"]
            except Exception as exc:  # noqa: BLE001 - 单次推理失败也降级
                logger.warning("动作解析失败，改用规则：%s", exc)
                return (
                    intent_parser.as_action(intent_parser.rule_parse(text)),
                    ["规则模式（模型推理失败）"],
                )

        note = {
            "failed": "规则模式（模型不可用）",
            "loading": "规则模式（模型加载中，稍后自动切换）",
        }.get(self._state, "规则模式（未接 LLM）")
        return intent_parser.as_action(intent_parser.rule_parse(text)), [note]

    # ---------- 工具执行 ----------

    def _guard_reply(self, text: str) -> str:
        """回复安全闸：修主语口误 + 拦截价格/销量断言（模型不许编造）。"""
        candidate = (text or "").strip()
        if not candidate:
            return _SAFE_FALLBACK
        # 助手自称“能/可以帮我找”属口误，改成“帮你”
        candidate = _OWNER_FIX.sub("帮你", candidate)
        if _PRICE_CLAIM.search(candidate):
            logger.warning("回复含价格/销量断言，已替换为安全话术：%s", candidate[:80])
            return _SAFE_FALLBACK
        return candidate[:300]

    def _sanitize_tool(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool == "text_search":
            return self._sanitize(arguments)
        if tool == "image_search":
            try:
                alpha = float(arguments.get("alpha", 0.6))
            except (TypeError, ValueError):
                alpha = 0.6
            return {"alpha": max(0.0, min(alpha, 1.0))}
        if tool == "get_item_detail":
            item_id = str(arguments.get("item_id") or "").strip()
            if not item_id:
                raise ApiError(ErrorCode.BAD_REQUEST, "缺少 item_id，无法查详情")
            return {"item_id": item_id}
        return {}

    def _run_tool(self, tool: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if tool == "text_search":
            return self._search_with_retry(arguments)
        if tool == "image_search":
            return {}, "当前是文字对话，没有图片；请点「上传图片」按图检索"
        if tool == "list_categories":
            if self._match is None:
                return {}, "索引服务未装配"
            return {"categories": self._match.index.categories}, ""
        if tool == "get_item_detail":
            if self._match is None:
                return {}, "索引服务未装配"
            item = self._match.index.find_item(arguments["item_id"])
            if item is None:
                return {}, "库里没有这件商品"
            return {"item": item}, ""
        raise ApiError(ErrorCode.BAD_REQUEST, f"暂不支持的工具：{tool}")

    def _search_with_retry(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        last = ""
        for attempt in range(1, max(1, self.settings.agent_retry_times) + 1):
            try:
                result = self._search(**arguments)
            except Exception as exc:  # noqa: BLE001 - HTTP/网络异常统一重试
                last = f"{type(exc).__name__}: {exc}"
                logger.warning("第 %s 次工具调用失败：%s", attempt, last)
                continue
            if result.get("error"):
                last = str(result["error"])
                logger.warning("第 %s 次工具返回错误：%s", attempt, last)
                continue
            return result, ""
        return {}, last or "检索服务无响应"

    def _sanitize(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_query = str(arguments.get("query") or "")[:200]
        query, count = _normalize_query(raw_query)
        if not query:
            raise ApiError(ErrorCode.BAD_REQUEST, "没听清要找什么，请再描述一下")
        try:
            top_k = int(arguments.get("top_k") or self.settings.agent_tool_top_k)
        except (TypeError, ValueError):
            top_k = self.settings.agent_tool_top_k
        if count:
            # 用户明说“10 个”，优先于模型给的数量
            top_k = count
        top_k = max(1, min(top_k, 50))

        category = arguments.get("category")
        if category not in _CATEGORIES:
            category = None
        out: dict[str, Any] = {"query": query, "top_k": top_k}
        if category:
            out["category"] = category
        return out

    # ---------- 第二轮点评 ----------

    # ---------- 工具结果渲染 ----------

    def _render_tool_result(
        self,
        tool: str,
        result: dict[str, Any],
        items: list[dict],
        text: str,
        messages: list[dict] | None = None,
        arguments: dict[str, Any] | None = None,
        say: str | None = None,
    ) -> str:
        """按工具类型生成回复：检索类走点评，其余走结构化模板。"""
        if tool == "list_categories":
            categories = result.get("categories") or []
            if not categories:
                return "索引里暂时没有可检索的类目。"
            return f"库里可检索 {len(categories)} 类：{'、'.join(categories)}。"

        if tool == "get_item_detail":
            item = result.get("item") or {}
            if not item:
                return "没找到这件商品的详情。"
            name = item.get("item_name") or "未命名商品"
            return (
                f"「{name}」属于{item.get('category') or '未知类目'}，"
                f"细分类 {item.get('type') or item.get('product_type') or '未标注'}，"
                f"颜色 {item.get('color') or '未标注'}，"
                f"材质 {item.get('material') or '未识别'}。"
            )

        # 检索类：v4 多轮把结果按训练格式回喂；v3 走单轮点评；失败都退回模板
        if self._multi_turn and self._parser is not None and items and messages is not None:
            tool_payload: dict[str, Any] = {
                "action": "tool",
                "tool": tool,
                "arguments": arguments or {},
            }
            if say:
                tool_payload["say"] = say
            reply = self._parser.reply_messages(
                messages
                + [
                    {"role": "assistant", "content": _dump(tool_payload)},
                    {"role": "user", "content": _result_message(items)},
                ]
            )
            if reply:
                guarded = self._guard_reply(reply)
                if 10 <= len(guarded) <= 300:
                    return guarded

        return self._second_round(text, items) or self._compose_reply(items)

    def _second_round(self, text: str, items: list[dict]) -> str | None:
        """把检索结果回喂给模型写点评；失败或不合规时返回 None，由模板兜底。"""
        if not items or self._state != "ready" or self._parser is None:
            return None
        comment_fn = getattr(self._parser, "comment", None)
        if not callable(comment_fn):
            return None
        fields = ("item_name", "type", "color", "material", "similarity")
        payload = {"items": [{key: item.get(key) for key in fields} for item in items[:5]]}
        comment = comment_fn(text, json.dumps(payload, ensure_ascii=False))
        if not comment:
            return None
        comment = comment.strip()
        if not 20 <= len(comment) <= 200:
            logger.info("点评长度不合规（%s 字），改用模板", len(comment))
            return None
        if _PRICE_CLAIM.search(comment):
            logger.warning("点评出现具体价格断言，改用模板：%s", comment)
            return None
        return comment

    # ---------- 以图搜图（图 + 可选文字融合） ----------

    def search_by_image(
        self,
        image: Any,
        message: str = "",
        alpha: float = 0.6,
        top_k: int = 5,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """图片 -> 相似商品；message 非空时按 α 融合图像/文本向量再检索。"""
        if self._match is None:
            raise ApiError(ErrorCode.MODEL_UNAVAILABLE, "检索服务未装配（match_service 为空）")
        encoder = self._match.encoder
        index = self._match.index
        if not encoder.model_loaded:
            raise ApiError(
                ErrorCode.MODEL_UNAVAILABLE,
                "当前是占位编码器，图搜结果无意义；请切换 SHOPVISION_MODEL_BACKEND=onnx",
            )

        text = (message or "").strip()[:200]
        v_img = encoder.encode_image(image)
        thinking = ["图像塔编码：visual 塔 → 512 维"]
        vector = v_img

        if text:
            alpha = max(0.0, min(float(alpha), 1.0))
            v_txt = encoder.encode_text(text)
            vector = self._unit(alpha * v_img + (1.0 - alpha) * v_txt)
            thinking.append(f"文本塔编码：text 塔（{text}）")
            thinking.append(f"向量融合：α={alpha:.2f}（图像 {alpha:.0%} / 文字 {1 - alpha:.0%}）")

        category, score, _ = index.best_category(vector)
        hits = index.search(vector, top_k=top_k)
        items = [hit.as_dict() for hit in hits]
        thinking.append(f"检索：{len(index.categories)} 类索引，命中 {len(items)} 条")

        reply = self._second_round(
            text or "与上传图片相似的商品", items
        ) or self._compose_image_reply(category, items, bool(text))

        # 图搜进入多轮上下文：下一句文字可以继续引用这批商品
        if session_id:
            self._store_slot(session_id, category, text)
            tool_arguments: dict[str, Any] = {
                "alpha": round(float(alpha), 2),
                "top_k": top_k,
            }
            if text:
                tool_arguments["message"] = text
            turns = [
                {
                    "role": "user",
                    "content": "按这张图找类似的" + (f"：{text}" if text else ""),
                },
                {
                    "role": "assistant",
                    "content": _dump(
                        {
                            "action": "tool",
                            "tool": "image_search",
                            "arguments": tool_arguments,
                        }
                    ),
                },
            ]
            if items:
                turns.append({"role": "user", "content": _result_message(items)})
            turns.append(
                {"role": "assistant", "content": _dump({"action": "reply", "text": reply})}
            )
            self._remember(session_id, turns)

        return {
            "reply": reply,
            "thinking": thinking,
            "tool_calls": [
                {
                    "name": "image_search",
                    "arguments": {
                        "alpha": round(float(alpha), 2),
                        "top_k": top_k,
                        **({"message": text} if text else {}),
                    },
                }
            ],
            "items": items,
            "category": category,
            "similarity": round(float(score), 4) if score else None,
        }

    @staticmethod
    def _unit(vector: Any) -> Any:
        """L2 归一化（融合后的向量必须重新归一化，余弦才等价于点积）。"""
        import numpy as np

        array = np.asarray(vector, dtype="float32").reshape(-1)
        return array / (np.linalg.norm(array) + 1e-12)

    def _compose_image_reply(
        self, category: str | None, items: list[dict], fused: bool
    ) -> str:
        if not items:
            return "这张图没检索到相近商品，换一张更清晰的正视图再试。"
        kind = "图 + 文" if fused else "这张图"
        head = f"{kind}看起来属于「{category or '未知类别'}」，找到 {len(items)} 件相似商品："
        lines = [head]
        for position, item in enumerate(items[:3], start=1):
            name = item.get("item_name") or "未命名商品"
            similarity = item.get("similarity")
            try:
                score = f"，相似度 {float(similarity):.2f}"
            except (TypeError, ValueError):
                score = ""
            lines.append(f"{position}. {name}{score}")
        return "\n".join(lines)

    def _compose_reply(self, items: list[dict]) -> str:
        if not items:
            return "库里没找到符合条件的商品。换个关键词试试，或者直接上传一张图让我看图找。"
        head = f"在「{items[0].get('category') or '全部'}」里找到 {len(items)} 件相近商品，最接近的是："
        lines = [head]
        for index, item in enumerate(items[:3], start=1):
            name = item.get("item_name") or "未命名商品"
            similarity = item.get("similarity")
            try:
                score = f"，相似度 {float(similarity):.2f}"
            except (TypeError, ValueError):
                score = ""
            lines.append(f"{index}. {name}{score}")
        return "\n".join(lines)


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _result_message(items: list[dict]) -> str:
    """与 v4 训练数据一致：检索结果以「检索结果：」前缀注入，只带训练字段。"""
    fields = ("category", "item_id", "item_name", "type", "color", "material", "similarity")
    payload = {"items": [{key: item.get(key) for key in fields} for item in items[:3]]}
    return "检索结果：" + _dump(payload)


def _brief(arguments: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in arguments.items())
