#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 ONNX（图像塔 + 文本塔）在 934 条 test 上算 R@K，与 PyTorch 结果比对（实验三 3.1.4 精度一致性）。

口径与实验二完全一致：文搜图 top-10、候选池 934、第 i 段文本的标准答案是第 i 张图。

用法（容器内）：
    python scripts/optimize/eval_onnx.py                       # FP32 ONNX，ORT-CPU
    python scripts/optimize/eval_onnx.py --precision fp16 --provider CUDAExecutionProvider
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Chinese-CLIP"))

DEFAULT_DATASET = "data/processed_data_retrieval/datasets/ShopVision"
DEFAULT_RUN_ID = "2026-10-24_exp3-speed"
CONTEXT_LENGTH = 52
IMAGE_SIZE = 224


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def load_queries(dataset: Path):
    rows = []
    with (dataset / "test_texts.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            image_ids = item.get("image_ids") or []
            if image_ids:
                rows.append((item["text"], image_ids[0]))
    return rows


def encode_texts(session, texts, batch_size: int):
    import numpy as np
    from cn_clip.clip import tokenize

    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        ids = tokenize(batch, context_length=CONTEXT_LENGTH)
        mask = ids.ne(0).long()
        out = session.run(None, {
            "input_ids": ids.numpy().astype("int64"),
            "attention_mask": mask.numpy().astype("int64"),
        })[0]
        vectors.append(out)
        print(f"[text] {start + len(batch)}/{len(texts)}", flush=True)
    feats = np.concatenate(vectors, axis=0)
    return feats / (np.linalg.norm(feats, axis=1, keepdims=True) + 1e-12)


def encode_images(session, dataset: Path, image_ids, batch_size: int, precision: str = "fp32"):
    import lmdb
    import numpy as np
    from PIL import Image
    from cn_clip.clip import image_transform

    preprocess = image_transform(IMAGE_SIZE)
    env = lmdb.open(str(dataset / "lmdb" / "test" / "imgs"), readonly=True, lock=False)
    vectors = []
    try:
        with env.begin(write=False) as txn:
            for start in range(0, len(image_ids), batch_size):
                batch_ids = image_ids[start : start + batch_size]
                tensors = []
                for image_id in batch_ids:
                    raw = txn.get(str(image_id).encode("utf-8"))
                    if raw is None:
                        raise KeyError(f"lmdb 里找不到图片：{image_id}")
                    image = Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
                    tensors.append(preprocess(image).numpy())
                # fp16 模型要求 float16 输入，否则报 Unexpected input data type
                np_dtype = np.float16 if precision == "fp16" else np.float32
                arr = np.stack(tensors).astype(np_dtype)
                out = session.run(None, {"image": arr})[0]
                vectors.append(out)
                print(f"[image] {start + len(batch_ids)}/{len(image_ids)}", flush=True)
    finally:
        env.close()
    feats = np.concatenate(vectors, axis=0)
    return feats / (np.linalg.norm(feats, axis=1, keepdims=True) + 1e-12)


def recall_at_k(sim) -> dict:
    import numpy as np

    order = np.argsort(-sim, axis=1)
    diag = np.arange(sim.shape[0])
    result = {}
    for k in (1, 5, 10):
        hit = (order[:, :k] == diag[:, None]).any(axis=1)
        result[f"r{k}"] = round(float(hit.mean()) * 100, 4)
    result["mean_recall"] = round((result["r1"] + result["r5"] + result["r10"]) / 3, 4)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=DEFAULT_RUN_ID)
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--precision", choices=["fp32", "fp16"], default="fp32")
    ap.add_argument("--provider", default="CPUExecutionProvider")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--baseline", default="", help="PyTorch 基线 JSON；留空自动找 test_fp32/test_none")
    args = ap.parse_args()

    import numpy as np
    import onnxruntime as ort

    dataset = resolve(args.dataset)
    onnx_dir = REPO_ROOT / "data" / "optimize" / args.run_id / "onnx"
    visual_onnx = onnx_dir / f"visual_{args.precision}.onnx"
    text_onnx = onnx_dir / f"text_{args.precision}.onnx"
    for path in (visual_onnx, text_onnx):
        if not path.is_file():
            print(f"找不到 {path}（先跑 export_onnx.py --tower ...）", file=sys.stderr)
            return 1

    rows = load_queries(dataset)
    texts = [r[0] for r in rows]
    image_ids = [r[1] for r in rows]
    print(f"评测样本：{len(texts)} 条 | ONNX {args.precision} | provider={args.provider}", flush=True)

    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers: list = [args.provider]
    if args.provider == "TensorrtExecutionProvider":
        cache_dir = REPO_ROOT / "data" / "optimize" / args.run_id / "trt_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        providers = [(args.provider, {
            "trt_fp16_enable": "True" if args.precision == "fp16" else "False",
            "trt_engine_cache_enable": "True",
            "trt_engine_cache_path": str(cache_dir),
            "trt_timing_cache_enable": "True",
            "trt_max_workspace_size": str(4 * 1024 ** 3),
        })]
    t0 = time.time()
    vis_sess = ort.InferenceSession(str(visual_onnx), sess_options=opts, providers=providers)
    txt_sess = ort.InferenceSession(str(text_onnx), sess_options=opts, providers=providers)
    for name, sess in (("visual", vis_sess), ("text", txt_sess)):
        actual = sess.get_providers()
        flag = "" if args.provider in actual else "  ⚠️ 已回退！"
        print(f"  {name} 实际后端：{actual}{flag}", flush=True)

    text_vecs = encode_texts(txt_sess, texts, args.batch_size)
    image_vecs = encode_images(vis_sess, dataset, image_ids, args.batch_size, args.precision)
    scores = recall_at_k(text_vecs @ image_vecs.T)
    elapsed = round(time.time() - t0, 1)

    # 读 PyTorch 基线（同一 934 条 test，FP32 口径）
    baseline = None
    baseline_dir = REPO_ROOT / "data" / "optimize" / "2026-10-23_exp3-quant" / "accuracy"
    base_path = resolve(args.baseline) if args.baseline else baseline_dir / "test_fp32.json"
    if base_path.is_file():
        baseline = json.loads(base_path.read_text(encoding="utf-8"))["scores"]

    print("\n指标        ONNX(%)     PyTorch基线(%)   差值(pp)")
    print("-" * 52)
    for key in ("r1", "r5", "r10", "mean_recall"):
        base = baseline[key] if baseline else float("nan")
        delta = scores[key] - base if baseline else float("nan")
        print(f"{key:<11s} {scores[key]:>8.2f} {base:>14.2f} {delta:>12.2f}")
    print("-" * 52)
    print(f"耗时 {elapsed}s")

    payload = {
        "run_id": args.run_id,
        "backend": "onnxruntime",
        "provider": args.provider,
        "precision": args.precision,
        "onnx": {
            "visual": str(visual_onnx.relative_to(REPO_ROOT)),
            "text": str(text_onnx.relative_to(REPO_ROOT)),
        },
        "dataset": str(dataset.relative_to(REPO_ROOT)),
        "n_texts": len(texts),
        "candidate_pool": len(image_ids),
        "elapsed_s": elapsed,
        "scores": scores,
        "pytorch_baseline": baseline,
        "delta_r1_pp": round(scores["r1"] - baseline["r1"], 4) if baseline else None,
        "consistency_within_1pp": (
            abs(scores["r1"] - baseline["r1"]) <= 1.0 if baseline else None
        ),
    }
    out_dir = REPO_ROOT / "data" / "optimize" / args.run_id / "accuracy"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"onnx_{args.precision}_{args.provider}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果：{out_path}")

    docs_dir = REPO_ROOT / "docs" / "optimize" / "runs" / args.run_id
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / out_path.name).write_text(
        out_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print(f"凭证（入 git）：{docs_dir / out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
