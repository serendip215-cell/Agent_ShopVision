# 对话导购页（/agent）后端新增说明

> **2026-11-09 更新（最新）**：后端已按 v4 多轮协议接入，本文 §0 / §2.1 的旧结论
> （“只缺一个接口”“前端只发 message”）已被 §0.1 取代；§4–§7 的实现要点仍然有效。

---

## 0.1 当前契约（v4 多轮，2026-11-09）

### 请求

```http
POST /api/v1/agent/chat
Content-Type: application/json

{ "message": "要白色的", "session_id": "3f2c…" }   # session_id 可选
```

### 成功返回

```json
{
  "code": 0,
  "result": {
    "reply": "这几款以白色为主，高帮运动鞋、休闲鞋居多……",
    "thinking": ["动作：tool（微调模型）", "继承上一轮查询：运动鞋 白色", "调用工具：text_search(query=运动鞋 白色, category=鞋)"],
    "tool_calls": [{ "name": "text_search", "arguments": { "query": "运动鞋 白色", "category": "鞋", "top_k": 5 } }],
    "items": [ { "category": "鞋", "item_name": "高帮鞋男欧货", "similarity": 0.47 } ],
    "say": "我先帮你找找"
  },
  "msg": "ok"
}
```

| 字段 | 说明 |
|---|---|
| `reply` | 助手回复：模型直接回答，或“检索结果 + 点评” |
| `items` | 命中的商品（前端渲染成并排小图，已有 `ItemThumbRow`） |
| `say` | v4 的工具调用过渡语（≤30 字），前端渲染成一行灰字，可为空 |
| `thinking` | 折叠展示；会写“微调模型/规则模式”“继承上一轮查询”“沿用上一轮类目” |

### 其他接口

| 方法 | 路由 | 说明 |
|---|---|---|
| GET | `/api/v1/agent/...` | 无独立查询接口，模型状态通过日志观察 |
| POST | `/api/v1/agent/image` | 图搜；表单增加 `session_id` 后，图搜结果进入多轮上下文 |
| DELETE | `/api/v1/agent/session/{session_id}` | 清空该会话的历史/摘要/槽位，返回 `{"deleted": true}` |

### 多轮行为

- 同一 `session_id` 下，服务端保存**最近 8 条消息**（约 2 轮检索对话）；
- 更早的内容压缩成一行摘要（用户原话 ≤6 句）追加到 system，不会全忘；
- 工具结果以 `检索结果：{...}` 的 user 消息回喂，与 v4 训练格式一致；
- 同类目且新查询更短时，后端自动合并查询（`运动鞋` + `白色` → `运动鞋 白色`）；
- 模型没给 `category` 时，用槽位兜底（图搜后的“换成黑色的吧”就靠这条）；
- 清理：30 分钟不活跃自动过期，会话数超过 500 时淘汰最久未用。

### 模型选择

适配器自动探测：`lora_adapter_v4` > `v3` > `v2`；`v4` 启用多轮，`v3/v2` 仍按单轮。
模型不可用（未下载/显存不足/加载失败）时降级 `rule_parse`，接口永远有响应。

---

> **历史说明（2026-11-08）**：5.2 微调模型与 5.3 Agent 已交付，本文 §4.1 / §5.1 / §5.2
> 三节从「待定/选一条」改为「已实现」，其余章节（前端契约、错误码、自测）保持原样有效。
> 实际交付能力见 `docs/实验五/05-5.3完成说明.md`。

> 对应前端页面：`webapp/frontend/src/pages/AgentChat.jsx`（导航里的「对话导购」）。
> 本文只说明**这个页面要跑起来，后端需要新增什么**，不含前端改动。
> 依据是当前源码实读结果（2026-11-08），不是设想稿。

---

## 0 一句话结论（历史，2026-11-08）

前端已经写好、会在缺少接口时如实报错；**后端缺 1 个接口：`POST /api/v1/agent/chat`**。
现在请求它拿到的是 `{code: 40400}`，页面显示「对话接口尚未上线（HTTP 404）」。

已具备、可直接复用的是 `scripts/agent/`（5.3 产出：白名单工具 `text_search` + `Agent.run_intent` + 单测）；
本次要做的事是「把已有 Agent 包成 HTTP 接口」，**不需要重写检索能力**。

