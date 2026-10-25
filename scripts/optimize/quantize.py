#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把实验二的微调权重转成不同精度，并报告参数量与文件体积（实验三 P2）。

和 `scripts/retrieval/encoder.py --quant` 的分工：
  本脚本   —— 落盘成文件，用来量「模型大小」（任务书表 1 要这个数字）
  encoder  —— 加载时量化，用来「跑」量化的模型（建索引、查询、评测）

三种产物：
  fp32w  —— 只保留 state_dict 的 FP32 权重（体积基准锚点，去掉优化器动量）
  fp16   —— 权重转成半精度
  int8   —— 动态量化（只量化 nn.Linear，PyTorch 内置，CPU 路径）

用法：
    python scripts/optimize/quantize.py --all
    python scripts/optimize/quantize.py --mode int8 --run-id 2026-10-23_exp3-quant

产物：data/optimize/<RUN_ID>/quantized/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Chinese-CLIP"))

DEFAULT_CKPT = (
    "data/processed_data_retrieval/experiments/"
    "2026-10-18_bs32_lr1e-5/checkpoints/epoch3.pt"
)
DEFAULT_RUN_ID = "2026-10-23_exp3-quant"
VISION, TEXT = "ViT-B-16", "RoBERTa-wwm-ext-base-chinese"


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def build_and_load(ckpt_path: Path):
    """构建官方模型结构并载入微调权重（自动剥 module. 前缀）。"""
    import torch
    from cn_clip.clip.utils import create_model

    model = create_model(f"{VISION}@{TEXT}")
    ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    sd = ck["state_dict"] if isinstance(ck, dict) and "state_dict" in ck else ck
    if next(iter(sd.keys())).startswith("module."):
        sd = {k[len("module."):]: v for k, v in sd.items() if "bert.pooler" not in k}
    model.load_state_dict(sd)
    model.eval()
    return model


def count_params(model) -> int:
    return sum(p.numel() for p in model.parameters())


def save_fp32w(model, out: Path) -> None:
    """纯 FP32 权重（体积基准）。

    注意：官方 create_model() 内部会调 convert_weights() 把 Conv/Linear 权重转成 FP16，
    所以这里必须显式 float() 转回来，否则存出来的是 FP16（体积会只有一半）。
    """
    import torch
    model.float()
    torch.save({"quant": "fp32", "state_dict": model.state_dict()}, out)


def save_fp16(model, out: Path) -> None:
    import torch
    model.float().half()
    torch.save({"quant": "fp16", "state_dict": model.state_dict()}, out)


def save_int8(model, out: Path) -> None:
    """动态量化：只把 nn.Linear 换成 int8 版本，其余层保持 FP32。

    注意这是 CPU 路径的量化（PyTorch 的 quantize_dynamic 只支持 CPU 推理）。
    Embedding / LayerNorm / patch-embed 卷积不在量化范围内，会保持原精度——
    这也是 int8 体积降不到 188MB 的原因（报告里要说明）。
    """
    import torch
    from torch.ao.quantization import quantize_dynamic
    from torch.ao.nn.quantized.dynamic import Linear as DynLinear

    model.float()
    total_params = sum(p.numel() for p in model.parameters())
    before = sum(p.numel() * p.element_size() for p in model.parameters()) / 1024 / 1024
    n_lin = sum(1 for m in model.modules() if isinstance(m, torch.nn.Linear))
    quantized = quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8, inplace=False)

    n_dyn = sum(1 for m in quantized.modules() if isinstance(m, DynLinear))
    n_left = sum(1 for m in quantized.modules() if isinstance(m, torch.nn.Linear))
    left_params = sum(p.numel() for p in quantized.parameters())
    left_bytes = sum(p.numel() * p.element_size() for p in quantized.parameters()) / 1024 / 1024
    quant_params = total_params - left_params
    print(f"量化前参数占用：{before:.1f} MB（{total_params:,} 参数）")
    print(f"Linear 层：{n_lin} 个 → 动态量化 {n_dyn} 个，残留 float Linear {n_left} 个")
    print(f"未量化参数：{left_params:,} 个，占 {left_bytes:.1f} MB")
    print(f"估算：int8 权重 ≈ {quant_params / 1024 / 1024:.1f} MB"
          f" + 未量化 {left_bytes:.1f} MB = {quant_params / 1024 / 1024 + left_bytes:.1f} MB")

    # 保存整个量化模块：加载时需要 cn_clip 与 torch.ao 可用（本仓库内没问题）。
    torch.save({"quant": "int8_dynamic", "model": quantized}, out)


