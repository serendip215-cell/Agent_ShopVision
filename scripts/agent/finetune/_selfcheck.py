"""评分函数的自检（不加载模型，纯逻辑验证）。

    python scripts/agent/finetune/_selfcheck.py

全部打印 PASS 才算评测脚本的判定逻辑可信。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.agent.finetune.eval_baseline_vs_lora import (  # noqa: E402
    parse_json_lenient,
    score_attribute,
    score_intent,
    score_tool_call,
)

failures: list[str] = []


def check(name: str, got, want) -> None:
    ok = abs(got - want) < 1e-9 if isinstance(want, (int, float)) else got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}  got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def main() -> None:
    gold_attr = "商品大类：鞋；细分类：高帮运动鞋；颜色：白色；材质：未识别"

    # 1. 完全一致 -> 1.0
    check("attribute 全对", score_attribute(gold_attr, gold_attr)[0], 1.0)

    # 2. 两项不同 -> 2/4 = 0.5
    half = "商品大类：鞋；细分类：休闲鞋；颜色：白色；材质：真皮"
    check("attribute 2/4", score_attribute(half, gold_attr)[0], 0.5)

    # 3. 输出为空 -> 0
    check("attribute 空输出", score_attribute("", gold_attr)[0], 0.0)

    gold_intent = json.dumps(
        {"intent": "search_products", "query": "黑色手机壳", "category": "手机壳", "top_k": 5},
        ensure_ascii=False,
    )

    # 4. 干净 JSON -> intent/category/top_k 全对 = 1.0
    check("intent 干净 JSON", score_intent(gold_intent, gold_intent)[0], 1.0)

    # 5. 带 markdown 包裹 + 前缀废话 -> 仍能解析出 JSON，得分 1.0
    wrapped = "好的，我帮您解析：\n```json\n" + gold_intent + "\n```"
    check("intent 包裹仍可解析", score_intent(wrapped, gold_intent)[0], 1.0)

    # 6. 完全不是 JSON -> 0
    check("intent 无 JSON", score_intent("我不知道", gold_intent)[0], 0.0)

    gold_tool = json.dumps(
        {"tool": "text_search",
         "arguments": {"query": "蓝色运动水杯", "category": "水杯", "top_k": 5}},
        ensure_ascii=False,
    )

    # 7. 完全一致 -> 1.0
    check("tool_call 全对", score_tool_call(gold_tool, gold_tool)[0], 1.0)

    # 8. 工具名错（白名单硬约束）-> 直接 0
    wrong_tool = json.dumps(
        {"tool": "image_search",
         "arguments": {"query": "蓝色运动水杯", "category": "水杯", "top_k": 5}},
        ensure_ascii=False,
    )
    check("tool_call 工具名错 -> 0", score_tool_call(wrong_tool, gold_tool)[0], 0.0)

    # 9. 工具名对、参数对 2/3 -> (1+2)/(1+3) = 0.75
    partial = json.dumps(
        {"tool": "text_search",
         "arguments": {"query": "蓝色运动水杯", "category": "水杯", "top_k": 3}},
        ensure_ascii=False,
    )
    check("tool_call 参数 2/3", score_tool_call(partial, gold_tool)[0], 0.75)

    # 10. parse_json_lenient 对非 dict 的处理
    check("parse 数组返回 None", parse_json_lenient("[1,2,3]"), None)
    check("parse 纯对象", parse_json_lenient('{"a":1}'), {"a": 1})

    print()
    if failures:
        print(f"{len(failures)} 项失败：{failures}")
        raise SystemExit(1)
    print("全部通过")


if __name__ == "__main__":
    main()