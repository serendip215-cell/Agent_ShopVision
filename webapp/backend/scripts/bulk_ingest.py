"""把一整个图片目录批量导入增量库（与上传入库同一套编码与 SQLite 写入）。

目录里每个子目录名默认就是类别名；也可以整目录只导入一个类别：

    cd webapp/backend
    python scripts/bulk_ingest.py D:/新商品                 # 子目录名 = 类别名
    python scripts/bulk_ingest.py D:/新商品 --category 鞋    # 全部算「鞋」
    python scripts/bulk_ingest.py D:/新商品 --create-category --recursive

行为：
* 只收 PNG / JPG / WEBP，单张上限跟上传接口一致（SHOPVISION_MAX_UPLOAD_MB）。
* 图片原样落到 data/uploaded_data/<类别>/images/，SQLite 只存路径 + 512 维向量。
* 按图片 sha256 去重；同一张图重复导入只报「重复」，不重写。
* 新类别默认拒绝，显式加 --create-category 才建；导入完要重启后端才看得到新条目。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from app.api.v1 import _decode_image  # noqa: E402
from app.deps import get_encoder, get_index, get_upload_store  # noqa: E402
from app.errors import ApiError, ErrorCode  # noqa: E402
from app.services.upload_store import normalize_category  # noqa: E402

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def image_files(folder: Path, recursive: bool = False) -> list[Path]:
    pattern = folder.rglob("*") if recursive else folder.glob("*")
    return sorted(p for p in pattern if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES)


def collect_jobs(
    source: Path, category: str | None = None, recursive: bool = False
) -> list[tuple[str, Path]]:
    """返回 [(类别名, 图片路径)]；类别名尚未正规化，由调用方逐张校验。"""
    if category is not None:
        return [(category, path) for path in image_files(source, recursive)]
    jobs = [
        (child.name, path)
        for child in sorted(source.iterdir(), key=lambda p: p.name)
        if child.is_dir()
        for path in image_files(child, recursive)
    ]
    if not jobs and image_files(source):
        raise ValueError(f"{source} 根目录直接放了图片；用 --category 指定类别，或按类别建子目录")
    return jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量导入图片目录到增量库")
    parser.add_argument("source", help="图片目录")
    parser.add_argument("--category", help="整目录导入这一个类别；不填则子目录名即类别")
    parser.add_argument("--create-category", action="store_true", help="允许创建新类别")
    parser.add_argument("--recursive", action="store_true", help="递归进子目录找图片")
    args = parser.parse_args(argv)

    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        print(f"目录不存在：{source}")
        return 2
    try:
        jobs = collect_jobs(source, args.category, args.recursive)
    except ValueError as exc:
        print(exc)
        return 2
    if not jobs:
        print("没有找到 PNG / JPG / WEBP 图片")
        return 1

    encoder = get_encoder()
    if not encoder.model_loaded:
        print("占位编码器禁止入库；请在 .env 设 SHOPVISION_MODEL_BACKEND=onnx 后重跑")
        return 1
    store = get_upload_store()
    known = set(get_index().categories)

    created = duplicate = failed = 0
    for index, (raw_category, path) in enumerate(jobs, 1):
        label = f"[{index}/{len(jobs)}]"
        try:
            category = normalize_category(raw_category)
            if category not in known and not args.create_category:
                raise ApiError(
                    ErrorCode.CATEGORY_NOT_FOUND,
                    f"{category}（确认要新建的话加 --create-category）",
                )
            raw = path.read_bytes()
            image, image_format = _decode_image(raw)
            item, is_new = store.add_item(
                category=category,
                vector=encoder.encode_image(image),
                raw=raw,
                image_format=image_format,
                metadata={"item_name": path.stem, "product_type": category},
                image_width=image.width,
                image_height=image.height,
            )
        except (ApiError, OSError) as exc:
            failed += 1
            print(f"{label} 失败 {path.name}：{exc}")
            continue
        if is_new:
            created += 1
            known.add(category)
            print(f"{label} 新增 {item['item_id']} ← {category}/{path.name}")
        else:
            duplicate += 1
            print(
                f"{label} 重复 {path.name}"
                f"（已在「{item.get('category')}」，item_id={item.get('item_id')}）"
            )

    print(f"\n完成：新增 {created}，重复 {duplicate}，失败 {failed}，共 {len(jobs)} 张")
    if created:
        print("提示：正在运行的后端有独立缓存，重启 uvicorn 后 /health 与检索才会看到新条目。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
