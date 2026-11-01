"""依赖注入：把单例的编码器/索引组装成 api 层要的服务。

api 层只写 ``Depends(get_match_service)``，不自己 new 东西——换占位/ONNX、
换索引目录都只动配置。测试里用 app.dependency_overrides 覆盖本文件即可。
"""

from __future__ import annotations

from functools import lru_cache

from .config import get_settings
from .services.encoder import Encoder, build_encoder
from .services.index_store import IndexStore
from .services.matching import MatchService


@lru_cache(maxsize=1)
def get_encoder() -> Encoder:
    return build_encoder(get_settings())


@lru_cache(maxsize=1)
def get_index() -> IndexStore:
    settings = get_settings()
    return IndexStore(settings.index_path, candidate_k=settings.candidate_k)


def get_match_service() -> MatchService:
    return MatchService(get_encoder(), get_index())
