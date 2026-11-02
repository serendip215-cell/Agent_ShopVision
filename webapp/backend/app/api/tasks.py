"""异步任务路由：提交单张/批量分类任务，轮询任务状态。

只有异步路径依赖 Celery + Redis；同步的 /image /text /match 不受影响。
Redis 不可用时提交接口返回 50001 并给出可操作的提示，服务本身照常可用。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from celery.result import AsyncResult, EagerResult
from fastapi import APIRouter, File, UploadFile

from ..celery_app import celery_app
from ..config import get_settings
from ..errors import ApiError, ErrorCode
from ..schemas import TaskStatusResponse, TaskSubmitResponse
from ..tasks import classify_image_file, classify_images_batch
from .v1 import _open_image

router = APIRouter(prefix="/api/v1/tasks", tags=["异步任务"])

# eager 模式（测试/无 Redis 冒烟）下 Celery 不落 backend，自己存一份结果。
# 不做淘汰：eager 只在测试里用，淘汰会让已完成任务被误报成 PENDING。
_EAGER_RESULTS: dict[str, EagerResult] = {}

_TASK_ERROR_HINT = "任务队列不可用：请确认 SHOPVISION_CELERY_BROKER_URL 指向的 Redis 可达"


def _temp_dir() -> Path:
    path = Path(tempfile.gettempdir()) / "shopvision-tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_upload(file: UploadFile, raw: bytes) -> Path:
    suffix = Path(file.filename or "upload").suffix or ".png"
    handle, name = tempfile.mkstemp(prefix="shopvision-", suffix=suffix, dir=_temp_dir())
    with os.fdopen(handle, "wb") as stream:
        stream.write(raw)
    return Path(name)


def _remember_eager(result: EagerResult) -> None:
    _EAGER_RESULTS[result.id] = result


def _enqueue(task: Any, *args: Any) -> Any:
    try:
        return task.delay(*args)
    except Exception as exc:  # noqa: BLE001 - 连接类异常统一转业务错误
        raise ApiError(ErrorCode.MODEL_UNAVAILABLE, _TASK_ERROR_HINT) from exc


@router.post(
    "/image",
    response_model=TaskSubmitResponse,
    summary="提交单张图片异步分类",
    description="大图或需要立即返回的场景用这个：提交后拿 task_id，再轮询 "
    "GET /api/v1/tasks/{task_id}。校验（格式/大小）仍在这里做，错误立即返回。",
)
async def submit_image_task(
    file: UploadFile = File(..., description="商品图（PNG/JPG/WEBP，≤10 MB）"),
) -> TaskSubmitResponse:
    raw = await file.read()
    _open_image(raw)  # 提交前先校验，坏图不入队
    path = _save_upload(file, raw)
    try:
        task = _enqueue(classify_image_file, str(path))
    except ApiError:
        path.unlink(missing_ok=True)  # 入队失败别把临时文件留在盘上
        raise
    if get_settings().celery_always_eager:
        _remember_eager(task)
    return TaskSubmitResponse.ok({"task_id": task.id, "status": "PENDING", "total": None})


@router.post(
    "/batch",
    response_model=TaskSubmitResponse,
    summary="提交批量图片异步分类",
    description="一次提交多张图，worker 串行处理并上报进度。"
    "单批上限见 SHOPVISION_ASYNC_BATCH_MAX_FILES（默认 12）。",
)
async def submit_batch_task(
    files: list[UploadFile] = File(..., description="多张商品图"),
) -> TaskSubmitResponse:
    limit = get_settings().async_batch_max_files
    if not files:
        raise ApiError(ErrorCode.EMPTY_UPLOAD)
    if len(files) > limit:
        raise ApiError(ErrorCode.BAD_REQUEST, f"单批最多 {limit} 张")

    paths: list[str] = []
    entries: list[dict[str, str]] = []
    try:
        for upload in files:
            raw = await upload.read()
            _open_image(raw)  # 任意一张不过校验就整批拒绝，避免半路失败
            path = _save_upload(upload, raw)
            paths.append(str(path))
            entries.append({"path": str(path), "name": upload.filename or path.name})
    except ApiError:
        for saved in paths:  # 校验失败时清掉已经落盘的临时文件
            Path(saved).unlink(missing_ok=True)
        raise

    try:
        task = _enqueue(classify_images_batch, entries)
    except ApiError:
        for saved in paths:  # 入队失败同样要清掉临时文件
            Path(saved).unlink(missing_ok=True)
        raise
    if get_settings().celery_always_eager:
        _remember_eager(task)
    return TaskSubmitResponse.ok({"task_id": task.id, "status": "PENDING", "total": len(paths)})


@router.get(
    "/{task_id}",
    response_model=TaskStatusResponse,
    summary="轮询任务状态",
    description="前端约每 800ms 轮询一次。PENDING/PROGRESS 时继续轮询；SUCCESS 拿结果；"
    "FAILURE 看 error。注意：不存在的 task_id 也会返回 PENDING（Celery 的语义）。",
)
def task_status(task_id: str) -> TaskStatusResponse:
    payload: dict[str, Any] = {"task_id": task_id, "status": "PENDING"}
    try:
        if get_settings().celery_always_eager:
            # eager 模式没有 backend 可查，只认进程内记下的结果；未知 id 按 Celery 语义算排队中
            result = _EAGER_RESULTS.get(task_id)
            if result is None:
                return TaskStatusResponse.ok(payload)
        else:
            result = AsyncResult(task_id, app=celery_app)
        state = result.state
        payload["status"] = _map_state(state)
        if state == "PROGRESS" and isinstance(result.info, dict):
            payload["progress"] = {
                "done": int(result.info.get("done", 0)),
                "total": int(result.info.get("total", 0)),
            }
        elif state == "SUCCESS":
            returned = result.result
            # 任务内部把业务错误当返回值（code != 0）而不是抛异常，这里要还原成 FAILURE，
            # 否则前端拿到 SUCCESS + result=null，分不清“没结果”和“出错了”
            if isinstance(returned, dict) and returned.get("code"):
                payload["status"] = "FAILURE"
                payload["error"] = {
                    "code": int(returned["code"]),
                    "msg": returned.get("msg") or ErrorCode.INTERNAL_ERROR.message,
                }
            else:
                payload["result"] = (
                    returned.get("result") if isinstance(returned, dict) else returned
                )
        elif state == "FAILURE":
            payload["error"] = {
                "code": int(ErrorCode.INTERNAL_ERROR),
                "msg": ErrorCode.INTERNAL_ERROR.message,
            }
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - Redis/backend 不可达
        raise ApiError(ErrorCode.MODEL_UNAVAILABLE, _TASK_ERROR_HINT) from exc
    return TaskStatusResponse.ok(payload)


def _map_state(state: str) -> str:
    if state in ("STARTED", "PROGRESS"):
        return "PROGRESS"
    if state in ("SUCCESS", "FAILURE"):
        return state
    return "PENDING"
