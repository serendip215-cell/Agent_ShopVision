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

from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_agent_service
from app.errors import ApiError, ErrorCode
from app.main import app
from app.services.agent_service import AgentService


class _FakeService:
    """接口层用的假服务：不碰模型、不碰索引。"""

    def __init__(self, reply: str = "在「鞋」里找到 1 件相近商品，最接近的是：\n1. 白色运动鞋") -> None:
        self.reply = reply

    def chat(self, message: str) -> dict:
        return {
            "reply": self.reply,
            "thinking": ["规则模式（未接 LLM）", "调用工具：text_search(query=白色运动鞋, top_k=5)"],
            "tool_calls": [{"name": "text_search", "arguments": {"query": "白色运动鞋", "top_k": 5}}],
            "items": [],
        }


class _BoomService:
    def chat(self, message: str) -> dict:
        raise ApiError(ErrorCode.BAD_REQUEST, "请输入想找的商品")


# 1×1 透明 PNG：只用于过 _open_image 的格式校验
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _FakeImageService:
    """图搜接口用的假服务：不加载模型、不碰索引。"""

    def search_by_image(self, image, message="", alpha=0.6, top_k=5) -> dict:
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

    def test_error_body_keeps_three_field_shape(self) -> None:
        app.dependency_overrides[get_agent_service] = _BoomService
        resp = self.client.post("/api/v1/agent/chat", json={"message": "随便看看"})
        body = resp.json()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(set(body), {"code", "result", "msg"})
        self.assertEqual(body["code"], 40000)
        self.assertIsNone(body["result"])


def _settings(**kwargs) -> Settings:
    base = {
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

    def test_reply_action_skips_tools(self) -> None:
        """模型选择 reply 时不应调用检索工具。"""

        class _ReplyParser:
            def parse_action(self, text: str) -> dict:
                return {"action": "reply", "text": "你好，我是导购助手。"}

        called: list[int] = []
        service = AgentService(
            _settings(), search_fn=lambda **kw: called.append(1) or {"items": []}
        )
        service._state = "ready"
        service._parser = _ReplyParser()

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
            _settings(), search_fn=lambda **kw: {"items": [{"category": "鞋", "item_name": "白鞋", "similarity": 0.5}]}
        )
        service._state = "ready"
        service._parser = _SayParser()

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
        service._parser = _FabricatingParser()

        result = service.chat("随便看看")
        self.assertNotIn("19.9", result["reply"])
        self.assertNotIn("人买过", result["reply"])
        self.assertIn("查一下商品库", result["reply"])

    def test_reply_owner_pronoun_is_fixed(self) -> None:
        """助手口误“能帮我找”要改成“能帮你找”。"""

        class _WrongVoiceParser:
            def parse_action(self, text: str) -> dict:
                return {"action": "reply", "text": "你好，能帮我找点什么吗？"}

        service = AgentService(_settings(), search_fn=lambda **kw: {"items": []})
        service._state = "ready"
        service._parser = _WrongVoiceParser()

        result = service.chat("你好")
        self.assertIn("能帮你找", result["reply"])
        self.assertNotIn("能帮我找", result["reply"])

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


class AgentImageRouteTest(unittest.TestCase):
    """图搜接口：成功路径用假服务；格式校验走真实的 _open_image。"""

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
            data={"message": "", "alpha": "0.6", "top_k": "5"},
        )
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["code"], 0)
        self.assertTrue(body["result"]["reply"].strip())
        self.assertEqual(body["result"]["category"], "鞋")
        self.assertEqual(len(body["result"]["items"]), 2)

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
