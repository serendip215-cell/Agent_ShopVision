# webapp — 实验四前后端

面向本项目的具体写法与运行说明。分工见 [`docs/流程与交接/实验四流程与分工.md`](../docs/流程与交接/实验四流程与分工.md)，
接口契约见 [`API约定.md`](API约定.md)。

## 〇、这个系统最终是什么（先看这一段）

一句话：**用户给一张商品图或一句中文查询，后端用实验三的双塔模型编码，在 9 类商品库（10,165 条）里检索，
返回类别与相似商品。**

### 1. 三个功能 = 任务书要的三个页面

| 页面 | 用户怎么用 | 屏幕上看什么 | 后端接口 |
|---|---|---|---|
| 图像分类 | 拖 / 选一张商品图 → 点「分析」 | 判出的类别 + 置信度，下面列相似商品（名称 / 类别 / 相似度） | `POST /api/v1/image` |
| 文本检索 | 输入「白色运动鞋」→ 类别可选 → 点「搜索」 | 相关商品列表（名称、类别、相似度） | `POST /api/v1/text` |
| 图文匹配 | 同时传图 + 输文本 → 点「匹配」 | 图判出的类别 vs 文判出的类别；一致显示「匹配」，不一致把两个类别都摆出来 | `POST /api/v1/match` |

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

**不做**（明确划出去，报告里如实写）：登录注册、下单、数据库持久化、批量异步（Celery 是可选加分项，
不排进主线）、模型训练（那是实验三的事）。

### 4. 怎么实现的（数据流）

```
浏览器 React 页面（三页签）
   │ axios  →  POST /api/v1/{image|text|match}
   ▼
api/v1.py  FastAPI 路由     ← 只校验参数，不写业务
   ▼
services/matching.py  MatchService   业务编排
   ├─ Encoder     双塔 ONNX 各编一路 → 512 维 L2 归一化向量
   └─ IndexStore  data/index_data_finetuned 的 9 类向量 + items.csv 元数据
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

## 一、现状（2026-11-01）

| 项 | 状态 |
|---|---|
| **后端** | ✅ 可跑。`backend/app/` 分层完成，占位模式端到端通，22 项自检通过 |
| **前端** | ❌ **未开始**。`frontend/` 只有占位 README |
| 模型产物（双塔 ONNX） | ⏸ 不在仓库，待训练机上传，见 [`实验四模型产物上传说明.md`](../docs/流程与交接/实验四模型产物上传说明.md) |

**先跑后端 + 占位编码器，模型后接。** 编码器是可替换接缝，`SHOPVISION_MODEL_BACKEND`
一行配置切换；接口形状不变，前端将来照 [`API约定.md`](API约定.md) 写即可。

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

> 依赖：fastapi / uvicorn / pydantic(-settings) / numpy / pillow / python-multipart（+ httpx 仅测试用）。
> 接真 ONNX 才需要 `onnxruntime` 与 Chinese-CLIP，见 `requirements.txt` 注释。
> 规范工具单独装：`pip install black ruff mypy`（不在运行依赖里，CI 与本地各自装）。

### 2. 配置

```powershell
copy .env.example .env              # 默认 placeholder，开箱即用
```

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

## 三、接口与调用

基址 `http://localhost:8000`，前缀 `/api/v1`；返回体统一 `{code, result, msg}`，
错误码表见 [`API约定.md`](API约定.md)。

| 方法 | 路径 | 用途 | 请求 |
|---|---|---|---|
| GET | `/api/v1/health` | 健康检查 | — |
| POST | `/api/v1/image` | 图像分类 | `multipart/form-data`：`file` |
| POST | `/api/v1/text` | 文本检索 | `application/json`：`{query, top_k?, category?}` |
| POST | `/api/v1/match` | 图文匹配 | `multipart/form-data`：`file` + `text` + `top_k?` |

### 接口文档（FastAPI 内置，不用装插件）

Java 那边用 springdoc / knife4j 挂 Swagger，FastAPI 是**自带**的，开服务就有：

| 地址 | 是什么 | 谁来用 |
|---|---|---|
| `/docs` | Swagger UI，能直接点着发请求试（等价于 Java 的 Knife4j） | 联调、演示、截图 |
| `/scalar` | Scalar，比 Swagger UI 现代、能折叠分组，同样能直接调 | 答辩演示、给人看 |
| `/redoc` | ReDoc，排版舒服的阅读版 | 写报告 API 文档那一节 |
| `/openapi.json` | OpenAPI 3 规范，机器可读 | 导给别人 / 喂 Postman |

接口分组按三个页面走（状态 / 图像分类页 / 文本检索页 / 多模态匹配页），每个接口都带
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

Postman **Import → File** 选中 `openapi.json`，四个请求（含文件上传字段）自动建好；
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
```

Python 客户端：

```python
import requests
print(requests.get("http://localhost:8000/api/v1/health").json())
print(requests.post("http://localhost:8000/api/v1/text", json={"query": "白色运动鞋", "top_k": 3}).json())
```

> `health` 里 `model_loaded: false` = 当前占位模式，**检索结果无意义**；`true` = 已接真 ONNX。

## 四、后端架构（分层与扩展点）

```
app/
├── main.py            FastAPI 实例、CORS、全局异常处理
├── config.py          Settings（环境变量 / .env）
├── schemas.py         请求体、统一返回体、结果模型（后两者供 /docs 生成文档）
├── errors.py          错误码枚举 + 业务异常
├── deps.py            依赖注入：编码器 / 索引 / 服务
├── api/v1.py          路由（Controller）：只取参、校验、调服务
└── services/
    ├── encoder.py     编码器接缝：PlaceholderEncoder / OnnxEncoder
    ├── index_store.py 数据访问：index_data_finetuned 的条目与向量
    └── matching.py    业务：status / 图像分类 / 文本检索 / 图文匹配
```

调用方向**单向**：`api → services → 数据访问`。

| 想改什么 | 动哪里 | 会不会牵动别处 |
|---|---|---|
| 换模型（占位 ↔ ONNX） | `.env` 的 `model_backend` + 路径 | 不改代码 |
| 加一个接口 | `api/v1.py` 加路由 + `matching.py` 加方法 | 不动其它层 |
| 换索引来源 / 存储 | 新写一个类，换 `deps.get_index` | api 层不动 |
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

## 六、前端（未开始）

React 19+ / Ant Design / Axios，三个页面（图像分类 / 文本分类 / 多模态匹配）一一对上三个接口。
公共组件：导航栏、输入区（Upload / TextArea）、结果区（类别标签 + 置信度）、异常提示。
按 [`API约定.md`](API约定.md) 写 Axios 封装；dev 环境把 `/api` 代理到 `http://localhost:8000`。
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