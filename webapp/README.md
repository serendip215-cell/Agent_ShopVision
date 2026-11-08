# webapp — 实验四前后端

面向本项目的具体写法与运行说明。分工见 [`docs/流程与交接/实验四流程与分工.md`](../docs/流程与交接/实验四流程与分工.md)，
接口契约见 [`API约定.md`](API约定.md)。

## 〇、这个系统最终是什么（先看这一段）

一句话：**用户给一张商品图或一句中文查询，后端用实验三的双塔模型编码，在 9 类商品库（9,393 条）里检索，
返回类别与相似商品；管理员还可以把新商品图增量写进已有类别或新类别。**

### 1. 三个功能 = 任务书要的三个页面（外加一个商品入库页）

| 页面 | 用户怎么用 | 屏幕上看什么 | 后端接口 |
|---|---|---|---|
| 图像分类 | 拖 / 选一张商品图 → 点「分析」 | 判出的类别 + 置信度，下面列相似商品（名称 / 类别 / 相似度） | `POST /api/v1/image` |
| 文本检索 | 输入「白色运动鞋」→ 类别可选 → 点「搜索」 | 相关商品列表（名称、类别、相似度） | `POST /api/v1/text` |
| 图文匹配 | 同时传图 + 输文本 → 点「匹配」 | 图判出的类别 vs 文判出的类别；一致显示「匹配」，不一致把两个类别都摆出来 | `POST /api/v1/match` |
| 商品入库 | 选图 → 看模型建议 → 选已有类别或输入新类别 → 确认 | 建议类别、候选相似度、写入后的 `item_id` 与入库时间 | `POST /api/v1/admin/items`、`POST /api/v1/admin/categories` |

### 2. 用户实际的一次操作（图像分类为例）

1. 打开 `http://localhost:5173`，导航栏三个页签。
2. 「图像分类」页选一张商品图。
3. 点「分析」→ 前端 axios 发 `POST /api/v1/image`（FormData）。
4. 后端：校验图片（≤10 MB、真是图片）→ 图像塔编码成 512 维向量 → 与 9 类向量比相似度 → 取最大那一类。
5. 返回 `{"code":0,"result":{"category":"鞋","confidence":0.42,"topk":[…]}}`，前端渲染类别标签 + 相似商品列表。
6. 传错东西（txt、超大图、模型没装）→ 后端回 `40001` / `40004` / `50001` + 中文 `msg`，前端直接弹提示。

### 3. 跑通后「能用」的验收口径

**能用**：传图出类别并给相似商品；中文查询出商品；图文比对出是否一致；错得明明白白有中文提示；
`/docs` 能看接口文档；三浏览器打开正常、手机屏不塌。

**不做**（明确划出去，报告里如实写）：登录注册、下单、管理鉴权、商品编辑/删除、多实例同时写入、
模型训练（那是实验三的事）。静态索引保持只读；上传数据用 SQLite 增量持久化，不是把整库重训。
批量 / 大图异步走 Celery + Redis，属于加分项，已经做了（见 §二.5），Redis 可以用云端免费层。

### 4. 怎么实现的（数据流）

```
浏览器 React 页面（三页签）
   │ axios  →  POST /api/v1/{image|text|match}
   ▼
api/v1.py  FastAPI 路由     ← 只校验参数，不写业务
   ▼
services/matching.py  MatchService   业务编排
   ├─ Encoder     双塔 ONNX 各编一路 → 512 维 L2 归一化向量
   ├─ IndexStore  data/index_data_finetuned 的 9 类静态向量 + items.csv 元数据
   └─ UploadStore SQLite 增量上传库；读时与静态索引按类别合并
   ▼
{code, result, msg}  →  前端渲染 / 弹中文错误
```

两个接缝，换东西不动代码：**模型**（`.env` 的 `model_backend=placeholder|onnx`）、
**索引**（换 `deps.get_index`）。

### 5. 演示流程（答辩 / 录屏用，qxy 收素材）

1. 图像分类页传一张鞋图 → 出「鞋」+ 相似商品（这条也用来测"前端展示延迟 ≤ 2 秒"）。
2. 文本页搜「白色运动鞋」→ 出鞋类商品。
3. 匹配页**故意**传鞋图 + 输「双肩包」→ 显示不匹配、两个类别都列出来——最能说明"双塔各编各判、再比对"。

> 模型产物没到位之前（见下节「现状」），流程能走通但**结果是占位向量算的，无意义**；
> 置信度、相似度这类数字等切到真 ONNX 再写进报告。

