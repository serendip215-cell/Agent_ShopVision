"""对话导购业务层：用户话 -> 意图 -> 白名单工具 -> 模板化回复。

对应契约 webapp/backend/README-agent-chat.md：
* 意图解析复用 5.3 的 scripts/agent（IntentParser：Qwen3-4B + LoRA v2）；
* 模型不可用（没下载 / 显存不足 / 加载失败）时自动降级 rule_parse，接口永远有响应；
* 模型在后台线程预热，不阻塞 uvicorn 启动；预热未完成时先用规则模式回答；
* 回复一律模板化拼装，商品信息只取工具真实返回，禁止模型编造。
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import threading
from typing import Any, Callable

from ..config import REPO_ROOT, Settings
from ..errors import ApiError, ErrorCode

logger = logging.getLogger("shopvision.agent")

_CATEGORIES = ["鞋", "水杯", "包", "男装", "运动服", "女装", "手机壳", "厨房用品", "家居用品"]

# 仓库根 scripts/agent 以独立包名加载：webapp/backend/scripts 是同名包，
# 直接 `import scripts.agent` 会命中它（且一旦被导入就缓存进 sys.modules），必然失败。
_AGENT_PKG = "sv_agent_pkg"


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
    """进程内单例：持有意图模型、工具调用与模板回复。"""

    def __init__(self, settings: Settings, search_fn: Callable[..., dict] | None = None) -> None:
        self.settings = settings
        self._search = search_fn or _default_search
        self._parser = None
        self._state = "cold"  # cold | loading | ready | failed
        self._reason = ""
        self._lock = threading.Lock()

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
            parser = IntentParser(
                base,
                self.settings.agent_adapter or self._guess_adapter_path(),
                no_4bit=self.settings.agent_no_4bit,
                max_new_tokens=self.settings.agent_max_new_tokens,
            )
            if not parser._ensure_model():
                raise RuntimeError("IntentParser 加载失败（详见日志）")
            self._parser = parser
            self._state = "ready"
            logger.info("agent 意图模型就绪：%s", base)
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
        default = REPO_ROOT / "dist" / "lora_adapter_v2"
        return str(default) if default.is_dir() else None

    # ---------- 对外能力 ----------

    def status(self) -> dict[str, Any]:
        return {"state": self._state, "reason": self._reason}

    def chat(self, message: str) -> dict[str, Any]:
        text = (message or "").strip()
        if not text:
            raise ApiError(ErrorCode.BAD_REQUEST, "请输入想找的商品")
        limit = self.settings.agent_max_message_len
        if len(text) > limit:
            raise ApiError(ErrorCode.BAD_REQUEST, f"消息过长（最多 {limit} 字）")

        intent, thinking = self._parse_intent(text)
        arguments = self._sanitize(intent.get("arguments") or {})
        thinking.append(f"调用工具：{intent['tool']}({_brief(arguments)})")

        result, error = self._run_tool(intent["tool"], arguments)
        if error:
            reply = f"检索暂时不可用（{error}）。可以稍后再试，或换个说法。"
            items: list[dict] = []
        else:
            items = result.get("items") or []
            reply = self._compose_reply(items)

        return {
            "reply": reply,
            "thinking": thinking,
            "tool_calls": [{"name": intent["tool"], "arguments": arguments}],
            "items": items[: arguments["top_k"]],
        }

    # ---------- 内部步骤 ----------

    def _parse_intent(self, text: str) -> tuple[dict[str, Any], list[str]]:
        intent_parser = _agent_module("intent_parser")
        normalize_intent = intent_parser.normalize_intent
        rule_parse = intent_parser.rule_parse

        if self._state == "ready" and self._parser is not None:
            try:
                raw = self._parser.parse(text)
                intent = normalize_intent(raw, text)
                thinking = [f"识别意图：{intent['tool']}（微调模型）"]
            except Exception as exc:  # noqa: BLE001 - 单次推理失败也降级
                logger.warning("模型推理失败，改用规则解析：%s", exc)
                intent, thinking = rule_parse(text), ["规则模式（模型推理失败）"]
        elif self._state == "failed":
            intent, thinking = rule_parse(text), ["规则模式（模型不可用）"]
        elif self._state == "loading":
            intent, thinking = rule_parse(text), ["规则模式（模型加载中，稍后自动切换）"]
        else:
            intent, thinking = rule_parse(text), ["规则模式（未接 LLM）"]

        # 确定性后处理：洗掉指令词、按关键词补类目。
        # 与 5.3 生产链路一致（评测里对应 --hybrid：纯模型 90% → 加后处理 100%）。
        fill_arguments = _agent_module("category_map").fill_arguments
        arguments, notes = fill_arguments(dict(intent.get("arguments") or {}), text)
        intent["arguments"] = arguments
        if notes:
            thinking.append(f"后处理：{notes}")
        return intent, thinking

    def _sanitize(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()[:200]
        if not query:
            raise ApiError(ErrorCode.BAD_REQUEST, "没听清要找什么，请再描述一下")
        try:
            top_k = int(arguments.get("top_k") or self.settings.agent_tool_top_k)
        except (TypeError, ValueError):
            top_k = self.settings.agent_tool_top_k
        top_k = max(1, min(top_k, 50))

        category = arguments.get("category")
        if category not in _CATEGORIES:
            category = None
        out: dict[str, Any] = {"query": query, "top_k": top_k}
        if category:
            out["category"] = category
        return out

    def _run_tool(self, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if name != "text_search":
            # 白名单外：按契约不落到 404xx（前端会把 404 一律当成"接口未上线"）
            raise ApiError(ErrorCode.BAD_REQUEST, f"暂不支持的工具：{name}")

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


def _brief(arguments: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in arguments.items())
