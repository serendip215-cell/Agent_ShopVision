"""扩充 tool_call 训练数据（ZXCcs231 优化方案第二阶段）。

**为什么要做这个**：
5.1 生成的 tool_call 样本 15/15 都是「帮我搜索XXX，限制在X类，返回N个结果」，
**类目明写在句子里**。模型因此只学会「照抄句中类目」，不会从商品名推断。
5060/3080Ti 实测纯模型类目准确率仅 10%。

**这次的核心改动**：训练数据里 **不再写「限制在X类」**，
让模型必须从商品名推断类目。同时混入多种口语句式。

数据来源：`data/processed_data_cleaning` 的真实商品（item_name / type / color）。
类目关键词来自 `category_map.CATEGORY_KEYWORDS`（同一份词表，保证训练与推理一致）。

用法：
    python scripts/agent/finetune/build_tool_call_expanded.py
    # -> data/agent/agent_finetune_data_expanded.json

然后重训：
    python scripts/agent/finetune/train_lora.py \
        --train-file data/agent/sft_expanded/train.jsonl \
        --output runs_exp/5.2_lora_v2
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.agent.category_map import CATEGORY_KEYWORDS, infer_category  # noqa: E402

CATEGORIES = ["鞋", "水杯", "包", "男装", "运动服", "女装", "手机壳", "厨房用品", "家居用品"]

# 口语化句式模板 —— 关键：**不含「限制在X类」**
TEMPLATES = [
    "{query}",
    "我想找{query}",
    "帮我找{query}",
    "有没有{query}",
    "推荐{query}",
    "找一下{query}",
    "帮我搜{query}",
    "{query}，要{top_k}个",
    "我想买{query}，要{top_k}个",
    "推荐{top_k}个{query}",
    "帮我找{query}，{top_k}个",
    "有没有{query}，来{top_k}个",
    "{query}多少钱",
    "想买{query}",
    "看看{query}",
]

# 无类目兜底（模型应输出不含 category）
NO_CATEGORY_INPUTS = [
    "随便看看有什么",
    "有什么推荐的吗",
    "你们卖什么",
    "帮我找找看",
    "随便推荐点东西",
    "有什么好东西",
]


def load_products() -> list[dict]:
    """从清洗数据加载真实商品。"""
    out = []
    for f in glob.glob(str(REPO_ROOT / "data" / "processed_data_cleaning" / "*" / "products.csv")):
        cat = os.path.basename(os.path.dirname(f))
        if cat not in CATEGORIES:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    name = (row.get("item_name") or "").strip()
                    if not name or len(name) < 2:
                        continue
                    out.append({
                        "name": name,
                        "category": cat,
                        "type": (row.get("type") or "").strip(),
                        "color": (row.get("color") or "").strip(),
                        "material": (row.get("material") or "").strip(),
                        "item_id": row.get("item_id") or "",
                    })
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 读取 {f} 失败：{e}")
    return out


def build_query(p: dict) -> str:
    """构造 query。**不包含类目名**，只用颜色 + 细分类 + 商品名片段。

    这是本次扩充的关键：query 里不能有「鞋」「水杯」这类字眼，
    否则模型又会去照抄而不是推断。
    """
    parts = []
    # 颜色
    if p["color"] and p["color"] not in ("未识别", "无", ""):
        parts.append(p["color"])
    # 细分类（比 item_name 更干净）
    if p["type"]:
        parts.append(p["type"])
    # 商品名截断（去掉品牌噪声）
    name = p["name"]
    if len(name) <= 12 and p["type"] not in name:
        parts.append(name)

    q = " ".join(dict.fromkeys(parts)).strip()
    return q if len(q) >= 2 else p["name"][:12]


def main() -> None:
    ap = argparse.ArgumentParser(description="扩充 tool_call 训练数据")
    ap.add_argument("--per-category", type=int, default=8, help="每个类目生成多少条")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "data/agent/agent_finetune_data_expanded.json")
    args = ap.parse_args()

    random.seed(args.seed)
    products = load_products()
    print(f"加载 {len(products)} 条商品")

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        by_cat[p["category"]].append(p)

    records = []
    used_queries: set[str] = set()
    rid = 0

    for cat in CATEGORIES:
        pool = by_cat.get(cat, [])
        if not pool:
            print(f"[warn] {cat} 无商品")
            continue

        # 打乱后取样，并验证 query 确实能推断回该类目
        random.shuffle(pool)
        picked = 0
        for p in pool:
            if picked >= args.per_category:
                break
            query = build_query(p)
            if len(query) < 2 or query in used_queries:
                continue
            # 自检：用同一份词表推断，必须能推断回原类目
            inferred = infer_category(query)
            if inferred != cat:
                continue
            used_queries.add(query)

            tpl = random.choice(TEMPLATES)
            top_k = random.choice([3, 5, 5, 5, 8, 10])
            user_text = tpl.format(query=query, top_k=top_k)

            rid += 1
            records.append({
                "id": f"tc_exp_{rid:03d}",
                "task": "tool_call",
                "item_id": p["item_id"],
                "category": cat,
                "instruction": "把用户需求转换为白名单检索工具调用参数，只输出 JSON。",
                "input": user_text,
                "output": json.dumps({
                    "tool": "text_search",
                    "arguments": {"query": query, "category": cat, "top_k": top_k},
                }, ensure_ascii=False),
            })
            picked += 1

        print(f"  {cat}: {picked} 条")

    # 无类目兜底样本
    for s in NO_CATEGORY_INPUTS:
        rid += 1
        records.append({
            "id": f"tc_exp_{rid:03d}",
            "task": "tool_call",
            "item_id": "",
            "category": "",
            "instruction": "把用户需求转换为白名单检索工具调用参数，只输出 JSON。",
            "input": s,
            "output": json.dumps({
                "tool": "text_search",
                "arguments": {"query": s, "top_k": 5},
            }, ensure_ascii=False),
        })
    print(f"  无类目兜底: {len(NO_CATEGORY_INPUTS)} 条")

    # 保留原有的 attribute / intent 数据，只替换 tool_call
    old_path = REPO_ROOT / "data/agent/agent_finetune_data.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    kept = [x for x in old if x["task"] != "tool_call"]
    print(f"\n保留原 attribute/intent: {len(kept)} 条")

    final = kept + records
    random.shuffle(final)

    args.out.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tc = [x for x in final if x["task"] == "tool_call"]
    print(f"\n=== 结果 ===")
    print(f"tool_call: {len(tc)} 条（原 15 条）")
    print(f"总计: {len(final)} 条")
    print(f"写入: {args.out}")

    # 校验：确认扩充数据里**没有**「限制在X类」这种明写类目的句式
    explicit = sum(1 for x in tc if "限制在" in x["input"])
    print(f"\n含「限制在X类」明写类目的样本: {explicit}/{len(tc)}  ← 必须是 0")

    # 类目分布
    dist = Counter(x["category"] for x in tc)
    print("类目分布:", dict(dist))


if __name__ == "__main__":
    main()