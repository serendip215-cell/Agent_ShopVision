# -*- coding: utf-8 -*-
"""重构 ShopVision 期末答辩 PPT（19 页精简易懂版，保留专有名词，严格对齐五份实验报告）。

用法：
    python docs/scripts/ppt/build_ppt.py
输出：
    docs/交付材料/期末_第23组/03_开发介绍视频与PPT/项目开发介绍_第23组.pptx
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[3]
FIGS5 = ROOT / "docs" / "typ" / "figs_exp5"
FIGS = ROOT / "docs" / "typ" / "figs"
FIGURES = ROOT / "docs" / "typ" / "figures"
ASSETS = Path(__file__).resolve().parent / "assets"
OUT_PPTX = ROOT / "docs" / "交付材料" / "期末_第23组" / "03_开发介绍视频与PPT" / "项目开发介绍_第23组.pptx"

# ===== ShopVision 品牌视觉色板（与前端 UI、新版极简海报 100% 统一） =====
C_DEEP = RGBColor(0x10, 0x26, 0x2A)       # 深海墨青
C_DEEP2 = RGBColor(0x18, 0x38, 0x3E)      # 浅一级深青
C_DEEP3 = RGBColor(0x21, 0x48, 0x4F)      # 深底细边
C_CANVAS = RGBColor(0xF5, 0xF7, 0xF7)     # 温润纸瓷白
C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
C_TEAL = RGBColor(0x22, 0x60, 0x68)       # 品牌主瓷青
C_TEAL_SOFT = RGBColor(0xE8, 0xF3, 0xF4)  # 浅瓷青底
C_WARM = RGBColor(0xB0, 0x62, 0x39)       # 暖陶土强调
C_WARM_LIGHT = RGBColor(0xD4, 0x88, 0x5C) # 暖杏点睛
C_WARM_SOFT = RGBColor(0xFB, 0xF1, 0xEA)  # 浅暖杏底
C_TEXT = RGBColor(0x24, 0x30, 0x36)       # 正文炭黑
C_MUTED = RGBColor(0x5A, 0x68, 0x70)      # 次级灰
C_LIGHT_TXT = RGBColor(0xD3, 0xE6, 0xE8)  # 深底浅字
C_LINE = RGBColor(0xD4, 0xDF, 0xE2)       # 极细分割线

FONT_ZH = "Microsoft YaHei"
FONT_MONO = "Consolas"
TOTAL_SLIDES = 19


def set_slide_bg(slide, color: RGBColor):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def set_shape_no_line(shape):
    shape.line.fill.background()


def set_shape_border(shape, color: RGBColor, width_pt: float = 0.85):
    shape.line.color.rgb = color
    shape.line.width = Pt(width_pt)


def add_rect(slide, x, y, w, h, fill: RGBColor, border: RGBColor | None = None,
             radius: float | None = None, border_pt: float = 0.85):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius is not None else MSO_SHAPE.RECTANGLE
    shp = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius is not None:
        shp.adjustments[0] = radius
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if border is not None:
        set_shape_border(shp, border, border_pt)
    else:
        set_shape_no_line(shp)
    return shp


def add_oval(slide, x, y, w, h, fill: RGBColor):
    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    set_shape_no_line(shp)
    return shp


def add_text(slide, x, y, w, h, text: str, size: float = 14, bold: bool = False,
             color: RGBColor = C_TEXT, align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP,
             font_name: str = FONT_ZH, line_spacing: float = 1.25, italic: bool = False):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = valign
    tf.margin_left = Inches(0.04)
    tf.margin_right = Inches(0.04)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = line_spacing
    run = p.add_run()
    run.text = text
    run.font.name = font_name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return tb


def add_bullets(slide, x, y, w, h, items: list[tuple[str, str] | str], size: float = 13.5,
                color: RGBColor = C_TEXT, lead_color: RGBColor = C_DEEP,
                bullet_color: RGBColor = C_TEAL, spacing: float = 6.5, line_spacing: float = 1.28):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.04)
    tf.margin_right = Inches(0.04)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    for idx, item in enumerate(items):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.space_after = Pt(spacing)
        p.line_spacing = line_spacing

        r_dot = p.add_run()
        r_dot.text = "▪  "
        r_dot.font.name = FONT_ZH
        r_dot.font.size = Pt(size)
        r_dot.font.bold = True
        r_dot.font.color.rgb = bullet_color

        if isinstance(item, tuple):
            lead, body = item
            r1 = p.add_run()
            r1.text = lead
            r1.font.name = FONT_ZH
            r1.font.size = Pt(size)
            r1.font.bold = True
            r1.font.color.rgb = lead_color

            r2 = p.add_run()
            r2.text = body
            r2.font.name = FONT_ZH
            r2.font.size = Pt(size)
            r2.font.color.rgb = color
        else:
            r1 = p.add_run()
            r1.text = item
            r1.font.name = FONT_ZH
            r1.font.size = Pt(size)
            r1.font.color.rgb = color
    return tb


def add_img_fit(slide, img_path: Path, x: float, y: float, max_w: float, max_h: float,
                bg_card: bool = True, caption: str | None = None, cap_size: float = 10.5):
    cap_h = 0.28 if caption else 0.0
    pad = 0.08 if bg_card else 0.0
    if bg_card:
        add_rect(slide, x, y, max_w, max_h, C_WHITE, border=C_LINE, radius=0.04, border_pt=0.75)

    avail_w = max_w - 2 * pad
    avail_h = max_h - cap_h - 2 * pad
    with Image.open(img_path) as im:
        iw, ih = im.size
    ratio = min(avail_w / iw, avail_h / ih)
    dw = iw * ratio
    dh = ih * ratio
    ix = x + pad + (avail_w - dw) / 2
    iy = y + pad + (avail_h - dh) / 2
    slide.shapes.add_picture(str(img_path), Inches(ix), Inches(iy), width=Inches(dw), height=Inches(dh))

    if caption:
        add_text(slide, x + 0.08, y + max_h - cap_h - 0.02, max_w - 0.16, cap_h,
                 caption, size=cap_size, color=C_MUTED, align=PP_ALIGN.CENTER,
                 valign=MSO_ANCHOR.MIDDLE, italic=True)


def add_kpi_card(slide, x, y, w, h, value: str, label: str, sub: str = "",
                 accent: RGBColor = C_TEAL, val_size: float = 28):
    add_rect(slide, x, y, w, h, C_WHITE, border=C_LINE, radius=0.06, border_pt=0.8)
    add_rect(slide, x + 0.06, y, w - 0.12, 0.055, accent)
    add_text(slide, x + 0.10, y + 0.13, w - 0.20, 0.50, value,
             size=val_size, bold=True, color=accent if accent == C_WARM else C_DEEP,
             align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
    add_text(slide, x + 0.08, y + 0.64, w - 0.16, 0.28, label,
             size=12.8, bold=True, color=C_TEXT, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
    if sub:
        add_text(slide, x + 0.08, y + 0.92, w - 0.16, h - 0.98, sub,
                 size=10.5, color=C_MUTED, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.TOP, line_spacing=1.22)


def add_header_footer(slide, slide_num: int, eyebrow: str, title: str):
    set_slide_bg(slide, C_CANVAS)
    add_rect(slide, 0, 0, 13.333, 0.06, C_TEAL)
    add_text(slide, 0.60, 0.24, 9.0, 0.26, eyebrow, size=10.5, bold=True,
             color=C_TEAL, font_name=FONT_MONO)
    add_text(slide, 0.60, 0.48, 12.1, 0.52, title, size=25.5, bold=True, color=C_DEEP)
    add_rect(slide, 0.60, 1.04, 12.133, 0.015, C_LINE)
    add_rect(slide, 0.60, 7.05, 12.133, 0.012, C_LINE)
    add_text(slide, 0.60, 7.10, 6.0, 0.28, "ShopVision · 第 23 组项目开发介绍（实验一 → 实验五）",
             size=10, color=C_MUTED)
    add_text(slide, 11.4, 7.10, 1.33, 0.28, f"{slide_num:02d} / {TOTAL_SLIDES:02d}",
             size=10, bold=True, color=C_TEAL, align=PP_ALIGN.RIGHT, font_name=FONT_MONO)


def add_section_divider(prs, slide_num: int, sec_no: str, title: str, subtitle: str,
                        bullets: list[tuple[str, str]], notes: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, C_DEEP)
    add_oval(slide, 9.6, -1.6, 5.4, 5.4, C_DEEP2)
    add_oval(slide, -1.5, 5.2, 3.6, 3.6, C_DEEP2)
    add_rect(slide, 0.72, 1.05, 0.90, 0.06, C_WARM_LIGHT)

    add_text(slide, 0.72, 1.22, 3.0, 0.90, sec_no, size=56, bold=True,
             color=C_WARM_LIGHT, font_name=FONT_MONO)
    add_text(slide, 0.72, 2.20, 11.8, 0.68, title, size=36, bold=True, color=C_WHITE)
    add_text(slide, 0.72, 2.94, 11.2, 0.42, subtitle, size=17, color=C_LIGHT_TXT)

    add_rect(slide, 0.72, 3.62, 11.88, 2.96, C_DEEP2, border=C_DEEP3, radius=0.05, border_pt=1.0)
    add_bullets(slide, 1.02, 3.92, 11.28, 2.48, bullets, size=15.0,
                color=C_LIGHT_TXT, lead_color=C_WHITE, bullet_color=C_WARM_LIGHT,
                spacing=11.0, line_spacing=1.28)

    add_text(slide, 0.72, 7.02, 6.0, 0.30, "ShopVision · 第 23 组项目开发介绍",
             size=10.5, color=RGBColor(0x95, 0xB4, 0xB8))
    add_text(slide, 11.4, 7.02, 1.22, 0.30, f"{slide_num:02d} / {TOTAL_SLIDES:02d}",
             size=10.5, bold=True, color=C_WARM_LIGHT, align=PP_ALIGN.RIGHT, font_name=FONT_MONO)
    set_notes(slide, notes)
    return slide


def set_notes(slide, text: str):
    slide.notes_slide.notes_text_frame.text = text.strip()


def set_cell_border(cell, color_hex="D4DFE2", width="9525"):
    tcPr = cell._tc.get_or_add_tcPr()
    for edge in ("lnL", "lnR", "lnT", "lnB"):
        ln = OxmlElement(f"a:{edge}")
        ln.set("w", width)
        ln.set("cap", "flat")
        ln.set("cmpd", "sng")
        ln.set("algn", "ctr")
        solidFill = OxmlElement("a:solidFill")
        srgbClr = OxmlElement("a:srgbClr")
        srgbClr.set("val", color_hex)
        solidFill.append(srgbClr)
        ln.append(solidFill)
        tcPr.append(ln)


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # =========================================================================
    # SLIDE 1: 封面
    # =========================================================================
    s1 = prs.slides.add_slide(blank)
    set_slide_bg(s1, C_DEEP)
    add_oval(s1, 9.5, -1.8, 5.8, 5.8, C_DEEP2)
    add_oval(s1, -1.8, 4.9, 4.4, 4.4, C_DEEP2)
    add_rect(s1, 0, 0, 13.333, 0.08, C_WARM_LIGHT)

    add_text(s1, 0.8, 0.85, 11.733, 0.36, "西安邮电大学  ·  AI 全栈开发课程设计  ·  期末答辩  ·  第 23 组",
             size=14, bold=True, color=C_WARM_LIGHT, align=PP_ALIGN.CENTER)
    add_text(s1, 0.8, 1.48, 11.733, 0.72, "ShopVision",
             size=44, bold=True, color=C_LIGHT_TXT, align=PP_ALIGN.CENTER)
    add_text(s1, 0.8, 2.24, 11.733, 0.82, "电商商品多模态推荐与上架 Agent",
             size=42, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    add_text(s1, 0.8, 3.16, 11.733, 0.44, "以图搜图  ·  以文搜图  ·  上架图文核验  ·  多轮对话导购",
             size=18, color=C_LIGHT_TXT, align=PP_ALIGN.CENTER)

    cards1 = [
        ("9,393", "洗干净的商品库", "3 个来源 → 9 大类目"),
        ("58.67%", "以文搜图 R@1", "微调前 37.37% · R@10 96.90%"),
        ("−57.73%", "图像编码提速", "TensorRT FP16：4.59→1.94 ms"),
        ("90% → 100%", "Agent 工具调用", "纯模型 90% · 规范化后 100%"),
    ]
    cw, gap = 2.72, 0.24
    start_x = (13.333 - (4 * cw + 3 * gap)) / 2
    for i, (val, lbl, sub) in enumerate(cards1):
        cx = start_x + i * (cw + gap)
        add_rect(s1, cx, 4.08, cw, 1.66, C_DEEP2, border=C_DEEP3, radius=0.07, border_pt=1.0)
        add_rect(s1, cx + 0.12, 4.08, cw - 0.24, 0.05, C_WARM_LIGHT if i == 3 else RGBColor(0x5F, 0xA8, 0xB0))
        add_text(s1, cx + 0.08, 4.24, cw - 0.16, 0.56, val,
                 size=29 if i < 3 else 25, bold=True,
                 color=C_WARM_LIGHT if i == 3 else C_WHITE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
        add_text(s1, cx + 0.08, 4.86, cw - 0.16, 0.32, lbl,
                 size=13.5, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        add_text(s1, cx + 0.08, 5.20, cw - 0.16, 0.36, sub,
                 size=10.5, color=C_LIGHT_TXT, align=PP_ALIGN.CENTER)

    add_text(s1, 0.8, 6.26, 11.733, 0.34,
             "项目组成员：何朝杨  ·  杜军博  ·  王陆洲  ·  张梓萱  ·  刘凡思雨  ·  秦鑫洋",
             size=14, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    add_text(s1, 0.8, 6.68, 11.733, 0.30, "2026 年 11 月  ·  全链路代码与实测凭证已入库",
             size=11.5, color=RGBColor(0x95, 0xB4, 0xB8), align=PP_ALIGN.CENTER)

    set_notes(s1, """【开场白，约 40 秒】
