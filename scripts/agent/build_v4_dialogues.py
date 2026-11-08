#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Agent v4 多轮对话训练集（含上下文记录）。

与 v3（单轮）的区别：
  * 每条样本是一段 2–6 轮的完整对话：user / assistant 交替，assistant 只输出协议 JSON；
  * **上下文记录**：工具执行结果以固定前缀 `检索结果：{...}` 的 user 消息注入，
    与后端第二轮回喂格式一致（训练/推理同构）；
  * 覆盖省略继承、指代查详情、话题切换、纠错、澄清追问、纯单轮六类场景；
  * 商品字段（名称/细分类/颜色/材质/id）全部取自 data/index_data_finetuned 的真实 CSV。

用法：
    python scripts/agent/build_v4_dialogues.py --dry-run     # 只统计
    python scripts/agent/build_v4_dialogues.py               # 生成到 data/agent/sft_v4
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_dialogue_sft import (  # noqa: E402
    SAY_POOL,
    gen_clarify as gen_clarify_single,
    gen_comments,
    gen_dialogs,
    gen_image_search,
    gen_item_detail,
    gen_list_categories,
    gen_text_search,
    load_items,
    pick_query,
)

DEFAULT_OUT = REPO_ROOT / "data" / "agent" / "sft_v4"
DEFAULT_SEED = 20261110
RESULT_PREFIX = "检索结果："

V4_SYSTEM_PROMPT = (
    "你是电商导购助手，支持多轮对话。可用工具：\n"
    "- text_search(query, category?, top_k)：按文字找商品\n"
    "- image_search(alpha)：按用户上传的图片找相似商品\n"
    "- list_categories()：列出可检索的类目\n"
    "- get_item_detail(item_id)：查某个商品详情\n"
    "只输出一个 JSON：{\"action\":\"tool\",\"tool\":...,\"arguments\":{...}} 或 "
    "{\"action\":\"reply\",\"text\":\"...\"}。\n"
    "多轮规则：\n"
    "1. 用户省略的条件（类目、颜色、数量）要沿用上一轮，不要重复追问；\n"
    "2. 工具结果会以「" + RESULT_PREFIX + "」开头的消息给出，其中的商品信息才可作为事实引用；\n"
    "3. 用户说「第 N 个」「刚才那个」时，用上一轮结果里的 item_id 调 get_item_detail；\n"
    "4. 用户明确换类目时，旧的颜色/描述要丢掉，不能串到新类目；\n"
    "5. 闲聊、追问、能力介绍一律 reply；reply 不得编造价格、销量、品牌；\n"
    "6. 始终以客服口吻对用户说话：说「帮你」，不要说「帮我」。"
)

PRICE_CLAIM = re.compile(
    r"(\d+(?:\.\d+)?\s*元)|([¥￥]\s*\d)|((?:售价|价格)\s*[为是:：]?\s*\d)|(\d+\s*折)"
    r"|((?:销量|已售|已有)\s*\d)|(\d+\s*[+万多]?\s*人(?:买|付款|购买|好评))"
)
TOOLS = {"text_search", "image_search", "list_categories", "get_item_detail"}
MAX_SAY = 30


# ---------------------------------------------------------------- 基础构件

def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def assistant(payload: dict) -> dict:
    return {"role": "assistant", "content": _json(payload)}


def tool(name: str, arguments: dict, say: str | None = None) -> dict:
    payload: dict = {"action": "tool", "tool": name, "arguments": arguments}
    if say:
        payload["say"] = say
    return payload


def reply(text: str) -> dict:
    return {"action": "reply", "text": text}


def result_message(items: list[dict]) -> dict:
    """上下文记录：工具结果以固定前缀注入，与后端第二轮格式一致。"""
    payload = {
        "items": [
            {
                "item_id": item["item_id"],
                "item_name": item["item_name"] or "未命名商品",
                "type": item["type"] or "未分类",
                "color": item["color"] or "未标注",
                "material": item["material"] or "未识别",
                "similarity": item["similarity"],
            }
            for item in items
        ]
    }
    return user(RESULT_PREFIX + _json(payload))


