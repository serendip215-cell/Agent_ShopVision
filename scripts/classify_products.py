#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 product_type 整理商品数据，并生成可直接用于项目的数据目录。

这个脚本是数据整理器，不是根据图片预测类别的深度学习分类模型。
它使用商品 CSV 中已经存在的 product_type，将商品记录和图片复制到：

    data/processed_data/<product_type>/

用法示例：
    python scripts/classify_products.py \
        --input-file data/raw_data/Amazon_data/products.csv \
        --clean-output
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - 环境错误
    raise SystemExit("缺少 Pillow，请先安装：python -m pip install Pillow") from exc


FINAL_FIELDS = [
    "item_id",
    "product_type",
    "item_name",
    "description",
    "brand",
    "color",
    "material",
    "local_image_path",
    "image_status",
    "image_height",
    "image_width",
]

QUALITY_FIELDS = [
    "item_id",
    "product_type",
    "image_path",
    "source_image_path",
    "decode_ok",
    "actual_height",
    "actual_width",
    "format",
    "file_size_bytes",
    "sha256",
    "quality_status",
    "quality_reason",
]


def clean_text(value: object) -> str:
    return str(value or "").replace("\ufeff", "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    last_error: UnicodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError as error:
            last_error = error
    raise RuntimeError(f"无法读取 CSV 编码：{path}") from last_error


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_product_type(value: str, category_map: dict[str, str]) -> str:
    value = clean_text(value) or "UNKNOWN"
    return clean_text(category_map.get(value, value)) or "UNKNOWN"


def safe_category(value: str) -> str:
    """将 product_type 转为安全目录名，同时尽量保留类别名称。"""

    value = clean_text(value) or "UNKNOWN"
    value = re.sub(r'[<>:"/\\|?*]+', "_", value).strip(" .")
    return value or "UNKNOWN"


def parse_category_map(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in value.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"类别映射格式错误：{pair}，应为 原类别=目标类别")
        source, target = pair.split("=", 1)
        result[clean_text(source)] = clean_text(target)
    return result


def resolve_source_path(value: str, input_file: Path, repo_root: Path) -> Path:
    source = Path(clean_text(value))
    if source.is_absolute():
        return source

    candidates = [repo_root / source, input_file.parent / source]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    # 返回最符合项目约定的路径，后面会记录 missing，而不是让整个批处理崩溃。
    return (repo_root / source).resolve()


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return Path(path).resolve().as_uri()


def copy_without_collision(
    source: Path,
    destination_dir: Path,
    used_names: dict[str, str],
) -> tuple[Path, str]:
    """复制图片；同名但内容不同的文件自动追加哈希，避免覆盖。"""

    digest = sha256_file(source)
    original_name = source.name
    previous_digest = used_names.get(original_name)
    if previous_digest == digest:
        return destination_dir / original_name, digest

    output_name = original_name
    if previous_digest is not None and previous_digest != digest:
        output_name = f"{source.stem}_{digest[:12]}{source.suffix}"

    destination = destination_dir / output_name
    if not destination.exists():
        shutil.copy2(source, destination)
    used_names[output_name] = digest
    if output_name == original_name:
        used_names[original_name] = digest
    return destination, digest


def prepare_dataset(
    input_file: Path,
    output_dir: Path,
    repo_root: Path,
    clean_output: bool,
    category_map: dict[str, str] | None = None,
) -> None:
    if not input_file.is_file():
        raise FileNotFoundError(f"找不到输入商品 CSV：{input_file}")

    raw_rows = read_csv(input_file)
    if not raw_rows:
        raise ValueError(f"输入 CSV 没有商品记录：{input_file}")
    actual_fields = set(raw_rows[0].keys())
    required = {"item_id", "product_type", "item_name", "local_image_path"}
    missing_fields = sorted(required - actual_fields)
    if missing_fields:
        raise ValueError(f"输入 CSV 缺少必需字段：{', '.join(missing_fields)}")

    if clean_output and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    category_map = category_map or {}
    grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in raw_rows:
        normalized_type = normalize_product_type(row.get("product_type", ""), category_map)
        row = dict(row)
        row["product_type"] = normalized_type
        grouped[safe_category(normalized_type)].append(row)

    summary_rows: list[dict[str, object]] = []
    total_ok = total_missing = total_failed = 0

    for category, rows in sorted(grouped.items()):
        category_dir = output_dir / category
        output_images = category_dir / "images"
        output_images.mkdir(parents=True, exist_ok=True)
        used_names: dict[str, str] = {}
        output_rows: list[dict[str, object]] = []
        quality_rows: list[dict[str, object]] = []
        status_counts: Counter[str] = Counter()

        for raw in rows:
            item_id = clean_text(raw.get("item_id"))
            source_value = clean_text(raw.get("local_image_path"))
            source_path = resolve_source_path(source_value, input_file, repo_root)
            image_status = "missing"
            decode_ok = "false"
            width = height = ""
            image_format = ""
            quality_reason = "图片文件不存在"
            digest = ""
            destination = None

            if source_path.is_file():
                try:
                    destination, digest = copy_without_collision(source_path, output_images, used_names)
                    with Image.open(source_path) as image:
                        image.load()
                        width, height = image.size
                        image_format = image.format or source_path.suffix.lstrip(".").upper()
                    image_status = "ok"
                    decode_ok = "true"
                    quality_reason = ""
                except Exception as error:  # Pillow 和文件错误统一记录
                    image_status = "failed"
                    quality_reason = str(error)
                    if not digest:
                        digest = sha256_file(source_path)

            status_counts[image_status] += 1
            if image_status == "ok":
                total_ok += 1
            elif image_status == "missing":
                total_missing += 1
            else:
                total_failed += 1

            local_path = repo_relative(destination, repo_root) if destination else ""
            output_rows.append(
                {
                    "item_id": item_id,
                    "product_type": clean_text(raw.get("product_type")) or "UNKNOWN",
                    "item_name": clean_text(raw.get("item_name")),
                    "description": clean_text(raw.get("description")),
                    "brand": clean_text(raw.get("brand")),
                    "color": clean_text(raw.get("color")),
                    "material": clean_text(raw.get("material")),
                    "local_image_path": local_path,
                    "image_status": image_status,
                    "image_height": height,
                    "image_width": width,
                }
            )
            quality_rows.append(
                {
                    "item_id": item_id,
                    "product_type": clean_text(raw.get("product_type")) or "UNKNOWN",
                    "image_path": local_path,
                    "source_image_path": source_value,
                    "decode_ok": decode_ok,
                    "actual_height": height,
                    "actual_width": width,
                    "format": image_format,
                    "file_size_bytes": destination.stat().st_size if destination and destination.exists() else "",
                    "sha256": digest,
                    "quality_status": "pass" if image_status == "ok" else image_status,
                    "quality_reason": quality_reason,
                }
            )

        write_csv(category_dir / "products.csv", FINAL_FIELDS, output_rows)
        write_csv(category_dir / "image_quality_report.csv", QUALITY_FIELDS, quality_rows)
        summary_rows.append(
            {
                "product_type": category,
                "record_count": len(rows),
                "image_ok": status_counts["ok"],
                "image_missing": status_counts["missing"],
                "image_failed": status_counts["failed"],
            }
        )

    write_csv(
        output_dir / "dataset_summary.csv",
        ["product_type", "record_count", "image_ok", "image_missing", "image_failed"],
        summary_rows,
    )
    print(f"输入记录: {len(raw_rows)}")
    print(f"类别数: {len(grouped)}")
    print(f"图片有效: {total_ok}; 缺失: {total_missing}; 失败: {total_failed}")
    print(f"输出目录: {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 product_type 整理商品数据")
    parser.add_argument("--input-file", required=True, help="输入商品 CSV 文件路径")
    parser.add_argument("--output-dir", default="data/processed_data", help="按类别输出的根目录")
    parser.add_argument("--repo-root", default=None, help="项目根目录，默认根据脚本位置自动判断")
    parser.add_argument("--clean-output", action="store_true", help="运行前删除整个输出目录")
    parser.add_argument(
        "--category-map",
        default="",
        help="类别归一化映射，例如：双肩包=包,运动鞋=鞋",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    input_file = Path(args.input_file)
    if not input_file.is_absolute():
        input_file = repo_root / input_file
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    category_map = parse_category_map(args.category_map)
    prepare_dataset(input_file.resolve(), output_dir.resolve(), repo_root, args.clean_output, category_map)


if __name__ == "__main__":
    main()
