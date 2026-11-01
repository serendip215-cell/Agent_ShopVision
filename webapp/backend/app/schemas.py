"""请求体与统一返回体。前端只认一种返回形状：{code, result, msg}。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 0
    result: Any = None
    msg: str = "ok"

    @classmethod
    def ok(cls, result: Any, msg: str = "ok") -> "ApiResponse":
        return cls(code=0, result=result, msg=msg)


class TextQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200, description="中文查询词")
    top_k: int = Field(default=5, ge=1, le=50)
    category: str | None = Field(default=None, description="限定类别，留空搜全部")
