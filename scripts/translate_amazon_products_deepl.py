#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用 DeepL API 翻译 Amazon 商品 CSV。

本脚本只服务于 Amazon 数据的中文化，不是其他数据集的通用翻译器。
它固定处理 Amazon 表中的五个文本字段：product_type、item_name、brand、color、material；
输入和输出路径通过命令行传入，原始 Amazon CSV、图片和 image_quality_report.csv 都不会修改。
翻译结果仍保留 Amazon 原始 CSV 的全部字段和顺序，供后续 MUGE 字段统一步骤使用。

示例：
    python scripts/translate_amazon_products_deepl.py \
        --input-file data/raw_data/Amazon_data/products.csv \
        --output-file data/raw_data/Amazon_data_translated/products.csv

API Key 从环境变量 DEEPL_API_KEY 读取，不要写入代码或 CSV。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AMAZON_TRANSLATION_FIELDS = ["product_type", "item_name", "brand", "color", "material"]
DEFAULT_API_KEY_ENV = "DEEPL_API_KEY"

# 当前 Amazon_data 中四个类别的固定中文译法；不代表其他数据集的类别映射。
KNOWN_PRODUCT_TYPE_MAP = {
    "CELLULAR_PHONE_CASE": "手机壳",
    "KITCHEN": "厨房用品",
    "SHOES": "鞋",
    "HOME": "家居用品",
}

FIELD_CONTEXT = {
    "product_type": "这是电商商品的类别，只翻译成简洁明确的中文类别词，不加入品牌、颜色、材质、尺寸或营销词。",
    "item_name": "这是电商商品标题。翻译为自然、简洁的中文标题，保留型号、品牌和原文明确的商品属性，不补写事实。",
    "brand": "这是商品品牌。优先保留官方品牌拼写；只有存在稳定公认的中文品牌名时才使用中文。",
    "color": "这是商品颜色。翻译为简洁的中文颜色词，多个颜色使用“、”分隔。",
    "material": "这是商品材质。翻译为简洁的中文材质名，多个材质使用“、”分隔。",
}