## 一、现状（2026-11-08 更新）

| 项 | 状态 |
|---|---|
| **后端** | ✅ 可跑。`backend/app/` 分层完成，同步三接口 + 异步任务（Celery）均已自检通过。**注：`/api/v1/agent/chat` 尚未实现**（属实验五 5.4） |
| **前端** | ✅ **8 页已实现**（React 19 + Antd），dev 代理 `/api`、`/item-images` 到后端。含实验五对话导购页 `AgentChat.jsx`（路由 `/agent`），等后端接口 |
| 模型产物（双塔 ONNX） | ✅ 已拉取到本地（`scripts/fetch_model_assets.py` 从 GitHub Release 下载并校验 sha256），`.env` 切 `onnx` 即用 |

编码器是可替换接缝，`SHOPVISION_MODEL_BACKEND` 一行配置切换占位 / ONNX；接口形状不变。

## 二、跑起来

### 1. 建虚拟环境并装依赖

```powershell
cd webapp\backend

py -3 -m venv .venv                 # 建虚拟环境（.venv 已在 .gitignore 里）
.\.venv\Scripts\Activate.ps1        # PowerShell 激活
# 若用 cmd：         .venv\Scripts\activate.bat
# 若用 Git Bash：    source .venv/Scripts/activate

pip install -r requirements.txt
```

> 依赖：fastapi / uvicorn / pydantic(-settings) / numpy / pillow / python-multipart（+ httpx 仅测试用）
> / celery + redis（异步任务，见 §二.5）。
> 接真 ONNX 才需要 `onnxruntime` 与 Chinese-CLIP，见 `requirements.txt` 注释。
> 规范工具单独装：`pip install black ruff mypy`（不在运行依赖里，CI 与本地各自装）。

### 2. 配置

```powershell
copy .env.example .env              # 默认 placeholder，开箱即用
```

#### 2.1 增量入库配置（可选）

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `SHOPVISION_DB_PATH` | `data/webapp.db` | 上传商品库（SQLite），运行产物，已 gitignore |
| `SHOPVISION_IMAGE_ROOT` | `data/processed_data_cleaning` | 静态清洗图根目录；`/item-images` 挂这里 |
| `SHOPVISION_UPLOAD_IMAGE_ROOT` | `data/uploaded_data` | 上传原图根目录；`/item-uploads` 挂这里 |
| `SHOPVISION_RAW_IMAGE_ROOT` | `data/raw_data` | 原始商品图根目录；`/item-originals` 挂这里 |
| `SHOPVISION_NEW_CATEGORY_MIN_ITEMS` | `1` | 新类别至少几条才参与自动判类 |

> 上传入库必须 `SHOPVISION_MODEL_BACKEND=onnx`；占位模式写库返回 `50001`，防止随机向量污染索引。
> 本轮未做管理鉴权，只允许本机演示，不要把 8000 端口暴露到公网。

### 3. 启动

```powershell
uvicorn app.main:app --reload --port 8000
```

- 接口文档（自动生成，见 §三）：http://localhost:8000/docs （还有 `/scalar`、`/redoc`）
- 健康检查：http://localhost:8000/api/v1/health

### 4. 自检

```powershell
python -m unittest discover -s tests -v
```

不依赖仓库大索引（自建小索引），覆盖检索、占位编码器、接口返回与错误码。

代码规范（配置统一在 [`backend/pyproject.toml`](backend/pyproject.toml)，行宽 100）：

```powershell
black --check .                     # 格式   black . 直接改
ruff check .                        # 静态   ruff check --fix . 自动修
mypy .                              # 类型   可选依赖缺装不算错（已配 overrides）
```

> **硬规则**：动过 `webapp/backend/**/*.py` 的提交，本地四条（black / ruff / mypy / unittest）
> 全绿才能推；CI 会复核同一套，红叉不许留着过夜。不许改 `pyproject.toml`、加 `# noqa`
> 或 `# type: ignore` 来绕红——规则松紧找 何朝杨 改，全组同步。
> 用 AI 改后端时，把这一段连同本 README 一起给它看。详见
> [`docs/流程与交接/实验四流程与分工.md` §七](../docs/流程与交接/实验四流程与分工.md)。
>
> CI：改动 `webapp/**` 推送或提 PR 时，GitHub Actions 自动跑这套
> （[`.github/workflows/backend-tests.yml`](../.github/workflows/backend-tests.yml)）。

