#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计两个塔的参数量与理论前向 FLOPs（实验三报告表 1 的「计算量」列）。

重要口径：**FLOPs 只由模型结构决定，与精度/后端无关**（FP32/FP16/INT8 完全相同）。
这正是报告里要写的那句"量化改位宽、不改 FLOPs 计数"。

统计范围：`FlopCounterMode` 只统计矩阵乘/卷积类算子，不含 LayerNorm、GELU、Softmax、
Embedding 查表——这是业界常用口径，报告里注明即可。

用法（容器内，CPU 即可）：
    python scripts/optimize/bench_flops.py

产物：data/optimize/<RUN_ID>/bench/flops.json（并自动复制到 docs/optimize/runs/）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Chinese-CLIP"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "optimize"))

DEFAULT_CKPT = (
    "data/processed_data_retrieval/experiments/"
    "2026-10-18_bs32_lr1e-5/checkpoints/epoch3.pt"
)
DEFAULT_RUN_ID = "2026-10-24_exp3-speed"
IMAGE_SIZE = 224
CONTEXT_LENGTH = 52


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def human(n: float) -> str:
    for unit in ("", "K", "M", "G", "T"):
        if abs(n) < 1000:
            return f"{n:.2f}{unit}"
        n /= 1000
    return f"{n:.2f}P"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=DEFAULT_CKPT)
    ap.add_argument("--run-id", default=DEFAULT_RUN_ID)
    ap.add_argument("--skip-save", action="store_true", help="只打印不写文件")
    args = ap.parse_args()

    import torch
    from torch.utils.flop_counter import FlopCounterMode
    from export_onnx import TextTower, build_model

    ckpt = resolve(args.checkpoint)
    if not ckpt.is_file():
        print(f"找不到权重：{ckpt}", file=sys.stderr)
        return 1

    t0 = time.time()
    model = build_model(ckpt)
    print("模型已加载（FP32）", flush=True)

    visual = model.visual
    text_tower = TextTower.build(model)

    n_visual = sum(p.numel() for p in visual.parameters())
    n_text = sum(p.numel() for p in text_tower.parameters())

    x = torch.randn(1, 3, IMAGE_SIZE, IMAGE_SIZE)
    with torch.no_grad():
        with FlopCounterMode(display=False) as fv:
            visual(x)
        flops_visual = fv.get_total_flops()

        ids = torch.randint(0, 1000, (1, CONTEXT_LENGTH), dtype=torch.long)
        mask = torch.ones((1, CONTEXT_LENGTH), dtype=torch.long)
        with FlopCounterMode(display=False) as ft:
            text_tower(ids, mask)
        flops_text = ft.get_total_flops()

    total_params = n_visual + n_text
    total_flops = flops_visual + flops_text
    elapsed = round(time.time() - t0, 1)

    print("\n塔        参数量            FLOPs（batch=1）")
    print("-" * 52)
    print(f"图像塔   {human(n_visual):>12s}   {human(flops_visual):>16s}")
    print(f"文本塔   {human(n_text):>12s}   {human(flops_text):>16s}")
    print("-" * 52)
    print(f"合计     {human(total_params):>12s}   {human(total_flops):>16s}")
    print("-" * 52)
    print(f"原始计数：params={total_params:,}  flops={total_flops:,}")
    print(f"文本塔序列长度：{CONTEXT_LENGTH}（与训练/推理一致）")
    print("口径：只统计 MatMul/Conv，不含 LayerNorm/GELU/Softmax/Embedding 查表；"
          "FLOPs 与精度/后端无关")

    payload = {
        "run_id": args.run_id,
        "checkpoint": str(ckpt.relative_to(REPO_ROOT)),
        "params": {
            "visual": n_visual,
            "text": n_text,
            "total": total_params,
        },
        "flops_forward_batch1": {
            "visual": flops_visual,
            "text": flops_text,
            "total": total_flops,
        },
        "flops_forward_human": {
            "visual": human(flops_visual),
            "text": human(flops_text),
            "total": human(total_flops),
        },
        "input": {"image": [1, 3, IMAGE_SIZE, IMAGE_SIZE], "text_seq_len": CONTEXT_LENGTH},
        "scope": "MatMul/Conv only (no LayerNorm/GELU/Softmax/Embedding)",
        "note": "FLOPs 只由模型结构决定，与 FP32/FP16/INT8 无关——量化改位宽，不改 FLOPs 计数。",
        "elapsed_s": elapsed,
    }

    if args.skip_save:
        print("\n（--skip-save，未写文件）")
        return 0

    out_dir = REPO_ROOT / "data" / "optimize" / args.run_id / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "flops.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果：{out_path}")

    docs_dir = REPO_ROOT / "docs" / "optimize" / "runs" / args.run_id
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "flops.json").write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"凭证（入 git）：{docs_dir / 'flops.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
