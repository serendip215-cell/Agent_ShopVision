#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推理延迟/吞吐基准：PyTorch vs ONNXRuntime（实验三 3.1.4 V2）。

口径（写进报告时必须一致）：
  - 只计模型 forward，不含预处理/后处理；
  - 先 warmup（默认 10 次）再计时（默认 50 次），取**中位数**；
  - 同一硬件对比：PyTorch-CPU vs ORT-CPU（GPU 口径另跑，不混比）；
  - 批大小 1 与 32 各测一遍；
  - 吞吐 = 批大小 / 单次耗时。

用法（容器内）：
    python scripts/optimize/bench_runtime.py                      # 图像塔，CPU，batch 1 与 32
    python scripts/optimize/bench_runtime.py --batch 1 --iters 100
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Chinese-CLIP"))

DEFAULT_CKPT = (
    "data/processed_data_retrieval/experiments/"
    "2026-10-18_bs32_lr1e-5/checkpoints/epoch3.pt"
)
DEFAULT_RUN_ID = "2026-10-24_exp3-speed"
RUN_ID_FOR_CACHE = DEFAULT_RUN_ID
VISION, TEXT = "ViT-B-16", "RoBERTa-wwm-ext-base-chinese"
IMAGE_SIZE = 224


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def build_visual(ckpt: Path, device: str = "cpu", precision: str = "fp32"):
    import torch
    from cn_clip.clip.utils import create_model

    model = create_model(f"{VISION}@{TEXT}")
    ck = torch.load(ckpt, map_location="cpu", weights_only=False)
    sd = ck["state_dict"] if isinstance(ck, dict) and "state_dict" in ck else ck
    if next(iter(sd.keys())).startswith("module."):
        sd = {k[len("module."):]: v for k, v in sd.items() if "bert.pooler" not in k}
    model.load_state_dict(sd)
    model.eval()
    model.float()

    if precision == "fp16":
        # 不能直接 model.half()：cn_clip 的 LayerNorm 内部强制 fp32（model.py:176），
        # 权重变 fp16 会触发 mixed dtype。官方用 convert_weights() 只转
        # Linear / Conv / MultiheadAttention / proj，LayerNorm 保持 fp32。
        from cn_clip.clip.model import convert_weights

        convert_weights(model)

    visual = model.visual
    if device == "cuda":
        visual = visual.to("cuda")
    return visual


def summarise(times: list[float], batch: int) -> dict:
    median = statistics.median(times)
    return {
        "batch": batch,
        "iters": len(times),
        "median_ms": round(median * 1000, 2),
        "mean_ms": round(statistics.fmean(times) * 1000, 2),
        "p90_ms": round(sorted(times)[int(len(times) * 0.9) - 1] * 1000, 2),
        "throughput_per_s": round(batch / median, 1),
    }


def bench_torch(visual, batch: int, iters: int, warmup: int,
                device: str = "cpu", precision: str = "fp32") -> dict:
    import torch

    dtype = torch.float16 if precision == "fp16" else torch.float32
    # 输入也要 fp16：cn_clip 的 encode_image 内部就是 x.type(self.dtype)
    x = torch.randn(batch, 3, IMAGE_SIZE, IMAGE_SIZE, dtype=dtype, device=device)
    with torch.no_grad():
        for _ in range(warmup):
            visual(x)
        if device == "cuda":
            torch.cuda.synchronize()
        times = []
        for _ in range(iters):
            if device == "cuda":
                torch.cuda.synchronize()
            t0 = time.perf_counter()
            visual(x)
            if device == "cuda":
                torch.cuda.synchronize()
            times.append(time.perf_counter() - t0)
    result = summarise(times, batch)
    result["device"] = device
    result["precision"] = precision
    return result


