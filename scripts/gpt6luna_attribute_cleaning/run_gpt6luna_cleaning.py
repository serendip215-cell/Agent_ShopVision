#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调用 OpenAI 兼容视觉接口识别 MUGE 商品并生成候选清洗数据。

默认只读取 data/processed_data/*/products.csv，输出到
data/processed_data_gpt6luna，不修改正式数据。
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

TARGET_TYPES = ("包", "水杯", "鞋")
UNKNOWN_VALUES = {"", "未知", "不确定", "无法判断", "无法识别", "不详", "none", "null", "n/a", "na"}
COLOR_MAP = {
    "白": "白色", "白色": "白色", "黑": "黑色", "黑色": "黑色",
    "红": "红色", "红色": "红色", "蓝": "蓝色", "蓝色": "蓝色",
    "绿": "绿色", "绿色": "绿色", "黄": "黄色", "黄色": "黄色",
    "灰": "灰色", "灰色": "灰色", "棕": "棕色", "棕色": "棕色",
    "咖啡": "棕色", "咖啡色": "棕色", "米": "米色", "米色": "米色",
    "米白": "米白色", "米白色": "米白色", "粉": "粉色", "粉色": "粉色",
    "紫": "紫色", "紫色": "紫色", "橙": "橙色", "橙色": "橙色",
    "银": "银色", "银色": "银色", "金": "金色", "金色": "金色",
    "透明": "透明", "彩色": "多色", "多色": "多色",
    "卡其": "卡其色", "卡其色": "卡其色", "藏青": "藏青色", "藏青色": "藏青色",
    "深蓝": "深蓝色", "深蓝色": "深蓝色", "浅蓝": "浅蓝色", "浅蓝色": "浅蓝色",
    "深灰": "深灰色", "深灰色": "深灰色", "浅灰": "浅灰色", "浅灰色": "浅灰色",
    "裸色": "裸色",
}
MATERIAL_TERMS = (
    "头层牛皮", "真皮", "二层牛皮", "牛皮", "羊皮", "皮革", "人造革",
    "PU", "PVC", "网面", "网布", "帆布", "尼龙", "涤纶", "聚酯纤维",
    "棉", "麻", "不锈钢", "玻璃", "陶瓷", "塑料", "硅胶", "橡胶",
    "EVA", "木质", "铝合金",
)

SYSTEM_PROMPT = """你是中文电商商品数据清洗员。你必须同时观察商品图片，并参考标题和当前类别作为弱提示。
当前类别可能错误，不能只复制当前类别。只把图片中真正作为商品主体的物品作为结果。
请只返回一个 JSON 对象，不要 Markdown、解释文字或代码围栏，字段必须是：
{
  "is_product": true,
  "product_type": "包|水杯|鞋|其他|无法判断",
  "type": "细分类名称，无法判断时为空字符串",
  "color": "主色或配色，无法确认时为空字符串",
  "material": "能从图片或标题可靠判断的主要材质，无法确认时为空字符串",
  "confidence": 0.0,
  "reason": "一句简短中文理由"
}
不要凭空猜颜色或材质。配件、包装盒、货架、食品、书籍、家具等不是目标商品时，is_product=false 或 product_type=其他。
"""
USER_PROMPT = """请识别这条商品记录。
当前类别（仅作弱提示）：{source_category}
标题：{item_name}
原有颜色：{old_color}
原有材质：{old_material}
原有描述：{old_description}
要求：
1. 先判断图片主体是否是可售商品；
2. 若是目标商品，判断商品大类（包、水杯、鞋）和细分类；
3. 颜色只填图片可见的主要颜色，材质只填有依据的材质；
4. 图片与文字冲突时以图片为主；
5. 只返回约定 JSON。
"""


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_value(env: dict[str, str], key: str, default: str = "") -> str:
    return os.environ.get(key, env.get(key, default)).strip()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    root = repo_root()
    parser = argparse.ArgumentParser(description="调用 GPT6Luna 识别商品大类、细分类、颜色和材质")
    parser.add_argument("--input-dir", type=Path, default=root / "data" / "processed_data")
    parser.add_argument("--output-dir", type=Path, default=root / "data" / "processed_data_gpt6luna")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--min-confidence", type=float, default=0.72)
    parser.add_argument("--image-detail", choices=("low", "high", "auto"), default=None)
    parser.add_argument("--force", action="store_true", help="忽略已有 audit，重新调用接口")
    return parser.parse_args()


def normalise_path(path: str) -> Path:
    return Path(path.replace("\\", "/"))


def resolve_image(row: dict[str, str], source_csv: Path, root: Path) -> Path | None:
    raw = (row.get("local_image_path") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidate = normalise_path(raw)
        candidates.extend((root / candidate, source_csv.parent / candidate))
    item_id = (row.get("item_id") or "").strip()
    suffix_id = item_id.rsplit("_", 1)[-1] if "_" in item_id else item_id
    if suffix_id:
        candidates.extend([
            source_csv.parent / "images" / f"{suffix_id}.jpg",
            source_csv.parent / "images" / f"{suffix_id}.jpeg",
            source_csv.parent / "images" / f"{suffix_id}.png",
        ])
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def compact(value: Any, limit: int = 120) -> str:
    text = "" if value is None else str(value).strip()
    return text[:limit]


def normalise_product_type(value: Any) -> str:
    text = compact(value, 40).replace(" ", "")
    if not text or text.lower() in UNKNOWN_VALUES:
        return ""
    if any(term in text for term in ("水杯", "保温杯", "马克杯", "杯子", "水壶", "咖啡杯")):
        return "水杯"
    if any(term in text for term in ("运动鞋", "板鞋", "高跟鞋", "皮鞋", "凉鞋", "拖鞋", "靴", "鞋")):
        return "鞋"
    if any(term in text for term in ("背包", "书包", "手提包", "斜挎包", "单肩包", "钱包", "包")):
        return "包"
    if text in {"其他", "非商品", "无法判断"}:
        return text
    return ""


def normalise_color(value: Any) -> str:
    text = compact(value, 60)
    if not text or text.lower() in UNKNOWN_VALUES:
        return ""
    text = re.sub(r"[，,、/|及与]", "/", text)
    parts = [part.strip() for part in text.split("/") if part.strip()]
    normalised: list[str] = []
    for part in parts:
        item = COLOR_MAP.get(part, "")
        if not item:
            item = next((v for k, v in COLOR_MAP.items() if k and k in part), "")
        if item and item not in normalised:
            normalised.append(item)
    return "、".join(normalised[:3])


def normalise_material(value: Any) -> str:
    text = compact(value, 60)
    if not text or text.lower() in UNKNOWN_VALUES:
        return ""
    for term in MATERIAL_TERMS:
        if term.lower() in text.lower():
            return term
    text = re.sub(r"[\r\n\t]+", "", text)
    if len(text) <= 12 and re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9（）()\- ]+", text):
        return text
    return ""


def normalise_fine_type(value: Any) -> str:
    text = compact(value, 40)
    if text.lower() in UNKNOWN_VALUES:
        return ""
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"^(细分类|细分类别|商品细分类)[:：]\s*", "", text)
    return text[:30]


def safe_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number /= 100
    return max(0.0, min(number, 1.0))


def parse_json_object(content: str) -> dict[str, Any]:
    fence = chr(96) * 3
    text = content.strip().replace(fence + "json", "").replace(fence, "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON 对象")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型返回的 JSON 不是对象")
    return value


def endpoint_from_env(env: dict[str, str]) -> str:
    base = env_value(env, "OPENAI_BASE_URL", "https://ai-pixel.online").rstrip("/")
    explicit = env_value(env, "OPENAI_API_PATH", "")
    if explicit:
        return explicit if explicit.startswith(("http://", "https://")) else base + "/" + explicit.lstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def call_api(*, endpoint: str, api_key: str, model: str, image_url: str,
             user_text: str, timeout: int, retries: int, image_detail: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_url, "detail": image_detail}},
            ]},
        ],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last_error = ""
    for attempt in range(retries + 1):
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            choices = data.get("choices") or []
            if not choices:
                raise ValueError("接口响应缺少 choices")
            message = choices[0].get("message") or {}
            content = message.get("content", "")
            if isinstance(content, list):
                content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
            return parse_json_object(str(content))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    detail = exc.read().decode("utf-8", errors="replace")[:400]
                except Exception:
                    detail = ""
                last_error = f"HTTP {exc.code}: {detail}"
            else:
                last_error = str(exc)
            if attempt < retries:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(last_error or "接口调用失败")


def record_key(source_category: str, item_id: str) -> str:
    return hashlib.sha1(f"{source_category}\0{item_id}".encode("utf-8")).hexdigest()


def load_rows(input_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    fieldnames: list[str] = []
    for csv_path in sorted(input_dir.glob("*/products.csv")):
        category = csv_path.parent.name
        if category not in TARGET_TYPES:
            continue
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not fieldnames:
                fieldnames = list(reader.fieldnames or [])
            for row in reader:
                row["_source_category"] = category
                row["_source_csv"] = str(csv_path)
                rows.append(row)
    if not fieldnames:
        raise FileNotFoundError(f"未找到 {input_dir}/*/products.csv")
    return rows, fieldnames


