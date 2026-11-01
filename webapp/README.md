# webapp — 实验四前后端

面向本项目的具体写法与运行说明。分工见 [`docs/流程与交接/实验四流程与分工.md`](../docs/流程与交接/实验四流程与分工.md)，
接口契约见 [`API约定.md`](API约定.md)。

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

- 在线文档（自动生成）：http://localhost:8000/docs
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

> CI：改动 `webapp/**` 推送或提 PR 时，GitHub Actions 自动跑同一套自检
> （[`.github/workflows/backend-tests.yml`](../.github/workflows/backend-tests.yml)）。
> 推之前本地先跑一遍，别把红叉推上去。

## 三、接口与调用

基址 `http://localhost:8000`，前缀 `/api/v1`；返回体统一 `{code, result, msg}`，
错误码表见 [`API约定.md`](API约定.md)。

| 方法 | 路径 | 用途 | 请求 |
|---|---|---|---|
| GET | `/api/v1/health` | 健康检查 | — |
| POST | `/api/v1/image` | 图像分类 | `multipart/form-data`：`file` |
| POST | `/api/v1/text` | 文本检索 | `application/json`：`{query, top_k?, category?}` |
| POST | `/api/v1/match` | 图文匹配 | `multipart/form-data`：`file` + `text` + `top_k?` |

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
├── schemas.py         请求体 + 统一返回体
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