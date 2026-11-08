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
from typing import TYPE_CHECKING, Any

import numpy as np

from ..errors import ApiError, ErrorCode

if TYPE_CHECKING:
    from .upload_store import UploadStore

_HIDDEN_FIELDS = {"vector_id", "text"}


def _load_original_paths(root: Path | None) -> dict[str, str]:
    """item_id -> 原始图片相对路径，来源是 raw_data/*/products.csv。

    静态索引里的 local_image_path 指向清洗/增强后的图；前台要展示原图，
    所以按 item_id 补一份原始路径。
    """
    if root is None or not root.is_dir():
        return {}
    mapping: dict[str, str] = {}
    for csv_path in sorted(root.glob("*/products.csv")):
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    item_id = (row.get("item_id") or "").strip()
                    original = (row.get("local_image_path") or "").strip()
                    if item_id and original:
                        mapping[item_id] = original
        except OSError:
            continue
    return mapping


@dataclass(frozen=True)
class Hit:
    category: str
    vector_id: int
    score: float
    item: dict[str, Any]

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "similarity": round(self.score, 6),
            **{k: v for k, v in self.item.items() if k not in _HIDDEN_FIELDS},
        }


class IndexStore:
    """懒加载的只读索引。每个类别首次访问时才落盘读取并缓存。"""

    def __init__(
        self,
        index_dir: Path,
        candidate_k: int = 50,
        upload_store: "UploadStore | None" = None,
        new_category_min_items: int = 1,
        raw_image_root: Path | None = None,
    ) -> None:
        self.index_dir = Path(index_dir)
        self._original_paths = _load_original_paths(raw_image_root)
        registry_path = self.index_dir / "index_registry.json"
        if not registry_path.is_file():
            raise ApiError(ErrorCode.INDEX_MISSING, f"找不到索引注册表：{registry_path}")
        with registry_path.open("r", encoding="utf-8") as handle:
            self._registry = json.load(handle)
        self.candidate_k = candidate_k
        self.upload_store = upload_store
        self.new_category_min_items = max(1, int(new_category_min_items))
        self._cache: dict[str, tuple[dict[int, dict[str, Any]], np.ndarray]] = {}
        # 同步路由跑在线程池里，首次加载要串起来；锁只护首次加载，命中后不加锁。
        self._lock = threading.Lock()

        self._static_dimension: int | None = None
        for entry in self._registry.get("categories", {}).values():
            self._static_dimension = int(entry.get("dimension", 0)) or None
            break
        if (
            upload_store is not None
            and upload_store.dimension
            and self._static_dimension
            and upload_store.dimension != self._static_dimension
        ):
            raise ApiError(
                ErrorCode.DIM_MISMATCH,
                f"上传库 {upload_store.dimension} 维，静态索引 {self._static_dimension} 维；"
                "不是同一个向量空间",
            )

    @property
    def categories(self) -> list[str]:
        names = set(self._registry.get("categories", {}))
        if self.upload_store is not None:
            names.update(self.upload_store.categories())
        return sorted(names)

    @property
    def classifiable_categories(self) -> list[str]:
        """参与 best_category 的类别：静态类别 + 达到门槛的新类别。"""
        static = set(self._registry.get("categories", {}))
        if self.upload_store is None:
            return sorted(static)
        counts = self.upload_store.counts()
        dynamic = {
            name
            for name, count in counts.items()
            if name not in static and count >= self.new_category_min_items
        }
        return sorted(static | dynamic)

    @property
    def dimension(self) -> int | None:
        if self._static_dimension:
            return self._static_dimension
        if self.upload_store is not None:
            return self.upload_store.dimension
        return None

    def summary(self) -> dict:
        """索引概况，供 health 之类的状态接口用，别让上层去翻内部字段。"""
        entries = self._registry.get("categories", {})
        category_counts = {name: int(entry.get("items", 0)) for name, entry in entries.items()}
        category_ready = {name: self._files_ready(entry) for name, entry in entries.items()}
        if self.upload_store is not None:
            for name, count in self.upload_store.counts().items():
                category_counts[name] = category_counts.get(name, 0) + count
                # 静态类别看原文件是否齐全；仅 DB 的新类别有商品才算可检索
                if name not in category_ready:
                    category_ready[name] = count > 0
        model = self._registry.get("model") or {}
        return {
            "index_dir": str(self.index_dir),
            "categories": self.categories,
            "dimension": self.dimension,
            "category_counts": category_counts,
            "total_items": sum(category_counts.values()),
            "category_ready": category_ready,
            "updated_at": self._registry.get("updated_at"),
            "model_name": model.get("name"),
            "model_checkpoint": model.get("checkpoint"),
        }

    def _files_ready(self, entry: dict) -> bool:
        """只查文件是否存在，不加载向量：状态页要的是真实可检索性，不是猜测。"""
        items_csv = entry.get("items_csv")
        if not items_csv:
            return False
        csv_path = self.index_dir / items_csv
        return csv_path.is_file() and (csv_path.parent / "image_embeddings.npy").is_file()

    def _load(self, category: str) -> tuple[dict[int, dict[str, Any]], np.ndarray]:
        cached = self._cache.get(category)
        if cached is not None:
            return cached
        with self._lock:
            if category not in self._cache:
                self._cache[category] = self._read(category)
            return self._cache[category]

    def reload(self, category: str) -> None:
        """入库后清缓存；与 _load 共用同一把锁，避免把提交前的旧快照写回。"""
        with self._lock:
            self._cache.pop(category, None)

    def _read(self, category: str) -> tuple[dict[int, dict[str, Any]], np.ndarray]:
        entry = (self._registry.get("categories") or {}).get(category)
        store = self.upload_store
        has_upload = store is not None and store.has_category(category)

        static_items: dict[int, dict[str, Any]]
        static_vectors: np.ndarray
        if entry is not None:
            static_items, static_vectors = self._read_static(category, entry)
        elif has_upload:
            # 上传时新建的类别：静态部分为空，不再抛 40401
            static_items = {}
            static_vectors = np.zeros((0, self.dimension or 0), dtype="float32")
        else:
            raise ApiError(ErrorCode.CATEGORY_NOT_FOUND, category)

        if store is None or not has_upload:
            return static_items, static_vectors

        dynamic_items, dynamic_vectors = store.items(category)
        if dynamic_vectors.shape[0] == 0:
            return static_items, static_vectors
        if static_vectors.shape[0] and static_vectors.shape[1] != dynamic_vectors.shape[1]:
            raise ApiError(
                ErrorCode.DIM_MISMATCH,
                f"类别 {category} 静态向量 {static_vectors.shape[1]} 维，"
                f"上传向量 {dynamic_vectors.shape[1]} 维",
            )
        # 动态行接在静态行后面；search 里 key 必须等于矩阵行号
        offset = len(static_items)
        merged = dict(static_items)
        for index, row in enumerate(dynamic_items):
            merged[offset + index] = row
        if static_vectors.shape[0] == 0:
            return merged, dynamic_vectors
        return merged, np.vstack([static_vectors, dynamic_vectors])

    def _read_static(
        self, category: str, entry: dict
    ) -> tuple[dict[int, dict[str, Any]], np.ndarray]:
        csv_path = self.index_dir / entry["items_csv"]
        if not csv_path.is_file():
            raise ApiError(ErrorCode.INDEX_MISSING, f"类别 {category} 缺少条目表：{csv_path}")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            # 用行号而不是 CSV 里的 vector_id：search 的 key 必须与矩阵行号一致
            items = {index: dict(row) for index, row in enumerate(csv.DictReader(handle))}
        for row in items.values():
            original = self._original_paths.get(row.get("item_id", ""))
            if original:
                row["original_image_path"] = original
        embeddings_path = csv_path.parent / "image_embeddings.npy"
        if not embeddings_path.is_file():
            raise ApiError(ErrorCode.INDEX_MISSING, f"类别 {category} 缺少向量：{embeddings_path}")
        # 不 mmap：每类向量仅数 MB，直接读入内存；mmap 会一直占着文件句柄，
        # Windows 下连测试的临时目录都删不掉。
        return items, np.load(embeddings_path)

    def check_dimension(self, vector: np.ndarray) -> None:
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
        # 维度只跟向量有关，查一次就够；放在循环外，别让它随类别数重复跑
        self.check_dimension(vector)
        pool: list[Hit] = []
        for category in categories or self.categories:
            items, embeddings = self._load(category)
            # 动态空类别是 (0, dim)，先挡掉，别让 matmul 抛 ValueError
            if embeddings.shape[0] == 0:
                continue
            sims = np.asarray(embeddings @ vector).reshape(-1)
            if sims.size == 0:
                continue
            k = min(self.candidate_k, sims.size)
            idx = np.argpartition(-sims, k - 1)[:k] if k < sims.size else np.arange(sims.size)
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
        # 与 search() 一致：不同源（编码器维度 ≠ 索引维度）时给 400 DIM_MISMATCH，
        # 不能放任 matmul 抛 ValueError 落到全局兜底变成 500。
        self.check_dimension(vector)
        scores: dict[str, float] = {}
        best: tuple[str | None, float] = (None, float("-inf"))
        for category in self.classifiable_categories:
            _, embeddings = self._load(category)
            if embeddings.shape[0] == 0:
                continue
            top = float(np.max(np.asarray(embeddings @ vector).reshape(-1)))
            scores[category] = top
            if top > best[1]:
                best = (category, top)
        return best[0], best[1], scores

    def find_item(self, item_id: str) -> dict[str, Any] | None:
        """按 item_id 精确查一条商品（供 get_item_detail 工具用）。

        只在静态索引里找；上传入库的条目走 UploadStore，属于后续扩展。
        """
        target = (item_id or "").strip()
        if not target:
            return None
        for category in self.categories:
            items, _ = self._load(category)
            for row in items.values():
                if str(row.get("item_id")) == target:
                    return {"category": category, **row}
        return None
