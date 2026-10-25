#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单精度精度评测（实验三 P3）：在固定 test 934 条上算 R@1 / R@5 / R@10。

和 `scripts/finetune/run_test_eval.sh` 的区别：那个走官方 `cn_clip/eval/` 三件套、
只支持原精度；本脚本复用 `ChineseClipEncoder`，因此可以用 `--quant` 在各精度下评同一批题。

用法（容器内）：
    python scripts/optimize/eval_quant.py --quant none --device cuda    # 官方默认（实际 FP16）
    python scripts/optimize/eval_quant.py --quant fp32 --device cpu     # 真正的 FP32
    python scripts/optimize/eval_quant.py --quant int8 --device cpu     # 动态量化（只能 CPU）

评测口径与实验二一致：934 段文本 vs 934 张图，全量候选，文搜图 top-10。
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
    """返回 [(text, image_id), ...]，按 test_texts.jsonl 顺序。"""
    rows = []
    with (dataset / "test_texts.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            image_ids = item.get("image_ids") or []
            if not image_ids:
                continue
            rows.append((item["text"], image_ids[0]))
    return rows


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


def encode_images_from_lmdb(encoder, dataset: Path, image_ids, batch_size: int):
    """直接从 lmdb 的 base64 解码，避免往磁盘写临时图片。"""
    import lmdb
    import numpy as np
    from PIL import Image

    imgs_dir = dataset / "lmdb" / "test" / "imgs"
    vectors = []
    total = (len(image_ids) + batch_size - 1) // batch_size
    env = lmdb.open(str(imgs_dir), readonly=True, lock=False, readahead=False)
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


def recall_at_k(sim, top_k=(1, 5, 10)) -> dict:
    import numpy as np

    # sim: (n_texts, n_images)，第 i 段文本的标准答案是第 i 张图（顺序一一对应）
    order = np.argsort(-sim, axis=1)
    diag = np.arange(sim.shape[0])
    result = {}
    for k in top_k:
        hit = (order[:, :k] == diag[:, None]).any(axis=1)
        result[f"r{k}"] = round(float(hit.mean()) * 100, 4)
    result["mean_recall"] = round(
        float(np.mean([result[f"r{k}"] for k in top_k])), 4
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--quant",
        choices=["none", "fp32", "fp16", "int8", "int8-pc", "int8-text", "int8-visual"],
        default="none",
    )
    ap.add_argument("--checkpoint", default=DEFAULT_CKPT)
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--run-id", default=DEFAULT_RUN_ID)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    ap.add_argument("--out", default="", help="输出 JSON；留空写到 data/optimize/<RUN_ID>/accuracy/")
    args = ap.parse_args()

    from encoder import ChineseClipEncoder

    ckpt = resolve(args.checkpoint)
    dataset = resolve(args.dataset)
    if not ckpt.is_file():
        print(f"找不到权重：{ckpt}", file=sys.stderr)
        return 1
    if not (dataset / "test_texts.jsonl").is_file():
        print(f"找不到评测集：{dataset / 'test_texts.jsonl'}", file=sys.stderr)
        return 1

    rows = load_queries(dataset)
    texts = [r[0] for r in rows]
    image_ids = [r[1] for r in rows]
    print(f"评测样本：{len(texts)} 条 | quant={args.quant} | device={args.device}", flush=True)

    started = time.time()
    encoder = ChineseClipEncoder(
        "ViT-B-16",
        resolve("models/chinese_clip"),
        args.device,
        False,
        checkpoint=ckpt,
        quant=args.quant,
    )
    print(f"编码模型：{encoder.model_tag}", flush=True)

    text_vectors = encode_texts(encoder, texts, args.batch_size)
    image_vectors = encode_images_from_lmdb(encoder, dataset, image_ids, args.batch_size)
    sim = text_vectors @ image_vectors.T
    scores = recall_at_k(sim)
    elapsed = round(time.time() - started, 1)

    print("\n指标        数值（%）")
    print("-" * 28)
    for key in ("r1", "r5", "r10", "mean_recall"):
        print(f"{key:<12s} {scores[key]:>8.2f}")
    print("-" * 28)
    print(f"耗时 {elapsed}s | 设备 {encoder.device} | 精度 {args.quant}")

    payload = {
        "run_id": args.run_id,
        "quant": args.quant,
        "model_tag": encoder.model_tag,
        "device": str(encoder.device),
        "checkpoint": str(ckpt.relative_to(REPO_ROOT)),
        "dataset": str(dataset.relative_to(REPO_ROOT)),
        "n_texts": len(texts),
        "n_images": len(image_ids),
        "batch_size": args.batch_size,
        "candidate_pool": len(image_ids),
        "elapsed_s": elapsed,
        "scores": scores,
        "notes": [
            "文搜图 top-10，候选池 = test 934 条，与实验二同一口径。",
            "quant=none 走官方默认加载（create_model 会把权重转 FP16），实际为 FP16。",
            "quant=int8 为 CPU 动态量化，只能与 CPU 口径的延迟对比。",
        ],
    }
    out = resolve(args.out) if args.out else (
        REPO_ROOT / "data" / "optimize" / args.run_id / "accuracy" / f"test_{args.quant}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果：{out}")

    # 凭证同步到入库目录（KB 级）：docs/optimize/runs/<RUN_ID>/accuracy/
    docs_dir = REPO_ROOT / "docs" / "optimize" / "runs" / args.run_id / "accuracy"
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_out = docs_dir / out.name
    docs_out.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"凭证（入 git）：{docs_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
