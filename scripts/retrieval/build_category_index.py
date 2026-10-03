"""Build per-category Chinese-CLIP and FAISS indexes.

Run from the repository root, for example:
    py -3 scripts/retrieval/build_category_index.py --categories "鞋" --overwrite
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from encoder import ChineseClipEncoder
from registry import load_registry, relative_path, save_registry, utc_now
from text_builder import build_product_text
from configuration import parse_configured_args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为已审核商品数据建立按类别的中文图文检索索引。")
    parser.add_argument("--input-dir", default="data/processed_data_cleaning", help="审核数据根目录（相对项目根目录）。")
    parser.add_argument("--output-dir", default="data/index_data", help="索引输出目录（相对项目根目录）。")
    parser.add_argument("--categories", default="", help="逗号分隔的类别；留空时自动发现所有包含 products.csv 的目录。")
    parser.add_argument("--model-name", default="ViT-B-16", help="Chinese-CLIP 模型名称。")
    parser.add_argument("--model-download-root", default="models/chinese_clip", help="模型缓存目录（相对项目根目录）。")
    parser.add_argument("--batch-size", type=int, default=16, help="图片和文本编码批大小。")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--use-modelscope", action="store_true", help="通过 ModelScope 下载模型权重。")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖输出目录中同名类别的索引。")
    return parse_configured_args(parser, "build", REPO_ROOT)


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def split_categories(value: str) -> list[str]:
    return [part.strip() for part in value.replace("，", ",").split(",") if part.strip()]


def discover_categories(input_dir: Path, requested: list[str]) -> list[str]:
    if (input_dir / "products.csv").exists():
        discovered = [input_dir.name]
    else:
        discovered = sorted(
            child.name for child in input_dir.iterdir()
            if child.is_dir() and (child / "products.csv").exists()
        )
    if not requested:
        return discovered
    missing = [name for name in requested if name not in discovered]
    if missing:
        raise FileNotFoundError(f"指定类别没有找到 products.csv：{', '.join(missing)}")
    return requested


def _normalise_path(value: str) -> Path:
    return Path(value.replace("\\", "/"))


def find_image(row: dict[str, str], csv_path: Path, input_dir: Path, category_dir: Path) -> Path | None:
    raw = (row.get("local_image_path") or row.get("image_path") or "").strip()
    raw_values = [raw]
    if raw.startswith("[") or raw.startswith("{"):
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, list):
                raw_values = [str(value).strip() for value in decoded if str(value).strip()]
            elif isinstance(decoded, dict):
                raw_values = [str(value).strip() for value in decoded.values() if str(value).strip()]
        except json.JSONDecodeError:
            pass
    candidates: list[Path] = []
    for raw_value in raw_values:
        if not raw_value:
            continue
        raw_path = _normalise_path(raw_value)
        candidates.extend([
            REPO_ROOT / raw_path,
            csv_path.parent / raw_path,
            category_dir / raw_path,
        ])
        if raw_path.name:
            candidates.extend([
                csv_path.parent / "images" / raw_path.name,
                category_dir / "images" / raw_path.name,
            ])
    item_id = (row.get("item_id") or row.get("product_id") or "").strip()
    if item_id:
        image_dir = category_dir / "images"
        candidates.extend(image_dir / f"{item_id}{suffix}" for suffix in (".jpg", ".jpeg", ".png", ".webp"))
        candidates.extend(sorted(image_dir.glob(f"{item_id}__*")))
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate.resolve()
    return None


def read_rows(category_dir: Path, input_dir: Path, category: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    csv_path = category_dir / "products.csv"
    valid: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not ({"item_id", "product_id"} & set(reader.fieldnames)):
            raise ValueError(f"{csv_path} 缺少 item_id 或 product_id 字段。")
        seen: set[str] = set()
        for line_number, raw_row in enumerate(reader, start=2):
            row = {key: (value or "") for key, value in raw_row.items() if key}
            item_id = (row.get("item_id") or row.get("product_id") or "").strip()
            if not item_id:
                errors.append({"line": str(line_number), "item_id": "", "reason": "缺少 item_id"})
                continue
            if item_id in seen:
                errors.append({"line": str(line_number), "item_id": item_id, "reason": "重复 item_id"})
                continue
            seen.add(item_id)
            image_path = find_image(row, csv_path, input_dir, category_dir)
            if image_path is None:
                errors.append({"line": str(line_number), "item_id": item_id, "reason": "找不到商品图片"})
                continue
            try:
                image_path.relative_to(REPO_ROOT)
            except ValueError:
                errors.append({"line": str(line_number), "item_id": item_id, "reason": "图片路径不在项目根目录内，无法保存相对路径"})
                continue
            try:
                from PIL import Image
                with Image.open(image_path) as image:
                    image.verify()
            except Exception as exc:
                errors.append({"line": str(line_number), "item_id": item_id, "reason": f"图片无法读取：{exc}"})
                continue
            row["item_id"] = item_id
            row["_image_path"] = str(image_path)
            row["_source_csv"] = str(csv_path)
            row["text"] = build_product_text(row)
            valid.append(row)
    return valid, errors


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_category(
    category: str,
    input_dir: Path,
    output_dir: Path,
    encoder: ChineseClipEncoder,
    batch_size: int,
    overwrite: bool,
) -> dict[str, Any]:
    category_dir = input_dir / category if not (input_dir / "products.csv").exists() else input_dir
    valid_rows, errors = read_rows(category_dir, input_dir, category)
    if not valid_rows:
        raise RuntimeError(f"类别 {category} 没有可建立索引的有效商品。")

    final_output = output_dir / category
    if final_output.exists():
        if not overwrite:
            raise FileExistsError(f"输出已存在：{final_output}；如需重建请加 --overwrite。")
    category_output = output_dir / f".{category}.tmp"
    if category_output.exists():
        shutil.rmtree(category_output)
    category_output.mkdir(parents=True, exist_ok=True)

    image_paths = [Path(row["_image_path"]) for row in valid_rows]
    texts = [str(row["text"]) for row in valid_rows]
    print(f"[{category}] 编码图片 {len(image_paths)} 条", flush=True)
    image_vectors = encoder.encode_images(image_paths, batch_size=batch_size)
    print(f"[{category}] 编码文本 {len(texts)} 条", flush=True)
    text_vectors = encoder.encode_texts(texts, batch_size=batch_size)

    try:
        import faiss
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("缺少 faiss 或 numpy，请先安装 requirements.txt。") from exc

    image_index = faiss.IndexFlatIP(image_vectors.shape[1])
    image_index.add(np.ascontiguousarray(image_vectors, dtype="float32"))
    text_index = faiss.IndexFlatIP(text_vectors.shape[1])
    text_index.add(np.ascontiguousarray(text_vectors, dtype="float32"))
    # Use Python file handles instead of FAISS' native path API. The latter
    # can fail on Windows when category directories contain Chinese names.
    with (category_output / "image_index.faiss").open("wb") as handle:
        handle.write(faiss.serialize_index(image_index).tobytes())
    with (category_output / "text_index.faiss").open("wb") as handle:
        handle.write(faiss.serialize_index(text_index).tobytes())
    np.save(category_output / "image_embeddings.npy", image_vectors)
    np.save(category_output / "text_embeddings.npy", text_vectors)

    source_fields: list[str] = []
    for source_row in valid_rows:
        for field in source_row:
            if not field.startswith("_") and field != "text" and field not in source_fields:
                source_fields.append(field)
    if "local_image_path" not in source_fields:
        source_fields.append("local_image_path")
    output_fields = ["vector_id"] + source_fields + ["text"]
    output_rows: list[dict[str, Any]] = []
    for vector_id, row in enumerate(valid_rows):
        output_row = {field: row.get(field, "") for field in source_fields}
        output_row["vector_id"] = vector_id
        output_row["local_image_path"] = relative_path(Path(row["_image_path"]), REPO_ROOT)
        output_row["text"] = row.get("text", "")
        output_rows.append(output_row)
    write_csv(category_output / "items.csv", output_rows, output_fields)
    if errors:
        write_csv(category_output / "errors.csv", errors, ["line", "item_id", "reason"])

    report = {
        "category": category,
        "source_csv": relative_path(category_dir / "products.csv", REPO_ROOT),
        "source_dir": relative_path(category_dir, REPO_ROOT),
        "output_dir": relative_path(final_output, REPO_ROOT),
        "model_name": encoder.model_name,
        "device": str(encoder.device),
        "dimension": int(image_vectors.shape[1]),
        "normalized": True,
        "items": len(output_rows),
        "errors": len(errors),
        "generated_at": utc_now(),
    }
    with (category_output / "build_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    if final_output.exists():
        shutil.rmtree(final_output)
    category_output.replace(final_output)
    print(f"[{category}] 完成：有效 {len(output_rows)}，跳过 {len(errors)}", flush=True)
    return report


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size 必须大于 0。")
    input_dir = resolve_path(args.input_dir)
    output_dir = resolve_path(args.output_dir)
    model_root = resolve_path(args.model_download_root)
    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在：{input_dir}")
    requested = split_categories(args.categories)
    categories = discover_categories(input_dir, requested)
    if not categories:
        raise RuntimeError(f"{input_dir} 下没有发现包含 products.csv 的类别目录。")
    print(f"待处理类别：{', '.join(categories)}", flush=True)
    registry_path = output_dir / "index_registry.json"
    registry = load_registry(registry_path)
    existing_model = registry.get("model", {}).get("name")
    if registry.get("categories") and existing_model and existing_model != args.model_name:
        raise RuntimeError(
            f"已有索引使用模型 {existing_model}，不能与 {args.model_name} 混用；"
            "请使用新的 --output-dir，或删除旧索引后重新构建。"
        )
    encoder = ChineseClipEncoder(args.model_name, model_root, args.device, args.use_modelscope)
    registry["updated_at"] = utc_now()
    registry["model"] = {
        "name": args.model_name,
        "download_root": relative_path(model_root, REPO_ROOT),
        "normalized": True,
        "use_modelscope": args.use_modelscope,
    }
    registry["categories"] = registry.get("categories", {})
    for category in categories:
        report = build_category(category, input_dir, output_dir, encoder, args.batch_size, args.overwrite)
        category_output = output_dir / category
        registry["categories"][category] = {
            "items": report["items"],
            "dimension": report["dimension"],
            "items_csv": relative_path(category_output / "items.csv", output_dir),
            "image_index": relative_path(category_output / "image_index.faiss", output_dir),
            "text_index": relative_path(category_output / "text_index.faiss", output_dir),
            "report": relative_path(category_output / "build_report.json", output_dir),
        }
    if not requested and not (input_dir / "products.csv").exists():
        registry["categories"] = {
            category: registry["categories"][category]
            for category in categories
            if category in registry["categories"]
        }
    save_registry(registry_path, registry)
    print(f"索引注册表已写入：{relative_path(registry_path, REPO_ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
