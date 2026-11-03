# API 约定（前后端共同遵守）

> 架构层定死的东西：**返回体形状、错误码、字段命名、请求格式**。前端照此写 Axios 封装，
> 后端照此返回，报告"API 文档 / 异常处理说明"两节直接引用本文。
>
> 代码位置：错误码 [`backend/app/errors.py`](backend/app/errors.py)、返回体 [`backend/app/schemas.py`](backend/app/schemas.py)。

## 一、统一返回体

所有接口（**成功或失败**）都返回同一形状，只有三个字段，不增删：

```json
{ "code": 0, "result": { "…": "…" }, "msg": "ok" }
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `code` | int | 0 = 成功；非 0 = 错误码，见下表 |
| `result` | object / array / null | 成功时的业务数据；失败时为 `null` |
| `msg` | string | 面向用户的提示，前端可直接展示 |

**HTTP 状态码 = `code` 的前三位**（`40001` → 400，`40401` → 404，`50001` → 500）。
这样任务书要求的"400 参数错 / 404 路径错 / 500 服务器错"是 HTTP 层，业务层还能细分到具体场景。

## 二、错误码表

| 业务码 | HTTP | 场景 | 默认 msg | 触发点 |
|---:|---:|---|---|---|
| `0` | 200 | 成功 | ok | — |
| `40000` | 400 | 参数校验失败 | 参数错误 | Pydantic 校验（空查询、`top_k` 越界、`confirm=true` 却没给 `category`、非法类别名等） |
| `40001` | 400 | 图像格式错误 / 损坏 | 图像格式错误，请上传 PNG/JPG | 上传内容不是可视 PNG/JPG/WEBP |
| `40002` | 400 | 上传内容为空 | 上传内容为空 | `file` 为空字节 |
| `40003` | 400 | 查询向量维度与索引不一致 | 查询向量维度与索引不一致 | 模型与索引不同源；上传向量维度 ≠ 库维度 |
| `40004` | 400 | 上传文件过大 | 上传文件过大 | `file` 超过 `SHOPVISION_MAX_UPLOAD_MB`（默认 10 MB） |
| `40400` | 404 | 路径 / 资源不存在 | 资源不存在 | 访问了未注册的 URL |
| `40401` | 404 | 类别不存在 | 类别不存在 | `category` 不在静态索引或上传库里；入库时需先建类或选已有类别 |
| `40402` | 404 | 索引文件缺失 | 索引文件缺失 | 注册表 / items.csv / 向量文件缺失 |
| `50000` | 500 | 未捕获服务器错误 | 服务器内部错误 | 未预料异常 |
| `50001` | 500 | 模型 / 依赖不可用 | 模型或依赖不可用 | ONNX 产物缺失、`onnxruntime`/`cn_clip` 未装；占位模式禁止入库；上传库与当前模型指纹不一致 |

约定：**新增场景就加一行、取一个同前缀新码，不改老码含义**；前端按整段码定位，按前三位做兜底。

## 三、接口清单

基址 `http://localhost:8000`，版本前缀 `/api/v1`；FastAPI 自动生成的接口文档：`/docs`（Swagger UI，
可试接口）、`/scalar`（更好看的同款）、`/redoc`（阅读版）、`/openapi.json`（OpenAPI 3，可导出）。
离线可翻的那份在 `docs/交付材料/实验四_第23组/api/`。返回值结构写在后端 `app/schemas.py` 的
`*Result` 模型里，只用于生成文档，线上形状以本文为准。

### GET /api/v1/health — 健康检查

```json
{ "code": 0, "result": {
    "model_loaded": false,
    "backend": "placeholder",
    "index_dir": "…/data/index_data_finetuned",
    "categories": ["包","厨房用品","女装","家居用品","手机壳","水杯","男装","运动服","鞋"],
    "dimension": 512,
    "category_counts": { "鞋": 3219, "水杯": 2016, "…": 0 },
    "total_items": 9393,
    "category_ready": { "鞋": true, "水杯": true, "…": true },
    "updated_at": "2026-10-18T13:50:44Z",
    "model_name": "ViT-B-16",
    "model_checkpoint": "data/processed_data_retrieval/experiments/…/checkpoints/epoch3.pt"
}, "msg": "ok" }
```

