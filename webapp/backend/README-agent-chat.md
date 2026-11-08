# 对话导购页（/agent）后端新增说明

> 对应前端页面：`webapp/frontend/src/pages/AgentChat.jsx`（导航里的「对话导购」）。
> 本文只说明**这个页面要跑起来，后端需要新增什么**，不含前端改动。
> 依据是当前源码实读结果（2026-11-08），不是设想稿。

---

## 0 一句话结论

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
| 待接的坑 | `scripts/agent/agent.py:_parse_intent` 仍是 `NotImplementedError`（等 5.2 微调模型） | 同上 |

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

### 4.1 工具层：两条路，选一条

| 方案 | 做法 | 优点 | 代价 |
|---|---|---|---|
| A（推荐，进程内） | 用 `Depends(get_match_service)` 取 `MatchService`，包一个本地 `text_search` 工具函数 | 无自请求、无端口依赖、延迟低（省一次 HTTP 往返） | 与 `scripts/agent/tools.py` 的 HTTP 版并存，需注明「同一契约、两份实现」 |
| B（复用现成） | 直接 import `scripts.agent.tools.text_search` | 零新代码 | 后端必须自己在 8000 跑着；单测要 mock；多一层序列化 |

不管选哪条，`tool_calls[].arguments` 必须与 5.2 微调数据里模型学会的参数完全一致：
`{"query": str, "category": str|None, "top_k": int}`，工具名固定 `text_search`。
**`image_search` / `match` 不进 LLM 工具白名单**（5.2 没教过），要图搜就走前端已有的 `/image`、`/match` 页面。

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

### 5.1 多轮对话（前端目前不支持）

前端每轮只发 `{message}`，历史只存在页面内存里，**后端拿不到上文**。两条路：

| 方案 | 后端 | 前端 | 适用 |
|---|---|---|---|
| **A 无状态单轮（建议先做）** | 只按当前 message 处理 | 零改动 | P0 答辩演示，能覆盖「说需求 → 出商品」 |
| B 有状态多轮 | 收 `session_id`（+ 可选 `messages`），内存/Redis 存最近 N 轮 | 需加 `session_id` 字段与前端生成逻辑 | 任务书"多轮推理测试"要写进报告时再做 |

建议：先按 A 上线，把 `AgentChatRequest` 里预留 `session_id: str | None = None`、`messages: list | None = None`（可选字段，前端不传也能用）。
这样 B 期只改前端 + 后端读字段，不用改契约形状。

### 5.2 意图解析谁来做

- 5.2 交付前：`_parse_intent` 仍是桩 → 用规则降级（关键词命中 9 个类目词 `鞋/水杯/包/男装/女装/运动服/手机壳/厨房用品/家居用品`，其余按 `text_search(query=原话)`）。
- 5.2 交付后：把 LLM 调用塞进 `_parse_intent`，输出 `{tool, arguments}`，其余流程不变。

两种模式对外返回形状完全一致，只差 `thinking` 文案。

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
| [`scripts/agent/README.md`](../../scripts/agent/README.md) | 5.3 产出与严格留 TODO：`_parse_intent` 必须等 5.2；image/match 不进 LLM 工具白名单 |
| [`docs/方案与指南/实验五-对话式导购助手方案.md`](../../docs/方案与指南/实验五-对话式导购助手方案.md) | 范围、架构、红线、验收口径 |
| [`docs/流程与交接/实验五流程与分工.md`](../../docs/流程与交接/实验五流程与分工.md) | 5.4.1 归王陆洲：`/agent/chat` + `404 ToolNotFound`；5.4.2 前端组件归张梓萱 |
| [`webapp/API约定.md`](../API约定.md) | 统一返回体、错误码表、前端 Axios 约定 |

> 本文与上述文档不冲突，只把「前端已经按什么契约在等」这一步补全：前端代码里冻结的形状是
> `{ code, result: { reply, thinking?, tool_calls? } }`，后端照此返回即可，无需再讨论字段名。