---

## 1 现状核对

| 项 | 结论 | 依据 |
|---|---|---|
| 前端调用地址 | `POST /api/v1/agent/chat`，body `{ message }` | `src/api/client.js:101 sendAgentChat`，axios `baseURL: '/api/v1'` |
| 代理 | dev 下 `/api` → `http://localhost:8000` | `vite.config.js` |
| 前端超时 | **30 秒**（axios `timeout: 30000`） | `src/api/client.js:18` |
| 后端现有路由 | 只有 `health / image / text / match` + `admin/*` + `tasks/*` | `app/api/v1.py`、`app/main.py` |
| agent 路由 | **不存在** → 请求落到 404 | `app/main.py` 未 include agent router |
| 可复用 Agent | `scripts/agent/tools.py`（`text_search`）、`agent.py`（`create_agent` / `run_intent`） | `scripts/agent/README.md`（5.3→5.4 交接） |
| ~~待接的坑~~ | ~~`_parse_intent` 仍是桩~~ → **已落地**：`scripts/agent/intent_parser.py` 已接 v2 微调模型，含工具名纠错与规则降级 | 已解除 |

> 注：`scripts/agent/tools.py` 通过 HTTP 调本机 `/api/v1/text`，所以它要求「后端自己已经在 8000 端口跑着」。
> 若在同一进程内实现，建议直接把 `MatchService.search_text` 包成工具（见 §5.1），避免自己请求自己。

---

## 2 前端契约（后端必须照这个返回，否则页面报错）

### 2.1 请求

```http
POST /api/v1/agent/chat
Content-Type: application/json

{ "message": "找一双白色运动鞋" }
```

- 前端只发这一个字段，**没有** `session_id`、没有历史消息数组（见 §5.2 的多轮取舍）。
- 前端不做长度限制，所以长度校验必须后端做（建议 `1 ≤ len ≤ 500`，与 `/text` 的 200 不同，对话类输入放宽些）。

### 2.2 成功返回

```json
{
  "code": 0,
  "result": {
    "reply": "在「鞋」里找到 5 件白色运动鞋，最接近的是……",
    "thinking": ["识别意图：找商品", "调用工具：text_search(query=白色运动鞋)"],
    "tool_calls": [
      { "name": "text_search", "arguments": { "query": "白色运动鞋", "top_k": 5 } }
    ]
  },
  "msg": "ok"
}
```

| 字段 | 类型 | 前端怎么用 | 硬约束 |
|---|---|---|---|
| `reply` | string | 直接渲染成助手气泡 | **必填且去空格后非空**；空了页面会报「返回内容不完整」 |
| `thinking` | string \| string[] | 数组按 `\n` 拼接，塞进「思考过程」折叠块 | 可选；非字符串元素会被丢弃 |
| `tool_calls` | array\<object\> | 逐条列「工具名 + 参数 JSON」 | 可选；只读 `name`（回退 `tool`）和 `arguments` |

**当前页面不渲染商品列表。** 对话里想直接出商品卡片（复用 `/text` 的 `MatchedItem`），需要前端加渲染 + 后端加 `items` 字段，属于前后端一起改，不在本文范围；
后端可以先按扩展字段返回（`result.items`），现有页面会忽略它，不会坏。

### 2.3 失败返回与前端提示的对应关系

失败同样是 `{code, result: null, msg}`，HTTP 状态码 = `code` 前三位（沿用现有约定）。

| 情况 | 前端实际表现 | 触发条件 |
|---|---|---|
| 后端没启动 / 连不上 8000 | 「后端服务未连接」 | axios `NETWORK` |
| 路由不存在 | 「对话接口尚未上线」 | `code` 等于 `'404'` 或以 `'404'` 开头 |
| 超过 30 秒没返回 | 「请求超时」 | axios `TIMEOUT` |
| 其他 | 直接展示 `msg` | `code != 0` |
| `code=0` 但 `reply` 空 | 「返回内容不完整」+ 约定提示 | 见 §2.2 |