各位老师、各位同学，大家好！我是第 23 组的汇报人，我们的项目是《ShopVision：电商商品多模态推荐与上架 Agent》。

用一句大白话说：我们做了一个能“看图、懂中文、还会多轮聊天”的电商导购与上架核验系统。你可以打字找商品、传图找同款、同时传图和文字检查商品有没有“图文不符”，还可以连续追问——先找运动鞋、再说“要白色的”，它知道你还在找鞋。

屏幕上四个数字是我们五个实验跑出来的核心成绩：9,393 条洗干净的商品图文库、以文搜图 R@1 达到 58.67%、TensorRT 让图像编码延迟降了 57.73%、Agent 工具调用纯模型 90% 加参数规范化后达到 100%。下面按实验一到实验五逐一介绍。""")

    # =========================================================================
    # SLIDE 2: 项目总览
    # =========================================================================
    s2 = prs.slides.add_slide(blank)
    add_header_footer(s2, 2, "PROJECT OVERVIEW", "项目总览：五个实验，一步步把系统搭起来")

    steps2 = [
        ("1", "实验一 · 洗干净数据", "整合 MUGE / 苏宁 / Amazon，筛掉错图错类，留 9 类 9,393 条"),
        ("2", "实验二 · 训准双塔模型", "全参微调 Chinese-CLIP ViT-B-16，R@1 从 37.37% 涨到 58.67%"),
        ("3", "实验三 · 给模型提速", "导出 ONNX 转 TensorRT FP16，图像编码延迟从 4.59 降到 1.94 ms"),
        ("4", "实验四 · 做成可用网站", "FastAPI 12 个接口 + React 19 八个页面，含 Celery 异步队列"),
        ("5", "实验五 · 装上对话大脑", "QLoRA 微调 Qwen3-4B，接 4 个工具支持多轮追问、绝不乱编商品"),
    ]
    for i, (num, stitle, sdesc) in enumerate(steps2):
        sy = 1.24 + i * 1.06
        add_rect(s2, 0.60, sy, 5.75, 0.92, C_WHITE, border=C_LINE, radius=0.08, border_pt=0.8)
        badge_c = C_WARM if i == 4 else C_TEAL
        add_oval(s2, 0.74, sy + 0.22, 0.48, 0.48, badge_c)
        add_text(s2, 0.74, sy + 0.22, 0.48, 0.48, num, size=16, bold=True, color=C_WHITE,
                 align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE, font_name=FONT_MONO)
        add_text(s2, 1.34, sy + 0.08, 4.88, 0.32, stitle, size=15, bold=True, color=C_DEEP)
        add_text(s2, 1.34, sy + 0.42, 4.88, 0.42, sdesc, size=12, color=C_MUTED, line_spacing=1.2)

    add_img_fit(s2, ASSETS / "closed_loop_v2.png", 6.55, 1.24, 6.18, 2.86,
                bg_card=True, caption="五个实验的数据与模型接力闭环")

    kpis2 = [
        ("9,393", "商品图文库", "3 来源 · 9 类目", C_TEAL),
        ("58.67%", "检索 R@1", "test 934 对", C_TEAL),
        ("−57.73%", "TRT 提速", "GPU 训练机测速", C_TEAL),
        ("82.5%", "v4 通过率", "40 题过 33 题", C_WARM),
    ]
    kw, kg = 1.44, 0.14
    for i, (v, l, sb, ac) in enumerate(kpis2):
        add_kpi_card(s2, 6.55 + i * (kw + kg), 4.24, kw, 1.42, v, l, sb, accent=ac, val_size=17.5)

    add_rect(s2, 6.55, 5.80, 6.18, 1.06, C_TEAL_SOFT, border=C_TEAL, radius=0.06, border_pt=0.8)
    add_text(s2, 6.74, 5.92, 5.80, 0.84,
             "核心思路：前一步的成果直接喂给下一步——洗净数据 → 训出双塔 → 加速推理 → 封装 API → 交给 Agent 当工具。所有实验日志和评测文件全部入库，随时能复现。",
             size=12.5, color=C_DEEP, line_spacing=1.34)

    set_notes(s2, """【总览页，约 1 分钟】
