"""对话导购接口与业务层自检（7 条，全部不需要 GPU / 模型）。

覆盖：
  1. 正常命中：接口返回 code=0、reply 非空、tool_calls[0].name 正确；
  2. 空 message：40000；
  3. 超长 message（>500）：40000；
  4. 业务异常体仍是 {code, result, msg} 三件套，HTTP 状态 = 码前三位；
  5. 业务层按检索结果模板拼回复（reply 里出现商品名，items 数量受 top_k 约束）；
  6. 工具连续失败时重试 3 次并给出降级文案；
  7. 参数清洗：非法类目丢弃、top_k 夹到 1..50。

模型不参与：AgentService 处于 cold 状态，走 rule_parse；检索用注入的假函数。
"""

from __future__ import annotations

import base64
import os

# 必须在导入 app.* 之前设置：本文件按字母序先于 test_backend 加载，
# 若这里不设，celery_app 会用真 broker，无 Redis 时异步任务用例会整片失败。
os.environ.setdefault("SHOPVISION_CELERY_ALWAYS_EAGER", "true")

import unittest
from typing import Any, cast

from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_agent_service
from app.errors import ApiError, ErrorCode
from app.main import app
from app.services.agent_service import AgentService


class _FakeService:
    """接口层用的假服务：不碰模型、不碰索引。"""

    def __init__(
        self, reply: str = "在「鞋」里找到 1 件相近商品，最接近的是：\n1. 白色运动鞋"
    ) -> None:
        self.reply = reply

    def chat(self, message: str, session_id: str | None = None) -> dict:
        return {
            "reply": self.reply,
            "thinking": [
                "规则模式（未接 LLM）",
                "调用工具：text_search(query=白色运动鞋, top_k=5)",
            ],
            "tool_calls": [
                {"name": "text_search", "arguments": {"query": "白色运动鞋", "top_k": 5}}
            ],
            "items": [],
        }

    def drop_session(self, session_id: str | None) -> bool:
        return bool(session_id)


class _BoomService:
    def chat(self, message: str, session_id: str | None = None) -> dict:
        raise ApiError(ErrorCode.BAD_REQUEST, "请输入想找的商品")


# 1×1 透明 PNG：只用于过 _open_image 的格式校验
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _fake_match():
    """图搜用的最小替身：一个编码器 + 一个只返回一条结果的索引。"""

    class _Encoder:
        model_loaded = True

        def encode_image(self, image):
            return [0.6, 0.8]

        def encode_text(self, text):
            return [0.6, 0.8]

    class _Hit:
        def as_dict(self):
            return {"category": "鞋", "item_name": "白色运动鞋", "similarity": 0.5}

    class _Index:
        categories = ["鞋"]

        def best_category(self, vector):
            return "鞋", 0.6, {}

        def search(self, vector, top_k=5):
            return [_Hit()]

    class _Match:
        encoder = _Encoder()
        index = _Index()

    return _Match()


class _FakeImageService:
    """图搜接口用的假服务：不加载模型、不碰索引。"""

    last_session = None

    def search_by_image(self, image, message="", alpha=0.6, top_k=5, session_id=None) -> dict:
        type(self).last_session = session_id
        return {
            "reply": "这张图看起来属于「鞋」，找到 2 件相似商品：\n1. 白色运动鞋",
            "thinking": ["图像塔编码：visual 塔 → 512 维", "检索：9 类索引，命中 2 条"],
            "tool_calls": [],
            "items": [
                {"category": "鞋", "item_name": "白色运动鞋", "similarity": 0.52},
                {"category": "鞋", "item_name": "小白鞋", "similarity": 0.48},
            ],
            "category": "鞋",
            "similarity": 0.52,
        }


class AgentChatRouteTest(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_ok_returns_reply_and_tool_calls(self) -> None:
        app.dependency_overrides[get_agent_service] = _FakeService
        resp = self.client.post("/api/v1/agent/chat", json={"message": "找一双白色运动鞋"})
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["code"], 0)
        self.assertTrue(body["result"]["reply"].strip())
        self.assertEqual(body["result"]["tool_calls"][0]["name"], "text_search")
        self.assertIsInstance(body["result"]["thinking"], list)

    def test_empty_message_is_40000(self) -> None:
        app.dependency_overrides[get_agent_service] = _FakeService
        resp = self.client.post("/api/v1/agent/chat", json={"message": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], 40000)

    def test_too_long_message_is_40000(self) -> None:
        app.dependency_overrides[get_agent_service] = _FakeService
        resp = self.client.post("/api/v1/agent/chat", json={"message": "鞋" * 501})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], 40000)

    def test_delete_session_route(self) -> None:
        """DELETE /agent/session/{id} 应释放上下文并返回 deleted。"""
        app.dependency_overrides[get_agent_service] = _FakeService
        resp = self.client.delete("/api/v1/agent/session/abc")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)
        self.assertTrue(resp.json()["result"]["deleted"])

    def test_error_body_keeps_three_field_shape(self) -> None:
        app.dependency_overrides[get_agent_service] = _BoomService
        resp = self.client.post("/api/v1/agent/chat", json={"message": "随便看看"})
        body = resp.json()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(set(body), {"code", "result", "msg"})
        self.assertEqual(body["code"], 40000)
        self.assertIsNone(body["result"])