### 5. 异步任务（批量 / 大图）——Celery + Redis

**三个同步接口不依赖 Redis，上面几步跑起来就能用。** 只有批量识别和 >2 MB 大图走任务队列，
需要额外起一个 worker（Redis 可以云端托管，不必本机装）：

1. **Redis 用组内共享的那台**：`1.95.164.146:4141`（Redis 7.0.15，16 个 DB），地址已经写在
   `.env.example` 里，`copy .env.example .env` 后直接可用；要换自己的就改这两行。
   云端 TLS 用 `rediss://` 前缀；队列用 `/0`，结果用 `/1`。

   ```env
   SHOPVISION_CELERY_BROKER_URL=redis://default:<密码>@1.95.164.146:4141/0
   SHOPVISION_CELERY_RESULT_BACKEND=redis://default:<密码>@1.95.164.146:4141/1
   ```

2. **另开一个终端起 worker**（在 `webapp\backend` 下；Windows 没有 prefork，必须 `--pool=solo`）：

   ```powershell
   .\.venv\Scripts\Activate.ps1
   celery -A app.celery_app worker --loglevel=info --pool=solo
   ```

3. **前端自动用**：图像分类页「批量测试」选多张（≤12 张），或单张 >2 MB，前端会先
   `POST /api/v1/tasks/{image|batch}` 拿 `task_id`，再按 800 ms 轮询 `GET /api/v1/tasks/{task_id}`，
   显示「第几张 / 共几张」，完成后把每张结果填回历史卡片。

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `SHOPVISION_CELERY_BROKER_URL` | `redis://localhost:6379/0` | 任务队列地址 |
| `SHOPVISION_CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | 结果存储（与队列分库） |
| `SHOPVISION_CELERY_RESULT_EXPIRES` | `3600` | 结果保留秒数 |
| `SHOPVISION_ASYNC_BATCH_MAX_FILES` | `12` | 单批上限，与前端一致 |
| `SHOPVISION_CELERY_ALWAYS_EAGER` | `false` | 设 `true` 时任务在进程内同步执行（CI / 无 Redis 冒烟） |

> Redis 不可达时**只有异步提交接口**返回 `50001` 并提示检查 broker 地址，
> 同步接口照常工作，页面不会整体挂掉。

## 三、接口与调用

基址 `http://localhost:8000`，前缀 `/api/v1`；返回体统一 `{code, result, msg}`，
错误码表见 [`API约定.md`](API约定.md)。

| 方法 | 路径 | 用途 | 请求 |
|---|---|---|---|
| GET | `/api/v1/health` | 健康检查 | — |
| POST | `/api/v1/image` | 图像分类 | `multipart/form-data`：`file` |
| POST | `/api/v1/text` | 文本检索 | `application/json`：`{query, top_k?, category?}` |
| POST | `/api/v1/match` | 图文匹配 | `multipart/form-data`：`file` + `text` + `top_k?` |
| POST | `/api/v1/admin/items` | 上传商品入库 | `multipart/form-data`：`file` + `category?` + `confirm?` + `create_category?` + 元数据 |
| POST | `/api/v1/admin/categories` | 新建空类别 | `application/json`：`{name}` |
| POST | `/api/v1/tasks/image` | 提交单张异步分类（大图） | `multipart/form-data`：`file` → `{task_id}` |
| POST | `/api/v1/tasks/batch` | 提交批量异步分类 | `multipart/form-data`：`files`（≤12）→ `{task_id}` |
| GET | `/api/v1/tasks/{task_id}` | 轮询任务状态 | — |

异步三个接口的 `status` 流转、批量结果里多出的 `file_name`、队列不可用时的 `50001`，
见 [`API约定.md`](API约定.md)「异步任务」一节。

### 接口文档（FastAPI 内置，不用装插件）

Java 那边用 springdoc / knife4j 挂 Swagger，FastAPI 是**自带**的，开服务就有：

| 地址 | 是什么 | 谁来用 |
|---|---|---|
| `/docs` | Swagger UI，能直接点着发请求试（等价于 Java 的 Knife4j） | 联调、演示、截图 |
| `/scalar` | Scalar，比 Swagger UI 现代、能折叠分组，同样能直接调 | 答辩演示、给人看 |
| `/redoc` | ReDoc，排版舒服的阅读版 | 写报告 API 文档那一节 |
| `/openapi.json` | OpenAPI 3 规范，机器可读 | 导给别人 / 喂 Postman |

