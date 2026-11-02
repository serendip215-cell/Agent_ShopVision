"""Celery 任务：从临时文件读图 → 调 MatchService → 返回可 JSON 序列化的结果。

图片字节不经过 broker（10 MB 级 blob 塞消息队列很浪费）：api 层先把上传写到
临时文件，任务只拿路径，处理完在 finally 里删掉。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PIL import Image

from .celery_app import celery_app
from .config import get_settings
from .deps import get_match_service
from .errors import ApiError, ErrorCode

logger = logging.getLogger("shopvision.tasks")


def _load_image(path: Path) -> Image.Image:
    try:
        image = Image.open(path)
        image.load()
    except Exception as exc:  # noqa: BLE001 - 任何解析失败都归为格式错误
        raise ApiError(ErrorCode.INVALID_IMAGE, f"无法解析：{type(exc).__name__}") from exc
    return image.convert("RGB")


def _classify_one(path_str: str) -> dict[str, Any]:
    """单张图分类，返回 {code, result, msg}；错误按业务码返回而不是抛。"""
    path = Path(path_str)
    try:
        if not path.is_file():
            raise ApiError(ErrorCode.NOT_FOUND, "临时文件已不存在")
        result = get_match_service().classify_image(_load_image(path))
        return {"code": 0, "result": result, "msg": "ok"}
    except ApiError as exc:
        return {"code": int(exc.code), "result": None, "msg": exc.msg}
    except Exception:  # noqa: BLE001 - 未捕获异常只回通用文案
        logger.exception("异步分类任务失败：%s", path.name)
        return {
            "code": int(ErrorCode.INTERNAL_ERROR),
            "result": None,
            "msg": ErrorCode.INTERNAL_ERROR.message,
        }


@celery_app.task(name="app.tasks.classify_image_file")
def classify_image_file(path_str: str) -> dict[str, Any]:
    """单张大图异步分类；临时文件无论成败都删除。"""
    try:
        return _classify_one(path_str)
    finally:
        Path(path_str).unlink(missing_ok=True)


@celery_app.task(bind=True, name="app.tasks.classify_images_batch")
def classify_images_batch(self: Any, entries: list[dict[str, str]]) -> dict[str, Any]:
    """批量分类；entries 为 [{path, name}]，name 是用户上传时的原始文件名。

    每张完成后上报进度，前端轮询读取；文件名回传给前端做缩略图对应。
    """
    total = len(entries)
    items: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, 1):
        try:
            outcome = _classify_one(entry["path"])
        finally:
            Path(entry["path"]).unlink(missing_ok=True)
        # 处理完再报进度，done 才代表“已完成”而不是“正在做第几张”
        if not get_settings().celery_always_eager:
            self.update_state(state="PROGRESS", meta={"done": index, "total": total})
        items.append({**outcome, "file_name": entry["name"]})
    return {"code": 0, "result": items, "msg": "ok"}
