# 局域网微调模型服务

该服务加载 Qwen3-4B 基座模型和 `dist/lora_adapter_v2`，通过 OpenAI 兼容接口为队友的 LangChain 后端提供模型推理。

## 启动

在仓库根目录执行。默认使用相对路径和 WireGuard 地址 `10.77.7.4`。

```powershell
cd D:\Document\Agent_ShopVision
& D:\environment\conda_envs\pytorch\python.exe -m pip install -r scripts\agent\model_server_requirements.txt
& D:\environment\conda_envs\pytorch\python.exe -m uvicorn scripts.agent.model_server:app --host 0.0.0.0 --port 8100 --workers 1
```

## 队友连接地址

```text
http://10.77.7.4:8100/v1
```

队友后端配置：

```env
SHOPVISION_LLM_BASE_URL=http://10.77.7.4:8100/v1
SHOPVISION_LLM_API_KEY=local
SHOPVISION_LLM_MODEL=shopvision-v2
```

## 检查

```powershell
curl.exe http://10.77.7.4:8100/health
curl.exe http://10.77.7.4:8100/v1/models
```

## 开放 WireGuard 局域网端口

使用**管理员 PowerShell**执行：

```powershell
cd D:\Document\Agent_ShopVision
.\scripts\agent\open_lan_ports.ps1
```

脚本开放商品检索 `8000` 和模型服务 `8100` 两个 TCP 端口。普通权限执行会出现“拒绝访问”。

服务只启动一个 worker。多个 worker 会重复加载模型并增加显存占用。

## 一、服务架构

```text
队友前端
    ↓
队友 Agent 后端
    ├── 调用模型：http://10.77.7.4:8100/v1
    └── 调用检索：http://10.77.7.4:8000
            ↑
       杜军博电脑
       ├── 8000 商品检索后端
       └── 8100 v2 微调模型服务
```

WireGuard 地址为 `10.77.7.4/32`。队友必须先连接同一个 WireGuard 网络。

## 二、你的电脑需要准备什么

确认模型文件存在：

```powershell
cd D:\Document\Agent_ShopVision
Test-Path .\dist\lora_adapter_v2\adapter_model.safetensors
Test-Path .\models\models\Qwen--Qwen3-4B-Instruct-2507\snapshots\master\config.json
```

两个命令都应返回 `True`。

启动商品检索后端，打开第一个 PowerShell：

```powershell
cd D:\Document\Agent_ShopVision\webapp\backend
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动模型服务，打开第二个 PowerShell：

```powershell
cd D:\Document\Agent_ShopVision
& D:\environment\conda_envs\pytorch\python.exe -m uvicorn scripts.agent.model_server:app --host 0.0.0.0 --port 8100 --workers 1
```

模型首次加载需要几十秒。看到 `Application startup complete` 后才表示服务可用。

## 三、队友后端如何配置

队友拉取代码后，在自己的后端 `.env` 中填写：

```env
SHOPVISION_LLM_BASE_URL=http://10.77.7.4:8100/v1
SHOPVISION_LLM_API_KEY=local
SHOPVISION_LLM_MODEL=shopvision-v2
SHOPVISION_API_BASE=http://10.77.7.4:8000
```

变量含义：

| 变量 | 作用 |
|---|---|
| `SHOPVISION_LLM_BASE_URL` | 你的 v2 模型服务地址 |
| `SHOPVISION_LLM_API_KEY` | 局域网占位密钥，当前不做认证 |
| `SHOPVISION_LLM_MODEL` | 模型服务名称 |
| `SHOPVISION_API_BASE` | 你的商品检索后端地址 |

队友不需要复制 Qwen3-4B 权重，也不需要复制 `dist/lora_adapter_v2`。

LangChain 连接方式：

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://10.77.7.4:8100/v1",
    api_key="local",
    model="shopvision-v2",
    temperature=0,
)
```

## 四、队友如何测试连通性

先确认两个端口：

```powershell
Test-NetConnection 10.77.7.4 -Port 8100
Test-NetConnection 10.77.7.4 -Port 8000
```

都应显示：

```text
TcpTestSucceeded : True
```

测试模型服务：

```powershell
curl.exe http://10.77.7.4:8100/health
curl.exe http://10.77.7.4:8100/v1/models
```

测试模型工具调用：

```powershell
curl.exe -X POST http://10.77.7.4:8100/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d "{\"model\":\"shopvision-v2\",\"messages\":[{\"role\":\"user\",\"content\":\"我想找白色运动鞋\"}],\"temperature\":0}"
```

正常返回中应包含：

```json
{
  "name": "text_search",
  "arguments": "{\"query\": \"白色运动鞋\", \"category\": \"鞋\", \"top_k\": 5}"
}
```

测试商品检索：

```powershell
curl.exe -X POST http://10.77.7.4:8000/api/v1/text `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"白色运动鞋\",\"category\":\"鞋\",\"top_k\":5}"
```

## 五、5.4 Agent 联调流程

队友实现 `/api/v1/agent/chat` 后，完整调用链路为：

```text
用户输入
    ↓
队友 Agent 后端
    ↓
10.77.7.4:8100/v1/chat/completions
    ↓
模型返回 text_search 工具调用
    ↓
10.77.7.4:8000/api/v1/text
    ↓
队友后端模板化生成回复
```

Agent 请求示例：

```json
{
  "message": "我想找白色运动鞋"
}
```

商品名称、价格、相似度等事实必须来自 8000 检索接口，模型只负责意图解析和工具调用。

## 六、端口和防火墙

必须使用**管理员 PowerShell**执行：

```powershell
cd D:\Document\Agent_ShopVision
.\scripts\agent\open_lan_ports.ps1
```

如果出现“拒绝访问”，说明当前 PowerShell 没有管理员权限。脚本开放：

```text
TCP 8000  商品检索
TCP 8100  模型服务
```

查看规则：

```powershell
Get-NetFirewallRule -DisplayName "ShopVision-*"
```

## 七、常见问题

### 1. 连接被拒绝

确认两个 Uvicorn 窗口都在运行，并确认队友已经连接 WireGuard。

### 2. 端口测试失败

检查 WireGuard 地址是否仍为 `10.77.7.4`，并使用管理员权限重新执行防火墙脚本。

### 3. 显存不足

保持 `--workers 1`，不要使用多个模型进程，也不要使用 `--no-4bit`。

### 4. 返回 404

模型服务地址必须包含 `/v1`：

```text
http://10.77.7.4:8100/v1
```

商品检索接口必须包含 `/api/v1`：

```text
http://10.77.7.4:8000/api/v1/text
```

### 5. 没有生成工具调用

确认服务加载的是：

```text
dist/lora_adapter_v2
```

不要误用旧版 `dist/lora_adapter`。

## 八、停止服务

在对应的 Uvicorn 窗口按：

```text
Ctrl + C
```

8000 和 8100 是两个独立服务，需要分别停止。