接口分组按页面走（状态 / 图像分类页 / 文本检索页 / 多模态匹配页 / 数据入库 / 异步任务），每个接口都带
summary、description、参数说明、**返回值结构**与可能的错误码（400/404/500）。
所以 **wlz 写 API 文档那一节，直接把 `/docs` 里内容整理成表格即可**，不用猜。

三份都是同一个来源（后端代码 + `app/schemas.py` 的结果模型），改接口自动跟着变；
`/docs`、`/scalar` 的前端资源走 CDN，**离线环境打不开**，离线看用下面这份 md。

### 怎么用（点开之后按哪几下）

先把服务跑起来（§二.3），然后照下面的走法挑一种：

**A. 点着调接口**（联调 / 答辩演示 / 录屏截图）

1. 开 `http://localhost:8000/docs`（想要好看点就开 `/scalar`，点法一模一样）
2. 展开 **文本检索页** → 右上角 **Try it out**
3. 请求体填 `{"query": "白色运动鞋", "top_k": 3}` → **Execute**
4. 下面 `Response body` 就是真实返回，`{code: 0, result: {...}}`；
   **图像分类页 / 多模态匹配页** 那两组点 **Choose File** 选一张商品图再 Execute，文件上传同样走得通

**B. 不起服务也要翻**（写报告 / 给评审看）

直接打开 `docs/交付材料/实验四_第23组/api/API文档.md`——VSCode 里按 `Ctrl+Shift+V` 是渲染后的预览。

**C. 拿去接前端 / 导工具**

Postman **Import → File** 选中 `openapi.json`，九个请求（含文件上传字段）自动建好；
也可以把这份 json 直接丢给 AI，让它照着发请求。

**按人分工**

- **zzx / lfsy**：照 `/docs` 里「图像分类页 / 文本检索页 / 多模态匹配页」三组的请求格式写 Axios 封装；
  每个字段的说明就是前端提示文案的来源。
- **wlz**：拿 `API文档.md` 当报告要求 3 的底稿，再补上本节末尾的 curl 调用示例。
- **验收 / 交付**：三个接口各 Execute 一次，`Response body` 截图（这就是「接口联调通过」的证据）。

### 离线版（交付材料，不用起服务）

```powershell
python scripts/export_api_docs.py     # 在 webapp/backend 下跑
```

生成到 `docs/交付材料/实验四_第23组/api/`：

| 文件 | 用途 |
|---|---|
| `API文档.md` | 人读版：路径/方法/参数/**返回值字段表**/错误码表，可离线翻、可直接贴报告 |
| `openapi.json` | 机器可读，导入 Postman / Apifox，或喂给 AI 让它照着调 |

它是**生成的**，改了接口重跑一遍即可；别手改那份 md（wlz 要润色就在报告正文里改）。
有测试盯着生成结果（`ExportApiDocsTest`），生成出半截内容会当场红。

> 返回值的字段结构来自 `app/schemas.py` 里的 `*Result` 模型（`ImageResult` / `TextResult` / …），
> 它们**只用于生成文档**：线上 JSON 形状仍由 [`API约定.md`](API约定.md) 冻结，模型只描述不改形状。
> 有测试盯着这点（`OpenApiTest`：三个字段不变、result 必须是有形状的模型而不是 `Any`）。

调用示例（PowerShell / Windows 自带 curl）：

```powershell
# 健康检查
curl.exe http://localhost:8000/api/v1/health

# 图像分类
curl.exe -X POST http://localhost:8000/api/v1/image -F "file=@data\processed_data\鞋\images\xxx.jpg"

# 文本检索
curl.exe -X POST http://localhost:8000/api/v1/text -H "Content-Type: application/json" -d "{\"query\":\"白色运动鞋\",\"top_k\":3}"

# 图文匹配
curl.exe -X POST http://localhost:8000/api/v1/match -F "file=@xxx.jpg" -F "text=白色运动鞋"

# 商品入库（先只传图看建议，不写库）
curl.exe -X POST http://localhost:8000/api/v1/admin/items -F "file=@xxx.jpg"

# 商品入库（确认写入已有类别；新类别加 create_category=true）
curl.exe -X POST http://localhost:8000/api/v1/admin/items -F "file=@xxx.jpg" -F "category=鞋" -F "confirm=true"

# 新建空类别
curl.exe -X POST http://localhost:8000/api/v1/admin/categories -H "Content-Type: application/json" -d "{\"name\":\"测试类\"}"
```

