"""路由层（Controller）：只做取参、校验、调服务、包统一返回体。

不写业务逻辑，不知道背后是占位还是 ONNX。
每个路由的 summary / description / response_model 都是给 /docs（Swagger UI）看的，
顺手把错误码表也塞进文档——报告"API 文档 / 异常处理说明"两节可以直接对着 /docs 写。
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from PIL import Image

from ..config import get_settings
from ..deps import get_match_service
from ..errors import ApiError, ErrorCode
from ..schemas import (
    ApiResponse,
    HealthResponse,
    ImageResponse,
    MatchResponse,
    TextQueryRequest,
    TextResponse,
)
from ..services.matching import MatchService

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

router = APIRouter(prefix="/api/v1")

_ALLOWED_FORMATS = {"PNG", "JPEG", "JPG", "WEBP"}

# 统一挂在每个路由上：让 /docs 的每个接口都列出可能的错误码（错误体也是 {code, result, msg}）
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {
        "model": ApiResponse,
        "description": "40000 参数错误 / 40001 图片格式错 / 40002 空上传 / "
        "40003 维度不一致 / 40004 文件过大",
    },
    404: {"model": ApiResponse, "description": "40401 类别不存在 / 40402 索引文件缺失"},
    500: {"model": ApiResponse, "description": "50000 未捕获异常 / 50001 模型或依赖不可用"},
}


def _decode_image(raw: bytes) -> tuple["PILImage", str]:
    """上传字节 -> (RGB 图片, 格式)；所有上传都从这里过，大小/格式校验也集中在这一道。"""
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
    image_format = (image.format or "").upper()
    if image_format not in _ALLOWED_FORMATS:
        raise ApiError(ErrorCode.INVALID_IMAGE, f"不支持 {image.format}")
    return image.convert("RGB"), "JPEG" if image_format == "JPG" else image_format


def _open_image(raw: bytes) -> "PILImage":
    """只要图片、不要格式的调用方（异步任务）走这个薄包装。"""
    return _decode_image(raw)[0]


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康检查",
    tags=["状态"],
    responses=_ERROR_RESPONSES,
    description="前端启动时先调这个探活。`model_loaded=false` 表示在跑占位编码器，"
    "链路通但检索结果无意义。",
)
def health(service: MatchService = Depends(get_match_service)) -> HealthResponse:
    result = service.status()
    result["backend"] = get_settings().model_backend
    return HealthResponse.ok(result)


@router.post(
    "/image",
    response_model=ImageResponse,
    summary="图像分类",
    tags=["图像分类页"],
    responses=_ERROR_RESPONSES,
    description="上传商品图 → 图像塔编码成 512 维向量 → 与全部可判类别比相似度 → "
    "返回最可能的类别、置信度与相似商品类别排序。",
)
async def classify_image(
    file: UploadFile = File(..., description="商品图（PNG/JPG/WEBP，≤10 MB）"),
    service: MatchService = Depends(get_match_service),
) -> ImageResponse:
    image = _open_image(await file.read())
    return ImageResponse.ok(service.classify_image(image))


@router.post(
    "/text",
    response_model=TextResponse,
    summary="文本检索",
    tags=["文本检索页"],
    responses=_ERROR_RESPONSES,
    description="中文查询 → 文本塔编码 → 在商品库里按余弦相似度取 top_k。"
    "`category` 留空表示搜全部类别；`query_category` 是文本塔独立判出的类别，"
    "不受 `category` 限定影响。两者不一致时视为没有交集，`items` 返回空数组。",
)
def search_text(
    payload: TextQueryRequest,
    service: MatchService = Depends(get_match_service),
) -> TextResponse:
    return TextResponse.ok(service.search_text(payload.query, payload.top_k, payload.category))


@router.post(
    "/match",
    response_model=MatchResponse,
    summary="图文匹配",
    tags=["多模态匹配页"],
    responses=_ERROR_RESPONSES,
    description="图与文**各自独立**编码、各自判类别，再比对两个类别是否一致；"
    "不用图像判出的类别去限定文本检索（那样比对恒为一致，等于循环论证）。",
)
async def multimodal_match(
    file: UploadFile = File(..., description="商品图"),
    text: str = Form(..., min_length=1, max_length=200, description="中文文本，如「白色运动鞋」"),
    top_k: int = Form(5, ge=1, le=50, description="返回的文本检索条数"),
    service: MatchService = Depends(get_match_service),
) -> MatchResponse:
    image = _open_image(await file.read())
    return MatchResponse.ok(service.match(image, text, top_k))
