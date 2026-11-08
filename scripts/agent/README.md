# scripts/agent — 实验5 Agent 集成（第 23 组）

> 5.3「Agent 框架集成」产出。负责人：何朝杨。
> 本文是 5.3 → 5.4 的交接说明：**5.3 做了什么、哪些严格留 TODO(5.2)、5.4 怎么接**。
> 串行关系见 [`docs/流程与交接/实验五流程与分工.md`](../../docs/流程与交接/实验五流程与分工.md) §八。

## 5.3 已实现（解耦，可独立运行）

| 文件 | 内容 |
|---|---|
| `tools.py` | 白名单工具 `text_search`（HTTP 调实验4 `/api/v1/text`），返回契约 `result`，**零第三方依赖**（仅 stdlib `urllib`） |
| `agent.py` | `create_agent()` 初始化 + `Agent.run_intent()` 编排：结构化意图 → 匹配工具 → 调用 → 返回 |
| `test_agent.py` | 6 个单元测试：工具注册、编排、HTTP mock、错误处理、准确率统计框架。**全绿** |
| `__init__.py` | 使 `scripts.agent` 成为可 import 包 |

### 关键对齐（与 5.2 微调数据严格一致）

微调数据 `agent_finetune_data.json` 里模型学会的工具名是 **`text_search`**、参数 `{query, category, top_k}`。工具层只实现这一个白名单工具，参数结构完全对齐。

**image_search / match 不在本文件实现** —— 微调数据没教过，留 5.4 前端/规则降级直接调实验4 接口，不走 LLM 工具调用。

### 运行

```bash
# 单测（需后端真实运行才能通 HTTP 用例；纯 mock 用例不需要）
python -m unittest discover -s scripts/agent -v
```

## 严格留 TODO（依赖 5.2，未交付前不写）

- `agent._parse_intent()`：**用户自然语言 → 结构化意图 `{tool, arguments}`**。这条要接 5.2 微调后的 LLM（模型学会输出 `text_search` 调用格式）。当前是 `NotImplementedError` 桩，5.3 只提供 `run_intent(intent)` 直接吃结构化意图的路径。
- 多轮对话状态 / 槽位继承（方案 §9 待定）。
- 无 LLM 的规则降级解析。

## 5.4 接手（王陆洲）怎么做

1. 接上 5.2 的 LLM：实现 `_parse_intent`，让 `agent.run(user_input)` 能真解析用户话。
2. 把 `Agent` 封装进 FastAPI `/api/v1/agent/chat`（见分工文档 §二/§四），新增错误码 `404 ToolNotFound`（同步 `errors.py` + `API约定.md`）。
3. 工具调用准确率：用 `accuracy(pairs)` 框架，喂 10 轮真实评测（ground_truth 来自微调评测集，预测来自 LLM 实际输出），达标 ≥90%。
4. 前端 `AgentChat.tsx`：调 `/api/v1/agent/chat`。