> 入库需要 `SHOPVISION_MODEL_BACKEND=onnx`；占位模式会被拒绝（`50001`）。本轮无管理鉴权，只在本机演示。
> 上传的商品图原样落到 `data/uploaded_data/<类别>/images/`，元数据与向量落在 `data/webapp.db`。

Python 客户端：

```python
import requests
print(requests.get("http://localhost:8000/api/v1/health").json())
print(requests.post("http://localhost:8000/api/v1/text", json={"query": "白色运动鞋", "top_k": 3}).json())
```

> `health` 里 `model_loaded: false` = 当前占位模式，**检索结果无意义**；`true` = 已接真 ONNX。

### 商品入库（增量数据，2026-11-03 起）

前端「商品入库」页（`/admin`）走的就是下面两步，不写库那一步可以单独调接口验证：

1. **选图看建议**：只传 `file`，图像塔给出 `suggested_category` 与 top3，**不写库**。
2. **确认写入**：`confirm=true` + `category`；类别不存在时勾新类别 → 后端 `create_category=true` 自动建类。

| 落点 | 内容 |
|---|---|
| `data/webapp.db` | SQLite：类别、条目元数据、512 维向量、去重指纹 `image_sha256` |
| `data/uploaded_data/<类别>/images/upload_*` | 上传原图，经 `/item-uploads` 提供 |
| `data/processed_data_cleaning/<类别>/images/` | 静态索引的清洗图，经 `/item-images` 提供 |
| `data/raw_data/*/images/` | 静态条目的原始商品图，经 `/item-originals` 提供给前台展示 |
| `data/index_data_finetuned/` | 静态索引，**只读不动** |

- 写库后 `IndexStore.reload(category)`，`/image`、`/text`、`/match` 无需重启即可检索到；`/health` 计数同步变化。
- 同一张图重复上传走 `image_sha256` 去重，返回原 `item_id`，计数不增。
- 新类别是**检索桶**，不是模型重新训练：类别名不进模型词表，1 件商品即参与自动判类（`SHOPVISION_NEW_CATEGORY_MIN_ITEMS`）。
- 空类别（只建类不传图）会出现在 `/health.categories`，但不参与自动判类，显式 `/text?category=` 返回空。
- 选图建议会附带细分类/颜色/材质：取同类最相似 5 条商品投票，入库页自动预填、可修改；图像分类页也展示这组参考值。这是检索参考值，不是训练过的属性识别模型。
- TODO：后续接入大模型或监督属性头直接识别属性，替换 `MatchService._attributes_from_hits` 即可，接口字段不变。

批量导入目录（按类别建子目录，子目录名即类别；也可整目录指定一个类别）：

```bash
cd webapp/backend
# D:/新商品/鞋/*.jpg、D:/新商品/包/*.jpg → 两个类别
python scripts/bulk_ingest.py D:/新商品

# 整个目录都算「鞋」；新类别要显式允许
python scripts/bulk_ingest.py D:/新商品 --category 鞋 --create-category

# 类别文件夹下面还有分子目录时
python scripts/bulk_ingest.py D:/新商品 --recursive --create-category
```

脚本复用同一套 ONNX 图像塔与 `UploadStore`：原图落盘、向量写库、按 `image_sha256` 去重，逐张打印新增/重复/失败并在结尾汇总。**导入完要重启 uvicorn**——脚本是独立进程，正在运行的后端看不到它写入的新条目。
- `placeholder` 模式拒绝写库；切换 ONNX 产物后 `model_tag` 变化，旧库需备份删除后重建。
- Celery worker 是独立进程，有自己那份索引缓存：同步接口立即生效，异步任务要重启 worker 才看得到新条目。

## 四、后端架构（分层与扩展点）

```
app/
├── main.py            FastAPI 实例、CORS、全局异常处理
├── config.py          Settings（环境变量 / .env）
├── schemas.py         请求体、统一返回体、结果模型（后两者供 /docs 生成文档）
├── errors.py          错误码枚举 + 业务异常
├── deps.py            依赖注入：编码器 / 索引 / 服务
├── celery_app.py      Celery 实例（broker / result backend 来自环境变量）
├── tasks.py           Celery 任务：单图 / 批量分类（读临时文件，回报进度）
├── api/v1.py          路由（Controller）：只取参、校验、调服务
├── api/admin.py       数据入库路由：上传商品 / 新建类别
├── api/tasks.py       异步任务路由：提交 → 返回 task_id，轮询 → 状态 + 结果
└── services/
    ├── encoder.py     编码器接缝：PlaceholderEncoder / OnnxEncoder（带 model_tag 指纹）
    ├── index_store.py 数据访问：静态索引 + 上传库按类别合并
    ├── upload_store.py SQLite 增量库：事务写入、去重、路径安全
    └── matching.py    业务：status / 图像分类 / 文本检索 / 图文匹配 / 入库
```

