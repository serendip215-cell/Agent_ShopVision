"""对话导购接口：POST /api/v1/agent/chat。

只做取参、校验、调服务、包统一返回体；业务全在 services/agent_service.py。
前端契约见 webapp/backend/README-agent-chat.md（前端已按此冻结）。

错误码约定：**不要用 404xx**——前端把 `404` 开头的 code 一律显示成「对话接口尚未上线」，
参数问题走 40000，模型/依赖不可用走 50001。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..deps import get_agent_service
from ..schemas import AgentChatRequest, AgentChatResponse, AgentImageResponse
from ..services.agent_service import AgentService
from .v1 import _ERROR_RESPONSES, _open_image

router = APIRouter(prefix="/api/v1", tags=["对话导购页"])


@router.post(
    "/agent/chat",
    response_model=AgentChatResponse,
    summary="对话导购",
    tags=["对话导购页"],
    responses=_ERROR_RESPONSES,
    description=(
        "一句话需求 → 意图解析（Qwen3-4B + LoRA，不可用时自动降级规则解析）"
        "→ 调 text_search 检索 → 模板化回复。\n\n"
        "`reply` 中的商品信息全部来自 `/api/v1/text` 的真实返回，模型只输出工具调用参数，"
        "不生成商品内容；`thinking` 会注明本轮是微调模型还是规则降级。"
    ),
)
def agent_chat(
    payload: AgentChatRequest,
    service: AgentService = Depends(get_agent_service),
) -> AgentChatResponse:
    return AgentChatResponse.ok(service.chat(payload.message))


@router.post(
    "/agent/image",
    response_model=AgentImageResponse,
    summary="以图搜图",
    tags=["对话导购页"],
    responses=_ERROR_RESPONSES,
    description=(
        "上传商品图 → 图像塔编码 → 与 9 类索引比对，返回相似商品。\n\n"
        "`message` 非空时做**向量融合**：`q = α·图像向量 + (1−α)·文本向量`，"
        "α 默认 0.6；融合后重新 L2 归一化再检索。\n\n"
        "`thinking` 会列出图像塔、文本塔与融合系数，便于报告核对口径。"
    ),
)
async def agent_image(
    file: UploadFile = File(..., description="商品图（PNG/JPG/WEBP，≤10 MB）"),
    message: str = Form("", max_length=200, description="可选文字描述，参与向量融合"),
    alpha: float = Form(0.6, ge=0.0, le=1.0, description="图像权重（0=纯文字，1=纯图像）"),
    top_k: int = Form(5, ge=1, le=50, description="返回相似商品条数"),
    service: AgentService = Depends(get_agent_service),
) -> AgentImageResponse:
    image = _open_image(await file.read())
    return AgentImageResponse.ok(service.search_by_image(image, message, alpha, top_k))
