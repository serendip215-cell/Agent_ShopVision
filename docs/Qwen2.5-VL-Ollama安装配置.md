# Qwen2.5-VL 本地安装与配置（Ollama）

对应开发文档第 3.1 节与实验 2/3 的模型选型：商品图片属性识别（类别、颜色、材质、
款式、可见文字）以及后续批量标注、Agent 工具调用，统一使用本地 Qwen2.5-VL。
Ollama 是最省事的本地部署方式，模型默认已量化，不需要单独做 4-bit 转换。

## 1. 硬件与版本选择

| 模型 | 下载大小 | 建议配置 | 说明 |
|---|---|---|---|
| `qwen2.5vl:3b` | 3.2 GB | 8 GB 内存 / 入门显卡 | 开发文档的起步版本，先用它 |
| `qwen2.5vl:7b` | 6 GB | 显存 ≥ 8 GB | 效果更好，推荐主力版本 |
| `qwen2.5vl:32b` | 21 GB | 显存 ≥ 24 GB | 课程项目用不上 |

注意：Ollama 库中的名字是 **`qwen2.5vl`**（`vl` 前没有连字符），不是 `qwen2.5-vl`。

## 2. Windows 安装 Ollama

1. 下载安装包：https://www.ollama.com/download/windows
2. 运行安装程序，安装完成后打开新的命令行窗口验证：

```bash
ollama --version
```

3. Ollama 安装后自动作为后台服务运行，API 监听 `http://localhost:11434`。

> 磁盘提示：模型默认存放在 `C:\Users\<用户名>\.ollama`。C 盘空间紧张时，
> 先设置环境变量 `OLLAMA_MODELS` 指到大容量盘（如 `D:\ollama-models`）再拉模型。

## 3. 拉取模型

```bash
ollama pull qwen2.5vl:3b     # 先拉 3B 验证环境
ollama pull qwen2.5vl:7b     # 硬件允许再拉 7B
ollama list                   # 查看已下载模型
```

## 4. 验证

命令行直接对话：

```bash
ollama run qwen2.5vl:3b "你是商品分析助手"
```

用项目里的真实商品图测试视觉能力（API 方式，也是后续批量标注脚本的调用形态）：

```python
import base64
import requests

img_path = "data/raw_data/Amazon_data/images/81iZlv3bjpL.jpg"  # 任选一张商品图
img_b64 = base64.b64encode(open(img_path, "rb").read()).decode()

resp = requests.post("http://localhost:11434/api/chat", json={
    "model": "qwen2.5vl:3b",
    "messages": [{
        "role": "user",
        "content": "识别这件商品的类别、颜色、材质和可见文字，只输出JSON："
                   '{"category":"","color":"","material":"","text":""}，'
                   "看不清的字段留空，不要猜测。",
        "images": [img_b64],
    }],
    "stream": False,
})
print(resp.json()["message"]["content"])
```

## 5. 与项目的衔接

- 模型只负责图片理解与生成；文件读写、检索、校验由 Agent 工具完成
  （开发文档第 3 节分工不变）。
- 批量标注流程：读取 `data/raw_data/<数据集>/images/` → 调用本地 API →
  属性结果写入 `processed_data/`，不在 `raw_data/` 下改写。
- 生成属性必须遵守开发文档 17.4 事实一致性约束：看不清的字段留空，
  不从标题臆造属性，与元数据冲突时以元数据为准。
- 提示词要求模型输出 JSON，便于脚本解析；正式标注脚本另行提交。

## 6. 常见问题

| 问题 | 处理 |
|---|---|
| `ollama pull` 很慢或中断 | 重新执行同一命令可断点续传；换网络时段再试 |
| 运行报显存/内存不足 | 换 `qwen2.5vl:3b`；关闭其他占显存的程序 |
| API 连不上 | 确认服务在跑：`ollama list` 可执行即正常；端口为 11434 |
| 想看模型占了多少资源 | `ollama ps` |
| 图片输入无反应 | 确认用的是 `vl` 系列模型（文本模型不支持图片） |
