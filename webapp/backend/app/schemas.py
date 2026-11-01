"""请求体、结果模型与统一返回体。前端只认一种返回形状：{code, result, msg}。

结果模型（`*Result` / `*Response`）只服务文档：让 /docs 把"返回值长什么样"画出来，
线上 JSON 形状仍由 `webapp/API约定.md` 冻结——模型只描述，不改形状、不增字段。
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse(BaseModel):
    """所有接口的统一返回体（成功与失败同形）。"""

    code: int = Field(default=0, description="0=成功；非 0 见错误码表（前三位即 HTTP 状态码）")
    result: Any = Field(default=None, description="成功时的业务数据；失败时为 null")
    msg: str = Field(default="ok", description="面向用户的提示，前端可直接展示")

    @classmethod
    def ok(cls, result: Any, msg: str = "ok") -> Self:
        return cls(code=0, result=result, msg=msg)


class TextQueryRequest(BaseModel):
    query: str = Field(
        min_length=1, max_length=200, description="中文查询词", examples=["白色运动鞋"]
    )
    top_k: int = Field(default=5, ge=1, le=50, description="返回条数上限")
    category: str | None = Field(default=None, description="限定类别，留空搜全部", examples=["鞋"])


# ---------- 结果模型：字段与 data/index_data_finetuned 的 items.csv 对齐 ----------


class CategoryScore(BaseModel):
    category: str = Field(description="类别名")
    similarity: float = Field(description="该类最高余弦相似度")


class MatchedItem(BaseModel):
    """检索命中的一条商品：相似度 + items.csv 原样字段。

    CSV 值一律是字符串，读取不做类型转换（`image_height` 等也是字符串）；
    未列出的列原样带出（extra=allow），`vector_id` 与 `text` 不外露。
    """

    model_config = ConfigDict(extra="allow")

    category: str = Field(description="命中类别")
    similarity: float = Field(description="余弦相似度（向量已 L2 归一化，故等于点积）")
    item_id: str | None = Field(default=None, description="数据源商品 ID")
    item_name: str | None = Field(default=None, description="商品标题")
    product_type: str | None = Field(default=None, description="商品大类")
    brand: str | None = Field(default=None, description="品牌，可能为空串")
    color: str | None = Field(default=None, description="颜色")
    material: str | None = Field(default=None, description="材质")
    description: str | None = Field(default=None, description="商品文案（实验一清洗后）")
    type: str | None = Field(default=None, description="细分类，如「女士小板鞋」")
    local_image_path: str | None = Field(default=None, description="原图相对路径")
    image_status: str | None = Field(default=None, description="图片处理状态")
    image_height: str | None = Field(default=None, description="图高（CSV 原样字符串）")
    image_width: str | None = Field(default=None, description="图宽（CSV 原样字符串）")


class HealthResult(BaseModel):
    model_loaded: bool = Field(
        description="true=已接真 ONNX 双塔；false=占位编码器，检索结果无意义"
    )
    backend: str = Field(description="当前编码器后端：placeholder / onnx")
    index_dir: str = Field(description="索引目录")
    categories: list[str] = Field(description="索引里注册的类别")
    dimension: int | None = Field(default=None, description="向量维度")


class ImageResult(BaseModel):
    category: str | None = Field(description="判出的类别：9 类里相似度最高的那个")
    confidence: float = Field(description="对 9 类最高分做 softmax 后的概率")
    score: float | None = Field(description="该类原始相似度")
    topk: list[CategoryScore] = Field(description="各类最高分，降序前 3")


class TextResult(BaseModel):
    query: str = Field(description="原查询词")
    category: str | None = Field(description="限定类别；搜全部时为命中最高的类别")
    items: list[MatchedItem] = Field(description="相关商品，按相似度降序")


class MatchResult(BaseModel):
    match: bool = Field(description="两条独立编码各自判出的类别是否一致")
    image_category: str | None = Field(default=None, description="图像塔判出的类别")
    text_category: str | None = Field(default=None, description="文本塔判出的类别")
    items: list[MatchedItem] = Field(description="文本检索结果，供对照")


# ---------- 各接口的返回模型：形状不变，只把 result 换成具体类型 ----------


class HealthResponse(ApiResponse):
    result: HealthResult | None = None


class ImageResponse(ApiResponse):
    result: ImageResult | None = None


class TextResponse(ApiResponse):
    result: TextResult | None = None


class MatchResponse(ApiResponse):
    result: MatchResult | None = None
