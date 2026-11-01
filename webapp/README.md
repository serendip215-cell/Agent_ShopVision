# 实验四前后端开发文档（Agent_ShopVision）

面向本项目的具体写法：这个前后端到底做什么、目录怎么分、每块怎么写、怎么跑起来。
分工见 [`docs/流程与交接/实验四流程与分工.md`](../docs/流程与交接/实验四流程与分工.md)。

## 零、目前情况（2026-11-01）

| 项 | 状态 |
|---|---|
| 前后端代码 | ❌ 未开始。本目录只有文档，`backend/`、`frontend/` 是占位 README |
| 实验四报告 | ❌ 未开始。分工与报告要求已定，见分工文档 |
| 模型产物（双塔 ONNX） | ⏸ 待外部：不在仓库、不在本机，只在训练机；上传安排见 [`实验四模型产物上传说明.md`](../docs/流程与交接/实验四模型产物上传说明.md) |
| Chinese-CLIP 权重 | ⏸ 不在仓库（`.gitignore`） |

**决策：先搭前后端 + 占位编码器，模型后接。** 接口按第六节的接缝钉死，占位与真 ONNX 同形状，`MODEL_BACKEND` 一行配置切换，前端和三个接口不感知。

**占位模式的边界**：`/health` 返回 `model_loaded: false`；报告里只写"链路跑通、模型待接入"，**不写**实测推理延迟和检索指标。等 ONNX 到位再出这些数字。

## 一、这套前后端是干什么的

## 一、这套前后端是干什么的

不是通用 demo，是给我们自己的双塔检索应用做一层可交互的 Web 壳：

- **前端**：上传商品图 / 输入中文查询，看到类别和检索结果。
- **后端**：用实验三优化后的 Chinese-CLIP 双塔（ONNX）把图/文编成向量，在已建好的 FAISS 索引里检索，返回统一 JSON。

数据不是 CIFAR-10，是 `data/processed_data_cleaning/` 的 9,393 条商品，索引是 `data/index_data_finetuned/`（9 类）。

## 二、目录结构

```
webapp/
├── README.md            # 本文档
├── backend/             # FastAPI 服务（负责人：何朝杨）
│   ├── app/
│   │   ├── main.py      # FastAPI 实例、CORS、路由挂载
│   │   ├── config.py     # 路径、端口、模型后端（ort/trt）、索引目录
│   │   ├── api/          # /api/v1/* 路由
│   │   ├── services/     # 编码器封装、FAISS 检索、图文匹配工作流
│   │   └── schemas.py    # 统一返回体与请求体
│   ├── requirements.txt
│   └── .env.example      # 模型路径、索引目录、Redis
└── frontend/            # React 应用（负责人：张梓萱）
    ├── src/
    │   ├── pages/        # 三个页面：ImagePage / TextPage / MatchPage
    │   ├── components/   # 导航栏、上传区、文本输入、结果区、异常提示
    │   └── api/          # Axios 实例与接口封装
    ├── package.json
    └── vite.config.js     # dev 代理到后端
```

## 三、后端怎么写（FastAPI）

### 3.1 统一返回体

所有接口返回同一形状，前端只认这一种：

```json
{ "code": 0, "result": { }, "msg": "ok" }
```

`code`：0 成功，400 参数错，404 路径错，500 服务器错。`msg` 给前端直接展示。

### 3.2 接口表

| 方法 | 路径 | 用途 | 入参 | 返回 result |
|---|---|---|---|---|
| GET | `/api/v1/health` | 健康检查 | — | `{model_loaded, backend, index_dir}` |
| POST | `/api/v1/image` | 图像分类：上传图 → 图像塔编码 → 找最近类别 | `multipart/form-data`：`file` | `{category, confidence, topk[]}` |
| POST | `/api/v1/text` | 文本检索：中文查询 → 文本塔编码 → FAISS 检索 | `application/json`：`{query, top_k}` | `{category, items[]}` |
| POST | `/api/v1/match` | 图文匹配 | `multipart/form-data`：`file` + `text` | `{match, image_category, text_category, items[]}` |

