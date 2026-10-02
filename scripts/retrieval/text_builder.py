"""Build the Chinese text used by the image-text retrieval index."""

from __future__ import annotations

from typing import Mapping


FIELD_LABELS = (
    ("商品大类", "product_type"),
    ("细分类", "type"),
    ("颜色", "color"),
    ("材质", "material"),
)


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def build_product_text(row: Mapping[str, object]) -> str:
    """Return one stable Chinese template for an indexed product row.

    The four controlled attributes are always emitted. Title and description
    are appended when available so text queries can use both structured fields
    and the reviewed product wording.
    """
    parts = [f"{label}：{_clean(row.get(field))}" for label, field in FIELD_LABELS]
    title = _clean(row.get("item_name"))
    description = _clean(row.get("description"))
    if title:
        parts.append(f"商品标题：{title}")
    # The reviewed CSV already stores the same four-field template in many
    # description cells. Do not append that template a second time.
    if description and not description.startswith("商品大类："):
        parts.append(f"商品描述：{description}")
    return "；".join(parts)
