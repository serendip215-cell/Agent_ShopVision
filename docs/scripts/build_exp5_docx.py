# -*- coding: utf-8 -*-
"""实验五（期末）项目总结报告高精度转 Word（.docx）。

复用 docs/scripts/typ_to_docx.py 的语义化导出 + pandoc + python-docx 后处理管线，
并在其基础上针对《实验五》报告版式做全项高保真还原，尽量 1:1 保留 PDF 格式：
  1. 源文件指向最新 docs/typ/实验五.typ（与 docs/build/实验五-*.pdf 同源）；
  2. 两张 SVG 矢量图替换为高清 PNG 栅格件（figs_exp5/ 下同名 .png）；
  3. 裸下划线转义 + 全部叠词折叠（修复「表 表 7」「图 图 2」「如表 表 1」）；
  4. 封面精确复刻 PDF 版式：不换行「题目：」、下划线与表格对齐、11pt 单行「主要分工」组员表；
  5. 封面后插入分节符（Next Page），封面无页码、正文摘要页起从「1」开始居中编号；
  6. 题注全部正体五号居中（去除 pandoc 默认斜体），表注/图片与相邻元素防分页拆散；
  7. 全文 13 张三线表按 A4 满版宽 16.0 cm 精确分配列宽、表头加粗、垂直居中、跨页重复表头；
  8. 参考文献 10.5pt 悬挂缩进左对齐、超链接统一纯黑色无下划线。

用法：
    py -3 docs/scripts/build_exp5_docx.py
    py -3 docs/scripts/build_exp5_docx.py --out "docs/交付材料/实验五_第23组/实验五实验报告 第23组.docx"
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs" / "scripts"))

import typ_to_docx as t2d  # noqa: E402

SRC = ROOT / "docs" / "typ" / "实验五.typ"
WORK = ROOT / "docs" / "build" / "_word" / "exp5_src"
FIGS = WORK / "figs_exp5"
DEFAULT_OUT = ROOT / "docs" / "交付材料" / "实验五_第23组" / "实验五实验报告 第23组.docx"

# 封面信息（与 docs/typ/实验五.typ 封面 100% 一致）
EXP5_COVER = {
    "school": "西 安 邮 电 大 学",
    "title": "AI 全栈开发实验",
    "subject_label": "题目：",
    "subject": "项目总结报告",
    "group_label": "组　号：",
    "group": "23",
    "members_label": "组员信息：",
    "time_label": "时　间：",
    "time": "2026.11.11",
    "members": [
        ("2610321101", "何朝杨", "5.3 Agent 框架集成与联调"),
        ("2610321103", "杜军博", "5.1 环境数据、项目总结报告整合与排版"),
        ("2610321135", "王陆洲", "5.4 后端服务与接口文档"),
        ("2610320046", "张梓萱", "5.4.2 前端页面与浏览器兼容"),
        ("2610320033", "刘凡思雨", "5.2 模型选择与 LoRA 微调、宣传海报"),
        ("2610321168", "秦鑫洋", "资料归档、截图录屏与交付材料整理"),
    ],
}

PNG_STANDINS = {
    "figs_exp5/00_实验闭环架构.svg": "00_实验闭环架构.png",
    "figs_exp5/02_微调流水线.svg": "02_微调流水线.png",
}

# 13 张正文三线表精确列宽（单位 cm，总宽严格 16.0 cm 对应 A4 2.5cm 页边距版心）
# 键为表头前两列元组，避免顺序调整时错配
TABLE_COL_WIDTHS_CM: dict[tuple[str, str], tuple[float, ...]] = {
    ("项目", "配置"): (3.4, 12.6),
    ("层次", "组件与作用"): (3.0, 13.0),
    ("划分", "样本数"): (2.2, 2.5, 4.3, 7.0),
    ("指标", "基座"): (3.4, 3.2, 3.4, 6.0),
    ("后端", "batch"): (4.6, 2.0, 3.1, 3.1, 3.2),
    ("评测版本", "数据"): (4.2, 2.4, 2.8, 3.2, 3.4),
    ("任务", "平均响应时间"): (3.3, 5.1, 5.5, 2.1),
    ("轮次", "输入"): (1.8, 7.4, 6.8),
    ("目标", "阈值"): (3.9, 3.5, 6.3, 2.3),
    ("问题", "原因"): (3.6, 5.6, 6.8),
    ("对比项", "实验 2 Chinese-CLIP"): (2.6, 6.4, 7.0),
    ("目录", "用途"): (6.4, 9.6),
    ("模型", "关键参数"): (3.8, 4.4, 7.8),
}


def prepare_workdir() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    FIGS.mkdir(parents=True)
    orig = ROOT / "docs" / "typ" / "figs_exp5"
    for png in sorted(orig.glob("*.png")):
        shutil.copy2(png, FIGS / png.name)
    print("工作目录就绪:", WORK, "（PNG", len(list(FIGS.glob("*.png"))), "张）")


def fix_semantic(semantic: Path) -> None:
    """语义化导出后修复裸下划线与交叉引用叠词。"""
    text = semantic.read_text(encoding="utf-8")
    lines = text.split("\n")
    n_esc = 0
    for i, line in enumerate(lines):
        q_parts = line.split('"')
        new_q = []
        for qi, qseg in enumerate(q_parts):
            if qi % 2 == 1:
                new_q.append(qseg)
                continue
            if "`" not in qseg:
                segs = [(qseg, False)]
            else:
                parts = qseg.split("`")
                segs = [(seg, k % 2 == 1) for k, seg in enumerate(parts)]
            out = []
            for seg, in_code in segs:
                if in_code:
                    out.append(seg)
                    continue
                fixed = re.sub(r"(?<!\\)_", r"\\_", seg)
                n_esc += len(re.findall(r"(?<!\\)_", seg))
                out.append(fixed)
            new_q.append("`".join(out))
        lines[i] = '"'.join(new_q)
    text = "\n".join(lines)

    # 折叠所有「表 表 7」「图 图 2」「如表 表 1」「如图 图 1」等叠词
    pattern_dbl = re.compile(r"([表图])\s+\1(?=\s*\d)")
    n_dbl = len(pattern_dbl.findall(text))
    text = pattern_dbl.sub(r"\1", text)
    semantic.write_text(text, encoding="utf-8")
    print(f"下划线转义: {n_esc} 处；叠词折叠: {n_dbl} 处")


def semantic_export(src: Path) -> Path:
    semantic = WORK / "report.typ"
    t2d.run([
        sys.executable,
        str(ROOT / "docs" / "scripts" / "typ_semantic_export.py"),
        "--src",
        str(src),
        "--out",
        str(semantic),
    ])
    text = semantic.read_text(encoding="utf-8")
    n_svg = sum(text.count(k) for k in PNG_STANDINS)
    for svg, png in PNG_STANDINS.items():
        text = text.replace(svg, f"figs_exp5/{png}")
    text = text.replace("(figs_exp5/", f"({FIGS.as_posix()}/")
    semantic.write_text(text, encoding="utf-8")
    print(f"SVG 引用替换: {n_svg} 处；图片路径改绝对路径: {FIGS}")
    fix_semantic(semantic)
    return semantic


def pandoc_convert(semantic: Path, out: Path) -> None:
    pandoc = t2d.find_pandoc()
    csl = t2d.ensure_csl()
    out.parent.mkdir(parents=True, exist_ok=True)
    t2d.run([
        str(pandoc),
        "-f",
        "typst",
        "-t",
        "docx",
        "--citeproc",
        f"--csl={csl}",
        f"--bibliography={t2d.BIB}",
        "--resource-path",
        str(WORK),
        "-o",
        str(out),
        str(semantic),
    ])


def _set_fixed_table_widths(table, widths_cm: tuple[float, ...]) -> None:
    """强制 Word 严格按固定列宽渲染，并设置单元格内边距与垂直居中。"""
    tbl = table._tbl
    tblPr = tbl.tblPr

    total_dxa = int(round(sum(widths_cm) * 567))
    for tag in ("w:tblW", "w:tblLayout", "w:tblCellMar"):
        for el in tblPr.findall(qn(tag)):
            tblPr.remove(el)

    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(total_dxa))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)

    tblLayout = OxmlElement("w:tblLayout")
    tblLayout.set(qn("w:type"), "fixed")
    tblPr.append(tblLayout)

    cellMar = OxmlElement("w:tblCellMar")
    for side, val in (("top", "60"), ("bottom", "60"), ("left", "80"), ("right", "80")):
        m = OxmlElement(f"w:{side}")
        m.set(qn("w:w"), val)
        m.set(qn("w:type"), "dxa")
        cellMar.append(m)
    tblPr.append(cellMar)

    # 重建 w:tblGrid
    old_grid = tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl.remove(old_grid)
    grid = OxmlElement("w:tblGrid")
    col_dxas = [int(round(w * 567)) for w in widths_cm]
    for dxa in col_dxas:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(dxa))
        grid.append(gc)
    tblPr.addnext(grid)

    table.autofit = False
    for r_idx, row in enumerate(table.rows):
        for c_idx, cell in enumerate(row.cells):
            if c_idx >= len(col_dxas):
                continue
            tcPr = cell._tc.get_or_add_tcPr()
            for el in tcPr.findall(qn("w:tcW")):
                tcPr.remove(el)
            tcW = OxmlElement("w:tcW")
            tcW.set(qn("w:w"), str(col_dxas[c_idx]))
            tcW.set(qn("w:type"), "dxa")
            tcPr.append(tcW)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                pf = p.paragraph_format
                pf.first_line_indent = Pt(0)
                pf.left_indent = Pt(0)
                pf.line_spacing = Pt(14)
                pf.space_before = Pt(0)
                pf.space_after = Pt(0)
                for r in p.runs:
                    t2d.set_font(r, "Times New Roman", "SimSun")
                    r.font.size = Pt(10.5)
                    r.font.color.rgb = RGBColor(0, 0, 0)
                    if r_idx == 0:
                        r.font.bold = True


def _cover_line_table(
    doc: Document,
    label: str,
    value: str,
    label_size: float,
    value_size: float,
    left_cm: float = 3.1,
    right_cm: float = 11.1,
    indent_cm: float = 0.9,
):
    """封面「标签：__________值__________」两列无框固定宽表格（标签绝不换行）。"""
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    tblPr = tbl._tbl.tblPr

    for tag in ("w:tblBorders", "w:tblW", "w:tblLayout", "w:tblInd", "w:tblCellMar"):
        for el in tblPr.findall(qn(tag)):
            tblPr.remove(el)

    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "none")
        e.set(qn("w:sz"), "0")
        borders.append(e)
    tblPr.append(borders)

    total_dxa = int(round((left_cm + right_cm) * 567))
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(total_dxa))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)

    tblLayout = OxmlElement("w:tblLayout")
    tblLayout.set(qn("w:type"), "fixed")
    tblPr.append(tblLayout)

    tblInd = OxmlElement("w:tblInd")
    tblInd.set(qn("w:w"), str(int(round(indent_cm * 567))))
    tblInd.set(qn("w:type"), "dxa")
    tblPr.append(tblInd)

    cellMar = OxmlElement("w:tblCellMar")
    for side, val in (("top", "0"), ("bottom", "40"), ("left", "20"), ("right", "20")):
        m = OxmlElement(f"w:{side}")
        m.set(qn("w:w"), val)
        m.set(qn("w:type"), "dxa")
        cellMar.append(m)
    tblPr.append(cellMar)

    old_grid = tbl._tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl._tbl.remove(old_grid)
    grid = OxmlElement("w:tblGrid")
    for cm_val in (left_cm, right_cm):
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(int(round(cm_val * 567))))
        grid.append(gc)
    tblPr.addnext(grid)

    left_cell, right_cell = tbl.rows[0].cells
    for cell, cm_val in ((left_cell, left_cm), (right_cell, right_cm)):
        tcPr = cell._tc.get_or_add_tcPr()
        for el in tcPr.findall(qn("w:tcW")):
            tcPr.remove(el)
        tcW = OxmlElement("w:tcW")
        tcW.set(qn("w:w"), str(int(round(cm_val * 567))))
        tcW.set(qn("w:type"), "dxa")
        tcPr.append(tcW)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM

    lp = left_cell.paragraphs[0]
    lp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    lpf = lp.paragraph_format
    lpf.first_line_indent = Pt(0)
    lpf.space_before = Pt(0)
    lpf.space_after = Pt(2)
    lpf.line_spacing = 1.0
    lr = lp.add_run(label)
    t2d.set_font(lr, "Times New Roman", "SimSun")
    lr.font.size = Pt(label_size)
    lr.font.bold = True
    lr.font.color.rgb = RGBColor(0, 0, 0)

    rp = right_cell.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rpf = rp.paragraph_format
    rpf.first_line_indent = Pt(0)
    rpf.space_before = Pt(0)
    rpf.space_after = Pt(2)
    rpf.line_spacing = 1.0
    vr = rp.add_run(value)
    t2d.set_font(vr, "Times New Roman", "SimSun")
    vr.font.size = Pt(value_size)
    vr.font.bold = True
    vr.font.color.rgb = RGBColor(0, 0, 0)

    # 左列显式清零所有边框，避免 Word 显示浅灰辅助线
    ltcPr = left_cell._tc.get_or_add_tcPr()
    for el in ltcPr.findall(qn("w:tcBorders")):
        ltcPr.remove(el)
    ltcb = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "none")
        e.set(qn("w:sz"), "0")
        ltcb.append(e)
    ltcPr.append(ltcb)

    tcPr = right_cell._tc.get_or_add_tcPr()
    for el in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(el)
    tcb = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "right"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "none")
        e.set(qn("w:sz"), "0")
        tcb.append(e)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "0")
    bottom.set(qn("w:color"), "000000")
    tcb.append(bottom)
    tcPr.append(tcb)

    return tbl._tbl


def build_exp5_cover_and_sections(doc: Document) -> None:
    """按 docs/typ/实验五.typ 1:1 复刻封面，并用分节符使封面无页码、正文从第 1 页编号。"""
    new_elems = []

    def add_para(
        text: str = "",
        size: float = 12.0,
        bold: bool = False,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        space_before: float = 0,
        space_after: float = 0,
        font_cn: str = "SimSun",
        font_en: str = "Times New Roman",
        left_indent_cm: float = 0.0,
    ):
        p = doc.add_paragraph()
        if text:
            r = p.add_run(text)
            t2d.set_font(r, font_en, font_cn)
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = RGBColor(0, 0, 0)
        pf = p.paragraph_format
        pf.alignment = align
        pf.first_line_indent = Pt(0)
        if left_indent_cm:
            pf.left_indent = Cm(left_indent_cm)
        pf.space_before = Pt(space_before)
        pf.space_after = Pt(space_after)
        pf.line_spacing = 1.15
        new_elems.append(p._element)
        return p

    # 1. 校名 + 实验名（字体与原 PDF 完全一致：校名宋体 26pt、实验名黑体+TNR 26pt）
    add_para(EXP5_COVER["school"], size=26, bold=True, space_before=36, font_cn="SimSun")
    add_para(EXP5_COVER["title"], size=26, bold=True, space_before=48, font_cn="SimHei")

    # 2. 题目
    add_para("", size=6, space_before=36)
    new_elems.append(
        _cover_line_table(
            doc, EXP5_COVER["subject_label"], EXP5_COVER["subject"], label_size=20, value_size=20
        )
    )

    # 3. 组号
    add_para("", size=6, space_before=32)
    new_elems.append(
        _cover_line_table(
            doc, EXP5_COVER["group_label"], EXP5_COVER["group"], label_size=14, value_size=14
        )
    )

    # 4. 组员信息标签 + 6 行全网格表（11pt 单行，表头为「学号 / 姓名 / 主要分工」）
    add_para("", size=6, space_before=20)
    add_para(
        EXP5_COVER["members_label"],
        size=14,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_after=6,
        left_indent_cm=1.0,
    )

    tbl = doc.add_table(rows=1 + len(EXP5_COVER["members"]), cols=3)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    new_elems.append(tbl._tbl)

    tblPr = tbl._tbl.tblPr
    for tag in ("w:tblBorders", "w:tblW", "w:tblLayout", "w:tblCellMar"):
        for el in tblPr.findall(qn(tag)):
            tblPr.remove(el)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), "000000")
        borders.append(e)
    tblPr.append(borders)

    col_widths_cm = (3.8, 3.3, 7.3)  # 总宽 14.4 cm，与上方横线区左右平齐
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(int(round(sum(col_widths_cm) * 567))))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)

    tblLayout = OxmlElement("w:tblLayout")
    tblLayout.set(qn("w:type"), "fixed")
    tblPr.append(tblLayout)

    cellMar = OxmlElement("w:tblCellMar")
    for side, val in (("top", "120"), ("bottom", "120"), ("left", "80"), ("right", "80")):
        m = OxmlElement(f"w:{side}")
        m.set(qn("w:w"), val)
        m.set(qn("w:type"), "dxa")
        cellMar.append(m)
    tblPr.append(cellMar)

    old_grid = tbl._tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl._tbl.remove(old_grid)
    grid = OxmlElement("w:tblGrid")
    for w in col_widths_cm:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(int(round(w * 567))))
        grid.append(gc)
    tblPr.addnext(grid)

    headers = ("学号", "姓名", "主要分工")
    rows_data = [headers, *EXP5_COVER["members"]]
    for r_idx, row_vals in enumerate(rows_data):
        for c_idx, val in enumerate(row_vals):
            cell = tbl.rows[r_idx].cells[c_idx]
            tcPr = cell._tc.get_or_add_tcPr()
            for el in tcPr.findall(qn("w:tcW")):
                tcPr.remove(el)
            tcW = OxmlElement("w:tcW")
            tcW.set(qn("w:w"), str(int(round(col_widths_cm[c_idx] * 567))))
            tcW.set(qn("w:type"), "dxa")
            tcPr.append(tcW)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

            cp = cell.paragraphs[0]
            cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cp.paragraph_format.first_line_indent = Pt(0)
            cp.paragraph_format.line_spacing = 1.1
            cp.paragraph_format.space_before = Pt(0)
            cp.paragraph_format.space_after = Pt(0)
            cr = cp.add_run(val)
            t2d.set_font(cr, "Times New Roman", "SimSun")
            cr.font.size = Pt(11)
            cr.font.bold = r_idx == 0
            cr.font.color.rgb = RGBColor(0, 0, 0)

    # 5. 时间
    add_para("", size=6, space_before=18)
    new_elems.append(
        _cover_line_table(
            doc, EXP5_COVER["time_label"], EXP5_COVER["time"], label_size=14, value_size=14
        )
    )

    # 6. 插入分节符段落（封面属于第 1 节无页码，正文属于第 2 节从第 1 页编号）
    sec_p = doc.add_paragraph()
    sec_p.paragraph_format.space_before = Pt(0)
    sec_p.paragraph_format.space_after = Pt(0)
    sec_p.paragraph_format.line_spacing = Pt(1)
    pPr = sec_p._p.get_or_add_pPr()
    cover_sectPr = OxmlElement("w:sectPr")
    pgSz = OxmlElement("w:pgSz")
    pgSz.set(qn("w:w"), "11906")
    pgSz.set(qn("w:h"), "16838")
    cover_sectPr.append(pgSz)
    pgMar = OxmlElement("w:pgMar")
    for k, v in (
        ("top", "1418"),
        ("right", "1418"),
        ("bottom", "1418"),
        ("left", "1418"),
        ("header", "851"),
        ("footer", "851"),
        ("gutter", "0"),
    ):
        pgMar.set(qn(f"w:{k}"), v)
    cover_sectPr.append(pgMar)
    sec_type = OxmlElement("w:type")
    sec_type.set(qn("w:val"), "nextPage")
    cover_sectPr.append(sec_type)
    pPr.append(cover_sectPr)
    new_elems.append(sec_p._element)

    # 整体插到正文最前
    body = doc.element.body
    anchor = body[0]
    for el in new_elems:
        anchor.addprevious(el)

    # 配置两节的页码：第 1 节（封面）清空页脚；第 2 节（正文）从 1 开始居中页码
    sec_cover = doc.sections[0]
    sec_body = doc.sections[1]
    sec_body.start_type = WD_SECTION_START.NEW_PAGE
    sec_body.footer.is_linked_to_previous = False
    for p in list(sec_cover.footer.paragraphs):
        p._element.getparent().remove(p._element)
    sec_cover.footer.add_paragraph()

    # 设置正文节起始页码为 1
    body_sectPr = sec_body._sectPr
    for old in body_sectPr.findall(qn("w:pgNumType")):
        body_sectPr.remove(old)
    pgNumType = OxmlElement("w:pgNumType")
    pgNumType.set(qn("w:start"), "1")
    body_sectPr.append(pgNumType)

    # 写入正文居中页码域
    for p in list(sec_body.footer.paragraphs):
        p._element.getparent().remove(p._element)
    fp = sec_body.footer.add_paragraph()
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fp.add_run()
    for fld_type in ("begin", "instr", "end"):
        if fld_type == "instr":
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = " PAGE "
            run._r.append(instr)
        else:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), fld_type)
            run._r.append(fld)
    t2d.set_font(run, "Times New Roman", "SimSun")
    run.font.size = Pt(10.5)
    run.font.color.rgb = RGBColor(0, 0, 0)

    print("  封面与分节: 已精确复刻（封面无页码、正文第 1 页起编、11pt 单行主要分工表）")


def _fix_hyperlinks_black(elem) -> None:
    """将参考文献等处的蓝色下划线超链接文字统一为纯黑无下划线，与 PDF 一致。"""
    for r in elem.findall(".//" + qn("w:r")):
        rPr = r.find(qn("w:rPr"))
        if rPr is None:
            rPr = OxmlElement("w:rPr")
            r.insert(0, rPr)
        for style_el in rPr.findall(qn("w:rStyle")):
            if style_el.get(qn("w:val")) == "Hyperlink":
                rPr.remove(style_el)
        for old in rPr.findall(qn("w:color")):
            rPr.remove(old)
        color = OxmlElement("w:color")
        color.set(qn("w:val"), "000000")
        rPr.append(color)
        for old in rPr.findall(qn("w:u")):
            rPr.remove(old)
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "none")
        rPr.append(u)
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.append(rFonts)
        rFonts.set(qn("w:ascii"), "Times New Roman")
        rFonts.set(qn("w:hAnsi"), "Times New Roman")
        rFonts.set(qn("w:eastAsia"), "SimSun")
        for old in rPr.findall(qn("w:sz")):
            rPr.remove(old)
        for old in rPr.findall(qn("w:szCs")):
            rPr.remove(old)
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), "21")  # 10.5pt
        szCs = OxmlElement("w:szCs")
        szCs.set(qn("w:val"), "21")
        rPr.append(sz)
        rPr.append(szCs)


def _get_style(doc: Document, name: str):
    for s in doc.styles:
        if s.name == name:
            return s
    return None


def _remove_empty_body_paras(doc: Document) -> int:
    """移除正文中既无文字也无图片/分节符/分页符的纯空白段落，防止表格满页后多出空白页。"""
    removed = 0
    for p in list(doc.paragraphs):
        xml = p._element.xml
        if p.text.strip():
            continue
        if any(tag in xml for tag in ("<w:drawing", "<w:pict", "<w:sectPr", "<w:br")):
            continue
        parent = p._element.getparent()
        if parent is not None:
            parent.remove(p._element)
            removed += 1
    return removed


def polish_exp5(doc: Document) -> None:
    """高保真论文排版精修：匹配 docs/typ/实验五.typ PDF 全部视觉与排版规范。"""
    t2d.set_page_layout(doc)
    n_empty = _remove_empty_body_paras(doc)
    if n_empty:
        print(f"  清理多余空段: {n_empty} 个")

    # 样式层：正文 12pt 宋体+TNR，固定行距 19pt（与 PDF 观感与分页高度一致）
    body_leading = Pt(19)
    normal = _get_style(doc, "Normal")
    if normal is not None:
        t2d.style_font(normal, "Times New Roman", "SimSun", size=12)
        normal.paragraph_format.line_spacing = body_leading
        normal.paragraph_format.space_before = Pt(0)
        normal.paragraph_format.space_after = Pt(0)

    for style_name in ("Body Text", "First Paragraph", "Normal (Web)"):
        st = _get_style(doc, style_name)
        if st is not None:
            st.paragraph_format.line_spacing = body_leading
            st.paragraph_format.space_before = Pt(0)
            st.paragraph_format.space_after = Pt(0)

    # 清除题注样式默认的斜体
    for cap_style in ("Caption", "Image Caption", "Table Caption"):
        st = _get_style(doc, cap_style)
        if st is not None:
            t2d.style_font(st, "Times New Roman", "SimSun", size=10.5, bold=False)
            st.font.italic = False

    heading_spec = {"Heading 1": 16, "Heading 2": 14, "Heading 3": 12}
    heading_gaps = {"Heading 1": (6, 12), "Heading 2": (12, 6), "Heading 3": (9, 4)}
    for name, size in heading_spec.items():
        st = _get_style(doc, name)
        if st is not None:
            east = "SimHei" if name == "Heading 1" else "SimSun"
            t2d.style_font(st, "Times New Roman", east, size=size, bold=True)
            before, after = heading_gaps[name]
            st.paragraph_format.space_before = Pt(before)
            st.paragraph_format.space_after = Pt(after)
            st.paragraph_format.line_spacing = Pt(size * 1.35)

    # 移除自动编号 numPr
    for para in doc.paragraphs:
        pPr = para._p.find(qn("w:pPr"))
        if pPr is not None:
            numPr = pPr.find(qn("w:numPr"))
            if numPr is not None:
                pPr.remove(numPr)

    first_h1_seen = False
    for para in doc.paragraphs:
        name = para.style.name
        pf = para.paragraph_format

        if name.startswith("Heading"):
            size = heading_spec.get(name, 12)
            if name == "Heading 1":
                # 第一个一级标题（摘要）紧接封面分节符，不再多插分页符避免空白页
                pf.page_break_before = first_h1_seen
                first_h1_seen = True
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                east = "SimHei"
            else:
                para.alignment = WD_ALIGN_PARAGRAPH.LEFT
                east = "SimSun"
            pf.first_line_indent = Pt(0)
            pf.keep_with_next = True
            for r in para.runs:
                t2d.set_font(r, "Times New Roman", east)
                r.font.size = Pt(size)
                r.font.bold = True
                r.font.italic = False
                r.font.color.rgb = RGBColor(0, 0, 0)
            continue

        if name in ("Image Caption", "Table Caption", "Caption", "Title"):
            if name != "Title":
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pf.first_line_indent = Pt(0)
            pf.line_spacing = Pt(15)
            pf.space_before = Pt(4 if name == "Table Caption" else 2)
            pf.space_after = Pt(4 if name == "Table Caption" else 8)
            if name == "Table Caption":
                pf.keep_with_next = True
            for r in para.runs:
                t2d.set_font(r, "Times New Roman", "SimSun")
                r.font.size = Pt(10.5)
                r.font.italic = False
                r.font.color.rgb = RGBColor(0, 0, 0)
            continue

        if name == "Source Code":
            pf.first_line_indent = Pt(0)
            pf.left_indent = Pt(0)
            pf.line_spacing = Pt(11)
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            for r in para.runs:
                t2d.set_font(r, "Consolas", "SimSun")
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(0, 0, 0)
            continue

        if "<w:drawing" in para._element.xml or "<w:pict" in para._element.xml:
            pf.first_line_indent = Pt(0)
            pf.left_indent = Pt(0)
            pf.line_spacing = 1.0
            pf.space_before = Pt(6)
            pf.space_after = Pt(2)
            pf.keep_with_next = True  # 图片与下方图注不分页拆散
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            continue

        if name == "Bibliography":
            pf.left_indent = Cm(0.85)
            pf.first_line_indent = Cm(-0.85)
            pf.line_spacing = Pt(16)
            pf.space_before = Pt(0)
            pf.space_after = Pt(3)
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _fix_hyperlinks_black(para._element)
            continue

        t_stripped = para.text.strip()
        if re.match(r"^\d+[.．、]\s*\S", t_stripped) and not re.match(r"^\d+\.\d", t_stripped):
            pf.line_spacing = body_leading
            pf.first_line_indent = Pt(0)
            pf.left_indent = Pt(0)
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            for r in para.runs:
                t2d.set_font(r, "Times New Roman", "SimSun")
                r.font.color.rgb = RGBColor(0, 0, 0)
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            continue

        # 正文：19pt 行距、首行缩进 2 字符
        pf.line_spacing = body_leading
        pf.first_line_indent = Pt(24)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        for r in para.runs:
            t2d.set_font(r, "Times New Roman", "SimSun")
            r.font.color.rgb = RGBColor(0, 0, 0)
        if len(t_stripped) > 24 and not t_stripped.startswith(("表 ", "图 ", "代码 ")):
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # 正文三线表：精确列宽 + 跨页表头重复 + 表头加粗 + 垂直居中
    matched_tables = 0
    for table in doc.tables:
        t2d.set_three_line(table)
        t2d.set_table_repeat_header(table)
        head_cells = [c.text.strip() for c in table.rows[0].cells] if table.rows else []
        key = (head_cells[0], head_cells[1]) if len(head_cells) >= 2 else ("", "")
        widths = TABLE_COL_WIDTHS_CM.get(key)
        if widths is None and table.columns:
            # 兜底均匀铺满 16.0 cm
            widths = tuple(round(16.0 / len(table.columns), 2) for _ in range(len(table.columns)))
        else:
            matched_tables += 1
        if widths:
            _set_fixed_table_widths(table, widths)

    # 题注编号
    n_fig, n_tbl = t2d.number_captions(doc)
    n_code = t2d.number_code_captions(doc)
    # 编号补前缀后再确保题注 run 非斜体
    for para in doc.paragraphs:
        if para.style.name in ("Image Caption", "Table Caption", "Caption"):
            for r in para.runs:
                r.font.italic = False
                t2d.set_font(r, "Times New Roman", "SimSun")
                r.font.size = Pt(10.5)
                r.font.color.rgb = RGBColor(0, 0, 0)

    print(f"  题注编号: 图 {n_fig} 条、表 {n_tbl} 条、代码 {n_code} 条（全正体）")
    print(f"  三线表列宽: 精确匹配 {matched_tables}/{len(doc.tables)} 张表（总宽 16.0cm）")

    # 最后插入封面与分节页码
    build_exp5_cover_and_sections(doc)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成实验五高保真 Word（.docx）报告")
    ap.add_argument("--src", type=Path, default=SRC, help="Typst 源文件路径")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出 Word (.docx) 路径")
    args = ap.parse_args(argv)

    src = args.src if args.src.is_absolute() else ROOT / args.src
    out = args.out if args.out.is_absolute() else ROOT / args.out
    if not src.is_file():
        raise SystemExit(f"未找到源文件：{src}")

    prepare_workdir()
    semantic = semantic_export(src)
    pandoc_convert(semantic, out)

    doc = Document(str(out))
    polish_exp5(doc)
    doc.save(str(out))

    heads = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
    print("\n=== 转换完成 ===")
    print("  输出  :", out)
    print("  大小  : {:.2f} MB".format(out.stat().st_size / 1024 / 1024))
    print("  标题  :", len(heads))
    print("  表格  :", len(doc.tables))
    print("  图片  :", len(doc.inline_shapes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