调用方向**单向**：`api → services → 数据访问`。

| 想改什么 | 动哪里 | 会不会牵动别处 |
|---|---|---|
| 换模型（占位 ↔ ONNX） | `.env` 的 `model_backend` + 路径 | 不改代码 |
| 加一个接口 | `api/v1.py` 加路由 + `matching.py` 加方法 | 不动其它层 |
| 换索引来源 / 存储 | 新写一个类，换 `deps.get_index` | api 层不动 |
| 增量入库 / 加新类别 | `services/upload_store.py` + `POST /admin/*` | 静态索引保持只读 |
| 改错误码 / 文案 | `errors.py` 一张表 | 全局一致 |
| 加鉴权 / 限流 | `deps.py` 加依赖 + `api/v1.py` 挂 `Depends` | 业务层不动 |

**已做到的解耦**：api 不写业务、services 不碰 HTTP；模型、索引、配置都从代码里抽成接缝或注入；
错误码集中一处；测试用 `dependency_overrides` 注入假服务，不需要真模型。

**已知取舍（有意为之，不是漏做）**：
- services 抛的是带 HTTP 状态码的 `ApiError`——省一层映射，代价是服务层知道 HTTP 语义；
  真要多协议复用时再拆成领域异常 + 适配层。
- `IndexStore` 首次访问某类时整块读入内存（不 mmap，避免 Windows 文件句柄锁），
  9 类全用约 120 MB；数据量再大就换 mmap 或向量库。
- `deps` / `get_settings` 用 `lru_cache` 做单例，改 `.env` 需重启进程。
- 上传图片上限 10 MB（`SHOPVISION_MAX_UPLOAD_MB`），超限返回 40004——防大文件全量读进内存；
  真要收大图再上流式接收或分片，不在本轮范围。

## 五、模型接入

`SHOPVISION_MODEL_BACKEND=onnx` 时加载实验三双塔 ONNX：

| 端点 | 输入 | 输出 |
|---|---|---|
| 图像塔 | `image` (batch,3,224,224) | `embedding` (batch,512) |
| 文本塔 | `input_ids` + `attention_mask` (batch,seq) | `embedding` (batch,512) |

分词仍用 `cn_clip.clip.tokenize`，预处理用 `image_transform(224)`，ONNX 输出自行 L2 归一化（已在 `OnnxEncoder` 处理）。
产物到位后只改 `.env` 路径，代码不动。**占位模式红线**：报告里不写实测推理延迟与检索指标。

## 六、前端

React 19 + Ant Design v5 + Vite 5 + Axios，四个页面（状态 / 图像分类 / 文本检索 / 图文匹配）一一对上同步接口，
外加「商品入库」页对接 `/admin/*`（大图/批量另走异步任务）。
页面只做编排，通用逻辑抽在 `src/hooks/`：`useAsyncRequest`（loading / error / duration / abort）、
`useImagePreview`（ObjectURL 生命周期）、`useQuerySync`（URL 参数持久化）。图像分类页再拆成
`components/image/` 下的上传 / 结果 / 历史三块。结构与运行方式见 [`frontend/README.md`](frontend/README.md)。
负责人：张梓萱（zzx）+ 刘凡思雨（lfsy）共同。

## 七、负责人

**开发**

| 部分 | 负责人 |
|---|---|
| 后端（`webapp/backend/`） | 何朝杨 |
| 前端（`webapp/frontend/`） | 张梓萱（zzx）+ 刘凡思雨（lfsy），**共同** |
| 响应式与浏览器兼容测试 | 张梓萱（zzx） |
| 端到端、CORS 与性能测试 | 刘凡思雨（lfsy） |
| 模型产物（ONNX）与加载路径 | 王陆洲（wlz） |

**文档（实验四报告）**

| 报告部分 | 负责人 |
|---|---|
| 成员分工表、架构设计文档 | 何朝杨 |
| 报告整合、排版与正式 PDF | 杜军博（djb） |
| API 文档、测试报告 | 王陆洲（wlz） |
| 问题与解决方案、交付材料整理与报告校对 | 秦鑫洋（qxy） |