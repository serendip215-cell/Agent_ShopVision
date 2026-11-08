"""5.2 评测：基座 vs LoRA 微调后的对比（任务书 5.2.2 要求）。

评测三类任务，各自有明确的机器判定口径，不靠人眼：

  attribute   —— 抽四个字段（大类/细分类/颜色/材质）比对，算字段级准确率
  intent      —— 解析出 JSON，比对 intent / category / top_k 三项
  tool_call   —— 解析出 JSON，比对 tool 名与 arguments 两个键

同时统计「输出是否为合法 JSON」，因为 5.3 的 _parse_intent 直接吃 JSON，
输出带解释性废话就等于不可用 —— 这是比准确率更硬的指标。

用法（仓库根目录，需要能加载基座权重）：

    # 1) 先测基座（未微调），产出基线分
    python scripts/agent/finetune/eval_baseline_vs_lora.py --model Qwen/Qwen3-4B-Instruct-2507

    # 2) 再测 LoRA 权重
    python scripts/agent/finetune/eval_baseline_vs_lora.py \
        --model Qwen/Qwen3-4B-Instruct-2507 \
        --adapter data/agent/finetune/run1/final_adapter \
        --tag lora

    # 3) 合并两份结果成对比表
    python scripts/agent/finetune/eval_baseline_vs_lora.py --compare \
        data/agent/finetune/eval_baseline.json \
        data/agent/finetune/eval_lora.json

单卡 4B 4-bit 下，11 条验证集约 1-2 分钟跑完。
基座权重加载后常驻显存，跑完记得关进程。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
      sys.path.insert(0, str(REPO_ROOT))

JSON_BLOCK = re.compile(r"\{.*\}", re.S)
ATTR_KEYS = ["商品大类", "细分类", "颜色", "材质"]


def parse_json_lenient(text: str) -> dict | None:
    """从模型输出里掏出第一个 JSON 对象；掏不出来返回 None。

    现实情况：模型经常在 JSON 前后加「好的，我来帮您…」这类话。
    这里模拟 5.3 _parse_intent 的容错策略（后续 5.3 会复用同一套逻辑）。
    """
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


def parse_attr_text(text: str) -> dict:
    """从「商品大类：X；细分类：Y；颜色：Z；材质：W」这种模板串抽字段。"""
    out = {}
    for key in ATTR_KEYS:
        m = re.search(rf"{key}[：:]\s*([^；;\n]+)", text or "")
        if m:
            out[key] = m.group(1).strip()
    return out


def score_attribute(pred: str, gold: str) -> tuple[float, dict]:
    p, g = parse_attr_text(pred), parse_attr_text(gold)
    if not g:
        return 0.0, {"fields": 0}
    hits = sum(1 for k in g if p.get(k) == g[k])
    return hits / len(g), {"fields": len(g), "hits": hits}


def score_intent(pred: str, gold: str) -> tuple[float, dict]:
    p = parse_json_lenient(pred)
    g = json.loads(gold)
    if p is None:
        return 0.0, {"json_ok": False}
    keys = ["intent", "category", "top_k"]
    hits = sum(1 for k in keys if str(p.get(k)) == str(g.get(k)))
    return hits / len(keys), {"json_ok": True, "hits": hits, "keys": len(keys)}


def score_tool_call(pred: str, gold: str) -> tuple[float, dict]:
    p = parse_json_lenient(pred)
    g = json.loads(gold)
    if p is None:
        return 0.0, {"json_ok": False}
    tool_ok = p.get("tool") == g.get("tool")
    ga, pa = g.get("arguments", {}), p.get("arguments") or {}
    arg_keys = ["query", "category", "top_k"]
    arg_hits = sum(1 for k in arg_keys if str(pa.get(k)) == str(ga.get(k)))
    # 工具名错则整条判错（工具名是白名单硬约束）
    total = (1 + arg_hits) / (1 + len(arg_keys)) if tool_ok else 0.0
    return total, {"json_ok": True, "tool_ok": tool_ok, "arg_hits": arg_hits}


SCORERS = {
    "attribute": score_attribute,
    "intent": score_intent,
    "tool_call": score_tool_call,
}


def load_model(model_id: str, adapter: str | None, no_4bit: bool):
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
            print("[warn] 无 bitsandbytes，用 bf16 全精度加载（显存需求翻倍）")

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=quant_config,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    if adapter:
        from peft import PeftModel

        print(f"[info] 挂载 LoRA 适配器：{adapter}")
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    return model, tokenizer


def generate(model, tokenizer, messages: list[dict], max_new_tokens: int = 256) -> str:
    import torch

    try:
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
    except TypeError:
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,          # 评测用贪心，保证可复现
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    gen = out[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(gen, skip_special_tokens=True).strip()


def run_eval(args) -> None:
    rows = [
        json.loads(line)
        for line in args.valid_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise SystemExit(f"{args.valid_file} 是空的")

    model, tokenizer = load_model(args.model, args.adapter, args.no_4bit)

    per_task: dict[str, list[float]] = defaultdict(list)
    json_ok: Counter = Counter()
    details = []

    for i, row in enumerate(rows, 1):
        msgs = row["messages"]
        task = row["meta"]["task"]
        gold = msgs[-1]["content"]
        pred = generate(model, tokenizer, msgs[:-1], args.max_new_tokens)

        scorer = SCORERS.get(task)
        if scorer is None:
            print(f"[warn] 未知任务类型 {task}，跳过")
            continue
        score, info = scorer(pred, gold)
        per_task[task].append(score)
        if task == "attribute" or info.get("json_ok"):
            json_ok[task] += 1

        details.append({
            "id": row["meta"]["id"],
            "task": task,
            "score": round(score, 4),
            "pred": pred,
            "gold": gold,
            **info,
        })
        print(f"[{i}/{len(rows)}] {task:10s} score={score:.3f}  id={row['meta']['id']}")

    total_scores = [s for v in per_task.values() for s in v]
    overall = sum(total_scores) / max(len(total_scores), 1)

    per_task_summary = {}
    for t, v in per_task.items():
        acc = sum(v) / len(v)
        valid = "n/a" if t == "attribute" else f"{json_ok[t]}/{len(v)}"
        per_task_summary[t] = {
            "count": len(v),
            "accuracy": round(acc, 4),
            "json_valid": valid,
        }

    summary = {
        "tag": args.tag,
        "model": args.model,
        "adapter": args.adapter,
        "valid_file": str(args.valid_file),
        "overall_accuracy": round(overall, 4),
        "per_task": per_task_summary,
        "details": details,
    }

    out = args.out or (REPO_ROOT / "data/agent/finetune" / f"eval_{args.tag}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n=== 汇总 ===")
    print(f"总体准确率 {summary['overall_accuracy']:.2%}")
    for t, s in summary["per_task"].items():
        print(f"  {t:10s} n={s['count']:2d}  acc={s['accuracy']:.2%}  json={s['json_valid']}")
    print(f"\n明细已写入：{out}")


def compare(paths: list[Path]) -> None:
    results = []
    for p in paths:
        if not p.exists():
            raise SystemExit(f"找不到结果文件：{p}")
        results.append(json.loads(p.read_text(encoding="utf-8")))

    tasks = sorted({t for r in results for t in r["per_task"]})
    width = 14
    header = f"{'task':12s}" + "".join(f"{r['tag']:>{width}s}" for r in results)
    print(header)
    print("-" * len(header))

    for t in tasks:
        line = f"{t:12s}"
        for r in results:
            s = r["per_task"].get(t)
            cell = f"{s['accuracy']:.2%}" if s else "-"
            line += f"{cell:>{width}s}"
        print(line)

    print("-" * len(header))
    line = f"{'overall':12s}"
    for r in results:
        line += f"{r['overall_accuracy']:>{width}.2%}"
    print(line)


def main() -> None:
    ap = argparse.ArgumentParser(description="5.2 基线 vs LoRA 评测")
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    ap.add_argument("--adapter", default=None, help="LoRA 权重目录；不填则测基座")
    ap.add_argument("--valid-file", type=Path, default=REPO_ROOT / "data/agent/sft/valid.jsonl")
    ap.add_argument("--tag", default="baseline")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--no-4bit", action="store_true")
    ap.add_argument("--compare", nargs="+", type=Path, default=None,
                    help="只做对比表：传入两个或多个 eval_*.json")
    args = ap.parse_args()

    if args.compare:
        compare(args.compare)
        return
    run_eval(args)


if __name__ == "__main__":
    main()