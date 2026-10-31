# -*- coding: utf-8 -*-
"""给 cli-anything-word 渲染出的 .docx 补上它块模型表达不了的排版，再导出 PDF。

cli 的块只能设 字号/粗斜体/对齐，于是下面这些改不了，只能用 Word COM 补：
  1. 封面：行距改单倍 + 「题目/组号/时间」按 Typst 的「75pt 标签列 + 335pt 取值列」排
     （标签右缘用空格顶到 174.6、取值中心顶到 335.1），三条填空线照 Typst 的实测几何画成
     浮动直线（167.6–502.6），并用 --typ-pdf 给的 Typst 版实测纵坐标校准每一段的段前间距
  2. 表格：正文三线表（上下 1pt + 表头下 0.5pt，五号字），封面的成员表保留全网格 14pt
  3. 行内格式：正文里的 <b></b> 变粗体、<s></s> 变上标（文献引用与 R@K 的编号）、
     <c></c> 变行内代码（Consolas 9pt，对应 Typst 的 `#show raw`）；
     <k:label></k:label>（交叉引用与文献号）变指向书签的内部超链接——书签由题注/文献条目
     段首的 <a:label> 建成，这样 Word 里点「图 1」也能跳到图 1
  6. 参考文献条目：悬挂缩进 24.3pt + 12pt 行距 + 两端对齐（正文样式的 20pt 行距/24pt 首行缩进
     会让条目第一行推右、续行拉回左缘，整块高度是 Typst 的 1.7 倍）
  4. 页码：封面不编号，正文从 1 开始（不同首页页脚 + 起始编号 0）；cli 的「空段 + 手动分页符」
     改写成后一段的「段前分页」——那个空段按正文样式占一整行，会把封面挤出一整页空白页
  5. 段首漏格式：CLI 给段落直接设字号/字体时漏掉第一个字符（留在正文样式的 12pt 上）
  6. 歧义字符的字体：清掉 run 的 hint="eastAsia"，让弯引号/×/≤/—/→/± 走 Times 而非宋体；
     并把字形名统一写成中文名（SimSun→宋体、SimHei→黑体，同一字体的英文名/中文名）

只改格式，不动一个字。用法:
  python docs/scripts/refine_word_report.py <in.docx> [--out out.docx] [--pdf out.pdf]
                                          [--typ-pdf 实验三-<时间戳>.pdf]
"""
from __future__ import annotations

import argparse
import re as _re
import sys
from pathlib import Path

import win32com.client as win32

WD_BORDER_OFF, WD_BORDER_SINGLE = 0, 1
WD_ALIGN_LEFT, WD_ALIGN_CENTER = 0, 1
WD_LINE_SINGLE, WD_LINE_EXACTLY = 0, 4
WD_TAB_CENTER, WD_TAB_RIGHT = 1, 2
# 边框常量：-1 上 -2 左 -3 下 -4 右 -5 内横 -6 内竖

# ---- 封面 ----
# Typst 的封面网格（docs/typ/实验三.typ）是 `#pad(left: 92.6pt)[#grid(columns: (75pt, 335pt))]`：
# 标签列右对齐到 167.6、取值列 167.6–502.6 带 0.5pt 下框线。Word 没法把文字排到段落下框线的
# 左边，改用「左缩进 = 167.6 + 首行悬挂 75pt + 标签/取值之间用空格顶」复刻：下框线从段落左缩进
# 画起，正好只覆盖 167.6–502.6（改前是从左边距 91.1 一路通栏，标签也整行居中，与 PDF 完全不同）。
COVER_LEFT = 167.6 - 70.9        # 96.7：段落左缩进，即填空虚线的起点
LIST_LEFT = 85.87 - 70.85        # 15：列表正文列（Typst 实测 85.87），序号挂在左边距
COVER_HANG = -(167.6 - 92.6)     # -75：首行悬挂，标签从版心 92.6 起排
COVER_LABEL_X = 174.6            # 标签右缘（Typst 让「：」探出线起点 7pt）
COVER_VALUE_X = 335.1            # 取值中心（取值列 167.6–502.6 的中点）
# 位置只能用空格顶：Word 对「首行悬挂」的段落会把制表位一律跳到左缩进——实测右对齐/居中制表位
# 全被忽略（标签既不对齐、取值还被拽到左缩进上）。空格宽度实测：宋体空格 = 0.5em（10pt→4.99、
# 14pt→7.0、20pt→9.99），所以 pad/gap 写成 (空格数, 字号)，距离 = 空格数 × 0.5 × 字号。
# 西文那半套也写成宋体：Word 会把 CJK 后面的第一个空格判给西文字体（Times 0.25em = 一半宽，
# 实测 22pt 下 18 个空格 192.7pt = 5.5 + 17×11），两边同字体就没这个歧义。
# 标签右缘瞄 174.6（「题目」的「：」在 Typst 里悬挂得多，是 177.6），取值中心瞄 335.1。
# 算出来的落点见注释，残差 ≤1.0pt；线由 _cover_rules 另画。
COVER_FIELDS = {                 # 段首匹配 -> 这一行怎么排
    "题目：": dict(label="题目：", value="算法优化实验", lab_pt=20.0, val_pt=22.0,
                   line_h=20.5, pad=(6, 8), gap=(23, 8)),       # 标签右缘 176.8、取值中心 334.9
    "组    号：": dict(label="组    号：", value="23", lab_pt=14.0, val_pt=14.0,
                       line_h=13.0, pad=(3, 8), gap=(34, 9)),   # 标签右缘 174.6、取值中心 334.6
    "组员信息：": dict(label="组员信息：", value="", lab_pt=14.0, val_pt=14.0,
                       line_h=None, pad=(3, 8), gap=None),      # 标签右缘 174.6（这一行没有填空线）
    "时    间：": dict(label="时    间：", value="2026.10.25", lab_pt=14.0, val_pt=14.0,
                       line_h=13.0, pad=(3, 8), gap=(32, 8)),  # 标签右缘 174.6、取值中心 334.3
}
COVER_KEYS = ("西 安 邮 电 大 学", "AI 全栈开发实验", "题目：", "组    号：", "组员信息：",
              "时    间：")      # 只有这些前缀会命中封面行（带 4 个空格的标签在正文里不会出现）
