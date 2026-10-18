"""Generate a small retrieval benchmark and use a configured chat model as its judge.

The model validates generated queries and grades retrieved products. Its reviewed
queries, judgments, metrics, and plots are stored together in one result run.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
EVAL_ROOT = REPO_ROOT / "evaluation" / "retrieval"


def read_env_file() -> dict[str, str]:
    env_path = REPO_ROOT / ".env"
    values: dict[str, str] = {}
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            values[name.strip()] = value.strip().strip("\"'")
    return values


ENV_FILE = read_env_file()
MODEL = os.environ.get("PIXEL_API_MODEL", ENV_FILE.get("PIXEL_API_MODEL", "gpt-6.1-sol")).strip()
BASE_URL = os.environ.get(
    "PIXEL_API_BASE_URL", ENV_FILE.get("PIXEL_API_BASE_URL", "https://api.ai-pixel.online/v1")
).strip().rstrip("/")
API_KEY = os.environ.get("PIXEL_API_KEY", ENV_FILE.get("PIXEL_API_KEY", "")).strip()
if not API_KEY:
    raise RuntimeError("请设置 PIXEL_API_KEY，或在仓库根目录 .env 中配置 PIXEL_API_KEY。")

API_USAGE: dict[str, int] = defaultdict(int)
API_CALL_COUNT = 0


def call_model(messages: list[dict[str, Any]], max_tokens: int = 1800) -> str:
    global API_CALL_COUNT
    request_body = json.dumps(
        {"model": MODEL, "messages": messages, "temperature": 0, "max_tokens": max_tokens},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=request_body,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
            choice = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            API_USAGE["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
            API_USAGE["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
            API_CALL_COUNT += 1
            if isinstance(choice, list):
                return "\n".join(str(part.get("text", "")) for part in choice)
            return str(choice)
        except urllib.error.HTTPError as exc:
            last_error = exc
            try:
                detail = exc.read().decode("utf-8", errors="replace")
                detail = detail.replace(API_KEY, "[REDACTED]")
                detail = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[REDACTED]", detail)[:240]
            except Exception:
                detail = ""
            no_route = "No eligible group" in detail
            if exc.code not in (429, 500, 502, 503, 504) or no_route or attempt == 4:
                # Deliberately omit response headers/body; they may contain provider details.
                raise RuntimeError(f"Pixel API 请求失败，HTTP {exc.code}。{detail}") from None
            delay = (3, 7, 15, 30)[attempt]
            print(f"[API 暂时不可用 HTTP {exc.code}] {delay} 秒后重试。", flush=True)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            last_error = exc
            if attempt == 4:
                raise RuntimeError(f"Pixel API 响应异常：{type(exc).__name__}。") from None
            delay = (3, 7, 15, 30)[attempt]
            print(f"[API 连接暂时异常] {delay} 秒后重试。", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"Pixel API 请求失败：{type(last_error).__name__ if last_error else 'unknown'}")


def parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型输出中没有 JSON 对象。")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型输出 JSON 顶层必须是对象。")
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_contact_sheet_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Find an installed font without assuming a particular Windows drive."""
    candidates: list[Path] = []
    system_root = os.environ.get("WINDIR") or os.environ.get("SYSTEMROOT")
    if system_root:
        candidates.extend(
            Path(system_root) / "Fonts" / name
            for name in ("msyh.ttc", "simhei.ttf", "simsun.ttc", "arial.ttf")
        )
    candidates.extend(Path(name) for name in (
        "NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf", "Arial.ttf", "DejaVuSans.ttf"
    ))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return ImageFont.truetype(str(candidate), size)
            if not candidate.is_absolute() and len(candidate.parts) == 1:
                return ImageFont.truetype(candidate.name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def root_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def select_diverse_items(category: str, rows: list[dict[str, str]], count: int, seed: int) -> list[dict[str, str]]:
    valid: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        item_id = (row.get("item_id") or row.get("product_id") or "").strip()
        image = (row.get("local_image_path") or "").strip()
        if not item_id or item_id in seen or not image or not root_path(image).is_file():
            continue
        seen.add(item_id)
        valid.append(row)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in valid:
        subtype = (row.get("type") or row.get("item_type") or "").strip()
        groups[subtype or (row.get("item_name") or "未分类")[:8]].append(row)
    rng = random.Random(seed)
    for values in groups.values():
        values.sort(key=lambda row: row.get("item_id", ""))
        rng.shuffle(values)
    selected: list[dict[str, str]] = []
    group_names = sorted(groups)
    while len(selected) < count and group_names:
        remaining: list[str] = []
        for group in group_names:
            if groups[group] and len(selected) < count:
                selected.append(groups[group].pop())
            if groups[group]:
                remaining.append(group)
        group_names = remaining
    if len(selected) < count:
        raise ValueError(f"类别 {category} 有图片的可用商品不足 {count} 条。")
    return selected


def item_prompt_record(index: int, row: dict[str, str]) -> dict[str, str | int]:
    return {
        "index": index,
        "product_type": row.get("product_type", ""),
        "subtype": row.get("type", ""),
        "title": row.get("item_name", ""),
        "brand": row.get("brand", ""),
        "color": row.get("color", ""),
        "material": row.get("material", ""),
        "description": (row.get("description", "") or "")[:180],
    }


def generate_queries_for_category(category: str, rows: list[dict[str, str]], category_number: int) -> list[dict[str, str]]:
    records = [item_prompt_record(i, row) for i, row in enumerate(rows, start=1)]
    prompt = (
        "你在为中文商品检索系统构造离线评测查询。根据每条商品的已知字段，为它生成一条自然、简洁、像真实买家输入的中文搜索词。"
        "不要照抄标题，不要编造未提供的价格、品牌、材质或功能；材料/颜色为空或未知时不要补造。"
        "查询应表达能从字段支持的商品类别、细分类或属性，长度约 8 至 28 个汉字。"
        "逐条保留 index，返回严格 JSON：{\"queries\":[{\"index\":1,\"query_text\":\"...\"}]}。\n商品记录：\n"
        + json.dumps(records, ensure_ascii=False)
    )
    response = call_model([{"role": "user", "content": prompt}], max_tokens=300)
    parsed = parse_json(response)
    results = parsed.get("queries", [])
    by_index = {int(row["index"]): str(row["query_text"]).strip() for row in results if "index" in row and row.get("query_text")}
    if set(by_index) != set(range(1, len(rows) + 1)):
        raise ValueError(f"类别 {category} 的查询生成条数不完整：收到 {len(by_index)}/{len(rows)}。")
    return [{"query_text": by_index[i]} for i in range(1, len(rows) + 1)]


def save_queries_and_manifest(
    categories: list[str], sample_count: int, work_dir: Path
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]], dict[tuple[str, str], dict[str, str]]]:
    queries: list[dict[str, str]] = []
    manifest: dict[str, dict[str, str]] = {}
    item_lookup: dict[tuple[str, str], dict[str, str]] = {}
    query_order = ["text", "image", "multimodal"]
    for category_index, category in enumerate(categories, start=1):
        category_csv = REPO_ROOT / "data" / "index_data" / category / "items.csv"
        rows = read_csv(category_csv)
        selected = select_diverse_items(category, rows, sample_count, 401 + category_index)
        for row in rows:
            item_id = (row.get("item_id") or row.get("product_id") or "").strip()
            if item_id:
                item_lookup[(category, item_id)] = row
        print(f"[生成查询] {category}: 选择 {sample_count} 个不同细分类商品", flush=True)
        generated = generate_queries_for_category(category, selected, category_index)
        for i, (item, generated_row) in enumerate(zip(selected, generated), start=1):
            item_id = (item.get("item_id") or item.get("product_id") or "").strip()
            image_path = item["local_image_path"].strip().replace("\\", "/")
            text = generated_row["query_text"]
            base_id = f"c{category_index:02d}_i{i:02d}"
            for mode in query_order:
                qid = f"pilot_{mode}_{base_id}"
                query = {
                    "query_id": qid,
                    "mode": mode,
                    "query_text": text if mode in ("text", "multimodal") else "",
                    "query_image": image_path if mode in ("image", "multimodal") else "",
                    "category": category,
                    "exclude_item_id": item_id if mode in ("image", "multimodal") else "",
                }
                queries.append(query)
                manifest[qid] = {
                    "query_id": qid,
                    "mode": mode,
                    "category": category,
                    "source_item_id": item_id,
                    "query_text": query["query_text"],
                    "query_image": query["query_image"],
                    "generation_source": f"{MODEL} based on indexed product fields",
                }
    write_csv(work_dir / "queries_generated.csv", queries, ["query_id", "mode", "query_text", "query_image", "category", "exclude_item_id"])
    write_csv(work_dir / "query_manifest.csv", list(manifest.values()), ["query_id", "mode", "category", "source_item_id", "query_text", "query_image", "generation_source"])
    return queries, manifest, item_lookup