⚠️ **已知判定缺陷，实现时绕开**：前端用 `code.startsWith('404')` 判「接口未上线」，
所以**任何 `404xx` 业务码**（如 `40401 类别不存在`）都会被显示成「对话接口尚未上线」。
因此 agent 接口内**不要把「类别不存在 / 无结果」落到 404 段**，改为 `40000` 或 `code=0` + 空结果说明；
或者上线路由后统一改前端的判定（改前端要另开任务）。

---

## 3 要新增 / 改动的文件

| 文件 | 动作 | 具体内容 |
|---|---|---|
| `app/api/agent.py` | **新建** | `router = APIRouter(prefix="/api/v1")`，`POST /agent/chat`，`response_model=AgentChatResponse`，`tags=["对话导购页"]`，`responses=_ERROR_RESPONSES`（复制 v1.py 的写法） |
| `app/services/agent_service.py` | **新建** | `AgentService.chat(message) -> AgentChatResult`：意图解析 → 白名单工具调用 → 模板化回复；含超时、3 次重试、规则降级 |
| `app/schemas.py` | 追加 | `AgentChatRequest` / `AgentToolCall` / `AgentChatResult` / `AgentChatResponse(ApiResponse)` |
| `app/errors.py` | 追加 | `TOOL_NOT_FOUND = 40403`（码表 `_MESSAGES` 同步一行）。**仅用于「LLM 请求了白名单里没有的工具」这种调试/异常场景**；因为前端把 `404xx` 一律显示为「接口未上线」（§2.3），用户可见的失败请走 `40000` / `50001` |
| `app/config.py` | 追加 | LLM 与 Agent 相关 `Settings` 字段（见 §4.2） |
| `app/deps.py` | 追加 | `@lru_cache` 的 `get_agent_service()`，与现有 `get_match_service()` 同风格 |
| `app/main.py` | 改动 | `from .api import admin, agent, tasks, v1` → `app.include_router(agent.router)`；`_TAGS_META` 加 `{"name": "对话导购页", ...}` |
| `requirements.txt` | 追加（可选） | `openai>=1.40`（DeepSeek/Qwen 兼容端点）或 `langchain>=1.0`，按 5.2 选的基座定 |
| `webapp/API约定.md` | 追加 | §三 加「POST /api/v1/agent/chat」；§二 加 `40403` 一行 |
| `tests/test_agent_api.py` | **新建** | 见 §6.2 |

`app/api/v1.py` **不用改**：agent 单独一个 router 更干净，也避免把 4 个检索接口的文件越拖越长。

---

## 4 实现要点

### 4.1 工具层：已按方案 B 落地（2026-11-08 更新）

**5.2 / 5.3 已交付，本节从「待定」改为「已实现」。**

现成可用的入口（`scripts/agent/`）：

| 入口 | 用途 | 是否需 GPU |
|---|---|---|
| `agent.run(user_input)` | 一站式：用户话 → 意图 → 工具 → 结果 | 是（首次加载 4B，约 8-10GB） |
| `agent._parse_intent(text)` | 只做意图解析 `{tool, arguments}` | 是 |
| `intent_parser.rule_parse(text)` | 规则降级（不加载模型） | 否 |
| `langchain_agent.create_shopvision_agent(...)` | LangChain 版（任务书 5.3.1 要求） | 是 |
| `conversation.ConversationStore` | 多轮槽位继承 | 否 |

**采用方案 B（HTTP 复用）**，不用进程内 `MatchService`，理由：
1. `scripts/agent/tools.py` 与 `langchain_agent.py` 已经实现并测过 HTTP 版（同一契约）
2. 进程内耦合会让 `scripts/agent` 依赖 `webapp/backend` 的模块结构，破坏解耦
3. 多一次 HTTP 往返在内网约 5-15ms，相对 4B 推理（数百 ms~2s）可忽略

**代价接受方式**：后端自己在 8000 端口监听时 HTTP 自请求才成立；
单测用 mock（`test_langchain_agent.py` 已有先例）。
若要规避自请求，可把 `tools.py` 的 `API_BASE` 指向同进程的 TestClient。

`tool_calls[].arguments` 与 5.2 微调数据严格一致：
`{"query": str, "category": str|None, "top_k": int}`，工具名 `text_search`。
**`image_search` / `match` 不进 LLM 工具白名单**（5.2 没教过），要图搜走前端 `/image`、`/match`。
`langchain_agent.py` 里虽然定义了这两个 `@tool`，但 description 明确写了「占位，由 5.4 前端直调」，
实际不会被模型选中。