def mb(n: int) -> float:
    return round(n / 1024 / 1024, 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=DEFAULT_CKPT)
    ap.add_argument("--run-id", default=DEFAULT_RUN_ID, help="实验三的 RUN_ID，决定输出目录")
    ap.add_argument("--mode", choices=["fp32w", "fp16", "int8"])
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if not args.all and not args.mode:
        ap.error("需要 --mode 或 --all")

    ckpt = resolve(args.checkpoint)
    out_dir = REPO_ROOT / "data" / "optimize" / args.run_id / "quantized"
    if not ckpt.is_file():
        print(f"找不到权重：{ckpt}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    modes = ["fp32w", "fp16", "int8"] if args.all else [args.mode]
    ckpt_mb = mb(ckpt.stat().st_size)

    rows = []
    for mode in modes:
        model = build_and_load(ckpt)
        params = count_params(model)
        out = out_dir / f"epoch3_{mode}.pt"
        print(f"\n=== {mode} ===")
        print(f"参数量：{params:,}")
        if mode == "fp32w":
            save_fp32w(model, out)
        elif mode == "fp16":
            save_fp16(model, out)
        else:
            save_int8(model, out)
        size = out.stat().st_size
        rows.append({"mode": mode, "params": params, "bytes": size, "mb": mb(size),
                     "file": str(out.relative_to(REPO_ROOT))})
        print(f"已保存：{out}  ({mb(size)} MB)")
        del model

    fp32_mb = next((r["mb"] for r in rows if r["mode"] == "fp32w"), None)
    fp16_mb = next((r["mb"] for r in rows if r["mode"] == "fp16"), None)
    print("\n精度        参数量         体积(MB)   相对FP32   相对FP16")
    print("-" * 62)
    for r in rows:
        rel32 = f"{r['mb'] / fp32_mb * 100:6.1f}%" if fp32_mb else "     —"
        rel16 = f"{r['mb'] / fp16_mb * 100:6.1f}%" if fp16_mb and r["mode"] != "fp16" else "     —"
        print(f"{r['mode']:10s} {r['params']:>12,} {r['mb']:>11.2f}   {rel32}    {rel16}")
    print("-" * 62)
    print(f"原始 ckpt（含优化器动量）：{ckpt_mb} MB ← 不是纯权重，不可直接当体积基准")

    report_path = out_dir / "quantize_report.json"
    # 与已有报告合并：只跑单组（--mode int8）时不能把之前 fp32w/fp16 的记录冲掉。
    merged: dict[str, dict] = {}
    if report_path.is_file():
        try:
            old = json.loads(report_path.read_text(encoding="utf-8"))
            for item in old.get("results", []):
                merged[item["mode"]] = item
        except (json.JSONDecodeError, KeyError):
            merged = {}
    for item in rows:
        merged[item["mode"]] = item
    order = ["fp32w", "fp16", "int8", "nf4"]
    results = [merged[m] for m in order if m in merged]

    report = {
        "run_id": args.run_id,
        "source_checkpoint": str(ckpt.relative_to(REPO_ROOT)),
        "source_ckpt_mb": ckpt_mb,
        "note": (
            "fp32w 为纯权重基准（100%）；原始 ckpt 含优化器动量不可用。"
            "官方 create_model() 默认把权重转成 FP16，故 fp32w/int8 均先 float() 转回 FP32。"
            "int8 为动态量化，只覆盖 nn.Linear；Embedding/LayerNorm/patch-embed 不量化，故降幅小于理论 75%。"
        ),
        "results": results,
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告：{report_path}")

    # 凭证同步到入库目录（KB 级）：docs/optimize/runs/<RUN_ID>/
    docs_dir = REPO_ROOT / "docs" / "optimize" / "runs" / args.run_id
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_report = docs_dir / "quantize_report.json"
    docs_report.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"凭证（入 git）：{docs_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
