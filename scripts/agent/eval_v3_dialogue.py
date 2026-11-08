#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent v3 对话/工具能力评测（40 条）。

判分口径（对应 docs/实验五/10-5.4-对话Agent训练规范.md §八）：
  * JSON 可解析率：解析失败直接算错；
  * action 判断：tool / reply 是否对；
  * 工具名与参数：query / category / top_k / alpha；
  * 回复安全：不得出现价格、销量、折扣等词；
  * 结果点评：非空且不编造价格。

用法：
    python scripts/agent/eval_v3_dialogue.py --dry-run          # 只打印用例
    python scripts/agent/eval_v3_dialogue.py \
        --model models/models/Qwen--Qwen3-4B-Instruct-2507/snapshots/master \
        --adapter dist/lora_adapter_v3
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_dialogue_sft import SYSTEM_PROMPT  # noqa: E402

OUT_PATH = REPO_ROOT / "data" / "agent" / "eval_v3_dialogue.json"

# 只拦「具体价格断言」：199元 / 售价 99 / 5折（允许“库里没有价格信息”这类说明）
PRICE_WORDS = re.compile(r"(\d+(?:\.\d+)?\s*元)|((?:售价|价格)\s*[为是:：]?\s*\d)|(\d+\s*折)")
JSON_BLOCK = re.compile(r"\{.*\}", re.S)

# 结果点评用例里的商品上下文（真实字段风格）
_ITEMS_CTX = [
    {"item_name": "高帮鞋男欧货", "type": "高帮运动鞋", "color": "白色", "material": "未识别", "similarity": 0.47},
    {"item_name": "真皮y3高帮男鞋", "type": "高帮运动鞋", "color": "白色", "material": "真皮", "similarity": 0.47},
    {"item_name": "小白鞋男生小码", "type": "休闲鞋", "color": "白色", "material": "未识别", "similarity": 0.46},
    {"item_name": "白色运动鞋男", "type": "运动鞋", "color": "白色", "material": "网布", "similarity": 0.45},
    {"item_name": "透气跑步鞋", "type": "跑步鞋", "color": "白色", "material": "未识别", "similarity": 0.44},
]


def _comment_input(query: str) -> str:
    payload = {"items": _ITEMS_CTX}
    return (
        f"用户想要{query}，检索结果：\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\n请基于以上字段写 60-120 字的点评。"
    )