这一页是整套系统的地图。五个实验像接力棒一样环环相扣：实验一洗干净数据，实验二训准双塔检索模型，实验三用 TensorRT 把速度提一倍多，实验四包成能用的网站和接口，实验五最后装上 Qwen3-4B 对话大脑。上一步的产物直接交给下一步用，全部日志与结果都保存在仓库里。""")

    # =========================================================================
    # SLIDE 3: 章节页 01 实验一
    # =========================================================================
    add_section_divider(
        prs, 3, "01", "实验一 · 洗干净三源商品数据",
        "先解决“数据脏、类目乱、缺属性”的问题，给后面打好地基",
        [
            ("三个来源：", "MUGE（4,704）+ 苏宁自研爬取（4,303）+ Amazon DeepL 译文（1,158），共 10,165 条"),
            ("去重洗脏：", "删重复商品与坏图；视觉模型逐图把关（0.72 阈值），踢掉 765 条“货不对板”"),
            ("防泄题切分：", "按商品 ID 算 MD5 切分训练/测试，同一款商品的多张图绝不拆两边"),
            ("最终产出：", "9 大类 9,393 条干净图文（通过率 92.4%），每步删改全有日志可查"),
        ],
        """【章节过渡，约 20 秒】
先看实验一：数据建设。俗话说垃圾进、垃圾出，我们整合了 MUGE、苏宁和 Amazon 译文共 10,165 条商品，洗掉错图错类后留下 9 类 9,393 条高质量数据。具体做法看下一页。"""
    )

    # =========================================================================
    # SLIDE 4: 实验一详细页
    # =========================================================================
    s4 = prs.slides.add_slide(blank)
    add_header_footer(s4, 4, "EXPERIMENT 01 · DATA ENGINEERING", "实验一：三源整合、视觉洗脏与防泄题切分")

    add_rect(s4, 0.60, 1.24, 6.20, 2.38, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s4, 0.80, 1.36, 5.80, 0.34, "三步把原始杂乱数据洗成标准图文库",
             size=15, bold=True, color=C_DEEP)
    add_bullets(s4, 0.80, 1.76, 5.80, 1.78, [
        ("收齐三源并对齐：", "MUGE + 爬虫 crawl_suning.py + DeepL 翻译 Amazon，统一成 12 列标准表"),
        ("两道去重保干净：", "标题去掉型号/颜色尾巴判重；图片用 SHA-256 指纹去重，坏图全部拦截"),
        ("视觉模型把关补全：", "逐图识别主体，踢掉混进来的果冻/书架/袜子等 765 条，补齐颜色和材质"),
    ], size=12.6, spacing=7.0, line_spacing=1.26)

    add_rect(s4, 0.60, 3.78, 6.20, 1.72, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s4, 0.80, 3.88, 5.80, 0.32, "按商品 ID 算 MD5 哈希切分（8:1:1，防止测试泄题）",
             size=14, bold=True, color=C_DEEP)
    splits = [
        ("train", "7,520", "80.1%", "拿来训练双塔模型"),
        ("valid", "939", "10.0%", "用来调参和看收敛"),
        ("test", "934", "9.9%", "封存考卷，只做最终打分"),
    ]
    for i, (sn, cnt, pct, use) in enumerate(splits):
        sx = 0.80 + i * 1.98
        add_rect(s4, sx, 4.26, 1.84, 1.08, C_TEAL_SOFT if i < 2 else C_WARM_SOFT, radius=0.08)
        add_text(s4, sx + 0.06, 4.32, 1.72, 0.30, f"{sn}  ({pct})",
                 size=11.5, bold=True, color=C_TEAL if i < 2 else C_WARM, align=PP_ALIGN.CENTER, font_name=FONT_MONO)
        add_text(s4, sx + 0.06, 4.62, 1.72, 0.34, cnt,
                 size=20, bold=True, color=C_DEEP, align=PP_ALIGN.CENTER)
        add_text(s4, sx + 0.06, 4.98, 1.72, 0.30, use,
                 size=10.2, color=C_MUTED, align=PP_ALIGN.CENTER)

    add_rect(s4, 0.60, 5.64, 6.20, 1.22, C_TEAL_SOFT, border=C_TEAL, radius=0.06, border_pt=0.8)
    add_text(s4, 0.80, 5.76, 5.80, 1.00,
             "两个实用设计：① 同一件商品的不同角度图片不会拆到训练和测试两边，考出来的分数才真实；② 训练和建 FAISS 索引用同一套描述模板（build_product_text），学什么就搜什么。",
             size=12.4, color=C_DEEP, line_spacing=1.34)

    add_img_fit(s4, FIGS / "fig_sources.png", 7.00, 1.24, 5.73, 2.74,
                bg_card=True, caption="三个数据源规模：MUGE 4,704 / 苏宁 4,303 / Amazon 1,158")
    add_img_fit(s4, FIGS / "fig_passrate.png", 7.00, 4.12, 5.73, 2.74,
                bg_card=True, caption="9 类商品清洗通过率（总体 92.4%，水杯误收异类最多）")

    set_notes(s4, """【实验一内容页，约 1 分 15 秒】
右上图是我们收集的三源数据：MUGE 4,704 条、苏宁爬虫 4,303 条、Amazon 译文 1,158 条，一共 10,165 条。

原始数据有很多重复款和错类，我们先去掉标题里的型号颜色尾巴判重、给图片算 SHA-256 去重，再让视觉模型按 0.72 置信度逐张把关，踢掉果冻、书架、水杯里混进来的袜子等 765 条异类，补全颜色和材质。右下图总体通过率 92.4%，留下 9,393 条（鞋 3,219 条最多、家居 264 条最少）。