# 固定行距的来历：Typst 的下框线画在字上沿下方 0.93em（实测 14pt 线 13.0、22pt 线 20.5），
# Word 的段落下框线画在行盒底，行距取 13.0/20.5 就能让线落回 Typst 的位置。
COVER_TABLE_KEY = "封面表"
# (段落文字前缀, 用来量纵坐标的 span 正则, 段前间距初值)；初值照 Typst 的 v(86/79.5/62.7/52/30)，
# 后面的校准会按实测改。首项减 70.9：Typst 封面 margin: 0pt，v(86) 里含了 2.5cm 上边距
COVER_ANCHORS = [
    ("西 安 邮 电 大 学", r"^西", 86 - 70.9),
    ("AI 全栈开发实验", r"^全栈开发实验", 79.5),
    ("题目：", r"^算法优化实验", 62.7),
    ("组    号：", r"^组(?!员)", 52.0),
    ("组员信息：", r"^组员", 30.0),
    # 封面表首格：表格的位置跟着「组员信息」的段后间距走，单独校（见 _fit_cover）
    (COVER_TABLE_KEY, r"^学号", 0.0),
    ("时", r"^时", 0.0),
]


def _set_inline_code(rng) -> None:
    """行内代码的字体：Typst 侧 `#show raw: set text(font: ("Consolas", "SimSun"), size: 9pt)`
    对行内 raw 同样生效，正文 12pt 里的 ``scripts/x.py`` 是 Consolas 9pt。
    East Asian 仍是宋体（行内代码里的中文，如 ``图表说明.md``，Typst 也是宋体 9pt）。"""
    f = rng.Font
    f.Name = f.NameAscii = "Consolas"
    f.NameFarEast = "SimSun"
    f.Size = 9


def _find_replace_format(doc, tag: str, apply) -> int:
    """把 <tag>…</tag> 之间的文字按 apply 设格式并去掉标记，返回处理处数。"""
    n = 0
    open_tag, close_tag = f"<{tag}>", f"</{tag}>"
    while True:
        rng = doc.Content
        if not rng.Find.Execute(FindText=open_tag, Forward=True, Wrap=1):
            break
        start_open, end_open = rng.Start, rng.End
        mid_start = end_open
        rng2 = doc.Range(end_open, doc.Content.End)
        if not rng2.Find.Execute(FindText=close_tag, Forward=True, Wrap=1):
            raise ValueError(f"{open_tag} 没有配对的 {close_tag}")
        mid_end = rng2.Start
        target = doc.Range(mid_start, mid_end)
        apply(target)
        # 先删后一个标记，再删前一个，避免偏移错位
        doc.Range(rng2.Start, rng2.End).Delete()
        doc.Range(start_open, end_open).Delete()
        n += 1
    return n


def _cover_paragraph(doc, key: str):
    """按文字前缀找封面段落。跳过表格里的段落——「时间」那一行在封面成员表**后面**，
    所以不能「遇到表格就停」。封面这几行的前缀（含 4 个空格）在正文里不会出现。"""
    for i in range(1, doc.Paragraphs.Count + 1):
        par = doc.Paragraphs(i)
        if par.Range.Information(12):          # wdWithInTable
            continue
        if par.Range.Text.lstrip().startswith(key):
            return par
    return None


def _cover_grid(par) -> None:
    """标签列：首行悬挂到版心 92.6、左缩进落在填空虚线的起点 167.6。
    必须同时改成左对齐——模板给封面段落的是居中，居中时整行会飘到版心中间去。"""
    pf = par.Format
    pf.FirstLineIndent, pf.LeftIndent, pf.RightIndent = COVER_HANG, COVER_LEFT, 23.4
    pf.Alignment = WD_ALIGN_LEFT


