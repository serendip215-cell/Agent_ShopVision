from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_INPUT_ROOT = PROJECT_ROOT / "data" / "processed_data"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed_data_clean"

# These rules remove only high-confidence text conflicts. Ambiguous rows are
# retained and written to review_candidates.csv so that they can be inspected.
CATEGORY_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "水杯": {
        "primary": (
            "水杯", "保温杯", "马克杯", "纸杯", "吸管杯", "茶杯", "咖啡杯",
            "玻璃杯", "奶茶杯", "豆浆杯", "酒杯", "红酒杯", "高脚杯", "量杯",
            "品茗杯", "主人杯", "快餐杯", "漱口杯", "啤酒杯", "焖烧杯", "饮料杯", "杯子",
        ),
        "strong_exclude": (
            "文胸", "胸罩", "内衣", "罩杯", "钢圈", "聚拢", "美背", "全罩杯",
            "无钢圈", "鞋架", "鞋柜", "鞋盒", "鞋子", "运动鞋", "双肩包",
            "背包", "书包", "斜挎包", "裙子", "裤子", "袜子", "手机壳", "炒锅",
            "奖杯", "世界杯", "杯赛", "不沾杯", "口红", "牙刷", "牙杯", "漱口",
            "果冻", "奶冻", "零食", "蛋糕", "鸟食", "宠物", "置物架", "收纳架",
            "收纳柜", "书架", "书柜", "货架", "层架", "杯架", "消毒柜", "橱柜",
            "茶杯犬", "真狗", "狗随身杯", "宠物饮水", "宠物水杯", "摆件", "托盘",
            "汽车脚垫", "脚垫", "打包袋", "洗头", "洗发", "泳衣", "泳装", "项链",
        ),
        "accessory_only": ("杯垫", "杯盖", "杯套", "杯刷", "杯架", "杯托", "杯洗", "杯罩", "吸管"),
    },
    "包": {
        "primary": (
            "包", "背包", "双肩包", "书包", "斜挎包", "手提包", "旅行包",
            "钱包", "电脑包", "腰包", "托特包", "胸包", "妈咪包",
        ),
        "strong_exclude": (
            "文胸", "胸罩", "内衣", "罩杯", "钢圈", "保温杯", "马克杯",
            "水杯", "奶茶杯", "纸杯", "手机壳", "炒锅", "电饭锅",
            "书包置物架", "书包柜", "书包架", "置物架", "收纳架", "收纳柜",
            "书架", "书柜", "货架", "衣柜", "橱柜", "展示架", "鞋架", "鞋柜",
        ),
        "accessory_only": ("鞋架", "鞋柜", "鞋盒", "鞋垫", "杯套"),
    },
    "鞋": {
        "primary": (
            "鞋", "运动鞋", "皮鞋", "高跟鞋", "板鞋", "球鞋", "凉鞋",
            "拖鞋", "靴子", "帆布鞋", "单鞋", "休闲鞋", "布鞋",
        ),
        "strong_exclude": (
            "文胸", "胸罩", "内衣", "罩杯", "钢圈", "水杯", "保温杯",
            "马克杯", "奶茶杯", "纸杯", "双肩包", "背包", "书包", "手机壳",
            "炒锅", "电饭锅", "鞋架", "鞋柜", "鞋盒", "鞋凳", "试鞋凳", "沙发凳",
            "宠物", "狗防咬", "汽车鞋", "鞋玩具", "装饰毛球", "置物架", "收纳架",
            "书架", "书柜", "货架",
        ),
        "accessory_only": ("鞋架", "鞋柜", "鞋盒", "鞋垫", "鞋油", "鞋刷"),
    },
}

REQUIRED_FIELDS = (
    "item_id", "product_type", "item_name", "description", "brand", "color",
    "material", "local_image_path", "image_status", "image_height", "image_width",
)


def normalize_text(*values: Any) -> str:
    text = " ".join(str(v or "") for v in values)
    text = re.sub(r"\s+", "", text).lower()
    return text


def contains_any(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value.lower() in text]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV 没有表头：{path}")
        return list(reader.fieldnames), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def resolve_repo_path(value: str) -> Path:
    value = str(value or "").replace("\\", "/")
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT.joinpath(*value.split("/"))