def conversation(turns: list[dict]) -> dict:
    return {"messages": [{"role": "system", "content": V4_SYSTEM_PROMPT}, *turns]}


def comment_text(items: list[dict]) -> str:
    """基于真实字段的点评（与 v3 同风格）。"""
    def first(value: str) -> str:
        return re.split(r"[、,，/]", value)[0].strip()

    colors = [first(item["color"]) for item in items if item["color"]]
    types = [first(item["type"]) for item in items if item["type"]]
    materials = [first(item["material"]) for item in items if item["material"]]
    color_text = "、".join(list(dict.fromkeys(colors))[:2]) or "常见颜色"
    type_text = "、".join(list(dict.fromkeys(types))[:2]) or "同类"
    if materials:
        material_text = f"其中 {len(materials)} 款标了材质（{'、'.join(list(dict.fromkeys(materials))[:2])}），其余未标注"
    else:
        material_text = "材质字段大多未标注"
    lowest = min(item["similarity"] for item in items)
    return (
        f"这几款以{color_text}为主，{type_text}居多，风格偏日常；"
        f"{material_text}。相似度都在 {lowest:.2f} 以上。"
    )[:118]


def v4_query(item: dict, rng: random.Random) -> str:
    """更真实的查询词：优先「颜色+细分类」，其次细分类、完整商品名，最后类目。"""
    color = re.split(r"[、,，/]", item.get("color") or "")[0].strip()
    type_ = re.split(r"[、,，/]", item.get("type") or "")[0].strip()
    name = (item.get("item_name") or "").strip()
    options = []
    if color and type_:
        options.append(f"{color}{type_}")
    if type_:
        options.append(type_)
    if 2 <= len(name) <= 18:
        options.append(name)
    if color:
        options.append(f"{color}的{item['category']}")
    return rng.choice(options) if options else item["category"]


def make_items(rng: random.Random, category_pool: dict[str, list[dict]], category: str) -> list[dict]:
    picked = rng.sample(category_pool[category], 5)
    return [
        {
            "category": category,
            "item_id": item["item_id"],
            "item_name": item["item_name"],
            "type": item["type"],
            "color": item["color"],
            "material": item["material"],
            "similarity": round(rng.uniform(0.43, 0.55), 2),
        }
        for item in picked
    ]


# ---------------------------------------------------------------- 场景生成

def gen_inherit(rng, pool, count) -> list[dict]:
    """省略继承：第二句只说颜色/数量，类目要沿用。"""
    out = []
    for _ in range(count):
        category = rng.choice([c for c in pool if len(pool[c]) >= 5])
        items = make_items(rng, pool, category)
        first_item = items[0]
        base_query = v4_query(first_item, rng)
        colors = [c for c in first_item["color"].split("、") if c.strip()]
        color = colors[-1] if len(colors) > 1 else (colors[0] if colors else "白色")
        top_k = rng.choice([3, 5, 8])

        turns = [
            user(f"找{base_query}"),
            assistant(tool("text_search", {"query": base_query, "category": category, "top_k": 5}, rng.choice(SAY_POOL))),
            result_message(items),
            assistant(reply(comment_text(items))),
            user(rng.choice([f"要{color}的", f"有{color}的吗", f"换成{color}"])),
            assistant(tool("text_search", {"query": color, "category": category, "top_k": top_k})),
        ]
        out.append(conversation(turns))
    return out


def gen_reference(rng, pool, count) -> list[dict]:
    """指代：第 N 个 -> get_item_detail 用上一轮结果的 item_id。"""
    out = []
    for _ in range(count):
        category = rng.choice([c for c in pool if len(pool[c]) >= 5])
        items = make_items(rng, pool, category)
        index = rng.randint(1, 5)
        target = items[index - 1]
        query = v4_query(items[0], rng)
        turns = [
            user(f"找{query}"),
            assistant(tool("text_search", {"query": query, "category": category, "top_k": 5})),
            result_message(items),
            assistant(reply(comment_text(items))),
            user(rng.choice([f"第{index}个什么材质", f"第{index}个的颜色呢", f"看看第{index}个的详情"])),
            assistant(tool("get_item_detail", {"item_id": target["item_id"]})),
        ]
        out.append(conversation(turns))
    return out