def _cover_field(doc, par, spec: dict) -> None:
    """把「题目/组号/组员信息/时间」排成 Typst 的网格：标签右缘对到 174.6、取值中心对到 335.1。

    这里只管文字，下框线交给 _cover_rules：Word 的段落下框线只能铺满「左缩进→右缩进」，
    而标签必须排在线左边（得用首行悬挂），Word 会把悬挂那段也一起铺上——实测线从 91.1 画到
    502.6，一半压在标签下面，跟 Typst 的 167.6–502.6 完全不是一回事。
    """
    _cover_grid(par)
    pf = par.Format
    pf.Borders(-3).LineStyle = WD_BORDER_OFF    # -3 = 下框线
    if spec["line_h"]:
        pf.LineSpacingRule, pf.LineSpacing = WD_LINE_EXACTLY, spec["line_h"]
    pad_n, pad_pt = spec["pad"]
    gap_n, gap_pt = spec["gap"] or (0, 14)
    label, value = spec["label"], spec["value"]
    # 重写整段文字：CLI 把「标签+取值」当成一整串居中排，这里按算好的空格数拆开定位
    rng = doc.Range(par.Range.Start, par.Range.End - 1)
    rng.Text = " " * pad_n + label + " " * gap_n + value
    rng.Font.Bold = True
    rng.Font.Size, rng.Font.Name, rng.Font.NameFarEast = spec["lab_pt"], "SimSun", "SimSun"
    i0 = par.Range.Start
    i_pad, i_lab = i0 + pad_n, i0 + pad_n + len(label)
    doc.Range(i0, i_pad).Font.Size = pad_pt            # 段首定位空格（宋体 0.5em）
    doc.Range(i_lab, i_lab + gap_n).Font.Size = gap_pt  # 标签与取值之间的定位空格
    # 取值：数字走 Times，汉字仍归东亚字体（SimSun），与 Typst 的字体表一致
    val = doc.Range(i_lab + gap_n, par.Range.End - 1)
    val.Font.Size, val.Font.Name = spec["val_pt"], "Times New Roman"


def _typ_rules(pdf: Path) -> list[tuple[float, float, float]]:
    """Typst 封面那三条填空线的 (x0, x1, 线心 y)。封面表的横线 x0≈92.4，用 x0>150 排掉。"""
    import fitz
    page = fitz.open(str(pdf))[0]
    rules = []
    for dr in page.get_drawings():
        r = dr["rect"]
        if r.height < 1.0 and r.width > 300 and r.x0 > 150:
            rules.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
    return sorted(rules, key=lambda t: t[2])


def _cover_rules(doc, typ_pdf: Path) -> int:
    """封面三条填空线：照 Typst 的实测几何画成浮动直线（167.6→502.6、0.5pt）。

    为什么不画成段落下框线：见 _cover_field 的说明——悬挂缩进会把线一并铺到标签底下。
    浮动线不占文字流高度（封面正卡在版心底线 771pt，多一个 1pt 空段就会被挤到下一页），
    坐标按页面算、锚在「题目」那段上，所以纵坐标校准怎么挪段落，线都钉在 Typst 的位置上。
    """
    n = 0
    for x0, x1, y in _typ_rules(typ_pdf):
        par = _cover_paragraph(doc, "题目：")
        par.Range.Select()                     # AddLine 锚在当前选区所在段落
        sh = doc.Shapes.AddLine(x0, y, x1, y)
        sh.RelativeHorizontalPosition = 1      # wdRelativeHorizontalPositionPage
        sh.RelativeVerticalPosition = 1        # wdRelativeVerticalPositionPage
        sh.Left, sh.Top, sh.Width = x0, y - 0.25, x1 - x0
        sh.WrapFormat.Type = 3                 # wdWrapNone：不推文字
        sh.LockAnchor = True
        sh.Line.Weight = 0.5
        sh.Line.ForeColor.RGB = 0
        n += 1
    return n


def _cover_anchors(pdf: Path) -> dict[str, float]:
    """量封面六个锚点 span 的上沿。两边都是同字形同字号，纵坐标可直接比。"""
    import fitz
    page = fitz.open(str(pdf))[0]
    ys: dict[str, list[float]] = {key: [] for key, _, _ in COVER_ANCHORS}
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                t = span["text"].lstrip()
                for key, pat, _ in COVER_ANCHORS:
                    if _re.match(pat, t):
                        ys[key].append(span["bbox"][1])
    return {k: min(v) for k, v in ys.items() if v}


