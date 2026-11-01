"""路由层（Controller）：只做取参、校验、调服务、包统一返回体。

不写业务逻辑，不知道背后是占位还是 ONNX。
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, File, Form, UploadFile
from PIL import Image

from ..config import get_settings
from ..deps import get_match_service
from ..errors import ApiError, ErrorCode
from ..schemas import ApiResponse, TextQueryRequest
from ..services.matching import MatchService

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

router = APIRouter(prefix="/api/v1")

_ALLOWED_FORMATS = {"PNG", "JPEG", "JPG", "WEBP"}


def _open_image(raw: bytes) -> "PILImage":
    """上传字节 -> RGB 图片；所有上传都从这里过，大小/格式校验也集中在这一道。"""
    limit = get_settings().max_upload_mb * 1024 * 1024
    if len(raw) > limit:
        raise ApiError(ErrorCode.FILE_TOO_LARGE, f"上限 {get_settings().max_upload_mb} MB")
    if not raw:
        raise ApiError(ErrorCode.EMPTY_UPLOAD)
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:  # noqa: BLE001 - 任何解析失败都归为格式错误
        raise ApiError(ErrorCode.INVALID_IMAGE, f"无法解析：{type(exc).__name__}") from exc
    if (image.format or "").upper() not in _ALLOWED_FORMATS:
        raise ApiError(ErrorCode.INVALID_IMAGE, f"不支持 {image.format}")
    return image.convert("RGB")


@router.get("/health", response_model=ApiResponse, summary="健康检查")
def health(service: MatchService = Depends(get_match_service)) -> ApiResponse:
    result = service.status()
    result["backend"] = get_settings().model_backend
    return ApiResponse.ok(result)


@router.post("/image", response_model=ApiResponse, summary="图像分类")
async def classify_image(
    file: UploadFile = File(..., description="商品图，multipart/form-data"),
    service: MatchService = Depends(get_match_service),
) -> ApiResponse:
    image = _open_image(await file.read())
    return ApiResponse.ok(service.classify_image(image))


@router.post("/text", response_model=ApiResponse, summary="文本检索")
def search_text(
    payload: TextQueryRequest,
    service: MatchService = Depends(get_match_service),
) -> ApiResponse:
    return ApiResponse.ok(
        service.search_text(payload.query, payload.top_k, payload.category)
    )


@router.post("/match", response_model=ApiResponse, summary="图文匹配")
async def multimodal_match(
    file: UploadFile = File(..., description="商品图"),
    text: str = Form(..., min_length=1, max_length=200),
    top_k: int = Form(5, ge=1, le=50),
    service: MatchService = Depends(get_match_service),
) -> ApiResponse:
    image = _open_image(await file.read())
    return ApiResponse.ok(service.match(image, text, top_k))