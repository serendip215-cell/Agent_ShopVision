# -*- coding: utf-8 -*-
"""从实验四.typ 生成「语义化」typst 版本，供 pandoc 转 Word。

为什么需要这一步：
    实验四.typ 为符合课程模板做了大量版式定制（#show heading 自定义渲染、
    #show figure.caption 五号居中、#let sxx 表格构造器等）。pandoc 的 typst
    reader 只会解析结构语义，遇到 `#show heading: it => {...}` 这类把标题
    降级成普通段落的规则，就无法识别标题层级，转出的 Word 会丢失大纲。

做法：
    保留正文内容与 #figure/#sxx 结构，只把**版式相关的 #set / #show 规则**
    替换成注释（不影响语义），其余原样保留；输出到 docs/build/_word/ 下，
    由 pandoc 读取。源文件 docs/typ/实验四.typ 不动。

用法：
    python docs/scripts/typ_semantic_export.py            # 生成并打印路径
    python docs/scripts/typ_semantic_export.py --keep-style  # 保留样式（仅调试用）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "typ" / "实验四.typ"
OUT_DIR = ROOT / "docs" / "build" / "_word"

# 需要屏蔽的版式规则：以 "#set " / "#show " 开头，且不属于语义结构
# 但封面区依赖 #set page，若整段去掉会让封面排版散开——封面在 Word 里本来就要重排，
# 因此一并屏蔽，Word 模板另行处理。
STYLE_PREFIXES = ("#set ", "#show ")

# 这些 #set 影响的是骨架（页面/文字基本属性），屏蔽无害且有助于 Word 重新排版
KEEP_PREFIXES = ("#import ", "#let ")


def shield_styles(text: str) -> tuple[str, int]:
    """把顶层的 #set / #show 规则整行注释掉（处理跨行块）。"""
    lines = text.split("\n")
    out: list[str] = []
    n = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith(STYLE_PREFIXES):
            # 该规则可能跨多行：以花括号/方括号/圆括号平衡判断结束。
            # 重要：扫描途中遇到 `#let` 定义必须停下——#let 定义的是内容构造器
            #（如 t5、sxx），属于语义结构，不能连同 #show 一起屏蔽。
            block = [line]
            depth = (
                line.count("{") - line.count("}")
                + line.count("[") - line.count("]")
                + line.count("(") - line.count(")")
            )
            j = i + 1
            while j < len(lines):
                nxt = lines[j].lstrip()
                if nxt.startswith("#let "):
                    break  # 定义体开始，不要吞掉
                block.append(lines[j])
                depth += (
                    lines[j].count("{") - lines[j].count("}")
                    + lines[j].count("[") - lines[j].count("]")
                    + lines[j].count("(") - lines[j].count(")")
                )
                j += 1
                if depth <= 0 and not block[-1].rstrip().endswith(("=>", "(", "[")):
                    break
                if j - i > 40:  # 安全阀
                    break
            for b in block:
                out.append("// WORD-EXPORT-SHIELDED " + b)
            n += 1
            i = j
            continue
        out.append(line)
        i += 1
    return "\n".join(out), n


def extract_lets(text: str) -> str:
    """从源文件中抽出 #let 定义（t5、sxx 这类内容构造器），供正文重新插入。

    #let 定义的是语义结构（表格构造器、五号字块），不是版式规则，
    必须保留，否则正文里的 sxx(...) 无法解析。
    """
    lines = text.split("\n")
    kept: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("#let "):
            depth = (
                lines[i].count("{") - lines[i].count("}")
                + lines[i].count("[") - lines[i].count("]")
                + lines[i].count("(") - lines[i].count(")")
            )
            kept.append(lines[i])
            j = i + 1
            while depth > 0 and j < len(lines):
                kept.append(lines[j])
                depth += (
                    lines[j].count("{") - lines[j].count("}")
                    + lines[j].count("[") - lines[j].count("]")
                    + lines[j].count("(") - lines[j].count(")")
                )
                j += 1
            kept.append("")
            i = j
            continue
        i += 1
    return "\n".join(kept).strip("\n")


def collect_numbering(text: str) -> dict[str, int]:
    """按文档出现顺序，为 fig / tbl / lst 三类标签编号，返回 {label: n}。

    figure 块以 ") <label>" 结尾，代码块以 "] <label>" 结尾，两种都匹配。
    必须在 unwrap_code_figures 之前调用，否则代码块的 label 会随外壳一起消失。
    """
    labels = re.findall(r"[\])]\s*<((?:fig|tbl|lst)-[a-z0-9-]+)>", text)
    numbering: dict[str, int] = {}
    counters: dict[str, int] = {"fig": 0, "tbl": 0, "lst": 0}
    for lb in labels:
        kind = lb.split("-", 1)[0]
        if kind in counters and lb not in numbering:
            counters[kind] += 1
            numbering[lb] = counters[kind]
    return numbering


def flatten_lists(text: str) -> tuple[str, int]:
    """把 Typst 的 `+` 列表转成「1. 内容」这样的普通段落。

    为什么要在源层做：pandoc 会把 `+` 列表解析成 OrderedList，写 docx 时
    变成 Word 自动编号（numPr）。自动编号的数字不在段落文本里，
    后续想统一顶格就会把编号一起弄丢；且编号定义带 left=720/hanging=360
    的缩进，渲染出来"标号左边空得太宽"。

    改成普通段落后，编号成为正文的一部分，既可顶格又不丢编号。
    """
    lines = text.split("\n")
    out: list[str] = []
    n = 0
    counter = 0
    in_list = False
    for line in lines:
        stripped = line.lstrip()
        # 连续 `+ ` 列表项
        if stripped.startswith("+ ") or stripped == "+":
            if not in_list:
                in_list = True
                counter = 0
                if out and out[-1].strip():
                    out.append("")   # 列表前留空行，保证段落独立
            counter += 1
            indent = line[: len(line) - len(stripped)]
            # 用全角句点「．」而非半角「.」：pandoc 会把 `1. ` 识别成有序列表
            # （转 Word 后又变回 numPr 自动编号，编号不进文本）；
            # 「1．」不触发列表解析，编号作为普通文本保留下来。
            out.append(f"{indent}{counter}．{stripped[2:].strip()}")
            # 每条之后留空行，否则相邻两行会被合并成同一段
            out.append("")
            n += 1
            continue
        # 空行不结束列表（Typst 允许列表项间隔空行）
        if stripped == "" and in_list:
            out.append(line)
            continue
        if in_list:
            in_list = False
            counter = 0
        out.append(line)
    return "\n".join(out), n


