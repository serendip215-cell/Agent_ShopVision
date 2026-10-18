#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把审核后的商品数据转成 Chinese-CLIP 微调用的 tsv + jsonl 数据集。

输入:data/processed_data_cleaning/<类别>/products.csv(9 个类别)
输出:data/processed_data_retrieval/datasets/ShopVision/
    ├── train_imgs.tsv / train_texts.jsonl
    ├── valid_imgs.tsv / valid_texts.jsonl
    ├── test_imgs.tsv  / test_texts.jsonl
    └── id_mapping.csv

文本用 build_product_text() 生成,和检索索引的文本格式完全一致。
按 item_id 哈希取模做 8:1:1 切分,同一商品不会跨集合。

用法:
    python scripts/build_retrieval_dataset.py
    python scripts/build_retrieval_dataset.py --input-dir data/processed_data_cleaning \\
        --output-dir data/processed_data_retrieval/datasets/ShopVision \\
        --train-ratio 0.8 --valid-ratio 0.1
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "retrieval"))

from text_builder import build_product_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 Chinese-CLIP 微调数据集(tsv + jsonl)")
    parser.add_argument("--input-dir", default="data/processed_data_cleaning", help="审核数据根目录")
    parser.add_argument("--output-dir", default="data/processed_data_retrieval/datasets/ShopVision", help="输出目录")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="训练集比例,默认 0.8")
    parser.add_argument("--valid-ratio", type=float, default=0.1, help="验证集比例,默认 0.1")
    return parser.parse_args()


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def split_by_hash(item_id: str, train_ratio: float, valid_ratio: float) -> str:
    """按 item_id 的 MD5 哈希值切分,保证同一 item_id 永远落在同一划分。"""
    digest = hashlib.md5(item_id.encode("utf-8")).hexdigest()
    value = int(digest, 16) % 1000 / 1000.0  # 0.000 ~ 0.999
    if value < train_ratio:
        return "train"
    if value < train_ratio + valid_ratio:
        return "valid"
    return "test"


def image_to_base64(image_path: Path) -> str | None:
    """读图片文件转 base64;读不出来返回 None。"""
    try:
        with image_path.open("rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None


def discover_categories(input_dir: Path) -> list[str]:
    return sorted(
        child.name for child in input_dir.iterdir()
        if child.is_dir() and (child / "products.csv").exists()
    )


def main() -> int:
    args = parse_args()
    if args.train_ratio <= 0 or args.valid_ratio < 0 or args.train_ratio + args.valid_ratio >= 1:
        raise ValueError("比例不合法:train_ratio + valid_ratio 必须小于 1 且大于 0")

    input_dir = resolve_path(args.input_dir)
    output_dir = resolve_path(args.output_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在:{input_dir}")

    categories = discover_categories(input_dir)
    if not categories:
        raise RuntimeError(f"{input_dir} 下没有发现包含 products.csv 的类别目录")
    print(f"发现 {len(categories)} 个类别:{', '.join(categories)}")

    # 打开输出文件
    output_dir.mkdir(parents=True, exist_ok=True)
    splits = ["train", "valid", "test"]
    img_files = {s: (output_dir / f"{s}_imgs.tsv").open("w", encoding="utf-8") for s in splits}
    txt_files = {s: (output_dir / f"{s}_texts.jsonl").open("w", encoding="utf-8") for s in splits}

    id_mapping_rows: list[dict[str, str]] = []
    stats = {
        "total": 0,
        "skipped_no_image": 0,
        "skipped_image_error": 0,
        "skipped_empty_text": 0,
        "per_category": Counter(),
        "per_split": Counter(),
    }

    numeric_id = 1
    for category in categories:
        csv_path = input_dir / category / "products.csv"
        print(f"\n[{category}] 读取 {csv_path.relative_to(REPO_ROOT)}")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats["total"] += 1
                item_id = (row.get("item_id") or "").strip()
                if not item_id:
                    continue

                # 图片
                image_path_str = (row.get("local_image_path") or "").strip()
                if not image_path_str:
                    stats["skipped_no_image"] += 1
                    continue
                image_path = resolve_path(image_path_str)
                if not image_path.is_file():
                    stats["skipped_no_image"] += 1
                    continue
                b64 = image_to_base64(image_path)
                if b64 is None:
                    stats["skipped_image_error"] += 1
                    continue

                # 文本(和建索引用同一个函数)
                text = build_product_text(row).strip()
                if not text:
                    stats["skipped_empty_text"] += 1
                    continue

                # 切分
                split = split_by_hash(item_id, args.train_ratio, args.valid_ratio)

                # 写文件
                img_files[split].write(f"{numeric_id}\t{b64}\n")
                txt_files[split].write(
                    json.dumps(
                        {"text_id": numeric_id, "text": text, "image_ids": [numeric_id]},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                id_mapping_rows.append(
                    {
                        "numeric_id": str(numeric_id),
                        "item_id": item_id,
                        "product_type": category,
                        "split": split,
                    }
                )
                stats["per_category"][category] += 1
                stats["per_split"][split] += 1
                numeric_id += 1

        print(f"[{category}] 完成,累计 {stats['per_category'][category]} 条")

    for f in img_files.values():
        f.close()
    for f in txt_files.values():
        f.close()

    # 写 id_mapping.csv
    with (output_dir / "id_mapping.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["numeric_id", "item_id", "product_type", "split"])
        writer.writeheader()
        writer.writerows(id_mapping_rows)

    # 统计报告
    print("\n" + "=" * 50)
    print("转换完成")
    print(f"总商品数:     {stats['total']}")
    print(f"成功转换:     {sum(stats['per_category'].values())}")
    print(f"跳过(无图):   {stats['skipped_no_image']}")
    print(f"跳过(图坏):   {stats['skipped_image_error']}")
    print(f"跳过(空文本): {stats['skipped_empty_text']}")
    print(f"\n按类别:")
    for cat in categories:
        print(f"  {cat}: {stats['per_category'][cat]}")
    print(f"\n按划分:")
    for split in splits:
        count = stats['per_split'][split]
        ratio = count / sum(stats['per_category'].values()) * 100 if sum(stats['per_category'].values()) else 0
        print(f"  {split}: {count} ({ratio:.1f}%)")
    print(f"\n输出目录: {output_dir.relative_to(REPO_ROOT)}")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"错误:{exc}", file=sys.stderr)
        raise SystemExit(1)
