"""增量入库存储：上传图片落盘 + 向量写 SQLite。

静态索引（data/index_data_finetuned）保持只读；这里只追加，不改它。
每个操作独立连接并显式 close：Windows 下 ``with sqlite3.connect(...)`` 只提交不关闭，
临时目录清理会失败。
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import numpy as np

from ..config import REPO_ROOT
from ..errors import ApiError, ErrorCode

_DDL = """
CREATE TABLE IF NOT EXISTS categories (
    name TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    category TEXT NOT NULL REFERENCES categories(name),
    item_name TEXT NOT NULL DEFAULT '',
    product_type TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '',
    material TEXT NOT NULL DEFAULT '',
    brand TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    local_image_path TEXT NOT NULL,
    image_status TEXT NOT NULL DEFAULT 'ok',
    image_height INTEGER NOT NULL DEFAULT 0,
    image_width INTEGER NOT NULL DEFAULT 0,
    vector BLOB NOT NULL,
    model_tag TEXT NOT NULL,
    image_sha256 TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE TABLE IF NOT EXISTS ingest_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

_FORMAT_EXT = {"PNG": "png", "JPEG": "jpg", "JPG": "jpg", "WEBP": "webp"}
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_HIDDEN_FIELDS = {"vector", "model_tag", "image_sha256"}


def normalize_category(name: str) -> str:
    """类别名既要能当 SQL 主键，也要能当 Windows 目录名。"""
    value = str(name or "").strip()
    if not value:
        raise ApiError(ErrorCode.BAD_REQUEST, "类别名不能为空")
    if len(value) > 64:
        raise ApiError(ErrorCode.BAD_REQUEST, "类别名最多 64 个字符")
    if value in {".", ".."} or value.startswith("."):
        raise ApiError(ErrorCode.BAD_REQUEST, "类别名不能以点开头")
    if _INVALID_CHARS.search(value):
        raise ApiError(ErrorCode.BAD_REQUEST, '类别名不能包含 < > : " / \\ | ? * 或控制字符')
    if value.endswith((".", " ")):
        raise ApiError(ErrorCode.BAD_REQUEST, "类别名不能以点或空格结尾")
    if value.split(".")[0].upper() in _RESERVED_NAMES:
        raise ApiError(ErrorCode.BAD_REQUEST, "类别名不能使用 Windows 保留名（CON/PRN/NUL 等）")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UploadStore:
    """上传商品库。读永远放行；写只在真实模型下发生。"""

    def __init__(
        self,
        db_path: Path,
        image_root: Path,
        *,
        dimension: int,
        model_tag: str,
    ) -> None:
        self.db_path = Path(db_path)
        self.image_root = Path(image_root)
        self.dimension = int(dimension)
        self.model_tag = model_tag
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.image_root.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_DDL)
            tags = [
                row["model_tag"] for row in conn.execute("SELECT DISTINCT model_tag FROM items")
            ]
        if len(tags) > 1:
            raise ApiError(
                ErrorCode.MODEL_UNAVAILABLE,
                f"上传库内混有两种向量模型 {tags}；请备份并删除 {self.db_path} 后重新入库",
            )

    def _public(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        for key in _HIDDEN_FIELDS:
            data.pop(key, None)
        return data

    def ensure_category(self, name: str) -> bool:
        name = normalize_category(name)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO categories(name, created_at) VALUES (?, ?)",
                (name, _now()),
            )
        return cursor.rowcount > 0

    def has_category(self, name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM categories WHERE name = ?", (name,)).fetchone()
        return row is not None

    def categories(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
        return [row["name"] for row in rows]

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            counts = {row["name"]: 0 for row in conn.execute("SELECT name FROM categories")}
            for row in conn.execute("SELECT category, COUNT(*) AS n FROM items GROUP BY category"):
                counts[row["category"]] = int(row["n"])
        return counts

    def items(self, category: str) -> tuple[list[dict], np.ndarray]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM items WHERE category = ? ORDER BY created_at, item_id",
                (category,),
            ).fetchall()
        if not rows:
            return [], np.zeros((0, self.dimension), dtype="float32")
        vectors = np.stack([np.frombuffer(row["vector"], dtype="float32") for row in rows])
        return [self._public(row) for row in rows], vectors

    def find_by_sha256(self, sha: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM items WHERE image_sha256 = ?", (sha,)).fetchone()
        return self._public(row) if row is not None else None

    def add_item(
        self,
        *,
        category: str,
        vector: np.ndarray,
        raw: bytes,
        image_format: str,
        metadata: dict[str, str],
        image_width: int,
        image_height: int,
    ) -> tuple[dict, bool]:
        """写一条上传商品；返回 (条目, 是否新建)。重复图片返回已有条目且 created=False。"""
        category = normalize_category(category)
        if not raw:
            raise ApiError(ErrorCode.EMPTY_UPLOAD)
        vector = np.asarray(vector, dtype="float32").reshape(-1)
        if vector.size != self.dimension:
            raise ApiError(
                ErrorCode.DIM_MISMATCH,
                f"上传向量 {vector.size} 维，存储要求 {self.dimension} 维",
            )
        ext = _FORMAT_EXT.get((image_format or "").upper())
        if ext is None:
            raise ApiError(ErrorCode.INVALID_IMAGE, f"不支持 {image_format}")

        sha = hashlib.sha256(raw).hexdigest()
        existing = self.find_by_sha256(sha)
        if existing is not None:
            self._log(existing.get("item_id", ""), "duplicate", "duplicate", "图片已入库")
            return existing, False

        folder = self.image_root / category / "images"
        folder.mkdir(parents=True, exist_ok=True)
        if not folder.resolve().is_relative_to(self.image_root.resolve()):
            raise ApiError(ErrorCode.BAD_REQUEST, "类别名越出图片目录")
        temp = folder / f".{sha}.tmp"
        temp.write_bytes(raw)

        final: Path | None = None
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing_row = conn.execute(
                    "SELECT * FROM items WHERE image_sha256 = ?", (sha,)
                ).fetchone()
                if existing_row is not None:
                    conn.execute("ROLLBACK")
                    temp.unlink(missing_ok=True)
                    self._log(existing_row["item_id"], "duplicate", "duplicate", "并发重复上传")
                    return self._public(existing_row), False

                tags = {
                    row["model_tag"] for row in conn.execute("SELECT DISTINCT model_tag FROM items")
                }
                if tags and self.model_tag not in tags:
                    raise ApiError(
                        ErrorCode.MODEL_UNAVAILABLE,
                        f"库内向量模型 {sorted(tags)} 与当前 {self.model_tag} 不一致；"
                        f"请备份并删除 {self.db_path} 后重新入库",
                    )

                item_id = self._unique_item_id(conn, sha)
                final = folder / f"{item_id}.{ext}"
                now = _now()
                conn.execute(
                    "INSERT OR IGNORE INTO categories(name, created_at) VALUES (?, ?)",
                    (category, now),
                )
                conn.execute(
                    "INSERT INTO items("
                    "item_id, category, item_name, product_type, type, color, material, brand, "
                    "description, local_image_path, image_status, image_height, image_width, "
                    "vector, model_tag, image_sha256, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item_id,
                        category,
                        metadata.get("item_name") or "",
                        metadata.get("product_type") or category,
                        metadata.get("type") or "",
                        metadata.get("color") or "",
                        metadata.get("material") or "",
                        metadata.get("brand") or "",
                        metadata.get("description") or "",
                        self._local_path(final),
                        "ok",
                        int(image_height),
                        int(image_width),
                        vector.tobytes(),
                        self.model_tag,
                        sha,
                        now,
                    ),
                )
                conn.execute(
                    "INSERT INTO ingest_log(item_id, action, status, message, created_at) "
                    "VALUES (?, 'upload', 'ok', '', ?)",
                    (item_id, now),
                )
                # 先落文件再提交：崩溃在两者之间只留孤儿图片，不会留“行指向不存在的图”
                os.replace(temp, final)
                conn.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                temp.unlink(missing_ok=True)
                if final is not None:
                    final.unlink(missing_ok=True)
                existing = self.find_by_sha256(sha)
                if existing is not None:
                    self._log(existing.get("item_id", ""), "duplicate", "duplicate", "并发重复上传")
                    return existing, False
                raise ApiError(ErrorCode.INTERNAL_ERROR, f"入库冲突：{exc}") from exc
            except ApiError:
                conn.execute("ROLLBACK")
                temp.unlink(missing_ok=True)
                if final is not None:
                    final.unlink(missing_ok=True)
                raise
            except Exception:
                conn.execute("ROLLBACK")
                temp.unlink(missing_ok=True)
                if final is not None:
                    final.unlink(missing_ok=True)
                raise

        row = self.find_by_sha256(sha)
        if row is None:
            raise ApiError(ErrorCode.INTERNAL_ERROR, "入库后未能读回条目")
        return row, True

    def _unique_item_id(self, conn: sqlite3.Connection, sha: str) -> str:
        for length in (12, 16, 64):
            candidate = f"upload_{sha[:length]}"
            row = conn.execute("SELECT 1 FROM items WHERE item_id = ?", (candidate,)).fetchone()
            if row is None:
                return candidate
        raise ApiError(ErrorCode.INTERNAL_ERROR, "无法分配 item_id")

    def _local_path(self, final: Path) -> str:
        try:
            return final.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return final.resolve().as_posix()

    def _log(self, item_id: str, action: str, status: str, message: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO ingest_log(item_id, action, status, message, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (item_id, action, status, message, _now()),
                )
        except sqlite3.Error:
            # 审计日志失败不影响入库主流程
            pass
