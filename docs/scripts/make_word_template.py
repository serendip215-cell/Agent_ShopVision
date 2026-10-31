# -*- coding: utf-8 -*-
"""用 Word COM 生成「实验三报告样式模板」.docx，供 cli-anything-word 的 --template 使用。

为什么要模板：cli-anything-word 的块级样式只能设 字号/粗斜体/对齐/颜色，改不了字体族、
行距、首行缩进、表格线。这些只能靠样式定义承载，而样式又只能通过 Word 自身写入。
本脚本只负责造样式壳子，正文仍然由 cli-anything-word 渲染。

样式映射（对齐 docs/typ/实验三.typ 的排版基准）：
  正文(-1)          宋体/Times 12pt，行距固定值 20 磅，首行缩进 24pt(=2 字符)，两端对齐
  标题 1(-2)        宋体 14pt 加粗（课程模板 AI全栈开发实验报告模板-2026-3.doc 里章标题就是宋体加粗），
                    段前 13pt / 段后 6pt，无缩进
  标题 2(-3)        宋体 12pt 粗体，段前 8pt / 段后 3pt
  标题 3(-4)        同标题 2
  题注(-35)         宋体/Times 10.5pt 居中，无缩进，供图表/代码题注使用
  引用(-181)        改作「代码」样式：Consolas 9pt + 0.4pt 外框，单倍行距、无缩进
用法: python docs/scripts/make_word_template.py [输出路径]
"""
import sys
from pathlib import Path

import win32com.client as win32

WD_LINE_SPACE_EXACTLY = 4
WD_ALIGN_LEFT, WD_ALIGN_CENTER, WD_ALIGN_JUSTIFY = 0, 1, 3
WD_BORDER_SINGLE = 1
WD_STYLE_NORMAL, WD_STYLE_H1, WD_STYLE_H2, WD_STYLE_H3 = -1, -2, -3, -4
WD_STYLE_CAPTION, WD_STYLE_QUOTE = -35, -181


def _set_font(style, latin: str, east_asian: str, size_pt: float, bold: bool | None = None):
    f = style.Font
    f.Name = latin
    f.NameFarEast = east_asian
    f.NameAscii = latin
    f.Size = size_pt
    f.Italic = 0          # 「引用」等内置样式自带斜体，不改会把代码整段排成 Consolas-Italic
    if bold is not None:
        f.Bold = -1 if bold else 0


def _set_par(style, *, align=None, indent_pt=0.0, line_pt=None, before_pt=0.0, after_pt=0.0):
    p = style.ParagraphFormat
    if align is not None:
        p.Alignment = align
    p.LeftIndent = 0
    p.RightIndent = 0
    p.FirstLineIndent = indent_pt
    if line_pt:
        p.LineSpacingRule = WD_LINE_SPACE_EXACTLY
        p.LineSpacing = line_pt
    p.SpaceBefore = before_pt
    p.SpaceAfter = after_pt


def build_template(out_path: Path) -> Path:
    app = win32.DispatchEx("Word.Application")
    app.Visible = False
    app.DisplayAlerts = 0
    try:
        doc = app.Documents.Add()
        ps = doc.PageSetup
        ps.PageWidth = 595.3          # A4
        ps.PageHeight = 841.9
        for attr in ("TopMargin", "BottomMargin", "LeftMargin", "RightMargin"):
            setattr(ps, attr, 70.9)   # 2.5cm

        normal = doc.Styles(WD_STYLE_NORMAL)
        _set_font(normal, "Times New Roman", "宋体", 12)
        _set_par(normal, align=WD_ALIGN_JUSTIFY, indent_pt=24, line_pt=20)

        _set_font(doc.Styles(WD_STYLE_H1), "Times New Roman", "宋体", 14, bold=True)
        _set_par(doc.Styles(WD_STYLE_H1), align=WD_ALIGN_LEFT, line_pt=20, before_pt=13, after_pt=6)
        for sid in (WD_STYLE_H2, WD_STYLE_H3):
            _set_font(doc.Styles(sid), "Times New Roman", "宋体", 12, bold=True)
            _set_par(doc.Styles(sid), align=WD_ALIGN_LEFT, line_pt=20, before_pt=8, after_pt=3)

        cap = doc.Styles(WD_STYLE_CAPTION)
        _set_font(cap, "Times New Roman", "宋体", 10.5)
        _set_par(cap, align=WD_ALIGN_CENTER, line_pt=14, before_pt=3, after_pt=3)

        code = doc.Styles(WD_STYLE_QUOTE)  # 借「引用」槽位当代码样式
        code.NameLocal = "代码"
        _set_font(code, "Consolas", "SimSun", 9)
        _set_par(code, align=WD_ALIGN_LEFT, line_pt=11)
        for edge in (-1, -2, -3, -4):     # 上/左/下/右，Typst 侧是 0.4pt 一圈框
            b = code.ParagraphFormat.Borders(edge)
            b.LineStyle = WD_BORDER_SINGLE
            b.LineWidth = 4                # 单位 1/8 pt -> 0.5pt
            b.Color = 0                    # 黑

        # 表格里的文字同样是五号（cli 渲染表格时不带样式，只能靠表样式承载）
        tstyle = doc.Styles.Add("三线表", 3)
        _set_font(tstyle, "Times New Roman", "宋体", 10.5)
        _set_par(tstyle, align=WD_ALIGN_CENTER, line_pt=12)
        for edge in (-1, -2, -3, -4, -5, -6):   # 上/左/下/右/内横/内竖
            tstyle.Table.Borders(edge).LineStyle = 0
        for edge in (-1, -2):                   # 只留上下框线
            tstyle.Table.Borders(edge).LineStyle = WD_BORDER_SINGLE
            tstyle.Table.Borders(edge).LineWidth = 8   # 1pt

        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.SaveAs2(str(out_path), FileFormat=16)   # wdFormatDocumentDefault = .docx
        doc.Close(False)
        return out_path
    finally:
        app.Quit()


if __name__ == "__main__":
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (
        Path(__file__).resolve().parents[2] / "docs/typ/word/实验三报告-样式模板.docx")
    print("模板已生成:", build_template(out))