"""对话导购接口：POST /api/v1/agent/chat。

只做取参、校验、调服务、包统一返回体；业务全在 services/agent_service.py。
前端契约见 webapp/backend/README-agent-chat.md（前端已按此冻结）。

错误码约定：**不要用 404xx**——前端把 `404` 开头的 code 一律显示成「对话接口尚未上线」，
参数问题走 40000，模型/依赖不可用走 50001。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_agent_service
from ..schemas import AgentChatRequest, AgentChatResponse
from ..services.agent_service import AgentService
from .v1 import _ERROR_RESPONSES

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
