#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 GPT6Luna 候选 CSV 对应的图片复制到候选结果目录。"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "processed_data_gpt6luna"


def resolve_source(raw_path: str) -> Path | None:
    if not raw_path:
        return None
    relative = Path(raw_path.replace("\\", "/"))
    candidates = [ROOT / relative, OUTPUT / relative]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def copy_and_rewrite(
    csv_path: Path,
    image_group: str,
    category_field: str | None = None,
    output_name: str | None = None,
) -> dict:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    copied = 0
    missing = 0
    for row in rows:
        source = resolve_source((row.get("local_image_path") or "").strip())
        category = (row.get(category_field or "") or "").strip() if category_field else csv_path.parent.name
        if not category:
            category = "未分类"
        if source is None:
            missing += 1
            continue
        filename = source.name
        if image_group in {"包", "水杯", "鞋"}:
            destination_dir = OUTPUT / image_group / "images"
            relative_prefix = f"data/processed_data_gpt6luna/{image_group}/images"
        else:
            destination_dir = OUTPUT / image_group / category / "images"
            relative_prefix = f"data/processed_data_gpt6luna/{image_group}/{category}/images"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / filename
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        row["local_image_path"] = f"{relative_prefix}/{filename}".replace("\\", "/")
        copied += 1

    target_csv = csv_path.with_name(output_name or csv_path.name)
    with target_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return {
        "file": str(csv_path.relative_to(ROOT)),
        "output_file": str(target_csv.relative_to(ROOT)),
        "rows": len(rows),
        "copied": copied,
        "missing": missing,
    }


def main() -> int:
    report = []
    for category in ("包", "水杯", "鞋"):
        report.append(
            copy_and_rewrite(
                OUTPUT / category / "products.csv",
                category,
                output_name="products_with_images.csv",
            )
        )
    review_path = OUTPUT / "review_candidates.csv"
    if review_path.exists():
        report.append(
            copy_and_rewrite(
                review_path,
                "review_images",
                "source_category",
                output_name="review_candidates_with_images.csv",
            )
        )
    excluded_path = OUTPUT / "excluded_samples.csv"
    if excluded_path.exists():
        report.append(
            copy_and_rewrite(
                excluded_path,
                "excluded_images",
                "source_category",
                output_name="excluded_samples_with_images.csv",
            )
        )
    (OUTPUT / "image_copy_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = sum(item["copied"] for item in report)
    missing = sum(item["missing"] for item in report)
    print(f"已复制或确认图片 {total} 张，缺失 {missing} 张。")
    print(f"报告：{OUTPUT / 'image_copy_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
