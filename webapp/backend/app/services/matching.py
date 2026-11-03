"""应用服务层：把编码器与索引组合成三个页面各自的动作。

api 层调用这里；这里只依赖 Encoder 与 IndexStore 两个抽象，不碰 HTTP。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ..errors import ApiError, ErrorCode
from .encoder import Encoder
from .index_store import IndexStore
from .upload_store import normalize_category

if TYPE_CHECKING:
    from PIL.Image import Image


def _softmax_pick(scores: dict[str, float], key: str) -> float:
    """把各类最高分做 softmax，取 key 那一类的概率当置信度。"""
    if not scores or key not in scores:
        return 0.0
    keys = list(scores)
    values = np.array([scores[k] for k in keys], dtype="float64")
    values -= values.max()
    probs = np.exp(values)
    probs /= probs.sum()
    return float(probs[keys.index(key)])


class MatchService:
    def __init__(self, encoder: Encoder, index: IndexStore) -> None:
        self.encoder = encoder
        self.index = index

    # 系统状态：api 的 health 只调这个，不穿透到 encoder/index
    def status(self) -> dict:
        return {"model_loaded": self.encoder.model_loaded, **self.index.summary()}

    # 数据入库：先给建议，confirm 后才写；写库后立即可检索
    def ingest_item(
        self,
        image: "Image",
        raw: bytes,
        image_format: str,
        *,
        category: str | None,
        confirm: bool,
        create_category: bool,
        metadata: dict[str, str],
    ) -> dict:
        if not self.encoder.model_loaded:
            raise ApiError(
                ErrorCode.MODEL_UNAVAILABLE,
                "占位编码器禁止入库；请切换 SHOPVISION_MODEL_BACKEND=onnx",
            )

        vector = self.encoder.encode_image(image)
        suggested_category, suggested_score, scores = self.index.best_category(vector)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]
        topk = [{"category": name, "similarity": round(score, 6)} for name, score in ranked]
        suggestion = {
            "created": False,
            "duplicate": False,
            "item_id": None,
            "category": None,
            "similarity": None,
            "suggested_category": suggested_category,
            "suggested_score": round(suggested_score, 6) if suggested_category else None,
            "topk": topk,
            "created_at": None,
            "item": None,
        }
        if not confirm:
            return suggestion

        if not category or not category.strip():
            raise ApiError(ErrorCode.BAD_REQUEST, "confirm=true 时必须指定 category")
        category = normalize_category(category)
        store = self.index.upload_store
        if store is None:
            raise ApiError(ErrorCode.MODEL_UNAVAILABLE, "上传存储未启用")

        known = set(self.index.categories)
        if category not in known and not create_category:
            raise ApiError(ErrorCode.CATEGORY_NOT_FOUND, category)

        similarity = None
        if category in known:
            hits = self.index.search(vector, [category], top_k=1)
            if hits:
                similarity = round(hits[0].score, 6)

        metadata = dict(metadata)
        metadata["item_name"] = metadata.get("item_name") or f"{category} 新增商品"
        item, created = store.add_item(
            category=category,
            vector=vector,
            raw=raw,
            image_format=image_format,
            metadata=metadata,
            image_width=image.width,
            image_height=image.height,
        )
        if created:
            # 已有类别也要 reload：否则 search 还会读到提交前的缓存
            self.index.reload(category)

        return {
            **suggestion,
            "created": created,
            "duplicate": not created,
            "item_id": item.get("item_id"),
            "category": item.get("category", category),
            "similarity": similarity,
            "created_at": item.get("created_at"),
            "item": item,
        }

    def create_category(self, name: str) -> dict:
        category = normalize_category(name)
        store = self.index.upload_store
        if store is None:
            raise ApiError(ErrorCode.MODEL_UNAVAILABLE, "上传存储未启用")
        return {"created": store.ensure_category(category), "name": category}

    # 图像分类页：商品图 -> 最近类别
    def classify_image(self, image: "Image") -> dict:
        vector = self.encoder.encode_image(image)
        category, score, scores = self.index.best_category(vector)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]
        # 判出类别内最相似的商品：前端拿它做“相似商品推荐”，不再用类别参考图顶替
        hits = self.index.search(vector, [category], top_k=4) if category else []
        return {
            "category": category,
            "confidence": round(_softmax_pick(scores, category or ""), 6),
            "score": round(score, 6) if category else None,
            "topk": [
                {
                    "category": c,
                    "similarity": round(s, 6),
                    # 与顶层 confidence 同口径：对全部类别做 softmax，而不是只归一化前三
                    "confidence": round(_softmax_pick(scores, c), 6),
                }
                for c, s in ranked
            ],
            "items": [hit.as_dict() for hit in hits],
        }

    # 文本分类页：中文查询 -> 相关商品
    def search_text(self, text: str, top_k: int = 5, category: str | None = None) -> dict:
        vector = self.encoder.encode_text(text)
        # 文本塔独立判类别：前端拿它和用户限定的 category 对照，提示语义冲突
        query_category, query_score, _ = self.index.best_category(vector)
        # 用户限定类别与模型判断不一致时，视为查询与限定类别没有交集，不返回该类别结果
        if category and query_category and category != query_category:
            hits = []
        else:
            hits = self.index.search(vector, [category] if category else None, top_k)
        return {
            "query": text,
            "category": category or (hits[0].category if hits else None),
            "query_category": query_category,
            "query_score": round(query_score, 6) if query_category else None,
            "items": [hit.as_dict() for hit in hits],
        }

    # 多模态匹配页：图 + 文 -> 先各判类别，再比对是否一致
    #
    # 故意不按 image_category 去过滤文本检索：任务书要的就是"两条独立编码、各判类别、
    # 再比对一致性"；若用图像判出的类别去限定文本检索，比对就变成循环论证、恒为一致。
    # items 保留全类别的文本检索结果，是为了给前端展示证据（含不一致时的对照）。
    def match(self, image: "Image", text: str, top_k: int = 5) -> dict:
        image_vector = self.encoder.encode_image(image)
        text_vector = self.encoder.encode_text(text)
        image_category, image_score, image_scores = self.index.best_category(image_vector)
        text_category, text_score, text_scores = self.index.best_category(text_vector)
        hits = self.index.search(text_vector, top_k=top_k)
        # 图像塔细分类取「判出类别内最相似的那条」的 type；类别未判定就留空
        image_type = None
        if image_category:
            image_hits = self.index.search(image_vector, [image_category], top_k=1)
            if image_hits:
                image_type = image_hits[0].item.get("type") or None
        # 文本塔细分类取「同类命中里排最前的那条」的 type；没有同类命中就留空
        text_type = next(
            (
                hit.item.get("type")
                for hit in hits
                if hit.category == text_category and hit.item.get("type")
            ),
            None,
        )
        return {
            "match": bool(image_category) and image_category == text_category,
            "image_category": image_category,
            "text_category": text_category,
            "image_confidence": round(_softmax_pick(image_scores, image_category or ""), 6),
            "image_score": round(image_score, 6) if image_category else None,
            "image_type": image_type,
            "text_confidence": round(_softmax_pick(text_scores, text_category or ""), 6),
            "text_score": round(text_score, 6) if text_category else None,
            "text_type": text_type,
            "items": [hit.as_dict() for hit in hits],
        }
