#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口：请优先使用 scripts/classify_products.py。

旧版本脚本按数据来源输出 MUGE_data；现在转而按 product_type 分类。
"""
from __future__ import annotations
import argparse
from pathlib import Path
from classify_products import parse_category_map, prepare_dataset

def main() -> None:
    parser = argparse.ArgumentParser(description="按 product_type 整理 MUGE 商品数据（兼容入口）")
    parser.add_argument("--input-dir", default="data/raw_data/MUGE_data")
    parser.add_argument("--output-dir", default="data/processed_data")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--clean-output", action="store_true")
    parser.add_argument("--category-map", default="双肩包=包,运动鞋=鞋")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    if not input_dir.is_absolute(): input_dir = repo_root / input_dir
    if not output_dir.is_absolute(): output_dir = repo_root / output_dir
    prepare_dataset((input_dir / "products.csv").resolve(), output_dir.resolve(), repo_root, args.clean_output, parse_category_map(args.category_map))

if __name__ == "__main__":
    main()