### 4.2 配置（追加到 `Settings`，前缀沿用 `SHOPVISION_`）

```python
# 对话导购（/agent/chat）
llm_base_url: str = ""                 # OpenAI 兼容端点，如 https://api.deepseek.com/v1
llm_api_key: str = ""                  # 只留在后端，.env 不入库
llm_model: str = ""                    # 5.2 交付的基座/微调模型名
llm_timeout_s: float = 8.0             # 必须 < 前端 30s；建议 8s 即降级
agent_max_message_len: int = 500
agent_history_turns: int = 6           # 有状态方案才用（§5.2）
agent_retry_times: int = 3             # 任务书要求"3 次重试 + 日志"
agent_tool_top_k: int = 5
```

`.env.example` 同步补上（空值即"规则模式"），并在注释里写明 **不要把 key 写进前端**。

### 4.3 分层不要破

- `api/agent.py`：只做取参、`ApiError` 抛错、`AgentChatResponse.ok(...)`。
- `services/agent_service.py`：全是业务（意图 → 工具 → 模板回复），不碰 `UploadFile` / `Request`。
- 抛错统一 `raise ApiError(ErrorCode.XXX, detail)`，由 `main.py` 现有 handler 转成 `{code, result: null, msg}`——**别自己拼 JSONResponse**。
- 未捕获异常交给全局 handler（`50000`），日志里保留 `logger.exception`。

### 4.4 回复必须模板化（红线）

- LLM 只输出结构化意图（工具名 + 参数），**不输出商品内容**。
- `reply` 由后端模板拼装：`命中 N 件 → 展示标题/类目/相似度`，商品信息一律取自工具返回值。
- 库里没有时，明确说「库内暂未收录，可换关键词或上传图片」，禁止编造商品名、价格、参数。
- 工具调用前做参数白名单校验：`top_k` 夹到 `1..50`、`category` 必须在 `/health.categories` 里、`query` 截断到 200。

### 4.5 超时、重试、降级

```
用户话 → 意图解析（LLM，8s 超时）
        ├ 成功 → 工具调用（text_search，超时 10s）
        └ 失败/无 key → 规则降级（关键词 + 9 个类目词匹配）
        → 模板回复
```

- 工具失败重试最多 `agent_retry_times` 次，间隔 0.3s / 0.6s / 1.2s，每次 `logger.warning`；
- 全链路总预算 **≤ 10s**，因为前端 30s 会直接判超时，用户看到的是「请求超时」而不是你的提示；
- 降级时 `thinking` 里写明「规则模式（未接 LLM）」，避免报告里把规则结果当成 LLM 能力。

---

## 5 两个需要拍板的点

### 5.1 多轮对话：后端能力已就绪，前端待接（2026-11-08 更新）

**方案 B 的后端部分已经实现**：`scripts/agent/conversation.py` 的 `ConversationStore`。

能力（16 项单测覆盖）：
- 槽位继承：先说「手机壳」，再说「黑色的」→ 自动带上类目
- 换类目清空旧描述：「手机壳」→「运动鞋」时不会把「黑色」串过去
- 「还有别的吗」/「换一批」：沿用上一轮全部条件
- 按 `thread_id` 会话隔离 + TTL 自动过期

**前端仍只发 `{message}`**，所以现在只能走单轮。接通多轮需要两处改动：

```python
# AgentChatRequest 加两个可选字段（前端不传也能用，向后兼容）
session_id: str | None = None      # 前端生成，存 localStorage
messages: list[dict] | None = None  # 可选：前端直接传历史
```

```javascript
// AgentChat.jsx 发请求处
const sid = localStorage.getItem('agent_session') || crypto.randomUUID()
localStorage.setItem('agent_session', sid)
const result = await sendAgentChat({ message, session_id: sid }, controller.signal)
```

**任务书 5.3.2 要求「单轮 + 多轮推理测试」**，多轮必须在报告里体现，
所以这两处改动建议在 5.4 联调时一并做掉，不要留给"以后"。

### 5.2 意图解析：已接 5.2 微调模型（2026-11-08 更新）

