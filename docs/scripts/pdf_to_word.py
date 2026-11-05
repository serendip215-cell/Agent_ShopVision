# -*- coding: utf-8 -*-
"""把实验四 PDF 转成 Word（.docx），并做必要的样式后处理。

方案说明（本机实测对比后的选择）：
  * typ → docx（pandoc）：格式能解析，但本份 typst 用 #show heading 自定义了标题渲染，
    pandoc 因此丢失标题结构（实测 0 个标题），且交叉引用渲染成 [chinese-clip] 未解析，
    表格被拆成 27 个（含封面表单），正文 14,362 字。不采用。
  * pdf → docx（pdf2docx）：按版面还原，标题字号/粗体保留，交叉引用渲染为 [1] 已解析，
    正文 17,752 字更完整。采用此方案。

pdf2docx 只按版面切块，段落样式统一为 Normal。本脚本在此基础上补两件事：
  1. 按字号/粗体把「一、」与「X.Y / X.Y.Z」识别成 Word 标题样式，便于生成目录与导航；
  2. 报告转换统计，便于核对有没有丢内容。

用法：
  python docs/scripts/pdf_to_word.py                 # 默认转 docs/build 下最新的实验四 PDF
  python docs/scripts/pdf_to_word.py --pdf <路径> --out <输出.docx>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "docs" / "build"
WORD_DIR = BUILD / "_word"

# 一级标题：一、二、…；二级/三级：1.2 / 1.2.3
RE_H1 = re.compile(r"^[一二三四五六七]、\S")
RE_H2 = re.compile(r"^\d+\.\d+ \S")
RE_H3 = re.compile(r"^\d+\.\d+\.\d+ \S")


def _first_run(para):
    return para.runs[0] if para.runs else None


def classify(para) -> str | None:
    """按文本形态与字号判断段落应属于哪级标题。"""
    t = para.text.strip()
    if not t or len(t) > 60:
        return None
    run = _first_run(para)
    size = run.font.size.pt if (run and run.font.size) else None
    bold = bool(run.font.bold) if run else False

    if RE_H1.match(t) and (size is None or size >= 13):
        return "Heading 1"
    if RE_H3.match(t):
        return "Heading 3"
    if RE_H2.match(t):
        return "Heading 2"
    # 兜底：14pt 且像章标题
    if RE_H1.match(t):
        return "Heading 1"
    if size and size >= 13 and bold:
        return "Heading 1"
    return None


def promote_headings(doc: Document) -> int:
    """把符合标题形态的 Normal 段落改挂到 Heading 样式（保留原有字体与字号）。"""
    changed = 0
    for para in doc.paragraphs:
        target = classify(para)
        if target and para.style.name != target:
            para.style = doc.styles[target]
            changed += 1
    return changed


def fix_paragraph_format(doc: Document) -> None:
    """正文段落统一两端对齐、首行缩进 2 字符；题注居中。"""
    for para in doc.paragraphs:
        style = para.style.name
        if style.startswith("Heading"):
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            continue
        t = para.text.strip()
        if re.match(r"^[图表]\s*\d+", t):
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif len(t) > 30:
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def convert(pdf: Path, out: Path) -> None:
    from pdf2docx import Converter

    out.parent.mkdir(parents=True, exist_ok=True)
    cv = Converter(str(pdf))
    try:
        cv.convert(str(out))
    finally:
        cv.close()

    doc = Document(str(out))
    n_heads = promote_headings(doc)
    fix_paragraph_format(doc)
    doc.save(str(out))

    heads = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
    text = "\n".join(p.text for p in doc.paragraphs)
    print(f"输出: {out}")
    print(f"  大小      : {out.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  段落数    : {len(doc.paragraphs)}")
    print(f"  表格数    : {len(doc.tables)}")
    print(f"  内嵌图片  : {len(doc.inline_shapes)}")
    print(f"  识别标题  : {len(heads)}（其中新挂样式 {n_heads} 个）")
    print(f"  正文字符  : {len(text)}")
    print(f"  含“如表”  : {'如表' in text}")
    print(f"  含引用[n] : {bool(re.search(r'\[\d+\]', text))}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="实验四 PDF → Word 转换")
    ap.add_argument("--pdf", type=Path, help="输入 PDF（默认取 docs/build 下最新的实验四 PDF）")
    ap.add_argument("--out", type=Path, help="输出 docx（默认 docs/build/_word/<同名>.docx）")
    args = ap.parse_args(argv)

    if args.pdf:
        pdf = args.pdf if args.pdf.is_absolute() else ROOT / args.pdf
    else:
        cands = sorted(BUILD.glob("实验四*.pdf"), key=lambda p: p.stat().st_mtime)
        if not cands:
            print("未找到 docs/build/实验四*.pdf，请先编译报告或指定 --pdf", file=sys.stderr)
            return 1
        pdf = cands[-1]

    if not pdf.is_file():
        print(f"PDF 不存在: {pdf}", file=sys.stderr)
        return 1

    out = args.out or (WORD_DIR / (pdf.stem + ".docx"))
    if not out.is_absolute():
        out = ROOT / out

    print(f"输入: {pdf}")
    convert(pdf, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))