`model_loaded: false` 表示当前跑占位编码器，检索结果无意义。
`category_counts` / `total_items` = 静态索引注册表快照 **+ 上传入库实时条数**；上传后无需重启，
下一次 `/health` 就能看到增量。
`category_ready` 静态类别看 `items.csv` 与 `image_embeddings.npy` 是否齐全；仅上传的新类别看
是否已有商品（0 条的空类别不参与自动判类）。
`updated_at` / `model_name` / `model_checkpoint` 只描述静态索引；上传条目不改变它们。

### POST /api/v1/image — 图像分类

- 请求：`multipart/form-data`，字段 `file`（商品图）
- 返回 `result`：

```json
{ "category": "鞋", "confidence": 0.42, "score": 0.31,
  "topk": [ { "category": "鞋", "similarity": 0.31, "confidence": 0.42 },
            { "category": "包", "similarity": 0.28, "confidence": 0.33 } ],
  "items": [ { "category": "鞋", "similarity": 0.92, "item_id": "…", "item_name": "…" } ] }
```

`topk[].confidence` 与顶层 `confidence` 同口径（对全部类别做 softmax），不是只对前 3 名归一化；
`items` 是判出类别内与上传图最相似的商品（最多 4 条），供前端做相似商品推荐。

### POST /api/v1/text — 文本检索

- 请求：`application/json`

```json
{ "query": "白色运动鞋", "top_k": 5, "category": "鞋" }
```

`category` 可省略（搜全部）；`top_k` 取值 1–50。

- 返回 `result`：

```json
{ "query": "白色运动鞋", "category": "鞋",
  "query_category": "鞋", "query_score": 0.63,
  "items": [ { "category": "鞋", "similarity": 0.63, "item_name": "…", "product_type": "鞋", "brand": "…" } ] }
```

`category` 是本次检索实际使用的范围（用户限定值；未限定时为命中 top-1 的类别）。
`query_category` / `query_score` 是文本塔独立判出的类别与原始相似度，不受 `category`
影响。当 `category` 与 `query_category` 不一致时，视为“用户限定”与“查询语义”没有
交集，后端直接返回空 `items`；前端应提示并引导用户改搜 `query_category` 或全部类别，
而不是把限定值当成模型判断。

### POST /api/v1/match — 图文匹配

- 请求：`multipart/form-data`，字段 `file`（图）+ `text`（文本）+ 可选 `top_k`
- 流程：图像分类 → 文本检索 → 比对类别是否一致
- 返回 `result`：

```json
{ "match": false, "image_category": "手机壳", "text_category": "包",
  "image_confidence": 0.91, "image_score": 0.37, "image_type": "女士小板鞋",
  "text_confidence": 0.88, "text_score": 0.33,
  "text_type": "休闲鞋", "items": [ … ] }
```

`image_confidence` / `text_confidence` 是两塔各自对判出类别做 softmax 的概率，分母是
**全部可判类别**（静态 9 类 + 达到门槛的新类别），不是只对前 3 名归一化；
`image_type` / `text_type` 是各自类别内最相似商品的细分类，用于解释判断；
`items` 是文本检索证据。细分类是**检索证据**，不是模型直接预测的细分类。

### 数据入库（新增）— POST /api/v1/admin/items、POST /api/v1/admin/categories

> **本轮未做管理鉴权**：任何能访问 8000 端口的人都能写入。只允许本机演示，禁止公网暴露；
> Vite 代理会让请求看起来来自本机，不能当鉴权。后续再加 `X-Admin-Token`。
> 入库必须跑真实 ONNX；`placeholder` 模式下写库返回 `50001`。