CASES: list[dict] = [
    # ---------- 工具：text_search（10） ----------
    {"id": 1, "input": "找一双白色运动鞋", "expect": {"action": "tool", "tool": "text_search", "query": "白色运动鞋", "category": "鞋", "top_k": 5}},
    {"id": 2, "input": "有没有黑色的双肩包", "expect": {"action": "tool", "tool": "text_search", "query": "黑色的双肩包", "category": "包", "top_k": 5}, "accept_category": ["包"]},
    {"id": 3, "input": "推荐3个蓝色运动水杯", "expect": {"action": "tool", "tool": "text_search", "query": "蓝色运动水杯", "category": "水杯", "top_k": 3}},
    {"id": 4, "input": "白色保温杯", "expect": {"action": "tool", "tool": "text_search", "query": "白色保温杯", "category": "水杯", "top_k": 5}},
    {"id": 5, "input": "找卡其色立领夹克", "expect": {"action": "tool", "tool": "text_search", "query": "卡其色立领夹克", "category": "男装", "top_k": 5}},
    {"id": 6, "input": "帮我搜透明玻璃杯，10个", "expect": {"action": "tool", "tool": "text_search", "query": "透明玻璃杯", "category": "水杯", "top_k": 10}},
    {"id": 7, "input": "黑色运动长袖套装", "expect": {"action": "tool", "tool": "text_search", "query": "黑色运动长袖套装", "category": "运动服", "top_k": 5}},
    {"id": 8, "input": "红色带盖炒锅", "expect": {"action": "tool", "tool": "text_search", "query": "红色带盖炒锅", "category": "厨房用品", "top_k": 5}},
    {"id": 9, "input": "灰色双肩包", "expect": {"action": "tool", "tool": "text_search", "query": "灰色双肩包", "category": "包", "top_k": 5}},
    {"id": 10, "input": "粉色女士连衣裙", "expect": {"action": "tool", "tool": "text_search", "query": "粉色女士连衣裙", "category": "女装", "top_k": 5}},
    # ---------- 工具：image / list / detail（10） ----------
    {"id": 11, "input": "按这张图找类似的", "expect": {"action": "tool", "tool": "image_search", "alpha_range": [0.3, 0.9]}},
    {"id": 12, "input": "和这张图像的商品", "expect": {"action": "tool", "tool": "image_search", "alpha_range": [0.3, 0.9]}},
    {"id": 13, "input": "这张图里的东西有卖吗", "expect": {"action": "tool", "tool": "image_search", "alpha_range": [0.3, 0.9]}},
    {"id": 14, "input": "我传了张图，找相近的", "expect": {"action": "tool", "tool": "image_search", "alpha_range": [0.3, 0.9]}},
    {"id": 15, "input": "你们能搜哪些类目", "expect": {"action": "tool", "tool": "list_categories"}},
    {"id": 16, "input": "库里有什么商品", "expect": {"action": "tool", "tool": "list_categories"}},
    {"id": 17, "input": "都支持哪些品类", "expect": {"action": "tool", "tool": "list_categories"}},
    {"id": 18, "input": "第二个是什么材质", "expect": {"action": "tool", "tool": "get_item_detail", "item_id_present": True}},
    {"id": 19, "input": "帮我看看第 1 个商品的详情", "expect": {"action": "tool", "tool": "get_item_detail", "item_id_present": True}},
    {"id": 20, "input": "第3个商品的颜色是什么", "expect": {"action": "tool", "tool": "get_item_detail", "item_id_present": True}},
    # ---------- 结果点评（10） ----------
    {"id": 21, "input": _comment_input("白色运动鞋"), "expect": {"action": "reply", "reply_safe": True}},
    {"id": 22, "input": _comment_input("高帮鞋"), "expect": {"action": "reply", "reply_safe": True}},
    {"id": 23, "input": _comment_input("小白鞋"), "expect": {"action": "reply", "reply_safe": True}},
    {"id": 24, "input": _comment_input("跑步鞋"), "expect": {"action": "reply", "reply_safe": True}},
    {"id": 25, "input": _comment_input("运动鞋"), "expect": {"action": "reply", "reply_safe": True}},
    {"id": 26, "input": _comment_input("休闲鞋"), "expect": {"action": "reply", "reply_safe": True}},
    {"id": 27, "input": _comment_input("白色球鞋"), "expect": {"action": "reply", "reply_safe": True}},
    {"id": 28, "input": _comment_input("男款运动鞋"), "expect": {"action": "reply", "reply_safe": True}},
    {"id": 29, "input": _comment_input("透气鞋"), "expect": {"action": "reply", "reply_safe": True}},
    {"id": 30, "input": _comment_input("真皮鞋"), "expect": {"action": "reply", "reply_safe": True}},
    # ---------- 对话 / 澄清（10） ----------
    {"id": 31, "input": "你好", "expect": {"action": "reply", "reply_safe": True}},
    {"id": 32, "input": "你能干什么", "expect": {"action": "reply", "reply_safe": True}},
    {"id": 33, "input": "你是谁", "expect": {"action": "reply", "reply_safe": True}},
    {"id": 34, "input": "帮我写代码", "expect": {"action": "reply", "reply_safe": True}},
    {"id": 35, "input": "今天天气怎么样", "expect": {"action": "reply", "reply_safe": True}},
    {"id": 36, "input": "随便看看", "expect": {"action": "reply", "reply_safe": True}},
    {"id": 37, "input": "都行", "expect": {"action": "reply", "reply_safe": True}},
    {"id": 38, "input": "便宜的", "expect": {"action": "reply", "reply_safe": True}},
    {"id": 39, "input": "谢谢", "expect": {"action": "reply", "reply_safe": True}},
    {"id": 40, "input": "能退货吗", "expect": {"action": "reply", "reply_safe": True}},
]


def parse_json_lenient(text: str) -> dict | None:
    """容忍 ```json 包裹、前后寒暄，取出第一个 JSON 对象。"""
    if not text:
        return None
    match = JSON_BLOCK.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _norm(value: object) -> str:
    return str(value or "").replace(" ", "").strip()


def score_case(case: dict, raw: str) -> dict:
    expect = case["expect"]
    payload = parse_json_lenient(raw)
    detail = {
        "id": case["id"],
        "input": case["input"][:40],
        "raw": raw.strip()[:200],
        "json_ok": payload is not None,
        "action_ok": False,
        "tool_ok": False,
        "args_ok": False,
        "safe_ok": False,
        "hit": False,
        "reason": "",
    }
    if payload is None:
        detail["reason"] = "JSON 解析失败"
        return detail

    detail["action_ok"] = payload.get("action") == expect["action"]
    if not detail["action_ok"]:
        detail["reason"] = f"action={payload.get('action')} 期望 {expect['action']}"
        return detail

    if expect["action"] == "tool":
        detail["tool_ok"] = payload.get("tool") == expect.get("tool")
        args = payload.get("arguments") or {}
        if not detail["tool_ok"]:
            detail["reason"] = f"tool={payload.get('tool')} 期望 {expect.get('tool')}"
            return detail

        ok = True
        if "query" in expect:
            ok = ok and _norm(args.get("query")) == _norm(expect["query"])
        if "category" in expect:
            accepted = case.get("accept_category") or [expect["category"]]
            ok = ok and args.get("category") in accepted
        if "top_k" in expect:
            try:
                ok = ok and int(args.get("top_k", 0)) == int(expect["top_k"])
            except (TypeError, ValueError):
                ok = False
        if "alpha_range" in expect:
            low, high = expect["alpha_range"]
            try:
                ok = ok and low <= float(args.get("alpha", 0)) <= high
            except (TypeError, ValueError):
                ok = False
        if expect.get("item_id_present"):
            ok = ok and bool(str(args.get("item_id") or "").strip())
        detail["args_ok"] = ok
        detail["safe_ok"] = True
        detail["hit"] = ok
        if not ok:
            detail["reason"] = f"arguments 不符：{args}"
        return detail

    # reply 分支
    text = str(payload.get("text") or "").strip()
    safe = bool(text) and not PRICE_WORDS.search(text)
    detail["safe_ok"] = safe
    detail["args_ok"] = safe
    detail["tool_ok"] = True
    detail["hit"] = safe
    if not text:
        detail["reason"] = "reply 为空"
    elif not safe:
        detail["reason"] = "reply 含价格/销量词"
    return detail


