#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Chinese-CLIP 的单塔导出成 ONNX，并校验 PyTorch 与 ONNXRuntime 输出是否一致（实验三 3.1.4 V1）。

为什么先导单塔而不是整模型：双塔各自有独立的输入（图像张量 / token 张量），
分开导出才能分别做动态轴、分别接 TensorRT 或 ORT，也便于定位导出失败的位置。

用法（容器内）：
    python scripts/optimize/export_onnx.py                       # 图像塔，FP32
    python scripts/optimize/export_onnx.py --precision fp16      # 图像塔，FP16（ORT-CPU 无法校验）
    python scripts/optimize/export_onnx.py --skip-verify         # 只导出不校验

产物：data/optimize/<RUN_ID>/onnx/visual_<precision>.onnx + export_report.json
"""

from __future__ import annotations

import argparse
import json
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
VISION, TEXT = "ViT-B-16", "RoBERTa-wwm-ext-base-chinese"
IMAGE_SIZE = 224


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def build_model(ckpt: Path):
    """构建官方结构并载入微调权重，固定为 FP32。

    不能先把 PyTorch 模型转 half 再导出：cn_clip 的 LayerNorm 里写死了
    `x.type(torch.float32)`，半精度权重 + fp32 输入会在 CPU 上触发
    "mixed dtype" 错误。FP16 要在 ONNX 图层面做（见 convert_to_fp16）。
    """
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
    return model


def export_visual(model, out_path: Path) -> None:
    import torch

    visual = model.visual
    visual.eval()
    dummy = torch.randn(1, 3, IMAGE_SIZE, IMAGE_SIZE)

    torch.onnx.export(
        visual,
        (dummy,),
        str(out_path),
        input_names=["image"],
        output_names=["embedding"],
        dynamic_axes={"image": {0: "batch"}, "embedding": {0: "batch"}},
        opset_version=17,
        do_constant_folding=True,
    )


def convert_to_fp16(fp32_path: Path, fp16_path: Path) -> str:
    """在 ONNX 图层面把权重转成 FP16（不重新 trace 模型）。返回转换实现名。"""
    import onnx

    impl = ""
    try:
        from onnxruntime.transformers.float16 import convert_float_to_float16
        impl = "onnxruntime.transformers.float16"
    except ImportError:
        from onnxconverter_common.float16 import convert_float_to_float16
        impl = "onnxconverter_common"

    model = onnx.load(str(fp32_path))
    model_fp16 = convert_float_to_float16(model, keep_io_types=False)
    onnx.save(model_fp16, str(fp16_path))
    return impl


class TextTower:
    """文本塔的导出包装：只吃 input_ids 与 attention_mask，不依赖 tokenizer。

    对应 cn_clip 的 CLIP.encode_text：
        attn_mask = text.ne(pad).type(dtype)
        x = bert(text, attention_mask=attn_mask)[0][:, 0, :] @ text_projection
    """

    @staticmethod
    def build(clip_model):
        import torch

        class _Wrapper(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.bert = clip_model.bert
                self.text_projection = clip_model.text_projection

            def forward(self, input_ids, attention_mask):
                x = self.bert(input_ids, attention_mask=attention_mask)[0]
                return x[:, 0, :] @ self.text_projection

        wrapper = _Wrapper()
        wrapper.eval()
        return wrapper


def export_text(model, out_path: Path, seq_len: int = 16) -> None:
    import torch

    wrapper = TextTower.build(model)
    dummy_ids = torch.randint(0, 1000, (1, seq_len), dtype=torch.long)
    dummy_mask = torch.ones((1, seq_len), dtype=torch.long)

    torch.onnx.export(
        wrapper,
        (dummy_ids, dummy_mask),
        str(out_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["embedding"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "embedding": {0: "batch"},
        },
        opset_version=17,
        do_constant_folding=True,
    )


def verify_text(model, onnx_path: Path) -> dict:
    import numpy as np
    import onnxruntime as ort
    import torch

    torch.manual_seed(0)
    ids = torch.randint(0, 1000, (2, 16), dtype=torch.long)
    mask = torch.ones((2, 16), dtype=torch.long)
    with torch.no_grad():
        ref = TextTower.build(model)(ids, mask)
    ref = ref.float().detach().numpy()

    provider = "CPUExecutionProvider"
    sess = ort.InferenceSession(str(onnx_path), providers=[provider])
    got = sess.run(None, {"input_ids": ids.numpy(), "attention_mask": mask.numpy()})[0]

    a = ref.reshape(ref.shape[0], -1)
    b = got.reshape(got.shape[0], -1)
    cos = np.sum(a * b, axis=1) / (
        np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12
    )
    return {
        "provider": provider,
        "cosine_min": float(np.min(cos)),
        "max_abs_diff": float(np.max(np.abs(a - b))),
        "shape_ref": list(ref.shape),
        "shape_onnx": list(got.shape),
        "pass": bool(np.min(cos) >= 0.999),
    }


def verify(model, onnx_path: Path) -> dict:
    """用同一输入比对 PyTorch(FP32) 与 ORT 的输出。"""
    import numpy as np
    import onnxruntime as ort
    import torch

    # 固定输入，保证两边吃到完全一样的数据
    torch.manual_seed(0)
    x = torch.randn(2, 3, IMAGE_SIZE, IMAGE_SIZE)

    with torch.no_grad():
        ref = model.visual(x)
    ref = ref.float().detach().numpy()

    providers = ort.get_available_providers()
    provider = "CPUExecutionProvider" if "CPUExecutionProvider" in providers else providers[0]
    sess = ort.InferenceSession(str(onnx_path), providers=[provider])
    got = sess.run(None, {"image": x.numpy()})[0]

    a = ref.reshape(ref.shape[0], -1)
    b = got.reshape(got.shape[0], -1)
    cos = np.sum(a * b, axis=1) / (
        np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12
    )
    return {
        "provider": providers[0],
        "cosine_min": float(np.min(cos)),
        "max_abs_diff": float(np.max(np.abs(a - b))),
        "ref_norm_mean": float(np.mean(np.linalg.norm(a, axis=1))),
        "out_norm_mean": float(np.mean(np.linalg.norm(b, axis=1))),
        "shape_ref": list(ref.shape),
        "shape_onnx": list(got.shape),
        "pass": bool(np.min(cos) >= 0.999),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=DEFAULT_CKPT)
    ap.add_argument("--run-id", default=DEFAULT_RUN_ID)
    ap.add_argument("--tower", choices=["visual", "text"], default="visual", help="导出哪个塔")
    ap.add_argument("--precision", choices=["fp32", "fp16"], default="fp32")
    ap.add_argument("--skip-verify", action="store_true")
    args = ap.parse_args()

    ckpt = resolve(args.checkpoint)
    out_dir = REPO_ROOT / "data" / "optimize" / args.run_id / "onnx"
    if not ckpt.is_file():
        print(f"找不到权重：{ckpt}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    fp32_path = out_dir / f"{args.tower}_fp32.onnx"
    onnx_path = out_dir / f"{args.tower}_{args.precision}.onnx"

    t0 = time.time()
    model = build_model(ckpt)
    print("模型已加载（FP32）", flush=True)

    if fp32_path.is_file():
        print(f"复用已有 FP32 ONNX：{fp32_path}", flush=True)
    else:
        print(f"开始导出{'图像' if args.tower == 'visual' else '文本'}塔 ONNX（FP32）...", flush=True)
        if args.tower == "visual":
            export_visual(model, fp32_path)
        else:
            export_text(model, fp32_path)
        print(f"FP32 导出完成：{fp32_path}"
              f"（{fp32_path.stat().st_size / 1024 / 1024:.2f} MB）", flush=True)

    convert_impl = ""
    if args.precision == "fp16":
        print("在 ONNX 图层转换为 FP16 ...", flush=True)
        convert_impl = convert_to_fp16(fp32_path, onnx_path)
        print(f"FP16 转换完成：{onnx_path}"
              f"（{onnx_path.stat().st_size / 1024 / 1024:.2f} MB，实现 {convert_impl}）", flush=True)
    else:
        onnx_path = fp32_path

    export_s = round(time.time() - t0, 1)
    size_mb = round(onnx_path.stat().st_size / 1024 / 1024, 2)
    print(f"目标产物：{onnx_path}（{size_mb} MB，总耗时 {export_s}s）", flush=True)

    report = {
        "run_id": args.run_id,
        "tower": args.tower,
        "precision": args.precision,
        "checkpoint": str(ckpt.relative_to(REPO_ROOT)),
        "onnx_path": str(onnx_path.relative_to(REPO_ROOT)),
        "fp32_onnx_path": str(fp32_path.relative_to(REPO_ROOT)),
        "fp16_conversion_impl": convert_impl or None,
        "onnx_mb": size_mb,
        "export_seconds": export_s,
        "opset": 17,
        "input": (
            {"name": "image", "shape": ["batch", 3, IMAGE_SIZE, IMAGE_SIZE]}
            if args.tower == "visual"
            else {"names": ["input_ids", "attention_mask"], "shape": ["batch", "seq"]}
        ),
        "output": {"name": "embedding", "shape": ["batch", 512]},
    }

    if args.precision == "fp16":
        # ORT-CPU 对 fp16 支持很差（内部会转回 fp32），校验意义不大，留到 GPU 上做
        print("注意：FP16 模型的数值校验留给 GPU 后端（ORT-CPU 会内部转 fp32，无意义）", flush=True)
    elif args.skip_verify:
        print("已跳过校验（--skip-verify）", flush=True)
    else:
        print("校验 PyTorch vs ONNXRuntime ...", flush=True)
        checker = verify if args.tower == "visual" else verify_text
        try:
            result = checker(model, onnx_path)
        except Exception as exc:  # noqa: BLE001 - 校验失败要保留原始信息
            print(f"校验失败：{type(exc).__name__}: {exc}", file=sys.stderr)
            report["verify"] = {"error": f"{type(exc).__name__}: {exc}"}
            result = None
        if result is not None:
            report["verify"] = result
            print(
                f"  provider={result['provider']}  余弦最小={result['cosine_min']:.6f}  "
                f"最大绝对差={result['max_abs_diff']:.6f}",
                flush=True,
            )
            print(f"  形状 ref={result['shape_ref']} onnx={result['shape_onnx']}", flush=True)
            print("✅ 通过（cos ≥ 0.999）" if result["pass"] else "❌ 未通过（cos < 0.999）", flush=True)

    report_path = out_dir / f"export_report_{args.precision}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告：{report_path}")

    docs_dir = REPO_ROOT / "docs" / "optimize" / "runs" / args.run_id
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / report_path.name).write_text(
        report_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print(f"凭证（入 git）：{docs_dir / report_path.name}")
    return 0 if report.get("verify", {}).get("pass", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
