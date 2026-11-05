# -*- coding: utf-8 -*-
"""实验四报告转 Word（.docx）：从 Typst 源语义化导出，经 pandoc 生成。

为什么不用 PDF→Word：
    pdf2docx 按视觉位置切块，实测会把段落切碎（半句话成一段）、
    把题注与正文粘在一起、把封面表单算成表格，格式混乱。

为什么不能直接 pandoc 转原 typ：
    docs/typ/实验四.typ 为课程模板做了大量版式定制（#show heading 自定义渲染），
    pandoc 会因此丢失全部标题层级；代码块包在 #figure(kind: raw) 里，
    docx writer 也不输出。

因此分三步：
    1. docs/scripts/typ_semantic_export.py 生成语义化 typ（屏蔽版式规则、
       保留 #let 构造器、解包代码块、去掉封面）；
    2. pandoc --from typst --to docx，带 citeproc 与 GB/T 7714 数字制 CSL，
       使引用渲染为 [1][2]…与原报告一致；
    3. 用 python-docx 补版式：正文两端对齐、题注居中、表格三线表化。

用法：
    python docs/scripts/typ_to_docx.py                # 全流程，输出到交付目录
    python docs/scripts/typ_to_docx.py --no-copy      # 只生成到 docs/build/_word/
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[2]
TYP = ROOT / "docs" / "typ" / "实验四.typ"
SEMANTIC = ROOT / "docs" / "typ" / "_实验四_semantic.typ"
BIB = ROOT / "docs" / "typ" / "refs.bib"
WORD_DIR = ROOT / "docs" / "build" / "_word"
CSL_DIR = WORD_DIR / "csl"
CSL_NAME = "gb-t-7714-2015-numeric.csl"
CSL_URL = (
    "https://raw.githubusercontent.com/citation-style-language/styles/master/"
    "china-national-standard-gb-t-7714-2015-numeric.csl"
)
DELIVER = ROOT / "docs" / "交付材料" / "实验四_第23组" / "实验四实验报告 第23组.docx"

PANDOC_CANDIDATES = [
    Path.home() / "AppData" / "Local" / "Pandoc" / "pandoc.exe",
    Path("C:/Program Files/Pandoc/pandoc.exe"),
]


def find_pandoc() -> Path:
    for p in PANDOC_CANDIDATES:
        if p.is_file():
            return p
    which = shutil.which("pandoc")
    if which:
        return Path(which)
    raise SystemExit("未找到 pandoc，请先安装：winget install JohnMacFarlane.Pandoc")


def ensure_csl() -> Path:
    CSL_DIR.mkdir(parents=True, exist_ok=True)
    csl = CSL_DIR / CSL_NAME
    if not csl.is_file():
        print(f"下载 CSL 样式: {CSL_URL}")
        urllib.request.urlretrieve(CSL_URL, csl)
    return csl


def run(cmd: list[str]) -> None:
    print(">> " + " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.stdout.strip():
        print(proc.stdout.strip()[:2000])
    if proc.returncode != 0:
        print(proc.stderr.strip()[:3000], file=sys.stderr)
        raise SystemExit(f"命令失败: {cmd[0]}")


# --------------------------- 后处理 ---------------------------
def set_three_line(table) -> None:
    """三线表：去掉全部框线，仅保留顶线、栏目线、底线。"""
    tbl = table._tbl
    # 先清空原有边框
    tblPr = tbl.tblPr
    for el in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(el)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none" if edge not in ("top", "bottom") else "single")
        el.set(qn("w:sz"), "8" if edge in ("top", "bottom") else "0")
        borders.append(el)
    tblPr.append(borders)
    # 表头下加一条 0.5pt 线
    if table.rows:
        for cell in table.rows[0].cells:
            tcPr = cell._tc.get_or_add_tcPr()
            for e in tcPr.findall(qn("w:tcBorders")):
                tcPr.remove(e)
            tcb = OxmlElement("w:tcBorders")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "4")
            tcb.append(bottom)
            tcPr.append(tcb)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER


def polish(doc) -> None:
    """正文两端对齐、题注居中、表格三线表化、字号五号。"""
    for para in doc.paragraphs:
        name = para.style.name
        if name.startswith("Heading"):
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            continue
        if name in ("Image Caption", "Table Caption", "Caption"):
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in para.runs:
                r.font.size = Pt(10.5)
            continue
        if name == "Source Code":
            for r in para.runs:
                r.font.size = Pt(9)
            continue
        t = para.text.strip()
        if len(t) > 24 and not t.startswith(("表 ", "图 ", "代码 ")):
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for table in doc.tables:
        set_three_line(table)
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(10.5)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Typst 报告转 Word（语义化方案）")
    ap.add_argument("--src", type=Path, default=TYP)
    ap.add_argument("--out", type=Path, default=WORD_DIR / "实验四.docx")
    ap.add_argument("--no-copy", action="store_true", help="不复制到交付目录")
    args = ap.parse_args(argv)

    py = sys.executable

    # 1) 语义化导出（输出放在 docs/typ/ 以让图片相对路径可解析）
    run([py, str(ROOT / "docs" / "scripts" / "typ_semantic_export.py"),
         "--src", str(args.src), "--out", str(SEMANTIC)])

    # 2) pandoc: typst -> docx（含引用解析）
    pandoc = find_pandoc()
    csl = ensure_csl()
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    run([str(pandoc), "-f", "typst", "-t", "docx",
         "--citeproc", f"--csl={csl}", f"--bibliography={BIB}",
         "--resource-path", str(ROOT / "docs" / "typ"),
         "-o", str(out), str(SEMANTIC)])

    # 3) 版式后处理
    from docx import Document

    doc = Document(str(out))
    polish(doc)
    doc.save(str(out))

    heads = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
    codes = [p for p in doc.paragraphs if p.style.name == "Source Code"]
    print("\n=== 转换结果 ===")
    print(f"  输出      : {out}")
    print(f"  大小      : {out.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"  标题      : {len(heads)}")
    print(f"  表格      : {len(doc.tables)}")
    print(f"  图片      : {len(doc.inline_shapes)}")
    print(f"  代码块    : {len(codes)}")

    if not args.no_copy:
        DELIVER.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, DELIVER)
        print(f"  已复制到  : {DELIVER}")

    # 语义化中间文件不留在版本库里
    if SEMANTIC.is_file():
        SEMANTIC.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))