def gen_switch(rng, pool, count) -> list[dict]:
    """话题切换：换类目时旧条件要丢掉。"""
    categories = [c for c in pool if len(pool[c]) >= 5]
    out = []
    for _ in range(count):
        first, second = rng.sample(categories, 2)
        items = make_items(rng, pool, first)
        query = v4_query(items[0], rng)
        turns = [
            user(f"找{query}"),
            assistant(tool("text_search", {"query": query, "category": first, "top_k": 5})),
            result_message(items),
            assistant(reply(comment_text(items))),
            user(rng.choice([f"换一类，看看{second}", f"不要{first}了，看看{second}", f"改成{second}"])),
            assistant(tool("text_search", {"query": second, "category": second, "top_k": 5})),
        ]
        out.append(conversation(turns))
    return out


def gen_correct(rng, pool, count) -> list[dict]:
    """纠错：保留类目，替换描述/款式。"""
    out = []
    for _ in range(count):
        category = rng.choice([c for c in pool if len(pool[c]) >= 5])
        items = make_items(rng, pool, category)
        alt = rng.choice(items[1:])
        alt_type = re.split(r"[、,，/]", alt["type"])[0].strip() or "低帮"
        query = v4_query(items[0], rng)
        turns = [
            user(f"找{query}"),
            assistant(tool("text_search", {"query": query, "category": category, "top_k": 5})),
            result_message(items),
            assistant(reply(comment_text(items))),
            user(rng.choice([f"不要这个，要{alt_type}的", f"换成{alt_type}", f"有没有{alt_type}"])),
            assistant(tool("text_search", {"query": alt_type, "category": category, "top_k": 5})),
        ]
        out.append(conversation(turns))
    return out


def gen_clarify(rng, pool, count) -> list[dict]:
    """澄清追问：先反问，用户补充后再检索。"""
    categories = [c for c in pool if len(pool[c]) >= 5]
    out = []
    for _ in range(count):
        category = rng.choice(categories)
        items = make_items(rng, pool, category)
        turns = [
            user(rng.choice(["随便看看", "都行", "帮我找点东西", "有好东西吗"])),
            assistant(reply(rng.choice([
                "想看哪一类？鞋、包、水杯、衣服，还是家居用品？",
                "可以给我一个关键词吗？比如「白色运动鞋」或「保温杯」。",
            ]))),
            user(rng.choice([f"看{category}", f"就{category}吧", f"{category}"])),
            assistant(tool("text_search", {"query": category, "category": category, "top_k": 5})),
            result_message(items),
            assistant(reply(comment_text(items))),
        ]
        out.append(conversation(turns))
    return out


def gen_single(rng, pool, count) -> list[dict]:
    """单轮工具/对话，保持 v3 的能力不退化。"""
    out = []
    categories = [c for c in pool if len(pool[c]) >= 5]
    for index in range(count):
        if index % 4 == 0:
            turns = [user("你好"), assistant(reply("你好，我是导购助手，可以帮你按描述或图片找商品。"))]
        elif index % 4 == 1:
            turns = [
                user("你们能搜哪些类目"),
                assistant(tool("list_categories", {})),
            ]
        elif index % 4 == 2:
            category = rng.choice(categories)
            items = make_items(rng, pool, category)
            turns = [
                user(f"找{pick_query(items[0], rng)}"),
                assistant(tool("text_search", {"query": pick_query(items[0], rng), "category": category, "top_k": 5}, rng.choice(SAY_POOL))),
                result_message(items),
                assistant(reply(comment_text(items))),
            ]
        else:
            turns = [
                user("按这张图找类似的"),
                assistant(tool("image_search", {"alpha": 0.6})),
            ]
        out.append(conversation(turns))
    return out


