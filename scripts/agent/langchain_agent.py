"""实验5 5.3 LangChain 版 Agent（对齐任务书 5.3.1）。

任务书原文：「LangChain 将实验4 的图像/文本分类 API 封装为工具，`create_agent` 初始化；
单轮 + 多轮推理测试」。

本模块就用 `langchain.agents.create_agent`（LangChain ≥1.0）实现，
与 `agent.py` 的自研极简版并存：

    自研版 agent.py       —— 零依赖兜底，无 LangChain / 无 GPU 时也能跑，用于演示降级
    本模块 langchain_agent.py —— 任务书要求的正式实现，走 LLM 工具调用 + 多轮记忆

设计要点：
  1. **工具封装**：实验4 的 `/api/v1/text`、`/api/v1/image`、`/api/v1/match`
     各自包成 `@tool`，description 写清参数，让模型自己选。
  2. **模型层**：用 `ChatOpenAI` 走 OpenAI 兼容接口。后端可以是
     - 本地微调模型起的 vLLM / Ollama 服务（OpenAI 兼容）
     - 或 DeepSeek / GLM 的官方 API
     这样 5.2 的 LoRA 和云端大模型都能接，不锁死。
  3. **多轮记忆**：用 LangGraph 的 `InMemorySaver` checkpointer，
     按 `thread_id` 隔离会话，实现任务书要求的「多轮推理」。
  4. **降级**：LangChain 装不上 / 模型连不上时，`create_shopvision_agent()`
     返回 None，调用方退回自研版。保证演示不会因为依赖问题崩掉。

用法：
    from scripts.agent.langchain_agent import create_shopvision_agent

    agent = create_shopvision_agent(base_url="http://localhost:8000/v1",
                                    model="qwen3-4b-shopvision")
    if agent:  # 走 LangChain
        result = agent.invoke(
            {"messages": [{"role": "user", "content": "我想找白色运动鞋"}]},
            config={"configurable": {"thread_id": "session-1"}},
        )
        print(result["messages"][-1].content)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("shopvision.langchain")

# 实验4 后端地址，与 tools.py 保持一致
API_BASE = os.environ.get("SHOPVISION_API_BASE", "http://localhost:8000")

# 是否装了 LangChain —— 用于上层判断走哪条实现
try:
    from langchain.agents import create_agent as _lc_create_agent
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langchain_core.tools import tool as _lc_tool

    LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover
    LANGCHAIN_AVAILABLE = False
    _lc_create_agent = None
    _lc_tool = None
    AIMessage = HumanMessage = ToolMessage = object  # type: ignore


def _http_post(path: str, payload: dict, timeout: int = 30) -> dict:
    """复用 tools.py 的裸 urllib 逻辑，避免引入 requests 依赖。"""
    import urllib.error
    import urllib.request

    url = f"{API_BASE}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.warning("%s HTTP %s", path, e.code)
        return {"error": f"服务返回 {e.code}", "items": []}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning("%s 请求失败：%s", path, e)
        return {"error": "检索服务不可用", "items": []}

    if body.get("code") != 0:
        return {"error": body.get("msg") or "调用失败", "items": []}
    return body.get("result") or {}


if LANGCHAIN_AVAILABLE:

    @_lc_tool
    def text_search(query: str, category: str = "", top_k: int = 5) -> str:
        """按中文文本检索商品，返回匹配的商品列表。

        Args:
            query: 检索词，如「白色运动鞋」「黑色木纹手机壳」
            category: 限定类目，可选。必须是：鞋/水杯/包/男装/运动服/女装/手机壳/厨房用品/家居用品
            top_k: 返回条数，默认 5，最大 20
        """
        from .intent_postprocessor import normalize_tool_call

        _, payload, _ = normalize_tool_call(
            "text_search",
            {"query": query, "category": category, "top_k": top_k},
            query,
            max_top_k=20,
        )
        result = _http_post("/api/v1/text", payload)
        if result.get("error"):
            return json.dumps({"error": result["error"]}, ensure_ascii=False)
        items = [
            {
                "item_id": it.get("item_id"),
                "item_name": it.get("item_name"),
                "category": it.get("category"),
                "similarity": it.get("similarity"),
            }
            for it in (result.get("items") or [])
        ]
        return json.dumps({"query": query, "items": items}, ensure_ascii=False)

    @_lc_tool
    def image_search(threshold: float = 0.3) -> str:
        """图像分类检索：上传的商品图属于哪个类目。

        注意：此工具需要图片已上传到后端，当前为占位实现，
        真实调用由 5.4 前端直连 `/api/v1/image`。

        Args:
            threshold: 置信度阈值
        """
        return json.dumps(
            {"note": "图像分类需前端上传图片后直调 /api/v1/image，此处仅占位",
             "threshold": threshold},
            ensure_ascii=False,
        )

    @_lc_tool
    def image_text_match(image_path: str, text: str) -> str:
        """判断一张图与一段文字是否匹配（图文一致性）。

        注意：当前为占位实现，真实调用由 5.4 前端直连 `/api/v1/match`。

        Args:
            image_path: 图片路径
            text: 待比对的文字描述
        """
        return json.dumps(
            {"note": "图文匹配由前端直调 /api/v1/match", "image_path": image_path, "text": text},
            ensure_ascii=False,
        )

    SHOPVISION_TOOLS = [text_search, image_search, image_text_match]
else:  # pragma: no cover
    SHOPVISION_TOOLS = []


SYSTEM_PROMPT = """你是 ShopVision 电商导购助手。

