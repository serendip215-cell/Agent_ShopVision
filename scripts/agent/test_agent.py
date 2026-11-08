"""实验5 Agent 骨架自检：工具注册、意图编排、HTTP 调用（mock）、准确率统计框架。

不依赖 5.2 模型，也不依赖后端服务真实运行：
- 用 unittest.mock 替换 text_search 的 HTTP 请求，验证编排逻辑正确
- accuracy() 是「工具调用准确率」评测骨架（报告要求 10 轮 ≥90%），
  真正的 10 轮评测数据待 5.2 接入后从微调数据/评测用例喂入。

运行：
    python -m unittest discover -s scripts/agent -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

# 仓库根加入路径，使绝对 import 可用（仓库根下 python -m unittest discover -s scripts/agent）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.agent import agent, tools  # noqa: E402


class AgentOrchestrationTest(unittest.TestCase):
    """编排逻辑：工具名对齐、参数传递、错误处理、未知工具。"""

    fake_result = {"query": "白鞋", "category": "鞋", "query_category": "鞋",
                   "query_score": 0.9, "items": [{"item_id": "x1", "title": "白鞋"}]}

    def _run(self, intent):
        return agent.create_agent().run_intent(intent)

    def test_text_search_tool_registered(self):
        self.assertIn("text_search", tools.TOOLS)
        entry = tools.TOOLS["text_search"]
        self.assertTrue(callable(entry["fn"]))
        self.assertIn("text_search", agent.create_agent().tool_registry)

    def test_tool_call_success_via_mock_http(self):
        """mock HTTP：urllib.urlopen 返回统一契约 {code,result,msg}，验证工具链路。"""
        ok_body = json.dumps(
            {"code": 0, "msg": "", "result": self.fake_result}
        ).encode("utf-8")
        fake_resp = mock.MagicMock()
        fake_resp.read.return_value = ok_body
        fake_resp.__enter__.return_value = fake_resp
        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            out = self._run(
                {"tool": "text_search", "arguments": {"query": "白鞋", "category": "鞋", "top_k": 5}}
            )
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["items"][0]["item_id"], "x1")

    def test_unknown_tool_reports_error(self):
        out = self._run({"tool": "no_such_tool", "arguments": {}})
        self.assertFalse(out["ok"])
        self.assertIn("未找到", out["reason"])

    def test_arguments_passed_to_tool(self):
        orig = tools.TOOLS["text_search"]  # 注册表条目是 dict，fn 是 key 不是属性
        m = mock.Mock(return_value=self.fake_result)
        with mock.patch.dict(tools.TOOLS, {"text_search": {**orig, "fn": m}}):
            run = agent.create_agent().run_intent(
                {"tool": "text_search", "arguments": {"query": "白鞋", "category": "鞋", "top_k": 5}}
            )
        m.assert_called_once_with(query="白鞋", category="鞋", top_k=5)
        self.assertTrue(run["ok"])
        self.assertEqual(run["result"]["items"][0]["item_id"], "x1")

    def test_wrong_arguments_caught(self):
        # LLM 给错参数名：应捕获 TypeError 而不是崩
        out = self._run({"tool": "text_search", "arguments": {"qurey": "白鞋"}})
        self.assertFalse(out["ok"])
        self.assertIn("参数异常", out["reason"])


class AccuracyFrameTest(unittest.TestCase):
    """工具调用准确率统计骨架（报告要求：10 轮 ≥90%）。

    当前只提供统计函数与一个小示例。真实的 10 轮评测输入：
    - 5.2 交付后，用微调评测集的结构化意图作为「ground_truth」
    - 把 LLM 实际解析出的意图(agent.run)与 ground_truth 比对
    """

    @staticmethod
    def accuracy(pairs):
        """pairs: [(case_id, predicted_intent, expected_intent)]。预测命中=工具名一致且参数匹配。"""
        hit = sum(
            1 for _, p, e in pairs
            if p.get("tool") == e.get("tool") and p.get("arguments") == e.get("arguments")
        )
        return hit / len(pairs) if pairs else 1.0

    def test_accuracy_counts_hits_and_misses(self):
        self.assertEqual(self.accuracy([]), 1.0)
        self.assertEqual(self.accuracy([("a", {"tool": "text_search", "arguments": {}},
                                        {"tool": "text_search", "arguments": {}})]), 1.0)
        self.assertEqual(self.accuracy([("a", {"tool": "text_search"}, {"tool": "match"})]), 0.0)


if __name__ == "__main__":
    unittest.main()