# ---------------------------------------------------------------- 校验

def rewrap_single(sample: dict) -> dict:
    """v3 单轮样本只换 system prompt，user/assistant 保持不变。"""
    return {
        "messages": [
            {"role": "system", "content": V4_SYSTEM_PROMPT},
            *sample["messages"][1:],
        ]
    }

def validate(samples: list[dict]) -> Counter:
    stats: Counter = Counter()
    seen: set[str] = set()
    for sample in samples:
        messages = sample["messages"]
        if messages[0]["role"] != "system":
            raise SystemExit("[x] 缺少 system 消息")
        if messages[-1]["role"] != "assistant":
            raise SystemExit("[x] 最后一条不是 assistant")
        for index, message in enumerate(messages[1:], start=1):
            expected = "user" if index % 2 == 1 else "assistant"
            if message["role"] != expected:
                raise SystemExit(f"[x] 角色顺序错误：第 {index} 条应为 {expected}")

        for message in messages[1:]:
            if message["role"] != "assistant":
                continue
            payload = json.loads(message["content"])
            action = payload.get("action")
            stats[action] += 1
            if action == "tool":
                name = payload.get("tool")
                if name not in TOOLS:
                    raise SystemExit(f"[x] 未知工具：{name}")
                stats["tool:" + name] += 1
                say = payload.get("say")
                if say and len(say) > MAX_SAY:
                    raise SystemExit(f"[x] say 超长：{say}")
            elif action == "reply":
                text = str(payload.get("text") or "").strip()
                if not text:
                    raise SystemExit("[x] reply 为空")
                if PRICE_CLAIM.search(text):
                    raise SystemExit(f"[x] reply 含价格/销量断言：{text}")
            else:
                raise SystemExit(f"[x] 未知 action：{action}")

        key = _json({"messages": messages})
        if key in seen:
            raise SystemExit("[x] 出现重复对话")
        seen.add(key)
        stats["conversations"] += 1
        stats["turns"] += (len(messages) - 1) // 2
    return stats


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Agent v4 多轮对话训练集")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写盘")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    items = load_items()
    pool: dict[str, list[dict]] = {}
    for item in items:
        pool.setdefault(item["category"], []).append(item)
    print(f"[1/4] 商品库 {len(items)} 条，{len(pool)} 个类目")

    samples: list[dict] = []

    # ① v3 的全部单轮能力（工具选择 / 对话 / 点评 / 澄清），只换 system prompt
    used: set[str] = set()
    singles: list[dict] = []
    singles += gen_text_search(items, rng, 80, used)
    singles += gen_image_search(rng, 25, used)
    singles += gen_list_categories(rng, 12, used)
    singles += gen_item_detail(items, rng, 12, used)
    singles += gen_comments(items, rng, 60)
    singles += gen_dialogs()
    singles += gen_clarify_single()
    samples += [rewrap_single(sample) for sample in singles]
    print(f"       单轮 {len(samples)} 条（工具/对话/点评/澄清）")

    # ② 多轮场景
    multi: list[dict] = []
    multi += gen_inherit(rng, pool, 70)
    multi += gen_reference(rng, pool, 50)
    multi += gen_switch(rng, pool, 40)
    multi += gen_correct(rng, pool, 40)
    multi += gen_clarify(rng, pool, 40)
    samples += multi
    print(f"       多轮 {len(multi)} 段（继承/指代/切换/纠错/澄清）")
    print(f"[2/4] 合计 {len(samples)} 条样本")

    stats = validate(samples)
    print(f"[3/4] 校验通过：{dict(stats)}")

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
        "version": "v4",
        "seed": args.seed,
        "conversations": len(samples),
        "train": len(train),
        "valid": len(valid),
        "stats": dict(stats),
        "source": "data/index_data_finetuned/*/items.csv",
        "format": "multi-turn; tool result injected as user message with prefix 检索结果：",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[4/4] 已写入 {out_dir}：train={len(train)} valid={len(valid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