规则：
1. 只能通过提供的工具获取商品信息，**绝对不要编造商品名称、价格、ID**。
2. 用户说要找商品时，调用 text_search。查询词用用户原话里的关键描述。
3. 如果用户没指定类目，category 留空让后端自动判断。
4. 返回结果后，用自然中文简要说明找到了什么，不要把原始 JSON 直接丢给用户。
5. 如果工具返回错误，如实告诉用户「检索服务暂时不可用」，不要假装成功。
"""


def create_shopvision_agent(
    base_url: str | None = None,
    api_key: str | None = None,
    model: str = "qwen3-4b-shopvision",
    with_memory: bool = True,
):
    """创建 LangChain Agent。任何一步失败返回 None，调用方自行降级。

    Args:
        base_url: OpenAI 兼容接口地址。本地 vLLM 通常是 http://host:port/v1
        api_key: 接口密钥；本地服务随便填
        model: 模型名
        with_memory: 是否启用多轮记忆（InMemorySaver）
    """
    if not LANGCHAIN_AVAILABLE:
        logger.warning("未安装 LangChain，返回 None 让调用方降级")
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("未安装 langchain-openai，返回 None 让调用方降级")
        return None

    try:
        llm_kwargs: dict[str, Any] = {
            "model": model,
            "temperature": 0,          # 工具调用要确定性
            "timeout": 60,
            "max_retries": 1,
        }
        if base_url:
            llm_kwargs["base_url"] = base_url
        if api_key:
            llm_kwargs["api_key"] = api_key
        llm = ChatOpenAI(**llm_kwargs)

        agent_kwargs: dict[str, Any] = {
            "model": llm,
            "tools": SHOPVISION_TOOLS,
            "system_prompt": SYSTEM_PROMPT,
            "name": "shopvision_agent",
        }

        if with_memory:
            # LangGraph checkpointer：按 thread_id 隔离多轮会话
            try:
                from langgraph.checkpoint.memory import InMemorySaver

                agent_kwargs["checkpointer"] = InMemorySaver()
            except ImportError:
                logger.warning("langgraph 不可用，多轮记忆关闭")

        agent = _lc_create_agent(**agent_kwargs)
        logger.info("LangChain Agent 创建成功：model=%s tools=%d", model, len(SHOPVISION_TOOLS))
        return agent
    except Exception as e:  # noqa: BLE001
        logger.error("创建 LangChain Agent 失败：%s", e)
        return None


def run_once(agent, user_input: str, thread_id: str = "default") -> dict[str, Any]:
    """跑一轮对话，返回结构化结果（供 FastAPI / 测试用）。

    Returns:
        {"ok": bool, "reply": str, "tool_calls": [...], "messages": 原始消息数}
    """
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Agent 调用失败：%s", e)
        return {"ok": False, "reply": f"Agent 调用失败：{e}", "tool_calls": []}

    messages = result.get("messages", [])
    reply = ""
    tool_calls: list[dict[str, Any]] = []

    for msg in messages:
        if isinstance(msg, AIMessage):
            if getattr(msg, "tool_calls", None):
                tool_calls.extend([
                    {"name": tc.get("name"), "args": tc.get("args")}
                    for tc in msg.tool_calls
                ])
            if msg.content:
                reply = msg.content if isinstance(msg.content, str) else str(msg.content)

    return {
        "ok": bool(reply),
        "reply": reply,
        "tool_calls": tool_calls,
        "message_count": len(messages),
    }


def get_history(agent, thread_id: str) -> list[dict[str, str]]:
    """取出某个会话的完整历史（多轮验证用）。"""
    try:
        state = agent.get_state({"configurable": {"thread_id": thread_id}})
        msgs = state.values.get("messages", [])
    except Exception as e:  # noqa: BLE001
        logger.warning("读取历史失败：%s", e)
        return []

    out = []
    for m in msgs:
        if isinstance(m, HumanMessage):
            out.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            out.append({"role": "assistant", "content": m.content})
        elif isinstance(m, ToolMessage):
            out.append({"role": "tool", "content": str(m.content)[:200]})
    return out


__all__ = [
    "LANGCHAIN_AVAILABLE",
    "SHOPVISION_TOOLS",
    "SYSTEM_PROMPT",
    "create_shopvision_agent",
    "run_once",
    "get_history",
    "text_search",
    "image_search",
    "image_text_match",
]