**不再是待定项。** `scripts/agent/agent.py` 的 `_parse_intent` 已落地：

```python
from scripts.agent.agent import run
result = run("帮我找黑色木纹手机壳，5个")
```

模型路径走环境变量，不写死：

```bash
export SHOPVISION_AGENT_MODEL=Qwen/Qwen3-4B-Instruct-2507
export SHOPVISION_AGENT_ADAPTER=dist/lora_adapter
```

**三层保障，不会白屏**：

| 层 | 触发条件 | 行为 |
|---|---|---|
| 1. 微调模型 | 正常情况 | 输出 `{tool, arguments}` |
| 2. 工具名纠错 | 模型把 `text_search` 写成 `tool_search` 等 | 编辑距离对齐白名单（实测错例从 0 分修正到 1.00） |
| 3. 规则降级 | 模型加载失败 / OOM / 推理超时 | `rule_parse()` 从原话抓类目和数量 |

**降级的 `thinking` 文案必须写明「规则模式（未接 LLM）」**，避免报告里把规则结果
当成 LLM 能力——这条红线和原文一致，不放松。

5.2 实测成绩：基座 12.88% → LoRA v1 75.76%（验证集 11 条，详见 `docs/实验五/03`）。

**5.3 工具调用准确率**（10 轮评测集，真跑推理）：

| 版本 | 纯模型 | 加后处理 |
|---|---:|---:|
| v1（原数据） | 10% | 100% |
| **v2（扩充重训）** | **90%** | **100%** |

演示与报告用 **`dist/lora_adapter_v2/`**。详见 `docs/实验五/09`。

---

## 6 自测

### 6.1 手工验证（可直接复制）

```powershell
# 后端已启动（uvicorn app.main:app --port 8000）
$body = '{"message":"找一双白色运动鞋"}'
$bytes = [Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/agent/chat" -Method Post `
  -Body $bytes -ContentType "application/json; charset=utf-8"
```

期望：`code=0`、`result.reply` 非空、`result.tool_calls[0].name = "text_search"`。

```bash
# 通过前端代理再验一次（确认 5173 也能通）
curl -s -X POST http://localhost:5173/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"有没有黑色的双肩包"}'
```

必测的边界（每条都要看返回是不是 `{code, result, msg}` 三件套）：

| 用例 | 期望 |
|---|---|
| 空 message / 全空格 | `40000`，msg 说明「请输入需求」 |
| 501 字超长 | `40000`（不要 500） |
| 库内有的需求（白色运动鞋） | `code=0`，reply 里有真实商品标题，tool_calls 有 `text_search` |
| 库外需求（比如"洗衣机"） | `code=0`，reply 明确说库内没有，**不编商品** |
| 断网 / 无 LLM key | `code=0`，走规则模式，`thinking` 标注「规则模式」 |
| 停掉 8000 后前端发消息 | 页面显示「后端服务未连接」，不是白屏 |
| LLM 故意拖 12s | 后端 8s 降级返回，页面不出现「请求超时」 |

### 6.2 单测（建议覆盖 7 条）

`tests/test_agent_api.py` 用 `TestClient` + `app.dependency_overrides` 覆盖工具函数（不打真 HTTP）：

1. 正常命中 → `code=0`，`reply` 非空，`tool_calls` 长度 1；
2. 空 message → `40000`；
3. 超长 message → `40000`；
4. 工具返回空 items → `code=0`，reply 为「库内没有」模板；
5. 工具抛异常 → 重试 3 次后 `50001`，msg 面向用户；
6. `thinking` 为 `list[str]` 时序列化正常；
7. 返回体字段只有 `code/result/msg`（防以后有人手拼 JSON 破坏契约）。

```powershell
cd webapp\backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### 6.3 文档自检

- `http://localhost:8000/docs` 里出现「对话导购页」分组和 `/api/v1/agent/chat`；
- `webapp/API约定.md` 的错误码表已经有 `40403`；
- 前端 `/agent` 页发一条消息，能看到气泡 + 可展开「思考过程」+ 「工具调用」块。

---

## 7 联调顺序（每步都能独立验证）

