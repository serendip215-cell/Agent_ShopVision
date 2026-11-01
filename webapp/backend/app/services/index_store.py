"""数据访问层：封装 data/index_data_finetuned 的 FAISS 索引与商品条目。

不改索引、不重算向量，只读：注册表 -> 每类的 items.csv + image_embeddings.npy。
向量已是 L2 归一化，故余弦相似度 = 点积；这里直接用 numpy，不引入 faiss 依赖。
"""

from __future__ import annotations

import csv
import json
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..errors import ApiError, ErrorCode

_HIDDEN_FIELDS = {"vector_id", "text"}


@dataclass(frozen=True)
class Hit:
    category: str
    vector_id: int
    score: float
    item: dict[str, str]

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "similarity": round(self.score, 6),
            **{k: v for k, v in self.item.items() if k not in _HIDDEN_FIELDS},
        }


class IndexStore:
    """懒加载的只读索引。每个类别首次访问时才落盘读取并缓存。"""

    def __init__(self, index_dir: Path, candidate_k: int = 50) -> None:
        self.index_dir = Path(index_dir)
        registry_path = self.index_dir / "index_registry.json"
        if not registry_path.is_file():
            raise ApiError(ErrorCode.INDEX_MISSING, f"找不到索引注册表：{registry_path}")
        with registry_path.open("r", encoding="utf-8") as handle:
            self._registry = json.load(handle)
        self.candidate_k = candidate_k
        self._cache: dict[str, tuple[dict[int, dict[str, str]], np.ndarray]] = {}
        # 同步路由跑在线程池里，首次加载要串起来；锁只护首次加载，命中后不加锁。
        self._lock = threading.Lock()

    @property
    def categories(self) -> list[str]:
        return sorted(self._registry.get("categories", {}))

    @property
    def dimension(self) -> int | None:
        for entry in self._registry.get("categories", {}).values():
            return int(entry.get("dimension", 0)) or None
        return None

    def summary(self) -> dict:
        """索引概况，供 health 之类的状态接口用，别让上层去翻内部字段。"""
        return {
            "index_dir": str(self.index_dir),
            "categories": self.categories,
            "dimension": self.dimension,
        }

    def _load(self, category: str) -> tuple[dict[int, dict[str, str]], np.ndarray]:
        cached = self._cache.get(category)
        if cached is not None:
            return cached
        with self._lock:
            if category not in self._cache:
                self._cache[category] = self._read(category)
            return self._cache[category]

    def _read(self, category: str) -> tuple[dict[int, dict[str, str]], np.ndarray]:
        entry = (self._registry.get("categories") or {}).get(category)
        if entry is None:
            raise ApiError(ErrorCode.CATEGORY_NOT_FOUND, category)
        csv_path = self.index_dir / entry["items_csv"]
        if not csv_path.is_file():
            raise ApiError(ErrorCode.INDEX_MISSING, f"类别 {category} 缺少条目表：{csv_path}")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            items = {int(row["vector_id"]): row for row in csv.DictReader(handle)}
        embeddings_path = csv_path.parent / "image_embeddings.npy"
        if not embeddings_path.is_file():
            raise ApiError(ErrorCode.INDEX_MISSING, f"类别 {category} 缺少向量：{embeddings_path}")
        # 不 mmap：每类向量仅数 MB，直接读入内存；mmap 会一直占着文件句柄，
        # Windows 下连测试的临时目录都删不掉。
        return items, np.load(embeddings_path)

    def _check_dim(self, vector: np.ndarray) -> None:
        expected = self.dimension
        if expected and vector.shape[-1] != expected:
            raise ApiError(
                ErrorCode.DIM_MISMATCH,
                f"查询向量 {vector.shape[-1]} 维，索引 {expected} 维；"
                "多半是模型/索引不同源（占位编码器下检索结果无意义）",
            )

    def search(
        self,
        vector: np.ndarray,
        categories: list[str] | None = None,
        top_k: int = 5,
    ) -> list[Hit]:
        """在指定（或全部）类别的图像向量上取余弦相似度最高的 top_k 条。"""
        vector = np.asarray(vector, dtype="float32").reshape(-1)
        if top_k < 1:
            raise ApiError(ErrorCode.BAD_REQUEST, "top_k 必须大于 0")
        pool: list[Hit] = []
        for category in (categories or self.categories):
            self._check_dim(vector)
            items, embeddings = self._load(category)
            sims = np.asarray(embeddings @ vector).reshape(-1)
            if sims.size == 0:
                continue
            k = min(self.candidate_k, sims.size)
            idx = (
                np.argpartition(-sims, k - 1)[:k] if k < sims.size else np.arange(sims.size)
            )
            for i in idx:
                i = int(i)
                row = items.get(i)
                if row is None:
                    continue
                pool.append(Hit(category, i, float(sims[i]), row))
        pool.sort(key=lambda hit: hit.score, reverse=True)
        return pool[:top_k]

    def best_category(self, vector: np.ndarray) -> tuple[str | None, float, dict[str, float]]:
        """每个类别取最高相似度，返回（最佳类别, 分数, 各类分数表）。"""
        vector = np.asarray(vector, dtype="float32").reshape(-1)
        scores: dict[str, float] = {}
        best: tuple[str | None, float] = (None, float("-inf"))
        for category in self.categories:
            items, embeddings = self._load(category)
            del items
            if embeddings.shape[0] == 0:
                continue
            top = float(np.max(np.asarray(embeddings @ vector).reshape(-1)))
            scores[category] = top
            if top > best[1]:
                best = (category, top)
        return best[0], best[1], scores