def relative_repo_path(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze_row(category: str, row: dict[str, str]) -> dict[str, Any]:
    rules = CATEGORY_RULES[category]
    text = normalize_text(row.get("item_name"), row.get("description"), row.get("brand"), row.get("material"))
    primary_hits = contains_any(text, rules["primary"])
    exclude_hits = contains_any(text, rules["strong_exclude"])
    accessory_hits = contains_any(text, rules["accessory_only"])

    # A title such as "水杯盖" or "恒温杯垫加杯子" contains the character
    # 杯 but describes an accessory, not the target drinkware product.
    if category == "水杯":
        water_accessory_hits = contains_any(
            text, ("杯垫", "杯盖", "杯套", "杯刷", "杯架", "杯托", "杯洗", "杯罩")
        )
        if water_accessory_hits:
            return {
                "decision": "exclude",
                "reason": "accessory_not_target_product",
                "evidence": ",".join(water_accessory_hits),
                "text": text,
            }

    # A bag title may mention an attached cup, but a phone case, bra or other
    # non-bag product should still be excluded even when the word "包" appears.
    if category == "包":
        hard_bag_conflicts = contains_any(
            text, ("文胸", "胸罩", "内衣", "罩杯", "钢圈", "手机壳", "炒锅", "电饭锅")
        )
        if hard_bag_conflicts:
            return {
                "decision": "exclude",
                "reason": "strong_category_conflict",
                "evidence": ",".join(hard_bag_conflicts),
                "text": text,
            }
        # "背包外挂水杯" is still a bag; cup words alone are not enough to
        # reject a row when a strong bag product term is present.
        exclude_hits = [hit for hit in exclude_hits if hit not in {"水杯", "保温杯", "马克杯", "奶茶杯", "纸杯"}]

    # Shoe accessories contain the character 鞋 but are not shoes themselves.
    if category == "鞋" and accessory_hits:
        footwear_hits = contains_any(
            text, ("运动鞋", "皮鞋", "高跟鞋", "板鞋", "球鞋", "凉鞋", "拖鞋", "靴子", "帆布鞋", "单鞋", "休闲鞋", "布鞋")
        )
        if not footwear_hits:
            return {
                "decision": "exclude",
                "reason": "accessory_not_target_product",
                "evidence": ",".join(accessory_hits),
                "text": text,
            }

    # A primary product term takes precedence over accessory words. For example,
    # "保温杯带杯盖" is a cup, while "杯垫" alone is not a cup.
    if exclude_hits:
        return {
            "decision": "exclude",
            "reason": "strong_category_conflict",
            "evidence": ",".join(exclude_hits),
            "text": text,
        }
    if accessory_hits and not primary_hits:
        return {
            "decision": "exclude",
            "reason": "accessory_not_target_product",
            "evidence": ",".join(accessory_hits),
            "text": text,
        }
    if not primary_hits:
        return {
            "decision": "review",
            "reason": "no_explicit_category_evidence",
            "evidence": "",
            "text": text,
        }
    return {
        "decision": "keep",
        "reason": "category_evidence_consistent",
        "evidence": ",".join(primary_hits),
        "text": text,
    }


def copy_filtered_quality_report(source_dir: Path, output_dir: Path, kept_ids: set[str], category: str) -> None:
    source_report = source_dir / "image_quality_report.csv"
    if not source_report.exists():
        return
    fields, rows = read_csv(source_report)
    output_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("item_id", "") not in kept_ids:
            continue
        image_name = Path(str(row.get("image_path", "")).replace("\\", "/")).name
        row["image_path"] = f"{relative_repo_path(output_dir)}/images/{image_name}"
        output_rows.append(row)
    write_csv(output_dir / "image_quality_report.csv", fields, output_rows)


def make_field_report(rows: list[dict[str, str]], category: str) -> dict[str, Any]:
    duplicate_ids = [item_id for item_id, count in Counter(row.get("item_id", "") for row in rows).items() if count > 1]
    missing_required = {
        field: sum(1 for row in rows if not str(row.get(field, "")).strip())
        for field in REQUIRED_FIELDS
    }
    missing_images = sum(
        1 for row in rows
        if not resolve_repo_path(row.get("local_image_path", "")).is_file()
    )
    return {
        "valid": not duplicate_ids and missing_images == 0,
        "category": category,
        "record_count": len(rows),
        "duplicate_item_ids": duplicate_ids,
        "missing_required_fields": missing_required,
        "missing_images": missing_images,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def process_category(category: str, input_root: Path, output_root: Path) -> dict[str, Any]:
    source_dir = input_root / category
    output_dir = output_root / category
    source_products = source_dir / "products.csv"
    fields, source_rows = read_csv(source_products)
    output_fields = list(fields)
    retained: list[dict[str, str]] = []
    excluded: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    kept_ids: set[str] = set()
    copied_images = 0

    for row in source_rows:
        result = analyze_row(category, row)
        item_id = row.get("item_id", "")
        image_source = resolve_repo_path(row.get("local_image_path", ""))
        image_name = Path(str(row.get("local_image_path", "")).replace("\\", "/")).name
        if result["decision"] == "exclude":
            excluded.append({
                "item_id": item_id,
                "source_category": category,
                "item_name": row.get("item_name", ""),
                "local_image_path": row.get("local_image_path", ""),
                "decision": result["decision"],
                "reason": result["reason"],
                "evidence": result["evidence"],
            })
            continue

        target_image = output_dir / "images" / image_name
        if image_source.is_file():
            target_image.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image_source, target_image)
            copied_images += 1
        output_row = dict(row)
        output_row["local_image_path"] = f"{relative_repo_path(output_dir)}/images/{image_name}"
        retained.append(output_row)
        kept_ids.add(item_id)
        if result["decision"] == "review":
            review.append({
                "item_id": item_id,
                "source_category": category,
                "item_name": row.get("item_name", ""),
                "local_image_path": output_row["local_image_path"],
                "decision": result["decision"],
                "reason": result["reason"],
                "evidence": result["evidence"],
            })

    write_csv(output_dir / "products.csv", output_fields, retained)
    copy_filtered_quality_report(source_dir, output_dir, kept_ids, category)
    field_report = make_field_report(retained, category)
    (output_dir / "field_check_report.json").write_text(
        json.dumps(field_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "product_type": category,
        "input_count": len(source_rows),
        "record_count": len(retained),
        "excluded_count": len(excluded),
        "review_count": len(review),
        "image_ok": sum(1 for row in retained if row.get("image_status") == "ok"),
        "image_missing": sum(1 for row in retained if not resolve_repo_path(row.get("local_image_path", "")).is_file()),
        "image_failed": sum(1 for row in retained if row.get("image_status") not in {"ok", "readable"}),
        "copied_images": copied_images,
        "excluded": excluded,
        "review": review,
    }


def write_readme(output_root: Path, summaries: list[dict[str, Any]], generated_at: str) -> None:
    total_input = sum(item["input_count"] for item in summaries)
    total_output = sum(item["record_count"] for item in summaries)
    total_excluded = sum(item["excluded_count"] for item in summaries)
    total_review = sum(item["review_count"] for item in summaries)
    lines = [
        "# processed_data_clean",
        "",
        "本目录是对 `data/processed_data/` 的候选清洗结果，供人工核查。原始 `data/processed_data/` 未被覆盖。",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 清洗范围",
        "",
        "- 当前只清洗包、水杯、鞋三个目录；不划分训练集、验证集和测试集。",
        "- 只剔除文本证据明确与当前类别冲突的记录。",
        "- 无明确类别词但没有强冲突的记录会保留，并写入 `review_candidates.csv`。",
        "- 所有路径使用仓库根目录相对路径。",
        "- 原始商品表、原始图片和原始报告不被修改。",
        "",
        "## 规则说明",
        "",
        "水杯类别会排除文胸、内衣、罩杯、鞋、背包等明确冲突内容；包和鞋类别也会排除强冲突词。",
        "商品配件（例如杯垫、杯盖、鞋架、鞋盒）在没有目标商品主体词时会进入排除清单。",
        "规则只处理高置信度冲突，不根据标题缺少某个关键词就直接删除图片。",
        "",
        "## 当前统计",
        "",
        f"- 清洗前记录：{total_input} 条；",
        f"- 保留记录：{total_output} 条；",
        f"- 排除记录：{total_excluded} 条；",
        f"- 待复核记录：{total_review} 条。",
        "",
        "每个类别目录包含 `products.csv`、`images/`、`image_quality_report.csv` 和 `field_check_report.json`。",
        "",
        "## 核查文件",
        "",
        "- `excluded_samples.csv`：已按规则排除的记录；",
        "- `review_candidates.csv`：没有明确类别证据、建议人工或视觉模型复核的记录；",
        "- `dataset_summary.csv`：清洗前后数量、图片状态和待复核数量；",
        "- `cleaning_report.json`：完整清洗统计和排除原因。",
        "",
        "核查无误后，再将本目录内容覆盖或合并回正式处理目录。",
        "",
    ]
    (output_root / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean non-target records from processed product categories without overwriting input.")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    input_root = args.input_root if args.input_root.is_absolute() else PROJECT_ROOT / args.input_root
    output_root = args.output_root if args.output_root.is_absolute() else PROJECT_ROOT / args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat()
    summaries: list[dict[str, Any]] = []
    all_excluded: list[dict[str, Any]] = []
    all_review: list[dict[str, Any]] = []
    for category in CATEGORY_RULES:
        summary = process_category(category, input_root, output_root)
        all_excluded.extend(summary.pop("excluded"))
        all_review.extend(summary.pop("review"))
        summaries.append(summary)

    summary_fields = [
        "product_type", "input_count", "record_count", "excluded_count", "review_count",
        "image_ok", "image_missing", "image_failed", "copied_images",
    ]
    write_csv(output_root / "dataset_summary.csv", summary_fields, summaries)
    review_fields = ["item_id", "source_category", "item_name", "local_image_path", "decision", "reason", "evidence"]
    write_csv(output_root / "excluded_samples.csv", review_fields, all_excluded)
    write_csv(output_root / "review_candidates.csv", review_fields, all_review)
    report = {
        "generated_at": generated_at,
        "input_root": relative_repo_path(input_root),
        "output_root": relative_repo_path(output_root),
        "category_rules": CATEGORY_RULES,
        "categories": summaries,
        "totals": {
            "input_count": sum(item["input_count"] for item in summaries),
            "record_count": sum(item["record_count"] for item in summaries),
            "excluded_count": len(all_excluded),
            "review_count": len(all_review),
        },
        "note": "This is a candidate cleaning output. The input directory was not overwritten.",
    }
    (output_root / "cleaning_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(output_root, summaries, generated_at)
    print(json.dumps(report["totals"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