def _settings(**kwargs) -> Settings:
    base: dict[str, Any] = {
        "agent_warmup": False,
        "agent_model": "unused",
        "agent_adapter": "",
        "agent_retry_times": 3,
        "agent_tool_top_k": 5,
        "agent_max_message_len": 500,
    }
    base.update(kwargs)
    return Settings(**base)


class AgentServiceTest(unittest.TestCase):
    def test_composes_reply_from_real_items(self) -> None:
        calls: list[dict] = []

        def fake_search(**kwargs):
            calls.append(kwargs)
            return {
                "items": [
                    {"category": "鞋", "item_name": "白色运动鞋", "similarity": 0.51},
                    {"category": "鞋", "item_name": "小白鞋", "similarity": 0.49},
                ]
            }

        service = AgentService(_settings(), search_fn=fake_search)
        result = service.chat("我想找白色运动鞋")

        self.assertIn("白色运动鞋", result["reply"])
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["tool_calls"][0]["name"], "text_search")
        self.assertEqual(calls[0]["category"], "鞋")
        self.assertTrue(any("规则模式" in line for line in result["thinking"]))

    def test_tool_failure_retries_then_degrades(self) -> None:
        attempts: list[int] = []

        def broken_search(**kwargs):
            attempts.append(1)
            raise RuntimeError("connection refused")

        service = AgentService(_settings(agent_retry_times=3), search_fn=broken_search)
        result = service.chat("我想找白色运动鞋")

        self.assertEqual(len(attempts), 3)
        self.assertIn("没办成", result["reply"])
        self.assertEqual(result["items"], [])

    def test_sanitizes_arguments(self) -> None:
        service = AgentService(_settings(), search_fn=lambda **kw: {"items": []})
        cleaned = service._sanitize(
            {"query": "  白色运动鞋  ", "top_k": 999, "category": "不存在的类目"}
        )
        self.assertEqual(cleaned["query"], "白色运动鞋")
        self.assertEqual(cleaned["top_k"], 50)
        self.assertNotIn("category", cleaned)

    def test_normalizes_polite_and_measure_words(self) -> None:
        """量词/客套话要剥掉，“N 个”要变成 top_k（对齐 v4 评测口径）。"""
        service = AgentService(_settings(), search_fn=lambda **kw: {"items": []})

        cleaned = service._sanitize({"query": "找一双白色运动鞋", "category": "鞋", "top_k": 5})
        self.assertEqual(cleaned["query"], "白色运动鞋")

        cleaned = service._sanitize(
            {"query": "帮我搜透明玻璃杯，10个", "category": "厨房用品", "top_k": 5}
        )
        self.assertEqual(cleaned["query"], "透明玻璃杯")
        self.assertEqual(cleaned["top_k"], 10)

        cleaned = service._sanitize({"query": "有没有黑色的双肩包", "category": "包", "top_k": 5})
        self.assertEqual(cleaned["query"], "黑色的双肩包")

    def test_reply_action_skips_tools(self) -> None:
        """模型选择 reply 时不应调用检索工具。"""

        class _ReplyParser:
            def parse_action(self, text: str) -> dict:
                return {"action": "reply", "text": "你好，我是导购助手。"}

        called: list[int] = []

        def fake_search(**kwargs: object) -> dict:
            called.append(1)
            return {"items": []}

        service = AgentService(_settings(), search_fn=fake_search)
        service._state = "ready"
        service._parser = cast(Any, _ReplyParser())

        result = service.chat("你好")
        self.assertEqual(result["reply"], "你好，我是导购助手。")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["tool_calls"], [])
        self.assertEqual(called, [])

    def test_say_is_passed_through(self) -> None:
        """v3 的过渡语 say 要原样带给前端。"""

        class _SayParser:
            def parse_action(self, text: str) -> dict:
                return {
                    "action": "tool",
                    "tool": "text_search",
                    "arguments": {"query": "白色运动鞋", "category": "鞋", "top_k": 5},
                    "say": "我先帮你找找",
                }

        service = AgentService(
            _settings(),
            search_fn=lambda **kw: {
                "items": [{"category": "鞋", "item_name": "白鞋", "similarity": 0.5}]
            },
        )
        service._state = "ready"
        service._parser = cast(Any, _SayParser())

        result = service.chat("找白色运动鞋")
        self.assertEqual(result["say"], "我先帮你找找")
        self.assertEqual(result["tool_calls"][0]["name"], "text_search")

    def test_unknown_tool_is_rejected(self) -> None:
        """白名单外的工具直接报 40000，而不是 500。"""
        service = AgentService(_settings(), search_fn=lambda **kw: {"items": []})
        with self.assertRaises(ApiError) as caught:
            service._run_tool("delete_everything", {})
        self.assertEqual(caught.exception.code, ErrorCode.BAD_REQUEST)

    def test_reply_with_price_is_replaced(self) -> None:
        """模型直接回答里出现价格/销量断言时必须换成安全话术。"""

        class _FabricatingParser:
            def parse_action(self, text: str) -> dict:
                return {"action": "reply", "text": "推荐白色小熊水杯，¥19.9，5000+人买过。"}

        service = AgentService(_settings(), search_fn=lambda **kw: {"items": []})
        service._state = "ready"
        service._parser = cast(Any, _FabricatingParser())

        result = service.chat("随便看看")
        self.assertNotIn("19.9", result["reply"])
        self.assertNotIn("人买过", result["reply"])
        self.assertIn("查一下商品库", result["reply"])

    def test_reply_owner_pronoun_is_fixed(self) -> None:
        """助手口误“能/可以帮我找”要改成“帮你找”。"""

        class _WrongVoiceParser:
            def parse_action(self, text: str) -> dict:
                return {"action": "reply", "text": "你好，可以帮我找点什么吗？"}

        service = AgentService(_settings(), search_fn=lambda **kw: {"items": []})
        service._state = "ready"
        service._parser = cast(Any, _WrongVoiceParser())

        result = service.chat("你好")
        self.assertIn("可以帮你找", result["reply"])
        self.assertNotIn("帮我找", result["reply"])

    def test_list_categories_reply(self) -> None:
        """list_categories 没有 items，不能套“没找到商品”的模板。"""

        class _Index:
            categories = ["鞋", "包", "水杯"]

        class _Match:
            index = _Index()

        service = AgentService(_settings(), match_service=_Match())
        result, error = service._run_tool("list_categories", {})
        self.assertEqual(error, "")
        reply = service._render_tool_result("list_categories", result, [], "有哪些类目")
        self.assertIn("3 类", reply)
        self.assertIn("鞋", reply)

    def test_get_item_detail_reply(self) -> None:
        """商品详情要按字段渲染，不调模型。"""

        class _Index:
            categories = ["鞋"]

            def find_item(self, item_id: str) -> dict:
                return {
                    "category": "鞋",
                    "item_id": item_id,
                    "item_name": "白色运动鞋",
                    "type": "运动鞋",
                    "color": "白色",
                    "material": "网布",
                }

        class _Match:
            index = _Index()

        service = AgentService(_settings(), match_service=_Match())
        result, error = service._run_tool("get_item_detail", {"item_id": "muge_1"})
        self.assertEqual(error, "")
        reply = service._render_tool_result("get_item_detail", result, [], "第二个")
        self.assertIn("白色运动鞋", reply)
        self.assertIn("网布", reply)

    def test_session_history_is_recorded(self) -> None:
        """带 session_id 时把「用户 -> 工具 -> 检索结果 -> 回复」写进历史。"""
        service = AgentService(
            _settings(),
            search_fn=lambda **kw: {
                "items": [{"category": "鞋", "item_name": "白色运动鞋", "similarity": 0.5}]
            },
        )
        service.chat("找白色运动鞋", session_id="s1")

        history = service._history("s1")
        self.assertGreaterEqual(len(history), 3)
        self.assertEqual(history[0]["role"], "user")
        self.assertIn("检索结果：", history[2]["content"])
        self.assertEqual(service._history("unknown"), [])

    def test_history_is_trimmed(self) -> None:
        """历史最多保留 8 条（约 2 轮），避免上下文无限增长。"""
        service = AgentService(_settings(), search_fn=lambda **kw: {"items": []})
        for index in range(10):
            service.chat(f"找点东西{index}", session_id="s2")
        self.assertLessEqual(len(service._history("s2")), 8)

    def test_summary_keeps_user_utterances(self) -> None:
        """B1 摘要只记用户原话，不包含注入的检索结果。"""
        service = AgentService(
            _settings(),
            search_fn=lambda **kw: {
                "items": [{"category": "鞋", "item_name": "白色运动鞋", "similarity": 0.5}]
            },
        )
        service.chat("找白色运动鞋", session_id="s3")
        service.chat("要高帮的", session_id="s3")

        summary = service._summary_line("s3")
        self.assertIn("找白色运动鞋", summary)
        self.assertIn("要高帮的", summary)
        self.assertNotIn("检索结果", summary)

    def test_image_search_records_session(self) -> None:
        """图搜带 session_id 时，结果要写进历史，后续文字才能引用。"""
        service = AgentService(_settings(), match_service=_fake_match())
        service.search_by_image(object(), "", 0.6, 5, "img-1")

        history = service._history("img-1")
        self.assertTrue(any("检索结果：" in message["content"] for message in history))
        self.assertTrue(any(message["role"] == "assistant" for message in history))

    def test_image_category_inherited_by_next_text_turn(self) -> None:
        """图搜后模型拿不到 category，后端要用槽位补上“鞋”。"""

        class _Parser:
            def parse_action_messages(self, messages) -> dict:
                return {
                    "action": "tool",
                    "tool": "text_search",
                    "arguments": {"query": "黑色", "top_k": 5},
                }

        service = AgentService(_settings(), match_service=_fake_match())
        service._state = "ready"
        service._multi_turn = True
        service._parser = cast(Any, _Parser())

        service.search_by_image(object(), "", 0.6, 5, "img-2")

        captured: dict = {}

        def fake_search(**kwargs):
            captured.update(kwargs)
            return {"items": []}

        service._search = fake_search
        service.chat("换成黑色的吧", session_id="img-2")

        self.assertEqual(captured.get("category"), "鞋")

    def test_drop_session_releases_memory(self) -> None:
        """前端点清空后，后端要立刻释放历史与摘要。"""
        service = AgentService(_settings(), search_fn=lambda **kw: {"items": []})
        service.chat("找点东西", session_id="s9")
        self.assertTrue(service._history("s9"))

        self.assertTrue(service.drop_session("s9"))
        self.assertEqual(service._history("s9"), [])
        self.assertEqual(service._summary_line("s9"), "")
        self.assertFalse(service.drop_session("s9"))

    def test_query_merged_across_turns(self) -> None:
        """第二句只说“白色”时，后端要拼成“运动鞋 白色”，否则检索为空。"""

        class _Parser:
            def __init__(self) -> None:
                self.calls = 0

            def parse_action_messages(self, messages) -> dict:
                self.calls += 1
                query = "运动鞋" if self.calls == 1 else "白色"
                return {
                    "action": "tool",
                    "tool": "text_search",
                    "arguments": {"query": query, "category": "鞋", "top_k": 5},
                }

        seen: list[str] = []

        def fake_search(**kwargs):
            seen.append(kwargs["query"])
            return {"items": []}

        service = AgentService(_settings(), search_fn=fake_search)
        service._state = "ready"
        service._multi_turn = True
        service._parser = cast(Any, _Parser())

        service.chat("找运动鞋", session_id="m1")
        service.chat("要白色的", session_id="m1")

        self.assertEqual(seen[0], "运动鞋")
        self.assertEqual(seen[1], "运动鞋 白色")

    def test_gc_evicts_expired_sessions(self) -> None:
        """超过 TTL 的会话要被回收，防止内存无限增长。"""
        service = AgentService(_settings(), search_fn=lambda **kw: {"items": []})
        for index in range(3):
            service.chat(f"找东西{index}", session_id=f"g{index}")

        with service._session_lock:
            service._seen["g0"] = 0  # 很久没活动
        service._gc()

        self.assertEqual(service._history("g0"), [])
        self.assertTrue(service._history("g2"))


class AgentImageRouteTest(unittest.TestCase):
    """图搜接口：成功路径用假服务；格式校验走真实的 _open_image。"""

    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_image_search_returns_items(self) -> None:
        app.dependency_overrides[get_agent_service] = _FakeImageService
        resp = self.client.post(
            "/api/v1/agent/image",
            files={"file": ("shoe.png", _PNG_1PX, "image/png")},
            data={"message": "", "alpha": "0.6", "top_k": "5", "session_id": "img-1"},
        )
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["code"], 0)
        self.assertTrue(body["result"]["reply"].strip())
        self.assertEqual(body["result"]["category"], "鞋")
        self.assertEqual(len(body["result"]["items"]), 2)
        # session_id 要透传给服务，图搜结果才能进多轮上下文
        self.assertEqual(_FakeImageService.last_session, "img-1")

    def test_non_image_is_invalid_image_error(self) -> None:
        app.dependency_overrides[get_agent_service] = _FakeImageService
        resp = self.client.post(
            "/api/v1/agent/image",
            files={"file": ("fake.png", b"not-an-image", "image/png")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], 40001)


if __name__ == "__main__":
    unittest.main()
