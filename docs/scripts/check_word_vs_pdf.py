# -*- coding: utf-8 -*-
"""逐字比对 Typst 版 PDF 与 Word 版 PDF，确认「内容一模一样」。

两端都去掉空白与页脚页码后再比；输出相似度与差异片段，相似度低于阈值即非零退出。
用法: python docs/scripts/check_word_vs_pdf.py [typst.pdf] [word.pdf]
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TYPST = max((ROOT / "docs" / "build").glob("实验三-*.pdf"), key=lambda p: p.stat().st_mtime)
DEFAULT_WORD = ROOT / "docs" / "build" / "_word" / "exp3_word.pdf"
THRESHOLD = 0.995


def text_without_footer(pdf: Path) -> str:
    """取正文文字（页脚在下边距里，按 y 位置排除）。"""
    out = []
    for page in fitz.open(pdf):
        bottom = page.rect.height - 2.5 / 2.54 * 72 + 4
        for blk in page.get_text("dict")["blocks"]:
            for line in blk.get("lines", []):
                text = "".join(s["text"] for s in line["spans"]).strip()
                if text and line["bbox"][3] <= bottom:
                    out.append(text)
    return re.sub(r"[\s　]+", "", "".join(out))


def main() -> int:
    typst = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TYPST
    word = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_WORD
    a, b = text_without_footer(typst), text_without_footer(word)
    ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    print(f"Typst {len(a)} 字 / Word {len(b)} 字，相似度 {ratio:.4f}")
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
           if o[0] != "equal"]
    if ratio >= THRESHOLD:
        print(f"内容一致（差异 {len(ops)} 段，均在 {THRESHOLD:.3f} 阈值内）")
        return 0
    print(f"差异 {len(ops)} 段，前 12 段：")
    for tag, i1, i2, j1, j2 in ops[:12]:
        print(f"  [{tag}] Typst: {a[max(0,i1-20):i2+20]!r}")
        print(f"          Word : {b[max(0,j1-20):j2+20]!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())