"""category_map 的单测：类目推断 + query 清洗 + 完整后处理。

    python -m unittest scripts.agent.test_category_map -v

这是 5.3 实测 20% 之后的修复核心：
训练集 15/15 的 tool_call 输入都以「限制在X类」显式给出类目，
模型没学过从商品名推断类目。所以用确定性映射补上这一环。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.agent.category_map import (  # noqa: E402
    clean_query,
    fill_arguments,
    fill_category,
    infer_category,
    infer_category_with_source,
)


class InferCategoryTest(unittest.TestCase):
    def test_category_name_itself(self):
        """类目名直接出现在句子里，最强信号。"""
        self.assertEqual(infer_category("帮我找黑色木纹手机壳，5个"), "手机壳")
        self.assertEqual(infer_category("我想找白色运动鞋"), "鞋")
        self.assertEqual(infer_category("推荐3个蓝色运动水杯"), "水杯")

    def test_keyword_mapping(self):
        """5.3 实测里模型答错的这几条，必须靠关键词救回来。"""
        self.assertEqual(infer_category("红色带盖炒锅"), "厨房用品")
        self.assertEqual(infer_category("帮我搜透明玻璃杯，10个"), "水杯")
        self.assertEqual(infer_category("黑色运动长袖套装"), "运动服")
        self.assertEqual(infer_category("找一下白色T恤"), "女装")
        self.assertEqual(infer_category("找卡其色立领夹克"), "男装")
        self.assertEqual(infer_category("有没有灰色的双肩包"), "包")

    def test_none_when_no_signal(self):
        """没有商品词时不能瞎猜。"""
        self.assertIsNone(infer_category("随便看看有什么"))
        self.assertIsNone(infer_category(""))
        self.assertIsNone(infer_category("你好"))

    def test_priority_mobile_case_over_others(self):
        """手机壳最具体，不能被含「壳」的其他词抢走。"""
        self.assertEqual(infer_category("硬壳手机壳"), "手机壳")

    def test_source_reporting(self):
        """能说明是靠哪个词命中的，供 thinking 与调试用。"""
        cat, src = infer_category_with_source("红色带盖炒锅")
        self.assertEqual(cat, "厨房用品")
        self.assertIn("炒锅", src)

        cat2, src2 = infer_category_with_source("白色运动鞋")
        self.assertEqual(cat2, "鞋")
        self.assertEqual(src2, "category-name")


class CleanQueryTest(unittest.TestCase):
    def test_strip_command_prefix(self):
        self.assertEqual(clean_query("找卡其色立领夹克"), "卡其色立领夹克")
        self.assertEqual(clean_query("帮我找黑色木纹手机壳"), "黑色木纹手机壳")
        self.assertEqual(clean_query("我想找白色运动鞋"), "白色运动鞋")

    def test_strip_quantity(self):
        """数量属于 top_k，不该留在 query 里。"""
        self.assertNotIn("5", clean_query("帮我找黑色木纹手机壳，5个"))
        self.assertNotIn("10", clean_query("帮我搜透明玻璃杯，10个"))

    def test_strip_tail_noise(self):
        self.assertEqual(clean_query("找一下白色T恤"), "白色T恤")

    def test_color_de(self):
        """「灰色的双肩包」→「灰色双肩包」，但只删颜色词后面的「的」。"""
        self.assertEqual(clean_query("有没有灰色的双肩包"), "灰色双肩包")

    def test_fallback_keeps_original(self):
        """兜底场景：清洗后太短就退回原话，不能把「随便看看有什么」改坏。"""
        self.assertEqual(clean_query("随便看看有什么"), "随便看看有什么")

    def test_empty(self):
        self.assertEqual(clean_query(""), "")


class FillArgumentsTest(unittest.TestCase):
    def test_fills_missing_category(self):
        args, notes = fill_arguments({"query": "红色带盖炒锅", "top_k": 5}, "红色带盖炒锅")
        self.assertEqual(args["category"], "厨房用品")
        self.assertIn("category_filled", notes)

    def test_keeps_existing_category(self):
        """模型自己给了类目就不覆盖 —— 模型优先。"""
        args, notes = fill_arguments(
            {"query": "鞋", "category": "鞋", "top_k": 5}, "找运动鞋"
        )
        self.assertEqual(args["category"], "鞋")
        self.assertNotIn("category_filled", notes)

    def test_cleans_query(self):
        args, notes = fill_arguments({"query": "找卡其色立领夹克", "top_k": 5},
                                     "找卡其色立领夹克")
        self.assertEqual(args["query"], "卡其色立领夹克")
        self.assertIn("query_cleaned", notes)

    def test_no_notes_when_nothing_changed(self):
        args, notes = fill_arguments(
            {"query": "白色运动鞋", "category": "鞋", "top_k": 5}, "白色运动鞋"
        )
        self.assertEqual(notes, {})

    def test_handles_non_dict(self):
        args, notes = fill_arguments(None, "找鞋")
        self.assertIsNone(args)

    def test_fill_category_helper(self):
        args, filled = fill_category({"query": "炒锅", "top_k": 5}, "红色带盖炒锅")
        self.assertEqual(args["category"], "厨房用品")
        self.assertIn("厨房用品", filled)


class EndToEndOnEvalSetTest(unittest.TestCase):
    """用 5.3 的 10 轮评测集做端到端后处理验证。"""

    def test_post_process_covers_all_ten(self):
        from scripts.agent.eval_tool_accuracy import CASES

        missed = []
        for c in CASES:
            gold = c["gold"]["arguments"]
            # 模拟模型输出：query 原样照抄、无 category
            args, _ = fill_arguments(
                {"query": c["input"], "top_k": gold["top_k"]}, c["input"]
            )
            q_ok = "".join(args['query'].split()) == "".join(gold["query"].split())
            c_ok = (args.get("category") or None) == (gold.get("category") or None)
            if not (q_ok and c_ok):
                missed.append((c["id"], c["input"], args))

        self.assertEqual(missed, [], f"后处理未覆盖：{missed}")



class ProductionPipelineTest(unittest.TestCase):
    """生产链路必须也走后处理 —— 否则评测分与实际演示行为不一致。"""

    def test_parse_intent_applies_post_process(self):
        from unittest.mock import patch

        import scripts.agent.agent as ag

        fake_output = {
            "tool": "text_search",
            "arguments": {"query": "找卡其色立领夹克", "top_k": 5},
        }

        class FakeParser:
            def parse(self, user_input):
                return dict(fake_output)

        with patch.object(ag, "_get_parser", return_value=FakeParser()):
            out = ag._parse_intent("找卡其色立领夹克")

        self.assertEqual(out["arguments"]["category"], "男装")
        self.assertEqual(out["arguments"]["query"], "卡其色立领夹克")
        self.assertIn("post_process", out)

    def test_post_process_exception_does_not_break_pipeline(self):
        """后处理出错不能影响主链路。"""
        from unittest.mock import patch

        import scripts.agent.agent as ag

        class FakeParser:
            def parse(self, user_input):
                return {"tool": "text_search", "arguments": {"query": "鞋", "top_k": 5}}

        with patch.object(ag, "_get_parser", return_value=FakeParser()), \
             patch("scripts.agent.category_map.fill_arguments", side_effect=RuntimeError("boom")):
            out = ag._parse_intent("找鞋")

        # 原始意图仍然返回
        self.assertEqual(out["tool"], "text_search")
        self.assertIn("arguments", out)



class HoldoutGeneralizationTest(unittest.TestCase):
    """留出集：训练集与评测集都没出现过的输入，检验泛化。

    回应「10 条测试集是不是自己出题自己答」的质疑：
    这 15 条是全新表达，含更口语的句式与易混淆词。
    """

    HOLDOUT_CATEGORY = [
        ("我想买个能保温的杯子", "水杯"),
        ("有没有那种跑步穿的运动裤", "运动服"),
        ("帮我看看这个枕头套", "家居用品"),
        ("推荐几款双肩背包给上学的孩子", "包"),
        ("这双帆布鞋多少钱", "鞋"),
        ("我要买男士牛仔裤", "男装"),
        ("想买条连衣裙夏天穿", "女装"),
        ("厨房需要个炒菜的锅", "厨房用品"),
        ("手机保护壳有什么好看的", "手机壳"),
        ("这个马克杯能装多少毫升", "水杯"),
        ("买个遮光窗帘", "家居用品"),
        ("运动套装有没有加大码", "运动服"),
        ("斜挎包适合男生吗", "包"),
        ("篮球鞋推荐", "鞋"),
        ("电饭煲哪个牌子好", "厨房用品"),
        ("帮我找找看", None),
        ("你好", None),
        ("今天天气怎么样", None),
        ("这个多少钱", None),
        ("随便推荐点东西吧", None),
    ]

    def test_category_accuracy_on_holdout(self):
        misses = []
        for text, expected in self.HOLDOUT_CATEGORY:
            got = infer_category(text)
            if (expected or None) != (got or None):
                misses.append((text, expected, got))
        # 允许 1 条漏判（规则层不可能 100%，但必须 ≥95%）
        self.assertLessEqual(len(misses), 1, f"留出集漏判过多：{misses}")

    def test_no_residual_quantifier(self):
        """清洗后不能留光杆量词残字。"""
        cases = [
            ("我想买个能保温的杯子", "能保温的杯子"),
            ("推荐几款双肩背包给上学的孩子", "双肩背包给上学的孩子"),
            ("几双运动鞋", "运动鞋"),
        ]
        for src, expected in cases:
            self.assertEqual(clean_query(src), expected, f"{src!r} 清洗不对")

    def test_keeps_shuang_in_product_name(self):
        """「双肩包」的「双」不能被当量词吃掉 —— 实测踩过这个坑。"""
        self.assertEqual(clean_query("双肩包"), "双肩包")
        self.assertIn("双肩背包", clean_query("推荐几款双肩背包给上学的孩子"))

    def test_removes_youmeiyou(self):
        self.assertEqual(clean_query("有没有那种跑步穿的运动裤"), "跑步穿的运动裤")


if __name__ == "__main__":
    unittest.main()