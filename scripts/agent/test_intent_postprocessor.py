import unittest

from scripts.agent.intent_postprocessor import normalize_tool_call


class IntentPostprocessorTest(unittest.TestCase):
    def test_tool_alias_and_category(self):
        tool, args, notes = normalize_tool_call(
            "tool_search", {"query": "白色运动鞋", "top_k": 5}, "我想找白色运动鞋"
        )
        self.assertEqual(tool, "text_search")
        self.assertEqual(args["category"], "鞋")
        self.assertIn("tool_normalized", notes)

    def test_query_cleanup(self):
        _, args, _ = normalize_tool_call(
            "text_search", {"query": "灰色的双肩包", "top_k": 5}, "有没有灰色的双肩包"
        )
        self.assertEqual(args["query"], "灰色双肩包")
        self.assertEqual(args["category"], "包")

    def test_top_k_and_category_validation(self):
        _, args, _ = normalize_tool_call(
            "text_search", {"query": "玻璃杯", "category": "未知", "top_k": 100}, "玻璃杯"
        )
        self.assertEqual(args["top_k"], 20)
        self.assertEqual(args.get("category"), "水杯")


if __name__ == "__main__":
    unittest.main()