def run_model(model: str, adapter: str | None, no_4bit: bool) -> list[dict]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    quant_config = None
    if not no_4bit:
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
            print("[warn] 无 bitsandbytes，按 bf16 加载（显存需求翻倍）")

    tokenizer = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
    net = AutoModelForCausalLM.from_pretrained(
        model,
        quantization_config=quant_config,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    if adapter:
        from peft import PeftModel

        net = PeftModel.from_pretrained(net, adapter)
    net.eval()

    results = []
    for case in CASES:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": case["input"]},
        ]
        try:
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
        except TypeError:
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        inputs = tokenizer(prompt, return_tensors="pt").to(net.device)
        with torch.inference_mode():
            out = net.generate(
                **inputs,
                max_new_tokens=160,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            )
        raw = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        detail = score_case(case, raw)
        results.append(detail)
        flag = "✓" if detail["hit"] else "✗"
        print(f"[{case['id']:>2}/40] {flag} {case['input'][:32]!r} {detail['reason']}")
    return results


def summarize(results: list[dict]) -> dict:
    total = len(results)
    json_ok = sum(1 for r in results if r["json_ok"])
    action_ok = sum(1 for r in results if r["action_ok"])
    hit = sum(1 for r in results if r["hit"])
    tool_cases = [r for r in results if r.get("tool_ok") or not r["json_ok"] or not r["action_ok"]]
    safe_cases = [r for r in results if r["action_ok"]]
    safe_ok = sum(1 for r in safe_cases if r["safe_ok"])
    return {
        "total": total,
        "json_ok": json_ok,
        "action_ok": action_ok,
        "hit": hit,
        "tool_or_args_ok": sum(1 for r in results if r["hit"] and r["action_ok"]),
        "safe_ok": safe_ok,
        "safe_total": len(safe_cases),
        "failed": [r["id"] for r in results if not r["hit"]],
        "json_rate": round(json_ok / total, 4),
        "action_rate": round(action_ok / total, 4),
        "hit_rate": round(hit / total, 4),
        "safe_rate": round(safe_ok / max(1, len(safe_cases)), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent v3 对话/工具评测（40 条）")
    parser.add_argument("--model", default="", help="基座模型路径或 HF id")
    parser.add_argument("--adapter", default="", help="LoRA 适配器目录")
    parser.add_argument("--no-4bit", action="store_true", help="不量化加载（显存足够时）")
    parser.add_argument("--dry-run", action="store_true", help="只打印用例，不加载模型")
    parser.add_argument("--out", default=str(OUT_PATH), help="结果 JSON 输出路径")
    args = parser.parse_args()

    if args.dry_run:
        for case in CASES:
            print(f"{case['id']:>2}. {case['input'][:60]!r} → {case['expect']}")
        print(f"\n共 {len(CASES)} 条用例（工具 20 / 点评 10 / 对话 10）")
        return 0

    if not args.model:
        parser.error("必须提供 --model（或先用 --dry-run 查看用例）")

    results = run_model(args.model, args.adapter or None, args.no_4bit)
    summary = summarize(results)

    print("\n" + "=" * 60)
    print("Agent v3 评测结果（40 条）")
    print("=" * 60)
    print(f"JSON 可解析   {summary['json_ok']}/{summary['total']}  ({summary['json_rate']:.1%})")
    print(f"action 正确   {summary['action_ok']}/{summary['total']}  ({summary['action_rate']:.1%})")
    print(f"整体命中      {summary['hit']}/{summary['total']}  ({summary['hit_rate']:.1%})")
    print(f"回复安全      {summary['safe_ok']}/{summary['safe_total']}  ({summary['safe_rate']:.1%})")
    if summary["failed"]:
        print(f"未通过用例：{summary['failed']}")

    passed = summary["hit_rate"] >= 0.9 and summary["action_rate"] >= 0.9 and summary["json_rate"] >= 0.95
    print("达标（≥90% 命中 / ≥90% action / ≥95% JSON）" if passed else "未达标，见上方失败项")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n明细已写入：{out_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
