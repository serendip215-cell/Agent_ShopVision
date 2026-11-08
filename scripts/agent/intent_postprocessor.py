"""Shared post-processing for local and remote Agent tool calls."""

from __future__ import annotations

from typing import Any

from .category_map import fill_arguments

TOOL_ALIASES = {
    "tool_search": "text_search",
}

ALLOWED_TOOLS = {"text_search"}
ALLOWED_CATEGORIES = {
    "鞋", "水杯", "包", "男装", "运动服", "女装", "手机壳", "厨房用品", "家居用品"
}


def normalize_tool_call(
    tool: str | None,
    arguments: dict[str, Any] | None,
    user_text: str,
    *,
    max_top_k: int = 20,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Normalize a model tool call before executing the retrieval tool.

    This function is shared by the local AgentService and the remote
    LangChain tool path so both deployment modes have identical behavior.
    """
    normalized_tool = TOOL_ALIASES.get(str(tool or ""), str(tool or ""))
    raw_args = dict(arguments or {})
    if raw_args.get("category") not in ALLOWED_CATEGORIES:
        raw_args["category"] = ""
    args, notes = fill_arguments(raw_args, user_text)

    query = str(args.get("query") or "").strip()[:200]
    try:
        top_k = int(args.get("top_k") or 5)
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(top_k, max_top_k))

    category = args.get("category")
    if category not in ALLOWED_CATEGORIES:
        category = None

    normalized_args: dict[str, Any] = {"query": query, "top_k": top_k}
    if category:
        normalized_args["category"] = category

    if normalized_tool != tool and tool:
        notes["tool_normalized"] = {"from": tool, "to": normalized_tool}
    return normalized_tool, normalized_args, notes


__all__ = [
    "ALLOWED_CATEGORIES",
    "ALLOWED_TOOLS",
    "TOOL_ALIASES",
    "normalize_tool_call",
]
