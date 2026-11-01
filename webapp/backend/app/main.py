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
from .errors import ApiError
from .schemas import ApiResponse


def _error(status: int, msg: str) -> JSONResponse:
    """错误也走统一返回体，HTTP 状态码与 body 里的 code 一致。"""
    return JSONResponse(status_code=status, content=ApiResponse(code=status, msg=msg).model_dump())


def _register_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.code, exc.msg)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []))
        return _error(400, f"参数错误：{field} {first.get('msg', '')}".strip())

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return _error(500, f"服务器错误：{type(exc).__name__}: {exc}")


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