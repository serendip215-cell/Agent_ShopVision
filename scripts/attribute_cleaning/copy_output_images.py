#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把清洗结果中的商品图片复制到与 processed_data 相同的类别目录。"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "processed_data_cleaning"


def resolve_source(raw_path: str) -> Path | None:
    if not raw_path:
        return None
    relative = Path(raw_path.replace("\\", "/"))
    candidate = ROOT / relative
    return candidate if candidate.is_file() else None


def copy_category(category: str) -> dict[str, int | str]:
    csv_path = OUTPUT / category / "products.csv"
    if not csv_path.exists():
        return {"category": category, "rows": 0, "copied": 0, "missing": 0}

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    image_dir = OUTPUT / category / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing = 0
    for row in rows:
        source = resolve_source((row.get("local_image_path") or "").strip())
        if source is None:
            missing += 1
            continue
        destination = image_dir / source.name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        row["local_image_path"] = (
            f"data/processed_data_cleaning/{category}/images/{source.name}"
        ).replace("\\", "/")
        copied += 1

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return {"category": category, "rows": len(rows), "copied": copied, "missing": missing}


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    categories = sorted(path.parent.name for path in OUTPUT.glob("*/products.csv"))
    report = [copy_category(category) for category in categories]
    (OUTPUT / "image_copy_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = sum(int(item["copied"]) for item in report)
    missing = sum(int(item["missing"]) for item in report)
    print(f"已复制图片 {total} 张，缺失 {missing} 张。")
    print(f"报告：{OUTPUT / 'image_copy_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

