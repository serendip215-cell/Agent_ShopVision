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
| `result.index_dir` | 字符串 | 索引目录 |
| `result.categories` | 字符串 的数组 | 索引里注册的类别 |
| `result.dimension` | 整数（可为空） | 向量维度 |
| `result.category_counts` | 对象 | 各类索引条数（构建时快照） |
| `result.total_items` | 整数 | 索引总条数 |

### 图像分类页

> 对应前端「图像分类」页面

#### `POST /api/v1/image` — 图像分类

上传商品图 → 图像塔编码成 512 维向量 → 与索引里 9 类向量比相似度 → 返回最可能的类别、置信度与相似商品类别排序。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `file` | 文件 | 文件 | 是 | 商品图（PNG/JPG/WEBP，≤10 MB） |

**返回**（`result` 结构如下；`code`/`msg` 见基础约定）

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | 整数 | 0=成功；非 0 见错误码表 |
| `msg` | 字符串 | 面向用户的提示 |
| `result.category` | 字符串（可为空） | 判出的类别：9 类里相似度最高的那个 |
| `result.confidence` | 小数 | 对 9 类最高分做 softmax 后的概率 |
| `result.score` | 小数（可为空） | 该类原始相似度 |
| `result.topk` | 对象 的数组 | 各类最高分，降序前 3 |
| `result.topk[].category` | 字符串 | 类别名 |
| `result.topk[].similarity` | 小数 | 该类最高余弦相似度 |

### 文本检索页

> 对应前端「文本检索」页面

#### `POST /api/v1/text` — 文本检索

中文查询 → 文本塔编码 → 在商品库里按余弦相似度取 top_k。`category` 留空表示搜全部类别。

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
| `result.items[].local_image_path` | 字符串（可为空） | 原图相对路径 |
| `result.items[].image_status` | 字符串（可为空） | 图片处理状态 |
| `result.items[].image_height` | 字符串（可为空） | 图高（CSV 原样字符串） |
| `result.items[].image_width` | 字符串（可为空） | 图宽（CSV 原样字符串） |

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
| `result.image_confidence` | 小数 | 图像塔对判出类别的置信度（9 类最高分 softmax） |
| `result.image_score` | 小数（可为空） | 图像塔该类别原始相似度 |
| `result.image_type` | 字符串（可为空） | 图像塔细分类：图像判出类别内最相似商品的 type |
| `result.text_confidence` | 小数 | 文本塔对判出类别的置信度（9 类最高分 softmax） |
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
| `result.items[].local_image_path` | 字符串（可为空） | 原图相对路径 |
| `result.items[].image_status` | 字符串（可为空） | 图片处理状态 |
| `result.items[].image_height` | 字符串（可为空） | 图高（CSV 原样字符串） |
| `result.items[].image_width` | 字符串（可为空） | 图宽（CSV 原样字符串） |

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
