"""商品词 → 9 大类目 的映射表（补齐模型与规则层共同缺失的一环）。

**为什么需要这个**：
5.2 的微调数据里，tool_call 样本 15/15 都以「限制在X类」的句式显式给出类目。
模型因此只学会了「抽取句中已给的类目」，**没学过从商品名推断类目**
（RTX 5060 实测 category 准确率仅 30%，见 docs/实验五/07）。

规则层 `conversation.extract_category` 也只认 9 个类目名本身，
「炒锅」「T恤」「玻璃杯」都识别不出，同样缺这层映射。

**这个模块就是补那个缺口的**：把商品词映射到类目，作为模型输出后的后处理。
这样做而不是重训模型，理由：
  1. 映射是确定性的，规则比 4B 模型的统计推断更可靠
  2. 不用再租 GPU 重训，也不受采样不足影响
  3. 与报告口径一致：LLM 只做意图解析，类目这类枚举约束交给确定性代码

词表来源：data/processed_data_cleaning 里各类目 `type` 字段的高频值（实测统计），
不是凭感觉编的。

用法：
    from scripts.agent.category_map import infer_category
    infer_category("红色带盖炒锅")        # -> "厨房用品"
    infer_category("找一下白色T恤")       # -> "女装"（T恤在女装/男装/运动服都有，按优先级）
"""

from __future__ import annotations

import re

# 类目 -> 关键词列表。顺序重要：越具体的类目放前面，命中即返回。
# 词来自清洗数据的 type 字段高频统计。
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    # 手机壳最具体，优先匹配（避免「壳」被别的类目抢）
    "手机壳": [
        "手机壳", "手机保护壳", "保护壳", "硬壳", "软壳", "硅胶壳", "手机套",
    ],
    # 厨房用品：锅具、餐具、电饭煲等
    "厨房用品": [
        "炒锅", "炖锅", "汤锅", "压力锅", "不粘锅", "平底锅", "煎锅", "奶锅",
        "电饭煲", "锅具", "炊具", "餐具", "碗", "盘子", "碟", "筷", "勺",
        "菜刀", "砧板", "案板", "保鲜盒", "便当盒",
    ],
    # 水杯：杯壶类。注意「玻璃杯」既可能是水杯也可能是厨房餐具，归水杯
    "水杯": [
        "水杯", "保温杯", "马克杯", "茶杯", "吸管杯", "玻璃杯", "陶瓷杯",
        "水壶", "运动水壶", "杯子", "随行杯", "咖啡杯", "tumbler",
    ],
    # 鞋
    "鞋": [
        "运动鞋", "跑步鞋", "跑鞋", "休闲鞋", "板鞋", "凉鞋", "拖鞋", "皮鞋",
        "高帮鞋", "低帮鞋", "帆布鞋", "乐福鞋", "小白鞋", "球鞋", "鞋",
    ],
    # 包
    "包": [
        "双肩包", "背包", "书包", "电脑包", "斜挎包", "单肩包", "手提包",
        "腰包", "胸包", "行李箱", "包",
    ],
    # 运动服：明显带运动属性的服装
    "运动服": [
        "运动套装", "运动外套", "运动夹克", "运动裤", "运动长袖", "运动短袖",
        "瑜伽服", "瑜伽套装", "健身服", "速干衣", "冲锋衣", "卫衣", "连帽卫衣",
        "圆领卫衣",
    ],
    # 女装
    "女装": [
        "连衣裙", "半身裙", "裙子", "针织衫", "针织毛衣", "毛衣", "针织开衫",
        "羽绒服", "女装", "女士", "T恤", "t恤", "衬衫", "上衣", "打底衫",
    ],
    # 男装
    "男装": [
        "男士", "男装", "牛仔裤", "牛仔长裤", "休闲长裤", "长裤", "短裤",
        "直筒裤", "衬衫", "夹克", "立领夹克", "polo", "Polo",
    ],
    # 家居用品
    "家居用品": [
        "枕套", "枕头", "装饰画", "相框", "收纳盒", "收纳箱", "窗帘", "遮光帘",
        "床单", "被套", "四件套", "毛毯", "地毯", "抱枕", "家居",
    ],
}

# 匹配优先级：越具体的类目优先，避免「T恤」被运动服抢走（运动服里也有T恤）
PRIORITY = [
    "手机壳", "厨房用品", "水杯", "家居用品",
    "运动服", "鞋", "包", "女装", "男装",
]


def infer_category(text: str) -> str | None:
    """从一句话里推断商品类目。匹配不到返回 None。

    Args:
        text: 用户原话或 query

    Returns:
        9 大类目之一，或 None

    Example:
        >>> infer_category("红色带盖炒锅")
        '厨房用品'
        >>> infer_category("找一下白色T恤")
        '女装'
        >>> infer_category("随便看看有什么")  # None
    """
    if not text:
        return None

    s = str(text)

    # 1. 先精确找类目名本身（最强信号）
    for cat in PRIORITY:
        if cat in s:
            return cat
    # 「鞋类」这类带后缀的写法
    if "鞋" in s:
        return "鞋"
    if "包" in s:
        return "包"

    # 2. 再找关键词，按优先级
    for cat in PRIORITY:
        for kw in CATEGORY_KEYWORDS[cat]:
            if kw in s:
                return cat

    return None


