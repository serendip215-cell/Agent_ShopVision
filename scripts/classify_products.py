#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 product_type 整理商品数据，并生成可直接用于项目的数据目录。

这个脚本是数据整理器，不是根据图片预测类别的深度学习分类模型。
它使用商品 CSV 中已经存在的 product_type，将商品记录和图片复制到：

    data/processed_data/<product_type>/

默认模式用于首次生成空的输出目录。已有输出目录时，必须明确选择全量重建或增量追加。

全量重建：
    python scripts/classify_products.py \
        --input-file data/raw_data/Amazon_data/products.csv \
        --clean-output

增量追加：
    python scripts/classify_products.py \
        --input-file data/raw_data/Amazon_data_translated/products.csv \
        --output-dir data/processed_data \
        --append --dataset-id Amazon_data --dry-run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    "is_cleaned",
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

SUMMARY_FIELDS = ["product_type", "record_count", "image_ok", "image_missing", "image_failed"]
INDEX_FILE_NAME = "merge_index.jsonl"
CONTENT_FIELDS = ["product_type", "item_name", "description", "brand", "color", "material"]


def clean_text(value: object) -> str:
    return str(value or "").replace("\ufeff", "").strip()


def normalize_cleaned_flag(value: object) -> str:
    """返回统一的小写布尔文本；缺失或无法识别时默认为 false。"""

    return "true" if clean_text(value).lower() in {"true", "1", "yes", "y"} else "false"


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
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """原子写入合并索引，避免中断时留下半个索引文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


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


def scan_image_index(destination_dir: Path) -> tuple[dict[str, Path], dict[str, str]]:
    """扫描已有图片，返回 SHA-256 到路径和文件名到 SHA-256 的索引。"""

    by_digest: dict[str, Path] = {}
    by_name: dict[str, str] = {}
    if not destination_dir.is_dir():
        return by_digest, by_name
    for image_path in destination_dir.iterdir():
        if not image_path.is_file():
            continue
        try:
            digest = sha256_file(image_path)
        except OSError:
            continue
        by_digest.setdefault(digest, image_path)
        by_name.setdefault(image_path.name, digest)
    return by_digest, by_name


def copy_or_reuse_image(
    source: Path,
    destination_dir: Path,
    by_digest: dict[str, Path],
    by_name: dict[str, str],
    dry_run: bool = False,
) -> tuple[Path, str, bool]:
    """按内容复用图片；同名但内容不同的图片使用哈希后缀，绝不覆盖旧文件。"""

    digest = sha256_file(source)
    existing = by_digest.get(digest)
    if existing is not None:
        return existing, digest, True

    original_name = source.name
    output_name = original_name
    previous_digest = by_name.get(output_name)
    if previous_digest is not None and previous_digest != digest:
        output_name = f"{source.stem}_{digest[:12]}{source.suffix}"
        suffix = 1
        while output_name in by_name and by_name[output_name] != digest:
            output_name = f"{source.stem}_{digest[:12]}_{suffix}{source.suffix}"
            suffix += 1

    destination = destination_dir / output_name
    if not dry_run and not destination.exists():
        shutil.copy2(source, destination)
    by_digest[digest] = destination
    by_name[output_name] = digest
    return destination, digest, False


def content_fingerprint(row: dict[str, str], image_digest: str) -> str:
    payload = "\x1f".join(clean_text(row.get(field, "")) for field in CONTENT_FIELDS)
    payload = f"{payload}\x1f{image_digest}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_key(dataset_id: str, item_id: str) -> str:
    return f"{dataset_id}::{item_id}"


def resolve_existing_image_path(value: str, repo_root: Path) -> Path:
    path = Path(clean_text(value))
    if path.is_absolute():
        return path
    return repo_root / path


def make_output_row(raw: dict[str, str], product_type: str, local_image_path: str, image_status: str,
                    height: object, width: object) -> dict[str, object]:
    return {
        "item_id": clean_text(raw.get("item_id")),
        "product_type": product_type,
        "item_name": clean_text(raw.get("item_name")),
        "description": clean_text(raw.get("description")),
        "brand": clean_text(raw.get("brand")),
        "color": clean_text(raw.get("color")),
        "material": clean_text(raw.get("material")),
        "local_image_path": local_image_path,
        "image_status": image_status,
        "image_height": height,
        "image_width": width,
        "is_cleaned": normalize_cleaned_flag(raw.get("is_cleaned")),
    }


def make_quality_row(raw: dict[str, str], product_type: str, local_image_path: str,
                     source_image_path: str, decode_ok: str, height: object, width: object,
                     image_format: str, file_size: object, image_digest: str,
                     quality_status: str, quality_reason: str) -> dict[str, object]:
    return {
        "item_id": clean_text(raw.get("item_id")),
        "product_type": product_type,
        "image_path": local_image_path,
        "source_image_path": source_image_path,
        "decode_ok": decode_ok,
        "actual_height": height,
        "actual_width": width,
        "format": image_format,
        "file_size_bytes": file_size,
        "sha256": image_digest,
        "quality_status": quality_status,
        "quality_reason": quality_reason,
    }


def summary_for_categories(category_rows: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    summary_rows: list[dict[str, object]] = []
    for category in sorted(category_rows):
        status_counts: Counter[str] = Counter(clean_text(row.get("image_status")) for row in category_rows[category])
        summary_rows.append(
            {
                "product_type": category,
                "record_count": len(category_rows[category]),
                "image_ok": status_counts["ok"],
                "image_missing": status_counts["missing"],
                "image_failed": status_counts["failed"],
            }
        )
    return summary_rows


def prepare_backup(output_dir: Path, backup_dir: Path) -> Path | None:
    if not output_dir.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"processed_data_{timestamp}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(output_dir, target)
    return target


def prepare_dataset(
    input_file: Path,
    output_dir: Path,
    repo_root: Path,
    clean_output: bool,
    append: bool,
    dataset_id: str | None,
    dry_run: bool,
    backup_dir: Path | None,
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

    if append and clean_output:
        raise ValueError("--append 和 --clean-output 不能同时使用")
    if append and not dataset_id:
        raise ValueError("增量追加必须提供 --dataset-id，例如 --dataset-id Amazon_data")
    dataset_id = clean_text(dataset_id) or input_file.parent.name

    output_has_content = output_dir.exists() and any(output_dir.iterdir())
    if not append and not clean_output and output_has_content:
        raise ValueError(
            f"输出目录已有内容：{output_dir}。请明确选择 --append 增量追加，"
            "或使用 --clean-output 全量重建，脚本不会默认覆盖已有结果。"
        )
    if dry_run and clean_output:
        raise ValueError("--dry-run 不能与 --clean-output 同时使用")
    if backup_dir and not append:
        raise ValueError("--backup-dir 只用于 --append 增量追加")
    if backup_dir and dry_run:
        raise ValueError("--backup-dir 不能与 --dry-run 同时使用")

    if backup_dir:
        backup_path = prepare_backup(output_dir, backup_dir)
        if backup_path:
            print(f"已备份旧输出：{backup_path}")

    if clean_output and output_dir.exists():
        shutil.rmtree(output_dir)
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    category_map = category_map or {}
    grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for raw in raw_rows:
        normalized_type = normalize_product_type(raw.get("product_type", ""), category_map)
        normalized = dict(raw)
        normalized["product_type"] = normalized_type
        grouped[safe_category(normalized_type)].append(normalized)

    category_rows: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    category_quality: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    image_indices: dict[str, tuple[dict[str, Path], dict[str, str]]] = {}
    existing_content_hashes: set[str] = set()
    existing_source_hashes: dict[str, str] = {}
    index_records = read_jsonl(output_dir / INDEX_FILE_NAME) if append else []
    index_identities: set[tuple[str, str, str]] = set()

    for record in index_records:
        record_source_key = clean_text(record.get("source_key"))
        if not record_source_key:
            record_source_key = source_key(clean_text(record.get("dataset_id")), clean_text(record.get("item_id")))
        record_hash = clean_text(record.get("record_hash"))
        if record_hash:
            existing_content_hashes.add(record_hash)
        if record_source_key:
            existing_source_hashes[record_source_key] = record_hash

    if append and output_dir.is_dir():
        for category_dir in sorted(output_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            products_path = category_dir / "products.csv"
            if not products_path.is_file():
                continue
            category = category_dir.name
            rows = read_csv(products_path)
            for row in rows:
                row["is_cleaned"] = normalize_cleaned_flag(row.get("is_cleaned"))
            category_rows[category].extend(rows)
            quality_path = category_dir / "image_quality_report.csv"
            if quality_path.is_file():
                category_quality[category].extend(read_csv(quality_path))
            image_indices[category] = scan_image_index(category_dir / "images")
            quality_by_location = {
                (clean_text(row.get("item_id")), clean_text(row.get("image_path"))): row
                for row in category_quality[category]
            }
            for row in rows:
                image_path = clean_text(row.get("local_image_path"))
                quality = quality_by_location.get((clean_text(row.get("item_id")), image_path), {})
                image_digest = clean_text(quality.get("sha256"))
                if not image_digest and image_path:
                    candidate = resolve_existing_image_path(image_path, repo_root)
                    if candidate.is_file():
                        try:
                            image_digest = sha256_file(candidate)
                        except OSError:
                            image_digest = ""
                record_hash = content_fingerprint(row, image_digest)
                existing_content_hashes.add(record_hash)
                legacy_key = source_key(f"legacy/{category}", clean_text(row.get("item_id")))
                existing_source_hashes.setdefault(legacy_key, record_hash)
                identity = (legacy_key, category, image_path)
                if identity not in index_identities:
                    index_records.append(
                        {
                            "dataset_id": "legacy",
                            "item_id": clean_text(row.get("item_id")),
                            "source_key": legacy_key,
                            "category": category,
                            "record_hash": record_hash,
                            "image_hash": image_digest,
                            "local_image_path": image_path,
                        }
                    )
                    index_identities.add(identity)

    affected_categories: set[str] = set()
    seen_source_hashes: dict[str, str] = {}
    seen_content_hashes: set[str] = set()
    added_records: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()

    for category, rows in sorted(grouped.items()):
        category_dir = output_dir / category
        output_images = category_dir / "images"
        if not dry_run:
            output_images.mkdir(parents=True, exist_ok=True)
        if category not in image_indices:
            image_indices[category] = scan_image_index(output_images)
        by_digest, by_name = image_indices[category]

        for raw in rows:
            item_id = clean_text(raw.get("item_id"))
            current_source_key = source_key(dataset_id, item_id)
            source_value = clean_text(raw.get("local_image_path"))
            source_path = resolve_source_path(source_value, input_file, repo_root)
            image_digest = ""
            if source_path.is_file():
                try:
                    image_digest = sha256_file(source_path)
                except OSError:
                    image_digest = ""
            record_hash = content_fingerprint(raw, image_digest)

            if current_source_key in existing_source_hashes:
                if existing_source_hashes[current_source_key] == record_hash:
                    stats["duplicate"] += 1
                else:
                    stats["conflict"] += 1
                continue
            if current_source_key in seen_source_hashes:
                if seen_source_hashes[current_source_key] == record_hash:
                    stats["duplicate"] += 1
                else:
                    stats["conflict"] += 1
                continue
            if record_hash in existing_content_hashes or record_hash in seen_content_hashes:
                stats["duplicate"] += 1
                continue

            image_status = "missing"
            decode_ok = "false"
            width = height = ""
            image_format = ""
            quality_reason = "图片文件不存在"
            destination: Path | None = None
            copied_or_reused = False

            if source_path.is_file():
                try:
                    destination, image_digest, reused = copy_or_reuse_image(
                        source_path, output_images, by_digest, by_name, dry_run=dry_run
                    )
                    copied_or_reused = not reused
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

            local_path = repo_relative(destination, repo_root) if destination else ""
            output_row = make_output_row(raw, category, local_path, image_status, height, width)
            quality_row = make_quality_row(
                raw,
                category,
                local_path,
                source_value,
                decode_ok,
                height,
                width,
                image_format,
                destination.stat().st_size if destination and destination.exists() else "",
                image_digest,
                "pass" if image_status == "ok" else image_status,
                quality_reason,
            )
            category_rows[category].append(output_row)
            category_quality[category].append(quality_row)
            affected_categories.add(category)
            seen_source_hashes[current_source_key] = record_hash
            seen_content_hashes.add(record_hash)
            added_records.append(
                {
                    "dataset_id": dataset_id,
                    "item_id": item_id,
                    "source_key": current_source_key,
                    "category": category,
                    "record_hash": record_hash,
                    "image_hash": image_digest,
                    "local_image_path": local_path,
                    "image_copied": copied_or_reused,
                }
            )
            stats["added"] += 1

    if not dry_run:
        for category in sorted(affected_categories if append else category_rows):
            category_dir = output_dir / category
            write_csv(category_dir / "products.csv", FINAL_FIELDS, category_rows[category])
            write_csv(category_dir / "image_quality_report.csv", QUALITY_FIELDS, category_quality[category])
        write_csv(output_dir / "dataset_summary.csv", SUMMARY_FIELDS, summary_for_categories(category_rows))
        if append or dataset_id:
            records_by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
            for record in index_records + added_records:
                identity = (
                    clean_text(record.get("source_key")),
                    clean_text(record.get("category")),
                    clean_text(record.get("local_image_path")),
                )
                records_by_identity[identity] = record
            write_jsonl(output_dir / INDEX_FILE_NAME, list(records_by_identity.values()))

    print(f"输入记录: {len(raw_rows)}")
    print(f"新增记录: {stats['added']}")
    print(f"重复跳过: {stats['duplicate']}")
    print(f"冲突跳过: {stats['conflict']}")
    print(f"模式: {'增量追加' if append else '全量重建'}{'（预览）' if dry_run else ''}")
    print(f"输出目录: {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 product_type 整理商品数据，并支持安全增量追加")
    parser.add_argument("--input-file", required=True, help="输入商品 CSV 文件路径")
    parser.add_argument("--output-dir", default="data/processed_data", help="按类别输出的根目录")
    parser.add_argument("--repo-root", default=None, help="项目根目录，默认根据脚本位置自动判断")
    parser.add_argument("--append", action="store_true", help="保留旧结果，去重后将新记录追加到已有分类")
    parser.add_argument("--dataset-id", default=None, help="数据集标识；--append 时必需，例如 Amazon_data")
    parser.add_argument("--dry-run", action="store_true", help="只预览新增、重复和冲突数量，不修改文件")
    parser.add_argument("--backup-dir", default=None, help="增量追加前备份旧输出的目录")
    parser.add_argument("--clean-output", action="store_true", help="删除整个输出目录后全量重建")
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
    backup_dir = Path(args.backup_dir) if args.backup_dir else None
    if backup_dir and not backup_dir.is_absolute():
        backup_dir = repo_root / backup_dir
    category_map = parse_category_map(args.category_map)
    prepare_dataset(
        input_file.resolve(),
        output_dir.resolve(),
        repo_root,
        args.clean_output,
        args.append,
        args.dataset_id,
        args.dry_run,
        backup_dir.resolve() if backup_dir else None,
        category_map,
    )


if __name__ == "__main__":
    main()
