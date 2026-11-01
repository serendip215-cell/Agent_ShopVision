# webapp/backend — FastAPI 服务

负责人：何朝杨。总体设计见 [上级文档](../README.md)。

## 分层

```
app/
├── main.py          # FastAPI 实例、CORS、全局异常处理
├── config.py        # Settings（环境变量 / .env）
├── schemas.py       # 请求体 + 统一返回体 {code, result, msg}
├── errors.py        # 业务异常（400 / 404 / 500）
├── deps.py          # 依赖注入：编码器、索引、服务
├── api/v1.py        # 路由（Controller）：/api/v1/{health,image,text,match}
└── services/
    ├── encoder.py    # 编码器接缝：PlaceholderEncoder / OnnxEncoder
    ├── index_store.py# 数据访问：index_data_finetuned 的 items + 向量
    └── matching.py   # 业务：图像分类 / 文本检索 / 图文匹配
```

调用方向单向：`api → services → 数据访问`。api 层不写业务，services 不碰 HTTP，
编码器是可替换的接缝（`SHOPVISION_MODEL_BACKEND=placeholder|onnx`）。

## 跑起来

```bash
cd webapp/backend
python -m venv .venv && . .venv/Scripts/activate    # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

- 健康检查：`GET http://localhost:8000/api/v1/health` → `model_loaded: false` 表示占位模式
- 自动文档：http://localhost:8000/docs

## 自检

```bash
cd webapp/backend
python -m unittest discover -s tests -v
```

覆盖索引检索、占位编码器确定性、服务组合、三个接口的返回与 400/404 错误码。

## 接真模型

`model_backend=onnx` 时加载实验三双塔 ONNX：

| 端点 | 输入 | 输出 |
|---|---|---|
| 图像塔 | `image` (batch,3,224,224) | `embedding` (batch,512) |
| 文本塔 | `input_ids` + `attention_mask` (batch,seq) | `embedding` (batch,512) |

分词仍用 `cn_clip.clip.tokenize`，预处理用 `image_transform(224)`；ONNX 输出需 L2 归一化（已处理）。
产物从 GitHub Release 拉，步骤见 [`docs/流程与交接/实验四模型产物上传说明.md`](../../docs/流程与交接/实验四模型产物上传说明.md)。

**占位模式红线**：检索结果无意义，报告里不写实测推理延迟与检索指标。