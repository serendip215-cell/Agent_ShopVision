"""多轮对话与槽位继承的单测。

    python -m unittest scripts.agent.test_conversation -v

重点验证「多轮」这个任务书指标：第二句不带类目时能继承第一句的类目。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.agent.conversation import (  # noqa: E402
    ConversationStore,
    extract_category,
    extract_colors,
    extract_top_k,
    is_followup,
    resolve_slots,
)


class ExtractTest(unittest.TestCase):
    def test_category(self):
        self.assertEqual(extract_category("我想找手机壳"), "手机壳")
        self.assertEqual(extract_category("白色运动鞋"), "鞋")
        self.assertIsNone(extract_category("随便看看"))

    def test_longest_category_wins(self):
        """「手机壳」不能被「鞋」这类短词误伤。"""
        self.assertEqual(extract_category("手机壳和鞋子"), "手机壳")

    def test_top_k(self):
        self.assertEqual(extract_top_k("找5个"), 5)
        self.assertEqual(extract_top_k("推荐3件"), 3)
        self.assertIsNone(extract_top_k("找几个"))
        self.assertEqual(extract_top_k("给我999个"), 20)  # 夹紧

    def test_colors(self):
        self.assertEqual(extract_colors("白色和黑色的鞋"), ["白色", "黑色"])
        self.assertEqual(extract_colors("鞋子"), [])

    def test_followup(self):
        self.assertTrue(is_followup("还有别的吗"))
        self.assertTrue(is_followup("换一批"))
        self.assertTrue(is_followup("再来点"))
        self.assertFalse(is_followup("我想找运动鞋"))


class SlotInheritanceTest(unittest.TestCase):
    """任务书要求的「多轮推理」——核心就是这几个用例。"""

    def setUp(self):
        self.store = ConversationStore()
        self.tid = "test-thread"

    def test_inherit_category(self):
        """第一句给类目，第二句只给颜色 —— 类目必须继承。"""
        r1 = self.store.chat(self.tid, "我想找手机壳")
        self.assertEqual(r1["slots"]["category"], "手机壳")

        r2 = self.store.chat(self.tid, "黑色的")
        self.assertEqual(r2["slots"]["category"], "手机壳", "类目必须继承")
        self.assertIn("黑色", r2["slots"]["query"])

    def test_inherit_top_k(self):
        self.store.chat(self.tid, "找水杯，3个")
        r2 = self.store.chat(self.tid, "蓝色的")
        self.assertEqual(r2["slots"]["top_k"], 3, "数量应继承")

    def test_override_category(self):
        """换类目等于换话题，旧描述词要清掉。"""
        self.store.chat(self.tid, "黑色手机壳")
        r2 = self.store.chat(self.tid, "我想找运动鞋")
        self.assertEqual(r2["slots"]["category"], "鞋")
        self.assertNotIn("黑色", r2["slots"]["query"], "换类目应清空旧描述")

    def test_followup_keeps_all_slots(self):
        """「还有别的吗」不该改变任何条件。"""
        self.store.chat(self.tid, "找白色运动鞋，5个")
        r2 = self.store.chat(self.tid, "还有别的吗")
        self.assertEqual(r2["slots"]["category"], "鞋")
        self.assertEqual(r2["slots"]["top_k"], 5)

    def test_three_turn_accumulation(self):
        """三轮累积：类目 + 颜色 + 数量。"""
        self.store.chat(self.tid, "我想找水杯")
        self.store.chat(self.tid, "蓝色的")
        r3 = self.store.chat(self.tid, "要3个")
        self.assertEqual(r3["slots"]["category"], "水杯")
        self.assertEqual(r3["slots"]["top_k"], 3)
        self.assertIn("蓝色", r3["slots"]["query"])

    def test_sessions_isolated(self):
        """不同 thread_id 不能串味。"""
        self.store.chat("a", "找手机壳")
        self.store.chat("b", "找运动鞋")
        self.assertEqual(self.store.get("a").slots.category, "手机壳")
        self.assertEqual(self.store.get("b").slots.category, "鞋")

    def test_reset(self):
        self.store.chat(self.tid, "找手机壳")
        self.store.reset(self.tid)
        self.assertIsNone(self.store.get(self.tid).slots.category)


class ExecutorTest(unittest.TestCase):
    def test_executor_receives_intent(self):
        store = ConversationStore()
        captured = {}

        def fake_exec(intent):
            captured.update(intent)
            return {"ok": True, "result": {"items": [
                {"item_name": "高帮鞋男欧货"}, {"item_name": "小白鞋"} ]}}

        r = store.chat("t", "找白色运动鞋，5个", executor=fake_exec)
        self.assertEqual(captured["tool"], "text_search")
        self.assertEqual(captured["arguments"]["category"], "鞋")
        self.assertEqual(captured["arguments"]["top_k"], 5)
        self.assertTrue(r["reply"])
        self.assertIn("2", r["reply"])

    def test_executor_error_degrades(self):
        """executor 抛异常不能崩，要返回可读错误。"""
        store = ConversationStore()

        def boom(intent):
            raise RuntimeError("后端挂了")

        r = store.chat("t", "找鞋", executor=boom)
        self.assertIn("失败", r["reply"])
        self.assertFalse(r["result"]["ok"])

    def test_no_items_reply(self):
        store = ConversationStore()

        def empty(intent):
            return {"ok": True, "result": {"items": []}}

        r = store.chat("t", "找鞋", executor=empty)
        self.assertIn("没找到", r["reply"])

    def test_history_recorded(self):
        store = ConversationStore()
        store.chat("t", "找鞋", executor=lambda i: {"ok": True, "result": {"items": []}})
        h = store.history("t")
        self.assertGreaterEqual(len(h), 2)  # user + assistant
        self.assertEqual(h[0]["role"], "user")


if __name__ == "__main__":
    unittest.main()