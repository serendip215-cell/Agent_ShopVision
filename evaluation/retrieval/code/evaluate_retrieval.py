"""Evaluate text, image, and multimodal product retrieval against labeled queries."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
RETRIEVAL_DIR = REPO_ROOT / "scripts" / "retrieval"
EVAL_ROOT = REPO_ROOT / "evaluation" / "retrieval"
RESULTS_ROOT = EVAL_ROOT / "results" / "runs"
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

from encoder import ChineseClipEncoder
from registry import load_registry


@dataclass
class CategoryData:
    name: str
    image_vectors: np.ndarray
    text_vectors: np.ndarray
    items: list[dict[str, str]]
    item_ids: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评测中文、图片和多模态商品检索效果并生成图表。")
    parser.add_argument("--queries", default="evaluation/retrieval/test_data/queries.csv")
    parser.add_argument("--qrels", default="evaluation/retrieval/test_data/qrels.csv")
    parser.add_argument("--index-dir", default="data/index_data")
    parser.add_argument("--config", default="configs/retrieval.json", help="检索配置文件；每次运行会复制到结果目录。")
    parser.add_argument("--run-id", default="", help="本次实验名称；省略时自动使用时间戳。")
    parser.add_argument("--output-dir", default="", help="可选的结果目录；省略时写入 results/runs/<run-id>/。")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidate-k", type=int, default=0, help="每路召回候选数；默认与搜索脚本一致 max(20, top-k*5)。")
    parser.add_argument("--relevance-threshold", type=int, default=2)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--use-modelscope", action="store_true")
    parser.add_argument("--image-weight", type=float, default=None, help="覆盖文字查询的文本-图片权重。")
    parser.add_argument("--text-weight", type=float, default=None, help="覆盖文字查询的文本-商品描述权重。")
    parser.add_argument("--image-to-image-weight", type=float, default=None, help="覆盖图文查询的图片-图片权重。")
    parser.add_argument("--text-to-image-weight", type=float, default=None, help="覆盖图文查询的文本-图片权重。")
    parser.add_argument("--text-to-description-weight", type=float, default=None, help="覆盖图文查询的文本-商品描述权重。")
    parser.add_argument("--overwrite", action="store_true", help="允许重用已有结果目录；仅覆盖本脚本生成的文件。")
    return parser.parse_args()


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return Path(os.path.relpath(path.resolve(), REPO_ROOT.resolve())).as_posix()


def prepare_output_dir(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"结果目录已存在且非空：{output_dir}。请更换 --run-id，或明确传入 --overwrite。"
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def clear_previous_eval_artifacts(output_dir: Path) -> None:
    for name in (
        "ranked_results.csv", "query_metrics.csv", "summary.json", "run_metadata.json",
        "metrics_by_mode.png", "first_relevant_rank.png", "sample_topk_scores.png",
    ):
        artifact = output_dir / name
        if artifact.is_file():
            artifact.unlink()


def snapshot_inputs(output_dir: Path, queries_path: Path, qrels_path: Path, config_path: Path) -> None:
    inputs_dir = output_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    query_snapshot = inputs_dir / "queries.csv"
    config_snapshot = inputs_dir / "retrieval_config.json"
    if queries_path.resolve() != query_snapshot.resolve():
        shutil.copy2(queries_path, query_snapshot)
    if qrels_path.is_file():
        qrels_snapshot = inputs_dir / "qrels.csv"
        if qrels_path.resolve() != qrels_snapshot.resolve():
            shutil.copy2(qrels_path, qrels_snapshot)
    else:
        (inputs_dir / "qrels.csv").unlink(missing_ok=True)
    if config_path.resolve() != config_snapshot.resolve():
        shutil.copy2(config_path, config_snapshot)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_categories(index_dir: Path, registry: dict[str, Any], requested: set[str]) -> dict[str, CategoryData]:
    loaded: dict[str, CategoryData] = {}
    for name, entry in sorted(registry.get("categories", {}).items()):
        if requested and name not in requested:
            continue
        category_dir = index_dir / name
        image_path = category_dir / "image_embeddings.npy"
        text_path = category_dir / "text_embeddings.npy"
        items_path = category_dir / entry.get("items_csv", f"{name}/items.csv").split("/", 1)[-1]
        if not image_path.is_file() or not text_path.is_file():
            raise FileNotFoundError(f"类别 {name} 缺少向量文件，请先构建该类别索引。")
        rows = read_csv(items_path)
        rows.sort(key=lambda row: int(row["vector_id"]))
        image_vectors = np.load(image_path, mmap_mode="r").astype("float32", copy=False)
        text_vectors = np.load(text_path, mmap_mode="r").astype("float32", copy=False)
        if len(rows) != len(image_vectors) or len(rows) != len(text_vectors):
            raise ValueError(f"类别 {name} 的 items.csv 行数与向量数不一致。")
        loaded[name] = CategoryData(
            name=name,
            image_vectors=image_vectors,
            text_vectors=text_vectors,
            items=rows,
            item_ids=[row.get("item_id", row.get("product_id", "")) for row in rows],
        )
    if not loaded:
        raise ValueError("查询集中指定的类别没有对应索引。")
    return loaded


def validate_queries(queries: list[dict[str, str]], categories: dict[str, CategoryData]) -> None:
    if not queries:
        raise ValueError("查询集为空。")
    seen: set[str] = set()
    category_names = set(categories)
    for row in queries:
        qid = row.get("query_id", "").strip()
        mode = row.get("mode", "").strip().lower()
        if not qid or qid in seen:
            raise ValueError(f"query_id 为空或重复：{qid!r}")
        seen.add(qid)
        has_text = bool(row.get("query_text", "").strip())
        has_image = bool(row.get("query_image", "").strip())
        if mode not in {"text", "image", "multimodal"}:
            raise ValueError(f"查询 {qid} 的 mode 必须是 text/image/multimodal。")
        if (mode == "text" and (not has_text or has_image)) or (
            mode == "image" and (has_text or not has_image)
        ) or (mode == "multimodal" and (not has_text or not has_image)):
            raise ValueError(f"查询 {qid} 的 mode 与 query_text/query_image 不匹配。")
        category = row.get("category", "").strip()
        if category and category not in category_names:
            raise ValueError(f"查询 {qid} 指定的类别未加载：{category}")


def encode_queries(
    queries: list[dict[str, str]], encoder: ChineseClipEncoder
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    text_rows = [(row["query_id"], row["query_text"].strip()) for row in queries if row.get("query_text", "").strip()]
    image_rows = [(row["query_id"], resolve_path(row["query_image"].strip())) for row in queries if row.get("query_image", "").strip()]
    text_vectors: dict[str, np.ndarray] = {}
    image_vectors: dict[str, np.ndarray] = {}
    if text_rows:
        vectors = encoder.encode_texts([text for _, text in text_rows], batch_size=32)
        text_vectors = {qid: vectors[i] for i, (qid, _) in enumerate(text_rows)}
    if image_rows:
        missing = [path for _, path in image_rows if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"查询图片不存在：{missing[0]}")
        vectors = encoder.encode_images([path for _, path in image_rows], batch_size=16)
        image_vectors = {qid: vectors[i] for i, (qid, _) in enumerate(image_rows)}
    return text_vectors, image_vectors


def rank_queries(
    queries: list[dict[str, str]],
    categories: dict[str, CategoryData],
    text_vectors: dict[str, np.ndarray],
    image_vectors: dict[str, np.ndarray],
    top_k: int,
    candidate_k: int,
    weights: dict[str, float],
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for query in queries:
        qid = query["query_id"].strip()
        mode = query["mode"].strip().lower()
        requested_category = query.get("category", "").strip()
        selected = [categories[requested_category]] if requested_category else list(categories.values())
        excluded = query.get("exclude_item_id", "").strip()
        candidates: list[dict[str, Any]] = []
        for category in selected:
            image_to_image = (
                category.image_vectors @ image_vectors[qid]
                if qid in image_vectors
                else None
            )
            text_to_image = (
                category.image_vectors @ text_vectors[qid]
                if qid in text_vectors
                else None
            )
            text_to_description = (
                category.text_vectors @ text_vectors[qid]
                if qid in text_vectors
                else None
            )
            candidate_indices: set[int] = set()
            for score_vector in (image_to_image, text_to_image, text_to_description):
                if score_vector is not None:
                    count = min(candidate_k, len(score_vector))
                    candidate_indices.update(np.argsort(score_vector)[-count:].tolist())
            for i in candidate_indices:
                item = category.items[i]
                item_id = category.item_ids[i]
                if not item_id or item_id == excluded:
                    continue
                if mode == "text":
                    score = weights["image"] * float(text_to_image[i]) + weights["text"] * float(text_to_description[i])
                elif mode == "image":
                    score = float(image_to_image[i])
                else:
                    score = (
                        weights["image_to_image"] * float(image_to_image[i])
                        + weights["text_to_image"] * float(text_to_image[i])
                        + weights["text_to_description"] * float(text_to_description[i])
                    )
                candidates.append({
                    "query_id": qid,
                    "mode": mode,
                    "category": category.name,
                    "item_id": item_id,
                    "score": score,
                    "image_to_image_similarity": float(image_to_image[i]) if image_to_image is not None else "",
                    "text_to_image_similarity": float(text_to_image[i]) if text_to_image is not None else "",
                    "text_to_description_similarity": float(text_to_description[i]) if text_to_description is not None else "",
                    "item_name": item.get("item_name", ""),
                    "type": item.get("type", ""),
                    "color": item.get("color", ""),
                    "local_image_path": item.get("local_image_path", ""),
                })
        candidates.sort(key=lambda item: item["score"], reverse=True)
        for rank, candidate in enumerate(candidates[:top_k], start=1):
            candidate["rank"] = rank
            candidate["score"] = round(candidate["score"], 8)
            for key in ("image_to_image_similarity", "text_to_image_similarity", "text_to_description_similarity"):
                if candidate[key] != "":
                    candidate[key] = round(candidate[key], 8)
            ranked.append(candidate)
    return ranked


def dcg(relevances: list[int]) -> float:
    return sum((2**rel - 1) / math.log2(i + 2) for i, rel in enumerate(relevances))


def calculate_metrics(
    queries: list[dict[str, str]],
    rankings: list[dict[str, Any]],
    qrels: list[dict[str, str]],
    threshold: int,
    top_k: int,
) -> list[dict[str, Any]]:
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    judgments: dict[str, dict[str, int]] = defaultdict(dict)
    for result in rankings:
        by_query[result["query_id"]].append(result)
    for judgment in qrels:
        judgments[judgment["query_id"].strip()][judgment["item_id"].strip()] = int(judgment["relevance"])
    metrics: list[dict[str, Any]] = []
    for query in queries:
        qid = query["query_id"].strip()
        result_rows = by_query.get(qid, [])
        rels = judgments.get(qid, {})
        relevant = {item_id for item_id, grade in rels.items() if grade >= threshold}
        retrieved_ids = [row["item_id"] for row in result_rows]
        row: dict[str, Any] = {"query_id": qid, "mode": query["mode"], "category": query.get("category", "")}
        for k in (1, 5, 10):
            hits = set(retrieved_ids[:k]) & relevant
            row[f"recall@{k}"] = len(hits) / len(relevant) if relevant else ""
            row[f"precision@{k}"] = len(hits) / k
        graded = [rels.get(item_id, 0) for item_id in retrieved_ids[:10]]
        ideal = sorted(rels.values(), reverse=True)[:10]
        row["ndcg@10"] = dcg(graded) / dcg(ideal) if ideal and dcg(ideal) else ""
        reciprocal_rank = 0.0
        first_relevant_rank = ""
        for rank, item_id in enumerate(retrieved_ids, start=1):
            if rels.get(item_id, 0) >= threshold:
                reciprocal_rank = 1 / rank
                first_relevant_rank = rank
                break
        row["mrr@10"] = reciprocal_rank
        row["first_relevant_rank"] = first_relevant_rank
        row["top1_item_id"] = retrieved_ids[0] if retrieved_ids else ""
        row["top1_relevance"] = rels.get(retrieved_ids[0], 0) if retrieved_ids else 0
        row["judged_relevant_count"] = len(relevant)
        row["returned_count"] = len(retrieved_ids)
        metrics.append(row)
    return metrics


def save_plots(output_dir: Path, rankings: list[dict[str, Any]], metrics: list[dict[str, Any]], queries: list[dict[str, str]]) -> list[str]:
    from PIL import Image, ImageDraw, ImageFont

    output_dir.mkdir(parents=True, exist_ok=True)
    plots: list[str] = []
    font_candidates: list[Path] = []
    system_root = os.environ.get("WINDIR") or os.environ.get("SYSTEMROOT")
    if system_root:
        font_candidates.extend(
            Path(system_root) / "Fonts" / name
            for name in ("msyh.ttc", "simhei.ttf", "simsun.ttc", "arial.ttf")
        )
    # Pillow can resolve installed font names on some platforms. Avoid relying
    # on one developer's fixed Windows installation path.
    font_candidates.extend(Path(name) for name in (
        "NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf", "Arial.ttf", "DejaVuSans.ttf"
    ))

    def make_font(size: int):
        for font_path in font_candidates:
            try:
                if font_path.is_file():
                    return ImageFont.truetype(str(font_path), size)
                # Let Pillow/platform font lookup resolve a font by installed name.
                if not font_path.is_absolute() and len(font_path.parts) == 1:
                    return ImageFont.truetype(font_path.name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    colors = {"text": "#4C78A8", "image": "#F58518", "multimodal": "#54A24B"}

    if metrics:
        metric_names = ["recall@1", "recall@5", "recall@10", "ndcg@10", "mrr@10"]
        labels = {"recall@1": "Recall@1", "recall@5": "Recall@5", "recall@10": "Recall@10", "ndcg@10": "nDCG@10", "mrr@10": "MRR@10"}
        modes = [mode for mode in ("text", "image", "multimodal") if any(row["mode"] == mode for row in metrics)]
        width, height = 1280, 720
        left, right, top, bottom = 100, 1230, 125, 565
        canvas = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(canvas)
        title_font, label_font, small_font = make_font(30), make_font(20), make_font(17)
        draw.text((left, 35), "不同查询模式的检索指标", fill="#18212B", font=title_font)
        for tick in range(6):
            value = tick / 5
            y = bottom - value * (bottom - top)
            draw.line((left, y, right, y), fill="#DCE2E8", width=1)
            draw.text((45, y - 12), f"{value:.1f}", fill="#4B5563", font=small_font)
        group_width = (right - left) / len(metric_names)
        bar_width = min(42, group_width * 0.72 / max(1, len(modes)))
        for metric_i, metric in enumerate(metric_names):
            mode_rows_x = left + metric_i * group_width + group_width / 2
            for mode_i, mode in enumerate(modes):
                mode_rows = [row for row in metrics if row["mode"] == mode and row[metric] != ""]
                value = float(np.mean([float(row[metric]) for row in mode_rows])) if mode_rows else 0.0
                x0 = mode_rows_x + (mode_i - (len(modes) - 1) / 2) * bar_width - bar_width / 2
                y0 = bottom - value * (bottom - top)
                draw.rectangle((x0, y0, x0 + bar_width - 2, bottom), fill=colors.get(mode, "#777777"))
            draw.text((mode_rows_x - 48, bottom + 18), labels[metric], fill="#263238", font=small_font)
        legend_x = left
        for mode in modes:
            draw.rectangle((legend_x, 620, legend_x + 22, 640), fill=colors.get(mode, "#777777"))
            draw.text((legend_x + 30, 618), mode, fill="#263238", font=small_font)
            legend_x += 190
        path = output_dir / "metrics_by_mode.png"
        canvas.save(path)
        plots.append(path.name)

    selected_queries: list[dict[str, str]] = []
    for mode in ("text", "image", "multimodal"):
        match = next((query for query in queries if query["mode"] == mode), None)
        if match:
            selected_queries.append(match)
    if selected_queries:
        rank_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rankings:
            rank_map[row["query_id"]].append(row)
        width, height = 1280, 720
        left, right, top, bottom = 100, 1230, 125, 565
        canvas = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(canvas)
        title_font, label_font, small_font = make_font(28), make_font(19), make_font(17)
        draw.text((left, 35), "样例查询 Top-K 分数", fill="#18212B", font=title_font)
        draw.text((left, 78), "不同查询模式的绝对分数不可直接比较", fill="#5B6573", font=small_font)
        all_scores = [float(row["score"]) for row in rankings]
        y_min = min(0.0, min(all_scores, default=0.0))
        y_max = max(0.1, max(all_scores, default=1.0))
        if y_max <= y_min:
            y_max = y_min + 1.0
        for tick in range(6):
            value = y_min + (y_max - y_min) * tick / 5
            y = bottom - tick * (bottom - top) / 5
            draw.line((left, y, right, y), fill="#DCE2E8", width=1)
            draw.text((35, y - 10), f"{value:.2f}", fill="#4B5563", font=small_font)
        x_max = max(1, max((len(rank_map[q["query_id"]]) for q in selected_queries), default=1))
        mode_legend_x = left
        for query in selected_queries:
            rows = sorted(rank_map[query["query_id"]], key=lambda row: row["rank"])
            if rows:
                color = colors.get(query["mode"], "#777777")
                points = []
                for row in rows:
                    x = left + (int(row["rank"]) - 1) * (right - left) / max(1, x_max - 1)
                    y = bottom - (float(row["score"]) - y_min) * (bottom - top) / (y_max - y_min)
                    points.append((int(x), int(y)))
                if len(points) > 1:
                    draw.line(points, fill=color, width=4)
                for point in points:
                    draw.ellipse((point[0] - 6, point[1] - 6, point[0] + 6, point[1] + 6), fill=color)
                draw.rectangle((mode_legend_x, 620, mode_legend_x + 22, 640), fill=color)
                draw.text((mode_legend_x + 30, 618), f"{query['query_id']} ({query['mode']})", fill="#263238", font=small_font)
                mode_legend_x += 340
        draw.text((left, 580), "排名（Top-K）", fill="#263238", font=small_font)
        path = output_dir / "sample_topk_scores.png"
        canvas.save(path)
        plots.append(path.name)

    if metrics:
        eligible = [row for row in metrics if row["first_relevant_rank"] != ""]
        if eligible:
            width, row_height = 1280, 45
            height = max(260, 145 + row_height * len(eligible))
            canvas = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(canvas)
            title_font, label_font = make_font(28), make_font(18)
            draw.text((55, 30), "每条查询的首个相关结果排名", fill="#18212B", font=title_font)
            max_rank = max(10, max(int(row["first_relevant_rank"]) for row in eligible))
            for i, row in enumerate(eligible):
                y = 100 + i * row_height
                label = f"{row['query_id']} ({row['mode']})"
                draw.text((55, y), label, fill="#263238", font=label_font)
                bar_left, bar_right = 400, 1150
                value = int(row["first_relevant_rank"])
                end = bar_left + (bar_right - bar_left) * value / max_rank
                draw.rectangle((bar_left, y + 2, end, y + 27), fill=colors.get(row["mode"], "#777777"))
                draw.text((end + 8, y), str(value), fill="#263238", font=label_font)
            path = output_dir / "first_relevant_rank.png"
            canvas.save(path)
            plots.append(path.name)
    return plots


def main() -> int:
    args = parse_args()
    if args.top_k < 1:
        raise ValueError("--top-k 必须大于 0。")
    if args.candidate_k < 0:
        raise ValueError("--candidate-k 不能为负数。")
    candidate_k = args.candidate_k if args.candidate_k > 0 else max(20, args.top_k * 5)
    queries_path = resolve_path(args.queries)
    qrels_path = resolve_path(args.qrels)
    index_dir = resolve_path(args.index_dir)
    config_path = resolve_path(args.config)
    run_id = args.run_id.strip() or datetime.now().astimezone().strftime("eval_%Y%m%d_%H%M%S_%f")
    if Path(run_id).name != run_id or run_id in {".", ".."}:
        raise ValueError("--run-id 只能是单层目录名，不能包含路径。")
    output_dir = resolve_path(args.output_dir) if args.output_dir else RESULTS_ROOT / run_id
    if not queries_path.is_file():
        raise FileNotFoundError(f"查询文件不存在：{queries_path}")
    if not config_path.is_file():
        raise FileNotFoundError(f"检索配置不存在：{config_path}")
    prepare_output_dir(output_dir, args.overwrite)
    snapshot_inputs(output_dir, queries_path, qrels_path, config_path)
    queries = read_csv(queries_path)
    scoped_categories = {row.get("category", "").strip() for row in queries if row.get("category", "").strip()}
    has_unscoped_queries = any(not row.get("category", "").strip() for row in queries)
    requested_categories = set() if has_unscoped_queries else scoped_categories
    registry = load_registry(index_dir / "index_registry.json")
    categories = load_categories(index_dir, registry, requested_categories)
    validate_queries(queries, categories)
    qrels = read_csv(qrels_path) if qrels_path.is_file() else []
    qids = {row["query_id"].strip() for row in queries}
    for row in qrels:
        if row.get("query_id", "").strip() not in qids:
            raise ValueError(f"qrels 中存在未知 query_id：{row.get('query_id')}")
        relevance = int(row.get("relevance", ""))
        if relevance < 0 or relevance > 3:
            raise ValueError("qrels.relevance 必须为 0、1、2 或 3。")

    with config_path.open("r", encoding="utf-8-sig") as handle:
        search_config = json.load(handle).get("search", {})
    weights = {
        "image": float(args.image_weight if args.image_weight is not None else search_config.get("image_weight", 0.7)),
        "text": float(args.text_weight if args.text_weight is not None else search_config.get("text_weight", 0.3)),
        "image_to_image": float(args.image_to_image_weight if args.image_to_image_weight is not None else search_config.get("image_to_image_weight", 0.5)),
        "text_to_image": float(args.text_to_image_weight if args.text_to_image_weight is not None else search_config.get("text_to_image_weight", 0.3)),
        "text_to_description": float(args.text_to_description_weight if args.text_to_description_weight is not None else search_config.get("text_to_description_weight", 0.2)),
    }
    text_total = weights["image"] + weights["text"]
    multi_total = weights["image_to_image"] + weights["text_to_image"] + weights["text_to_description"]
    if text_total <= 0 or multi_total <= 0 or min(weights.values()) < 0:
        raise ValueError("检索权重必须非负，且各模式的权重和必须大于 0。")
    weights["image"] /= text_total
    weights["text"] /= text_total
    for key in ("image_to_image", "text_to_image", "text_to_description"):
        weights[key] /= multi_total

    model_config = registry.get("model", {})
    checkpoint_value = model_config.get("checkpoint", "")
    checkpoint = resolve_path(checkpoint_value) if checkpoint_value.strip() else None
    quant = (model_config.get("quant", "none") or "none").strip().lower()
    encoder = ChineseClipEncoder(
        model_config.get("name", "ViT-B-16"),
        resolve_path(model_config.get("download_root", "models/chinese_clip")),
        args.device,
        args.use_modelscope or bool(model_config.get("use_modelscope", False)),
        checkpoint=checkpoint,
        quant=quant,
    )
    text_vectors, image_vectors = encode_queries(queries, encoder)
    rankings = rank_queries(queries, categories, text_vectors, image_vectors, args.top_k, candidate_k, weights)
    metrics = calculate_metrics(queries, rankings, qrels, args.relevance_threshold, args.top_k) if qrels else []
    if args.overwrite:
        clear_previous_eval_artifacts(output_dir)
    write_csv(output_dir / "ranked_results.csv", rankings)
    if metrics:
        write_csv(output_dir / "query_metrics.csv", metrics)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "query_count": len(queries),
        "qrels_count": len(qrels),
        "index_categories": list(categories),
        "top_k": args.top_k,
        "candidate_k_per_channel": candidate_k,
        "relevance_threshold": args.relevance_threshold,
        "weights": weights,
        "metrics_by_mode": {},
        "interpretation": "无人工 qrels 时仅为排序流程冒烟检查；使用演示标注时指标只反映样例构造，不代表泛化效果。",
    }
    if metrics:
        for mode in ("text", "image", "multimodal"):
            mode_rows = [row for row in metrics if row["mode"] == mode]
            if not mode_rows:
                continue
            mode_summary: dict[str, Any] = {"query_count": len(mode_rows)}
            for key in ("recall@1", "recall@5", "recall@10", "precision@10", "ndcg@10", "mrr@10"):
                valid = [float(row[key]) for row in mode_rows if row[key] != ""]
                if valid:
                    mode_summary[key] = round(float(np.mean(valid)), 6)
            summary["metrics_by_mode"][mode] = mode_summary
    metadata = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "queries": display_path(queries_path),
        "qrels": display_path(qrels_path) if qrels_path.is_file() else None,
        "index_dir": display_path(index_dir),
        "config": display_path(config_path),
        "model_name": model_config.get("name", "ViT-B-16"),
        "checkpoint": model_config.get("checkpoint", ""),
        "device": args.device,
        "use_modelscope": args.use_modelscope or bool(model_config.get("use_modelscope", False)),
        "top_k": args.top_k,
        "candidate_k_per_channel": candidate_k,
        "relevance_threshold": args.relevance_threshold,
        "weights": weights,
        "query_count": len(queries),
        "qrels_count": len(qrels),
        "index_categories": list(categories),
    }
    (output_dir / "run_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plots = save_plots(output_dir, rankings, metrics, queries)
    print(json.dumps({"run_id": run_id, "output_dir": display_path(output_dir), "summary": summary, "outputs": ["ranked_results.csv", "query_metrics.csv" if metrics else None, "summary.json", "run_metadata.json", *plots]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"评测失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