切分时我们按商品 ID 算 MD5 做 8:1:1 划分，保证同一款商品的多张图不会拆进训练和测试两边，防止模型提前见过考题；并且训练和建索引用同一套 build_product_text 模板。""")

    # =========================================================================
    # SLIDE 5: 章节页 02 实验二
    # =========================================================================
    add_section_divider(
        prs, 5, "02", "实验二 · 训准 Chinese-CLIP 图文双塔",
        "让模型把“商品图片”和“中文描述”对齐到同一 512 维向量空间",
        [
            ("双塔怎么工作：", "图像塔 ViT-B-16 看图、文本塔 RoBERTa 读字，越像的商品向量夹角越小"),
            ("全参微调路线：", "双塔全参微调（开 AMP + 梯度检查点，lr=1e-5），没用冻结也没用 LoRA"),
            ("三组对照验证：", "拿“没训 / 脏数据训 / 干净数据训”同场考试，算清微调和清洗各自涨了多少分"),
            ("重建检索库：", "训练完用 epoch3.pt 把 9,393 条商品重编一遍，重建 FAISS 索引库"),
        ],
        """【章节过渡，约 20 秒】
数据洗干净后，实验二来训检索模型。我们用 Chinese-CLIP 双塔做全参数微调——特别说明实验二没有用 LoRA，是在本组 5060 Ti 显卡上 6 分钟全参训完的，还做了三组对照验证数据清洗到底值不值。"""
    )

    # =========================================================================
    # SLIDE 6: 实验二详细页
    # =========================================================================
    s6 = prs.slides.add_slide(blank)
    add_header_footer(s6, 6, "EXPERIMENT 02 · FULL FINE-TUNING", "实验二：Chinese-CLIP 双塔全参微调与对比实验")

    add_img_fit(s6, FIGS / "fig_recall.png", 0.60, 1.24, 6.45, 2.70,
                bg_card=True, caption="三组对比（934 题考卷）：未微调 vs 脏数据直训 vs 干净数据微调")

    add_img_fit(s6, FIGS / "fig_curves.png", 0.60, 4.08, 6.45, 2.78,
                bg_card=True, caption="训练平稳收敛：验证 Loss 降至 0.1403，未见过拟合")

    add_kpi_card(s6, 7.25, 1.24, 5.48, 1.26, "37.37% → 58.67%",
                 "以文搜图首位命中 R@1（涨 21.3 个百分点）",
                 "前 5 命中 R@5：89.08%   |   前 10 命中 R@10：96.90%",
                 accent=C_TEAL, val_size=27)

    add_rect(s6, 7.25, 2.62, 5.48, 2.26, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s6, 7.45, 2.72, 5.08, 0.30, "怎么训出来的（本组电脑单卡，不是云端）",
             size=13.8, bold=True, color=C_DEEP)
    add_bullets(s6, 7.45, 3.08, 5.08, 1.72, [
        ("训练机器：", "Win11 + WSL2 + Docker，本组 RTX 5060 Ti 8GB"),
        ("全参省显存：", "全参微调 + AMP 半精度 + grad_checkpointing"),
        ("极速收敛：", "batch=32、lr=1e-5，跑 3 轮 705 步约 6 分钟"),
        ("排坑记录：", "WSL2 下 NCCL 卡死 → 打 NoDDP 补丁单卡跑通"),
    ], size=11.4, spacing=6.5, line_spacing=1.24)

    add_rect(s6, 7.25, 5.00, 5.48, 1.88, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_text(s6, 7.45, 5.10, 5.08, 0.30, "三组对比拆账：微调和洗数据各自功劳多大？",
             size=13.5, bold=True, color=C_WARM)
    add_bullets(s6, 7.45, 5.44, 5.08, 1.36, [
        ("微调本身涨 +13.59%（64%）：", "没微调 37.37% → 脏数据直训 50.96%"),
        ("洗数据再涨 +7.71%（36%）：", "样本少 772 条，R@1 反升至 58.67%"),
        ("结论：", "质量优于数量！训完用 epoch3.pt 重建 FAISS 索引"),
    ], size=11.4, lead_color=C_DEEP, bullet_color=C_WARM, spacing=6.0, line_spacing=1.24)

    set_notes(s6, """【实验二内容页，约 1 分 30 秒】
实验二我们对 Chinese-CLIP ViT-B-16 做双塔全参微调。在本组 RTX 5060 Ti 8GB 上，打开 AMP 和 grad_checkpointing 省显存，跑 3 轮 705 步只要 6 分钟，还用 NoDDP 补丁解决了 WSL2 下 NCCL 卡死的坑。

看左上三组对比：蓝柱没微调 R@1 只有 37.37%；橙柱拿未清洗的 10,165 条直接训到 50.96%（微调本身功劳 +13.59%，约占 64%）；绿柱拿清洗后 9,393 条训到 58.67%（样本少了 772 条，反而多涨 +7.71%，约占 36%），R@5 到 89.08%、R@10 到 96.90%，直接证明质量优于数量。最后用 epoch3.pt 重建全库 FAISS 索引。""")

    # =========================================================================
    # SLIDE 7: 章节页 03 实验三
    # =========================================================================
    add_section_divider(
        prs, 7, "03", "实验三 · 用 TensorRT 给模型提速",
        "不改模型结构、几乎不掉精度，让图片编码速度翻一倍多",
        [
            ("先试 INT8 量化：", "测了 6 种配置，最好仍掉点 13.06%（超标），果断放弃并留档"),
            ("改走提速主线：", "PyTorch 导成 ONNX → 转 FP16 → TensorRT 引擎做算子融合"),
            ("公平对比测速：", "同一台 GPU 训练机配对测速（暖机 10 次取 20 次中位数），不跨硬件占便宜"),
            ("核对检索精度：", "934 道考题逐后端复查，确认提速后检索准度几乎没掉"),
        ],
        """【章节过渡，约 20 秒】
模型训准之后，实验三让它跑得更快。我们先试了 INT8 动态量化，掉点 13% 远超 2% 红线，诚实冻结留档；主线改走 ONNX 加 TensorRT FP16 引擎提速，速度翻倍且精度几乎无损。"""
    )

    # =========================================================================
    # SLIDE 8: 实验三流水线与延迟
    # =========================================================================
    s8 = prs.slides.add_slide(blank)
    add_header_footer(s8, 8, "EXPERIMENT 03 · ACCELERATION PIPELINE", "实验三：导出 ONNX 与 TensorRT FP16 提速")

    add_img_fit(s8, FIGS5 / "14_推理加速流水线.png", 0.60, 1.24, 5.10, 4.30,
                bg_card=True, caption="四步提速：导出 ONNX → 转 FP16 → 构建 TensorRT → 配对测速")

    add_rect(s8, 0.60, 5.68, 5.10, 1.18, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_text(s8, 0.78, 5.76, 4.74, 0.28, "导出时踩过的坑", size=13, bold=True, color=C_WARM)
    add_text(s8, 0.78, 6.08, 4.74, 0.72,
             "直接调 .half() 转半精度会让 LayerNorm 报错；改先导出 FP32 ONNX 再做图层级转 FP16 顺利解决。图像塔固定 224×224，文本塔支持动态 batch。",
             size=11.8, color=C_DEEP, line_spacing=1.28)

    add_img_fit(s8, FIGS5 / "10_延迟对比.png", 5.92, 1.24, 6.81, 3.86,
                bg_card=True, caption="单图（batch=1）与批量（batch=32）推理耗时对比，柱越短越快")

    add_kpi_card(s8, 5.92, 5.26, 3.30, 1.60, "−57.73%",
                 "单图延迟砍半（目标 ≥40%）",
                 "4.59 → 1.94 ms（batch=1）\nbatch=32：50.43 → 23.84 ms（−52.73%）",
                 accent=C_TEAL, val_size=28)
    add_kpi_card(s8, 9.43, 5.26, 3.30, 1.60, "2.366×",
                 "单图加速比（目标 ≥1.2×）",
                 "batch=32 加速 2.115 倍\n同台 GPU 训练机配对测图像塔",
                 accent=C_WARM, val_size=28)

    set_notes(s8, """【实验三流水线与延迟页，约 1 分 15 秒】
