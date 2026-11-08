"""langchain_agent 的单测（不依赖真实后端 / 真实模型）。

    python -m unittest scripts.agent.test_langchain_agent -v

覆盖：
  - 工具注册与参数 schema
  - LangChain 缺失时的降级（返回 None 而非崩溃）
  - text_search 工具的真实 HTTP 调用逻辑（用 mock 拦）
  - run_once 的返回结构
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.agent import langchain_agent as la  # noqa: E402


class ToolRegistrationTest(unittest.TestCase):
    def test_langchain_installed(self):
        """5.2/5.3 环境应该装了 LangChain。没装是本机环境问题，不是代码问题。"""
        if not la.LANGCHAIN_AVAILABLE:
            self.skipTest("本机未安装 LangChain，跳过工具测试")
        self.assertTrue(la.LANGCHAIN_AVAILABLE)

    def test_tool_count_and_names(self):
        if not la.LANGCHAIN_AVAILABLE:
            self.skipTest("本机未安装 LangChain")
        names = [t.name for t in la.SHOPVISION_TOOLS]
        self.assertEqual(names, ["text_search", "image_search", "image_text_match"])

    def test_text_search_schema(self):
        """模型靠 description + schema 选工具，参数名不能错。"""
        if not la.LANGCHAIN_AVAILABLE:
            self.skipTest("本机未安装 LangChain")
        tool = next(t for t in la.SHOPVISION_TOOLS if t.name == "text_search")
        schema = tool.args
        self.assertIn("query", schema)
        self.assertIn("category", schema)
        self.assertIn("top_k", schema)
        # description 里应列出可选类目，模型才知道怎么填
        self.assertIn("鞋", tool.description)
        self.assertIn("手机壳", tool.description)


class DegradeTest(unittest.TestCase):
    def test_returns_none_without_langchain(self):
        """LangChain 缺失时返回 None，让调用方降级，不能抛异常。"""
        with patch.object(la, "LANGCHAIN_AVAILABLE", False):
            self.assertIsNone(la.create_shopvision_agent())

    def test_returns_none_when_llm_init_fails(self):
        """模型初始化失败也要返回 None，不能把异常抛给 FastAPI。"""
        if not la.LANGCHAIN_AVAILABLE:
            self.skipTest("本机未安装 LangChain")
        with patch.dict(sys.modules, {"langchain_openai": None}):
            self.assertIsNone(la.create_shopvision_agent(base_url="http://x"))


class TextSearchToolTest(unittest.TestCase):
    """工具层真实逻辑：走 _http_post，用 mock 拦截。"""

    def test_success_formats_items(self):
        if not la.LANGCHAIN_AVAILABLE:
            self.skipTest("本机未安装 LangChain")
        fake = {
            "query": "白色运动鞋",
            "items": [
                {"item_id": "muge_430640", "item_name": "高帮鞋男欧货",
                 "category": "鞋", "similarity": 0.4662, "brand": "不该出现"},
            ],
        }
        with patch.object(la, "_http_post", return_value=fake):
            out = json.loads(la.text_search.invoke(
                {"query": "白色运动鞋", "category": "鞋", "top_k": 5}
            ))
        self.assertEqual(out["query"], "白色运动鞋")
        self.assertEqual(len(out["items"]), 1)
        self.assertEqual(out["items"][0]["item_id"], "muge_430640")
        # 只保留关键字段，不要把整个 result 塞给模型
        self.assertNotIn("brand", out["items"][0])

    def test_error_passthrough(self):
        if not la.LANGCHAIN_AVAILABLE:
            self.skipTest("本机未安装 LangChain")
        with patch.object(la, "_http_post", return_value={"error": "服务不可用"}):
            out = json.loads(la.text_search.invoke({"query": "鞋"}))
        self.assertIn("error", out)

    def test_top_k_clamped(self):
        if not la.LANGCHAIN_AVAILABLE:
            self.skipTest("本机未安装 LangChain")
        captured = {}

        def fake_post(path, payload, timeout=30):
            captured.update(payload)
            return {"items": []}

        with patch.object(la, "_http_post", side_effect=fake_post):
            la.text_search.invoke({"query": "鞋", "top_k": 999})
        self.assertLessEqual(captured["top_k"], 20)


class RunOnceTest(unittest.TestCase):
    def test_structure_on_success(self):
        """run_once 要返回固定结构，供 FastAPI 直接用。"""
        if not la.LANGCHAIN_AVAILABLE:
            self.skipTest("本机未安装 LangChain")
        from langchain_core.messages import AIMessage, HumanMessage

        fake_agent = MagicMock()
        fake_agent.invoke.return_value = {
            "messages": [
                HumanMessage(content="找白色运动鞋"),
                AIMessage(content="", tool_calls=[
                    {"name": "text_search", "args": {"query": "白色运动鞋"}, "id": "c1"}
                ]),
                AIMessage(content="为您找到 3 款白色运动鞋"),
            ]
        }
        out = la.run_once(fake_agent, "找白色运动鞋", thread_id="t1")
        self.assertTrue(out["ok"])
        self.assertEqual(out["reply"], "为您找到 3 款白色运动鞋")
        self.assertEqual(len(out["tool_calls"]), 1)
        self.assertEqual(out["tool_calls"][0]["name"], "text_search")

    def test_structure_on_error(self):
        if not la.LANGCHAIN_AVAILABLE:
            self.skipTest("本机未安装 LangChain")
        fake_agent = MagicMock()
        fake_agent.invoke.side_effect = RuntimeError("模型超时")
        out = la.run_once(fake_agent, "找鞋")
        self.assertFalse(out["ok"])
        self.assertIn("模型超时", out["reply"])


class SystemPromptTest(unittest.TestCase):
    def test_no_fabrication_rule(self):
        """报告要强调「不编造商品」，prompt 里必须有这条。"""
        self.assertIn("不要编造", la.SYSTEM_PROMPT)
        self.assertIn("text_search", la.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()