def infer_category_with_source(text: str) -> tuple[str | None, str]:
    """返回 (类目, 依据)，依据用于 thinking 文案与调试。

    Returns:
        ("厨房用品", "keyword:炒锅") / ("鞋", "category-name") / (None, "none")
    """
    if not text:
        return None, "empty"

    s = str(text)
    for cat in PRIORITY:
        if cat in s:
            return cat, "category-name"

    for cat in PRIORITY:
        for kw in CATEGORY_KEYWORDS[cat]:
            if kw in s:
                return cat, f"keyword:{kw}"

    return None, "none"


def fill_category(arguments: dict, text: str) -> tuple[dict, str | None]:
    """模型没输出 category 时补上。已有则不覆盖（模型说的优先）。

    Args:
        arguments: 模型的 arguments
        text: 用户原话

    Returns:
        (补好的 arguments, 补的类目或 None)
    """
    if not isinstance(arguments, dict):
        return arguments, None
    if arguments.get("category"):
        return arguments, None

    cat, src = infer_category_with_source(text)
    if cat:
        arguments = dict(arguments)
        arguments["category"] = cat
        return arguments, f"{cat}（{src}）"
    return arguments, None




# ------------------------------------------------------------------
# query 清洗（与类目推断同属「确定性后处理层」）
# ------------------------------------------------------------------

# 指令性前缀，长的在前，避免「帮我找」被「找」先切坏
_COMMAND_PREFIXES = [
    "帮我搜一下", "帮我找一下", "帮我搜", "帮我找", "帮我",
    "我想找", "我想搜", "我想买", "想找", "想要",
    "有没有", "找一下", "搜一下", "搜索", "推荐", "请帮我",
    "找", "搜", "要", "来", "买个", "买",
]

# 结尾语气词与标点
_TAIL_NOISE = ["，", ",", "。", ".", "！", "!", "？", "?", "吧", "呢", "啊", "呀", "哈"]

# 数量词：「5个」「3件」
_QUANTITY_RE = re.compile(r"\d+\s*(?:个|件|条|款|双|只|套)")


def clean_query(text: str) -> str:
    """把用户原话清洗成检索词。

    规则（对照 gold 标注总结）：
      1. 去掉指令性前缀（找 / 帮我找 / 有没有 / 推荐 / 我想找…）
      2. 去掉数量词（5个 / 3件），它属于 top_k 不属于 query
      3. 去掉结尾语气词与标点
      4. **清洗后不足 2 个字就退回原话** —— 兜底场景（如「随便看看有什么」）不该被改坏

    Example:
        >>> clean_query("找卡其色立领夹克")
        '卡其色立领夹克'
        >>> clean_query("有没有灰色的双肩包")
        '灰色的双肩包'
        >>> clean_query("帮我找黑色木纹手机壳，5个")
        '黑色木纹手机壳'
        >>> clean_query("随便看看有什么")
        '随便看看有什么'
    """
    if not text:
        return ""

    s = str(text).strip()

    # 1. 去前缀（只去一次，避免把商品名里的字也吃掉）
    for p in _COMMAND_PREFIXES:
        if s.startswith(p) and len(s) > len(p) + 1:
            s = s[len(p):].strip()
            break

    # 2. 去数量词
    s = _QUANTITY_RE.sub(" ", s).strip()

    # 3. 去结尾噪声（反复几轮，处理「，5个吧」这种叠加）
    for _ in range(3):
        before = s
        s = s.strip()
        for t in _TAIL_NOISE:
            if s.endswith(t):
                s = s[: -len(t)].strip()
        if s == before:
            break

    # 4. 去掉颜色词后面跟着的结构助词「的」：「灰色的双肩包」->「灰色双肩包」
    #    只在颜色词紧邻时删除，避免误伤「的确良」这类商品名
    _COLOR_WORDS = ["白色", "黑色", "红色", "蓝色", "灰色", "卡其色", "米色", "粉色",
                    "绿色", "黄色", "紫色", "棕色", "银色", "金色", "透明"]
    for c in _COLOR_WORDS:
        s = s.replace(c + "的", c)

    # 5. 兜底：清洗过头就退回原话
    if len(s) < 2:
        return str(text).strip()

    return re.sub(r"\s+", " ", s).strip()


def fill_arguments(arguments: dict, text: str) -> tuple[dict, dict]:
    """模型输出后的确定性后处理：补类目 + 规范化 query。

    这是**生产环境的实际行为**。报告里要写明「模型 + 规则后处理」是混合方案，
    不能把后处理的效果算成模型能力。

    Args:
        arguments: 模型输出的 arguments
        text: 用户原话

    Returns:
        (补好的 arguments, 补充说明 dict)
    """
    if not isinstance(arguments, dict):
        return arguments, {}

    out = dict(arguments)
    notes: dict = {}

    # query 规范化：模型常把「找」「有没有」留在 query 里
    raw_q = out.get("query") or ""
    cleaned = clean_query(raw_q) if raw_q else clean_query(text)
    if cleaned != raw_q:
        out["query"] = cleaned
        notes["query_cleaned"] = {"from": raw_q, "to": cleaned}

    # 补类目：模型没输出时用关键词映射
    if not out.get("category"):
        cat, src = infer_category_with_source(text)
        if cat:
            out["category"] = cat
            notes["category_filled"] = {"value": cat, "source": src}

    return out, notes


__all__ = [
    "CATEGORY_KEYWORDS",
    "PRIORITY",
    "infer_category",
    "infer_category_with_source",
    "fill_category",
    "clean_query",
    "fill_arguments",
]