def _fit_cover(doc, typ_pdf: Path, probe: Path) -> list[tuple[str, float, float]]:
    """按 Typst 的封面实测纵坐标校准每段的段前间距，返回 [(项, 目标 y, 实际 y)]。

    根因：封面段落只被设了字号，行距仍继承正文样式的「固定值 20 磅」——26pt / 22pt 的字被塞进
    20pt 行盒，行高比 Typst 小十来磅，于是每往下一项就往上涨一点，到封面表时已差 32pt。
    行距已在 _cover 里改回单倍，这里再逐项量着校准（改行距会改变行高，故要迭代两三次）。
    """
    targets = _cover_anchors(typ_pdf)
    errs: dict[str, float] = {}
    for it in range(4):
        doc.Repaginate()
        doc.ExportAsFixedFormat(str(probe), 17)
        got = _cover_anchors(probe)
        errs = {k: got[k] - targets[k] for k in targets if k in got}    # 正 = 偏下
        print(f"  封面校准 {it + 1}：{' '.join(f'{k}{e:+.1f}' for k, e in errs.items())}",
              flush=True)
        if max((abs(e) for e in errs.values()), default=0) < 0.5:
            break
        up = 0.0
        for key, _, _ in COVER_ANCHORS:        # 顺序即版面顺序：改前一段会带着后面所有段一起走
            if key not in errs:
                continue
            need = errs[key] - up              # 这一项还要再往上抬多少
            # 封面表那一项调的是「组员信息」的段后间距：表格跟着它走，动它不会挪「组员信息」自己
            par = _cover_paragraph(doc, "组员信息：" if key == COVER_TABLE_KEY else key)
            if par is None:
                continue
            pf = par.Format
            if key == COVER_TABLE_KEY:
                old = pf.SpaceAfter
                pf.SpaceAfter = max(0.0, old - need)
                up += old - pf.SpaceAfter          # 只累计真正生效的位移（夹到 0 就没有了）
            else:
                old = pf.SpaceBefore
                pf.SpaceBefore = max(0.0, old - need)
                up += old - pf.SpaceBefore
    # 没量到的（多半是被挤到第 2 页去了）返回 None，别当成 0 残差
    return [(k, targets[k], targets[k] + errs[k] if k in errs else None) for k in targets]


def _cover(doc) -> int:
    """封面：行距改单倍 + 「题目/组号/组员信息/时间」排成 Typst 的标签/取值网格。"""
    n = 0
    for i in range(1, doc.Paragraphs.Count + 1):
        par = doc.Paragraphs(i)
        if par.Range.Information(12):          # 表格里的段落（封面成员表、正文表）都不碰
            continue
        text = par.Range.Text.lstrip()
        if not text.startswith(COVER_KEYS):    # 只认封面这六行，正文段落一律不动
            continue
        pf = par.Format
        # 正文样式是「固定行距 20 磅」，封面的 26pt/22pt 大字号行会被压扁成 20pt 的行盒
        pf.LineSpacingRule = WD_LINE_SINGLE
        is_field = False
        for key, spec in COVER_FIELDS.items():
            if text.startswith(key):
                _cover_field(doc, par, spec)
                is_field = True
                n += 1
                if key == "组员信息：":
                    pf.SpaceAfter = 2          # 封面表紧跟这一行，段后间距是它的位置旋钮
        if not is_field:
            pf.FirstLineIndent = 0             # 正文样式的 24pt 首行缩进会把这些居中行顶偏
            if text.startswith("AI 全栈开发实验"):
                # 模板：'AI' 用 Times New Roman、其余中文用黑体（Normal 是宋体，这里补上）
                par.Range.Font.NameFarEast = "黑体"
        for key, _, before in COVER_ANCHORS:
            if text.startswith(key):
                pf.SpaceBefore = before
                break
    return n


def _strip_east_asian_hint(docx: Path) -> tuple[int, int]:
    """直接改 docx 的 XML：删 `w:hint="eastAsia"`，并把字形名写成中文名。返回 (hint 数, 改名数)。

    hint：CLI 给每个 run 都写了 hint="eastAsia"，Word 于是把「东亚与西文两套字体都覆盖」的
    歧义字符按东亚字体（宋体）排：弯引号 “ ”、×、≤、≥、—、→、±。Typst 的字体表是
    ("Times New Roman", "SimSun")，这些字符都先命中 Times——实测两边 119 个字符字体族不一致。
    删掉 hint 后歧义字符走 hAnsi（Times），与 Typst 一致；汉字本就归东亚字体，不受影响。

    字体名：SimSun/SimHei 是 simsun.ttc / simhei.ttf 里的英文名（name 表 langID 1033），
    同一个文件的 langID 2052 就是「宋体」「黑体」。Word 两套写法都认、界面也回显中文名，
    这里统一写成中文名，方便人看文件、也方便用中文名 grep。只改 rFonts 的字体属性值。
    """
    import re as _re
    import shutil
    import zipfile

    alias = {"SimSun": "宋体", "SimHei": "黑体"}
    fonts = _re.compile(r'(w:(?:ascii|hAnsi|eastAsia|cs)=")(SimSun|SimHei)(")')

    tmp = docx.with_name(docx.stem + ".tmp.docx")
    n_hint = n_alias = 0
    with zipfile.ZipFile(docx) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                text = data.decode("utf-8")
                n_hint += text.count(' w:hint="eastAsia"')
                text = text.replace(' w:hint="eastAsia"', "")
                text, n = fonts.subn(lambda m: m.group(1) + alias[m.group(2)] + m.group(3), text)
                n_alias += n
                data = text.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(str(tmp), str(docx))
    return n_hint, n_alias


