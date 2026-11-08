"""5.2 交付后的意图解析实现（供 5.3 接入）。

设计要点：
  1. **懒加载**：模型只在第一次调用时加载，5.3 的单测（纯结构化意图路径）不需要 GPU。
  2. **工具名纠错**：实测微调模型会把 `text_search` 写成 `tool_search`
     （见 docs/实验五/03-微调结果实跑记录.md 第五节）。这里用编辑距离对齐白名单，
     不改评测口径——评测照样按严格匹配算分，纠错只发生在运行时链路。
  3. **JSON 容错**：模型可能输出「好的，我来帮您…」+ markdown 代码块包裹，
     复用 eval_baseline_vs_lora.py 的 parse_json_lenient 逻辑。
  4. **降级**：模型不可用（无 GPU / 无权重）时退回规则解析，保证前端永远有响应。

用法：
    from scripts.agent.intent_parser import IntentParser
    p = IntentParser(base_model="Qwen/Qwen3-4B-Instruct-2507",
                     adapter="dist/lora_adapter")
    intent = p.parse("帮我找黑色木纹手机壳，5个")   # -> {"tool": "text_search", "arguments": {...}}
"""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger("shopvision.intent")

JSON_BLOCK = re.compile(r"\{.*\}", re.S)

# 白名单工具（与 scripts/agent/tools.py 的 TOOLS 保持一致）
WHITELIST = ["text_search"]

# v3 协议：动作二选一（tool / reply），工具扩到 4 个
TOOLS = ["text_search", "image_search", "list_categories", "get_item_detail"]

# v3 的系统提示词与训练数据同源，避免训练/推理不一致
try:  # 生成脚本与解析器同目录，正常都能导入
    from .build_dialogue_sft import SYSTEM_PROMPT as V3_SYSTEM_PROMPT
except Exception:  # pragma: no cover - 只做兜底，正常不会走到
    V3_SYSTEM_PROMPT = (
        "你是电商导购助手。可用工具：text_search / image_search / list_categories / "
        "get_item_detail。只输出一个 JSON：{\"action\":\"tool\",...} 或 {\"action\":\"reply\",\"text\":\"...\"}。"
    )

CATEGORIES = ["鞋", "水杯", "包", "男装", "运动服", "女装", "手机壳", "厨房用品", "家居用品"]


def closest_tool(name: str, candidates: list[str] | None = None) -> str | None:
    """把模型给出的工具名对齐到白名单里最像的那个。

    实测 case：模型输出 `tool_search`，正确是 `text_search`。
    相似度阈值 0.6 —— 低于这个值认为是真的编造，不强行对齐。
    """
    candidates = candidates or WHITELIST
    if not name:
        return None
    if name in candidates:
        return name

    def tokens(s: str) -> set[str]:
        """按 _ - 空格 切开，并额外按驼峰切；小写归一。"""
        parts = re.split(r"[_\-\s]+", s.lower())
        out: set[str] = set()
        for p in parts:
            out.add(p)
            out.update(re.findall(r"[a-z]+", p))
        return {t for t in out if t}

    name_tokens = tokens(name)
    best, best_score = None, 0.0
    for cand in candidates:
        cand_tokens = tokens(cand)
        # 1) 字符相似度
        score = SequenceMatcher(None, name.lower(), cand.lower()).ratio()
        # 2) 词元集合重合度（修 search_text → text_search 这类词序颠倒）
        if name_tokens and cand_tokens:
            overlap = len(name_tokens & cand_tokens) / len(name_tokens | cand_tokens)
            score = max(score, overlap)
            if name_tokens == cand_tokens:
                score = 1.0
        # 3) 动词尾相同加权（_search / _match 这类尾词更有区分度）
        suffix = name.split("_")[-1].lower() if "_" in name else ""
        if suffix and cand.lower().endswith(suffix):
            score = max(score, 0.75)
        if score > best_score:
            best, best_score = cand, score

    if best_score >= 0.6:
        logger.info("工具名纠错：%r -> %r (相似度 %.2f)", name, best, best_score)
        return best
    logger.warning("工具名 %r 无法对齐白名单 %s", name, candidates)
    return None


