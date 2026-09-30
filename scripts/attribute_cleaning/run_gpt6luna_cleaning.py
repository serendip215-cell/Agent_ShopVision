#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调用 OpenAI 兼容视觉接口识别 MUGE 商品并生成候选清洗数据。

默认只读取 data/processed_data/*/products.csv，输出到
data/processed_data_cleaning，不修改正式数据。
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
import shutil
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

TARGET_TYPES: tuple[str, ...] = ()
MODEL_FAILURE_FILE = "model_failures.csv"
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
  "product_type": "目标类别列表|其他|无法判断",
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
2. 若是目标商品，判断商品大类（{allowed_categories}）和细分类；
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
    parser = argparse.ArgumentParser(description="调用 GPT6Luna 识别商品大类、细分类、颜色和材质")
    parser.add_argument("--input-dir", type=Path, default=Path("data/processed_data"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed_data_cleaning"))
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--categories", default="", help="逗号分隔的目标类别；留空则自动读取输入目录下的类别文件夹")
    parser.add_argument("--min-confidence", type=float, default=0.72)
    parser.add_argument("--image-detail", choices=("low", "high", "auto"), default=None)
    parser.add_argument("--force", action="store_true", help="允许覆盖已有输出；是否调用模型仍只由 is_readed 决定")
    parser.add_argument(
        "--append",
        action="store_true",
        help="保留已有清洗输出，并按 item_id 增量合并",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="删除已有清洗输出目录后重新生成",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="兼容旧命令；失败记录因 is_readed=false 会在普通运行中自动重试",
    )
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
    if text in TARGET_TYPES:
        return text
    for category in TARGET_TYPES:
        compact_category = category.replace(" ", "")
        category_stem = re.sub(r"(类别|品类|类)$", "", compact_category)
        if category_stem and (category_stem in text or text in category_stem):
            return category
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
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_url, "detail": image_detail}},
            ]},
        ],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Connection": "close"}
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
                time.sleep(min(1.5 * (2 ** attempt), 15))
    raise RuntimeError(last_error or "接口调用失败")


def record_key(source_category: str, item_id: str) -> str:
    return hashlib.sha1(f"{source_category}\0{item_id}".encode("utf-8")).hexdigest()


def input_csv_paths(input_dir: Path) -> list[tuple[str, Path]]:
    """支持两种入口：类别目录本身，或包含多个类别子目录的数据集根目录。"""
    direct_csv = input_dir / "products.csv"
    if direct_csv.is_file():
        return [(input_dir.name, direct_csv)]
    return [(csv_path.parent.name, csv_path) for csv_path in sorted(input_dir.glob("*/products.csv"))]