def run_retrieval(queries_path: Path, qrels_path: Path, output_dir: Path, top_k: int, candidate_k: int, device: str) -> None:
    evaluator = EVAL_ROOT / "code" / "evaluate_retrieval.py"
    command = [
        sys.executable, str(evaluator),
        "--queries", queries_path.relative_to(REPO_ROOT).as_posix(),
        "--qrels", qrels_path.relative_to(REPO_ROOT).as_posix(),
        "--output-dir", output_dir.relative_to(REPO_ROOT).as_posix(),
        "--run-id", output_dir.name,
        "--top-k", str(top_k), "--candidate-k", str(candidate_k), "--device", device,
        "--overwrite",
    ]
    print("[检索] 开始编码查询并生成 Top-K 候选", flush=True)
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def candidate_records(qid: str, results: list[dict[str, str]], item_lookup: dict[tuple[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for result in results:
        item_id = result["item_id"]
        item = item_lookup.get((result["category"], item_id), {})
        values.append({
            "rank": int(result["rank"]),
            "item_id": item_id,
            "item_name": item.get("item_name", result.get("item_name", "")),
            "product_type": item.get("product_type", result["category"]),
            "subtype": item.get("type", result.get("type", "")),
            "brand": item.get("brand", ""),
            "color": item.get("color", result.get("color", "")),
            "material": item.get("material", ""),
            "description": (item.get("description", "") or "")[:450],
            "local_image_path": result.get("local_image_path", ""),
        })
    return values


def normalize_grade(value: Any) -> int:
    grade = int(value)
    if grade < 0 or grade > 3:
        raise ValueError(f"模型相关度超出 0..3：{grade}")
    return grade


def label_text_queries(
    queries: list[dict[str, str]], rankings: dict[str, list[dict[str, str]]],
    manifest: dict[str, dict[str, str]], item_lookup: dict[tuple[str, str], dict[str, str]],
    progress_path: Path | None = None,
) -> list[dict[str, Any]]:
    text_queries = [query for query in queries if query["mode"] == "text"]
    labels = read_jsonl(progress_path) if progress_path else []
    completed = {
        qid for qid in {row["query_id"] for row in labels}
        if any(row.get("query_id") == qid and isinstance(row.get("query_valid"), bool) for row in labels)
    }
    for start in range(0, len(text_queries), 3):
        batch = text_queries[start : start + 3]
        if all(query["query_id"] in completed for query in batch):
            continue
        cases = []
        for query in batch:
            source_id = manifest[query["query_id"]]["source_item_id"]
            source_item = item_lookup.get((query["category"], source_id), {})
            cases.append({
                "query_id": query["query_id"],
                "query_text": query["query_text"],
                "category": query["category"],
                "source_product": item_prompt_record(0, source_item),
                "candidates": candidate_records(query["query_id"], rankings.get(query["query_id"], []), item_lookup),
            })
        prompt = (
            "你是商品检索评测的 AI 评审员。先核验 query_text 是否自然、是否能由 source_product 的已知信息支持；明显错字、无依据属性或与源商品意图不符时 query_valid=false。"
            "再按唯一评价口径给每个候选商品评 0-3：0 不相关，1 弱相关，2 相关替代，3 高度符合。类别固定；优先检查细分类及查询明确提出的颜色、材质、型号等约束。"
            "只在查询明确提出时才把型号兼容性当作约束。商品字段缺失表示未知，不要因此扣分；不要虚构属性。"
            "每条查询必须返回 query_valid (JSON 布尔值)、query_review_reason 和全部候选判断；item_id 必须原样返回。只输出严格 JSON："
            "{\"queries\":[{\"query_id\":\"...\",\"query_valid\":true,\"query_review_reason\":\"简短中文依据\",\"items\":[{\"item_id\":\"...\",\"relevance\":0,\"confidence\":\"high|medium|low\",\"reason\":\"简短中文依据\"}]}]}\n"
            + json.dumps(cases, ensure_ascii=False)
        )
        print(f"[{MODEL} AI 复核-文字] {min(start + len(batch), len(text_queries))}/{len(text_queries)} 条查询", flush=True)
        parsed = parse_json(call_model([{"role": "user", "content": prompt}], max_tokens=2600))
        batch_labels = parse_label_response(parsed, batch, cases)
        labels.extend(batch_labels)
        completed.update(query["query_id"] for query in batch)
        if progress_path:
            append_jsonl(progress_path, batch_labels)
    return labels


def make_contact_sheet(query: dict[str, str], ranked: list[dict[str, str]], sheet_dir: Path) -> Path:
    width, tile, label_height, columns, rows = 756, 240, 30, 3, 4
    canvas = Image.new("RGB", (width, rows * (tile + label_height)), "white")
    draw = ImageDraw.Draw(canvas)
    try:
        font = load_contact_sheet_font(16)
    except OSError:
        font = ImageFont.load_default()
    tiles: list[tuple[str, str]] = [("QUERY IMAGE", query["query_image"])]
    tiles.extend((f"RANK {row['rank']}", row.get("local_image_path", "")) for row in ranked[:10])
    for index, (label, path) in enumerate(tiles):
        x, y = (index % columns) * (tile + 12), (index // columns) * (tile + label_height)
        draw.text((x + 6, y + 5), label, fill="#17202A", font=font)
        image_path = root_path(path) if path else None
        if image_path and image_path.is_file():
            try:
                with Image.open(image_path) as source:
                    thumb = ImageOps.fit(source.convert("RGB"), (tile, tile))
                canvas.paste(thumb, (x, y + label_height))
            except OSError:
                draw.rectangle((x, y + label_height, x + tile, y + label_height + tile), outline="#C62828", width=3)
                draw.text((x + 8, y + label_height + 8), "IMAGE ERROR", fill="#C62828", font=font)
        else:
            draw.rectangle((x, y + label_height, x + tile, y + label_height + tile), outline="#999999", width=2)
            draw.text((x + 8, y + label_height + 8), "NO IMAGE", fill="#777777", font=font)
    sheet_dir.mkdir(parents=True, exist_ok=True)
    output = sheet_dir / f"{query['query_id']}.jpg"
    canvas.save(output, format="JPEG", quality=82, optimize=True)
    return output


def image_data_url(path: Path) -> str:
    raw = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{raw}"


def parse_label_response(parsed: dict[str, Any], batch: list[dict[str, str]], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_map = {query["query_id"]: query for query in batch}
    case_map = {case["query_id"]: case for case in cases}
    output: list[dict[str, Any]] = []
    returned: set[tuple[str, str]] = set()
    reviewed_queries: dict[str, tuple[bool, str]] = {}
    for query_result in parsed.get("queries", []):
        qid = str(query_result.get("query_id", ""))
        if qid not in query_map:
            continue
        query_valid = query_result.get("query_valid")
        if isinstance(query_valid, str) and query_valid.casefold() in {"true", "false"}:
            query_valid = query_valid.casefold() == "true"
        query_review_reason = str(query_result.get("query_review_reason", "")).strip()
        if not isinstance(query_valid, bool) or not query_review_reason:
            raise ValueError(f"AI 未完整复核查询有效性：{qid}")
        reviewed_queries[qid] = (query_valid, query_review_reason[:300])
        known = {str(candidate["item_id"]) for candidate in case_map[qid]["candidates"]}
        for item in query_result.get("items", []):
            item_id = str(item.get("item_id", ""))
            if item_id not in known:
                continue
            returned.add((qid, item_id))
            output.append({
                "query_id": qid,
                "item_id": item_id,
                "relevance": normalize_grade(item.get("relevance", item.get("grade", 0))),
                "confidence": str(item.get("confidence", "low")),
                "reason": str(item.get("reason", ""))[:300],
                "query_valid": query_valid,
                "query_review_reason": query_review_reason[:300],
                "judgment_source": "AI 复核",
            })
    expected = {(qid, str(candidate["item_id"])) for qid, case in case_map.items() for candidate in case["candidates"]}
    missing = expected - returned
    if missing:
        raise ValueError(f"{MODEL} AI 复核有 {len(missing)} 个候选未返回；停止生成，以免未判候选被误当作不相关。")
    missing_queries = set(query_map) - reviewed_queries.keys()
    if missing_queries:
        raise ValueError(f"{MODEL} AI 复核缺少 {len(missing_queries)} 条查询的有效性判断。")
    return output


def label_visual_queries(
    queries: list[dict[str, str]], rankings: dict[str, list[dict[str, str]]],
    manifest: dict[str, dict[str, str]], item_lookup: dict[tuple[str, str], dict[str, str]],
    sheet_dir: Path,
    progress_path: Path | None = None,
) -> list[dict[str, Any]]:
    visual_queries = [query for query in queries if query["mode"] in ("image", "multimodal")]
    prepared: list[tuple[dict[str, str], dict[str, Any], Path]] = []
    for query in visual_queries:
        candidates = candidate_records(query["query_id"], rankings.get(query["query_id"], []), item_lookup)
        sheet = make_contact_sheet(query, rankings.get(query["query_id"], []), sheet_dir)
        source_id = manifest[query["query_id"]]["source_item_id"]
        source_item = item_lookup.get((query["category"], source_id), {})
        candidate_summary = [
            {key: item[key] for key in ("rank", "item_id", "item_name", "subtype", "color", "material", "description")}
            for item in candidates
        ]
        prepared.append((query, {
            "query_id": query["query_id"],
            "query_text": query["query_text"],
            "category": query["category"],
            "source_product": item_prompt_record(0, source_item),
            "candidates": candidate_summary,
        }, sheet))
    labels = read_jsonl(progress_path) if progress_path else []
    labeled_pairs = {(row["query_id"], str(row["item_id"])) for row in labels}
    for index, (query, case, sheet) in enumerate(prepared, start=1):
        expected = {(query["query_id"], str(item["item_id"])) for item in case["candidates"]}
        query_reviewed = any(
            row.get("query_id") == query["query_id"] and isinstance(row.get("query_valid"), bool)
            for row in labels
        )
        if expected and expected.issubset(labeled_pairs) and query_reviewed:
            continue
        content: list[dict[str, Any]] = [{
            "type": "text",
            "text": (
                "你是商品检索评测的 AI 评审员。联系表第一格是 QUERY IMAGE，之后按 RANK 1 到 RANK 10 排列候选图；JSON 提供查询类别、文字条件、源商品和候选属性。"
                "先核验查询是否可用于评测：图片清楚且类别合适，文字自然并有商品字段依据；图文模式的图片与文字不能明显冲突。若有明显错字、信息冲突或查询无法判断，query_valid=false 并说明原因。"
                "再按统一的视觉商品检索口径判 0-3：0 不相关，1 弱相关，2 相关替代，3 高度符合。须满足查询明确提出的约束；只有查询明确要求时才检查型号兼容。"
                "图片看不清时降低 confidence，不要猜颜色/材质；候选字段缺失表示未知，不等于不匹配。每个候选都要判分并原样返回 item_id。"
                "只输出严格 JSON：{\"queries\":[{\"query_id\":\"...\",\"query_valid\":true,\"query_review_reason\":\"简短中文依据\",\"items\":[{\"item_id\":\"...\",\"relevance\":0,\"confidence\":\"high|medium|low\",\"reason\":\"简短中文依据\"}]}]}"
            ),
        }]
        content.append({"type": "text", "text": json.dumps(case, ensure_ascii=False)})
        content.append({"type": "image_url", "image_url": {"url": image_data_url(sheet)}})
        print(f"[{MODEL} AI 复核-图片/图文] {index}/{len(prepared)} 条查询", flush=True)
        batch_labels: list[dict[str, Any]] | None = None
        for attempt in range(2):
            try:
                parsed = parse_json(call_model([{"role": "user", "content": content}], max_tokens=2200))
                batch_labels = parse_label_response(parsed, [query], [case])
                break
            except (ValueError, json.JSONDecodeError) as exc:
                if attempt == 1:
                    raise ValueError(f"视觉查询 {query['query_id']} 连续两次未完整复核：{exc}") from exc
                print(f"[{MODEL} AI 复核] {query['query_id']} 输出不完整，单条重试。", flush=True)
        if batch_labels is None:
            raise RuntimeError(f"视觉查询 {query['query_id']} 未生成标注。")
        labels.extend(batch_labels)
        labeled_pairs.update((row["query_id"], str(row["item_id"])) for row in batch_labels)
        if progress_path:
            append_jsonl(progress_path, batch_labels)
    unique = {(row["query_id"], str(row["item_id"])): row for row in labels}
    return list(unique.values())


def create_ai_review_outputs(
    queries: list[dict[str, str]], manifest: dict[str, dict[str, str]],
    text_labels: list[dict[str, Any]], visual_labels: list[dict[str, Any]],
    result_dir: Path, rankings: dict[str, list[dict[str, str]]],
    item_lookup: dict[tuple[str, str], dict[str, str]],
) -> tuple[Path, Path, list[dict[str, Any]], list[dict[str, Any]]]:
    labels = text_labels + visual_labels
    label_map = {(row["query_id"], row["item_id"]): row for row in labels}
    query_review: dict[str, tuple[bool, str]] = {}
    for row in labels:
        qid = row["query_id"]
        value = (bool(row["query_valid"]), str(row["query_review_reason"]))
        if qid in query_review and query_review[qid] != value:
            raise ValueError(f"同一查询的 AI 有效性判断不一致：{qid}")
        query_review[qid] = value
    if set(query_review) != {query["query_id"] for query in queries}:
        raise ValueError("AI 复核未覆盖所有查询，停止生成最终评测输入。")

    # Text queries are generated from a catalog item. Keep that source item as
    # a known positive anchor, even when it is outside the returned Top-K.
    for query in queries:
        if query["mode"] != "text" or not query_review[query["query_id"]][0]:
            continue
        qid = query["query_id"]
        source_id = manifest[qid]["source_item_id"]
        label_map[(qid, source_id)] = {
            "query_id": qid, "item_id": source_id, "relevance": 3,
            "confidence": "medium",
            "reason": "查询由该商品字段生成；源商品作为已知相关锚点，查询有效性已由 AI 复核。",
            "judgment_source": "源商品锚点",
            "query_valid": True,
            "query_review_reason": query_review[qid][1],
        }
    rows = sorted(label_map.values(), key=lambda row: (row["query_id"], row["item_id"]))
    qrel_fields = ["query_id", "item_id", "relevance"]
    review_rows: list[dict[str, Any]] = []
    for row in rows:
        category = manifest[row["query_id"]]["category"]
        item = item_lookup.get((category, row["item_id"]), {})
        ranked = next((candidate for candidate in rankings.get(row["query_id"], []) if candidate["item_id"] == row["item_id"]), {})
        review_rows.append({
            "query_id": row["query_id"], "item_id": row["item_id"],
            "category": category, "result_rank": ranked.get("rank", ""),
            "item_name": item.get("item_name", ranked.get("item_name", "")),
            "type": item.get("type", ranked.get("type", "")),
            "color": item.get("color", ranked.get("color", "")),
            "material": item.get("material", ""),
            "local_image_path": item.get("local_image_path", ranked.get("local_image_path", "")),
            "relevance": row["relevance"], "confidence": row.get("confidence", "medium"),
            "reason": row["reason"], "judgment_source": row.get("judgment_source", "AI 复核"),
            "query_valid": row["query_valid"],
            "query_review_reason": row["query_review_reason"],
            "included_in_evaluation": query_review[row["query_id"]][0],
        })
    valid_queries = [query for query in queries if query_review[query["query_id"]][0]]
    valid_ids = {query["query_id"] for query in valid_queries}
    final_qrels = [
        {"query_id": row["query_id"], "item_id": row["item_id"], "relevance": row["relevance"]}
        for row in rows if row["query_id"] in valid_ids
    ]
    query_audit = []
    for query in queries:
        valid, reason = query_review[query["query_id"]]
        query_audit.append({
            **manifest[query["query_id"]],
            "ai_query_valid": str(valid).lower(),
            "evaluation_status": "included" if valid else "excluded",
            "ai_review_reason": reason,
        })

    input_dir = result_dir / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    generated_path = input_dir / "queries_generated.csv"
    manifest_path = input_dir / "query_manifest.csv"
    final_queries_path = input_dir / "queries.csv"
    final_qrels_path = input_dir / "qrels.csv"
    write_csv(generated_path, queries, ["query_id", "mode", "query_text", "query_image", "category", "exclude_item_id"])
    write_csv(manifest_path, list(manifest.values()), ["query_id", "mode", "category", "source_item_id", "query_text", "query_image", "generation_source"])
    write_csv(final_queries_path, valid_queries, ["query_id", "mode", "query_text", "query_image", "category", "exclude_item_id"])
    write_csv(final_qrels_path, final_qrels, qrel_fields)
    write_csv(result_dir / "ai_review.csv", review_rows, [
        "query_id", "item_id", "category", "result_rank", "item_name", "type", "color", "material",
        "local_image_path", "relevance", "confidence", "reason", "judgment_source", "query_valid",
        "query_review_reason", "included_in_evaluation",
    ])
    write_csv(result_dir / "query_audit.csv", query_audit, [
        "query_id", "mode", "category", "source_item_id", "query_text", "query_image", "generation_source",
        "ai_query_valid", "evaluation_status", "ai_review_reason",
    ])
    return final_queries_path, final_qrels_path, valid_queries, final_qrels


def main() -> int:
    parser = argparse.ArgumentParser(description="生成商品检索试点数据，由配置的模型复核查询和候选商品。")
    parser.add_argument("--per-category", type=int, default=5, help="每类选取商品数；每件商品生成文字、图片、图文 3 条查询。")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="cuda")
    parser.add_argument("--run-id", default=datetime.now().astimezone().strftime("gpt_pilot_%Y%m%d_%H%M%S_%f"))
    parser.add_argument("--resume", action="store_true", help="从本轮 work 检查点继续，跳过已完成的 AI 复核。")
    args = parser.parse_args()
    if args.per_category < 1:
        raise ValueError("--per-category 必须大于 0。")
    if Path(args.run_id).name != args.run_id or args.run_id in {".", ".."}:
        raise ValueError("--run-id 只能是单层目录名，不能包含路径。")
    result_dir = EVAL_ROOT / "results" / "runs" / args.run_id
    work_dir = result_dir / "work"
    query_path = work_dir / "queries_generated.csv"
    manifest_path = work_dir / "query_manifest.csv"
    registry_path = REPO_ROOT / "data" / "index_data" / "index_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    if args.resume:
        if not query_path.is_file() or not manifest_path.is_file():
            raise FileNotFoundError(f"运行目录 {args.run_id} 缺少 work 查询或 query_manifest.csv，无法恢复。")
        if not (result_dir / "ranked_results.csv").is_file():
            raise FileNotFoundError(f"运行目录 {args.run_id} 缺少 ranked_results.csv，请先完成检索排名。")
        queries = read_csv(query_path)
        manifest = {row["query_id"]: row for row in read_csv(manifest_path)}
        categories = sorted({row.get("category", "").strip() for row in queries if row.get("category", "").strip()})
        item_lookup: dict[tuple[str, str], dict[str, str]] = {}
        for category in categories:
            for item in read_csv(REPO_ROOT / "data" / "index_data" / category / "items.csv"):
                item_id = (item.get("item_id") or item.get("product_id") or "").strip()
                if item_id:
                    item_lookup[(category, item_id)] = item
        print(f"[恢复] 加载 {len(queries)} 条已有查询及排名，不重新生成查询或向量。", flush=True)
    else:
        if result_dir.exists():
            raise FileExistsError(f"运行目录已存在，避免覆盖：{args.run_id}；如需继续请使用 --resume。")
        work_dir.mkdir(parents=True)
        categories = sorted(registry.get("categories", {}))
        if not categories:
            raise ValueError("data/index_data/index_registry.json 中没有已注册类别。")
        queries, manifest, item_lookup = save_queries_and_manifest(categories, args.per_category, work_dir)
        # First pass creates the fixed Top-K candidate pool. Labels are added after AI review.
        run_retrieval(query_path, work_dir / "qrels_pending.csv", result_dir, args.top_k, args.candidate_k, args.device)
    ranking_rows = read_csv(result_dir / "ranked_results.csv")
    rankings: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in ranking_rows:
        rankings[row["query_id"]].append(row)
    for qid in rankings:
        rankings[qid].sort(key=lambda row: int(row["rank"]))

    text_labels = label_text_queries(
        queries, rankings, manifest, item_lookup, work_dir / "text_review_progress.jsonl"
    )
    sheet_dir = result_dir / "contact_sheets"
    visual_labels = label_visual_queries(
        queries, rankings, manifest, item_lookup, sheet_dir,
        work_dir / "visual_review_progress.jsonl",
    )
    final_queries_path, final_qrels_path, final_queries, final_qrels = create_ai_review_outputs(
        queries, manifest, text_labels, visual_labels, result_dir, rankings, item_lookup
    )
    if not final_queries:
        raise ValueError("AI 复核判定所有查询均无效，无法计算评测指标。")
    # Reuse the fixed query/ranking setup with the canonical AI-reviewed labels.
    run_retrieval(final_queries_path, final_qrels_path, result_dir, args.top_k, args.candidate_k, args.device)

    summary_path = result_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    audit_rows = read_csv(result_dir / "query_audit.csv")
    included_count = sum(row["evaluation_status"] == "included" for row in audit_rows)
    summary.update({
        "evaluation_label_source": "AI query and candidate relevance review; generated text queries retain source-item anchors",
        "ai_judge_model": MODEL,
        "ai_reviewed_query_count": len(audit_rows),
        "included_query_count": included_count,
        "excluded_query_count": len(audit_rows) - included_count,
        "tuning_role": "pilot_validation",
        "relevance_rubric": "0 不相关；1 弱相关；2 相关替代；3 高度符合。按视觉商品检索意图及查询明确约束评分。",
        "interpretation": "本轮由 AI 生成查询并复核查询有效性和候选相关度；文字查询保留由源商品构造的确定性相关锚点。结果可用于初步调参，但不作为独立最终测试集或人工真值。",
    })
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata_path = result_dir / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update({
        "evaluation_label_source": "AI query and candidate relevance review; generated text queries retain source-item anchors",
        "ai_judge_model": MODEL,
        "canonical_queries": f"evaluation/retrieval/results/runs/{args.run_id}/inputs/queries.csv",
        "canonical_qrels": f"evaluation/retrieval/results/runs/{args.run_id}/inputs/qrels.csv",
        "tuning_role": "pilot_validation",
    })
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = (
        f"# {MODEL} AI 复核检索试点评测\n\n"
        f"- 日期：{datetime.now().astimezone().isoformat(timespec='seconds')}\n"
        f"- 类别：{len(categories)} 类；生成查询 {len(queries)} 条，AI 判定有效 {len(final_queries)} 条、排除 {len(queries) - len(final_queries)} 条。\n"
        f"- 最终 qrels：{len(final_qrels)} 条 AI 候选判断及源商品锚点；最终统一使用 `inputs/queries.csv`、`inputs/qrels.csv` 和本目录指标。\n"
        f"- 相关度口径：0 不相关，1 弱相关，2 相关替代，3 高度符合；遵循查询明确约束。\n"
        f"- 本进程 API 调用：{API_CALL_COUNT} 次；服务返回 Token：prompt {API_USAGE['prompt_tokens']}，completion {API_USAGE['completion_tokens']}。\n\n"
        "## 用途与边界\n\n"
        "AI 核验查询有效性并对 Top-K 候选评分；文字查询的源商品作为确定性相关锚点。无效查询保留在 `query_audit.csv`，不进入最终指标。"
        "本结果作为后续融合权重调优的试点验证集，调参时固定本轮查询、qrels、索引和候选参数。"
        "由于查询与标签均由 AI 生成/评审，本轮不是独立最终测试集；最终效果应另用留出的查询集评估。\n\n"
        "## 文件入口\n\n"
        "- `inputs/queries.csv`、`inputs/qrels.csv`：本轮唯一正式评测输入。\n"
        "- `ai_review.csv`、`query_audit.csv`：AI 逐商品判断和查询纳入/排除依据。\n"
        "- `ranked_results.csv`、`query_metrics.csv`、`summary.json`：统一口径下的排序与指标。\n"
        "- `contact_sheets/`：AI 视觉判断使用的查询图和候选商品联系表。\n"
        "\n## 文件说明与后续用途\n\n"
        "| 文件/目录 | 内容与用途 | 后续用途 |\n"
        "|---|---|---|\n"
        "| `inputs/queries.csv` | AI 判定有效、实际计算指标的查询。 | **权重调优固定输入**；论文中说明查询类型和范围。 |\n"
        "| `inputs/qrels.csv` | 最终 0–3 级相关性标签，含 AI 候选判断和文字查询源商品锚点。 | **权重调优固定标签**；论文评测方法和指标依据。 |\n"
        "| `inputs/queries_generated.csv` | 全部生成查询，包含被排除项。 | 追溯查询筛选；不直接计算指标。 |\n"
        "| `inputs/query_manifest.csv` | 查询与类别、源商品、模式及生成来源的关系。 | 检查来源商品重叠、构造独立留出集。 |\n"
        "| `inputs/retrieval_config.json` | 本轮使用的检索参数快照。 | 复现实验并确认调优时参数一致。 |\n"
        "| `ai_review.csv` | 候选等级、理由、置信度、查询状态；区分 AI 判断和源商品锚点。 | 审计 AI 标签、分析误判；不代替 `qrels.csv`。 |\n"
        "| `query_audit.csv` | 每条查询的 AI 有效性判断、纳入状态和理由。 | 说明查询过滤过程、分析数据质量。 |\n"
        "| `ranked_results.csv` | Top-K 结果、排序和各检索通道分数。 | **分析权重变化和检索错误**；制作论文案例。 |\n"
        "| `query_metrics.csv` | 每条查询的 Precision、Recall、nDCG、MRR 等。 | **比较调优前后效果**；重新绘制统计图。 |\n"
        "| `summary.json` | 分查询模式的总体指标和评测口径。 | 脚本读取和实验间机器比较。 |\n"
        "| `run_metadata.json` | 索引、模型、权重、Top-K 和相对输入路径。 | 核对实验可比性、复现设置。 |\n"
        "| `api_usage.json` | 模型名、调用次数和 token 统计，不含 API Key。 | 记录模型成本；恢复运行时统计可能仅覆盖本进程。 |\n"
        "| `contact_sheets/` | 图片/图文查询及 Top-K 候选的联系表。 | 复查视觉判断、选取论文定性案例。 |\n"
        "| `metrics_by_mode.png` | 不同查询模式的指标对比图。 | 论文结果图；可由指标数据重绘。 |\n"
        "| `first_relevant_rank.png` | 首个相关结果的排名分布。 | 论文分析用户找到相关商品所需浏览位置。 |\n"
        "| `sample_topk_scores.png` | 示例查询的 Top-K 分项分数图。 | 解释排序和权重变化；可从排名数据重绘。 |\n"
        "| `测试结果说明.md` | 本轮结论、局限和文件用途。 | 阅读入口；不作为计算输入。 |\n\n"
        "后续权重调优必须固定 `inputs/queries.csv`、`inputs/qrels.csv`、索引和模型版本；其他结果文件用于复现、诊断或写作。图表可重绘，但保留当前版本便于对照。\n"
    )
    (result_dir / "测试结果说明.md").write_text(report, encoding="utf-8")
    usage = {"model": MODEL, "base_url": BASE_URL, "calls_this_process": API_CALL_COUNT, "tokens_this_process": dict(API_USAGE), "resumed": args.resume}
    (result_dir / "api_usage.json").write_text(json.dumps(usage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(work_dir, ignore_errors=True)
    print(f"完成：AI 复核 {len(queries)} 条查询，最终纳入 {len(final_queries)} 条、{len(final_qrels)} 条相关性判断。", flush=True)
    print(f"结果：{result_dir}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        API_KEY = ""
