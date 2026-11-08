"""5.3.2 工具调用准确率评测（任务书要求 10 轮 ≥90%）。

任务书原文：「单轮 + 多轮推理测试，统计工具调用准确率」，
报告要求：「工具调用准确率（10 轮目标 ≥90%）」。

**评测口径（写清楚，避免报告被质疑）**：
  一条算「命中」必须同时满足：
    1. 工具名对（走白名单纠错后的结果，纠错规则见 intent_parser.closest_tool）
    2. 三个参数全对：query（忽略空格差异）、category、top_k
  满分 10 条，准确率 = 命中数 / 10。**不放宽任何一条**。

**两种评测模式**：
  --mode rule     不加载模型，用规则解析跑（无 GPU 也能出数字，用于验证评测脚本本身）
  --mode model    加载 5.2 微调模型跑（真实成绩，需要 ~8GB 显存）

用法：
    # 先验证评测脚本本身（无 GPU）
    python scripts/agent/eval_tool_accuracy.py --mode rule

    # 真实微调模型评测
    python scripts/agent/eval_tool_accuracy.py --mode model \
        --model Qwen/Qwen3-4B-Instruct-2507 \
        --adapter dist/lora_adapter
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.agent.intent_parser import (  # noqa: E402
    IntentParser,
    normalize_intent,
    parse_json_lenient,
    rule_parse,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# 10 轮评测集。刻意覆盖 9 个类目 + 1 条不带类目的兜底，
# 与 5.1 的 intent/tool_call 样本格式一致，便于报告交叉引用。
CASES: list[dict[str, Any]] = [
    {"id": 1, "input": "帮我找黑色木纹手机壳，5个",
     "gold": {"tool": "text_search",
              "arguments": {"query": "黑色 木纹手机壳", "category": "手机壳", "top_k": 5}}},
    {"id": 2, "input": "我想找白色运动鞋",
     "gold": {"tool": "text_search",
              "arguments": {"query": "白色 运动鞋", "category": "鞋", "top_k": 5}}},
    {"id": 3, "input": "推荐3个蓝色运动水杯",
     "gold": {"tool": "text_search",
              "arguments": {"query": "蓝色 运动水杯", "category": "水杯", "top_k": 3}}},
    {"id": 4, "input": "找卡其色立领夹克",
     "gold": {"tool": "text_search",
              "arguments": {"query": "卡其色 立领夹克", "category": "男装", "top_k": 5}}},
    {"id": 5, "input": "有没有灰色的双肩包",
     "gold": {"tool": "text_search",
              "arguments": {"query": "灰色 双肩包", "category": "包", "top_k": 5}}},
    {"id": 6, "input": "红色带盖炒锅",
     "gold": {"tool": "text_search",
              "arguments": {"query": "红色 带盖炒锅", "category": "厨房用品", "top_k": 5}}},
    {"id": 7, "input": "帮我搜透明玻璃杯，10个",
     "gold": {"tool": "text_search",
              "arguments": {"query": "透明 玻璃杯", "category": "水杯", "top_k": 10}}},
    {"id": 8, "input": "黑色运动长袖套装",
     "gold": {"tool": "text_search",
              "arguments": {"query": "黑色 运动长袖套装", "category": "运动服", "top_k": 5}}},
    {"id": 9, "input": "找一下白色T恤",
     "gold": {"tool": "text_search",
              "arguments": {"query": "白色 T恤", "category": "女装", "top_k": 5}}},
    {"id": 10, "input": "随便看看有什么",
     "gold": {"tool": "text_search",
              "arguments": {"query": "随便看看有什么", "top_k": 5}}},
]


def normalize_text(s: Any) -> str:
    """query 比对时忽略空格与标点差异——模型加不加空格不算错。"""
    return "".join(str(s or "").split())


def score_one(pred: dict, gold: dict) -> tuple[bool, dict]:
    """严格口径：工具名 + 三个参数全对才算命中。"""
    tool_ok = pred.get("tool") == gold.get("tool")
    pa, ga = pred.get("arguments") or {}, gold.get("arguments") or {}

    query_ok = normalize_text(pa.get("query")) == normalize_text(ga.get("query"))
    cat_ok = (pa.get("category") or "") == (ga.get("category") or "")
    try:
        topk_ok = int(pa.get("top_k", 0)) == int(ga.get("top_k", 0))
    except (TypeError, ValueError):
        topk_ok = False

    hit = tool_ok and query_ok and cat_ok and topk_ok
    return hit, {
        "tool_ok": tool_ok,
        "query_ok": query_ok,
        "category_ok": cat_ok,
        "top_k_ok": topk_ok,
    }


def run_rule_mode() -> list[dict]:
    """规则模式：验证评测脚本逻辑，不需要 GPU。
    注意：规则解析不会自己补颜色词到 query，所以这里预期得分为中等——
    它衡量的是「评测脚本能否正确判分」，不是模型性能。
    """
    results = []
    for case in CASES:
        pred = rule_parse(case["input"])
        hit, detail = score_one(pred, case["gold"])
        results.append({"id": case["id"], "input": case["input"],
                        "pred": pred, "gold": case["gold"],
                        "hit": hit, **detail})
    return results


def run_model_mode(model: str, adapter: str | None, no_4bit: bool) -> list[dict]:
    """真实模型模式。"""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    quant_config = None
    if not no_4bit:
        try:
            import bitsandbytes  # noqa: F401
            from transformers import BitsAndBytesConfig

            quant_config = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
            )
        except ImportError:
            print("[warn] 无 bitsandbytes，全精度加载（显存需求翻倍）")

    tok = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
    m = AutoModelForCausalLM.from_pretrained(
        model, quantization_config=quant_config, torch_dtype=torch.bfloat16,
        device_map="auto", trust_remote_code=True,
    )
    if adapter:
        from peft import PeftModel
        m = PeftModel.from_pretrained(m, adapter)
    m.eval()

    results = []
    for case in CASES:
        messages = [{"role": "user", "content": (
            "把用户需求转换为白名单检索工具调用参数，只输出 JSON。\n"
            "白名单工具：text_search\n\n" + case["input"]
        )}]
        try:
            prompt = tok.apply_chat_template(messages, tokenize=False,
                                             add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt, return_tensors="pt").to(m.device)
        with torch.inference_mode():
            out = m.generate(**inputs, max_new_tokens=128, do_sample=False,
                             pad_token_id=tok.pad_token_id or tok.eos_token_id)
        raw = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

        pred = normalize_intent(parse_json_lenient(raw), case["input"])
        hit, detail = score_one(pred, case["gold"])
        results.append({"id": case["id"], "input": case["input"], "raw": raw,
                        "pred": pred, "gold": case["gold"], "hit": hit, **detail})
        print(f"[{case['id']:2d}/10] {'✓' if hit else '✗'}  {case['input'][:24]}")
    return results


def report(results: list[dict], mode: str, out: Path) -> float:
    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    acc = hits / total if total else 0.0

    print("\n" + "=" * 62)
    print(f"工具调用准确率（{mode} 模式，{total} 轮）")
    print("=" * 62)

    for r in results:
        mark = "✓" if r["hit"] else "✗"
        fails = [k.replace("_ok", "") for k in
                 ("tool_ok", "query_ok", "category_ok", "top_k_ok") if not r[k]]
        print(f"{mark} #{r['id']:2d}  {r['input'][:26]:28s}"
              + ("" if r["hit"] else f"  失败项: {','.join(fails)}"))

    print("-" * 62)
    print(f"命中 {hits}/{total} = {acc:.0%}   目标 ≥90% → {'达标' if acc >= 0.9 else '未达标'}")

    # 分项统计，报告里能看出是哪一环弱
    for key, label in [("tool_ok", "工具名"), ("query_ok", "query"),
                       ("category_ok", "类目"), ("top_k_ok", "top_k")]:
        ok = sum(1 for r in results if r[key])
        print(f"  {label:8s} {ok}/{total} = {ok / total:.0%}")

    payload = {"mode": mode, "total": total, "hits": hits,
               "accuracy": round(acc, 4), "target": 0.9,
               "passed": acc >= 0.9, "details": results}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n明细已写入：{out}")
    return acc


def main() -> None:
    ap = argparse.ArgumentParser(description="5.3.2 工具调用准确率评测")
    ap.add_argument("--mode", choices=["rule", "model"], default="rule")
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--no-4bit", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    out = args.out or (REPO_ROOT / f"data/agent/eval_tool_accuracy_{args.mode}.json")

    if args.mode == "rule":
        print("规则模式：不加载模型，用于验证评测脚本本身的判分逻辑\n")
        results = run_rule_mode()
    else:
        results = run_model_mode(args.model, args.adapter, args.no_4bit)

    acc = report(results, args.mode, out)
    raise SystemExit(0 if acc >= 0.9 else 1)


if __name__ == "__main__":
    main()