ANCHOR_RE = _re.compile(r"^<a:([A-Za-z0-9-]+)>")
REF_RE = _re.compile(r"<k:([A-Za-z0-9-]+)>(.*?)</k:\1>")
BIB_RE = _re.compile(r"^\[(\d+)\]\s")


def _bookmark(label: str) -> str:
    """书签名：Word 只允许字母/数字/下划线，且不能是 R1C1 这种单元格引用。"""
    return "ref_" + label.replace("-", "_")


BIB_INDENT = 24.3      # Typst 侧 gb-7714-2015-numeric 的悬挂缩进：正文列在 95.2pt（版心左缘 70.9 + 24.3）
BIB_LEADING = 12.0     # Typst 侧每行 12.0pt（`#set par(leading: 5pt)` 的实际行距，实测 pitch 12.0）


def _set_bib_entry(par) -> None:
    """参考文献条目的段落格式：标签顶到版心左缘、正文列悬挂缩进 24.3pt、行距 12pt、两端对齐。

    条目段落是 CLI 直接给字号 10.5pt 的普通段落，其余仍继承正文样式：20pt 固定行距 + 24pt
    首行缩进。结果是每条文献的第一行被推右、续行又拉回版心左缘（正好和 Typst 相反），行距也
    是 Typst 的 1.67 倍——12 条文献占 584pt 而不是 336pt，看上去像每条都断成了好几段。
    """
    pf = par.Format
    pf.LeftIndent = BIB_INDENT
    pf.FirstLineIndent = -BIB_INDENT
    pf.LineSpacingRule = 4          # wdLineSpaceExactly
    pf.LineSpacing = BIB_LEADING
    pf.SpaceBefore = pf.SpaceAfter = 0
    pf.Alignment = 3                # wdAlignParagraphJustify，与 Typst 的 par(justify: true) 一致


def _cross_refs(doc) -> tuple[int, int]:
    """交叉引用做成 Word 内部超链接，返回 (书签数, 链接数)。

    Typst 里 @fig/@tbl/@lst 与 @cite 都是可点的（导出的 PDF 有 46 个内部链接），
    CLI 渲染出来只是纯文字。Word 只有「书签 + 指向书签的超链接」这一条路。
    """
    n_bm = n_lk = 0
    # 第一遍：书签。正文里的引用可能出现在被引对象之前（“见表 1”在表 1 之前），必须全部先建好
    for i in range(1, doc.Paragraphs.Count + 1):
        par = doc.Paragraphs(i)
        m = ANCHOR_RE.match(par.Range.Text)
        bib = BIB_RE.match(par.Range.Text)
        if bib:
            # 文献条目靠 [n] 前缀认（不用锚点标记：CLI 会把标记在 '<' 处拆成两个 run，
            # 跨 run 删标记后 Word 会在空 run 里补一个删不掉空格）
            _set_bib_entry(par)
            name = f"ref_bib_{bib.group(1)}"
        elif m:
            name = _bookmark(m.group(1))
        else:
            continue
        if not doc.Bookmarks.Exists(name):
            doc.Bookmarks.Add(name, doc.Range(par.Range.Start, par.Range.Start))
            n_bm += 1
        if m:
            doc.Range(par.Range.Start, par.Range.Start + m.end()).Delete()   # 去掉锚点标记
    # 第二遍：引用文字变超链接
    for i in range(1, doc.Paragraphs.Count + 1):
        par = doc.Paragraphs(i)
        text = par.Range.Text
        base = par.Range.Start
        for m in reversed(list(REF_RE.finditer(text))):     # 从后往前，删标记不影响前面的偏移
            label = m.group(1)
            name = _bookmark(label)
            if not doc.Bookmarks.Exists(name):
                continue
            head, tail = len(f"<k:{label}>"), len(f"</k:{label}>")
            rng = doc.Range(base + m.start(), base + m.end())
            inner = doc.Range(rng.Start + head, rng.End - tail)
            sup = inner.Font.Superscript
            # 先删标记再建链接：标记挨着超链接域时 Word 会拒删（“无法编辑 Range”），
            # 而且域一旦建立，Range 边界会扩到域码里
            doc.Range(inner.End, inner.End + tail).Delete()      # 先尾后头，Range 是活对象会自动跟
            doc.Range(inner.Start - head, inner.Start).Delete()
            doc.Hyperlinks.Add(inner, "", name)
            # 超链接默认套 Hyperlink 字符样式（蓝 + 下划线），刷回正文的黑色无下划线；
            # 文献号是上标，Add 之后上标会被字符样式冲掉，按原值补回
            inner.Font.Underline = 0
            inner.Font.Color = 0
            if sup:
                inner.Font.Superscript = sup
            n_lk += 1
    return n_bm, n_lk