def read_audit(path: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return results
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("record_key"):
                results[str(item["record_key"])] = item
    return results


def make_record(row: dict[str, str], *, root: Path, env: dict[str, str],
                args: argparse.Namespace) -> dict[str, Any]:
    source_category = row["_source_category"]
    item_id = (row.get("item_id") or "").strip()
    image_path = resolve_image(row, Path(row["_source_csv"]), root)
    base: dict[str, Any] = {
        "record_key": record_key(source_category, item_id),
        "item_id": item_id, "source_category": source_category, "status": "review",
        "reason": "", "model": env_value(env, "MODEL", "gpt6luna"),
        "product_type": "", "type": "", "color": "", "material": "", "confidence": 0.0,
    }
    if image_path is None:
        base["reason"] = "图片文件不存在"
        return base
    try:
        user_text = USER_PROMPT.format(
            source_category=source_category,
            item_name=compact(row.get("item_name"), 160),
            old_color=compact(row.get("color"), 40),
            old_material=compact(row.get("material"), 40),
            old_description=compact(row.get("description"), 160),
        )
        parsed = call_api(
            endpoint=endpoint_from_env(env),
            api_key=env_value(env, "OPENAI_API_KEY"),
            model=env_value(env, "MODEL", "gpt6luna"),
            image_url=image_data_url(image_path),
            user_text=user_text,
            timeout=int(env_value(env, "REQUEST_TIMEOUT", "120")),
            retries=int(env_value(env, "MAX_RETRIES", "3")),
            image_detail=args.image_detail or env_value(env, "IMAGE_DETAIL", "high"),
        )
        product_type = normalise_product_type(parsed.get("product_type"))
        fine_type = normalise_fine_type(parsed.get("type") or parsed.get("fine_type"))
        color = normalise_color(parsed.get("color"))
        material = normalise_material(parsed.get("material"))
        confidence = safe_float(parsed.get("confidence"))
        is_product = parsed.get("is_product")
        if isinstance(is_product, str):
            is_product = is_product.strip().lower() in {"true", "1", "yes", "是"}
        is_product = bool(is_product)
        if not is_product or product_type == "其他":
            base["status"] = "excluded"
            base["reason"] = "模型判断为非目标商品或其他类别"
        elif product_type not in TARGET_TYPES:
            base["reason"] = "模型无法归入目标大类"
        elif confidence < args.min_confidence:
            base["reason"] = f"置信度 {confidence:.2f} 低于阈值 {args.min_confidence:.2f}"
        else:
            base["status"] = "accepted"
            base["reason"] = "通过商品类别和置信度检查"
        base.update({
            "product_type": product_type, "type": fine_type, "color": color,
            "material": material, "confidence": confidence,
            "model_reason": compact(parsed.get("reason"), 240),
        })
        return base
    except Exception as exc:
        base["reason"] = compact(f"接口或解析失败：{exc}", 400)
        return base


def description_for(product_type: str, fine_type: str, color: str, material: str) -> str:
    return (
        f"商品大类：{product_type or '未识别'}；"
        f"细分类：{fine_type or '未识别'}；"
        f"颜色：{color or '未识别'}；"
        f"材质：{material or '未识别'}"
    )


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field, "") for field in fieldnames})


