"""Search reviewed products with a category image index."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from encoder import ChineseClipEncoder
from registry import load_registry
from text_builder import build_product_text
from configuration import parse_configured_args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用中文文本查询商品图片索引。")
    parser.add_argument("query", help="中文搜索词。")
    parser.add_argument("--index-dir", default="data/index_data", help="索引目录（相对项目根目录）。")
    parser.add_argument("--category", default="", help="限定类别；留空时搜索注册表中的全部类别。")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=0, help="每个类别先取多少候选，默认 max(20, top-k*5)。")
    parser.add_argument("--product-type", default="")
    parser.add_argument("--type", dest="sub_type", default="")
    parser.add_argument("--color", default="")
    parser.add_argument("--material", default="")
    parser.add_argument("--model-name", default="", help="默认读取索引注册表中的模型名称。")
    parser.add_argument("--model-download-root", default="", help="模型缓存目录；留空时读取索引注册表。")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--use-modelscope", action="store_true", help="通过 ModelScope 下载模型权重。")
    return parse_configured_args(parser, "search", REPO_ROOT)


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def load_items(path: Path) -> dict[int, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {int(row["vector_id"]): row for row in csv.DictReader(handle)}


def matches(row: dict[str, str], args: argparse.Namespace) -> bool:
    filters = {
        "product_type": args.product_type,
        "type": args.sub_type,
        "color": args.color,
        "material": args.material,
    }
    return all(not value or value.casefold() in (row.get(field, "") or "").casefold() for field, value in filters.items())


def main() -> int:
    args = parse_args()
    if args.top_k < 1:
        raise ValueError("--top-k 必须大于 0。")
    index_dir = resolve_path(args.index_dir)
    registry = load_registry(index_dir / "index_registry.json")
    categories = registry.get("categories", {})
    if args.category:
        if args.category not in categories:
            raise KeyError(f"索引注册表中没有类别：{args.category}")
        selected = [args.category]
    else:
        selected = sorted(categories)
    if not selected:
        raise RuntimeError("索引注册表中没有可用类别，请先运行 build_category_index.py。")
    model_name = args.model_name or registry.get("model", {}).get("name", "ViT-B-16")
    model_root_value = args.model_download_root or registry.get("model", {}).get("download_root", "models/chinese_clip")
    use_modelscope = args.use_modelscope or bool(registry.get("model", {}).get("use_modelscope", False))
    encoder = ChineseClipEncoder(model_name, resolve_path(model_root_value), args.device, use_modelscope)
    query_vector = encoder.encode_texts([args.query], batch_size=1)
    candidate_k = args.candidate_k if args.candidate_k > 0 else max(20, args.top_k * 5)

    try:
        import faiss
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("缺少 faiss，请先安装 requirements.txt。") from exc

    results: list[dict[str, Any]] = []
    for category in selected:
        entry = categories[category]
        with (index_dir / entry["image_index"]).open("rb") as handle:
            image_index = faiss.deserialize_index(np.frombuffer(handle.read(), dtype="uint8"))
        distances, ids = image_index.search(query_vector, min(candidate_k, image_index.ntotal))
        items = load_items(index_dir / entry["items_csv"])
        for similarity, vector_id in zip(distances[0], ids[0]):
            if vector_id < 0 or vector_id not in items:
                continue
            row = items[vector_id]
            if not matches(row, args):
                continue
            result = {
                key: value for key, value in row.items()
                if key not in {"vector_id", "text"}
            }
            result["category"] = category
            result["similarity"] = round(float(similarity), 6)
            results.append(result)
    results.sort(key=lambda item: item["similarity"], reverse=True)
    payload = {
        "query": args.query,
        "categories": selected,
        "top_k": args.top_k,
        "results": results[: args.top_k],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