左边是加速四步：从 epoch3.pt 导出 FP32 ONNX，再用图层级方式转 FP16（避开直接 .half() 导致 LayerNorm 报错的坑），最后交给 TensorRT 融合算子。

看右边柱状图，同一台 GPU 训练机（torch 2.7.1+cu128、TensorRT 10.x）同精度配对测速：ORT-CPU 和 ORT-CUDA 提速有限，TensorRT FP16 直接拉开差距——batch=1 从 4.59 毫秒降到 1.94 毫秒（−57.73%，2.366 倍），batch=32 从 50.43 降到 23.84 毫秒（−52.73%，2.115 倍），大幅超标完成任务。""")

    # =========================================================================
    # SLIDE 9: 实验三收益与精度代价
    # =========================================================================
    s9 = prs.slides.add_slide(blank)
    add_header_footer(s9, 9, "EXPERIMENT 03 · TRADE-OFF ANALYSIS", "实验三：速度翻倍、体积减半，精度几乎不掉")

    add_img_fit(s9, FIGS5 / "11_吞吐对比.png", 0.60, 1.24, 3.92, 2.74,
                bg_card=True, caption="每秒处理图片数（吞吐量）对比")
    add_img_fit(s9, FIGS5 / "12_精度误差热力图.png", 4.70, 1.24, 3.92, 2.74,
                bg_card=True, caption="各后端 R@K 精度差值（越接近 0 越好）")
    add_img_fit(s9, FIGS5 / "13_模型文件大小.png", 8.81, 1.24, 3.92, 2.74,
                bg_card=True, caption="FP32 vs FP16 模型文件体积（MiB）")

    add_kpi_card(s9, 0.60, 4.14, 3.92, 1.56, "+136.58%",
                 "单图吞吐翻倍（目标 ≥50%）",
                 "batch=32 吞吐提升 +111.52%\n来自 TensorRT 算子融合与 kernel 优化",
                 accent=C_TEAL, val_size=28)
    add_kpi_card(s9, 4.70, 4.14, 3.92, 1.56, "−0.4283pp",
                 "R@1 精度仅微降 0.43%",
                 "FP32 基线 58.57% → TRT FP16 58.14%\n远优于任务书 1% 与 0.5% 红线",
                 accent=C_WARM, val_size=28)
    add_kpi_card(s9, 8.81, 4.14, 3.92, 1.56, "体积减半",
                 "FP16 权重文件缩小 50%",
                 "双塔纯权重：718.3 → 359.2 MiB\n文本塔 ONNX：389.6 → 195.0 MiB",
                 accent=C_TEAL, val_size=28)

    add_rect(s9, 0.60, 5.84, 12.133, 1.04, C_TEAL_SOFT, border=C_TEAL, radius=0.06, border_pt=0.8)
    add_text(s9, 0.80, 5.95, 11.73, 0.84,
             "实话实说三个边界：① 速度在 GPU 训练机同精度配对测（原始 JSON 未记具体型号，不补写），精度对同源 PyTorch FP32（58.57%）比；② 图像塔占双塔总计算量 79%，所以优先加速图像塔最划算；③ INT8 动态量化掉点 13.06pp 已放弃，TRT 逐样本排名未测不夸大。",
             size=11.8, color=C_DEEP, line_spacing=1.32)

    set_notes(s9, """【实验三收益与代价页，约 1 分钟】
这一页算一笔“赚了多少、赔了多少”的账：吞吐量翻了一倍多（+136.58%），模型文件体积直接减半方便部署；而代价几乎可以忽略——在 934 条测试题上，TensorRT FP16 的 R@1 只比同源 FP32 少了 0.43 个百分点（相当于 934 题里净差约 4 题），R@5 更是零误差。底部也坦诚说明边界：源测速 JSON 没写具体 GPU 型号我们不补写，INT8 掉点 13% 已放弃，未测项不声称。""")

    # =========================================================================
    # SLIDE 10: 章节页 04 实验四
    # =========================================================================
    add_section_divider(
        prs, 10, "04", "实验四 · 把模型做成能用的网站和接口",
        "用 FastAPI + React 19 搭起前后端系统，让用户直接点选搜商品",
        [
            ("前后端齐全：", "React 19 + Ant Design 做了 8 个页面，FastAPI 提供 12 个标准接口"),
            ("规范返回体：", "所有接口统一返回 {code, result, msg}，错误码前三位直接对应 HTTP 状态"),
            ("解耦且抗压：", "模拟/真 ONNX 模型一行配置切换；批量大图走 Celery + Redis 异步队列不卡页面"),
            ("交付即验收：", "离线 OpenAPI 文档随包入库，前端 21 项单测与生产构建全部通过"),
        ],
        """【章节过渡，约 20 秒】
前面都在打磨模型，实验四把它变成真正能点、能搜、能上架的完整网站，一共 12 个后端接口、8 个前端页面，也为实验五的对话导购打好底座。"""
    )

    # =========================================================================
    # SLIDE 11: 实验四架构与接口
    # =========================================================================
    s11 = prs.slides.add_slide(blank)
    add_header_footer(s11, 11, "EXPERIMENT 04 · SYSTEM ARCHITECTURE", "实验四：四层架构设计与 12 个核心接口")

    add_img_fit(s11, FIGS5 / "01_系统架构.png", 0.60, 1.24, 7.15, 3.92,
                bg_card=True, caption="四层分工：前端页面 → FastAPI 接单 → 业务编排 → ONNX 模型与 FAISS 索引")

    add_rect(s11, 0.60, 5.30, 7.15, 1.58, C_WHITE, border=C_LINE, radius=0.06)
    add_bullets(s11, 0.78, 5.42, 6.80, 1.38, [
        ("模型可热切换：", "占位模拟与真 ONNX 接口一致，改 .env 一行切换，前后端并行开发"),
        ("防脏数据入库：", "上传新商品必开真 ONNX，占位模式拒绝（50001），防假向量入库"),
        ("一键启动联调：", "scripts/start_all.py 支持一键启停与 --lan 演示，前端 21 单测全过"),
    ], size=11.4, spacing=7.0, line_spacing=1.24)

    add_kpi_card(s11, 7.98, 1.24, 2.28, 1.30, "12", "后端 API 接口", "同步 + 异步 + Agent", accent=C_TEAL, val_size=30)
    add_kpi_card(s11, 10.45, 1.24, 2.28, 1.30, "8", "前端功能页", "React 19 + Antd", accent=C_WARM, val_size=30)

    add_rect(s11, 7.98, 2.70, 4.75, 4.18, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s11, 8.18, 2.82, 4.35, 0.34, "接口分组（统一前缀 /api/v1）",
             size=14.5, bold=True, color=C_DEEP)
    add_bullets(s11, 8.18, 3.24, 4.35, 2.80, [
        ("三大核心检索（3）：", "/image 识图找同款、/text 搜中文、/match 查图文是否一致"),
        ("异步批量队列（3）：", "/tasks/image、/tasks/batch（上限 12 张）、/tasks/{id}，Celery + Redis 排队，断队列不影响同步搜"),
        ("对话导购接口（3）：", "/agent/chat 聊天、/agent/image 发图接话、DELETE 清空会话"),
        ("入库与状态（3）：", "/admin/items 新商品入库、/admin/categories、/health 体检"),
    ], size=12.0, spacing=8.0, line_spacing=1.25)

    add_rect(s11, 8.18, 6.20, 4.35, 0.50, C_TEAL_SOFT, radius=0.08)
    add_text(s11, 8.30, 6.24, 4.12, 0.42,
             "离线 openapi.json 与 API文档.md 已入库，不用起服务也能审阅",
             size=10.5, bold=True, color=C_TEAL, valign=MSO_ANCHOR.MIDDLE)

    set_notes(s11, """【实验四架构页，约 1 分 15 秒】
左边四层架构职责很清楚：前端通过 Axios 发请求，后端接入层做参数校验和包装，业务层 MatchService 编排编码和查库（不碰 HTTP，方便单测），底层接 ONNX 和 FAISS。