def parse_json_lenient(text: str) -> dict | None:
    """从模型输出里掏出第一个 JSON 对象（与评测脚本同一套容错逻辑）。"""
    text = (text or "").strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = JSON_BLOCK.search(text)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def rule_parse(user_input: str) -> dict[str, Any]:
    """无 LLM 的规则降级：从用户话里抓类目/数量，构造 text_search 意图。

    方案文档 P0 明确要求「不接 LLM 也能演示」，这条路径就是那个兜底。
    抓不到类目就留给后端自动判类（接口支持 category 为空）。
    """
    text = user_input or ""
    category = next((c for c in CATEGORIES if c in text), None)

    top_k = 5
    m = re.search(r"(\d+)\s*(?:个|件|条|款)", text)
    if m:
        top_k = max(1, min(int(m.group(1)), 20))

    # 去掉指令性词缀，留检索词
    query = text
    # 长的先替换，避免「帮我找」被「找」先吃掉变成「帮我 」
    for noise in ["帮我找", "帮我搜", "我想找", "有没有", "随便看看",
                  "找一下", "搜索", "想找", "推荐", "看看",
                  "帮我", "想", "找", "搜", "要", "来",
                  "一下", "吧", "呢", "，", ","]:
        query = query.replace(noise, " ")
    # 去掉数量词（"5个" / "3件"），它属于 top_k 不属于 query
    query = re.sub(r"\d+\s*(?:个|件|条|款)", " ", query)
    query = re.sub(r"\s+", " ", query).strip() or text

    args: dict[str, Any] = {"query": query, "top_k": top_k}
    if category:
        args["category"] = category
    return {"tool": "text_search", "arguments": args}


def normalize_intent(raw: dict | None, user_input: str) -> dict[str, Any]:
    """把模型输出规范成 {tool, arguments}，工具名走白名单纠错。"""
    if not raw:
        return rule_parse(user_input)

    # 实测：模型有时输出 {"name": "text_search"} 而不是 {"tool": ...}（5060 上 10 条里有 7 条）
    tool_raw = (raw.get("tool") or raw.get("name")
                or raw.get("intent") or raw.get("function") or "")
    tool = closest_tool(str(tool_raw))
    if tool is None:
        logger.warning("模型给出未知工具 %r，降级规则解析", tool_raw)
        return rule_parse(user_input)

    args = raw.get("arguments")
    if not isinstance(args, dict):
        # 有的模型把参数平铺在顶层
        args = {k: raw[k] for k in ("query", "category", "top_k") if k in raw}
    if not args.get("query"):
        return rule_parse(user_input)

    # top_k 兜底与夹紧
    try:
        args["top_k"] = max(1, min(int(args.get("top_k", 5)), 20))
    except (TypeError, ValueError):
        args["top_k"] = 5

    return {"tool": tool, "arguments": args}


def as_action(intent: dict[str, Any]) -> dict[str, Any]:
    """把 v2 的 {tool, arguments} 包装成 v3 的 tool 动作。"""
    return {"action": "tool", **intent}


def _tool_payload(payload: dict[str, Any], user_input: str) -> dict[str, Any]:
    """校验并规范化工具动作；工具名走白名单纠错。"""
    raw_tool = (
        payload.get("tool")
        or payload.get("name")
        or payload.get("intent")
        or payload.get("function")
        or ""
    )
    tool = closest_tool(str(raw_tool), TOOLS)
    if tool is None:
        return as_action(rule_parse(user_input))

    args = payload.get("arguments")
    if not isinstance(args, dict):
        args = {
            key: payload[key]
            for key in ("query", "category", "top_k", "item_id", "alpha")
            if key in payload
        }

    if tool == "text_search":
        args = normalize_intent(payload, user_input)["arguments"]
    else:
        args = {key: value for key, value in args.items() if value not in (None, "")}

    out: dict[str, Any] = {"action": "tool", "tool": tool, "arguments": args}
    say = payload.get("say")
    if isinstance(say, str) and say.strip():
        out["say"] = say.strip()[:30]
    return out


def normalize_action(payload: dict[str, Any] | None, user_input: str) -> dict[str, Any]:
    """统一成 v3 动作；兼容 v2 只给 {tool, arguments} 的输出。"""
    if not payload:
        return as_action(rule_parse(user_input))

    action = str(payload.get("action") or "").strip().lower()
    if action == "reply":
        text = str(payload.get("text") or "").strip()
        if text:
            return {"action": "reply", "text": text}
        return as_action(rule_parse(user_input))

    if action == "tool":
        return _tool_payload(payload, user_input)

    # v2 兼容：没有 action，但有工具名
    if any(key in payload for key in ("tool", "name", "intent", "function")):
        return _tool_payload(payload, user_input)

    return as_action(rule_parse(user_input))


