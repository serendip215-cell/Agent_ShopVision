"""运行配置。所有可调项走环境变量 / .env，代码里不写死路径。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# webapp/backend/app/config.py -> 仓库根
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHOPVISION_", env_file=".env", extra="ignore")

    # placeholder = 确定性占位编码器（先跑通链路）；onnx = 实验三双塔 ONNX
    model_backend: str = "placeholder"
    onnx_visual: str = ""
    onnx_text: str = ""
    onnx_provider: str = "CPUExecutionProvider"
    onnx_context_length: int = 52

    index_dir: str = "data/index_data_finetuned"
    embedding_dim: int = 512
    candidate_k: int = 50
    max_upload_mb: int = 10  # 上传图片大小上限，防止大文件全量读进内存

    # 增量入库：静态索引只读，上传数据落 SQLite，图片落 image_root。
    db_path: str = "data/webapp.db"
    image_root: str = "data/processed_data_cleaning"
    raw_image_root: str = "data/raw_data"  # 原始商品图，前台优先展示这份
    new_category_min_items: int = 1  # 新类别至少几条才参与自动判类

    # 异步任务（Celery + Redis）。Redis 可以是云端托管，填 rediss:// 走 TLS。
    # 只影响 /api/v1/tasks/*；三个同步接口不依赖 Redis。
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_always_eager: bool = False  # 测试用：任务同步执行，不需要 Redis
    celery_result_expires: int = 3600  # 任务结果保留秒数
    async_batch_max_files: int = 12  # 单次批量任务的文件数上限

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    def repo_path(self, value: str) -> Path:
        """相对路径按仓库根解析。"""
        path = Path(value).expanduser()
        return path if path.is_absolute() else REPO_ROOT / path

    @property
    def index_path(self) -> Path:
        return self.repo_path(self.index_dir)

    @property
    def db_file(self) -> Path:
        return self.repo_path(self.db_path)

    @property
    def image_root_path(self) -> Path:
        return self.repo_path(self.image_root)

    @property
    def raw_image_root_path(self) -> Path:
        return self.repo_path(self.raw_image_root)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例：.env 只在首次读取，改配置需重启进程（与 deps 的单例一致）。"""
    return Settings()