三个很实在的设计：第一，占位模型和真 ONNX 接口一模一样，改一行配置切换；第二，上传新商品强制开真 ONNX，防止占位假向量把真索引搞脏；第三，批量传图走 Celery + Redis 异步队列（单批最多 12 张），就算 Redis 没开，也只有异步接口报 50001，日常搜图搜文完全不受影响。""")

    # =========================================================================
    # SLIDE 12: 实验四真实页面展示
    # =========================================================================
    s12 = prs.slides.add_slide(blank)
    add_header_footer(s12, 12, "EXPERIMENT 04 · FRONTEND UI & ERROR HANDLING", "实验四：真实页面演示与友好错误提示")

    add_img_fit(s12, FIGURES / "01_首页.png", 0.60, 1.24, 3.86, 4.18,
                bg_card=True, caption="工作台首页：一站进入搜图、搜文、查匹配与对话")
    add_img_fit(s12, FIGURES / "02_图像分类_识别结果.png", 4.74, 1.24, 3.86, 4.18,
                bg_card=True, caption="识图实测：传小白鞋图 → 认出「鞋」并推相似款")
    add_img_fit(s12, FIGURES / "04_图文匹配_并排.png", 8.87, 1.24, 3.86, 4.18,
                bg_card=True, caption="图文核验：一致（鞋+白鞋）vs 不一致（鞋+包）")

    add_rect(s12, 0.60, 5.58, 12.133, 1.28, C_WHITE, border=C_LINE, radius=0.06)
    add_bullets(s12, 0.80, 5.70, 11.73, 1.06, [
        ("图文核验绝不“和稀泥”：", "右图故意传“鞋图 + 双肩包文字”——图和文各自独立判类、互不偷看，再比对结果，立刻抓住“货不对板”。"),
        ("一看就懂的错误码（前三位 = HTTP 状态）：", "400xx 输入有误（如 40001 图片坏了）；404xx 找不到（40401 类目不存在、40403 非法工具）；500xx 服务不可用（50001），前端全翻成中文提示。"),
    ], size=12.4, spacing=7.0, line_spacing=1.28)

    set_notes(s12, """【实验四页面页，约 1 分钟】
看三个真实跑出来的页面：左图是工作台首页，干净直观；中间是图像分类实测，上传白鞋立刻识别出「鞋」并给出相似商品卡片；最右是图文匹配并排对照——鞋图配“白色运动鞋”判一致，鞋图配“双肩包”判不一致，因为图像和文本是各判各的类、互不偷看，所以绝不和稀泥。出错时所有 400xx/404xx/500xx 错误码都会自动变成中文提示。""")

    # =========================================================================
    # SLIDE 13: 章节页 05 实验五
    # =========================================================================
    add_section_divider(
        prs, 13, "05", "实验五 · 给系统装上 Qwen3-4B 对话导购",
        "用户直接说人话、发图片、连续追问，Agent 自动选工具查真货",
        [
            ("轻量大模型：", "选 Qwen3-4B-Instruct-2507 + QLoRA 4-bit 微调，8GB 显卡就能跑"),
            ("一条铁律：", "大模型只管“听懂话 + 调工具 + 写点评”，商品全部查真库，绝不胡编价格"),
            ("三道防错保险：", "白名单锁死 4 个工具 + 自动纠错洗参数 + 模型断线自动切规则兜底"),
            ("越聊越懂你：", "四代数据迭代（v1→v4），支持记住上一轮类目、刚搜完图直接接着聊"),
        ],
        """【章节过渡，约 20 秒】
最后是实验五：对话导购 Agent。在这里我们才用 QLoRA 微调 Qwen3-4B。核心铁律只有一句：大模型只负责听懂人话和选工具，所有商品事实全由实验四检索接口提供，绝不胡编价格。"""
    )

    # =========================================================================
    # SLIDE 14: 实验五微调与协议
    # =========================================================================
    s14 = prs.slides.add_slide(blank)
    add_header_footer(s14, 14, "EXPERIMENT 05 · AGENT QLORA & PROTOCOL", "实验五：Qwen3-4B 微调迭代与两轮防幻觉流程")

    add_img_fit(s14, ASSETS / "agent_pipeline_v2.png", 0.60, 1.24, 5.45, 5.62,
                bg_card=True, caption="Agent 怎么工作：先微调大脑 → 查真库 → 回喂写安全推荐语")

    add_rect(s14, 6.26, 1.24, 6.47, 2.16, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s14, 6.46, 1.34, 6.07, 0.32, "四代数据升级：发现一个问题，解决一个问题", size=14.2, bold=True, color=C_DEEP)
    add_bullets(s14, 6.46, 1.72, 6.07, 1.60, [
        ("v1（100 条）：", "题目里直接写死了类目，模型只会照抄还拼错工具名，纯模型仅 10%"),
        ("v2（163 条）：", "扩到 78 条不写类目的口语题，逼模型自己猜类目 → 纯模型飙到 90%"),
        ("v3 / v4 多轮：", "v3 补齐 4 个工具（440 条）；v4 扩到 549 段 / 1,029 轮多轮对话（max_len 2048）"),
    ], size=12.0, spacing=6.5, line_spacing=1.24)

    add_rect(s14, 6.26, 3.54, 6.47, 1.74, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s14, 6.46, 3.64, 6.07, 0.32, "云端低成本训练 + 本地换卡复查",
             size=14.0, bold=True, color=C_DEEP)
    add_bullets(s14, 6.46, 4.00, 6.07, 1.22, [
        ("AutoDL 租卡训练：", "v1/v3/v4 用 RTX 4090 48GB；v2 用 RTX 3080Ti 12GB（插件仅 64MB）"),
        ("换机器不掉分：", "v2 在 3080Ti 与本组 RTX 5060 8GB 上测出完全一样的结果，非常稳定"),
    ], size=12.0, spacing=6.5, line_spacing=1.24)

    add_kpi_card(s14, 6.26, 5.42, 2.04, 1.44, "57.53 s", "v1 训练时间", "3 epoch / 18 步", accent=C_TEAL, val_size=24)
    add_kpi_card(s14, 8.48, 5.42, 2.04, 1.44, "≈ ¥0.13", "v1 训练花费", "4090 按时计费", accent=C_WARM, val_size=24)
    add_kpi_card(s14, 10.69, 5.42, 2.04, 1.44, "520.2 s", "v4 多轮训练", "549 段长对话", accent=C_TEAL, val_size=24)

    set_notes(s14, """【实验五微调页，约 1 分 30 秒】
左边展示了我们防幻觉的核心逻辑：模型第一轮只输出 JSON 指令，不编商品；经过四工具白名单、纠错和参数规范化后去查真库；第二轮把真商品喂回模型写推荐语，并由安全闸拦截乱报价（因为我们数据库本身没价格字段）。

右边是四代数据的进化：v1 题目写死了类目导致口语场景只有 10%；v2 去掉类目提示扩到 78 条，纯模型直接涨到 90%；v3/v4 补齐四工具和多轮对话（v4 达 549 段 1,029 轮）。训练在 AutoDL 完成，v1 只花了一毛三，v2 在 3080Ti 和本组 5060 上结果完全一致。""")

    # =========================================================================
    # SLIDE 15: 工具调用评测
    # =========================================================================
    s15 = prs.slides.add_slide(blank)
    add_header_footer(s15, 15, "EXPERIMENT 05 · TOOL CALL EVALUATION", "工具调用实测：纯模型 90%，加规范化 100%")

    add_img_fit(s15, FIGS5 / "03_工具调用评测_纯模型90%.png", 0.60, 1.24, 5.95, 4.08,
                bg_card=True, caption="纯模型裸考：10 轮对 9 轮 = 90%（类目 10/10 全对）")
    add_img_fit(s15, FIGS5 / "03_工具调用评测_混合100%.png", 6.78, 1.24, 5.95, 4.08,
                bg_card=True, caption="模型 + 参数规范化（洗去多余字词）：10 轮全对 = 100%")

    add_rect(s15, 0.60, 5.48, 12.133, 1.38, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_bullets(s15, 0.80, 5.60, 11.73, 1.18, [
        ("绝不夸大成绩：", "100% 是加上“参数规范化”洗词后的工程功劳，不是模型自己变强——我们坚持报「纯模型 90%，规范化后 100%」。"),
        ("两台卡实测一致：", "RTX 3080Ti 与 RTX 5060 8GB 结果一模一样；唯一扣分题「有没有灰色的双肩包」，仅因查询词多留了一个「的」字。"),
        ("说明一句：", "5.2 阶段验证集 75.76% 总共只有 11 题（工具调用仅 1 题），样本太小不作准，统一看这里 10 轮实测。"),
    ], size=11.8, lead_color=C_WARM, bullet_color=C_WARM, spacing=5.0, line_spacing=1.24)

    set_notes(s15, """【工具调用评测页，约 1 分钟】
