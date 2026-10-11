"""Search reviewed products with fused image/text indexes."""

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
from configuration import parse_configured_args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用中文、商品图片或二者组合查询商品索引。")
    parser.add_argument("query", nargs="?", default="", help="中文搜索词；可与 --image 同时使用。")
    parser.add_argument("--image", default="", help="待查询的商品图片路径。")
    parser.add_argument("--index-dir", default="data/index_data", help="索引目录（相对项目根目录）。")
    parser.add_argument("--category", default="", help="限定类别；留空时搜索注册表中的全部类别。")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=0, help="每个类别先取多少候选，默认 max(20, top-k*5)。")
    parser.add_argument("--image-weight", type=float, default=0.7, help="文本-图片相似度权重，默认 0.7。")
    parser.add_argument("--text-weight", type=float, default=0.3, help="文本-商品描述相似度权重，默认 0.3。")
    parser.add_argument("--image-to-image-weight", type=float, default=0.5, help="图片-图片相似度权重，默认 0.5。")
    parser.add_argument("--text-to-image-weight", type=float, default=0.3, help="文本-图片相似度权重，默认 0.3。")
    parser.add_argument("--text-to-description-weight", type=float, default=0.2, help="文本-商品描述相似度权重，默认 0.2。")
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
    has_text_query = bool(args.query.strip())
    has_image_query = bool(args.image.strip())
    if not has_text_query and not has_image_query:
        raise ValueError("必须提供中文查询词，或使用 --image 提供商品图片。")
    if args.top_k < 1:
        raise ValueError("--top-k 必须大于 0。")
    if args.candidate_k < 0:
        raise ValueError("--candidate-k 不能为负数。")
    if args.image_weight < 0 or args.text_weight < 0:
        raise ValueError("--image-weight 和 --text-weight 不能为负数。")
    weight_total = args.image_weight + args.text_weight
    if weight_total <= 0:
        raise ValueError("--image-weight 和 --text-weight 至少有一个大于 0。")
    image_weight = args.image_weight / weight_total
    text_weight = args.text_weight / weight_total
    multimodal_weights = [
        args.image_to_image_weight,
        args.text_to_image_weight,
        args.text_to_description_weight,
    ]
    if any(weight < 0 for weight in multimodal_weights):
        raise ValueError("多模态查询的三个权重不能为负数。")
    multimodal_total = sum(multimodal_weights)
    if multimodal_total <= 0:
        raise ValueError("多模态查询的三个权重至少有一个大于 0。")
    image_to_image_weight = args.image_to_image_weight / multimodal_total
    text_to_image_weight = args.text_to_image_weight / multimodal_total
    text_to_description_weight = args.text_to_description_weight / multimodal_total
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
    text_query_vector = None
    image_query_vector = None
    if has_text_query:
        text_query_vector = encoder.encode_texts([args.query], batch_size=1)
    if has_image_query:
        image_path = resolve_path(args.image)
        if not image_path.is_file():
            raise FileNotFoundError(f"查询图片不存在：{image_path}")
        image_query_vector = encoder.encode_images([image_path], batch_size=1)
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
        items = load_items(index_dir / entry["items_csv"])
        image_to_image_scores: dict[int, float] = {}
        text_to_image_scores: dict[int, float] = {}
        text_to_description_scores: dict[int, float] = {}
        if image_query_vector is not None:
            image_distances, image_ids = image_index.search(
                image_query_vector, min(candidate_k, image_index.ntotal)
            )
            image_to_image_scores = {
                int(vector_id): float(similarity)
                for similarity, vector_id in zip(image_distances[0], image_ids[0])
                if vector_id >= 0
            }
        if text_query_vector is not None:
            text_image_distances, text_image_ids = image_index.search(
                text_query_vector, min(candidate_k, image_index.ntotal)
            )
            text_to_image_scores = {
                int(vector_id): float(similarity)
                for similarity, vector_id in zip(text_image_distances[0], text_image_ids[0])
                if vector_id >= 0
            }
        text_index_path = index_dir / entry.get("text_index", "")
        if text_query_vector is not None:
            if not text_index_path.exists():
                raise FileNotFoundError(
                    f"类别 {category} 缺少文本索引：{text_index_path}，请重新构建该类别索引。"
                )
            with text_index_path.open("rb") as handle:
                text_index = faiss.deserialize_index(np.frombuffer(handle.read(), dtype="uint8"))
            text_distances, text_ids = text_index.search(
                text_query_vector, min(candidate_k, text_index.ntotal)
            )
            text_to_description_scores = {
                int(vector_id): float(similarity)
                for similarity, vector_id in zip(text_distances[0], text_ids[0])
                if vector_id >= 0
            }
        candidate_ids = (
            set(image_to_image_scores)
            | set(text_to_image_scores)
            | set(text_to_description_scores)
        )
        for vector_id in candidate_ids:
            if vector_id not in items:
                continue
            row = items[vector_id]
            if not matches(row, args):
                continue
            image_to_image_similarity = image_to_image_scores.get(vector_id, 0.0)
            text_to_image_similarity = text_to_image_scores.get(vector_id, 0.0)
            text_to_description_similarity = text_to_description_scores.get(vector_id, 0.0)
            if has_image_query and has_text_query:
                similarity = (
                    image_to_image_weight * image_to_image_similarity
                    + text_to_image_weight * text_to_image_similarity
                    + text_to_description_weight * text_to_description_similarity
                )
            elif has_image_query:
                similarity = image_to_image_similarity
            else:
                similarity = image_weight * text_to_image_similarity + text_weight * text_to_description_similarity
            result = {
                key: value for key, value in row.items()
                if key not in {"vector_id", "text"}
            }
            result["category"] = category
            result["similarity"] = round(float(similarity), 6)
            if has_image_query:
                result["image_to_image_similarity"] = round(image_to_image_similarity, 6)
            if has_text_query:
                result["text_to_image_similarity"] = round(text_to_image_similarity, 6)
                result["text_to_description_similarity"] = round(text_to_description_similarity, 6)
            results.append(result)
    results.sort(key=lambda item: item["similarity"], reverse=True)
    payload = {
        "query": args.query if has_text_query else "",
        "query_image": args.image if has_image_query else "",
        "query_type": "multimodal" if has_text_query and has_image_query else ("text" if has_text_query else "image"),
        "categories": selected,
        "top_k": args.top_k,
        "results": results[: args.top_k],
    }
    if has_text_query and not has_image_query:
        payload["weights"] = {
            "image": round(image_weight, 6),
            "text": round(text_weight, 6),
        }
    if has_image_query and has_text_query:
        payload["multimodal_weights"] = {
            "image_to_image": round(image_to_image_weight, 6),
            "text_to_image": round(text_to_image_weight, 6),
            "text_to_description": round(text_to_description_weight, 6),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
