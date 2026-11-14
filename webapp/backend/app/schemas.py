"""请求体、结果模型与统一返回体。前端只认一种返回形状：{code, result, msg}。

结果模型（`*Result` / `*Response`）只服务文档：让 /docs 把"返回值长什么样"画出来，
线上 JSON 形状仍由 `webapp/API约定.md` 冻结——模型只描述；新增字段先写进约定再落模型。
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


class AdminCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64, description="新类别名", examples=["测试类"])


# ---------- 结果模型：字段与 data/index_data_finetuned 的 items.csv 对齐 ----------


class CategoryScore(BaseModel):
    category: str = Field(description="类别名")
    similarity: float = Field(description="该类最高余弦相似度")
    confidence: float = Field(
        description="对全部类别做 softmax 后该类的概率，与顶层 confidence 同口径"
    )


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
    local_image_path: str | None = Field(
        default=None, description="索引图片相对路径（静态条目是清洗/增强后的图；上传条目即原图）"
    )
    original_image_path: str | None = Field(
        default=None,
        description="原始商品图相对路径；仅静态索引条目有，经 /item-originals 访问",
    )
    image_status: str | None = Field(default=None, description="图片处理状态")
    image_height: str | int | None = Field(
        default=None, description="图高（静态索引为 CSV 原样字符串，上传入库为整数）"
    )
    image_width: str | int | None = Field(
        default=None, description="图宽（静态索引为 CSV 原样字符串，上传入库为整数）"
    )


class HealthResult(BaseModel):
    model_loaded: bool = Field(
        description="true=已接真 ONNX 双塔；false=占位编码器，检索结果无意义"
    )
    backend: str = Field(description="当前编码器后端：placeholder / onnx")
    index_dir: str = Field(description="静态索引目录")
    categories: list[str] = Field(description="全部类别：静态索引 + 上传入库")
    dimension: int | None = Field(default=None, description="向量维度")
    category_counts: dict[str, int] = Field(
        default_factory=dict, description="各类条数：静态索引 + 上传入库"
    )
    total_items: int = Field(default=0, description="可检索总条数")
    category_ready: dict[str, bool] = Field(
        default_factory=dict,
        description="各类是否可检索：静态类别看文件是否齐全，仅上传的新类别看是否有商品",
    )
    updated_at: str | None = Field(default=None, description="静态索引构建时间（不含上传入库）")
    model_name: str | None = Field(default=None, description="建索引所用视觉塔，如 ViT-B-16")
    model_checkpoint: str | None = Field(default=None, description="建索引所用权重路径")


class ItemAttributes(BaseModel):
    """上传图的属性参考值：同类别最相似几条商品的多数投票，不是独立属性模型。"""

    type: str | None = Field(default=None, description="细分类参考值")
    color: str | None = Field(default=None, description="颜色参考值")
    material: str | None = Field(default=None, description="材质参考值")


class ImageResult(BaseModel):
    category: str | None = Field(description="判出的类别：全部可判类别里相似度最高的那个")
    confidence: float = Field(description="对全部可判类别最高分做 softmax 后的概率")
    score: float | None = Field(description="该类原始相似度")
    attributes: ItemAttributes = Field(
        default_factory=ItemAttributes,
        description="按同类最相似商品投票得到的细分类/颜色/材质参考值，可能为空",
    )
    topk: list[CategoryScore] = Field(description="各类最高分，降序前 3")
    items: list[MatchedItem] = Field(
        default_factory=list, description="判出类别内与上传图最相似的商品，供相似商品推荐"
    )


class TextResult(BaseModel):
    query: str = Field(description="原查询词")
    category: str | None = Field(description="限定类别；搜全部时为命中最高的类别")
    query_category: str | None = Field(
        default=None, description="文本塔独立判出的类别，不受 category 限定影响"
    )
    query_score: float | None = Field(
        default=None, description="文本塔对 query_category 的原始相似度"
    )
    items: list[MatchedItem] = Field(description="相关商品，按相似度降序")


class MatchResult(BaseModel):
    match: bool = Field(description="两条独立编码各自判出的类别是否一致")
    image_category: str | None = Field(default=None, description="图像塔判出的类别")
    text_category: str | None = Field(default=None, description="文本塔判出的类别")
    image_confidence: float = Field(
        default=0.0, description="图像塔对判出类别的置信度（全部可判类别最高分 softmax）"
    )
    image_score: float | None = Field(default=None, description="图像塔该类别原始相似度")
    image_type: str | None = Field(
        default=None,
        description="图像塔细分类：图像判出类别内最相似商品的 type",
    )
    text_confidence: float = Field(
        default=0.0, description="文本塔对判出类别的置信度（全部可判类别最高分 softmax）"
    )
    text_score: float | None = Field(default=None, description="文本塔该类别原始相似度")
    text_type: str | None = Field(
        default=None, description="文本塔细分类：同类命中里排最前的那条商品的 type"
    )
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


# ---------- 数据入库：上传商品 / 新建空类别 ----------


class AdminTopCategory(BaseModel):
    category: str = Field(description="候选类别")
    similarity: float = Field(description="该类别最高余弦相似度")


class AdminItem(BaseModel):
    """一条上传商品；静态字段与 items.csv 对齐，宽高为整数。"""

    model_config = ConfigDict(extra="allow")

    item_id: str = Field(description="上传条目 ID，形如 upload_<sha256 前缀>")
    category: str = Field(description="所属类别")
    item_name: str | None = Field(default=None, description="商品标题")
    product_type: str | None = Field(default=None, description="商品大类")
    type: str | None = Field(default=None, description="细分类")
    color: str | None = Field(default=None, description="颜色")
    material: str | None = Field(default=None, description="材质")
    brand: str | None = Field(default=None, description="品牌")
    description: str | None = Field(default=None, description="商品文案")
    local_image_path: str | None = Field(default=None, description="原图相对路径")
    image_status: str | None = Field(default=None, description="图片处理状态")
    image_height: int | None = Field(default=None, description="图高")
    image_width: int | None = Field(default=None, description="图宽")
    created_at: str | None = Field(default=None, description="入库时间（UTC）")


class AdminItemResult(BaseModel):
    created: bool = Field(description="true=本次真正写入；false=未写（建议或重复）")
    duplicate: bool = Field(description="true=图片已存在，返回已有条目")
    item_id: str | None = Field(default=None, description="写入或命中的条目 ID")
    category: str | None = Field(default=None, description="实际所属类别")
    similarity: float | None = Field(
        default=None, description="写入前在目标类别内的最近邻相似度；空类别为 null"
    )
    suggested_category: str | None = Field(default=None, description="图像塔建议的类别")
    suggested_score: float | None = Field(default=None, description="建议类别的原始相似度")
    suggested_attributes: ItemAttributes = Field(
        default_factory=ItemAttributes,
        description="按建议类别内最相似商品投票得到的细分类/颜色/材质参考值",
    )
    topk: list[AdminTopCategory] = Field(
        default_factory=list, description="建议类别的相似度排序，最多 3 个"
    )
    created_at: str | None = Field(default=None, description="条目入库时间")
    item: AdminItem | None = Field(default=None, description="写入或命中的完整条目")


class AdminCategoryResult(BaseModel):
    created: bool = Field(description="true=本次新建；false=类别已存在")
    name: str = Field(description="规范化后的类别名")


class AdminItemResponse(ApiResponse):
    result: AdminItemResult | None = None


class AdminCategoryResponse(ApiResponse):
    result: AdminCategoryResult | None = None


# ---------- 异步任务（Celery + Redis）：提交与轮询 ----------


class TaskSubmitResult(BaseModel):
    task_id: str = Field(description="任务 ID，用于轮询 GET /api/v1/tasks/{task_id}")
    status: str = Field(description="提交后的初始状态，通常是 PENDING")
    total: int | None = Field(default=None, description="批量任务的文件数；单张任务为 null")


class TaskProgress(BaseModel):
    done: int = Field(description="已完成数")
    total: int = Field(description="总数")


class TaskError(BaseModel):
    code: int = Field(description="业务错误码，见错误码表")
    msg: str = Field(description="面向用户的提示")


class TaskStatusResult(BaseModel):
    task_id: str = Field(description="任务 ID")
    status: str = Field(description="PENDING / PROGRESS / SUCCESS / FAILURE")
    progress: TaskProgress | None = Field(default=None, description="PROGRESS 时的进度")
    result: Any = Field(
        default=None,
        description="SUCCESS 时的业务结果：单张任务为 ImageResult；"
        "批量任务为逐张 [{file_name, code, result, msg}] 列表",
    )
    error: TaskError | None = Field(default=None, description="FAILURE 时的错误")


class TaskSubmitResponse(ApiResponse):
    result: TaskSubmitResult | None = None


class TaskStatusResponse(ApiResponse):
    result: TaskStatusResult | None = None


# ---------- 对话导购（Agent）：/api/v1/agent/chat ----------


class AgentChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=500,
        description="用户一句话需求",
        examples=["找一双白色运动鞋"],
    )
    session_id: str | None = Field(
        default=None,
        max_length=64,
        description="多轮会话 ID；可留空（后端 ConversationStore 已支持，前端暂未传）",
    )


class AgentToolCall(BaseModel):
    name: str = Field(
        description="工具名：text_search / image_search / list_categories / get_item_detail"
    )
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具实参")


class AgentChatResult(BaseModel):
    reply: str = Field(description="助手回复（模型直接回答，或检索结果 + 点评）")
    thinking: list[str] = Field(default_factory=list, description="思考过程，前端折叠展示")
    tool_calls: list[AgentToolCall] = Field(
        default_factory=list, description="本轮调用过的工具（名称 + 参数）"
    )
    items: list[MatchedItem] = Field(
        default_factory=list, description="检索命中的商品；前端渲染为并排小图"
    )
    say: str | None = Field(
        default=None, description="工具调用前的过渡语（仅有 tool 动作时出现，≤30 字）"
    )


class AgentChatResponse(ApiResponse):
    result: AgentChatResult | None = None


class AgentImageResult(BaseModel):
    """以图搜图（可叠加文字融合）的结果。"""

    reply: str = Field(description="助手回复（模板拼装，商品信息来自检索结果）")
    thinking: list[str] = Field(default_factory=list, description="编码与检索过程")
    tool_calls: list[AgentToolCall] = Field(
        default_factory=list, description="图搜不走 LLM 工具调用，固定为空"
    )
    items: list[MatchedItem] = Field(default_factory=list, description="相似商品，按相似度降序")
    category: str | None = Field(default=None, description="查询向量判出的类别")
    similarity: float | None = Field(
        default=None, description="查询向量与该类别最高相似度（余弦，非概率）"
    )


class AgentImageResponse(ApiResponse):
    result: AgentImageResult | None = None