def bench_ort(onnx_path: Path, batch: int, iters: int, warmup: int, provider: str,
              threads: int = 0, graph_opt: str = "all", precision: str = "fp32") -> dict:
    import numpy as np
    import onnxruntime as ort

    level = {
        "all": ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
        "extended": ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED,
        "basic": ort.GraphOptimizationLevel.ORT_ENABLE_BASIC,
    }[graph_opt]
    opts = ort.SessionOptions()
    opts.graph_optimization_level = level
    if threads > 0:
        opts.intra_op_num_threads = threads
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    # TensorRT 需要显式给 provider_options：开 fp16、开引擎缓存（首次构建很慢）
    providers: list = [provider]
    if provider == "TensorrtExecutionProvider":
        cache_dir = REPO_ROOT / "data" / "optimize" / RUN_ID_FOR_CACHE / "trt_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        providers = [(provider, {
            "trt_fp16_enable": "True" if precision == "fp16" else "False",
            "trt_engine_cache_enable": "True",
            "trt_engine_cache_path": str(cache_dir),
            "trt_timing_cache_enable": "True",
            "trt_max_workspace_size": str(4 * 1024 ** 3),
        })]

    sess = ort.InferenceSession(str(onnx_path), sess_options=opts, providers=providers)
    actual = sess.get_providers()
    if provider not in actual:
        print(f"  ⚠️ 请求的 {provider} 不可用，实际回退到 {actual[0]}，本次结果无效！", flush=True)
    np_dtype = np.float16 if precision == "fp16" else np.float32
    feed = {"image": np.random.randn(batch, 3, IMAGE_SIZE, IMAGE_SIZE).astype(np_dtype)}
    for _ in range(warmup):
        sess.run(None, feed)
    times = []
    for _ in range(iters):
        t0 = time.perf_counter()
        sess.run(None, feed)
        times.append(time.perf_counter() - t0)
    result = summarise(times, batch)
    result["provider"] = provider
    result["actual_providers"] = actual
    result["provider_ok"] = provider in actual
    result["graph_optimization_level"] = graph_opt
    result["intra_op_threads"] = threads if threads > 0 else "auto"
    result["precision"] = precision
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=DEFAULT_CKPT)
    ap.add_argument("--run-id", default=DEFAULT_RUN_ID)
    ap.add_argument("--onnx", default="", help="ONNX 路径；留空用 <RUN_ID>/onnx/visual_fp32.onnx")
    ap.add_argument("--batch", type=int, nargs="+", default=[1, 32])
    ap.add_argument("--iters", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--provider", default="CPUExecutionProvider")
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu", help="PyTorch 侧设备")
    ap.add_argument("--precision", choices=["fp32", "fp16"], default="fp32")
    ap.add_argument("--ort-threads", type=int, default=0, help="ORT intra_op 线程数；0 = 自动")
    ap.add_argument("--graph-opt", choices=["all", "extended", "basic"], default="all")
    ap.add_argument("--torch-threads", type=int, default=0, help="PyTorch 线程数；0 = 不改")
    args = ap.parse_args()

    ckpt = resolve(args.checkpoint)
    onnx_path = resolve(args.onnx) if args.onnx else (
        REPO_ROOT / "data" / "optimize" / args.run_id / "onnx" / f"visual_{args.precision}.onnx"
    )
    if not ckpt.is_file():
        print(f"找不到权重：{ckpt}", file=sys.stderr)
        return 1
    if not onnx_path.is_file():
        print(f"找不到 ONNX：{onnx_path}（先跑 export_onnx.py）", file=sys.stderr)
        return 1

    import torch

    if args.torch_threads > 0:
        torch.set_num_threads(args.torch_threads)
    print(f"torch 线程数={torch.get_num_threads()} | CPU 核数={os.cpu_count()} "
          f"| 设备={args.device} | 精度={args.precision} "
          f"| ORT 线程={args.ort_threads or 'auto'} | 图优化={args.graph_opt}", flush=True)
    visual = build_visual(ckpt, args.device, args.precision)
    print("PyTorch 模型已就绪", flush=True)

    rows = []
    for batch in args.batch:
        iters = args.iters if batch <= 32 else max(10, args.iters // 5)
        print(f"\n=== batch {batch}（warmup {args.warmup} / 计时 {iters}）===", flush=True)
        t_torch = bench_torch(visual, batch, iters, args.warmup, args.device, args.precision)
        print(f"  PyTorch  {t_torch['median_ms']:>9.2f} ms  {t_torch['throughput_per_s']:>8.1f} 样本/秒", flush=True)
        t_ort = bench_ort(onnx_path, batch, iters, args.warmup, args.provider,
                          args.ort_threads, args.graph_opt, args.precision)
        print(f"  ORT      {t_ort['median_ms']:>9.2f} ms  {t_ort['throughput_per_s']:>8.1f} 样本/秒", flush=True)

        speedup = t_torch["median_ms"] / t_ort["median_ms"]
        latency_cut = (1 - t_ort["median_ms"] / t_torch["median_ms"]) * 100
        tput_gain = (t_ort["throughput_per_s"] / t_torch["throughput_per_s"] - 1) * 100
        if not t_ort.get("provider_ok", True):
            verdict = "⚠️ 后端回退，结果无效"
        else:
            verdict = "✅ 达标" if latency_cut >= 40 else "❌ 未达标"
        print(
            f"  加速 {speedup:.2f}× | 延迟降低 {latency_cut:+.1f}% | 吞吐 {tput_gain:+.1f}%  {verdict}",
            flush=True,
        )
        rows.append({
            "batch": batch,
            "torch": t_torch,
            "ort": t_ort,
            "speedup": round(speedup, 3),
            "latency_change_pct": round(-latency_cut, 2),
            "throughput_change_pct": round(tput_gain, 2),
            "meets_40pct_latency_target": latency_cut >= 40,
            "meets_50pct_throughput_target": tput_gain >= 50,
        })

    report = {
        "run_id": args.run_id,
        "tower": "visual",
        "device": args.device,
        "precision": args.precision,
        "onnx": str(onnx_path.relative_to(REPO_ROOT)),
        "provider": args.provider,
        "graph_optimization_level": args.graph_opt,
        "ort_intra_op_threads": args.ort_threads if args.ort_threads > 0 else "auto",
        "torch_threads": torch.get_num_threads(),
        "cpu_count": os.cpu_count(),
        "method": {
            "warmup": args.warmup,
            "metric": "median",
            "scope": "仅模型 forward，不含预处理/后处理",
            "fairness": "同硬件对比：PyTorch-CPU vs ORT-CPU",
        },
        "results": rows,
    }
    out_dir = REPO_ROOT / "data" / "optimize" / args.run_id / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    # 文件名带设备/精度/后端/线程配置后缀，避免覆盖历史结果
    tag = f"t{args.ort_threads if args.ort_threads > 0 else 'auto'}_{args.graph_opt}"
    prov = args.provider.replace("ExecutionProvider", "").lower() or "cpu"
    report_path = out_dir / f"bench_visual_{args.device}_{args.precision}_{prov}_{tag}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告：{report_path}")

    docs_dir = REPO_ROOT / "docs" / "optimize" / "runs" / args.run_id
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / report_path.name).write_text(
        report_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print(f"凭证（入 git）：{docs_dir / report_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
