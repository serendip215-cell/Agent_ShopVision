"""intent_parser 的单测（纯逻辑，不需要 GPU / 模型权重）。

    python -m unittest scripts.agent.test_intent_parser -v

覆盖 5.2 实测暴露的问题：
  - 模型把 text_search 写成 tool_search 时能被纠错
  - 各种 JSON 包裹能解析
  - 模型完全胡说时降级到规则解析
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.agent.intent_parser import (  # noqa: E402
    closest_tool,
    normalize_intent,
    parse_json_lenient,
    rule_parse,
)


class ToolNameCorrectionTest(unittest.TestCase):
    """5.2 实测：模型输出 tool_search，正确是 text_search。"""

    def test_exact_match(self):
        self.assertEqual(closest_tool("text_search"), "text_search")

    def test_measured_typo(self):
        """真实失败案例：多写了一个 tool_ 前缀。"""
        self.assertEqual(closest_tool("tool_search"), "text_search")

    def test_other_plausible_typos(self):
        for bad in ["textsearch", "Text_Search", "text-searc", "search_text"]:
            self.assertEqual(closest_tool(bad), "text_search", f"{bad} 应被纠错")

    def test_garbage_not_forced(self):
        """完全不相关的不该强行对齐，否则会掩盖真问题。"""
        self.assertIsNone(closest_tool("image_resize_magic"))
        self.assertIsNone(closest_tool(""))

    def test_unknown_tool_falls_back_to_rules(self):
        """未知工具应降级规则解析，而不是返回错误意图。"""
        raw = {"tool": "totally_unknown_xyz", "arguments": {"query": "白色运动鞋"}}
        out = normalize_intent(raw, "找白色运动鞋")
        self.assertEqual(out["tool"], "text_search")
        self.assertIn("query", out["arguments"])


class JsonToleranceTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_json_lenient('{"a":1}'), {"a": 1})

    def test_markdown_wrapped(self):
        s = '好的，我来帮您：\n```json\n{"tool":"text_search"}\n```'
        self.assertEqual(parse_json_lenient(s), {"tool": "text_search"})

    def test_prose_wrapped(self):
        s = '解析结果是 {"tool":"text_search","arguments":{"query":"鞋"}} 希望有帮助'
        out = parse_json_lenient(s)
        self.assertEqual(out["tool"], "text_search")

    def test_not_json(self):
        self.assertIsNone(parse_json_lenient("我不知道"))
        self.assertIsNone(parse_json_lenient("[1,2,3]"))


class RuleFallbackTest(unittest.TestCase):
    """方案 P0：不接 LLM 也要能演示。"""

    def test_extracts_category(self):
        out = rule_parse("帮我找黑色运动鞋")
        self.assertEqual(out["tool"], "text_search")
        self.assertEqual(out["arguments"]["category"], "鞋")

    def test_extracts_top_k(self):
        out = rule_parse("找3个白色水杯")
        self.assertEqual(out["arguments"]["top_k"], 3)
        self.assertEqual(out["arguments"]["category"], "水杯")

    def test_default_top_k(self):
        out = rule_parse("找运动水杯")
        self.assertEqual(out["arguments"]["top_k"], 5)

    def test_no_category_leaves_it_out(self):
        """抓不到类目就不传，让后端自动判类。"""
        out = rule_parse("随便看看有什么")
        self.assertNotIn("category", out["arguments"])

    def test_top_k_clamped(self):
        out = rule_parse("给我99个包")
        self.assertLessEqual(out["arguments"]["top_k"], 20)


class NormalizeIntentTest(unittest.TestCase):
    def test_flat_arguments(self):
        """有的模型把参数平铺在顶层。"""
        raw = {"tool": "text_search", "query": "白色运动鞋", "category": "鞋", "top_k": 3}
        out = normalize_intent(raw, "找白色运动鞋")
        self.assertEqual(out["arguments"]["query"], "白色运动鞋")
        self.assertEqual(out["arguments"]["top_k"], 3)

    def test_missing_query_degrades(self):
        raw = {"tool": "text_search", "arguments": {"category": "鞋"}}
        out = normalize_intent(raw, "找鞋子")
        self.assertIn("query", out["arguments"])

    def test_bad_top_k(self):
        raw = {"tool": "text_search", "arguments": {"query": "鞋", "top_k": "abc"}}
        out = normalize_intent(raw, "找鞋")
        self.assertEqual(out["arguments"]["top_k"], 5)

    def test_none_input(self):
        out = normalize_intent(None, "找白色运动鞋")
        self.assertEqual(out["tool"], "text_search")



class NameFieldTest(unittest.TestCase):
    """5060 实测：模型有 4/10 条输出 {"name": ...} 而不是 {"tool": ...}。

    这算真实的模型行为差异，解析层必须兼容 —— 否则整条判为「未知工具」。
    """

    def test_name_field_recognized(self):
        raw = {"name": "text_search", "arguments": {"query": "黑色木纹手机壳", "top_k": 5}}
        out = normalize_intent(raw, "帮我找黑色木纹手机壳，5个")
        self.assertEqual(out["tool"], "text_search")
        self.assertEqual(out["arguments"]["query"], "黑色木纹手机壳")

    def test_name_field_with_typo_still_corrected(self):
        """name 字段 + 工具名拼错，两个问题都要处理。"""
        raw = {"name": "tool_search", "arguments": {"query": "鞋", "top_k": 5}}
        out = normalize_intent(raw, "找鞋")
        self.assertEqual(out["tool"], "text_search")

    def test_function_field_recognized(self):
        """OpenAI function calling 风格。"""
        raw = {"function": "text_search", "arguments": {"query": "水杯", "top_k": 3}}
        out = normalize_intent(raw, "找水杯")
        self.assertEqual(out["tool"], "text_search")


if __name__ == "__main__":
    unittest.main()