def resolve_crossrefs(text: str, numbering: dict[str, int]) -> tuple[str, int]:
    """把 @fig-x / @tbl-x / @lst-x 替换成实际编号文字。

    pandoc 的 typst reader 不渲染交叉引用：实测 `如@tbl-env 所示` 被解析成
    `如[tbl-env] 所示`（纯文本），docx 里会原样出现方括号假标签。
    因此在导出阶段就按 numbering 替换为「图 N」「表 N」「代码 N」。
    """
    prefix = {"fig": "图", "tbl": "表", "lst": "代码"}
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        lb = m.group(1)
        num = numbering.get(lb)
        if num is None:
            return m.group(0)
        n += 1
        return f"{prefix[lb.split('-', 1)[0]]} {num}"

    text = re.sub(r"@((?:fig|tbl|lst)-[a-z0-9-]+)", repl, text)
    return text, n


def unwrap_code_figures(text: str) -> tuple[str, int]:
    """把 #figure(kind: raw)[```lang ... ```] 解包成裸 fenced code。

    pandoc 的 typst reader 能解析 figure 里的 CodeBlock（AST 正确），
    但 docx writer 不会输出它——实测代码块全部丢失。解包成顶层
    fenced code 后，docx 会正常生成代码块；题注改写为一行普通段落。
    """
    pattern = re.compile(
        r"#figure\(\s*\n?\s*kind:\s*raw,.*?caption:\s*\[(?P<cap>.*?)\],\s*\n?\)\[\s*\n?"
        r"(?P<code>```[a-z]*\n.*?```)\s*\n?\]",
        re.S,
    )

    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        cap = m.group("cap").strip()
        code = m.group("code").strip()
        return f"{code}\n\n代码：{cap}\n"

    new = pattern.sub(repl, text)
    return new, count


def drop_cover(text: str) -> tuple[str, bool]:
    """去掉封面区（从 #pagebreak 之前整段），Word 里封面另行排版。

    返回 (新文本, 是否处理过)。
    """
    marker = "#pagebreak()"
    if marker not in text:
        return text, False
    idx = text.find(marker)
    # 保留 pagebreak 之后的正文；封面段整体丢弃
    head_end = idx + len(marker)
    # 跳过紧接着的 #set page(...) 与 counter 更新块
    tail = text[head_end:]
    tail = re.sub(r"\A\s*#set page\([^)]*\)\s*", "", tail, flags=re.S)
    tail = re.sub(r"\A\s*#counter\(page\)\.update\(1\)\s*", "", tail, flags=re.S)
    return tail.lstrip("\n"), True


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="生成语义化 typst 版本供 pandoc 转 Word")
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--keep-style", action="store_true", help="保留版式规则（仅调试）")
    ap.add_argument("--keep-cover", action="store_true", help="保留封面区")
    args = ap.parse_args(argv)

    src = args.src if args.src.is_absolute() else ROOT / args.src
    text = src.read_text(encoding="utf-8")

    # 顺序很重要：先从**原始文本**抽出 #let 定义（此时它们还在），
    # 再屏蔽版式规则、去掉封面，最后把定义插回正文前。
    lets = extract_lets(text) if not args.keep_cover else ""

    # 列表先展开成带编号的普通段落：pandoc 会把 `+` 列表做成 Word 自动编号，
    # 编号数字不在文本里，后续按"顶格"处理时编号会丢失。
    text, nlist = flatten_lists(text)
    print(f"列表展开: {nlist} 项（转为「N. 内容」普通段落）")

    if not args.keep_style:
        text, n = shield_styles(text)
        print(f"已屏蔽版式规则: {n} 条")

    if not args.keep_cover:
        text, done = drop_cover(text)
        if lets:
            text = lets + "\n\n" + text
            print(f"#let 定义: 保留 {lets.count('#let ')} 个（t5 / sxx 等）")
        print(f"封面处理: {'已移除（Word 另排）' if done else '未找到 #pagebreak，跳过'}")

    # 交叉引用编号必须在**解包前**收集：unwrap_code_figures 会去掉
    # #figure 外壳连同 `] <lst-xxx>` 标记，之后再收集就漏掉代码块编号。
    numbering = collect_numbering(text)

    # 解包 figure 包裹的代码块：pandoc docx writer 不输出 figure 内的 CodeBlock
    text, ncode = unwrap_code_figures(text)
    print(f"代码块解包: {ncode} 处（否则 docx 会丢失）")

    # 交叉引用换成实际编号：pandoc 不渲染 @fig-/@tbl-，会留下 [tbl-env] 假标签
    text, nref = resolve_crossrefs(text, numbering)
    print(f"交叉引用: 替换 {nref} 处为「图 N/表 N/代码 N」（编号表 {len(numbering)} 条）")

    out = args.out or (OUT_DIR / (src.stem + "_semantic.typ"))
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"输出: {out}  ({len(text)} 字符)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))