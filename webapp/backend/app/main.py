"""FastAPI 入口：装配路由、CORS、全局异常处理。

启动：uvicorn app.main:app --reload --port 8000
文档（FastAPI 内置，等价于 Java 的 springdoc/knife4j）：
    http://localhost:8000/docs        Swagger UI，可直接发请求试
    http://localhost:8000/redoc       ReDoc，适合当阅读版
    http://localhost:8000/openapi.json  机器可读的 OpenAPI 3，可导出给报告/Postman
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import v1
from .config import REPO_ROOT, get_settings
from .errors import ApiError, ErrorCode
from .schemas import ApiResponse

logger = logging.getLogger("shopvision.api")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_IMAGES_DIR = REPO_ROOT / "data" / "processed_data_cleaning"

_DESCRIPTION = """实验四后端：电商商品图文检索服务，集成实验三优化后的 Chinese-CLIP 双塔（ONNX）。

所有接口统一返回 `{code, result, msg}`：`code=0` 为成功，非 0 为错误码，且**前三位就是 HTTP 状态码**
（`40001` → 400、`40401` → 404、`50001` → 500）。完整码表见仓库 `webapp/API约定.md`。

- Swagger UI：`/docs`（本页，可直接发请求试接口）
- ReDoc：`/redoc`（阅读版）
- OpenAPI JSON：`/openapi.json`（可导出，供 API 文档或 Postman 使用）
"""

# tags 与前端页面一一对应，评审/报告里指哪打哪
_TAGS_META = [
    {"name": "状态", "description": "探活与索引概况，前端启动时先调"},
    {"name": "图像分类页", "description": "对应前端「图像分类」页面"},
    {"name": "文本检索页", "description": "对应前端「文本检索」页面"},
    {"name": "多模态匹配页", "description": "对应前端「多模态匹配」页面"},
]


def _body(code: ErrorCode, msg: str = "") -> JSONResponse:
    """所有响应（含错误）都是 {code, result, msg}；HTTP 状态码取自业务码前三位。"""
    return JSONResponse(
        status_code=code.http_status,
        content=ApiResponse(code=int(code), msg=msg or code.message).model_dump(),
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
        # 异常原文只进服务端日志，不回给前端（可能含路径等内部信息）
        logger.exception("未捕获异常：%s", type(exc).__name__)
        return _body(ErrorCode.INTERNAL_ERROR)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Agent ShopVision API",
        version="0.1.0",
        description=_DESCRIPTION,
        openapi_tags=_TAGS_META,
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

    # 静态文件服务：商品原图。用独立前缀，避免和前端 public/items 演示图冲突
    # 前端通过 /item-images/{category}/images/{file} 访问
    if _IMAGES_DIR.exists():
        app.mount("/item-images", StaticFiles(directory=str(_IMAGES_DIR)), name="item-images")
        logger.info(f"已挂载商品图片目录: {_IMAGES_DIR} -> /item-images")
    else:
        logger.warning(f"商品图片目录不存在: {_IMAGES_DIR}")

    @app.get("/scalar", include_in_schema=False)
    def scalar_docs() -> FileResponse:
        """Scalar 版接口文档（比 Swagger UI 好看，同样能在页面上直接调）。"""
        return FileResponse(_STATIC_DIR / "scalar.html")

    @app.get("/", include_in_schema=False)
    def root() -> ApiResponse:
        return ApiResponse.ok(
            {"docs": "/docs", "scalar": "/scalar", "redoc": "/redoc", "health": "/api/v1/health"}
        )

    return app


app = create_app()