`/api/v1/match` 就是任务书 4.2.3 的多模型协同：先走图像分类 → 再走文本检索 → 比对两边类别是否一致 → 给 `match` 真/假与证据。用 FastAPI 依赖注入把两个 service 串起来。

`http://localhost:8000/docs` 是 FastAPI 自动文档，报告里 API 文档那节直接引用它 + 手写端点表。

### 3.3 数据流

```
前端表单校验 → Axios POST → FastAPI 路由
  → 预处理（图像 resize 224 / 文本分词）
  → 双塔 ONNX 编码（实验三优化产物）
  → FAISS 检索 data/index_data_finetuned/
  → 统一 JSON → 前端渲染
```

图像预处理复用实验一的图像读取逻辑（尺寸、通道、可读性检查）。

### 3.4 异常与 CORS

- 定义业务异常类型（输入错 / 模型错 / 权限错），FastAPI 异常处理器统一转成 `{code,result,msg}`。
- CORS：开发环境 `allow_origins=["http://localhost:5173"]`（Vite dev 端口），生产环境写具体域名，不用 `*`。
- 返回值避免浏览器敏感字符，图像走二进制上传，不要 base64 塞进 URL。

### 3.5 异步任务（Celery）

大图 / 批量检索这类耗时任务走 Celery + Redis，前端轮询取结果。**先不做**：等单张推理的实测延迟出来，确认 ≤2s 目标的场景是否需要异步，再决定上不上（避免为没测过的任务加组件）。

## 四、前端怎么写（React + Ant Design + Axios）

- 三个页面一一对应三个接口：`ImagePage`→`/api/v1/image`、`TextPage`→`/api/v1/text`、`MatchPage`→`/api/v1/match`。
- 公共组件：导航栏、数据输入区（`Upload` / `TextArea`）、结果区（类别标签 + 置信度 + 结果列表）、异常提示（`message.error`）。
- Axios 统一拦截：请求错误 / 超时 / 非 0 `code` 都转成友好提示，例如"图像格式错误，请上传 PNG/JPG"。
- 响应式用 Ant Design `Row/Col`（Grid）+ Flex，不用绝对定位，适配手机/平板/PC。
- dev 代理：`vite.config.js` 里把 `/api` 代理到 `http://localhost:8000`，绕开开发期跨域。

## 五、怎么跑起来

后端：

```bash
cd webapp/backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
cp .env.example .env       # 填模型路径、索引目录
uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd webapp/frontend
npm install
npm run dev                # 默认 http://localhost:5173
```

`GET http://localhost:8000/api/v1/health` 返回 `model_loaded: true` 就说明模型接上了。

## 六、模型怎么接（待定，本机暂未跑通）

这一段是本轮唯一的未知项，写清楚免得后面当成已完成：

- 实验三优化产物是**图像塔 TensorRT/ONNX + 文本塔 ONNX**，但 `scripts/models/` 和 `models/` 里目前没有双塔 ONNX，只有抠图用的 `isnet-general-use.onnx`；Chinese-CLIP 权重也不在仓库里。
- 所以后端加载层留一个接缝：`config.py` 里读模型路径与后端类型（`ort` / `trt`），`services/encoder.py` 按配置加载；**配置缺失时降级为占位编码器**（随机/哈希向量），让前后端链路先跑通，`/health` 返回 `model_loaded: false`。
- ONNX 双塔与权重到位后，只改 `.env` 指向真实文件，代码不动。产物来源由 王陆洲 对接。
- 红线：模型没真跑通前，报告不写实测推理延迟。

## 七、负责人

| 部分 | 负责人 |
|---|---|
| 后端（`webapp/backend/`） | 何朝杨 |
| 前端（`webapp/frontend/`） | 张梓萱 |
| 兼容性与端到端测试 | 刘凡思雨 |
| 模型产物与加载路径 | 王陆洲 |
| 推理耗时口径核对 | 杜军博 |