#### POST /api/v1/admin/items — 上传商品入库

- 请求：`multipart/form-data`
  - `file`：商品图（PNG/JPG/WEBP，≤10 MB）
  - `category`：目标类别；`confirm=false` 时可省略
  - `confirm`：`true` 才真正写库；缺省或 `false` 只返回建议
  - `create_category`：`true` 时类别不存在就自动建类
  - 可选元数据：`item_name`、`type`、`color`、`material`、`brand`、`description`
- 只传 `file`（或 `confirm=false`）：返回图像塔建议，**不写库**：

```json
{ "code": 0, "result": {
    "created": false, "duplicate": false, "item_id": null, "category": null,
    "similarity": null,
    "suggested_category": "鞋", "suggested_score": 0.31,
    "topk": [ { "category": "鞋", "similarity": 0.31 }, { "category": "包", "similarity": 0.28 } ],
    "created_at": null, "item": null
}, "msg": "ok" }
```

- `confirm=true` 且带 `category`：真正写库；`similarity` 是写入前目标类别内的最近邻
  （空类别为 `null`），`item` 是写回条目：

```json
{ "code": 0, "result": {
    "created": true, "duplicate": false,
    "item_id": "upload_1a2b3c4d5e6f", "category": "鞋",
    "similarity": 0.92,
    "suggested_category": "鞋", "suggested_score": 0.31,
    "topk": [ … ], "created_at": "2026-11-03T06:00:00Z",
    "item": { "item_id": "upload_…", "category": "鞋", "item_name": "…",
              "local_image_path": "data/processed_data_cleaning/鞋/images/upload_….png",
              "image_height": 800, "image_width": 600, "created_at": "…" }
}, "msg": "ok" }
```

- 同一张图重复上传：`duplicate=true`、`created=false`，返回原 `item_id`，计数不增。
- `confirm=true` 却没给 `category` → `40000`；类别不存在且 `create_category=false` → `40401`；
  类别名含路径分隔符 / 控制字符 / Windows 保留名 → `40000`。
- 上传成功后立即写进内存索引缓存（`IndexStore.reload`），`/image`、`/text`、`/match` 无需重启即可检索到。
- **新类别是检索桶，不是模型重新训练**：类别名不会进入模型词表；1 件商品即可参与自动判类
  （`SHOPVISION_NEW_CATEGORY_MIN_ITEMS` 默认 1），样本越多越稳。

#### POST /api/v1/admin/categories — 新建空类别

- 请求：`application/json`：`{ "name": "测试类" }`
- 返回：

```json
{ "code": 0, "result": { "created": true, "name": "测试类" }, "msg": "ok" }
```

已存在时 `created=false`。空类别会出现在 `/health.categories` 与前端类别列表里，但**不参与
自动判类**；显式 `/text` 限定该类别返回空 `items`，上传首条商品后即参与。

### 异步任务（批量 / 大图）— Celery + Redis

### 异步任务（批量 / 大图）— Celery + Redis

同步接口每次只处理一张图、且必须在请求内算完；批量或大图改走任务队列：**先提交拿
`task_id`，前端轮询状态，`SUCCESS` 后取结果**。三张表共用同一个统一返回体。

#### POST /api/v1/tasks/image — 提交单张图片异步分类

- 请求：`multipart/form-data`，字段 `file`（校验同 `/image`，坏图直接 400，不入队）
- 返回 `result`：`{ "task_id": "…", "status": "PENDING", "total": null }`

#### POST /api/v1/tasks/batch — 提交批量图片异步分类

- 请求：`multipart/form-data`，字段 `files`（可重复，单批上限
  `SHOPVISION_ASYNC_BATCH_MAX_FILES`，默认 12；任意一张不过校验整批 400）
- 返回 `result`：`{ "task_id": "…", "status": "PENDING", "total": 5 }`

