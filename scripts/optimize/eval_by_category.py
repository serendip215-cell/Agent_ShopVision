#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按类别拆分检索精度（实验三报告「误差分布热力图」的数据来源）。

在完整 934 条候选池上算全局 R@K，再按 product_type 分组统计各类别的 R@K 与相对基线的 ΔR@1。

用法（容器内）：
    python scripts/optimize/eval_by_category.py --quant fp32 --device cpu        # 基线
    python scripts/optimize/eval_by_category.py --quant int8-pc --device cpu     # 量化配置
    python scripts/optimize/eval_by_category.py --quant int8-visual --device cpu

产物：data/optimize/<RUN_ID>/accuracy/by_category_<quant>.json（并自动复制到 docs/optimize/runs/）
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Chinese-CLIP"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "retrieval"))

DEFAULT_CKPT = (
    "data/processed_data_retrieval/experiments/"
    "2026-10-18_bs32_lr1e-5/checkpoints/epoch3.pt"
)
DEFAULT_DATASET = "data/processed_data_retrieval/datasets/ShopVision"
DEFAULT_RUN_ID = "2026-10-23_exp3-quant"


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
            ids = item.get("image_ids") or []
            if ids:
                rows.append((item["text"], int(ids[0])))
    return rows


def load_categories(dataset: Path) -> dict[int, str]:
    mapping = {}
    with (dataset / "id_mapping.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            mapping[int(row["numeric_id"])] = row["product_type"]
    return mapping


def encode_texts(encoder, texts, batch_size: int):
    import numpy as np

    vectors = []
    total = (len(texts) + batch_size - 1) // batch_size
    with encoder.torch.no_grad():
        for idx, start in enumerate(range(0, len(texts), batch_size), start=1):
            batch = list(texts[start : start + batch_size])
            tokens = encoder.clip.tokenize(batch).to(encoder.device)
            feats = encoder.model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)
            vectors.append(feats.detach().cpu().numpy().astype("float32"))
            print(f"[text] {idx}/{total}", flush=True)
    return np.concatenate(vectors, axis=0)


def encode_images(encoder, dataset: Path, image_ids, batch_size: int):
    import lmdb
    import numpy as np
    from PIL import Image

    env = lmdb.open(str(dataset / "lmdb" / "test" / "imgs"), readonly=True, lock=False)
    vectors = []
    total = (len(image_ids) + batch_size - 1) // batch_size
    try:
        with env.begin(write=False) as txn, encoder.torch.no_grad():
            for idx, start in enumerate(range(0, len(image_ids), batch_size), start=1):
                batch_ids = image_ids[start : start + batch_size]
                tensors = []
                for image_id in batch_ids:
                    raw = txn.get(str(image_id).encode("utf-8"))
                    if raw is None:
                        raise KeyError(f"lmdb 里找不到图片：{image_id}")
                    image = Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
                    tensors.append(encoder.preprocess(image))
                inputs = encoder.torch.stack(tensors).to(encoder.device)
                feats = encoder.model.encode_image(inputs)
                feats = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)
                vectors.append(feats.detach().cpu().numpy().astype("float32"))
                print(f"[image] {idx}/{total}", flush=True)
    finally:
        env.close()
    return np.concatenate(vectors, axis=0)


def recall(sim_rows, k: int) -> float:
    """sim_rows: [(row_scores, correct_index), ...]"""
    import numpy as np

    if not sim_rows:
        return 0.0
    hits = 0
    for scores, target in sim_rows:
        topk = np.argpartition(-scores, min(k, len(scores) - 1))[:k]
        if target in topk:
            hits += 1
    return round(hits / len(sim_rows) * 100, 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quant", choices=["none", "fp32", "fp16", "int8", "int8-pc",
                                        "int8-text", "int8-visual"], default="fp32")
    ap.add_argument("--checkpoint", default=DEFAULT_CKPT)
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--run-id", default=DEFAULT_RUN_ID)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--device", choices=["auto", "cpu", "cuda"], default="cpu")
    args = ap.parse_args()

    import numpy as np
    from encoder import ChineseClipEncoder

    ckpt = resolve(args.checkpoint)
    dataset = resolve(args.dataset)
    if not ckpt.is_file():
        print(f"找不到权重：{ckpt}", file=sys.stderr)
        return 1

    rows = load_queries(dataset)
    cats = load_categories(dataset)
    texts = [r[0] for r in rows]
    image_ids = [r[1] for r in rows]
    labels = [cats.get(i, "未知") for i in image_ids]
    print(f"评测样本：{len(texts)} 条 | quant={args.quant} | device={args.device}", flush=True)

    t0 = time.time()
    encoder = ChineseClipEncoder("ViT-B-16", resolve("models/chinese_clip"), args.device,
                                 False, checkpoint=ckpt, quant=args.quant)
    print(f"编码模型：{encoder.model_tag}", flush=True)
    text_vecs = encode_texts(encoder, texts, args.batch_size)
    image_vecs = encode_images(encoder, dataset, image_ids, args.batch_size)
    sim = text_vecs @ image_vecs.T  # (934, 934)

    # 全局
    global_rows = [(sim[i], i) for i in range(len(rows))]
    global_scores = {f"r{k}": recall(global_rows, k) for k in (1, 5, 10)}
    global_scores["mean_recall"] = round(
        (global_scores["r1"] + global_scores["r5"] + global_scores["r10"]) / 3, 4
    )

    # 分类别
    buckets = defaultdict(list)
    for i, label in enumerate(labels):
        buckets[label].append((sim[i], i))
    by_cat = {}
    for label, items in sorted(buckets.items()):
        scores = {f"r{k}": recall(items, k) for k in (1, 5, 10)}
        scores["mean_recall"] = round(
            (scores["r1"] + scores["r5"] + scores["r10"]) / 3, 4
        )
        scores["n"] = len(items)
        by_cat[label] = scores

    elapsed = round(time.time() - t0, 1)

    print("\n全局：")
    for key in ("r1", "r5", "r10", "mean_recall"):
        print(f"  {key:<12s} {global_scores[key]:>8.2f}")
    print("\n分类别 R@1：")
    print(f"  {'类别':<10s} {'n':>5s} {'R@1':>8s} {'R@5':>8s} {'R@10':>8s}")
    for label, s in by_cat.items():
        print(f"  {label:<10s} {s['n']:>5d} {s['r1']:>8.2f} {s['r5']:>8.2f} {s['r10']:>8.2f}")

    payload = {
        "run_id": args.run_id,
        "backend": "pytorch",
        "quant": args.quant,
        "model_tag": encoder.model_tag,
        "device": str(encoder.device),
        "checkpoint": str(ckpt.relative_to(REPO_ROOT)),
        "dataset": str(dataset.relative_to(REPO_ROOT)),
        "n_texts": len(texts),
        "candidate_pool": len(image_ids),
        "elapsed_s": elapsed,
        "note": "候选池为完整 934 条；分类别指标在完整候选池上计算后再按类别分组汇总。",
        "global": global_scores,
        "by_category": by_cat,
    }
    out_dir = REPO_ROOT / "data" / "optimize" / args.run_id / "accuracy"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"by_category_{args.quant}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果：{out_path}")

    docs_dir = REPO_ROOT / "docs" / "optimize" / "runs" / args.run_id / "accuracy"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / out_path.name).write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"凭证（入 git）：{docs_dir / out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