def load_rows(input_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    fieldnames: list[str] = []
    for category, csv_path in input_csv_paths(input_dir):
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
        "reason": "", "model": env_value(env, "MODEL", "gpt6luna"), "is_readed": "false",
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
            allowed_categories="、".join(TARGET_TYPES),
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
            "is_readed": "true",
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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_cleaning_report_history(path: Path) -> list[dict[str, Any]]:
    """读取报告历史，并把旧版单次快照迁移成第一条历史记录。"""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    history = payload.get("runs")
    if isinstance(history, list):
        return [item for item in history if isinstance(item, dict)]
    if not any(key in payload for key in ("input_rows", "accepted_rows", "review_rows", "excluded_rows")):
        return []
    # 兼容修改前生成的扁平报告，避免第一次升级时丢失历史汇总。
    return [{
        "generated_at": payload.get("generated_at"),
        "legacy": True,
        "input_rows": payload.get("input_rows", 0),
        "accepted_rows": payload.get("accepted_rows", 0),
        "review_rows": payload.get("review_rows", 0),
        "excluded_rows": payload.get("excluded_rows", 0),
        "target_types": payload.get("target_types", []),
    }]


def load_existing_outputs(output_dir: Path) -> dict[str, Any]:
    accepted: dict[str, list[dict[str, str]]] = {}
    failures: dict[str, list[dict[str, str]]] = {}
    for csv_path in sorted(output_dir.glob("*/products.csv")):
        accepted[csv_path.parent.name] = read_csv_rows(csv_path)
    for csv_path in sorted(output_dir.glob(f"*/{MODEL_FAILURE_FILE}")):
        failures[csv_path.parent.name] = read_csv_rows(csv_path)
    return {
        "accepted": accepted,
        "failures": failures,
        "unprocessed": read_csv_rows(output_dir / "unprocessed_samples.csv"),
        "review": read_csv_rows(output_dir / "review_candidates.csv"),
        "excluded": read_csv_rows(output_dir / "excluded_samples.csv"),
    }



def without_read_field(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(row)
    cleaned.pop("is_read", None)
    cleaned.pop("is_readed", None)
    cleaned.pop("tpye", None)
    return cleaned


def mark_source_row_read(source_csv: Path, item_id: str) -> bool:
    """将模型成功返回后的源记录标记为已读。"""
    if not source_csv.exists() or not item_id:
        return False
    with source_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not fieldnames:
        return False
    if "is_readed" not in fieldnames:
        fieldnames.append("is_readed")
    changed = False
    for row in rows:
        if (row.get("item_id") or "").strip() == item_id and row.get("is_readed") != "true":
            row["is_readed"] = "true"
            changed = True
    if not changed:
        return False
    temporary = source_csv.with_name(f".{source_csv.name}.is_readed.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(source_csv)
    return True


def build_output_row(row: dict[str, str], result: dict[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    output = {field: row.get(field, "") for field in fieldnames}
    output["product_type"] = result.get("product_type", "")
    output["color"] = result.get("color", "")
    output["material"] = result.get("material", "")
    output["type"] = result.get("type", "")
    output["description"] = description_for(output["product_type"], output["type"], output["color"], output["material"])
    return output


def write_csv_atomic(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field, "") for field in fieldnames})
    temporary.replace(path)


def copy_output_image(row: dict[str, Any], image_dir: Path, *, root: Path) -> str:
    """将记录图片复制到清洗输出目录，并返回仓库根目录相对路径。"""
    source_csv = Path(row.get("_source_csv") or (root / "__missing_source__.csv"))
    source = resolve_image(row, source_csv, root)
    if source is None:
        return str(row.get("local_image_path", "") or "")

    raw_item_id = str(row.get("item_id") or "").strip()
    safe_item_id = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_item_id).strip("._-")
    if not safe_item_id:
        safe_item_id = hashlib.sha1(raw_item_id.encode("utf-8")).hexdigest()[:12]
    prefix = f"{safe_item_id}__"
    filename = source.name if source.name.startswith(prefix) else prefix + source.name
    image_dir.mkdir(parents=True, exist_ok=True)
    destination = image_dir / filename
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    try:
        relative = destination.resolve().relative_to(root.resolve())
        return relative.as_posix()
    except ValueError:
        return destination.resolve().as_posix()


class StreamingOutputWriter:
    """逐条更新通过记录和未通过记录，避免等全部模型任务结束后才落盘。"""

    def __init__(self, output_dir: Path, fieldnames: list[str], existing: dict[str, Any], *, root: Path) -> None:
        self.output_dir = output_dir
        self.root = root
        self.clean_fields = [field for field in fieldnames if field not in {"tpye", "is_read", "is_readed"}]
        if "type" not in self.clean_fields:
            self.clean_fields.append("type")
        self.unprocessed_fields = self.clean_fields + [
            "source_category", "status", "reason", "model_product_type", "model_type",
            "model_color", "model_material", "confidence",
        ]
        self.failure_fields = self.clean_fields + [
            "source_category", "failure_status", "failure_reason", "attempt_count", "last_failed_at",
        ]
        self.accepted_rows: dict[str, list[dict[str, Any]]] = {}
        self.unprocessed_rows: list[dict[str, Any]] = []
        self.failure_rows: dict[str, list[dict[str, Any]]] = {}
        self.run_counts: dict[str, int] = {
            "input": 0,
            "accepted": 0,
            "review": 0,
            "excluded": 0,
        }
        self.run_counts_by_category: dict[str, dict[str, int]] = {}
        self._load_existing(existing)
        self._rewrite_existing()

    def _normalise_unprocessed(self, row: dict[str, Any], default_status: str) -> dict[str, Any]:
        output = {field: row.get(field, "") for field in self.clean_fields}
        output.update({
            "source_category": row.get("source_category", ""),
            "status": row.get("status") or default_status,
            "reason": row.get("reason") or row.get("review_reason") or row.get("exclude_reason", ""),
            "model_product_type": row.get("model_product_type", ""),
            "model_type": row.get("model_type", ""),
            "model_color": row.get("model_color", ""),
            "model_material": row.get("model_material", ""),
            "confidence": row.get("confidence", 0.0),
        })
        return output

    def _load_existing(self, existing: dict[str, Any]) -> None:
        seen_ids: set[str] = set()
        for category, rows in existing.get("accepted", {}).items():
            kept_rows: list[dict[str, Any]] = []
            for row in rows:
                item_id = (row.get("item_id") or "").strip()
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                kept_rows.append(without_read_field(row))
            self.accepted_rows[category] = kept_rows

        failure_seen: set[str] = set()
        for category, rows in existing.get("failures", {}).items():
            kept_rows: list[dict[str, Any]] = []
            for row in rows:
                item_id = (row.get("item_id") or "").strip()
                if item_id and item_id in failure_seen:
                    continue
                if item_id:
                    failure_seen.add(item_id)
                output = {field: row.get(field, "") for field in self.failure_fields}
                output["failure_status"] = row.get("failure_status") or "pending"
                output["attempt_count"] = row.get("attempt_count") or 1
                kept_rows.append(output)
            self.failure_rows[category] = kept_rows

        def add_unprocessed(rows: Iterable[dict[str, Any]], default_status: str) -> None:
            for row in rows:
                item_id = (row.get("item_id") or "").strip()
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                self.unprocessed_rows.append(self._normalise_unprocessed(row, default_status))

        add_unprocessed(existing.get("unprocessed", []), "review")
        add_unprocessed(existing.get("review", []), "review")
        add_unprocessed(existing.get("excluded", []), "excluded")

        # 兼容尚未生成 model_failures.csv 的旧输出，把模型调用失败记录迁移到按类别队列。
        for row in self.unprocessed_rows:
            reason = str(row.get("reason") or "")
            if not reason.startswith(("接口或解析失败", "图片文件不存在")):
                continue
            category = str(row.get("source_category") or "UNKNOWN")
            failures = self.failure_rows.setdefault(category, [])
            item_id = (row.get("item_id") or "").strip()
            if any((failure.get("item_id") or "").strip() == item_id for failure in failures):
                continue
            failure = {field: row.get(field, "") for field in self.failure_fields}
            failure.update({
                "source_category": category,
                "failure_status": "pending",
                "failure_reason": reason,
                "attempt_count": 1,
                "last_failed_at": "",
            })
            failures.append(failure)

    def _rewrite_accepted(self, category: str) -> None:
        rows = self.accepted_rows.get(category, [])
        write_csv_atomic(self.output_dir / category / "products.csv", rows, self.clean_fields)

    def _rewrite_unprocessed(self) -> None:
        write_csv_atomic(self.output_dir / "unprocessed_samples.csv", self.unprocessed_rows, self.unprocessed_fields)

    def _rewrite_failures(self, category: str) -> None:
        rows = self.failure_rows.get(category, [])
        write_csv_atomic(self.output_dir / category / MODEL_FAILURE_FILE, rows, self.failure_fields)

    def _rewrite_existing(self) -> None:
        # 迁移旧版结果时同时把成功和失败图片收进对应输出目录。
        for category, rows in self.accepted_rows.items():
            for row in rows:
                row["local_image_path"] = copy_output_image(
                    row, self.output_dir / category / "images", root=self.root
                )
            self._rewrite_accepted(category)
        for category in self.failure_rows:
            self._rewrite_failures(category)
        failure_ids = {
            (row.get("item_id") or "").strip()
            for rows in self.failure_rows.values()
            for row in rows
            if (row.get("item_id") or "").strip()
        }
        for row in self.unprocessed_rows:
            item_id = (row.get("item_id") or "").strip()
            reason = str(row.get("reason") or "")
            # 只有模型正常返回但规则未通过的记录才复制到 failed_images。
            # 接口、解析或图片失败记录保留源路径，等待后续重试。
            if item_id not in failure_ids and not reason.startswith(("接口或解析失败", "图片文件不存在")):
                row["local_image_path"] = copy_output_image(
                    row, self.output_dir / "failed_images", root=self.root
                )
        # 即使当前没有失败记录，也先创建带表头的统一文件，便于流式运行时直接查看。
        self._rewrite_unprocessed()
        for legacy_name in ("review_candidates.csv", "excluded_samples.csv"):
            legacy_path = self.output_dir / legacy_name
            if legacy_path.exists():
                legacy_path.unlink()

    def item_ids(self) -> set[str]:
        item_ids: set[str] = set()
        for rows in self.accepted_rows.values():
            item_ids.update((row.get("item_id") or "").strip() for row in rows if (row.get("item_id") or "").strip())
        item_ids.update((row.get("item_id") or "").strip() for row in self.unprocessed_rows if (row.get("item_id") or "").strip())
        for rows in self.failure_rows.values():
            item_ids.update((row.get("item_id") or "").strip() for row in rows if (row.get("item_id") or "").strip())
        return item_ids

    def remove_item(self, item_id: str) -> set[str]:
        changed_categories: set[str] = set()
        if not item_id:
            return changed_categories
        for category, rows in self.accepted_rows.items():
            for row in rows:
                if (row.get("item_id") or "").strip() == item_id:
                    self._delete_managed_image(row.get("local_image_path", ""))
            filtered = [row for row in rows if (row.get("item_id") or "").strip() != item_id]
            if len(filtered) != len(rows):
                self.accepted_rows[category] = filtered
                changed_categories.add(category)
        for row in self.unprocessed_rows:
            if (row.get("item_id") or "").strip() == item_id:
                self._delete_managed_image(row.get("local_image_path", ""))
        self.unprocessed_rows = [
            row for row in self.unprocessed_rows
            if (row.get("item_id") or "").strip() != item_id
        ]
        return changed_categories

    def _clear_failure(self, item_id: str) -> None:
        if not item_id:
            return
        for category, rows in list(self.failure_rows.items()):
            for row in rows:
                if (row.get("item_id") or "").strip() == item_id:
                    self._delete_managed_image(row.get("local_image_path", ""))
            filtered = [row for row in rows if (row.get("item_id") or "").strip() != item_id]
            if len(filtered) == len(rows):
                continue
            self.failure_rows[category] = filtered
            self._rewrite_failures(category)

    def _record_failure(self, row: dict[str, str], result: dict[str, Any], image_path: str) -> None:
        category = str(row.get("_source_category") or "UNKNOWN")
        item_id = (row.get("item_id") or "").strip()
        existing_rows = self.failure_rows.setdefault(category, [])
        previous = next(
            (failure for failure in existing_rows if (failure.get("item_id") or "").strip() == item_id),
            None,
        )
        try:
            previous_attempts = int(previous.get("attempt_count") or 0) if previous else 0
        except (TypeError, ValueError):
            previous_attempts = 0
        attempt_count = previous_attempts + 1
        existing_rows[:] = [
            failure for failure in existing_rows
            if (failure.get("item_id") or "").strip() != item_id
        ]
        failure = {field: row.get(field, "") for field in self.failure_fields}
        failure.update({
            "source_category": category,
            "failure_status": "pending",
            "failure_reason": result.get("reason", ""),
            "attempt_count": attempt_count,
            "last_failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "local_image_path": image_path,
        })
        existing_rows.append(failure)
        self._rewrite_failures(category)

    def _delete_managed_image(self, raw_path: str) -> None:
        if not raw_path:
            return
        candidate = Path(str(raw_path).replace("\\", "/"))
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self.output_dir.resolve())
        except (OSError, ValueError):
            return
        if resolved.parent.name not in {"images", "failed_images"}:
            return
        if resolved.is_file():
            resolved.unlink()

    def write_result(self, row: dict[str, str], result: dict[str, Any]) -> None:
        item_id = (row.get("item_id") or "").strip()
        changed_categories = self.remove_item(item_id)
        for category in changed_categories:
            self._rewrite_accepted(category)
        status = result.get("status")
        accepted_result = status == "accepted" and result.get("product_type") in TARGET_TYPES
        run_status = "accepted" if accepted_result else ("excluded" if status == "excluded" else "review")
        source_category = str(row.get("_source_category") or "UNKNOWN")
        self.run_counts["input"] += 1
        self.run_counts[run_status] += 1
        category_counts = self.run_counts_by_category.setdefault(
            source_category, {"input": 0, "accepted": 0, "review": 0, "excluded": 0}
        )
        category_counts["input"] += 1
        category_counts[run_status] += 1
        result_is_readed = str(result.get("is_readed", "")).strip().lower() == "true"
        if result_is_readed:
            # 模型成功返回后，该记录不再属于待重试失败队列，即使规则结果是 review/excluded。
            self._clear_failure(item_id)
        if accepted_result:
            category = str(result["product_type"])
            accepted = build_output_row(row, result, self.clean_fields)
            accepted["local_image_path"] = copy_output_image(
                row, self.output_dir / category / "images", root=self.root
            )
            self.accepted_rows.setdefault(category, []).append(accepted)
            self._rewrite_accepted(category)
            return
        unprocessed = {field: row.get(field, "") for field in self.clean_fields}
        unprocessed.update({
            "source_category": row.get("_source_category", ""),
            "status": status if status in {"review", "excluded"} else "review",
            "reason": result.get("reason", ""),
            "model_product_type": result.get("product_type", ""),
            "model_type": result.get("type", ""),
            "model_color": result.get("color", ""),
            "model_material": result.get("material", ""),
            "confidence": result.get("confidence", 0.0),
        })
        if result_is_readed:
            # 模型正常返回但规则结果未通过，复制图片供人工复核。
            unprocessed["local_image_path"] = copy_output_image(
                row, self.output_dir / "failed_images", root=self.root
            )
        else:
            # 接口、解析或图片失败不复制到 failed_images，只进入失败队列重试。
            unprocessed["local_image_path"] = row.get("local_image_path", "")
        self.unprocessed_rows.append(unprocessed)
        self._rewrite_unprocessed()
        if not result_is_readed:
            self._record_failure(row, result, unprocessed["local_image_path"])

    def finalize(
        self,
        min_confidence: float,
        target_types: tuple[str, ...],
        pending_rows: Iterable[dict[str, str]] = (),
    ) -> dict[str, Any]:
        pending_rows = list(pending_rows)
        categories = list(dict.fromkeys([*target_types, *self.accepted_rows.keys()]))
        counts = {
            category: {"input": 0, "accepted": 0, "review": 0, "excluded": 0, "pending": 0}
            for category in categories
        }
        for category, rows in self.accepted_rows.items():
            counts.setdefault(category, {"input": 0, "accepted": 0, "review": 0, "excluded": 0, "pending": 0})
            counts[category]["input"] += len(rows)
            counts[category]["accepted"] += len(rows)
        for row in self.unprocessed_rows:
            category = (row.get("source_category") or "").strip() or "UNKNOWN"
            counts.setdefault(category, {"input": 0, "accepted": 0, "review": 0, "excluded": 0, "pending": 0})
            counts[category]["input"] += 1
            if row.get("status") == "excluded":
                counts[category]["excluded"] += 1
            else:
                counts[category]["review"] += 1
        pending_by_source_category: dict[str, int] = {}
        for row in pending_rows:
            category = (row.get("_source_category") or "").strip() or "UNKNOWN"
            counts.setdefault(category, {"input": 0, "accepted": 0, "review": 0, "excluded": 0, "pending": 0})
            counts[category]["input"] += 1
            counts[category]["pending"] += 1
            pending_by_source_category[category] = pending_by_source_category.get(category, 0) + 1
        summary_rows = [
            {"product_type": category, "input_count": values["input"],
             "accepted_count": values["accepted"], "review_count": values["review"],
             "excluded_count": values["excluded"], "pending_count": values["pending"],
             "min_confidence": min_confidence}
            for category, values in counts.items()
        ]
        write_csv_atomic(self.output_dir / "dataset_summary.csv", summary_rows,
                         ["product_type", "input_count", "accepted_count", "review_count",
                          "excluded_count", "pending_count", "min_confidence"])
        generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        report_path = self.output_dir / "cleaning_report.json"
        history = read_cleaning_report_history(report_path)
        pending_count = len(pending_rows)
        if self.run_counts["input"] or not history:
            history.append({
                "generated_at": generated_at,
                "input_rows": self.run_counts["input"] + pending_count,
                "processed_rows": self.run_counts["input"],
                "accepted_rows": self.run_counts["accepted"],
                "review_rows": self.run_counts["review"],
                "excluded_rows": self.run_counts["excluded"],
                "pending_rows": pending_count,
                "target_types": list(target_types),
                "min_confidence": min_confidence,
                "by_source_category": self.run_counts_by_category,
                "pending_by_source_category": pending_by_source_category,
            })
        report = {
            "report_version": 2,
            "generated_at": generated_at,
            "input_rows": sum(values["input"] for values in counts.values()),
            "accepted_rows": sum(len(rows) for rows in self.accepted_rows.values()),
            "review_rows": sum(1 for row in self.unprocessed_rows if row.get("status") != "excluded"),
            "excluded_rows": sum(1 for row in self.unprocessed_rows if row.get("status") == "excluded"),
            "pending_rows": pending_count,
            "target_types": list(target_types),
            "output_types": list(counts),
            "output_fields": self.clean_fields,
            "unprocessed_file": "unprocessed_samples.csv",
            "model_failure_file": f"<source_category>/{MODEL_FAILURE_FILE}",
            "failed_images_dir": "failed_images",
            "relative_image_paths": True,
            "input_read_field": {"name": "is_readed", "pending_value": "false", "model_success_value": "true"},
            "note": "通过记录逐条写入类别 products.csv 和 images/；模型正常返回但规则未通过的记录写入 unprocessed_samples.csv，并将能找到的图片复制到 failed_images/；接口、解析或图片失败记录写入 model_failures.csv，等待重试且不复制到 failed_images/；中断时 pending_rows 表示尚未完成模型处理的记录。",
            "runs": history,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report



def main() -> int:
    args = parse_args()
    root = repo_root()
    if not args.input_dir.is_absolute():
        args.input_dir = root / args.input_dir
    if not args.output_dir.is_absolute():
        args.output_dir = root / args.output_dir
    if args.append and args.clean_output:
        raise ValueError("--append 和 --clean-output 不能同时使用")
    output_has_content = args.output_dir.is_dir() and any(args.output_dir.iterdir())
    if output_has_content and not args.append and not args.force and not args.clean_output:
        raise FileExistsError(
            f"输出目录已有内容：{args.output_dir}。请明确选择 --append 增量追加、"
            "--force 重新处理，或 --clean-output 全量重建。"
        )
    if args.clean_output and args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    env = load_env(Path(__file__).resolve().parent / ".env")
    workers = args.workers or int(env_value(env, "MAX_WORKERS", "4"))
    if not env_value(env, "OPENAI_API_KEY"):
        print("警告：未读取到 OPENAI_API_KEY；若中转站不接受匿名请求，接口调用会失败。", file=sys.stderr)
    global TARGET_TYPES, SYSTEM_PROMPT
    requested_categories = [item.strip() for item in args.categories.replace("，", ",").split(",") if item.strip()]
    discovered_categories = [category for category, _ in input_csv_paths(args.input_dir)]
    TARGET_TYPES = tuple(dict.fromkeys(requested_categories or discovered_categories or TARGET_TYPES))
    if not TARGET_TYPES:
        raise FileNotFoundError(
            f"未发现可用类别：{args.input_dir} 下需要至少一个 <类别>/products.csv，或使用 --categories 指定类别"
        )
    SYSTEM_PROMPT = SYSTEM_PROMPT.replace("目标类别列表", "|".join(TARGET_TYPES))
    rows, fieldnames = load_rows(args.input_dir)
    unique_fields: list[str] = []
    for field in fieldnames:
        if field == "tpye" or field in unique_fields:
            continue
        unique_fields.append(field)
    if unique_fields != fieldnames:
        fieldnames = unique_fields
        for row in rows:
            row.pop("tpye", None)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    existing = load_existing_outputs(args.output_dir) if (args.append or args.force) else {
        "accepted": {}, "failures": {}, "unprocessed": [], "review": [], "excluded": []
    }
    stream_writer = StreamingOutputWriter(args.output_dir, fieldnames, existing, root=root)
    saved_item_ids = stream_writer.item_ids()
    audit_path = args.output_dir / "model_audit.jsonl"
    completed = read_audit(audit_path)
    pending = []
    for row in rows:
        item_id = (row.get("item_id") or "").strip()
        key = record_key(row["_source_category"], item_id)
        previous = completed.get(key)
        input_is_readed = str(row.get("is_readed", "")).strip().lower() in {"true", "1", "yes", "y", "是"}
        if input_is_readed:
            # is_readed 只负责决定是否调用模型；审计结果仅用于补回缺失的输出。
            if previous is not None and (not item_id or item_id not in saved_item_ids):
                stream_writer.write_result(row, previous)
            elif previous is None:
                print(
                    f"警告：{item_id} 的 is_readed=true，但 model_audit.jsonl 中没有对应结果；"
                    "跳过模型调用。",
                    file=sys.stderr,
                )
        else:
            # 只要源记录仍为 false，就必须调用模型；已有输出或旧审计不会阻止重试。
            pending.append(row)
    print(f"输入 {len(rows)} 条，已完成 {len(rows) - len(pending)} 条，待处理 {len(pending)} 条。")
    pending_by_key = {
        record_key(row["_source_category"], (row.get("item_id") or "").strip()): row
        for row in pending
    }
    append_mode = "a"
    interrupted = False
    try:
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
                        source_row = future_map[future]
                        result_is_readed = str(result.get("is_readed", "")).strip().lower() == "true"
                        if result_is_readed:
                            try:
                                mark_source_row_read(Path(source_row["_source_csv"]), result["item_id"])
                            except OSError as exc:
                                print(
                                    f"警告：无法更新 is_readed：{source_row['_source_csv']}：{exc}",
                                    file=sys.stderr,
                                )
                        stream_writer.write_result(source_row, result)
                        pending_by_key.pop(result["record_key"], None)
                        done += 1
                        print(f"[{done}/{len(pending)}] {result['item_id']} {result['status']} "
                              f"{result.get('product_type', '')} {result.get('reason', '')}")
    except KeyboardInterrupt:
        interrupted = True
        print("检测到手动中断，正在保存已经完成的结果和当前汇总……", file=sys.stderr)
    finally:
        # 正常完成和 Ctrl+C 都要落盘汇总；强制终止进程无法执行 finally。
        stream_writer.finalize(
            args.min_confidence,
            TARGET_TYPES,
            pending_rows=pending_by_key.values(),
        )
    if interrupted:
        print(
            f"已保存检查点：{args.output_dir}；仍有 {len(pending_by_key)} 条记录待下次运行。",
            file=sys.stderr,
        )
        return 130
    print(f"候选结果已写入：{args.output_dir}")
    print("请先核查各类别 products.csv 和 unprocessed_samples.csv，再决定是否覆盖正式数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
