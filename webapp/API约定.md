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
| `40000` | 400 | 参数校验失败 | 参数错误 | Pydantic 校验（空查询、`top_k` 越界等） |
| `40001` | 400 | 图像格式错误 / 损坏 | 图像格式错误，请上传 PNG/JPG | 上传内容不是可视 PNG/JPG/WEBP |
| `40002` | 400 | 上传内容为空 | 上传内容为空 | `file` 为空字节 |
| `40003` | 400 | 查询向量维度与索引不一致 | 查询向量维度与索引不一致 | 模型与索引不同源 |
| `40004` | 400 | 上传文件过大 | 上传文件过大 | `file` 超过 `SHOPVISION_MAX_UPLOAD_MB`（默认 10 MB） |
| `40400` | 404 | 路径 / 资源不存在 | 资源不存在 | 访问了未注册的 URL |
| `40401` | 404 | 类别不存在 | 类别不存在 | `category` 不在索引注册表里 |
| `40402` | 404 | 索引文件缺失 | 索引文件缺失 | 注册表 / items.csv / 向量文件缺失 |
| `50000` | 500 | 未捕获服务器错误 | 服务器内部错误 | 未预料异常 |
| `50001` | 500 | 模型 / 依赖不可用 | 模型或依赖不可用 | ONNX 产物缺失、`onnxruntime`/`cn_clip` 未装 |

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
    "dimension": 512
}, "msg": "ok" }
```

`model_loaded: false` 表示当前跑占位编码器，检索结果无意义。

### POST /api/v1/image — 图像分类

- 请求：`multipart/form-data`，字段 `file`（商品图）
- 返回 `result`：

```json
{ "category": "鞋", "confidence": 0.42, "score": 0.31,
  "topk": [ { "category": "鞋", "similarity": 0.31 }, { "category": "包", "similarity": 0.28 } ] }
```

### POST /api/v1/text — 文本检索

- 请求：`application/json`

```json
{ "query": "白色运动鞋", "top_k": 5, "category": "鞋" }
```

`category` 可省略（搜全部）；`top_k` 取值 1–50。

- 返回 `result`：

```json
{ "query": "白色运动鞋", "category": "鞋",
  "items": [ { "category": "鞋", "similarity": 0.63, "item_name": "…", "product_type": "鞋", "brand": "…" } ] }
```

### POST /api/v1/match — 图文匹配

- 请求：`multipart/form-data`，字段 `file`（图）+ `text`（文本）+ 可选 `top_k`
- 流程：图像分类 → 文本检索 → 比对类别是否一致
- 返回 `result`：

```json
{ "match": false, "image_category": "手机壳", "text_category": "包", "items": [ … ] }
```

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

- URL 用名词 + 版本：`/api/v1/image`、`/api/v1/text`、`/api/v1/match`；方法对应动作。
- JSON 字段用 `snake_case`（与后端 Python 一致），不混 `camelCase`。
- 不新增返回字段、不改老码含义；要改就升 `/api/v2`。

## 六、现状提醒

当前 `SHOPVISION_MODEL_BACKEND=placeholder`：接口形状、错误码、数据流都已联调通过，
但**检索结果无意义**（占位向量 vs 真实索引）。报告里不写实测推理延迟与检索指标，
等双塔 ONNX 到位切 `onnx` 后再出这些数字。