class IntentParser:
    """持有微调模型的意图解析器。首次 parse 时才加载权重。"""

    def __init__(self, base_model: str, adapter: str | None = None,
                 no_4bit: bool = False, max_new_tokens: int = 128):
        self.base_model = base_model
        self.adapter = adapter
        self.no_4bit = no_4bit
        self.max_new_tokens = max_new_tokens
        self._model = None
        self._tokenizer = None
        self._load_failed = False

    def _ensure_model(self):
        if self._model is not None or self._load_failed:
            return self._model is not None
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            quant_config = None
            if not self.no_4bit:
                try:
                    import bitsandbytes  # noqa: F401
                    from transformers import BitsAndBytesConfig

                    quant_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.bfloat16,
                        bnb_4bit_use_double_quant=True,
                    )
                except ImportError:
                    logger.warning("无 bitsandbytes，用 bf16 全精度加载")

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.base_model, trust_remote_code=True
            )
            model = AutoModelForCausalLM.from_pretrained(
                self.base_model,
                quantization_config=quant_config,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
            )
            if self.adapter:
                from peft import PeftModel

                model = PeftModel.from_pretrained(model, self.adapter)
            model.eval()
            self._model = model
            logger.info("意图模型加载完成：%s + %s", self.base_model, self.adapter)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("意图模型加载失败，后续走规则降级：%s", e)
            self._load_failed = True
            return False

    def parse(self, user_input: str) -> dict[str, Any]:
        """用户话 -> {tool, arguments}。任何异常都降级到规则解析。"""
        if not self._ensure_model():
            return rule_parse(user_input)

        try:
            import torch

            messages = [{"role": "user", "content": (
                "把用户需求转换为白名单检索工具调用参数，只输出 JSON。\n"
                f"白名单工具：{', '.join(WHITELIST)}\n\n{user_input}"
            )}]
            try:
                prompt = self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True,
                    enable_thinking=False,
                )
            except TypeError:
                prompt = self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
            inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
            with torch.inference_mode():
                out = self._model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=False,
                    pad_token_id=self._tokenizer.pad_token_id or self._tokenizer.eos_token_id,
                )
            gen = self._tokenizer.decode(
                out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
            ).strip()
            logger.debug("模型原始输出：%r", gen)
            return normalize_intent(parse_json_lenient(gen), user_input)
        except Exception as e:  # noqa: BLE001
            logger.error("推理失败，降级规则解析：%s", e)
            return rule_parse(user_input)


    # ---------- v3：动作协议与第二轮点评 ----------

    def _generate(self, system: str, user: str, max_new_tokens: int | None = None) -> str:
        """按 system + user 生成文本（动作解析与点评复用）。"""
        import torch

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            prompt = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
        except TypeError:
            prompt = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
        with torch.inference_mode():
            out = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens or self.max_new_tokens,
                do_sample=False,
                pad_token_id=self._tokenizer.pad_token_id or self._tokenizer.eos_token_id,
            )
        return self._tokenizer.decode(
            out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        ).strip()

    def parse_action(self, user_input: str) -> dict[str, Any]:
        """v3 入口：返回 {action: tool|reply, ...}；任何异常都退回规则动作。"""
        if not self._ensure_model():
            return as_action(rule_parse(user_input))
        try:
            generated = self._generate(V3_SYSTEM_PROMPT, user_input)
            logger.debug("模型动作原始输出：%r", generated)
            return normalize_action(parse_json_lenient(generated), user_input)
        except Exception as exc:  # noqa: BLE001
            logger.error("动作解析失败，降级规则：%s", exc)
            return as_action(rule_parse(user_input))

    def comment(self, user_input: str, items_json: str) -> str | None:
        """第二轮点评：基于检索结果写 60-120 字；失败返回 None 由调用方降级模板。"""
        if not self._ensure_model():
            return None
        try:
            user = (
                f"用户想要{user_input}，检索结果：\n{items_json}\n"
                "请基于以上字段写 60-120 字的点评。"
            )
            generated = self._generate(V3_SYSTEM_PROMPT, user, max_new_tokens=200)
            payload = parse_json_lenient(generated)
            if not payload:
                return None
            text = str(payload.get("text") or "").strip()
            return text or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("点评生成失败：%s", exc)
            return None


__all__ = [
    "IntentParser",
    "closest_tool",
    "parse_json_lenient",
    "rule_parse",
    "normalize_intent",
    "normalize_action",
    "as_action",
    "WHITELIST",
    "TOOLS",
    "CATEGORIES",
]