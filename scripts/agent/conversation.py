"""多轮对话与槽位继承（任务书 5.3.2「单轮 + 多轮推理测试」）。

方案 §9 原本把「对话历史存哪」列为待定。这里定为：**后端内存会话**
（不进 Redis，不依赖前端 localStorage），理由是演示场景单机即可，
且 5.4 的 `/api/v1/agent/chat` 本来就在后端。

核心能力是**槽位继承**：
    用户：我想找手机壳
    用户：黑色的，5 个          ← 这里不该重新问"你要找什么类目"

4B 模型在多轮里很容易丢失上文类目，所以槽位由代码显式维护，
比单纯依赖模型记忆可靠得多。这与「LLM 只做意图解析、事实来自接口」
的报告口径一致——槽位继承是工程逻辑，不该指望参数量。

用法：
    from scripts.agent.conversation import ConversationStore

    store = ConversationStore()
    r1 = store.chat("s1", "我想找手机壳")
    r2 = store.chat("s1", "黑色的，5个")     # 自动继承 category=手机壳
    r2["slots"]  # {"category": "手机壳", "top_k": 5}
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("shopvision.conversation")

CATEGORIES = ["鞋", "水杯", "包", "男装", "运动服", "女装", "手机壳", "厨房用品", "家居用品"]

# 颜色词，用于合并进 query
COLORS = ["白色", "黑色", "红色", "蓝色", "灰色", "卡其色", "米色", "粉色", "绿色",
          "黄色", "紫色", "棕色", "银色", "金色", "透明"]

# 「还有别的吗」「换一批」这类追问，应沿用上一轮参数只翻页/重查
FOLLOWUP_PATTERNS = [
    r"还有(别的|其他|更多)",
    r"换(一批|一个)",
    r"再(来|找|搜)",
    r"其他的?呢",
    r"有没有(别的|其他)",
]


@dataclass
class Slot:
    """一次会话累积的检索条件。"""

    category: str | None = None
    query_parts: list[str] = field(default_factory=list)
    top_k: int = 5
    last_query: str | None = None

    def build_query(self) -> str:
        """把累积的词拼成检索词。去重保序。"""
        seen: set[str] = set()
        parts: list[str] = []
        for p in self.query_parts:
            p = p.strip()
            if p and p not in seen:
                seen.add(p)
                parts.append(p)
        return " ".join(parts) if parts else (self.last_query or "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "query": self.build_query(),
            "top_k": self.top_k,
        }


@dataclass
class Session:
    """一个会话的历史与槽位。"""

    thread_id: str
    slots: Slot = field(default_factory=Slot)
    turns: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def extract_category(text: str) -> str | None:
    """从一句话里抓类目。越长越具体优先（如「手机壳」优先于「鞋」）。"""
    hits = [c for c in CATEGORIES if c in text]
    if not hits:
        return None
    return max(hits, key=len)


def extract_top_k(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(?:个|件|条|款)", text)
    if not m:
        return None
    return max(1, min(int(m.group(1)), 20))


def extract_colors(text: str) -> list[str]:
    return [c for c in COLORS if c in text]


def is_followup(text: str) -> bool:
    """是否「还有别的吗」这类追问。"""
    return any(re.search(p, text) for p in FOLLOWUP_PATTERNS)


def strip_noise(text: str) -> str:
    """去掉指令性词缀，留检索词。"""
    out = text
    for noise in ["帮我找", "帮我搜", "我想找", "想找", "搜索", "找一下", "推荐",
                  "给我", "来点", "看看", "一下", "吧", "呢", "的", "，", ",", "。"]:
        out = out.replace(noise, " ")
    return re.sub(r"\s+", " ", out).strip()


def resolve_slots(session: Session, user_input: str) -> Slot:
    """把这一句的信息合并进会话槽位（多轮继承的核心）。

    规则：
      1. 句子里有新类目 -> 覆盖旧类目
      2. 句子里有新数量 -> 覆盖 top_k
      3. 句子里有颜色但没类目 -> 视为对上文的补充，并入 query
      4. 「还有别的吗」 -> 全部沿用上一轮
    """
    slots = session.slots
    text = user_input or ""

    category = extract_category(text)
    if category:
        slots.category = category
        # 换类目等于换话题，清掉旧的描述词，避免「手机壳」和「运动鞋」混在一起
        slots.query_parts = []

    top_k = extract_top_k(text)
    if top_k:
        slots.top_k = top_k

    if is_followup(text):
        # 追问：不改条件
        return slots

    colors = extract_colors(text)
    cleaned = strip_noise(text)
    # 去掉数量词和类目词，剩下的才是有效的描述词
    cleaned = re.sub(r"\d+\s*(?:个|件|条|款)", "", cleaned).strip()
    if category:
        cleaned = cleaned.replace(category, "").strip()

    if colors:
        # 颜色单独成词，便于和上一轮拼接
        for c in colors:
            cleaned = cleaned.replace(c, "").strip()
        for c in colors:
            if c not in slots.query_parts:
                slots.query_parts.append(c)

    # 剩下的描述（如「立领夹克」「木纹硬壳」）作为补充词
    if cleaned and len(cleaned) >= 2:
        # 避免把整句重复塞进去
        if cleaned not in slots.query_parts:
            slots.query_parts.append(cleaned)

    return slots


class ConversationStore:
    """内存会话存储。线程安全不是重点（演示单进程），但要能清理。"""

    def __init__(self, ttl_seconds: int = 3600):
        self._sessions: dict[str, Session] = {}
        self._ttl = ttl_seconds

    def new_thread_id(self) -> str:
        return f"s-{uuid.uuid4().hex[:12]}"

    def get(self, thread_id: str) -> Session:
        self._evict_expired()
        if thread_id not in self._sessions:
            self._sessions[thread_id] = Session(thread_id=thread_id)
        s = self._sessions[thread_id]
        s.updated_at = time.time()
        return s

    def reset(self, thread_id: str) -> None:
        self._sessions.pop(thread_id, None)

    def _evict_expired(self) -> None:
        now = time.time()
        dead = [k for k, v in self._sessions.items() if now - v.updated_at > self._ttl]
        for k in dead:
            self._sessions.pop(k, None)

    def chat(
        self,
        thread_id: str,
        user_input: str,
        executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """走一轮对话：解析槽位 -> 调 executor -> 记录历史。

        Args:
            thread_id: 会话 ID
            user_input: 用户这句话
            executor: 实际执行函数，接收 intent dict，返回结果 dict。
                      不传则只做槽位解析（用于单测 / 无模型演示）。

        Returns:
            {"reply": str, "intent": {...}, "slots": {...}, "result": {...}}
        """
        session = self.get(thread_id)
        slots = resolve_slots(session, user_input)
        query = slots.build_query()

        intent: dict[str, Any] = {"tool": "text_search", "arguments": {"query": query,
                                                                     "top_k": slots.top_k}}
        if slots.category:
            intent["arguments"]["category"] = slots.category

        result: dict[str, Any] = {}
        if executor is not None:
            try:
                result = executor(intent)
            except Exception as e:  # noqa: BLE001
                logger.error("executor 失败：%s", e)
                result = {"ok": False, "reason": str(e)}

        session.turns.append({
            "role": "user", "content": user_input,
            "intent": intent, "slots": slots.to_dict(),
            "at": time.time(),
        })
        if result:
            session.turns.append({"role": "assistant", "result": result, "at": time.time()})
        session.slots.last_query = query

        return {
            "reply": _compose_reply(result, slots),
            "intent": intent,
            "slots": slots.to_dict(),
            "result": result,
        }

    def history(self, thread_id: str) -> list[dict[str, Any]]:
        return self.get(thread_id).turns


def _compose_reply(result: dict[str, Any], slots: Slot) -> str:
    """把结果拼成一句人话。无结果时给明确提示，不假装成功。"""
    if not result:
        return ""

    if result.get("ok") is False:
        return f"检索失败了：{result.get('reason') or '服务暂时不可用，请稍后再试'}"

    items = ((result.get("result") or {}).get("items")) or result.get("items") or []
    if not items:
        cat = f"{slots.category}类的" if slots.category else ""
        return f"没找到符合条件的{cat}商品，换个描述试试？"

    names = [it.get("item_name") for it in items[:3] if it.get("item_name")]
    cat = f"{slots.category}类" if slots.category else ""
    head = f"在{cat}找到 {len(items)} 件商品"
    if names:
        return f"{head}，例如：{'、'.join(names)}。"
    return f"{head}。"


__all__ = [
    "CATEGORIES",
    "COLORS",
    "Slot",
    "Session",
    "ConversationStore",
    "extract_category",
    "extract_top_k",
    "extract_colors",
    "is_followup",
    "resolve_slots",
]