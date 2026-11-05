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
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
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


# 封面信息（与 docs/typ/实验四.typ 封面区一致，按课程模板
# AI全栈开发实验报告模板-2026-4.doc 的版式排布）
COVER = {
    "school": "西 安 邮 电 大 学",
    "title": "AI 全栈开发实验",
    "subject_label": "题目：",
    "subject": "前后端开发实验",
    "group_label": "组　号：",
    "group": "23",
    "members_label": "组员信息：",
    "time_label": "时　间：",
    "time": "2026.11.05",
    "members": [
        ("2610321101", "何朝杨", "后端 AI 服务、架构设计文档与成员分工表"),
        ("2610321103", "杜军博", "报告整合、排版与正式 PDF；核对推理耗时口径"),
        ("2610321135", "王陆洲", "API 文档与测试报告、模型产物上传"),
        ("2610320046", "张梓萱", "前端页面架构与公共组件、响应式与浏览器兼容"),
        ("2610320033", "刘凡思雨", "前端三页面交互与数据流、端到端与性能测试"),
        ("2610321168", "秦鑫洋", "问题与解决方案、截图录屏与交付材料整理"),
    ],
}


def _line_para(doc, label: str, value: str, label_size: float,
               value_size: float, indent_pt: float = 60):
    """封面「标签：__________值__________」一行。

    横线不用下划线空格拼（长度不可控、右端常断开），改用**段落下边框**：
    边框自动贯穿到右边距，值用制表位居中压在这条线上，与模板的
    「固定宽横线 + 居中值」一致。

    返回该段落的 XML 元素——不要用 doc.paragraphs[-1] 反查：
    表格也属于 body 的子元素，插入表格后段落列表的末尾就会错位，
    曾导致封面的「时间」行丢失。
    """
    from docx.enum.text import WD_TAB_ALIGNMENT

    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.first_line_indent = Pt(0)
    pf.line_spacing = Pt(value_size * 1.5)
    pf.left_indent = Pt(indent_pt)
    pf.right_indent = Pt(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf.space_after = Pt(10)

    # 段落下边框即在整行宽度上画线（横贯到右侧边界）。
    # python-docx 没有 pBdr 的 get_or_add_*，需手工插入；
    # OOXML 规定 pPr 子元素有固定顺序，pBdr 必须排在 spacing/ind/jc 之前，
    # 否则 Word 会忽略它（实测 append 到末尾时横线不显示）。
    pPr = p._p.get_or_add_pPr()
    for old in pPr.findall(qn("w:pBdr")):
        pPr.remove(old)
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), "000000")
    pBdr.append(bottom)
    # pBdr 在 CT_PPr 中的合法前驱：pStyle、keepNext、keepLines、pageBreakBefore、
    # framePr、widowControl、numPr、suppressLineNumbers；插到第一个既有元素之前。
    after_tags = ("w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore",
                  "w:framePr", "w:widowControl", "w:numPr", "w:suppressLineNumbers")
    anchor = None
    for tag in after_tags:
        found = pPr.find(qn(tag))
        if found is not None:
            anchor = found
    if anchor is not None:
        anchor.addnext(pBdr)
    else:
        pPr.insert(0, pBdr)

    lab = p.add_run(label)
    set_font(lab, "Times New Roman", "SimSun")
    lab.font.size = Pt(label_size)
    lab.font.bold = True
    lab.font.color.rgb = RGBColor(0, 0, 0)

    # 制表位：把值置于横线中央。
    # 版心宽 = A4 纸宽 595.3pt − 左右边距各 70.9pt(2.5cm) ≈ 453.5pt；
    # 该行左侧还有 indent_pt 的缩进，剩余可用宽度即为横线长度。
    usable_pt = 453.5 - indent_pt
    pf.tab_stops.add_tab_stop(Pt(max(usable_pt / 2 + indent_pt, 80)), WD_TAB_ALIGNMENT.CENTER)

    tab = p.add_run("\t")
    set_font(tab, "Times New Roman", "SimSun")
    val = p.add_run(value)
    set_font(val, "Times New Roman", "SimSun")
    val.font.size = Pt(value_size)
    val.font.bold = True
    val.font.color.rgb = RGBColor(0, 0, 0)
    return p._element


