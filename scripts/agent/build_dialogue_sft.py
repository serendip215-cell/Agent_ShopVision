#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Agent v3 的 SFT 数据：工具调用 + 对话 + 结果点评 + 澄清。

设计原则（对应 docs/实验五/10-5.4-对话Agent训练规范.md）：
  * 商品事实全部来自 data/index_data_finetuned/*/items.csv，不编造；
  * 每条 assistant 内容都是裸 JSON（无 Markdown、无解释）；
  * 结果点评样本的输入里带检索结果 JSON，与推理时第二轮同构；
  * 固定随机种子，可复现；输出前统一校验。

用法：
    python scripts/agent/build_dialogue_sft.py                      # 生成 440 条
    python scripts/agent/build_dialogue_sft.py --dry-run            # 只统计，不写盘
    python scripts/agent/build_dialogue_sft.py --out data/agent/sft_v3 --seed 7
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = REPO_ROOT / "data" / "index_data_finetuned"
DEFAULT_OUT = REPO_ROOT / "data" / "agent" / "sft_v3"
DEFAULT_SEED = 20261109

SYSTEM_PROMPT = (
    "你是电商导购助手。可用工具：\n"
    "- text_search(query, category?, top_k)：按文字找商品\n"
    "- image_search(alpha)：按用户上传的图片找相似商品\n"
    "- list_categories()：列出可检索的类目\n"
    "- get_item_detail(item_id)：查某个商品详情\n"
    '只输出一个 JSON：{"action":"tool","tool":...,"arguments":{...}} 或 '
    '{"action":"reply","text":"..."}。\n'
    "需要检索才调工具；闲聊、追问、能力介绍一律 reply。\n"
    'reply 只能引用给定信息，不得编造价格、销量、品牌。可加 "say" 说明你要做什么。'
)

SAY_POOL = [
    "我先帮你找找",
    "我查一下库里的商品",
    "好，我搜一下",
    "我看下有没有合适的",
    "稍等，我找一下",
    "我按你说的条件找找",
]

# 只拦「具体价格断言」：199元 / 售价 99 / 5折；允许“库里没有价格信息”这类诚实说明
PRICE_WORDS = re.compile(r"(\d+(?:\.\d+)?\s*元)|((?:售价|价格)\s*[为是:：]?\s*\d)|(\d+\s*折)")
MAX_SAY_LEN = 30

# 用户输入前缀：让模板能组合出互不重复的说法（去重校验要求每条唯一）
PREFIXES = ["", "请问", "想问一下，", "麻烦", "帮我"]


def _first_token(value: str) -> str:
    """多值字段（"紫色、黑色、蓝色"）取第一个词，避免查询词读起来像清单。"""
    return re.split(r"[、,，/]", value)[0].strip()


def unique_user(used: set[str], templates: list[str], **kwargs: object) -> str:
    """在模板 × 前缀里挑一个没出现过的用户输入。"""
    for prefix in PREFIXES:
        for template in templates:
            text = prefix + template.format(**kwargs)
            if text not in used:
                used.add(text)
                return text
    raise SystemExit(f"[x] 模板不够用，无法生成不重复输入：{templates[:1]} {kwargs}")


# ---------------------------------------------------------------- 数据加载

def load_items() -> list[dict]:
    """读 9 类商品的真实字段（名称/细分类/颜色/材质）。"""
    registry_path = INDEX_DIR / "index_registry.json"
    if not registry_path.is_file():
        raise SystemExit(f"[x] 找不到索引注册表：{registry_path}")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    items: list[dict] = []
    for category, entry in (registry.get("categories") or {}).items():
        csv_path = INDEX_DIR / entry["items_csv"]
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                items.append(
                    {
                        "category": category,
                        "item_id": (row.get("item_id") or "").strip(),
                        "item_name": (row.get("item_name") or "").strip(),
                        "type": (row.get("type") or row.get("product_type") or "").strip(),
                        "color": (row.get("color") or "").strip(),
                        "material": (row.get("material") or "").strip(),
                    }
                )
    if not items:
        raise SystemExit("[x] 商品库为空，检查 data/index_data_finetuned")
    return items


# ---------------------------------------------------------------- 样本构造

def dumps(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def make_sample(user: str, assistant: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": dumps(assistant)},
        ]
    }


def tool_call(tool: str, arguments: dict, say: str | None = None) -> dict:
    payload: dict = {"action": "tool", "tool": tool, "arguments": arguments}
    if say:
        payload["say"] = say
    return payload


def reply(text: str) -> dict:
    return {"action": "reply", "text": text}


def pick_query(item: dict, rng: random.Random) -> str:
    """从真实字段拼一个口语查询词（类目名不一定出现，逼模型自己推）。"""
    color = _first_token(item["color"])
    type_ = _first_token(item["type"])
    candidates = []
    if color and type_:
        candidates.append(f"{color}{type_}")
    if type_:
        candidates.append(type_)
    if color:
        candidates.append(f"{color}的{item['category']}")
    if item["item_name"]:
        candidates.append(item["item_name"][:10])
    return rng.choice(candidates) if candidates else item["category"]


def gen_text_search(
    items: list[dict], rng: random.Random, count: int, used: set[str]
) -> list[dict]:
    templates = [
        "找{query}",
        "有没有{query}",
        "推荐{top_k}个{query}",
        "帮我搜{query}",
        "我想要{query}",
        "{query}有吗",
        "看看{query}",
        "来{top_k}个{query}",
    ]
    out = []
    with_say = set(rng.sample(range(count), k=count // 2))
    for index in range(count):
        item = rng.choice(items)
        query = pick_query(item, rng)
        top_k = rng.choice([3, 5, 5, 8])
        user = unique_user(used, templates, query=query, top_k=top_k)
        say = rng.choice(SAY_POOL) if index in with_say else None
        out.append(
            make_sample(
                user,
                tool_call(
                    "text_search",
                    {"query": query, "category": item["category"], "top_k": top_k},
                    say,
                ),
            )
        )
    return out


def gen_image_search(rng: random.Random, count: int, used: set[str]) -> list[dict]:
    templates = [
        "按这张图找类似的",
        "找和这张图相似的商品",
        "这张图里的东西有卖吗",
        "图里的商品能找到吗",
        "我传的图是什么类，找同款",
        "根据这张图推荐几件",
        "这张图的同款有吗",
        "看图找相似商品",
    ]
    out = []
    with_say = set(rng.sample(range(count), k=count // 3))
    for index in range(count):
        alpha = rng.choice([0.5, 0.6, 0.6, 0.7])
        user = unique_user(used, templates)
        say = rng.choice(SAY_POOL) if index in with_say else None
        out.append(
            make_sample(user, tool_call("image_search", {"alpha": alpha}, say))
        )
    return out


def gen_list_categories(rng: random.Random, count: int, used: set[str]) -> list[dict]:
    templates = [
        "你们能搜哪些类目",
        "库里有什么商品",
        "能搜什么东西",
        "都有哪些类别",
        "支持哪些品类",
        "能搜哪几类",
        "有没有类目列表",
        "你们覆盖什么品类",
    ]
    out = []
    for _ in range(count):
        out.append(make_sample(unique_user(used, templates), tool_call("list_categories", {})))
    return out


def gen_item_detail(
    items: list[dict], rng: random.Random, count: int, used: set[str]
) -> list[dict]:
    """带上一轮上下文：让模型学会「第 N 个」对应哪条 item_id，而不是瞎猜。"""
    templates = [
        "第{index}个是什么材质",
        "第{index}个商品的颜色是什么",
        "帮我看看第{index}个的详细参数",
        "刚才第{index}个的材质呢",
    ]
    out = []
    for _ in range(count):
        picked = rng.sample(items, 3)
        context = "上一轮检索结果：\n" + "\n".join(
            f"{i + 1}. {item['item_name'][:18]}（id={item['item_id']}）"
            for i, item in enumerate(picked)
        )
        index = rng.randint(1, 3)
        user = ""
        for prefix in PREFIXES:
            for template in templates:
                candidate = f"{context}\n{prefix}{template.format(index=index)}"
                if candidate not in used:
                    used.add(candidate)
                    user = candidate
                    break
            if user:
                break
        if not user:
            raise SystemExit("[x] get_item_detail 模板不够用")
        out.append(
            make_sample(
                user,
                tool_call("get_item_detail", {"item_id": picked[index - 1]["item_id"]}),
            )
        )
    return out


def _fmt_list(values: list[str]) -> str:
    """多值字段（如“白色、黑色”）只取前一个词，最多列两项，避免点评里堆一长串。"""
    firsts = []
    for value in values:
        token = re.split(r"[、,，/]", value)[0].strip()
        if token:
            firsts.append(token)
    unique = [value for value in dict.fromkeys(firsts) if value]
    return "、".join(unique[:2]) if unique else ""


def gen_comments(items: list[dict], rng: random.Random, count: int) -> list[dict]:
    """结果点评：输入带 5 条真实商品字段，输出只引用这些字段。"""
    by_category: dict[str, list[dict]] = {}
    for item in items:
        by_category.setdefault(item["category"], []).append(item)

    usable = {key: value for key, value in by_category.items() if len(value) >= 5}
    if not usable:
        raise SystemExit("[x] 没有哪个类目凑得齐 5 条商品，无法生成点评样本")

    categories = list(usable)
    out = []
    for index in range(count):
        category = categories[index % len(categories)]
        picked = rng.sample(usable[category], 5)
        payload = {
            "items": [
                {
                    "item_name": item["item_name"] or "未命名商品",
                    "type": item["type"] or "未分类",
                    "color": item["color"] or "未标注",
                    "material": item["material"] or "未识别",
                    "similarity": round(rng.uniform(0.42, 0.52), 2),
                }
                for item in picked
            ]
        }
        query = pick_query(picked[0], rng)
        user = (
            f"用户想要{query}，检索结果：\n{dumps(payload)}\n"
            "请基于以上字段写 60-120 字的点评。"
        )

        colors = [item["color"] for item in picked if item["color"]]
        types = [item["type"] for item in picked if item["type"]]
        materials = [item["material"] for item in picked if item["material"]]
        color_text = _fmt_list(colors) or "颜色"
        type_text = _fmt_list(types) or "同类"
        if materials:
            material_text = f"其中 {len(materials)} 款标了材质（{_fmt_list(materials)}），其余未标注"
        else:
            material_text = "材质字段大多未标注"
        text = (
            f"这几款以{color_text}为主，{type_text}居多，风格偏日常；"
            f"{material_text}。相似度都在 {min(i['similarity'] for i in payload['items']):.2f} 以上。"
        )
        out.append(make_sample(user, reply(text[:118])))
    return out


# 对话样本：每组 3 种用户说法，同一条回复
DIALOG_GROUPS: list[tuple[list[str], str]] = [
    (["你好", "您好", "在吗"], "你好，我是导购助手，可以帮你按描述或图片找商品。"),
    (["你能干什么", "你会什么", "有什么功能"], "我能在 9 类商品里按文字或图片检索，也能聊聊商品和使用场景。"),
    (["谢谢", "太好了", "麻烦了"], "不客气，需要找别的随时说。"),
    (["你是谁", "你是机器人吗", "你是什么模型"], "我是接在商品库上的导购助手，检索用的是图文双塔模型。"),
    (["早上好", "晚上好", "下午好"], "你好，想看点什么？可以描述款式，也可以直接传图。"),
    (["再见", "拜拜", "下次聊"], "好的，随时回来找我找商品。"),
    (["这个贵吗", "有便宜点的吗", "能便宜吗"], "商品库里没有价格信息，我按款式和相似度帮你找，价格要看去哪儿买。"),
    (["能退货吗", "怎么退换", "售后怎么办"], "退换货要看具体店铺政策，我这边只负责帮找商品。"),
    (["能开发票吗", "发票怎么开", "怎么开票"], "开票需要联系卖家，我这里查不到。"),
    (["你数据从哪来的", "数据是真的吗", "库有多大"], "库里有 9 类共 9,393 条商品图文，来自公开数据清洗后的结果。"),
    (["帮我写代码", "写首诗", "做个 PPT"], "这个不在我能力范围内，我主要负责商品检索和导购。"),
    (["你好聪明", "你真好", "厉害"], "谢谢，能帮上忙就好。"),
    (["怎么用", "怎么搜索", "教我用"], "直接说需求，比如“找一双白色运动鞋”，或者上传一张商品图。"),
    (["搜索不到怎么办", "找不着", "没有结果"], "可以换个说法、去掉太细的限制，或者放宽类目再找。"),
    (["能识图吗", "能看懂图片吗", "能看图吗"], "图片由图像塔负责编码检索，我能按图找相似商品。"),
    (["你支持语音吗", "能说话吗", "能语音吗"], "目前只支持文字和图片输入。"),
    (["商品有货吗", "库存多少", "还有吗"], "库里没有实时库存，只能帮你找相似商品。"),
    (["怎么联系客服", "人工客服", "找客服"], "这里没有人工客服入口，可以联系购买平台的客服。"),
    (["有什么推荐", "推荐点东西", "随便推荐"], "可以说说想要的类型或颜色，我按条件找；也可以先看看鞋或包。"),
    (["你懂搭配吗", "怎么搭配", "搭配建议"], "我能从颜色和细分类给点参考，更细的搭配建议还得你自己拿主意。"),
    (["能比价吗", "哪个便宜", "差价大吗"], "库里没有价格字段，没法比价。"),
    (["帮我下单", "直接买", "加购物车"], "我只能找商品，下单要去对应平台。"),
    (["图片模糊怎么办", "拍不清", "图片太小"], "换一张光线好、主体完整的正视图，检索会更准。"),
    (["能搜品牌吗", "有耐克吗", "有阿迪吗"], "可以用品牌词试试，不过品牌字段不一定齐全。"),
    (["你几岁了", "你有名字吗", "你叫什么"], "我是导购助手，没有年龄，名字就叫 ShopVision。"),
    (["今天天气怎么样", "几点了", "讲个笑话"], "这些我不太擅长，还是帮你找商品更靠谱。"),
    (["嗯", "哦", "好的"], "需要找什么随时说。"),
    (["刚才那个再看下", "上一个还有吗", "刚才那个呢"], "可以点上方卡片查看详情，也可以把商品名告诉我再查。"),
    (["为什么要用你", "有什么好处", "优势是什么"], "一句话就能检索 9 类商品，还能按图找同款，比翻列表快。"),
    (["模型多大", "参数量多少", "什么模型"], "对话模型是 4B 的微调版本，检索用的是双塔模型。"),
]

CLARIFY_GROUPS: list[tuple[list[str], str]] = [
    (["随便看看", "都行", "你看着办"], "想看哪一类？鞋、包、水杯、衣服，还是家居用品？"),
    (["找点东西", "帮我找", "有没有商品"], "可以给我一个关键词吗？比如“白色运动鞋”或“保温杯”。"),
    (["好看的", "好一点的", "高端点的"], "能补充下品类或颜色吗？我好按条件找。"),
    (["就那个", "你知道的", "老样子"], "我这边没有历史偏好，说说这次想要什么？"),
    (["便宜的", "性价比高的", "实惠的"], "库里没有价格信息，说说品类和你更看重的点吧。"),
    (["多一点", "再来几个", "还有别的吗"], "可以，先告诉我想找的类目，我再多给几条。"),
    (["图片里的", "这个图", "刚才那张图"], "请重新上传一张图，我按图找相似商品。"),
    (["不要鞋", "换一类", "别的类目"], "那想看包、水杯、衣服还是家居用品？"),
    (["颜色随便", "都好看", "无所谓"], "颜色随便的话，说下品类我直接找。"),
    (["男款女款都行", "不限", "都可以"], "那先定个品类吧，比如运动鞋或双肩包。"),
]


def gen_dialogs() -> list[dict]:
    out = []
    for variants, text in DIALOG_GROUPS:
        for user in variants:
            out.append(make_sample(user, reply(text)))
    return out


def gen_clarify() -> list[dict]:
    out = []
    for variants, text in CLARIFY_GROUPS:
        for user in variants:
            out.append(make_sample(user, reply(text)))
    return out


# ---------------------------------------------------------------- 校验与写盘

def validate(samples: list[dict]) -> Counter:
    counts: Counter = Counter()
    seen: set[str] = set()
    for sample in samples:
        messages = sample["messages"]
        if len(messages) != 3 or messages[2]["role"] != "assistant":
            raise SystemExit("[x] 结构错误：样本不是 system/user/assistant 三段")
        payload = json.loads(messages[2]["content"])
        action = payload.get("action")
        counts[action] += 1

        if action == "tool":
            counts[f"tool:{payload.get('tool')}"] += 1
            say = payload.get("say")
            if say:
                if len(say) > MAX_SAY_LEN:
                    raise SystemExit(f"[x] say 超长：{say}")
                counts["with_say"] += 1
        elif action == "reply":
            text = payload.get("text") or ""
            if not text.strip():
                raise SystemExit("[x] reply 为空")
            if PRICE_WORDS.search(text):
                raise SystemExit(f"[x] reply 含具体价格断言：{text}")
        else:
            raise SystemExit(f"[x] 未知 action：{action}")

        key = messages[1]["content"] + messages[2]["content"]
        if key in seen:
            raise SystemExit(f"[x] 重复样本：{messages[1]['content'][:20]}")
        seen.add(key)
    return counts


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Agent v3 对话/工具 SFT 数据")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子")
    parser.add_argument("--limit", type=int, default=440, help="总条数上限")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写盘")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    items = load_items()
    print(f"[1/4] 商品库：{len(items)} 条，{len({i['category'] for i in items})} 个类目")

    samples: list[dict] = []
    used: set[str] = set()
    samples += gen_text_search(items, rng, 120, used)
    samples += gen_image_search(rng, 40, used)
    samples += gen_list_categories(rng, 20, used)
    samples += gen_item_detail(items, rng, 20, used)
    samples += gen_comments(items, rng, 120)
    samples += gen_dialogs()
    samples += gen_clarify()
    print(
        f"[2/4] 生成 {len(samples)} 条"
        f"（对话 {len(DIALOG_GROUPS) * 3}、澄清 {len(CLARIFY_GROUPS) * 3}）"
    )

    if args.limit and len(samples) > args.limit:
        samples = samples[: args.limit]
        print(f"      按 --limit 截断到 {len(samples)} 条")

    counts = validate(samples)
    print(f"[3/4] 校验通过：{dict(counts)}")

    if args.dry_run:
        print("[4/4] --dry-run，未写文件")
        return 0

    rng.shuffle(samples)
    split = max(1, int(len(samples) * 0.9))
    train, valid = samples[:split], samples[split:]

    out_dir = Path(args.out)
    write_jsonl(out_dir / "train.jsonl", train)
    write_jsonl(out_dir / "valid.jsonl", valid)
    manifest = {
        "version": "v3",
        "seed": args.seed,
        "total": len(samples),
        "train": len(train),
        "valid": len(valid),
        "counts": dict(counts),
        "source": "data/index_data_finetuned/*/items.csv",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[4/4] 已写入 {out_dir}：train={len(train)} valid={len(valid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