1. `schemas.py` 加 4 个模型 → `/docs` 能渲染（此时还没有路由，报不出来属正常）。
2. 建 `services/agent_service.py`，先用**规则模式**跑通 `text_search`（不接 LLM）。
3. 建 `api/agent.py` + `main.py` 注册 → `curl` 拿到 `code=0`，前端页面从「接口未上线」变成正常对话。
4. 接 LLM（`_parse_intent`）：成功、超时、异常三态都要试。
5. 补 `40403` 与 `API约定.md`，跑 §6.2 单测。
6. 前端回归：`/agent` 页正常对话，同时确认 `/image`、`/text`、`/match` 不受影响（它们共用 `_ERROR_RESPONSES` 与全局 handler）。
7. 10 轮固定脚本评测（工具调用准确率 ≥90%，方案验收口径），把结果写进报告，不要用占位/规则结果冒充 LLM。

---

## 8 与其他文档的关系

| 文档 | 内容 |
|---|---|
| [`scripts/agent/README.md`](../../scripts/agent/README.md) | 5.3 产出说明。**注：原「`_parse_intent` 必须等 5.2」的限制已解除**（2026-11-08 落地），现由 `intent_parser.py` 实现 |
| [`docs/方案与指南/实验五-对话式导购助手方案.md`](../../docs/方案与指南/实验五-对话式导购助手方案.md) | 范围、架构、红线、验收口径 |
| [`docs/流程与交接/实验五流程与分工.md`](../../docs/流程与交接/实验五流程与分工.md) | 5.4.1 归王陆洲：`/agent/chat` + `404 ToolNotFound`；5.4.2 前端组件归张梓萱 |
| [`webapp/API约定.md`](../API约定.md) | 统一返回体、错误码表、前端 Axios 约定 |

> 本文与上述文档不冲突，只把「前端已经按什么契约在等」这一步补全：前端代码里冻结的形状是
> `{ code, result: { reply, thinking?, tool_calls? } }`，后端照此返回即可，无需再讨论字段名。

---

## 9 附：5.3 已交付能力速查（2026-11-08）

给写 `/api/v1/agent/chat` 的人直接照着用，不用再翻 `scripts/agent/`。

```python
# 一站式：用户话 -> 意图 -> 工具 -> 结果（需 GPU，首次加载 4B 约 8-10GB）
from scripts.agent.agent import run
result = run("帮我找黑色木纹手机壳，5个")
# {"ok": True, "tool": "text_search", "arguments": {...}, "result": {"items": [...]}}

# 多轮：槽位继承（不需要 GPU）
from scripts.agent.conversation import ConversationStore
store = ConversationStore()
r1 = store.chat("session-1", "我想找手机壳", executor=...)   # executor 传你的工具调用函数
r2 = store.chat("session-1", "黑色的")                        # 自动继承 category=手机壳
r2["slots"]   # {"category": "手机壳", "query": "黑色", "top_k": 5}

# LangChain 版（任务书 5.3.1 要求，需 GPU + 已起 OpenAI 兼容服务）
from scripts.agent.langchain_agent import create_shopvision_agent, run_once
agent = create_shopvision_agent(base_url="http://localhost:8000/v1", model="qwen3-4b-shopvision")
r = run_once(agent, "找白色运动鞋", thread_id="session-1")

# 规则降级（不需要 GPU，永远可用）
from scripts.agent.intent_parser import rule_parse
rule_parse("找3个蓝色水杯")
# {"tool": "text_search", "arguments": {"query": "蓝色水杯", "top_k": 3, "category": "水杯"}}
# 已实测：指令词「找/帮我找/推荐/有没有」等会被剔除，只留描述词
```

**准确的 `thinking` 文案建议**（前端要展开显示）：

| 场景 | thinking 内容 |
|---|---|
| 微调模型命中 | `["识别意图：text_search", "调用工具：text_search(query=白色运动鞋)"]` |
| 工具名被纠错 | 追加一条 `["注意：工具名 tool_search 已纠错为 text_search"]` |
| 规则降级 | `["规则模式（未接 LLM）：按关键词匹配类目", "调用工具：text_search(...)"]` |

**注意**：`scripts/agent/conversation.py` 里的 `_compose_reply()` 已经能生成
「找到 N 件商品，例如：xxx」这类模板回复，可直接复用，不必重写。