左边是 v2 纯模型裸考，10 轮对 9 轮（90%），已经达到任务书 ≥90% 的要求，唯一扣分是因为查询词里多带了一个“的”字；右边加上参数规范化清洗词后 10 轮全对（100%）。我们严守红线，永远双口径并报，不把后处理功劳算到纯模型头上。而且在 3080Ti 和本组 5060 上结果完全一致。""")

    # =========================================================================
    # SLIDE 16: 多轮对话评测
    # =========================================================================
    s16 = prs.slides.add_slide(blank)
    add_header_footer(s16, 16, "EXPERIMENT 05 · DIALOGUE EVALUATION", "多轮对话考试：v3 单轮 vs v4 多轮（40 题实测）")

    add_text(s16, 0.60, 1.18, 6.0, 0.30, "v4 多轮模型成绩（40 道对话考题，凭证：eval_v4_dialogue.json）",
             size=12.8, bold=True, color=C_DEEP)

    add_kpi_card(s16, 0.60, 1.54, 2.86, 1.54, "100%", "JSON 全部合法", "40/40 零格式崩溃\nv3 单轮曾为 95%（38/40）", accent=C_TEAL, val_size=30)
    add_kpi_card(s16, 3.64, 1.54, 2.86, 1.54, "90.0%", "选对动作（工具/回复）", "36/40 判断正确\nv3 单轮为 92.5%（37/40）", accent=C_TEAL, val_size=30)
    add_kpi_card(s16, 0.60, 3.24, 2.86, 1.54, "82.5%", "40 题全项通过率", "33/40 工具+参数+安全全过\n（测指令准确度，非线上搜库）", accent=C_WARM, val_size=30)
    add_kpi_card(s16, 3.64, 3.24, 2.86, 1.54, "100%", "零胡说安全率", "36/36 无乱报价、无吹销量\n安全防线零漏网", accent=C_TEAL, val_size=30)

    add_rect(s16, 0.60, 4.94, 5.90, 1.92, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s16, 0.78, 5.04, 5.54, 0.28, "进步在哪？剩下的 7 题错在哪？", size=13.2, bold=True, color=C_DEEP)
    add_bullets(s16, 0.78, 5.38, 5.54, 1.40, [
        ("彻底治好乱码崩溃：", "v3 遇到多轮指代曾瞎编 77 位商品 ID 搞坏 JSON；v4 学会多轮上下文后 JSON 100% 合法。"),
        ("7 题未通过全部查清：", "3 题仅多留了量词「一双」、3 题问类目直接口头答没调工具、1 题缺后端历史注入，零崩溃。"),
    ], size=11.6, spacing=6.0, line_spacing=1.24)

    add_img_fit(s16, FIGS5 / "18_Agent首轮卡片.png", 6.72, 1.24, 2.92, 4.02,
                bg_card=True, caption="首轮搜文字：自动出推荐语与商品卡")
    add_img_fit(s16, FIGS5 / "19_图搜接话.png", 9.81, 1.24, 2.92, 4.02,
                bg_card=True, caption="发图接话：搜完图继续用文字聊")

    add_rect(s16, 6.72, 5.42, 6.01, 1.44, C_TEAL_SOFT, border=C_TEAL, radius=0.06, border_pt=0.8)
    add_text(s16, 6.92, 5.54, 5.62, 1.22,
             "图和字在同一个聊天里打通：发文字搜商品、传图片找同款、接着追问，共用同一个 session_id。图搜走真 ONNX 图像塔（首位相似度 0.9573），认出的类目自动记进聊天记录。",
             size=12.2, color=C_DEEP, line_spacing=1.34)

    set_notes(s16, """【多轮评测页，约 1 分 15 秒】
v4 在 40 道多轮协议考题上：JSON 解析从 95% 升到 100%，彻底治好了 v3 瞎编 77 位 ID 搞坏格式的问题；动作准确 90%；40 题全项达标 33 题（82.5%，注意这是考模型指令和参数是否全对，不是搜库召回率），剩下的 7 题全查清原因：3 题多留了量词“一双”、3 题问类目直接口头回答、1 题缺历史注入；安全率 100% 零乱报价。""")

    # =========================================================================
    # SLIDE 17: 多轮会话管理与安全闸
    # =========================================================================
    s17 = prs.slides.add_slide(blank)
    add_header_footer(s17, 17, "EXPERIMENT 05 · SESSION & SAFETY GUARD", "多轮聊天背后的 5 个贴心工程设计")

    add_img_fit(s17, FIGS5 / "20_多轮追问.png", 0.60, 1.24, 2.98, 4.30,
                bg_card=True, caption="多轮追问：刷新网页聊天记录还在")
    add_img_fit(s17, FIGS5 / "21_清空会话.png", 3.76, 1.24, 2.98, 4.30,
                bg_card=True, caption="一键清空：前端页面和后端内存一起清")

    add_rect(s17, 6.96, 1.24, 5.77, 4.30, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s17, 7.18, 1.38, 5.33, 0.34, "怎么做到“聊得准、不跑偏、不占内存、不胡说”", size=14.0, bold=True, color=C_DEEP)
    add_bullets(s17, 7.18, 1.82, 5.33, 3.56, [
        ("记住重点不爆显存：", "只留最近 8 条消息 + 最多 6 句用户原话摘要，既省算力又不忘偏好。"),
        ("记住上一轮找啥：", "先搜「运动鞋」、再说「要白色的」→ 自动合并搜「运动鞋 白色」，不跑偏。"),
        ("搜完图能接着聊：", "图搜走真 ONNX（首位 0.9573），把类目写入记录，下一句直接接着筛。"),
        ("自动清理防爆内存：", "点清空立即调 DELETE 释放；30 分钟不用自动过期（TTL），最多存 500 个会话（LRU）。"),
        ("最后一道安全闸：", "数据库没价格和销量，拦截乱报价、乱吹销量，顺手纠正口误与客套话。"),
    ], size=12.2, spacing=8.5, line_spacing=1.26)

    add_rect(s17, 0.60, 5.72, 12.133, 1.14, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_text(s17, 0.80, 5.84, 11.73, 0.92,
             "实话实说测试范围：左边截图是在没装 Qwen 权重的本机测的（走规则兜底模式，图搜走真 ONNX），验证了界面渲染、刷新保持和清空释放；真模型 v4 的多轮过渡语与槽位继承现场演练，已整理成「演示机验证checklist.md」待上 GPU 演示机复测。",
             size=12.0, color=C_DEEP, line_spacing=1.34)

    set_notes(s17, """【多轮会话管理页，约 1 分钟】