def build_output_row(row: dict[str, str], result: dict[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    output = {field: row.get(field, "") for field in fieldnames}
    output["product_type"] = result.get("product_type", "")
    output["color"] = result.get("color", "")
    output["material"] = result.get("material", "")
    output["type"] = result.get("type", "")
    output["tpye"] = result.get("type", "")
    output["description"] = description_for(output["product_type"], output["type"], output["color"], output["material"])
    return output


def write_outputs(*, output_dir: Path, rows: list[dict[str, str]],
                  results: dict[str, dict[str, Any]], fieldnames: list[str],
                  min_confidence: float) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    final_fields = list(fieldnames)
    for field in ("type", "tpye"):
        if field not in final_fields:
            final_fields.append(field)
    accepted: dict[str, list[dict[str, Any]]] = {category: [] for category in TARGET_TYPES}
    review_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    counts = {category: {"input": 0, "accepted": 0, "review": 0, "excluded": 0} for category in TARGET_TYPES}
    for row in rows:
        source_category = row["_source_category"]
        counts[source_category]["input"] += 1
        key = record_key(source_category, (row.get("item_id") or "").strip())
        result = results.get(key) or {
            "status": "review", "reason": "尚未完成模型识别", "product_type": "",
            "type": "", "color": "", "material": "", "confidence": 0.0,
        }
        status = result.get("status")
        if status == "accepted" and result.get("product_type") in TARGET_TYPES:
            category = str(result["product_type"])
            accepted[category].append(build_output_row(row, result, fieldnames))
            counts[category]["accepted"] += 1
        elif status == "excluded":
            excluded_rows.append({
                **{field: row.get(field, "") for field in fieldnames},
                "source_category": source_category, "exclude_reason": result.get("reason", ""),
            })
            counts[source_category]["excluded"] += 1
        else:
            review_rows.append({
                **{field: row.get(field, "") for field in fieldnames},
                "source_category": source_category, "review_reason": result.get("reason", ""),
                "model_product_type": result.get("product_type", ""),
                "model_type": result.get("type", ""), "model_color": result.get("color", ""),
                "model_material": result.get("material", ""), "confidence": result.get("confidence", 0.0),
            })
            counts[source_category]["review"] += 1
    for category, category_rows in accepted.items():
        write_csv(output_dir / category / "products.csv", category_rows, final_fields)
    review_fields = fieldnames + ["source_category", "review_reason", "model_product_type",
                                  "model_type", "model_color", "model_material", "confidence"]
    excluded_fields = fieldnames + ["source_category", "exclude_reason"]
    write_csv(output_dir / "review_candidates.csv", review_rows, review_fields)
    write_csv(output_dir / "excluded_samples.csv", excluded_rows, excluded_fields)
    summary_rows = [
        {"product_type": category, "input_count": values["input"],
         "accepted_count": values["accepted"], "review_count": values["review"],
         "excluded_count": values["excluded"], "min_confidence": min_confidence}
        for category, values in counts.items()
    ]
    write_csv(output_dir / "dataset_summary.csv", summary_rows,
              ["product_type", "input_count", "accepted_count", "review_count", "excluded_count", "min_confidence"])
    report = {
        "input_rows": len(rows), "accepted_rows": sum(len(items) for items in accepted.values()),
        "review_rows": len(review_rows), "excluded_rows": len(excluded_rows),
        "target_types": list(TARGET_TYPES), "output_fields": final_fields,
        "relative_image_paths": True,
        "note": "图片不重复复制，products.csv 中的 local_image_path 保留仓库根目录相对路径。",
    }
    (output_dir / "cleaning_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = f"""# GPT6Luna 清洗候选结果

本目录由 scripts/gpt6luna_attribute_cleaning/run_gpt6luna_cleaning.py 生成。
正式数据目录未被覆盖。

- 输入记录：{len(rows)}
- 接受记录：{report["accepted_rows"]}
- 待复核：{report["review_rows"]}
- 排除：{report["excluded_rows"]}

products.csv 保留原始字段，并增加 type 和 tpye 两列；description 使用统一模板生成。
所有图片路径保持仓库根目录相对路径，不复制图片文件。
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = repo_root()
    env = load_env(Path(__file__).resolve().parent / ".env")
    workers = args.workers or int(env_value(env, "MAX_WORKERS", "4"))
    if not env_value(env, "OPENAI_API_KEY"):
        print("警告：未读取到 OPENAI_API_KEY；若中转站不接受匿名请求，接口调用会失败。", file=sys.stderr)
    rows, fieldnames = load_rows(args.input_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.output_dir / "model_audit.jsonl"
    completed = {} if args.force else read_audit(audit_path)
    pending = [
        row for row in rows
        if record_key(row["_source_category"], (row.get("item_id") or "").strip()) not in completed
    ]
    print(f"输入 {len(rows)} 条，已完成 {len(rows) - len(pending)} 条，待处理 {len(pending)} 条。")
    append_mode = "a" if audit_path.exists() and not args.force else "w"
    with audit_path.open(append_mode, encoding="utf-8") as audit_handle:
        if pending:
            with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
                future_map = {executor.submit(make_record, row, root=root, env=env, args=args): row for row in pending}
                done = 0
                for future in as_completed(future_map):
                    result = future.result()
                    completed[result["record_key"]] = result
                    audit_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                    audit_handle.flush()
                    done += 1
                    print(f"[{done}/{len(pending)}] {result['item_id']} {result['status']} "
                          f"{result.get('product_type', '')} {result.get('reason', '')}")
    write_outputs(output_dir=args.output_dir, rows=rows, results=completed,
                  fieldnames=fieldnames, min_confidence=args.min_confidence)
    print(f"候选结果已写入：{args.output_dir}")
    print("请先核查 review_candidates.csv 和各类别 products.csv，再决定是否覆盖正式数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
