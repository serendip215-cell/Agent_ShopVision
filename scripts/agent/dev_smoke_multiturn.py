#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多轮自检：同一个 session 连发两句，看第二句有没有继承类目。

用法（后端已启动）：
    python scripts/agent/dev_smoke_multiturn.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1/agent/chat"
SESSION = "diag-session-1"


def call(message: str) -> dict:
    body = json.dumps({"message": message, "session_id": SESSION}).encode("utf-8")
    request = urllib.request.Request(
        BASE, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)["result"]
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def show(turn: str, message: str, result: dict) -> None:
    print(f"\n=== {turn}：{message} ===")
    if "error" in result:
        print("请求失败：", result["error"])
        return
    print("thinking:", json.dumps(result.get("thinking") or [], ensure_ascii=False))
    for call_info in result.get("tool_calls") or []:
        print("tool:", call_info.get("name"), json.dumps(call_info.get("arguments") or {}, ensure_ascii=False))
    items = result.get("items") or []
    print("items:", [(item.get("category"), item.get("item_name")) for item in items[:3]])
    print("reply:", (result.get("reply") or "")[:100].replace("\n", " / "))


def main() -> int:
    print("后端：", BASE)
    print("会话：", SESSION)

    first = call("找运动鞋")
    show("第 1 轮", "找运动鞋", first)

    second = call("要白色的")
    show("第 2 轮", "要白色的", second)

    if "error" in first or "error" in second:
        return 1

    args1 = (first.get("tool_calls") or [{}])[0].get("arguments") or {}
    args2 = (second.get("tool_calls") or [{}])[0].get("arguments") or {}
    categories = {item.get("category") for item in (second.get("items") or [])}

    print("\n=== 判定 ===")
    print("第 1 轮 category:", args1.get("category"), "query:", args1.get("query"))
    print("第 2 轮 category:", args2.get("category"), "query:", args2.get("query"))
    print("第 2 轮结果类目:", categories)

    query2 = str(args2.get("query") or "")
    inherited_category = args2.get("category") == "鞋"
    merged_query = "运动鞋" in query2 and "白色" in query2
    only_shoes = categories == {"鞋"}

    print("类目继承：", "✅" if inherited_category else "❌")
    print("查询合并：", "✅" if merged_query else f"❌（实际 {query2}）")
    print("结果纯鞋类：", "✅" if only_shoes else "❌")

    ok = inherited_category and merged_query and only_shoes
    print("多轮继承：", "✅ 通过" if ok else "❌ 失败")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