def clean_text(value: object) -> str:
    return str(value or "").replace("\ufeff", "").strip()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """读取 Amazon 商品表，并保留输入表头顺序；兼容常见中文 CSV 编码。"""
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                fields = [clean_text(field) for field in (reader.fieldnames or [])]
                if not fields:
                    raise ValueError(f"CSV 没有表头：{path}")
                rows = [
                    {field: clean_text(raw_row.get(field, "")) for field in fields}
                    for raw_row in reader
                ]
                return fields, rows
        except UnicodeDecodeError as error:
            last_error = error
    raise RuntimeError(f"无法读取 CSV 编码：{path}") from last_error


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    """以 UTF-8 BOM 写出结果，方便 Excel 打开中文；字段顺序由输入表头决定。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_audit(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_latest_audit(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return latest
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            item_id = clean_text(record.get("item_id", ""))
            if item_id:
                latest[item_id] = record
    return latest


def resolve_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def parse_inline_map(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in value.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"类别映射格式错误：{pair}，应为 原类别=中文类别")
        source, target = pair.split("=", 1)
        result[clean_text(source).upper()] = clean_text(target)
    return result


def load_category_map(path: Path | None, inline: str) -> dict[str, str]:
    result = dict(KNOWN_PRODUCT_TYPE_MAP)
    if path:
        if not path.is_file():
            raise FileNotFoundError(f"找不到类别映射文件：{path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("类别映射文件必须是 JSON 对象，例如 {\"SHOES\": \"鞋\"}")
        result.update({clean_text(k).upper(): clean_text(v) for k, v in data.items()})
    result.update(parse_inline_map(inline))
    return result


def load_deepl_client(api_key_env: str) -> Any:
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(
            f"没有找到环境变量 {api_key_env}。请先在 PowerShell 执行："
            f' $env:{api_key_env}="你的 API Key"'
        )
    try:
        import deepl
    except ImportError as error:
        raise RuntimeError("缺少 DeepL Python SDK，请先执行：python -m pip install deepl") from error
    # 官方 SDK 会根据 API Key 自动选择对应的 API 地址。
    return deepl.DeepLClient(api_key)


def translate_batch(
    client: Any,
    texts: list[str],
    field: str,
    target_lang: str,
    source_lang: str | None,
    batch_size: int,
    max_retries: int,
) -> dict[str, str]:
    """按字段批量翻译去重后的文本，并返回原文到译文的映射。"""

    unique_texts = list(dict.fromkeys(texts))
    result: dict[str, str] = {}
    context = FIELD_CONTEXT.get(field, "这是电商商品字段，请准确翻译为简体中文，不要补写事实。")
    for start in range(0, len(unique_texts), batch_size):
        batch = unique_texts[start : start + batch_size]
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "target_lang": target_lang,
                    "context": context,
                }
                if source_lang:
                    kwargs["source_lang"] = source_lang
                translated = client.translate_text(batch, **kwargs)
                values = translated if isinstance(translated, list) else [translated]
                if len(values) != len(batch):
                    raise RuntimeError("DeepL 返回数量与输入数量不一致")
                for source, value in zip(batch, values):
                    text = clean_text(getattr(value, "text", ""))
                    if not text:
                        raise RuntimeError(f"DeepL 返回空译文，字段：{field}")
                    result[source] = text
                print(f"  {field}: 已翻译 {min(start + len(batch), len(unique_texts))}/{len(unique_texts)} 条")
                break
            except Exception as error:  # SDK 的异常类型随版本变化，统一做重试。
                last_error = error
                if attempt >= max_retries:
                    break
                wait_seconds = min(2**attempt, 8)
                print(f"  {field}: 第 {attempt + 1} 次失败，{wait_seconds} 秒后重试：{error}", file=sys.stderr)
                time.sleep(wait_seconds)
        if last_error is not None and any(source not in result for source in batch):
            raise RuntimeError(f"DeepL 批量翻译失败（字段 {field}）：{last_error}")
    return result


def translate_file(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    input_file = resolve_path(args.input_file, repo_root).resolve()
    output_file = resolve_path(args.output_file, repo_root).resolve()
    audit_file = resolve_path(args.audit_file, repo_root).resolve() if args.audit_file else output_file.with_name("translation_audit.jsonl")
    # 不提供通用 --fields 参数：本入口只允许翻译 Amazon 的五个文本字段。
    fields_to_translate = AMAZON_TRANSLATION_FIELDS
    category_map = load_category_map(
        resolve_path(args.category_map_file, repo_root).resolve() if args.category_map_file else None,
        args.product_type_map,
    )

    if input_file == output_file:
        raise ValueError("输入和输出不能是同一个文件；Amazon 原始 products.csv 不允许被覆盖")
    if not input_file.is_file():
        raise FileNotFoundError(f"找不到输入 CSV：{input_file}")
    input_fields, input_rows = read_csv(input_file)
    required = ["item_id", *fields_to_translate]
    missing = [field for field in required if field not in input_fields]
    if missing:
        raise ValueError(f"输入 CSV 缺少字段：{', '.join(missing)}")
    if not input_rows:
        raise ValueError(f"输入 CSV 没有商品记录：{input_file}")

    existing_by_id: dict[str, dict[str, str]] = {}
    if output_file.is_file() and not args.no_resume:
        output_fields, output_rows = read_csv(output_file)
        if output_fields != input_fields:
            raise ValueError("已有输出文件字段与输入不一致，请更换输出路径或使用 --no-resume")
        existing_by_id = {
            clean_text(row.get("item_id", "")): row
            for row in output_rows
            if clean_text(row.get("item_id", ""))
        }
    latest_audit = {} if args.no_resume else read_latest_audit(audit_file)

    # 先复制所有 Amazon 原始列，再只替换五个文本字段，避免丢失来源字段。
    output_rows: list[dict[str, str]] = []
    pending_ids: list[str] = []
    seen_item_ids: set[str] = set()
    for source_row in input_rows:
        item_id = clean_text(source_row.get("item_id", ""))
        if not item_id:
            raise ValueError("输入 CSV 存在空的 item_id")
        if item_id in seen_item_ids:
            raise ValueError(f"输入 CSV 存在重复的 item_id：{item_id}")
        seen_item_ids.add(item_id)
        row = dict(source_row)
        previous = existing_by_id.get(item_id)
        audit_record = latest_audit.get(item_id, {})
        resume_ok = (
            audit_record.get("status") == "ok"
            and audit_record.get("dataset") == "Amazon_data"
            and audit_record.get("provider") == "deepl"
        )
        if previous and resume_ok:
            # 只复用本脚本产生的成功记录，避免把历史 Ollama 审计误当成 DeepL 结果。
            row.update({field: clean_text(previous.get(field, row.get(field, ""))) for field in input_fields})
        else:
            # 待处理记录先清空翻译字段；非翻译字段仍来自本次输入文件。
            for field in fields_to_translate:
                row[field] = ""
            pending_ids.append(item_id)
        output_rows.append(row)

    input_by_id = {clean_text(row["item_id"]): row for row in input_rows}
    output_by_id = {clean_text(row["item_id"]): row for row in output_rows}

    if not pending_ids:
        print("没有待翻译记录，输出文件已经是最新状态。")
        return 0

    client = load_deepl_client(args.api_key_env)
    try:
        for field in fields_to_translate:
            # 已有明确词典的 product_type 不消耗 API 额度；未知类别才交给 DeepL。
            source_values: list[str] = []
            for item_id in pending_ids:
                row = output_by_id[item_id]
                source_value = clean_text(input_by_id[item_id].get(field, ""))
                if not source_value:
                    continue
                if field == "product_type" and source_value.upper() in category_map:
                    row[field] = category_map[source_value.upper()]
                else:
                    source_values.append(source_value)
            if source_values:
                translated_map = translate_batch(
                    client,
                    source_values,
                    field,
                    args.target_lang,
                    args.source_lang or None,
                    args.batch_size,
                    args.max_retries,
                )
                for item_id in pending_ids:
                    row = output_by_id[item_id]
                    source_value = clean_text(input_by_id[item_id].get(field, ""))
                    if source_value and not (field == "product_type" and source_value.upper() in category_map):
                        row[field] = translated_map[source_value]
            # 每个字段完成后保存一次，长任务中断时仍能保留已完成的字段批次。
            write_csv(output_file, input_fields, output_rows)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    timestamp = datetime.now(timezone.utc).isoformat()
    pending_id_set = set(pending_ids)
    for index, source_row in enumerate(input_rows, start=1):
        item_id = clean_text(source_row["item_id"])
        if item_id in pending_id_set:
            append_audit(
                audit_file,
                {
                    "time": timestamp,
                    "item_id": item_id,
                    "row_number": index,
                    "status": "ok",
                    "dataset": "Amazon_data",
                    "provider": "deepl",
                    "fields": AMAZON_TRANSLATION_FIELDS,
                },
            )
    write_csv(output_file, input_fields, output_rows)
    print(f"完成：翻译 {len(pending_ids)} 条 Amazon 商品记录")
    print(f"翻译结果：{output_file}")
    print(f"审计记录：{audit_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="使用 DeepL API 翻译 Amazon 商品 CSV")
    parser.add_argument("--input-file", required=True, help="Amazon 原始 products.csv")
    parser.add_argument("--output-file", required=True, help="Amazon 中文翻译结果 CSV，不覆盖输入")
    parser.add_argument("--audit-file", default=None, help="审计 JSONL，默认写入输出目录")
    parser.add_argument("--category-map-file", default=None, help="Amazon 类别映射 JSON 文件，可覆盖内置映射")
    parser.add_argument("--product-type-map", default="", help="额外 Amazon 类别映射，例如 SHOES=鞋,KITCHEN=厨房用品")
    parser.add_argument("--source-lang", default=None, help="源语言代码；不填写则自动检测")
    parser.add_argument("--target-lang", default="ZH", help="目标语言代码，默认 ZH")
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV, help="API Key 环境变量名")
    parser.add_argument("--batch-size", type=int, default=50, help="每批文本数量，默认 50")
    parser.add_argument("--max-retries", type=int, default=2, help="批量失败后的重试次数")
    parser.add_argument("--repo-root", default=None, help="项目根目录")
    parser.add_argument("--no-resume", action="store_true", help="忽略已有输出和审计记录，从头翻译")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.batch_size <= 0 or args.max_retries < 0:
        raise SystemExit("--batch-size 必须大于 0，--max-retries 不能小于 0")
    try:
        return translate_file(args)
    except KeyboardInterrupt:
        print("已中断；已完成的批次保存在输出 CSV 中。", file=sys.stderr)
        return 130
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