def build_cover(doc) -> None:
    """在文档最前面插入课程模板样式的封面页。

    语义化导出时封面被去掉（Word 另行排版），此处按
    AI全栈开发实验报告模板-2026-4.doc 的要素重建：
    校名、实验名、题目、组号、组员信息表、时间，随后分页。
    """
    from docx.oxml import OxmlElement as OE

    new_elems = []

    def add_para(text="", size=12.0, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER,
                 space_before=0, space_after=0, font_cn="SimSun",
                 font_en="Times New Roman"):
        p = doc.add_paragraph()
        if text:
            r = p.add_run(text)
            set_font(r, font_en, font_cn)
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = RGBColor(0, 0, 0)
        pf = p.paragraph_format
        pf.alignment = align
        pf.first_line_indent = Pt(0)
        pf.space_before = Pt(space_before)
        pf.space_after = Pt(space_after)
        pf.line_spacing = Pt(size * 1.4)
        new_elems.append(p._element)
        return p

    # 校名：宋体 26pt 粗体，字间加空格（与模板一致）
    add_para(COVER["school"], size=26, bold=True, space_before=54)
    # 实验名：26pt 粗体
    add_para(COVER["title"], size=26, bold=True, space_before=40)
    # 题目
    add_para("", size=6, space_before=26)
    new_elems.append(_line_para(doc, COVER["subject_label"], COVER["subject"], 20, 22, indent_pt=70))
    # 组号
    add_para("", size=6, space_before=20)
    new_elems.append(_line_para(doc, COVER["group_label"], COVER["group"], 14, 14, indent_pt=70))
    # 组员信息
    add_para("", size=6, space_before=16)
    p = doc.add_paragraph()
    r = p.add_run(COVER["members_label"])
    set_font(r, "Times New Roman", "SimSun")
    r.font.size = Pt(14)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0, 0, 0)
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.left_indent = Pt(70)
    p.paragraph_format.space_after = Pt(2)
    new_elems.append(p._element)

    # 组员表：全网格 0.5pt，三列
    tbl = doc.add_table(rows=1 + len(COVER["members"]), cols=3)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    # add_table 会把表追加到文档末尾；这里把它登记进待搬移列表，
    # 稍后与封面段落一起挪到正文最前（否则组员表会跑到文末）。
    new_elems.append(tbl._tbl)
    # 先移除默认样式带来的边框，再绘制 0.5pt 全网格
    tblPr = tbl._tbl.tblPr
    for el in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(el)
    borders = OE("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OE(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), "000000")
        borders.append(e)
    tblPr.append(borders)
    tbl.autofit = False
    widths = (Cm(3.9), Cm(3.5), Cm(7.0))
    headers = ("学号", "姓名", "分工")
    for j, (h, w) in enumerate(zip(headers, widths)):
        cell = tbl.rows[0].cells[j]
        cell.width = w
        cp = cell.paragraphs[0]
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cp.paragraph_format.first_line_indent = Pt(0)
        cr = cp.add_run(h)
        set_font(cr, "Times New Roman", "SimSun")
        cr.font.size = Pt(14)
        cr.font.bold = True
        cr.font.color.rgb = RGBColor(0, 0, 0)
    for i, (sid, name, duty) in enumerate(COVER["members"], start=1):
        for j, val in enumerate((sid, name, duty)):
            cell = tbl.rows[i].cells[j]
            cell.width = widths[j]
            cp = cell.paragraphs[0]
            cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cp.paragraph_format.first_line_indent = Pt(0)
            cr = cp.add_run(val)
            set_font(cr, "Times New Roman", "SimSun")
            cr.font.size = Pt(14)
            cr.font.color.rgb = RGBColor(0, 0, 0)
            if j == 0:
                cr.font.bold = True

    # 时间
    add_para("", size=6, space_before=14)
    new_elems.append(_line_para(doc, COVER["time_label"], COVER["time"], 14, 14, indent_pt=70))

    # 封面后分页：也登记进列表，与封面元素一起按顺序搬移
    brk = doc.add_paragraph()
    brk.paragraph_format.first_line_indent = Pt(0)
    brk.add_run().add_break(WD_BREAK.PAGE)
    new_elems.append(brk._element)

    # 把封面元素按登记顺序整体插到正文最前
    body = doc.element.body
    anchor = body[0]
    for el in new_elems:
        anchor.addprevious(el)

    print(f"  封面: 已生成（校名/实验名/题目/组号/组员表 {len(COVER['members'])} 行/时间）")


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
    # pandoc 给 Body Text 带 9pt 段前 + 9pt 段后，段间显得松。
    # 统一为：段前 0、段后 18 磅（只留一种间距，避免叠加成 18pt 双份）。
    for style_name in ("Body Text", "First Paragraph", "Normal (Web)"):
        try:
            spf = doc.styles[style_name].paragraph_format
            spf.space_before = Pt(0)
            spf.space_after = Pt(18)
        except KeyError:
            pass
    heading_spec = {"Heading 1": 14, "Heading 2": 12, "Heading 3": 12}
    for name, size in heading_spec.items():
        try:
            style_font(doc.styles[name], "Times New Roman", "SimSun", size=size, bold=True)
        except KeyError:
            pass

    # 编号列表项统一顶格：pandoc 把它们做成 Word 自动编号（numPr），
    # 编号定义的 w:ind 是 left=720/hanging=360，即左侧 36pt 缩进，
    # 看起来"标号左边空得太宽"。这里把自动编号拆掉——编号文本已经
    # 在段落里（"1. …"），去掉 numPr 后按普通段落处理并顶格。
    n_unlisted = 0
    for para in doc.paragraphs:
        pPr = para._p.find(qn("w:pPr"))
        if pPr is None:
            continue
        numPr = pPr.find(qn("w:numPr"))
        if numPr is not None:
            pPr.remove(numPr)
            n_unlisted += 1

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
        # 含图片的段落：必须用单倍行距、无缩进、居中。
        # 若沿用正文的固定 20 磅行距，图片会被压进行高里几乎不可见
        # （实测 extent 约 8.3cm 高却只剩一条灰线）。
        if "<w:drawing" in para._element.xml or "<w:pict" in para._element.xml:
            pf.first_line_indent = Pt(0)
            pf.left_indent = Pt(0)
            pf.line_spacing = 1.0
            pf.space_before = Pt(6)
            pf.space_after = Pt(3)
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # 图片段落本身不含文字 run，无需处理字体
            continue

        # 编号列表项（"1. xxx" / "2. xxx" 等）顶格：左缩进与首行缩进都清零。
        # 中文里这类列举项常顶格排版，加缩进反而与正文段落混淆。
        t_stripped = para.text.strip()
        if re.match(r"^\d+[.．、]\s*\S", t_stripped) and not re.match(r"^\d+\.\d", t_stripped):
            pf.line_spacing = Pt(20)
            pf.first_line_indent = Pt(0)
            pf.left_indent = Pt(0)
            pf.space_before = Pt(0)
            pf.space_after = Pt(18)
            for r in para.runs:
                set_font(r, "Times New Roman", "SimSun")
                r.font.color.rgb = RGBColor(0, 0, 0)
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            continue

        # 正文：行距 20 磅、首行缩进 2 字符、段前 0 / 段后 18 磅
        pf.line_spacing = Pt(20)
        pf.first_line_indent = Pt(24)     # 12pt 字号的 2 字符
        pf.space_before = Pt(0)
        pf.space_after = Pt(18)
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
                    p.paragraph_format.left_indent = Pt(0)
                    p.paragraph_format.line_spacing = Pt(12)
                    for r in p.runs:
                        set_font(r, "Times New Roman", "SimSun")
                        r.font.size = Pt(10.5)
                        r.font.color.rgb = RGBColor(0, 0, 0)

    # 参考文献：清掉 pandoc 带来的左缩进（实测 31.2pt），改为按条目悬挂观感
    for para in doc.paragraphs:
        if para.style.name == "Bibliography":
            pf = para.paragraph_format
            pf.left_indent = Pt(0)
            pf.first_line_indent = Pt(0)
            pf.line_spacing = Pt(18)
            pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # 题注编号与页码
    n_fig, n_tbl = number_captions(doc)
    add_page_numbers(doc)
    print(f"  题注编号: 图 {n_fig} 条、表 {n_tbl} 条")
    print("  页面: A4 / 边距 2.5cm / 页脚页码已插入")

    # 封面：最后生成，避免被前面的段落遍历与表格处理影响
    build_cover(doc)


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
