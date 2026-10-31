# -*- coding: utf-8 -*-
"""把 docs/typ/实验三.typ 转成 cli-anything-word 的项目 JSON（再交给该 CLI 渲染成 .docx）。

只处理实验三.typ 实际用到的语法：一/二/三级标题、正文段落、`+` 编号列表、
`#figure(image/table/raw)`、`#pagebreak`、`#set`/#bibliography，以及行内的
`*粗体*`、`` `代码` ``、`@fig-`/`@tbl-`/`@lst-` 交叉引用、`@bibkey` 文献引用。

CLI 的块模型表达不了的行内格式，用哨兵标记带进 .docx，由
docs/scripts/refine_word_report.py 用 Word COM 补上（<b></b> 粗体、<s></s> 上标、
<c></c> 行内代码、<k:label></k:label> 交叉引用超链接、<a:label> 题注/文献条目的书签锚点）。

用法:
  python docs/scripts/typ_to_word.py -o docs/build/_word/exp3_project.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TYP = ROOT / "docs" / "typ" / "实验三.typ"
DEFAULT_PDF = max((ROOT / "docs" / "build").glob("实验三-*.pdf"), key=lambda p: p.stat().st_mtime)
IMAGE_DIR = ROOT / "docs" / "typ" / "figs_exp3"
PIPELINE_PNG = ROOT / "docs" / "交付材料" / "实验三_第23组" / "推理加速流水线图.png"

BOLD_OPEN, BOLD_CLOSE = "<b>", "</b>"
SUP_OPEN, SUP_CLOSE = "<s>", "</s>"
CODE_OPEN, CODE_CLOSE = "<c>", "</c>"
REF_OPEN, REF_CLOSE = "<k:", "</k:"      # <k:fig-accel>图 1</k:fig-accel>
ANCHOR_OPEN, ANCHOR_CLOSE = "<a:", ">"   # <a:fig-accel> 建书签用（无闭合，题注段首）
CJK = re.compile(r"[　-鿿＀-￯]")

MEMBERS = [
    ("2610321101", "何朝杨", "实验三报告整合、排版与图表引用"),
    ("2610321103", "杜军博", "推理加速评测复算与交付（速度精度验收、132 查询复算）"),
    ("2610321135", "王陆洲", "模型导出与推理测量（ONNX、ORT/TRT 测速、FLOPs）"),
    ("2610320046", "张梓萱", "训练数据与划分核验、成果核验与交付"),
    ("2610320033", "刘凡思雨", "结果数据核对与模型/索引版本记录"),
    ("2610321168", "秦鑫洋", "交付材料整理与报告校对"),
]


# ------------------------------- 小工具 -------------------------------
def scan_balanced(text: str, start: int) -> int:
    """返回 text[start] 处配对的 () 或 [] 闭合后的下标。

    起点是 `(` 时忽略 `[]` 里的括号（Typst 的表格单元格里常带括号文字）；
    起点是 `[` 时只按中括号配对。
    """
    open_ch, close_ch = text[start], {"(": ")", "[": "]"}[text[start]]
    depth, in_str = 0, False
    for i in range(start, len(text)):
        ch = text[i]
        if ch == '"' and text[i - 1] != "\\":
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f"括号不配对：{text[start:start+60]!r}")


def split_top(text: str, sep: str = ",") -> list[str]:
    """按顶层分隔符切分（忽略括号/中括号里的分隔符）。"""
    out, buf, depth, br, in_str = [], [], 0, 0, False
    for i, ch in enumerate(text):
        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            in_str = not in_str
        if not in_str:
            depth += ch in "("
            depth -= ch in ")"
            br += ch in "["
            br -= ch in "]"
            if ch == sep and depth == 0 and br == 0:
                out.append("".join(buf))
                buf = []
                continue
        buf.append(ch)
    out.append("".join(buf))
    return [x.strip() for x in out if x.strip()]


def extract_cells(text: str) -> list[str]:
    """收集顶层的 `[..]` 单元格内容。

    圆括号整组跳过（`table.header([..],[..])` 里的表头单元格因此不会混进数据序列，
    表头由 parse_figure 单独取）。
    """
    out, pos = [], 0
    while pos < len(text):
        ch = text[pos]
        if ch == "(":
            pos = scan_balanced(text, pos) + 1
            continue
        if ch == "[" and (pos == 0 or text[pos - 1] != "\\"):
            en = scan_balanced(text, pos)
            out.append(strip_markup(text[pos + 1:en]).replace("\n", " "))
            pos = en + 1
            continue
        pos += 1
    return out


def minus_signs(text: str) -> str:
    """ASCII `-` 换成 U+2212（Typst 在「前一字符非字母数字时紧接数字」这一条件下会换）。

    实测 PDF：`-0.86%`→`−0.86%`，而 `4e-6`/`ViT-B-16`/`2026-10-24`/`2704-2713` 保持 ASCII，
    即前一字符是字母数字时一律不换。
    """
    return re.sub(r"(?<![0-9A-Za-z])-(?=\d)", "−", text)


def strip_markup(text: str) -> str:
    """去掉 Typst 行内标记，保留哨兵标记给 refine 阶段用。"""
    t = text
    t = re.sub(r"#h\([^)]*\)", " ", t)
    t = re.sub(r"#text\([^)]*\)\[([^\[\]]*)\]", r"\1", t)
    # 行内代码：Typst 的 `#show raw` 让行内 raw 也是 Consolas 9pt，而 CLI 的块模型没有
    # run 级字体，只能用哨兵标记带到 refine 阶段再改（不这么做，路径/文件名会排成正文字体）
    t = re.sub(r"`([^`]*)`", CODE_OPEN + r"\1" + CODE_CLOSE, t)
    t = re.sub(r"\\([@\\])", r"\1", t)                 # \@ -> @
    t = re.sub(r"\*([^*]+)\*", BOLD_OPEN + r"\1" + BOLD_CLOSE, t)
    t = t.replace("\\", "")
    return minus_signs(smart_quotes(re.sub(r"[ \t]+", " ", t).strip()))


def smart_quotes(text: str) -> str:
    """Typst 会把直引号排成弯引号，Word 不会——这里补上，保证两边逐字一致。"""
    out: list[str] = []
    expect_open = True
    for ch in text:
        if ch != '"':
            out.append(ch)
            continue
        out.append("“" if expect_open else "”")
        expect_open = not expect_open
    return "".join(out)


def join_lines(lines: list[str]) -> str:
    """把续行拼成一段：中文之间不加空格，拉丁词之间补一个空格。"""
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out and not CJK.search(out[-1]) and not CJK.search(ln[0]):
            # 拉丁词之间补空格，但行正好断在网址中间时不补（Typst 只是换行，没有空格）
            tail = out.rsplit(" ", 1)[-1]
            url_tail = tail.endswith("/") or (tail.endswith(".") and re.search(r"[/:]", tail))
            if not url_tail:
                out += " "
        out += ln
    return out


def cjk_join(lines: list[str]) -> str:
    return join_lines(lines)


# ------------------------------- 解析 -------------------------------
def read_references(pdf: Path) -> list[str]:
    """从 Typst 编译出的 PDF 里取参考文献原文，保证 Word 版逐字一致。"""
    import fitz

    # 按行取，并剔掉下边距里的页脚页码——否则参考文献末条会粘上「16」这种页码（已踩过）
    text = "\n".join(
        "\n".join("".join(s["text"] for s in ln["spans"])
                  for blk in pg.get_text("dict")["blocks"]
                  for ln in blk.get("lines", [])
                  if ln["bbox"][3] <= pg.rect.height - 2.5 / 2.54 * 72)
        for pg in fitz.open(pdf))
    sec = text[text.index("七、参考文献") + len("七、参考文献"):text.index("附录 A")]
    parts = re.split(r"\[(\d+)\]", sec)
    refs: dict[int, list[str]] = {}
    cur = None
    for chunk in parts[1:]:
        if chunk.strip().isdigit():
            cur = int(chunk.strip())
            refs[cur] = []
        elif cur is not None:
            refs[cur].append(chunk)
    return [f"[{n}] {cjk_join(''.join(refs[n]).splitlines())}" for n in sorted(refs)]


def parse_body(lines: list[str]) -> tuple[list[dict], int]:
    """返回 (块列表, 已解析到第几行)；块的 cross-ref 在第二遍填。"""
    blocks: list[dict] = []
    i = 0
    text_buf: list[str] = []
    merged = "\n".join(lines)
    offsets, off = [], 0                      # 每行在 merged 里的字符偏移
    for ln in lines:
        offsets.append(off)
        off += len(ln) + 1

    def flush():
        nonlocal text_buf
        if text_buf:
            blocks.append({"type": "paragraph", "text": join_lines(text_buf)})
            text_buf = []

    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if not s or s.startswith("//"):
            flush()
            i += 1
            continue
        m = re.match(r"^(={1,3})\s+(.*)$", s)
        if m:
            flush()
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue
        if s.startswith("#set ") or s.startswith("#show ") or s.startswith("#import"):
            i += 1
            continue
        if s.startswith("#bibliography("):
            flush()
            blocks.append({"type": "_refs"})
            i += 1
            continue
        if s.startswith("#pagebreak("):
            # Typst 的弱分页（weak: true）只是「正好落在页末才换页」，Word 侧由标题样式的
            # 「与下段同页」天然保证，照搬成硬分页反而会把上一节残留的两行单独顶成一页
            flush()
            if "weak" not in s:
                blocks.append({"type": "page_break"})
            i += 1
            continue
        if s.startswith("#figure("):
            flush()
            start = offsets[i]
            close = scan_balanced(merged, merged.index("(", start))
            # 代码图写作 `#figure(...)[```...```] <label>`，正文内容在圆括号之后的中括号里
            tail = merged.find("[", close)
            if tail != -1 and not merged[close + 1:tail].strip():
                close = scan_balanced(merged, tail)
            end = merged.find("\n", close)
            chunk = merged[start:end]
            blocks.append(parse_figure(chunk))
            i += chunk.count("\n") + 1
            continue
        if s.startswith("+ ") or (s.startswith("+") and len(s) > 1 and s[1] != "+"):
            flush()
            items = []
            while i < len(lines):
                cur = lines[i].strip()
                if cur.startswith("+ "):
                    items.append(cur[2:].strip())
                    i += 1
                elif not cur:
                    break
                else:
                    break
            blocks.append({"type": "list", "list_style": "number", "items": items})
            continue
        if s.startswith("#"):
            raise ValueError(f"未识别的块级命令（第 {i+1} 行）：{s[:60]}")
        text_buf.append(s)
        i += 1
    flush()
    return blocks, i


def parse_figure(chunk: str) -> dict:
    cap = re.search(r"caption:\s*\[", chunk)
    caption = ""
    if cap:
        st = chunk.index("[", cap.start())
        en = scan_balanced(chunk, st)
        caption = chunk[st + 1:en]
    label = re.search(r"<([a-z]+-[a-z0-9-]+)>", chunk)
    img = re.search(r'image\("([^"]+)"\)', chunk)
    if img:
        path = img.group(1)
        return {"type": "_image", "path": path, "caption": caption,
                "label": label.group(1) if label else ""}
    if "kind: raw" in chunk:
        body = chunk[chunk.index(")[") + 2:] if ")[:" in chunk.replace(" ", "") else chunk
        fences = re.findall(r"```[a-z]*\n(.*?)```", chunk, re.S)
        code = fences[0].rstrip("\n") if fences else body
        return {"type": "_code", "code": code, "caption": caption,
                "label": label.group(1) if label else ""}
    # 表格
    tst = chunk.index("table(") + len("table")
    ten = scan_balanced(chunk, tst)
    tb = chunk[tst + len("table("):ten]
    ncols = 3
    cm = re.search(r"columns:\s*\(([^)]*)\)", tb)
    if cm:
        ncols = len(split_top(cm.group(1)))
    cells = extract_cells(tb)                       # 已整组跳过 table.header(...)，只剩数据格
    header = []
    if "table.header(" in tb:
        hi = tb.index("table.header(") + len("table.header")     # 指向 '('
        header = extract_cells(tb[hi + 1:scan_balanced(tb, hi)])
    data = [header] if header else []
    for k in range(0, len(cells), ncols):
        row = cells[k:k + ncols]
        if len(row) == ncols:
            data.append(row)
    return {"type": "table", "rows": len(data), "cols": ncols, "header": True, "data": data,
            "caption": caption, "label": label.group(1) if label else ""}


# ------------------------------- 组装 -------------------------------
def resolve_inline(text: str, nums: dict[str, int], cites: dict[str, int]) -> str:
    """`*粗*` 已在 strip_markup 里变成哨兵；这里把 @ref / @cite 换成印刷出来的编号。"""
    kind_of = {"fig": "图", "tbl": "表", "lst": "代码"}
    out: list[str] = []
    pending: list[str] = []          # 连续的文献引用，合并成一组 [1,2]

    def flush_pending():
        if pending:
            # 每个文献号单独包一层 <k:bib-N>，refine 里逐个做成指向文献条目的超链接
            parts = []
            for k in pending:
                n = cites.get(k)
                parts.append("?" if n is None
                             else f"{REF_OPEN}bib-{n}>{n}{REF_CLOSE}bib-{n}>")
            out.append(SUP_OPEN + "[" + ",".join(parts) + "]" + SUP_CLOSE)
            pending.clear()

    for piece in re.split(r"((?<!\\)@[A-Za-z][\w-]*)", text):
        if not piece:
            continue                      # 相邻引用的分隔空串不能打断合并
        if piece.startswith("@"):
            key = piece[1:]
            if "-" in key and key.split("-")[0] in kind_of:
                flush_pending()
                shown = f"{kind_of[key.split('-')[0]]} {nums.get(key, '?')}"
                out.append(f"{REF_OPEN}{key}>{shown}{REF_CLOSE}{key}>")
            else:
                pending.append(key)
        else:
            flush_pending()
            out.append(piece)
    flush_pending()
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--typ", default=str(DEFAULT_TYP))
    ap.add_argument("--pdf", default=str(DEFAULT_PDF))
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    lines = Path(args.typ).read_text(encoding="utf-8").splitlines()
    body_start = next(i for i, l in enumerate(lines) if l.strip().startswith("= 一、实验目的"))
    blocks, _ = parse_body(lines[body_start:])

    # 编号：图片类图 / 表 / 代码，按出现顺序
    nums, counters = {}, {"_image": 0, "table": 0, "_code": 0}
    for b in blocks:
        if b["type"] in counters and b.get("label"):
            counters[b["type"]] += 1
            nums[b["label"]] = counters[b["type"]]
    print(f"编号：图 {counters['_image']} / 表 {counters['table']} / 代码 {counters['_code']}")

    # 文献编号：正文首次引用顺序
    # 在原始 typ 文本上扫（此时 R\@K 还带反斜杠，能与真正的 @引用 区分开）
    cites: dict[str, int] = {}
    raw_body = "\n".join(lines[body_start:])
    for key in re.findall(r"(?<!\\)@([A-Za-z][\w-]*)", raw_body):
        if not key.startswith(("fig-", "tbl-", "lst-")) and key not in cites:
            cites[key] = len(cites) + 1
    refs = read_references(Path(args.pdf))
    print(f"引用 {len(cites)} 条，参考文献 {len(refs)} 条")
    if len(refs) != len(cites):
        print("!! 引用数与参考文献条数不一致，需要核对", file=sys.stderr)

    # 图片宽度：按文档顺序取 Typst PDF 里实际渲染的宽度
    try:
        import fitz

        widths = []
        for pg in fitz.open(args.pdf):
            for blk in pg.get_text("dict")["blocks"]:
                if blk["type"] == 1 and blk["bbox"][1] < 690:
                    widths.append(round((blk["bbox"][2] - blk["bbox"][0]) / 28.3465, 2))
        print("PDF 里图片宽度(cm):", widths)
    except Exception as exc:  # pragma: no cover - 仅诊断用
        widths = []
        print("（宽度探测失败）", exc)

    # 流水线图是矢量 SVG，PDF 里不落成图片对象，宽度取 SVG 自身尺寸
    svg = ROOT / "docs" / "typ" / "figures" / "acceleration_pipeline.svg"
    m = re.search(r'width="([\d.]+)pt"', svg.read_text(encoding="utf-8"))
    svg_width_cm = round(float(m.group(1)) / 28.3465, 2) if m else None
    widths = ([svg_width_cm] if svg_width_cm else []) + widths

    content = [
        {"type": "paragraph", "text": "西 安 邮 电 大 学",
         "style": {"align": "center", "size_pt": 26, "bold": True}},
        {"type": "paragraph", "text": "AI 全栈开发实验",
         "style": {"align": "center", "size_pt": 26, "bold": True}},
        {"type": "paragraph", "text": "题目：算法优化实验",   # Typst 封面是「题目：」紧排，不要加空
         "style": {"align": "center", "size_pt": 22, "bold": True}},
        {"type": "paragraph", "text": "组    号：23",
         "style": {"align": "center", "size_pt": 14, "bold": True}},
        {"type": "paragraph", "text": "组员信息：",
         "style": {"align": "center", "size_pt": 14, "bold": True}},
        {"type": "table", "rows": 7, "cols": 3, "header": True,
         "data": [["学号", "姓名", "分工"]] + [list(m) for m in MEMBERS], "table_style": "成员表"},
        {"type": "paragraph", "text": "时    间：2026.10.25",
         "style": {"align": "center", "size_pt": 14, "bold": True}},
        {"type": "page_break"},
    ]

    img_i = 0
    for b in blocks:
        kind = b["type"]
        # 顺序很关键：先在带 `\@` 的原文上解析交叉引用（否则 R\@K 会被当成文献引用），
        # 再 strip_markup 去掉 Typst 行内标记并把 \@ 还原成 @
        if kind == "paragraph":
            content.append({"type": "paragraph",
                            "text": strip_markup(resolve_inline(b["text"], nums, cites))})
        elif kind == "heading":
            content.append({"type": "heading", "level": b["level"],
                            "text": strip_markup(resolve_inline(b["text"], nums, cites))})
        elif kind == "list":
            content.append({"type": "list", "list_style": "number",
                            "items": [strip_markup(resolve_inline(i, nums, cites)) for i in b["items"]]})
        elif kind == "page_break":
            content.append({"type": "page_break"})
        elif kind == "table":
            content.append({"type": "table", "rows": b["rows"], "cols": b["cols"],
                            "header": True, "data": b["data"], "table_style": "三线表"})
            content.append({"type": "paragraph",
                            "text": f"{ANCHOR_OPEN}{b['label']}{ANCHOR_CLOSE}表 {nums.get(b['label'], '?')} "
                                    + strip_markup(b["caption"]),
                            "style": {"name": "caption"}})
        elif kind == "_code":
            content.append({"type": "paragraph", "text": b["code"].replace("\n", "\v"),
                            "style": {"name": "quote"}})
            content.append({"type": "paragraph",
                            "text": f"{ANCHOR_OPEN}{b['label']}{ANCHOR_CLOSE}代码 {nums.get(b['label'], '?')} "
                                    + strip_markup(b["caption"]),
                            "style": {"name": "caption"}})
        elif kind == "_image":
            path = b["path"]
            if path.endswith(".svg"):
                path = str(PIPELINE_PNG)
            else:
                path = str(IMAGE_DIR / Path(path).name)
            item = {"type": "image", "path": path}
            if img_i < len(widths):
                item["width_cm"] = widths[img_i]
            img_i += 1
            content.append(item)
            content.append({"type": "paragraph",
                            "text": f"{ANCHOR_OPEN}{b['label']}{ANCHOR_CLOSE}图 {nums.get(b['label'], '?')} "
                                    + strip_markup(b["caption"]),
                            "style": {"name": "caption"}})
        elif kind == "_refs":
            for r in refs:
                # 不给文献条目埋 <a:…> 锚点：CLI 渲染时会把标记在第一字符 '<' 处拆成两个 run，
                # 跨 run 删掉标记后 Word 会在空 run 里留一个空格（实测删不掉），干脆靠 [n] 前缀认人
                content.append({"type": "paragraph", "text": r,
                                "style": {"size_pt": 10.5, "align": "left"}})
        else:  # pragma: no cover
            raise ValueError(f"未知块：{kind}")

    project = {
        "version": "1.0",
        "name": "实验三实验报告 第23组",
        "type": "word",
        "settings": {
            "page_width_cm": 21.0, "page_height_cm": 29.7, "orientation": "portrait",
            "margin_top_cm": 2.5, "margin_bottom_cm": 2.5,
            "margin_left_cm": 2.5, "margin_right_cm": 2.5,
        },
        "styles": {},
        "header": {"primary": "", "first_page": ""},
        "footer": {"primary": "", "first_page": ""},
        "page_numbers": True,
        "metadata": {"title": "AI全栈开发实验三：算法优化实验", "author": "第23组"},
        "content": content,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(project, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写出 {out}：{len(content)} 个块（标题 "
          f"{sum(1 for c in content if c['type'] == 'heading')}，"
          f"表 {sum(1 for c in content if c['type'] == 'table')}，"
          f"图 {sum(1 for c in content if c['type'] == 'image')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())