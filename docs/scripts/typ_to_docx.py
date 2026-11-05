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
from docx.shared import Cm, Pt, RGBColor

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


def set_font(run, latin: str, eastasia: str) -> None:
    """同时设置西文与中文（东亚）字体，否则 Word 中文仍走默认字体。"""
    run.font.name = latin
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), latin)
    rFonts.set(qn("w:hAnsi"), latin)
    rFonts.set(qn("w:eastAsia"), eastasia)


def style_font(style, latin: str, eastasia: str, size: float | None = None,
               bold: bool | None = None) -> None:
    """在样式定义上设置字体/字号/粗体，并清除主题色（默认是蓝色 0F4761）。"""
    f = style.font
    f.name = latin
    if size is not None:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    # 颜色强制为黑色：显式写 w:color，并把主题色属性去掉
    rgb = f.color
    rgb.rgb = RGBColor(0, 0, 0)
    rPr = style.element.get_or_add_rPr()
    color_el = rPr.find(qn("w:color"))
    if color_el is None:
        color_el = OxmlElement("w:color")
        rPr.append(color_el)
    color_el.set(qn("w:val"), "000000")
    for attr in ("w:themeColor", "w:themeShade", "w:themeTint"):
        if color_el.get(qn(attr)) is not None:
            del color_el.attrib[qn(attr)]
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), latin)
    rFonts.set(qn("w:hAnsi"), latin)
    rFonts.set(qn("w:eastAsia"), eastasia)


def number_captions(doc) -> tuple[int, int]:
    """给题注补上「图 N」「表 N」前缀。

    pandoc 只保留 caption 正文，不输出编号（实测 20 条题注全部无编号），
    而 PDF 里是「图 1 xxx」「表 1 xxx」。这里按出现顺序补回。
    """
    n_fig = n_tbl = 0
    for para in doc.paragraphs:
        st = para.style.name
        if st not in ("Image Caption", "Table Caption", "Caption"):
            continue
        text = para.text.strip()
        if not text or text.startswith(("图 ", "表 ")):
            continue
        if st == "Image Caption":
            n_fig += 1
            prefix = f"图 {n_fig} "
        else:
            n_tbl += 1
            prefix = f"表 {n_tbl} "
        # 保留首个 run 的字体设置，把前缀拼到它前面
        if para.runs:
            para.runs[0].text = prefix + para.runs[0].text
        else:
            para.add_run(prefix)
    return n_fig, n_tbl


def set_page_layout(doc) -> None:
    """A4 纸、页边距 2.5cm，与 PDF 一致。"""
    for sec in doc.sections:
        sec.page_width = Cm(21)
        sec.page_height = Cm(29.7)
        sec.top_margin = Cm(2.5)
        sec.bottom_margin = Cm(2.5)
        sec.left_margin = Cm(2.5)
        sec.right_margin = Cm(2.5)
        sec.header_distance = Cm(1.5)
        sec.footer_distance = Cm(1.5)


def add_page_numbers(doc) -> None:
    """页脚居中插入页码域（与 PDF 的页脚一致）。"""
    for sec in doc.sections:
        footer = sec.footer
        # 清空原有内容
        for p in list(footer.paragraphs):
            p._element.getparent().remove(p._element)
        p = footer.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        run = p.add_run()
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = " PAGE "
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        run._r.append(fld_begin)
        run._r.append(instr)
        run._r.append(fld_end)

        set_font(run, "Times New Roman", "SimSun")
        run.font.size = Pt(10.5)
        run.font.color.rgb = RGBColor(0, 0, 0)


def polish(doc) -> None:
    """按课程模板口径统一版式：字体颜色、字号、行距、缩进、题注编号、页码。"""
    set_page_layout(doc)

    # ---- 样式层 ----
    try:
        normal = doc.styles["Normal"]
        style_font(normal, "Times New Roman", "SimSun", size=12)
        pf = normal.paragraph_format
        pf.line_spacing = Pt(20)          # 原文行距 20 磅
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
    except KeyError:
        pass
    heading_spec = {"Heading 1": 14, "Heading 2": 12, "Heading 3": 12}
    for name, size in heading_spec.items():
        try:
            style_font(doc.styles[name], "Times New Roman", "SimSun", size=size, bold=True)
        except KeyError:
            pass

    for para in doc.paragraphs:
        name = para.style.name
        pf = para.paragraph_format
        if name.startswith("Heading"):
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            size = heading_spec.get(name, 12)
            pf.first_line_indent = Pt(0)
            for r in para.runs:
                set_font(r, "Times New Roman", "SimSun")
                r.font.size = Pt(size)
                r.font.bold = True
                r.font.color.rgb = RGBColor(0, 0, 0)
            continue
        if name in ("Image Caption", "Table Caption", "Caption", "Title"):
            if name != "Title":
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pf.first_line_indent = Pt(0)
            pf.line_spacing = Pt(15)
            for r in para.runs:
                set_font(r, "Times New Roman", "SimSun")
                r.font.size = Pt(10.5)
                r.font.color.rgb = RGBColor(0, 0, 0)
            continue
        if name == "Source Code":
            pf.first_line_indent = Pt(0)
            pf.line_spacing = Pt(11)
            for r in para.runs:
                set_font(r, "Consolas", "SimSun")
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(0, 0, 0)
            continue
        # 正文：行距 20 磅、首行缩进 2 字符
        pf.line_spacing = Pt(20)
        pf.first_line_indent = Pt(24)     # 12pt 字号的 2 字符
        for r in para.runs:
            set_font(r, "Times New Roman", "SimSun")
            r.font.color.rgb = RGBColor(0, 0, 0)
        t = para.text.strip()
        if len(t) > 24 and not t.startswith(("表 ", "图 ", "代码 ")):
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for table in doc.tables:
        set_three_line(table)
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.first_line_indent = Pt(0)
                    p.paragraph_format.line_spacing = Pt(12)
                    for r in p.runs:
                        set_font(r, "Times New Roman", "SimSun")
                        r.font.size = Pt(10.5)
                        r.font.color.rgb = RGBColor(0, 0, 0)

    # 题注编号与页码
    n_fig, n_tbl = number_captions(doc)
    add_page_numbers(doc)
    print(f"  题注编号: 图 {n_fig} 条、表 {n_tbl} 条")
    print("  页面: A4 / 边距 2.5cm / 页脚页码已插入")


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