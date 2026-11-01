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
    """上传字节 -> RGB 图片；格式不对抛 400，前端拿到的 msg 可直接展示。"""
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
    settings = get_settings()
    return ApiResponse.ok(
        {
            "model_loaded": service.encoder.model_loaded,
            "backend": settings.model_backend,
            "index_dir": str(settings.index_path),
            "categories": service.index.categories,
            "dimension": service.index.dimension,
        }
    )


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