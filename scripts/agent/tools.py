"""实验5 Agent 工具层：把实验4 的检索能力封装成 Agent 可调用的工具。

约定（与 scripts/agent/build_agent_finetune_data.py 的 tool_call 格式严格对齐）：
    模型学会的工具名是 text_search，参数是 {"query", "category", "top_k"}。
    本文件只实现 text_search 白名单工具——image_search / match 不属于 5.2
    训练数据，留给 5.4 前端/规则降级直接调，不走 LLM 工具调用（见交接文档）。

工具通过 HTTP 调实验4 后端 /api/v1/text（复用「文本分类页：中文查询→相关商品」），
不 import experiment4 内部服务层，因此本目录可在独立 conda 环境运行，与 backend 解耦。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("shopvision.agent.tools")

# 实验4 后端地址。默认本地；部署时用环境变量 SHOPVISION_TEXT_API 覆盖。
TEXT_SEARCH_API: str = "http://127.0.0.1:8000/api/v1/text"
TIMEOUT_SECONDS: float = 30.0


def text_search(query: str, top_k: int = 5, category: str | None = None) -> dict[str, Any]:
    """文搜商品。返回实验4 统一契约 {code, result, msg} 中的 result dict。

    参数与微调数据 arguments 对齐：
        query   用户检索词（1–200 字符）
        top_k   返回条数（1–50，默认 5）
        category 可选，限定类目；与模型判出的 class_category 不一致时返回空 items
    """
    payload = {"query": query, "top_k": top_k}
    if category:
        payload["category"] = category
    logger.info("tool text_search: query=%r top_k=%s category=%r", query, top_k, category)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TEXT_SEARCH_API, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.warning("text_search HTTP %s: %s", e.code, e.read().decode("utf-8", "replace"))
        return _error("text_search 服务返回异常")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning("text_search 请求失败：%s", e)
        return _error("检索服务不可用，请稍后重试")
    except ValueError:  # 响应不是合法 JSON
        logger.warning("text_search 响应非 JSON")
        return _error("检索服务响应异常")
    if body.get("code") != 0:
        logger.warning("text_search 业务错误：code=%s msg=%s", body.get("code"), body.get("msg"))
        return {"error": body.get("msg") or "检索失败", "code": body.get("code")}
    return body.get("result") or {}


def _error(msg: str) -> dict[str, Any]:
    return {"error": msg, "items": []}


TOOLS: dict[str, Any] = {
    "text_search": {
        "description": "按文本检索商品，返回匹配的商品列表。参数：query(必填，用户检索词)，category(可选，限定类目)，top_k(可选，返回条数，默认5)。",
        "fn": text_search,
    },
}


def get_tool(name: str) -> dict[str, Any] | None:
    """按工具名取工具（工具名 = 微调数据里模型学会的名字）。"""
    return TOOLS.get(name)