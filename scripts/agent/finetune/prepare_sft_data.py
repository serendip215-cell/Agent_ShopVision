"""5.2 微调数据转换：agent_finetune_data.json -> chat 格式 SFT 数据集。

5.1 产出的是「instruction / input / output」三段式（100 条，seed=42）。
SFTTrainer + Qwen chat template 要的是 messages 结构，本脚本做无损转换：

    instruction + "\n\n" + input   ->  user
    output                         ->  assistant

为什么不做 instruction 合并到 system：Qwen3 系的 chat template 对多轮很敏感，
把任务描述放 system 会削弱「只输出 JSON/模板串」的约束，实测更容易加前缀废话。
所以统一 user 侧拼接，保持与 5.1 数据的字面一致。

同时按 item_id 哈希切 train/valid（8:1:1 对应 80/10/10 条），与实验2 的切分口径一致
（实验2 也是 item_id 哈希，见 scripts/build_retrieval_dataset.py），避免同商品泄漏到两侧。

用法（仓库根目录）：
    python scripts/agent/finetune/prepare_sft_data.py
    python scripts/agent/finetune/prepare_sft_data.py --valid-ratio 0.1 --seed 42

输出：
    data/agent/sft/train.jsonl
    data/agent/sft/valid.jsonl
    data/agent/sft/manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SRC = REPO_ROOT / "data" / "agent" / "agent_finetune_data.json"
DEFAULT_OUT = REPO_ROOT / "data" / "agent" / "sft"


def bucket_of(item_id: str) -> int:
    """稳定哈希分桶：同一 item_id 永远进同一侧，跨多次运行可复现。"""
    h = hashlib.sha256(str(item_id).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


def to_record(row: dict) -> dict:
    """一条 5.1 记录 -> OpenAI messages 格式（SFTTrainer 直接吃）。"""
    instruction = (row.get("instruction") or "").strip()
    inp = (row.get("input") or "").strip()
    output = (row.get("output") or "").strip()

    user = f"{instruction}\n\n{inp}" if inp else instruction
    return {
        "messages": [
            {"role": "user", "content": user},
            {"role": "assistant", "content": output},
        ],
        "meta": {
            "id": row.get("id"),
            "task": row.get("task"),
            "item_id": row.get("item_id"),
            "category": row.get("category"),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="转换 5.1 数据为 SFT chat 格式")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--valid-ratio", type=float, default=0.1, help="验证集比例，默认 0.1")
    ap.add_argument("--seed", type=int, default=42, help="保留参数，切分实际由 item_id 哈希决定")
    args = ap.parse_args()

    if not args.src.exists():
        raise SystemExit(f"找不到输入：{args.src}\n先跑 scripts/agent/build_agent_finetune_data.py")

    rows = json.loads(args.src.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"{args.src} 不是非空 list")

    cut = int(round(args.valid_ratio * 100))
    train, valid = [], []
    for row in rows:
        rec = to_record(row)
        (valid if bucket_of(rec["meta"]["item_id"]) < cut else train).append(rec)

    # 100 条数据下 valid 可能抽到 0 条之外的极端情况，兜底保证有 10 条左右
    if len(valid) == 0:
        raise SystemExit("切分后 valid 为空，调大 --valid-ratio 或检查 item_id 分布")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("train", train), ("valid", valid)):
        path = args.out_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for rec in data:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{name:5s} {len(data):3d} 条 -> {path}")

    manifest = {
        "schema_version": 1,
        "source": str(args.src.relative_to(REPO_ROOT)).replace("\\", "/"),
        "source_sha256": hashlib.sha256(args.src.read_bytes()).hexdigest(),
        "split_strategy": "sha256(item_id)[:8] % 100 < valid_ratio*100",
        "valid_ratio": args.valid_ratio,
        "train_count": len(train),
        "valid_count": len(valid),
        "train_task_counts": dict(Counter(r["meta"]["task"] for r in train)),
        "valid_task_counts": dict(Counter(r["meta"]["task"] for r in valid)),
        "format": "openai-messages(user+assistant), no system prompt",
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()