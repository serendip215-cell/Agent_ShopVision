#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可复用的商品 CSV 字段、路径和图片对应检查器。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path


STANDARD_FIELDS = [
    "item_id", "product_type", "item_name", "description", "brand", "color",
    "material", "local_image_path", "image_status", "image_height", "image_width",
]
DEFAULT_REQUIRED_FIELDS = ["item_id", "product_type", "item_name", "local_image_path"]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                return list(reader.fieldnames or []), list(reader)
        except UnicodeDecodeError as error:
            last_error = error
    raise RuntimeError(f"无法读取 CSV 编码：{path}") from last_error


def resolve_path(value: str, input_file: Path, repo_root: Path) -> Path:
    path = Path(str(value or "").strip())
    if path.is_absolute():
        return path
    for candidate in (repo_root / path, input_file.parent / path):
        if candidate.is_file():
            return candidate.resolve()
    return (repo_root / path).resolve()


def check_file(input_file: Path, repo_root: Path, required_fields: list[str], check_images: bool) -> dict[str, object]:
    if not input_file.is_file():
        raise FileNotFoundError(f"找不到输入 CSV：{input_file}")
    fields, rows = read_csv(input_file)
    field_set = set(fields)
    missing_fields = [field for field in required_fields if field not in field_set]
    extra_fields = [field for field in fields if field not in STANDARD_FIELDS]
    empty_counts: Counter[str] = Counter()
    for row in rows:
        for field in required_fields:
            if not str(row.get(field, "") or "").strip():
                empty_counts[field] += 1

    ids = [str(row.get("item_id", "") or "").strip() for row in rows]
    duplicate_ids = sorted(i for i, count in Counter(ids).items() if i and count > 1)
    absolute_paths: list[dict[str, object]] = []
    missing_images: list[dict[str, object]] = []
    status_mismatches: list[dict[str, object]] = []
    if check_images and "local_image_path" in field_set:
        for line, row in enumerate(rows, start=2):
            raw_path = str(row.get("local_image_path", "") or "").strip()
            if not raw_path:
                continue
            if Path(raw_path).is_absolute():
                absolute_paths.append({"line": line, "path": raw_path})
            resolved = resolve_path(raw_path, input_file, repo_root)
            exists = resolved.is_file() and resolved.stat().st_size > 0 if resolved.exists() else False
            if not exists:
                missing_images.append({"line": line, "item_id": row.get("item_id", ""), "path": raw_path})
            declared = str(row.get("image_status", "") or "").strip().lower()
            if declared == "ok" and not exists:
                status_mismatches.append({"line": line, "item_id": row.get("item_id", ""), "declared": declared, "actual": "missing"})
            if declared in {"missing", "failed"} and exists:
                status_mismatches.append({"line": line, "item_id": row.get("item_id", ""), "declared": declared, "actual": "ok"})

    errors: list[str] = []
    if missing_fields: errors.append("missing_fields")
    if any(empty_counts.values()): errors.append("empty_required_fields")
    if duplicate_ids: errors.append("duplicate_item_id")
    if absolute_paths: errors.append("absolute_image_path")
    if missing_images: errors.append("missing_images")
    if status_mismatches: errors.append("image_status_mismatch")
    return {
        "input_file": input_file.as_posix(), "repo_root": repo_root.as_posix(), "row_count": len(rows),
        "fields": fields, "standard_fields": STANDARD_FIELDS, "missing_fields": missing_fields,
        "extra_fields": extra_fields, "required_empty_counts": dict(empty_counts),
        "duplicate_item_ids": duplicate_ids, "absolute_image_paths": absolute_paths,
        "missing_images": missing_images, "image_status_mismatches": status_mismatches,
        "errors": errors, "valid": not errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查商品 CSV 的字段和图片路径")
    parser.add_argument("--input-file", required=True, help="要检查的商品 CSV")
    parser.add_argument("--repo-root", default=None, help="项目根目录")
    parser.add_argument("--report", default=None, help="可选 JSON 报告输出路径")
    parser.add_argument("--required-fields", default=",".join(DEFAULT_REQUIRED_FIELDS))
    parser.add_argument("--skip-images", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    input_file = Path(args.input_file)
    if not input_file.is_absolute(): input_file = repo_root / input_file
    required = [x.strip() for x in args.required_fields.split(",") if x.strip()]
    report = check_file(input_file.resolve(), repo_root, required, not args.skip_images)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute(): report_path = repo_root / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text + "\n", encoding="utf-8")
        print(f"报告已写入: {report_path}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
