"""应用服务层：把编码器与索引组合成三个页面各自的动作。

api 层调用这里；这里只依赖 Encoder 与 IndexStore 两个抽象，不碰 HTTP。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .encoder import Encoder
from .index_store import IndexStore

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
        hits = self.index.search(vector, [category] if category else None, top_k)
        return {
            "query": text,
            "category": category or (hits[0].category if hits else None),
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
