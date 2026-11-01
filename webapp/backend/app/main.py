"""FastAPI 入口：装配路由、CORS、全局异常处理。

启动：uvicorn app.main:app --reload --port 8000
文档：http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import v1
from .config import get_settings
from .errors import ApiError, ErrorCode
from .schemas import ApiResponse


def _body(code: ErrorCode, msg: str) -> JSONResponse:
    """所有响应（含错误）都是 {code, result, msg}；HTTP 状态码取自业务码前三位。"""
    return JSONResponse(
        status_code=code.http_status,
        content=ApiResponse(code=int(code), msg=msg).model_dump(),
    )


def _register_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=ApiResponse(code=int(exc.code), msg=exc.msg).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return _body(ErrorCode.BAD_REQUEST, f"{field} {first.get('msg', '')}".strip())

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            code = ErrorCode.NOT_FOUND
        elif exc.status_code >= 500:
            code = ErrorCode.INTERNAL_ERROR
        else:
            code = ErrorCode.BAD_REQUEST
        return _body(code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return _body(ErrorCode.INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Agent ShopVision API",
        version="0.1.0",
        description="实验四后端：电商商品图文检索服务（集成实验三优化模型）。",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(v1.router)
    _register_handlers(app)

    @app.get("/", include_in_schema=False)
    def root() -> ApiResponse:
        return ApiResponse.ok({"docs": "/docs", "health": "/api/v1/health"})

    return app


app = create_app()