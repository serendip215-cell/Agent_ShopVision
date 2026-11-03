# Agent ShopVision API（v0.1.0）

> 本文档由 `webapp/backend/scripts/export_api_docs.py` 从后端代码自动生成，**不要手改**；
> 改完接口在 `webapp/backend` 下重跑一次即可。线上最新版：服务跑起来看 `/docs`、`/scalar`、`/redoc`。

实验四后端：电商商品图文检索服务，集成实验三优化后的 Chinese-CLIP 双塔（ONNX）。

所有接口统一返回 `{code, result, msg}`：`code=0` 为成功，非 0 为错误码，且**前三位就是 HTTP 状态码**
（`40001` → 400、`40401` → 404、`50001` → 500）。完整码表见仓库 `webapp/API约定.md`。

- Swagger UI：`/docs`（本页，可直接发请求试接口）
- ReDoc：`/redoc`（阅读版）
- OpenAPI JSON：`/openapi.json`（可导出，供 API 文档或 Postman 使用）

## 基础约定

- 基址 `http://localhost:8000`，版本前缀 `/api/v1`
- 所有接口（含出错）都返回同一形状：`{code, result, msg}`，**HTTP 状态码 = code 前三位**
- 图像接口用 `multipart/form-data`，文本接口用 `application/json`
- 调用示例见 [`webapp/README.md` §三](https://github.com/serendip215-cell/Agent_ShopVision/blob/main/webapp/README.md)

## 错误码表

| 业务码 | HTTP | 默认提示 | 场景 |
|---:|---:|---|---|
| `40000` | 400 | 参数错误 | BAD_REQUEST |
| `40001` | 400 | 图像格式错误，请上传 PNG/JPG | INVALID_IMAGE |
| `40002` | 400 | 上传内容为空 | EMPTY_UPLOAD |
| `40003` | 400 | 查询向量维度与索引不一致 | DIM_MISMATCH |
| `40004` | 400 | 上传文件过大 | FILE_TOO_LARGE |
| `40400` | 404 | 资源不存在 | NOT_FOUND |
| `40401` | 404 | 类别不存在 | CATEGORY_NOT_FOUND |
| `40402` | 404 | 索引文件缺失 | INDEX_MISSING |
| `50000` | 500 | 服务器内部错误 | INTERNAL_ERROR |
| `50001` | 500 | 模型或依赖不可用 | MODEL_UNAVAILABLE |

## 接口清单

### 状态

> 探活与索引概况，前端启动时先调

#### `GET /api/v1/health` — 健康检查

前端启动时先调这个探活。`model_loaded=false` 表示在跑占位编码器，链路通但检索结果无意义。

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.model_loaded` | 布尔 | true=已接真 ONNX 双塔；false=占位编码器，检索结果无意义 |
| `result.backend` | 字符串 | 当前编码器后端：placeholder / onnx |
| `result.index_dir` | 字符串 | 静态索引目录 |
| `result.categories` | 字符串 的数组 | 全部类别：静态索引 + 上传入库 |
| `result.dimension` | 整数（可为空） | 向量维度 |
| `result.category_counts` | 对象 | 各类条数：静态索引 + 上传入库 |
| `result.total_items` | 整数 | 可检索总条数 |
| `result.category_ready` | 对象 | 各类是否可检索：静态类别看文件是否齐全，仅上传的新类别看是否有商品 |
| `result.updated_at` | 字符串（可为空） | 静态索引构建时间（不含上传入库） |
| `result.model_name` | 字符串（可为空） | 建索引所用视觉塔，如 ViT-B-16 |
| `result.model_checkpoint` | 字符串（可为空） | 建索引所用权重路径 |

### 图像分类页

> 对应前端「图像分类」页面

#### `POST /api/v1/image` — 图像分类

上传商品图 → 图像塔编码成 512 维向量 → 与全部可判类别比相似度 → 返回最可能的类别、置信度与相似商品类别排序。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `file` | 文件 | 文件 | 是 | 商品图（PNG/JPG/WEBP，≤10 MB） |

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.category` | 字符串（可为空） | 判出的类别：全部可判类别里相似度最高的那个 |
| `result.confidence` | 小数 | 对全部可判类别最高分做 softmax 后的概率 |
| `result.score` | 小数（可为空） | 该类原始相似度 |
| `result.topk` | 对象 的数组 | 各类最高分，降序前 3 |
| `result.topk[].category` | 字符串 | 类别名 |
| `result.topk[].similarity` | 小数 | 该类最高余弦相似度 |
| `result.topk[].confidence` | 小数 | 对全部类别做 softmax 后该类的概率，与顶层 confidence 同口径 |
| `result.items` | 对象 的数组 | 判出类别内与上传图最相似的商品，供相似商品推荐 |
| `result.items[].category` | 字符串 | 命中类别 |
| `result.items[].similarity` | 小数 | 余弦相似度（向量已 L2 归一化，故等于点积） |
| `result.items[].item_id` | 字符串（可为空） | 数据源商品 ID |
| `result.items[].item_name` | 字符串（可为空） | 商品标题 |
| `result.items[].product_type` | 字符串（可为空） | 商品大类 |
| `result.items[].brand` | 字符串（可为空） | 品牌，可能为空串 |
| `result.items[].color` | 字符串（可为空） | 颜色 |
| `result.items[].material` | 字符串（可为空） | 材质 |
| `result.items[].description` | 字符串（可为空） | 商品文案（实验一清洗后） |
| `result.items[].type` | 字符串（可为空） | 细分类，如「女士小板鞋」 |
| `result.items[].local_image_path` | 字符串（可为空） | 索引图片相对路径（静态条目是清洗/增强后的图；上传条目即原图） |
| `result.items[].original_image_path` | 字符串（可为空） | 原始商品图相对路径；仅静态索引条目有，经 /item-originals 访问 |
| `result.items[].image_status` | 字符串（可为空） | 图片处理状态 |
| `result.items[].image_height` | 字符串 或 整数（可为空） | 图高（静态索引为 CSV 原样字符串，上传入库为整数） |
| `result.items[].image_width` | 字符串 或 整数（可为空） | 图宽（静态索引为 CSV 原样字符串，上传入库为整数） |

### 文本检索页

> 对应前端「文本检索」页面

#### `POST /api/v1/text` — 文本检索

中文查询 → 文本塔编码 → 在商品库里按余弦相似度取 top_k。`category` 留空表示搜全部类别；`query_category` 是文本塔独立判出的类别，不受 `category` 限定影响。两者不一致时视为没有交集，`items` 返回空数组。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `query` | 请求体 | 字符串 | 是 | 中文查询词 |
| `top_k` | 请求体 | 整数 | 否 | 返回条数上限 |
| `category` | 请求体 | 字符串（可为空） | 否 | 限定类别，留空搜全部 |

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.query` | 字符串 | 原查询词 |
| `result.category` | 字符串（可为空） | 限定类别；搜全部时为命中最高的类别 |
| `result.query_category` | 字符串（可为空） | 文本塔独立判出的类别，不受 category 限定影响 |
| `result.query_score` | 小数（可为空） | 文本塔对 query_category 的原始相似度 |
| `result.items` | 对象 的数组 | 相关商品，按相似度降序 |
| `result.items[].category` | 字符串 | 命中类别 |
| `result.items[].similarity` | 小数 | 余弦相似度（向量已 L2 归一化，故等于点积） |
| `result.items[].item_id` | 字符串（可为空） | 数据源商品 ID |
| `result.items[].item_name` | 字符串（可为空） | 商品标题 |
| `result.items[].product_type` | 字符串（可为空） | 商品大类 |
| `result.items[].brand` | 字符串（可为空） | 品牌，可能为空串 |
| `result.items[].color` | 字符串（可为空） | 颜色 |
| `result.items[].material` | 字符串（可为空） | 材质 |
| `result.items[].description` | 字符串（可为空） | 商品文案（实验一清洗后） |
| `result.items[].type` | 字符串（可为空） | 细分类，如「女士小板鞋」 |
| `result.items[].local_image_path` | 字符串（可为空） | 索引图片相对路径（静态条目是清洗/增强后的图；上传条目即原图） |
| `result.items[].original_image_path` | 字符串（可为空） | 原始商品图相对路径；仅静态索引条目有，经 /item-originals 访问 |
| `result.items[].image_status` | 字符串（可为空） | 图片处理状态 |
| `result.items[].image_height` | 字符串 或 整数（可为空） | 图高（静态索引为 CSV 原样字符串，上传入库为整数） |
| `result.items[].image_width` | 字符串 或 整数（可为空） | 图宽（静态索引为 CSV 原样字符串，上传入库为整数） |

### 多模态匹配页

> 对应前端「多模态匹配」页面

#### `POST /api/v1/match` — 图文匹配

图与文**各自独立**编码、各自判类别，再比对两个类别是否一致；不用图像判出的类别去限定文本检索（那样比对恒为一致，等于循环论证）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `file` | 文件 | 文件 | 是 | 商品图 |
| `text` | 表单字段 | 字符串 | 是 | 中文文本，如「白色运动鞋」 |
| `top_k` | 表单字段 | 整数 | 否 | 返回的文本检索条数 |

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.match` | 布尔 | 两条独立编码各自判出的类别是否一致 |
| `result.image_category` | 字符串（可为空） | 图像塔判出的类别 |
| `result.text_category` | 字符串（可为空） | 文本塔判出的类别 |
| `result.image_confidence` | 小数 | 图像塔对判出类别的置信度（全部可判类别最高分 softmax） |
| `result.image_score` | 小数（可为空） | 图像塔该类别原始相似度 |
| `result.image_type` | 字符串（可为空） | 图像塔细分类：图像判出类别内最相似商品的 type |
| `result.text_confidence` | 小数 | 文本塔对判出类别的置信度（全部可判类别最高分 softmax） |
| `result.text_score` | 小数（可为空） | 文本塔该类别原始相似度 |
| `result.text_type` | 字符串（可为空） | 文本塔细分类：同类命中里排最前的那条商品的 type |
| `result.items` | 对象 的数组 | 文本检索结果，供对照 |
| `result.items[].category` | 字符串 | 命中类别 |
| `result.items[].similarity` | 小数 | 余弦相似度（向量已 L2 归一化，故等于点积） |
| `result.items[].item_id` | 字符串（可为空） | 数据源商品 ID |
| `result.items[].item_name` | 字符串（可为空） | 商品标题 |
| `result.items[].product_type` | 字符串（可为空） | 商品大类 |
| `result.items[].brand` | 字符串（可为空） | 品牌，可能为空串 |
| `result.items[].color` | 字符串（可为空） | 颜色 |
| `result.items[].material` | 字符串（可为空） | 材质 |
| `result.items[].description` | 字符串（可为空） | 商品文案（实验一清洗后） |
| `result.items[].type` | 字符串（可为空） | 细分类，如「女士小板鞋」 |
| `result.items[].local_image_path` | 字符串（可为空） | 索引图片相对路径（静态条目是清洗/增强后的图；上传条目即原图） |
| `result.items[].original_image_path` | 字符串（可为空） | 原始商品图相对路径；仅静态索引条目有，经 /item-originals 访问 |
| `result.items[].image_status` | 字符串（可为空） | 图片处理状态 |
| `result.items[].image_height` | 字符串 或 整数（可为空） | 图高（静态索引为 CSV 原样字符串，上传入库为整数） |
| `result.items[].image_width` | 字符串 或 整数（可为空） | 图宽（静态索引为 CSV 原样字符串，上传入库为整数） |

### 数据入库

> 上传商品到已有/新类别，或新建空类别（未启用鉴权）

#### `POST /api/v1/admin/items` — 上传商品入库

只传 `file` 时只返回建议类别，不写库；`confirm=true` 且带 `category` 才真正入库。类别不存在时传 `create_category=true` 自动建类。同一张图重复上传返回已有条目（duplicate=true），不会重复计数。占位编码器下拒绝入库（50001）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `file` | 文件 | 文件 | 是 | 商品图（PNG/JPG/WEBP，≤10 MB） |
| `category` | 表单字段 | 字符串（可为空） | 否 | 目标类别；为空时只返回建议 |
| `confirm` | 表单字段 | 布尔 | 否 | true 才真正写库 |
| `create_category` | 表单字段 | 布尔 | 否 | 类别不存在时自动创建 |
| `item_name` | 表单字段 | 字符串（可为空） | 否 | 商品标题 |
| `type` | 表单字段 | 字符串（可为空） | 否 | 细分类 |
| `color` | 表单字段 | 字符串（可为空） | 否 | 颜色 |
| `material` | 表单字段 | 字符串（可为空） | 否 | 材质 |
| `brand` | 表单字段 | 字符串（可为空） | 否 | 品牌 |
| `description` | 表单字段 | 字符串（可为空） | 否 | 商品文案 |

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.created` | 布尔 | true=本次真正写入；false=未写（建议或重复） |
| `result.duplicate` | 布尔 | true=图片已存在，返回已有条目 |
| `result.item_id` | 字符串（可为空） | 写入或命中的条目 ID |
| `result.category` | 字符串（可为空） | 实际所属类别 |
| `result.similarity` | 小数（可为空） | 写入前在目标类别内的最近邻相似度；空类别为 null |
| `result.suggested_category` | 字符串（可为空） | 图像塔建议的类别 |
| `result.suggested_score` | 小数（可为空） | 建议类别的原始相似度 |
| `result.topk` | 对象 的数组 | 建议类别的相似度排序，最多 3 个 |
| `result.topk[].category` | 字符串 | 候选类别 |
| `result.topk[].similarity` | 小数 | 该类别最高余弦相似度 |
| `result.created_at` | 字符串（可为空） | 条目入库时间 |
| `result.item` | 对象（可为空） | 写入或命中的完整条目 |
| `result.item.item_id` | 字符串 | 上传条目 ID，形如 upload_<sha256 前缀> |
| `result.item.category` | 字符串 | 所属类别 |
| `result.item.item_name` | 字符串（可为空） | 商品标题 |
| `result.item.product_type` | 字符串（可为空） | 商品大类 |
| `result.item.type` | 字符串（可为空） | 细分类 |
| `result.item.color` | 字符串（可为空） | 颜色 |
| `result.item.material` | 字符串（可为空） | 材质 |
| `result.item.brand` | 字符串（可为空） | 品牌 |
| `result.item.description` | 字符串（可为空） | 商品文案 |
| `result.item.local_image_path` | 字符串（可为空） | 原图相对路径 |
| `result.item.image_status` | 字符串（可为空） | 图片处理状态 |
| `result.item.image_height` | 整数（可为空） | 图高 |
| `result.item.image_width` | 整数（可为空） | 图宽 |
| `result.item.created_at` | 字符串（可为空） | 入库时间（UTC） |


#### `POST /api/v1/admin/categories` — 新建空类别

只建类别、不写商品。空类别不会参与自动判类，但可以在检索页显式指定（结果为空）；上传首条商品后即参与判类。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `name` | 请求体 | 字符串 | 是 | 新类别名 |

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.created` | 布尔 | true=本次新建；false=类别已存在 |
| `result.name` | 字符串 | 规范化后的类别名 |

### 异步任务

#### `POST /api/v1/tasks/image` — 提交单张图片异步分类

大图或需要立即返回的场景用这个：提交后拿 task_id，再轮询 GET /api/v1/tasks/{task_id}。校验（格式/大小）仍在这里做，错误立即返回。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `file` | 文件 | 文件 | 是 | 商品图（PNG/JPG/WEBP，≤10 MB） |

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.task_id` | 字符串 | 任务 ID，用于轮询 GET /api/v1/tasks/{task_id} |
| `result.status` | 字符串 | 提交后的初始状态，通常是 PENDING |
| `result.total` | 整数（可为空） | 批量任务的文件数；单张任务为 null |


#### `POST /api/v1/tasks/batch` — 提交批量图片异步分类

一次提交多张图，worker 串行处理并上报进度。单批上限见 SHOPVISION_ASYNC_BATCH_MAX_FILES（默认 12）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `files` | 表单字段 | 文件 的数组 | 是 | 多张商品图 |

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.task_id` | 字符串 | 任务 ID，用于轮询 GET /api/v1/tasks/{task_id} |
| `result.status` | 字符串 | 提交后的初始状态，通常是 PENDING |
| `result.total` | 整数（可为空） | 批量任务的文件数；单张任务为 null |


#### `GET /api/v1/tasks/{task_id}` — 轮询任务状态

前端约每 800ms 轮询一次。PENDING/PROGRESS 时继续轮询；SUCCESS 拿结果；FAILURE 看 error。注意：不存在的 task_id 也会返回 PENDING（Celery 的语义）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `task_id` | path | 字符串 | 是 |  |

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.task_id` | 字符串 | 任务 ID |
| `result.status` | 字符串 | PENDING / PROGRESS / SUCCESS / FAILURE |
| `result.progress` | 对象（可为空） | PROGRESS 时的进度 |
| `result.progress.done` | 整数 | 已完成数 |
| `result.progress.total` | 整数 | 总数 |
| `result.result` | 对象或数组 | SUCCESS 时的业务结果：单张任务为 ImageResult；批量任务为逐张 [{file_name, code, result, msg}] 列表 |
| `result.error` | 对象（可为空） | FAILURE 时的错误 |
| `result.error.code` | 整数 | 业务错误码，见错误码表 |
| `result.error.msg` | 字符串 | 面向用户的提示 |
