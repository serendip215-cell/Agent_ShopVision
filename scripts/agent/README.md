# scripts/agent — 实验五 5.3 Agent 集成（第 23 组）

> **2026-11-08 22:10 重写**：原文写于 5.3 中途（`_parse_intent` 还是
> `NotImplementedError` 桩），现已完成并达标，本文更新为实际状态。
>
> 负责人：何朝杨（后续由 Alma 补齐并优化）。
> 进度总览见 [`docs/实验五/00-当前进度总览.md`](../../docs/实验五/00-当前进度总览.md)。

## 一、现在有什么（13 个 Python 文件）

### 核心实现

| 文件 | 作用 |
|---|---|
| `tools.py` | 白名单工具 `text_search`（HTTP 调实验4 `/api/v1/text`），零第三方依赖（仅 stdlib `urllib`） |
| `agent.py` | `create_agent()` + `Agent.run_intent()` 编排；`_parse_intent()` **已接 5.2 微调模型** |
| `intent_parser.py` | 意图解析核心：`IntentParser`（懒加载 Qwen3-4B + LoRA）、工具名编辑距离纠错、规则降级、JSON 容错 |
| `category_map.py` | 商品词 → 9 大类目映射 + query 清洗（确定性后处理层） |
| `conversation.py` | 多轮对话与槽位继承（`ConversationStore`） |
| `langchain_agent.py` | **LangChain 版**（任务书 5.3.1 要求），用 `langchain.agents.create_agent` |

### 评测与数据

| 文件 | 作用 |
|---|---|
| `eval_tool_accuracy.py` | 10 轮工具调用准确率评测，支持 `--hybrid`（带后处理） |
| `build_agent_finetune_data.py` | 5.1 的 100 条数据生成 |

### 测试（5 个文件，共 78 项）

| 文件 | 项数 | 覆盖 |
|---|---:|---|
| `test_agent.py` | 6 | 工具注册、编排、HTTP mock、准确率统计框架 |
| `test_intent_parser.py` | 21 | 工具名纠错（含实测错例）、JSON 容错、`name` 字段、规则降级 |
| `test_conversation.py` | 16 | 槽位继承、类目覆盖、会话隔离、三轮累积 |
| `test_langchain_agent.py` | 11 | 工具 schema、降级、HTTP 调用、返回结构 |
| `test_category_map.py` | 24 | 类目映射、query 清洗、生产链路、留出集泛化 |

```bash
python -m unittest discover -s scripts/agent -v   # 78 项全绿
```

## 二、两套 Agent 实现（并存，不是重复）

| 实现 | 文件 | 用途 | 依赖 |
|---|---|---|---|
| **LangChain 版（任务书要求）** | `langchain_agent.py` | 走 LLM 工具调用 + LangGraph 多轮记忆 | langchain ≥1.0、langchain-openai、langgraph |
| **自研极简版（降级）** | `agent.py` + `intent_parser.py` | 无 LangChain / 无 GPU / 模型连不上时的兜底 | 仅 stdlib（HTTP 部分） |

`create_shopvision_agent()` 任何一步失败都返回 `None`，调用方自动降级，不会白屏。

## 三、怎么用

### 最简（生产链路，含后处理）

```python
from scripts.agent.agent import run

result = run("帮我找黑色木纹手机壳，5个")
# {"ok": True, "tool": "text_search",
#  "arguments": {"query": "黑色木纹手机壳", "category": "手机壳", "top_k": 5},
#  "post_process": {...}, "result": {"items": [...]}}
```

模型路径走环境变量，不写死：

```bash
export SHOPVISION_AGENT_MODEL=Qwen/Qwen3-4B-Instruct-2507
export SHOPVISION_AGENT_ADAPTER=dist/lora_adapter_v2
```

### 多轮

```python
from scripts.agent.conversation import ConversationStore

store = ConversationStore()
store.chat("s1", "我想找手机壳", executor=...)   # executor 传工具调用函数
r = store.chat("s1", "黑色的")                   # 自动继承 category=手机壳
r["slots"]   # {"category": "手机壳", "query": "黑色", "top_k": 5}
```

### LangChain 版

```python
from scripts.agent.langchain_agent import create_shopvision_agent, run_once

agent = create_shopvision_agent(base_url="http://localhost:8000/v1", model="qwen3-4b-shopvision")
r = run_once(agent, "找白色运动鞋", thread_id="s1")
```

### 评测

```bash
python scripts/agent/eval_tool_accuracy.py --mode rule                    # 规则验证（无需 GPU）
python scripts/agent/eval_tool_accuracy.py --mode model \
    --model <路径> --adapter dist/lora_adapter_v2                          # 纯模型
python scripts/agent/eval_tool_accuracy.py --mode model \
    --model <路径> --adapter dist/lora_adapter_v2 --hybrid                 # 加后处理
```

## 四、实测成绩

| 版本 | 纯模型 | 加后处理 | 机器 |
|---|---:|---:|---|
| v1（原数据） | 10% | 100% | 3080Ti / 5060 |
| **v2（扩充重训）** | **90%** ✅ | **100%** | 3080Ti / 5060 |

任务书要求 ≥90%，**v2 达标**。两机结果一致。

**注意区分**：v1 的 100% 里后处理贡献 90pp（几乎全靠规则）；
v2 的 90% 是模型自己的能力，后处理只修一个「的」。

详见 [`docs/实验五/09`](../../docs/实验五/09-5.3优化实跑：扩充数据重训.md)。

## 五、5.4 接手要做什么

`王陆洲` 的任务：

1. **`POST /api/v1/agent/chat`** —— 契约见
   [`webapp/backend/README-agent-chat.md`](../../webapp/backend/README-agent-chat.md)
   （Zhangzx 已按前端实现写好契约）
2. 新增错误码 `40403` / `404 ToolNotFound`，同步 `errors.py` 与 `API约定.md`
3. **多轮**：前端加 `session_id`，后端用 `ConversationStore`（已实现，16 项单测）
4. 前端 `AgentChat.jsx` 已提交，接口一上就能联调

最省事的接法：

```python
from scripts.agent.agent import run

@app.post("/api/v1/agent/chat")
def agent_chat(req: AgentChatRequest):
    r = run(req.message)
    return AgentChatResponse.ok(
        reply=compose_reply(r),      # 模板化，别让模型编商品
        tool_calls=[{"name": r["tool"], "arguments": r["arguments"]}],
    )
```

## 六、image / match 为什么不进 LLM 工具白名单

5.2 微调数据只教了 `text_search` 一种工具调用。项目里含 image 的文件是
实验3 的检索索引与质检，**没有图片类 LLM 工具训练数据**。

因此：

- Agent 结构化工具白名单**仅 `text_search`**，与微调数据严格对齐
- `image_search` / `match` 是**实验4 后端现成接口**，由 5.4 前端或规则降级直调
- `langchain_agent.py` 里虽然定义了这两个 `@tool`，但 description 明确写了
  「占位，由 5.4 前端直调」，实际不会被模型选中

**若组内要求「LLM 也能调 image/match」**，需补工具 + 补微调样本 + 重新训练，属新增范围。