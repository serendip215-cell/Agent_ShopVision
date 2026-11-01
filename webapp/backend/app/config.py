"""运行配置。所有可调项走环境变量 / .env，代码里不写死路径。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# webapp/backend/app/config.py -> 仓库根
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SHOPVISION_", env_file=".env", extra="ignore"
    )

    # placeholder = 确定性占位编码器（先跑通链路）；onnx = 实验三双塔 ONNX
    model_backend: str = "placeholder"
    onnx_visual: str = ""
    onnx_text: str = ""
    onnx_provider: str = "CPUExecutionProvider"
    onnx_context_length: int = 52

    index_dir: str = "data/index_data_finetuned"
    embedding_dim: int = 512
    candidate_k: int = 50

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    def repo_path(self, value: str) -> Path:
        """相对路径按仓库根解析。"""
        path = Path(value).expanduser()
        return path if path.is_absolute() else REPO_ROOT / path

    @property
    def index_path(self) -> Path:
        return self.repo_path(self.index_dir)


def get_settings() -> Settings:
    return Settings()