#### GET /api/v1/tasks/{task_id} — 轮询任务状态

- 返回 `result`：

```json
{ "task_id": "…", "status": "PROGRESS",
  "progress": { "done": 2, "total": 5 }, "result": null, "error": null }
```

| `status` | 含义 | 前端动作 |
|---|---|---|
| `PENDING` | 排队中（**不存在的 task_id 也返回这个**，Celery 语义） | 继续轮询 |
| `PROGRESS` | 执行中，`progress` 给出已完成 / 总数 | 继续轮询（约 800ms） |
| `SUCCESS` | 完成，`result` 是业务数据 | 停止轮询，渲染结果 |
| `FAILURE` | 失败，`error: {code, msg}` | 停止轮询，按 `msg` 提示 |

- 单图任务 `SUCCESS` 时 `result` 与 `/image` 的 `result` 同形；
- 批量任务 `SUCCESS` 时 `result` 是数组，每项在单图返回体基础上多一个 `file_name`：

```json
[ { "code": 0, "result": { "category": "鞋", "confidence": 0.42, "topk": [ … ] },
    "msg": "ok", "file_name": "a.png" }, … ]
```

- 队列不可用（Redis 不可达 / worker 没起）时，提交接口返回 `50001`
  「任务队列不可用：请确认 SHOPVISION_CELERY_BROKER_URL 指向的 Redis 可达」；
  三个同步接口不受影响。

## 四、前端约定（zzx / lfsy 照此写 Axios）

- 图像接口用 `FormData`（`multipart/form-data`），文本接口用 JSON。
- 统一拦截：`HTTP 非 2xx` 或 `code != 0` 都当作错误，直接把 `msg` 弹给用户——`msg` 是给人看的。
- 错误码前三位决定处理方式：4xx 提示用户改输入；5xx 提示"服务异常，稍后重试"。
- dev 环境 `vite.config.js` 把 `/api` 代理到 `http://localhost:8000`，绕开跨域。

## 五、命名与版本

- URL 用名词 + 版本：`/api/v1/image`、`/api/v1/text`、`/api/v1/match`、
  `/api/v1/admin/items`、`/api/v1/admin/categories`；方法对应动作。
- JSON 字段用 `snake_case`（与后端 Python 一致），不混 `camelCase`。
- 不新增返回字段、不改老码含义；要改就升 `/api/v2`（例外：`/match` 已追加
  `image_confidence` / `image_score` / `image_type` / `text_confidence` / `text_score` /
  `text_type`；`/health` 追加 `category_ready` / `updated_at` / `model_name` /
  `model_checkpoint`；`/image` 追加 `topk[].confidence` 与 `items`；`/text` 追加
  `query_category` / `query_score`；新增 `/admin/items` 与 `/admin/categories`。
  以上新增均为纯扩展。`/health` 的 `categories` / `category_counts` / `total_items` /
  `category_ready` 字段名不变，但口径从“仅静态索引”扩展为“静态索引 + 上传入库”；
  这是增量入库带来的口径变化，不是字段改名）

## 六、现状提醒

`.env.example` 默认 `SHOPVISION_MODEL_BACKEND=placeholder`，只用于跑通链路；当前仓库的
`webapp/backend/.env` 已切到 `onnx`，`/health` 返回 `backend=onnx`、`model_loaded=true`。
以 `/health` 为准；报告里的实测推理延迟与检索指标只在 `onnx` 模式下记录。

上传入库同样必须跑 `onnx`：占位模式写库会被拒绝（`50001`），避免随机向量污染真实索引。
上传数据落 `data/webapp.db`（SQLite）与 `data/processed_data_cleaning/<类别>/images/upload_*`，
两者都是运行产物、默认 gitignore；静态索引 `data/index_data_finetuned/` 始终保持只读。
切换 ONNX 产物后 `model_tag` 变化，旧上传库会被拒绝写入；备份并删除 `data/webapp.db` 后重新入库。