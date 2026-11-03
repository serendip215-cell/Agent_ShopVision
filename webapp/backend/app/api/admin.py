"""数据入库路由：上传商品到已有/新类别，或只建一个空类别。

本轮未做管理鉴权：只允许本机演示，不要暴露到公网。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..deps import get_match_service
from ..schemas import (
    AdminCategoryRequest,
    AdminCategoryResponse,
    AdminItemResponse,
)
from ..services.matching import MatchService
from .v1 import _ERROR_RESPONSES, _decode_image

router = APIRouter(prefix="/api/v1/admin", tags=["数据入库"])


@router.post(
    "/items",
    response_model=AdminItemResponse,
    summary="上传商品入库",
    tags=["数据入库"],
    responses=_ERROR_RESPONSES,
    description="只传 `file` 时只返回建议类别，不写库；`confirm=true` 且带 `category` "
    "才真正入库。类别不存在时传 `create_category=true` 自动建类。"
    "同一张图重复上传返回已有条目（duplicate=true），不会重复计数。"
    "占位编码器下拒绝入库（50001）。",
)
async def ingest_item(
    file: UploadFile = File(..., description="商品图（PNG/JPG/WEBP，≤10 MB）"),
    category: str | None = Form(None, max_length=64, description="目标类别；为空时只返回建议"),
    confirm: bool = Form(False, description="true 才真正写库"),
    create_category: bool = Form(False, description="类别不存在时自动创建"),
    item_name: str | None = Form(None, max_length=200, description="商品标题"),
    item_type: str | None = Form(None, alias="type", max_length=100, description="细分类"),
    color: str | None = Form(None, max_length=50, description="颜色"),
    material: str | None = Form(None, max_length=50, description="材质"),
    brand: str | None = Form(None, max_length=100, description="品牌"),
    description: str | None = Form(None, max_length=1000, description="商品文案"),
    service: MatchService = Depends(get_match_service),
) -> AdminItemResponse:
    raw = await file.read()
    image, image_format = _decode_image(raw)
    metadata = {
        "item_name": item_name or "",
        "type": item_type or "",
        "color": color or "",
        "material": material or "",
        "brand": brand or "",
        "description": description or "",
    }
    result = service.ingest_item(
        image,
        raw,
        image_format,
        category=category,
        confirm=confirm,
        create_category=create_category,
        metadata=metadata,
    )
    return AdminItemResponse.ok(result)


@router.post(
    "/categories",
    response_model=AdminCategoryResponse,
    summary="新建空类别",
    tags=["数据入库"],
    responses=_ERROR_RESPONSES,
    description="只建类别、不写商品。空类别不会参与自动判类，"
    "但可以在检索页显式指定（结果为空）；上传首条商品后即参与判类。",
)
def create_category(
    payload: AdminCategoryRequest,
    service: MatchService = Depends(get_match_service),
) -> AdminCategoryResponse:
    return AdminCategoryResponse.ok(service.create_category(payload.name))