def refine(doc_path: Path, out_path: Path, pdf_path: Path | None,
           typ_pdf: Path | None = None) -> None:
    app = win32.DispatchEx("Word.Application")
    app.Visible = False
    app.DisplayAlerts = 0
    probe = out_path.with_name(out_path.stem + "-封面校准.pdf") if pdf_path else None
    try:
        doc = app.Documents.Open(str(doc_path))

        # 1) 封面：行距、标签/取值网格、填空线（纵坐标校准放到最后，等表格与空段都压紧了再量）
        n_cov = _cover(doc)

        # 1.5) 编号列表：cli 把列表段落的左缩进设成 900 twips（45pt），正文列因此比 Typst 窄
        #      30pt——Typst 的列表是「序号挂在左边距（70.9）、正文从 85.9 起」，续行也落在 85.9。
        #      按 Typst 的实测几何改回去（左缩进 15pt + 悬挂 15pt = 序号 70.9、正文 85.9）。
        n_list = 0
        for i in range(1, doc.Paragraphs.Count + 1):
            par = doc.Paragraphs(i)
            if par.Range.Information(12) or not par.Range.ListFormat.ListString:
                continue                           # 只认带序号的列表段（表格里的不碰）
            pf = par.Format
            pf.LeftIndent, pf.FirstLineIndent = LIST_LEFT, -LIST_LEFT
            n_list += 1

        # 2) 表格
        cover_done = False
        for ti in range(1, doc.Tables.Count + 1):
            tb = doc.Tables(ti)
            # 单元格会继承正文样式的首行缩进，Typst 的表格没有——不归零会少一个字的宽度而多折一行
            tb.Range.ParagraphFormat.FirstLineIndent = 0
            tb.Range.ParagraphFormat.LeftIndent = 0
            is_cover = not cover_done and tb.Rows.Count == 7 and tb.Columns.Count == 3
            if is_cover:
                cover_done = True
                for edge in (-1, -2, -3, -4, -5, -6):
                    b = tb.Borders(edge)
                    b.LineStyle = WD_BORDER_SINGLE
                    b.LineWidth = 4
                    b.Color = 0
                tb.Range.Font.Size = 14
                tb.Range.ParagraphFormat.Alignment = WD_ALIGN_CENTER
                tb.Rows(1).Range.Font.Bold = True
                # Typst 封面表的学号列也是粗体（`[#text(stroke: faux-bold, weight: "bold")[2610321101]]`），
                # 中文表头因为伪粗体不带粗体位，只有学号这列能靠字体族比对发现
                for ri in range(1, tb.Rows.Count + 1):
                    tb.Cell(ri, 1).Range.Font.Bold = True
                # 列宽与单元格内边距照抄 Typst（112/99/198.5pt、inset x=5pt）：
                # 不固定列宽时 Word 自动分配，分工列偏窄会多折出一行，整张表就顶出版心
                tb.AutoFitBehavior(0)                      # wdAutoFitFixed
                for ci, width in enumerate((112, 99, 198.5), start=1):
                    tb.Columns(ci).Width = width
                # Typst 的封面表单元格行距是 13.6pt（14pt 字只占 13.6pt 行高）、inset y=10.5。
                # Word 侧单元格继承正文样式的固定 20pt 行距，两行格就比 Typst 高 7pt、整表高 24pt
                # → 整表顶到封面底部。改成固定 13.5pt + 内边距 8.55pt 后逐行对齐
                # （1 行 30.6 / 2 行 44.1，实测差 ≤0.5pt）。
                tpf = tb.Range.ParagraphFormat
                tpf.LineSpacingRule, tpf.LineSpacing = WD_LINE_EXACTLY, 13.5
                # 8.3 = 反推出 Typst 的 30.6/44.1 行高（再减去 Word 自己加的 0.5pt 边框）
                tb.TopPadding = tb.BottomPadding = 8.3
                # Typst 的 inset x=5pt 靠「标点悬挂」把「（ONNX、」留在行尾；Word 不悬挂，
                # 5pt 内边距会让「模型导出与推理测量（ONNX、ORT/TRT 测速、FLOPs）」多折一行 →
                # 内边距归零把内容区还原成整列宽（实测该格折行数与 Typst 一致）
                tb.LeftPadding = tb.RightPadding = 0
                tb.Rows.LeftIndent = 21.7                  # Typst 把封面表左缩进到 92.6pt（版心 70.9 + 21.7）
                tb.Rows.AllowBreakAcrossPages = False
                continue
            for edge in (-1, -2, -3, -4, -5, -6):
                tb.Borders(edge).LineStyle = WD_BORDER_OFF
            for edge, width in ((-1, 8), (-3, 8)):      # 上下框 1pt
                b = tb.Borders(edge)
                b.LineStyle = WD_BORDER_SINGLE
                b.LineWidth = width
                b.Color = 0
            hb = tb.Rows(1).Borders(-3)                 # 表头下 0.5pt
            hb.LineStyle = WD_BORDER_SINGLE
            hb.LineWidth = 4
            hb.Color = 0
            tb.Range.Font.Size = 10.5
            tb.Range.ParagraphFormat.SpaceBefore = 2
            tb.Range.ParagraphFormat.SpaceAfter = 2
            # 正文三线表的表头在 Typst 侧是常规字重（`t5()` 只设了 10.5pt，表头格没包 strong），
            # 而 CLI 渲染时把 header 行加粗了（project JSON 里的 "header": true），抹平它
            tb.Rows(1).Range.Font.Bold = False

        # 2.2) 图片段落：正文样式是「固定行距 20 磅 + 首行缩进 24pt」，内嵌图会因此被压成一条
        #      20pt 高的细条（字全盖在图上），还整体右移 24pt 顶出版心右缘。
        #      图片段落改成单倍行距、去缩进，并与题注同页（Typst 侧是 block(breakable: false)）。
        n_img = 0
        for i in range(1, doc.InlineShapes.Count + 1):
            shape = doc.InlineShapes(i)
            par = shape.Range.Paragraphs(1)
            par.Format.FirstLineIndent = 0
            par.Format.LeftIndent = 0
            par.Format.RightIndent = 0
            par.Format.LineSpacingRule = 0         # wdLineSpaceSingle：行高随图高
            par.Format.SpaceBefore = par.Format.SpaceAfter = 0
            par.Format.KeepWithNext = True         # 图与题注不拆页
            n_img += 1

        # 2.5) cli 每张表后都补了一个空段（Word 需要表后有空段，否则表会吃掉下一段），
        #      它按正文字号占掉一整行 20pt：封面那张会把「时间：」挤到第 2 页，正文里也把
        #      图表题注推低。压到 1pt 单倍行距，只留一个段落标记。
        n_tight = 0
        for i in range(doc.Paragraphs.Count, 1, -1):
            par = doc.Paragraphs(i)
            if par.Range.Text.strip() or par.Range.Information(12):    # 空段且不在表格内
                continue
            if not doc.Paragraphs(i - 1).Range.Information(12):         # 前一段要在表格里
                continue
            par.Range.Font.Size = 1
            par.Format.LineSpacingRule = 0                              # wdLineSpaceSingle
            par.Format.SpaceBefore = par.Format.SpaceAfter = 0
            n_tight += 1

        # 3) 行内格式：行内代码、粗体、上标。行内代码先做：它在正文里是 Consolas 9pt，
        #    若留到第 5 步之后再改，段首字符的比对照样成立，但标记还在时按字符位置比对更稳。
        n_code = _find_replace_format(doc, "c", _set_inline_code)
        n_bold = _find_replace_format(doc, "b", lambda r: setattr(r.Font, "Bold", -1))
        n_sup = _find_replace_format(doc, "s", lambda r: setattr(r.Font, "Superscript", -1))
        # 3.5) 交叉引用：必须在 <s> 之后（文献号要先成为上标，建链接时要保住这个状态）
        n_bm, n_lk = _cross_refs(doc)

        # 4) 页码：封面不编号，正文从 1 起
        sec = doc.Sections(1)
        sec.PageSetup.DifferentFirstPageHeaderFooter = True
        sec.Footers(1).PageNumbers.RestartNumberingAtSection = True
        sec.Footers(1).PageNumbers.StartingNumber = 0
        # 渲染出来的页眉默认带一条通栏下框线（Typst 没有页眉，自然也没有这条线），清掉；
        # 页脚一并清，免得页码上方多一条横线
        for i in (1, 2, 3):                        # 主页眉/首页页眉/偶数页页眉
            rng = sec.Headers(i).Range
            for pi in range(1, rng.Paragraphs.Count + 1):
                for edge in (-1, -2, -3, -4):
                    rng.Paragraphs(pi).Format.Borders(edge).LineStyle = WD_BORDER_OFF
        for i in (1, 2, 3):
            rng = sec.Footers(i).Range
            for pi in range(1, rng.Paragraphs.Count + 1):
                for edge in (-1, -2, -3, -4):
                    rng.Paragraphs(pi).Format.Borders(edge).LineStyle = WD_BORDER_OFF

        # 4.5) 分页符：cli 用「空段 + 手动分页符」分页，这个空段按正文样式要占掉一整行 20pt，
        #      而封面正好排到版心底线（771pt）附近，于是它被挤到下一页，白多一张只有页脚的空页，
        #      正文页码也跟着整体后移。改成 Word 原生的「段前分页」：把分页符空段删掉，在它后面
        #      那一段上设 PageBreakBefore。空段里没有一个字，正文一个字都没动。
        n_brk = 0
        for i in range(doc.Paragraphs.Count, 1, -1):
            par = doc.Paragraphs(i)
            if par.Range.Information(12) or "\f" not in par.Range.Text:
                continue
            if par.Range.Text.strip() or i >= doc.Paragraphs.Count:  # 只认「整段就一个分页符」
                continue
            doc.Paragraphs(i + 1).Format.PageBreakBefore = True
            par.Range.Delete()
            n_brk += 1

        # 5) cli 给段落直接设字号/字体时漏掉了第一个字符（它留在正文样式的 12pt 上），
        #    表现是段首一个字明显偏小（封面「西 安 邮 电 大 学」的「西」只有 12pt）。
        #    逐段比对首字符与第二字符的字号/字体，不一致就照第二个字符刷过去。
        #    只比字号和字体族，不碰粗体/上标——那是行内标记有意区分的（如加粗的 R\@1）。
        n_head = 0
        for i in range(1, doc.Paragraphs.Count + 1):
            rng = doc.Paragraphs(i).Range
            if rng.End - rng.Start < 2:
                continue
            a = doc.Range(rng.Start, rng.Start + 1).Font
            b = doc.Range(rng.Start + 1, rng.Start + 2).Font
            if (a.Size, a.Name, a.NameFarEast) != (b.Size, b.Name, b.NameFarEast):
                a.Size, a.Name, a.NameFarEast = b.Size, b.Name, b.NameFarEast
                n_head += 1
            # 粗体位漏掉同理（封面「AI 全栈开发实验」的 A 只有 Times 常规体，I 是粗体）。
            # 只在「第二字符粗、第一字符不粗」时补：反过来是行内 <b> 标记，不能反向抹平。
            if b.Bold and not a.Bold:
                a.Bold = True
                n_head += 1

        # 5.5) 封面纵坐标校准：表格行高、表后空段的压缩都会改变封面各段的实际位置，
        #      所以放到这里（所有影响版面的改动都做完之后）按 Typst 的实测值对齐。
        cov_msg = ""
        n_cov_line = _cover_rules(doc, typ_pdf) if typ_pdf is not None else 0
        if typ_pdf is not None and probe is not None:
            fits = _fit_cover(doc, typ_pdf, probe)
            got = [(k, t, g) for k, t, g in fits if g is not None]
            worst = max((abs(g - t) for _, t, g in got), default=0.0)
            cov_msg = f"封面校准 {len(got)}/{len(fits)} 项，最大残差 {worst:.1f}pt：" + \
                      " ".join(f"{k}{g - t:+.1f}" if g is not None else f"{k}(第 1 页没有)"
                               for k, t, g in fits)

        doc.SaveAs2(str(out_path), FileFormat=16)
        doc.Close(False)

        # 6) 歧义字符的字体与字体名：改 docx 里的 XML（Word COM 没有对应属性），必须在保存之后做，
        #    且做完要重新打开再导 PDF——Word 一保存就按自己的模型把 hint 与英文名写回去。
        n_hint, n_alias = _strip_east_asian_hint(out_path)
        doc = app.Documents.Open(str(out_path))
        if pdf_path:
            doc.ExportAsFixedFormat(str(pdf_path), 17)
        pages = doc.ComputeStatistics(2)      # wdStatisticPages
        words = doc.ComputeStatistics(0)
        doc.Close(False)
        print(f"格式补齐：行内代码 {n_code} 处、粗体 {n_bold} 处、上标 {n_sup} 处、"
              f"表后空段压紧 {n_tight} 处、分页符改段前分页 {n_brk} 处、列表缩进 {n_list} 处、"
              f"段首字号 {n_head} 处、"
              f"封面填空 {n_cov} 处、封面填空线 {n_cov_line} 条、"
              f"交叉引用书签 {n_bm} / 链接 {n_lk} 处、歧义字符 hint {n_hint} 处、"
              f"字体中文名 {n_alias} 处；"
              f"{'（含封面成员表）' if cover_done else ''}")
        print(f"输出 {out_path}（{pages} 页、{words} 字）" + (f"；PDF {pdf_path}" if pdf_path else ""))
        if cov_msg:
            print("封面：" + cov_msg)
    finally:
        try:
            app.Quit()
        except Exception as exc:               # Word 忙时 Quit 拿不到对象；别让它盖住真正的错
            print(f"注意：Word 未能正常退出（{exc.__class__.__name__}），可能有后台进程残留",
                  file=sys.stderr)
        if probe and probe.exists():
            probe.unlink()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--out", default=None)
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--typ-pdf", default=None, help="Typst 版 PDF：给了就按它的封面实测纵坐标校准")
    args = ap.parse_args()
    src = Path(args.docx).resolve()          # Word 按自己的 cwd 解析相对路径，必须先绝对化
    refine(src, Path(args.out).resolve() if args.out else src,
           Path(args.pdf).resolve() if args.pdf else None,
           Path(args.typ_pdf).resolve() if args.typ_pdf else None)
    sys.exit(0)