右边五个设计很接地气：8 条消息加 6 句摘要控显存；记住上一轮类目把“运动鞋”和“白色”合起来搜；图搜结果写进聊天历史方便接话；30 分钟过期加 500 会话上限防内存越涨越多；最后一道安全闸挡住乱报价和乱吹销量。底部也如实说明：左侧回归截图在本机规则兜底模式下完成，真模型 v4 端到端演练已备好 checklist 待上演示机跑。""")

    # =========================================================================
    # SLIDE 18: 总结与展望
    # =========================================================================
    s18 = prs.slides.add_slide(blank)
    add_header_footer(s18, 18, "SUMMARY & OUTLOOK", "项目总结：全部真实成绩与下一步计划")

    rows_data = [
        ("环节", "最终成绩", "测试条件（全部有凭证）"),
        ("三源洗数据", "10,165 → 9,393 条（92.4%）", "MUGE + 苏宁 + Amazon 共 9 类"),
        ("双塔全参微调", "R@1：37.37% → 58.67%", "test 934 题；微调 +13.6 / 洗数据 +7.7pp"),
        ("TensorRT 提速", "4.59 → 1.94 ms（−57.73%）", "GPU 训练机单图配对；R@1 仅差 −0.43pp"),
        ("Agent 调工具", "纯模型 90% → 规范化 100%", "v2 十轮，3080Ti 与 5060 两卡一致"),
        ("v4 多轮对话", "JSON 100% / 动作 90% / 过 82.5%", "40 题协议考卷；零胡说安全率 100%"),
        ("网站接口耗时", "搜文 46.4 ms / 搜图 115.8 ms", "本机 ONNX CPU 压测 30 次均值"),
    ]
    tbl_shape = s18.shapes.add_table(len(rows_data), 3, Inches(0.60), Inches(1.26), Inches(7.15), Inches(5.52))
    tbl = tbl_shape.table
    tbl.columns[0].width = Inches(1.58)
    tbl.columns[1].width = Inches(2.74)
    tbl.columns[2].width = Inches(2.83)

    for r_idx, row in enumerate(rows_data):
        for c_idx, val in enumerate(row):
            cell = tbl.cell(r_idx, c_idx)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.08)
            cell.margin_top = Inches(0.05)
            cell.margin_bottom = Inches(0.05)
            cell.fill.solid()
            if r_idx == 0:
                cell.fill.fore_color.rgb = C_DEEP
                txt_c, bld, fsz = C_WHITE, True, 12.2
            else:
                cell.fill.fore_color.rgb = C_WHITE if r_idx % 2 == 1 else C_TEAL_SOFT
                txt_c = C_DEEP if c_idx == 0 else (C_WARM if (r_idx in (3, 4) and c_idx == 1) else C_TEXT)
                bld = (c_idx == 0 or (c_idx == 1 and r_idx in (2, 3, 4)))
                fsz = 11.4
            set_cell_border(cell, "D4DFE2", "9525")
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            p.line_spacing = 1.18
            run = p.add_run()
            run.text = val
            run.font.name = FONT_ZH
            run.font.size = Pt(fsz)
            run.font.bold = bld
            run.font.color.rgb = txt_c

    add_rect(s18, 7.98, 1.26, 4.75, 2.66, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s18, 8.18, 1.38, 4.35, 0.32, "我们做成了什么", size=14.8, bold=True, color=C_DEEP)
    add_bullets(s18, 8.18, 1.78, 4.35, 2.02, [
        ("全链路跑通：", "从洗数据、训模型、加速、做网站到对话 Agent，全部留痕可复现。"),
        ("防泄题、同模板：", "MD5 切分防偷看考题，训练和搜库用同一套模板。"),
        ("靠谱不胡说：", "白名单 + 洗参数 + 规则兜底 + 安全闸，商品全查真库。"),
        ("开箱能演示：", "一键启动（支持局域网）、8 个页面与离线接口文档齐全。"),
    ], size=11.4, spacing=5.5, line_spacing=1.22)

    add_rect(s18, 7.98, 4.08, 4.75, 2.70, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_text(s18, 8.18, 4.20, 4.35, 0.32, "还有哪些不足 & 下一步怎么改", size=14.5, bold=True, color=C_WARM)
    add_bullets(s18, 8.18, 4.60, 4.35, 2.04, [
        ("补难例对话：", "加入“不要黑色”“200 元以内”等否定与多条件对话样本。"),
        ("聊天记录持久化：", "把内存里的会话搬到 Redis / SQLite，重启服务不丢失。"),
        ("挡住库外商品：", "给 FAISS 加上相似度底线，库里没有的商品直接提示找不到。"),
        ("演示机实机联调：", "按 checklist 在 GPU 演示机走完 v4 完整多轮对话演示。"),
    ], size=11.4, lead_color=C_DEEP, bullet_color=C_WARM, spacing=5.5, line_spacing=1.22)

    set_notes(s18, """【总结页，约 1 分钟】
左边六行是全项目真实成绩单，每一条都能回仓库查凭证；右边是我们已经做成的四件事，以及坦诚列出的四个不足和下一步改进方向。""")

    # =========================================================================
    # SLIDE 19: 致谢与团队成员
    # =========================================================================
    s19 = prs.slides.add_slide(blank)
    set_slide_bg(s19, C_DEEP)
    add_oval(s19, 9.2, -1.6, 5.6, 5.6, C_DEEP2)
    add_oval(s19, -1.6, 4.8, 4.2, 4.2, C_DEEP2)
    add_rect(s19, 0, 7.42, 13.333, 0.08, C_WARM_LIGHT)

    add_text(s19, 0.8, 1.95, 11.733, 0.90, "谢谢各位老师与同学聆听",
             size=44, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    add_text(s19, 0.8, 2.98, 11.733, 0.48, "欢迎批评指正  ·  全部代码、日志与评测凭证均可复查",
             size=18, color=C_LIGHT_TXT, align=PP_ALIGN.CENTER)

    add_rect(s19, 2.2, 3.88, 8.933, 0.025, C_WARM_LIGHT)

    add_text(s19, 0.8, 4.26, 11.733, 0.36, "ShopVision · 第 23 组团队成员",
             size=14, bold=True, color=C_WARM_LIGHT, align=PP_ALIGN.CENTER)
    add_text(s19, 0.8, 4.74, 11.733, 0.46,
             "何朝杨   ·   杜军博   ·   王陆洲   ·   张梓萱   ·   刘凡思雨   ·   秦鑫洋",
             size=21, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    add_text(s19, 0.8, 5.75, 11.733, 0.36, "西安邮电大学  ·  AI 全栈开发课程设计  ·  2026 年 11 月",
             size=13, color=RGBColor(0x95, 0xB4, 0xB8), align=PP_ALIGN.CENTER)

    set_notes(s19, """【收尾与答辩追问预案，约 20 秒】
以上就是第 23 组的全部汇报内容，谢谢大家，欢迎提问！

【高频答辩 7 问速答】
1. 实验二用了 LoRA 吗？→ 没有，实验二是 Chinese-CLIP 全参微调（AMP + 梯度检查点，本组 RTX 5060 Ti 8GB 跑 6 分钟）；QLoRA 只用在实验五的 Qwen3-4B。
2. 洗数据功劳有多大？→ test 934 题三组对比：没微调 37.37% → 脏数据训 50.96%（+13.59%，约 64%）→ 干净数据训 58.67%（少 772 条反多涨 +7.71%，约 36%）。
3. 为什么不用 INT8 量化？实验三用 3080Ti 了吗？→ INT8 最好也掉 13.06pp 超标放弃；实验三在 GPU 训练机做同精度配对测速（源 JSON 未记型号不补写），3080Ti 是实验五 v2 评测用的。
4. 错误码怎么设计的？→ 5 位码前三位就是 HTTP 状态码：400xx 输入错（40001 图坏）、404xx 找不到（40401 类目不存在、40403 非法工具）、500xx 服务不可用（50001）。
5. 工具调用 100% 是纯模型吗？→ 不是，纯模型 90%（9/10，唯一差错是查询词多带了个「的」），加参数规范化后 100%，3080Ti 与 5060 两卡一致。
6. v4 的 82.5% 是搜库命中率吗？→ 不是，是 40 道协议考题里工具、参数、安全回复全对的综合通过率（33/40）；7 题未通过分别是 3 题多带量词「一双」、3 题问类目直接口头答、1 题缺历史注入。
7. 为什么点评不提价格？→ 数据库 12 列本身没有价格和销量字段，安全闸专门拦截乱报价，防止大模型胡编。""")

    OUT_PPTX.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT_PPTX))
    print(f"PPTX 生成成功: {OUT_PPTX} ({OUT_PPTX.stat().st_size / 1024 / 1024:.2f} MB, {len(prs.slides)} 页)")


if __name__ == "__main__":
    build()
