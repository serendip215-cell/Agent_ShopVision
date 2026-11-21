# -*- coding: utf-8 -*-
"""重构 ShopVision 期末答辩 PPT（19 页可编辑 PPTX，严格对齐实验一~五报告与仓库凭证）。

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
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[3]
FIGS5 = ROOT / "docs" / "typ" / "figs_exp5"
FIGS = ROOT / "docs" / "typ" / "figs"
FIGURES = ROOT / "docs" / "typ" / "figures"
ASSETS = Path(__file__).resolve().parent / "assets"
OUT_PPTX = ROOT / "docs" / "交付材料" / "期末_第23组" / "03_开发介绍视频与PPT" / "项目开发介绍_第23组.pptx"

# ===== ShopVision 品牌视觉色板（与前端 UI、新版极简海报 100% 统一） =====
C_DEEP = RGBColor(0x10, 0x26, 0x2A)       # 深海墨青（封面/章节/标题主墨）
C_DEEP2 = RGBColor(0x18, 0x38, 0x3E)      # 浅一级深青（深色页卡片/装饰）
C_DEEP3 = RGBColor(0x21, 0x48, 0x4F)      # 边框/细装饰
C_CANVAS = RGBColor(0xF5, 0xF7, 0xF7)     # 温润纸瓷白画布
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
    bg = slide.background
    fill = bg.fill
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
                bullet_color: RGBColor = C_TEAL, spacing: float = 6.0, line_spacing: float = 1.28):
    """添加带粗体引导词的清晰要点列表。"""
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
    """按原图真实长宽比等比居中放入指定区域，不拉伸、不裁切。"""
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
    add_text(slide, x + 0.12, y + 0.13, w - 0.24, 0.50, value,
             size=val_size, bold=True, color=accent if accent == C_WARM else C_DEEP,
             align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
    add_text(slide, x + 0.10, y + 0.64, w - 0.20, 0.28, label,
             size=12.5, bold=True, color=C_TEXT, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
    if sub:
        add_text(slide, x + 0.10, y + 0.90, w - 0.20, h - 0.96, sub,
                 size=10.0, color=C_MUTED, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.TOP, line_spacing=1.2)


def add_header_footer(slide, slide_num: int, eyebrow: str, title: str):
    set_slide_bg(slide, C_CANVAS)
    # 顶部细饰条
    add_rect(slide, 0, 0, 13.333, 0.06, C_TEAL)
    # 英文眉标 + 大标题
    add_text(slide, 0.60, 0.24, 9.0, 0.26, eyebrow, size=10.5, bold=True,
             color=C_TEAL, font_name=FONT_MONO)
    add_text(slide, 0.60, 0.48, 12.1, 0.52, title, size=25, bold=True, color=C_DEEP)
    add_rect(slide, 0.60, 1.04, 12.133, 0.015, C_LINE)
    # 页脚
    add_rect(slide, 0.60, 7.05, 12.133, 0.012, C_LINE)
    add_text(slide, 0.60, 7.10, 6.0, 0.28, "ShopVision · 第 23 组项目开发介绍（实验一 → 实验五）",
             size=10, color=C_MUTED)
    add_text(slide, 11.4, 7.10, 1.33, 0.28, f"{slide_num:02d} / {TOTAL_SLIDES:02d}",
             size=10, bold=True, color=C_TEAL, align=PP_ALIGN.RIGHT, font_name=FONT_MONO)


def add_section_divider(prs, slide_num: int, sec_no: str, title: str, subtitle: str,
                        bullets: list[tuple[str, str]], notes: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, C_DEEP)
    # 柔和几何装饰圆
    add_oval(slide, 9.6, -1.6, 5.4, 5.4, C_DEEP2)
    add_oval(slide, -1.5, 5.2, 3.6, 3.6, C_DEEP2)
    add_rect(slide, 0.72, 1.05, 0.90, 0.06, C_WARM_LIGHT)

    add_text(slide, 0.72, 1.22, 3.0, 0.90, sec_no, size=56, bold=True,
             color=C_WARM_LIGHT, font_name=FONT_MONO)
    add_text(slide, 0.72, 2.20, 11.8, 0.68, title, size=35, bold=True, color=C_WHITE)
    add_text(slide, 0.72, 2.94, 11.2, 0.40, subtitle, size=16, color=C_LIGHT_TXT)

    # 要点卡片（充裕高度防溢出）
    add_rect(slide, 0.72, 3.58, 11.88, 3.08, C_DEEP2, border=C_DEEP3, radius=0.05, border_pt=1.0)
    add_bullets(slide, 0.98, 3.80, 11.36, 2.68, bullets, size=13.5,
                color=C_LIGHT_TXT, lead_color=C_WHITE, bullet_color=C_WARM_LIGHT,
                spacing=7.5, line_spacing=1.26)

    add_text(slide, 0.72, 7.02, 6.0, 0.30, "ShopVision · 第 23 组项目开发介绍",
             size=10.5, color=RGBColor(0x95, 0xB4, 0xB8))
    add_text(slide, 11.4, 7.02, 1.22, 0.30, f"{slide_num:02d} / {TOTAL_SLIDES:02d}",
             size=10.5, bold=True, color=C_WARM_LIGHT, align=PP_ALIGN.RIGHT, font_name=FONT_MONO)
    set_notes(slide, notes)
    return slide


def set_notes(slide, text: str):
    ns = slide.notes_slide
    tf = ns.notes_text_frame
    tf.text = text.strip()


def set_cell_border(cell, color_hex="D4DFE2", width="12700"):
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
    add_text(s1, 0.8, 3.16, 11.733, 0.44, "三源清洗数据 → 双塔全参微调 → TensorRT 加速 → Web 全栈 → Qwen3-4B 对话导购",
             size=16, color=C_LIGHT_TXT, align=PP_ALIGN.CENTER)

    # 四张核心成果卡
    cards1 = [
        ("9,393", "清洗图文商品库", "三源 10,165 → 9 类 9,393"),
        ("58.67%", "图文检索 R@1", "基线 37.37% · R@10 96.90%"),
        ("−57.73%", "图像塔 TRT 延迟", "4.59 → 1.94 ms（batch=1）"),
        ("90% → 100%", "Agent 工具调用率", "纯模型 90% · 规范化后 100%"),
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
    add_text(s1, 0.8, 6.68, 11.733, 0.30, "2026 年 11 月  ·  全部实验凭证与代码已入库可复现",
             size=11.5, color=RGBColor(0x95, 0xB4, 0xB8), align=PP_ALIGN.CENTER)

    set_notes(s1, """【开场白，约 45 秒】
各位老师、各位同学，大家好，我是第 23 组的汇报人。我们组的项目是《ShopVision：电商商品多模态推荐与上架 Agent》。

先用一句话概括我们做的系统：这是一个融合跨模态检索与多轮对话的电商智能导购与上架核验平台。用户可以输入一句中文描述找商品、上传一张图找相似款或核验图文是否一致，还可以像跟导购聊天一样连续追问——例如先说「帮我找运动鞋」，再追问「要白色的」，系统会自动继承类目并合并查询。

整个工程由五个阶段层层递进完成：实验一做三源数据采集与清洗，实验二做 Chinese-CLIP 双塔全参微调，实验三做 ONNX 与 TensorRT 推理加速，实验四搭建 FastAPI + React 19 全栈系统，实验五接入 Qwen3-4B QLoRA 对话导购 Agent。

屏幕中间四个数字是我们最核心的实测结果：9,393 条清洗后的九类商品图文数据；测试集图文检索 R@1 从 37.37% 提升到 58.67%；TensorRT FP16 让图像塔 batch=1 延迟降低 57.73%；Agent 工具调用纯模型达到 90%，加入参数规范化后达到 100%。所有指标均对应仓库内的原始凭证，下面逐章汇报。""")

    # =========================================================================
    # SLIDE 2: 项目总览
    # =========================================================================
    s2 = prs.slides.add_slide(blank)
    add_header_footer(s2, 2, "PROJECT OVERVIEW", "项目总览：五个实验，一条可复现工程链路")

    steps2 = [
        ("1", "实验一 · 数据建设", "MUGE + 苏宁 + Amazon 译文三源 10,165 条，经视觉清洗得 9 类 9,393 条"),
        ("2", "实验二 · 双塔微调", "Chinese-CLIP ViT-B-16 全参微调（AMP + 梯度检查点），R@1 37.37% → 58.67%"),
        ("3", "实验三 · 推理加速", "ONNX 导出 + 图层级 FP16 + TensorRT 引擎，batch=1 延迟 4.59 → 1.94 ms"),
        ("4", "实验四 · Web 系统", "React 19 + FastAPI + FAISS + Celery/Redis，12 个 API 路径、8 个页面"),
        ("5", "实验五 · 对话 Agent", "Qwen3-4B QLoRA 4-bit + LangChain 四工具路由，支持多轮槽位继承与安全闸"),
    ]
    for i, (num, stitle, sdesc) in enumerate(steps2):
        sy = 1.24 + i * 1.06
        add_rect(s2, 0.60, sy, 5.75, 0.92, C_WHITE, border=C_LINE, radius=0.08, border_pt=0.8)
        badge_c = C_WARM if i == 4 else C_TEAL
        add_oval(s2, 0.74, sy + 0.22, 0.48, 0.48, badge_c)
        add_text(s2, 0.74, sy + 0.22, 0.48, 0.48, num, size=16, bold=True, color=C_WHITE,
                 align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE, font_name=FONT_MONO)
        add_text(s2, 1.34, sy + 0.08, 4.88, 0.32, stitle, size=14.5, bold=True, color=C_DEEP)
        add_text(s2, 1.34, sy + 0.41, 4.88, 0.44, sdesc, size=11.5, color=C_MUTED, line_spacing=1.2)

    # 右上：全新纠偏后的闭环架构图
    add_img_fit(s2, ASSETS / "closed_loop_v2.png", 6.55, 1.24, 6.18, 2.86,
                bg_card=True, caption="实验 1 → 5 数据流与模型/服务复用闭环")

    # 右中：4 格数字卡
    kpis2 = [
        ("9,393", "清洗图文库", "三源 9 大类目", C_TEAL),
        ("58.67%", "test R@1", "934 对 · +21.3pp", C_TEAL),
        ("−57.73%", "TRT 图像塔", "GPU 训练机 batch=1", C_TEAL),
        ("82.5%", "v4 综合通过", "40 条对话 33/40", C_WARM),
    ]
    kw, kg = 1.44, 0.14
    for i, (v, l, sb, ac) in enumerate(kpis2):
        add_kpi_card(s2, 6.55 + i * (kw + kg), 4.24, kw, 1.42, v, l, sb, accent=ac, val_size=17.5)

    # 右下总结框
    add_rect(s2, 6.55, 5.80, 6.18, 1.06, C_TEAL_SOFT, border=C_TEAL, radius=0.06, border_pt=0.8)
    add_text(s2, 6.72, 5.90, 5.84, 0.88,
             "工程闭环纪律：每一阶段的产物直接成为下一阶段的输入——清洗数据 → 全参微调权重 → ONNX/TRT 引擎 → HTTP API → Agent 工具。训练日志、评测 JSON 与测速快照全部归档入库，支持独立复现。",
             size=11.8, color=C_DEEP, line_spacing=1.32)

    set_notes(s2, """【总览页，约 1 分钟】
这一页是整个项目的全貌地图。左边五个模块串联起五个实验：

实验一，三源数据建设：整合 MUGE、苏宁易购自研爬取和 Amazon DeepL 译文共 10,165 条商品，经两层去重和视觉清洗后得到 9 类 9,393 条干净图文对。

实验二，双塔全参微调：用清洗数据对 Chinese-CLIP ViT-B-16 做 AMP 混合精度加梯度检查点的全参对比学习，测试集 R@1 从 37.37% 提升到 58.67%。

实验三，推理加速：导出双塔 ONNX，走图层级 FP16 转 TensorRT，在 GPU 训练机同硬件配对测速下将 batch=1 图像塔延迟从 4.59 毫秒降到 1.94 毫秒。

实验四，Web 全栈系统：把模型和 512 维 FAISS 索引封装成 FastAPI 的 12 个路径（含 Celery + Redis 异步队列）和 React 19 的 8 个前端页面。

实验五，对话导购 Agent：基于 Qwen3-4B 做 4-bit QLoRA 微调，接入 LangChain 四工具白名单，实现多轮槽位继承和安全闸控管。

右上图清晰展示了数据与模型的复用闭环：每一阶段的输出都是下一阶段的输入，所有凭证全部入库可复查。""")

    # =========================================================================
    # SLIDE 3: 章节页 01 实验一
    # =========================================================================
    add_section_divider(
        prs, 3, "01", "实验一 · 多源数据采集与清洗",
        "构建高质量、可追溯、防泄漏的中文电商九类商品图文数据集",
        [
            ("三源数据获取：", "MUGE（4,704 条）+ 苏宁易购合规爬取（4,303 条）+ Amazon DeepL 中文化（1,158 条），合计 10,165 条图文对"),
            ("两层去重与视觉清洗：", "标题规范化 + SHA-256 图片指纹去重；视觉模型按 0.72 阈值审核主体并补全细分类/颜色/材质，剔除 765 条异类"),
            ("防泄漏切分与统一模板：", "按 MD5(item_id) 8:1:1 划分（7,520 / 939 / 934），训练与检索索引共用 build_product_text 模板"),
            ("标准落盘产出：", "data/processed_data_cleaning/（9 类 9,393 条，总体清洗通过率 92.4%，全流程留痕可复核）"),
        ],
        """【章节过渡，约 25 秒】
下面进入实验一：多源数据采集与清洗。我们的项目遵循以数据为中心的思路——如果底层数据混杂脏图和错类，后面微调和 Agent 都会受牵连。

实验一整合了 MUGE、苏宁易购和 Amazon 译文三个来源共 10,165 条商品，经过严格去重与视觉清洗后产出 9 类 9,393 条数据，后续四个实验全部建立在这份数据之上。"""
    )

    # =========================================================================
    # SLIDE 4: 实验一详细页
    # =========================================================================
    s4 = prs.slides.add_slide(blank)
    add_header_footer(s4, 4, "EXPERIMENT 01 · DATA ENGINEERING", "实验一：三源采集、视觉清洗与防泄漏数据集")

    # 左侧上半：清洗流水线卡片
    add_rect(s4, 0.60, 1.24, 6.20, 2.38, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s4, 0.80, 1.36, 5.80, 0.34, "自动化采集与两层清洗流水线（全流程 CSV / JSONL 留痕）",
             size=14, bold=True, color=C_DEEP)
    add_bullets(s4, 0.80, 1.74, 5.80, 1.80, [
        ("三源整合：", "MUGE（4,704）+ 自研爬虫 crawl_suning.py（4,303）+ DeepL 翻译 Amazon（1,158）→ 统一 12 字段标准 schema"),
        ("规则与指纹质检：", "剥离容量/型号/颜色变体判重 + 全库 SHA-256 图片指纹复用；check_product_fields 核验图片全部可读"),
        ("视觉审核与增强：", "视觉模型按 0.72 阈值剔除果冻/书架/袜子等 765 条异类，补全细分类/颜色/材质，并支持 ISNet 商品抠图"),
    ], size=12, spacing=6.5, line_spacing=1.26)

    # 左侧中部：防泄漏划分表
    add_rect(s4, 0.60, 3.78, 6.20, 1.72, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s4, 0.80, 3.88, 5.80, 0.32, "按 MD5(item_id) 8:1:1 防泄漏划分（9,393 条清洗通过集）",
             size=13.5, bold=True, color=C_DEEP)
    splits = [
        ("train", "7,520", "80.1%", "双塔对比学习微调"),
        ("valid", "939", "10.0%", "超参监控与早停判定"),
        ("test", "934", "9.9%", "最终评测与实验三精度核验"),
    ]
    for i, (sn, cnt, pct, use) in enumerate(splits):
        sx = 0.80 + i * 1.98
        add_rect(s4, sx, 4.26, 1.84, 1.08, C_TEAL_SOFT if i < 2 else C_WARM_SOFT, radius=0.08)
        add_text(s4, sx + 0.06, 4.32, 1.72, 0.30, f"{sn}  ({pct})",
                 size=11.5, bold=True, color=C_TEAL if i < 2 else C_WARM, align=PP_ALIGN.CENTER, font_name=FONT_MONO)
        add_text(s4, sx + 0.06, 4.62, 1.72, 0.34, cnt,
                 size=20, bold=True, color=C_DEEP, align=PP_ALIGN.CENTER)
        add_text(s4, sx + 0.06, 4.98, 1.72, 0.30, use,
                 size=9.8, color=C_MUTED, align=PP_ALIGN.CENTER)

    # 左侧底部说明条
    add_rect(s4, 0.60, 5.64, 6.20, 1.22, C_TEAL_SOFT, border=C_TEAL, radius=0.06, border_pt=0.8)
    add_text(s4, 0.80, 5.74, 5.80, 1.02,
             "关键工程约束：① 同一商品的多张图片因 MD5(item_id) 确定性哈希永不跨集合，杜绝数据泄漏；② 训练文本与建 FAISS 索引共用同一 build_product_text 五段模板（大类/细分类/颜色/材质/标题），确保训练与线上分布一致；③ 全库不含个人隐私，爬取限速合规。",
             size=11.5, color=C_DEEP, line_spacing=1.32)

    # 右侧上下两张真实图表（含苏宁三源图 + 九类通过率图）
    add_img_fit(s4, FIGS / "fig_sources.png", 7.00, 1.24, 5.73, 2.74,
                bg_card=True, caption="三源原始数据规模对比（MUGE 4,704 / 苏宁 4,303 / Amazon 1,158）")
    add_img_fit(s4, FIGS / "fig_passrate.png", 7.00, 4.12, 5.73, 2.74,
                bg_card=True, caption="九大商品类目视觉清洗通过率（总体 92.4%，水杯剔除异类最多）")

    set_notes(s4, """【实验一内容页，约 1 分 20 秒】
实验一解决的是高质量多模态数据源头问题。先看右上图，我们整合了三个来源：MUGE 公开中文图文 4,704 条、自研合规爬虫 crawl_suning.py 采集的苏宁易购 4,303 条，以及经 DeepL 分字段中文化的 Amazon 1,158 条，合计 10,165 条商品、统一到 9 个大类和固定 12 列 schema。

原始数据存在重复变体和错类混入，所以我们做了两层去重和两层清洗：规则层剥离容量、型号和颜色尾巴做标题判重，并用 SHA-256 指纹避免同一张图重复落盘；视觉审核层按 0.72 置信度阈值逐图检查主体，把果冻、书架、水杯类里误收的袜子等 765 条异类剔除并写入审计日志，同时补全细分类、颜色和材质。看右下图，总体清洗通过率 92.4%，清洗后最终得到 9,393 条（其中鞋 3,219 条最多，家居用品 264 条最少）。

左下角是防泄漏划分：在脚本 build_retrieval_dataset.py 里，我们按 item_id 的 MD5 哈希做 8:1:1 切分，得到 7,520 训练、939 验证、934 测试。这样同一商品的多张图绝不会一边进训练集一边进测试集，保证评测分数真实可信。并且训练文本和建索引文本共用同一 build_product_text 函数，避免分布漂移。""")

    # =========================================================================
    # SLIDE 5: 章节页 02 实验二
    # =========================================================================
    add_section_divider(
        prs, 5, "02", "实验二 · Chinese-CLIP 双塔全参微调",
        "以对比学习对齐中文商品属性描述与商品图像，并通过三组对照验证清洗增益",
        [
            ("双塔模型选型：", "视觉塔 ViT-B-16 + 文本塔 RoBERTa-wwm-ext-base-chinese，输出 512 维 L2 归一化跨模态向量"),
            ("全参训练策略：", "采用双塔全参数微调（AMP 混合精度 + 梯度检查点，lr=1e-5），并非冻结或 LoRA；3 轮 705 步稳定收敛"),
            ("三组严谨消融：", "预训练零样本基线（37.37%）vs 未清洗直训（50.96%）vs 清洗后微调（58.67%），清晰拆解微调与清洗各自贡献"),
            ("索引同源重建：", "以最优权重 epoch3.pt 重编码全部 9,393 条商品并重建 FAISS 索引，写入 data/index_data_finetuned/"),
        ],
        """【章节过渡，约 25 秒】
数据洗干净之后，实验二解决核心的跨模态检索能力：怎么让模型准确把一张商品图和一句中文属性描述映射到同一 512 维向量空间。

这里特别明确我们的技术路线：实验二对 Chinese-CLIP ViT-B-16 采用了 AMP 混合精度加梯度检查点的全参微调，在本组 RTX 5060 Ti 8GB 训练机上 6 分钟完成，并通过三组对照实验量化验证了数据清洗的真实增益。注意实验二没有用 LoRA，QLoRA 用在后面实验五的 4B 大语言模型上。"""
    )

    # =========================================================================
    # SLIDE 6: 实验二详细页（全面纠偏 + 换回真正三组对照图 fig_recall.png）
    # =========================================================================
    s6 = prs.slides.add_slide(blank)
    add_header_footer(s6, 6, "EXPERIMENT 02 · FULL FINE-TUNING", "实验二：Chinese-CLIP 双塔全参微调与三组消融对照")

    # 左上：真正的三组对照图 fig_recall.png（彻底替换旧 PPT 错贴的实验三图！）
    add_img_fit(s6, FIGS / "fig_recall.png", 0.60, 1.24, 6.45, 2.70,
                bg_card=True, caption="三组消融对照（test 934 对）：预训练基线 vs 未清洗直训 vs 清洗数据微调")

    # 左下：训练曲线 fig_curves.png
    add_img_fit(s6, FIGS / "fig_curves.png", 0.60, 4.08, 6.45, 2.78,
                bg_card=True, caption="验证集 Loss 单调降至 0.1403（batch 内 32 候选两路准确率升至 94.5%+）")

    # 右上：核心提升高亮卡
    add_kpi_card(s6, 7.25, 1.24, 5.48, 1.26, "37.37% → 58.67%",
                 "test 934 对文搜图 R@1（+21.30pp，相对 +57.0%）",
                 "R@5: 89.08%   |   R@10: 96.90%   |   mean_recall: 63.53 → 81.55",
                 accent=C_TEAL, val_size=27)

    # 右中：真实全参训练配置（严格对照 params_2026-10-18-12-27-38.txt）
    add_rect(s6, 7.25, 2.62, 5.48, 2.26, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s6, 7.45, 2.71, 5.08, 0.30, "实际训练配置（本组训练机，非云平台，全参微调）",
             size=13, bold=True, color=C_DEEP)
    add_bullets(s6, 7.45, 3.04, 5.08, 1.78, [
        ("环境与硬件：", "Win11 + WSL2 + Docker（pytorch:2.7.1-cuda12.8），本组 RTX 5060 Ti 8GB 单卡"),
        ("微调方式：", "双塔全参微调（freeze_vision=False），启用 AMP 混合精度 + grad_checkpointing"),
        ("核心超参：", "batch=32、lr=1e-5、wd=0.001、warmup=100、seed=123；3 epoch / 705 步约 6 分钟"),
        ("工程排坑：", "WSL2 下 NCCL 通信挂死 → 本地补丁（NoDDP + --skip-aggregate）单卡跑通"),
    ], size=10.5, spacing=3.5, line_spacing=1.20)

    # 右下：三组消融贡献拆解（严格对照 05-未清洗数据对照组.md）
    add_rect(s6, 7.25, 5.00, 5.48, 1.88, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_text(s6, 7.45, 5.09, 5.08, 0.28, "三组对照拆解（同一 test 934 题，质量优于数量）",
             size=12.8, bold=True, color=C_WARM)
    add_bullets(s6, 7.45, 5.41, 5.08, 1.40, [
        ("微调本身增益（约 64%）：", "零样本 37.37% → 未清洗直训（10,165 条）50.96%，净增 +13.59pp"),
        ("视觉清洗贡献（约 36%）：", "未清洗 50.96% → 清洗微调（9,393 条）58.67%，少 772 条反多涨 +7.71pp"),
        ("索引同源重建：", "以 epoch3.pt 重编码 9,393 条全库并重建 FAISS 索引，线上与训练一致"),
    ], size=10.5, lead_color=C_DEEP, bullet_color=C_WARM, spacing=3.5, line_spacing=1.20)

    set_notes(s6, """【实验二内容页，约 1 分 40 秒】
实验二是整个系统检索精度的核心。我们选用 Chinese-CLIP ViT-B-16，视觉塔是 ViT-B-16，文本塔是 RoBERTa-wwm-ext-base-chinese，两路特征 L2 归一化后以双向 InfoNCE 对比损失联合优化。

先说清楚训练方式和环境——我们在实验二用的是全参数微调，而不是冻结或 LoRA：因为电商属性域和通用图文域差异较大，双塔共 1.88 亿参数在本组 RTX 5060 Ti 8GB 显卡上，配合 AMP 混合精度和梯度检查点，batch=32、学习率 1e-5，跑 3 个 epoch、705 步只花了约 6 分钟就稳定收敛。中间踩过 WSL2 下 NCCL 集合通信挂死的坑，我们打了三处本地补丁，用 NoDDP 包装保留 module. 前缀并启用 --skip-aggregate，实现纯单卡零侵入训练。

看左上角的三组对照柱状图，蓝色是预训练零样本基线，R@1 为 37.37%；橙色是用清洗前 10,165 条脏数据直接微调，R@1 到 50.96%，说明微调本身贡献了 +13.59 个百分点（占总提升约 64%）；绿色是用清洗后 9,393 条干净数据同配方微调，R@1 冲到 58.67%，样本少了 772 条，反而再净增 +7.71 个百分点（占总提升约 36%），强有力验证了“数据质量优于数量”。R@5 达 89.08%，R@10 达 96.90%。

看左下训练曲线，验证集 loss 单调下降到 0.1403，batch 内 32 候选口径的图文两路准确率稳步上升到 94.5% 以上，未见明显过拟合。最后用 epoch3.pt 重编码全库并重建 FAISS 索引。""")

    # =========================================================================
    # SLIDE 7: 章节页 03 实验三
    # =========================================================================
    add_section_divider(
        prs, 7, "03", "实验三 · 模型优化与 TensorRT 推理加速",
        "系统评估动态量化与推理加速路线，在严控精度差前提下实现推理速度翻倍",
        [
            ("量化探索与止损（3.1.1）：", "实测 FP32 / FP16 / INT8 / per-channel / 分塔 6 种配置，动态 INT8 精度掉 −13.06pp（超 ≤2% 阈值），果断冻结留档"),
            ("加速主线（3.1.4 & 3.2.1）：", "PyTorch 微调权重 → ONNX FP32 导出 → 图层级 FP16 转换 → TensorRT 引擎算子融合与 kernel 重写"),
            ("双口径严格核验：", "速度在 GPU 训练机（torch 2.7.1+cu128 / TensorRT 10.x）做同精度配对测速（暖机 10 次取 20 次中位数）；精度在 934 条 test 集对同源 FP32 复算"),
            ("完整凭证归档：", "原始测量 JSON、9 张 450 DPI 中文图表与复算脚本归档于 evaluation/retrieval/results/runs/"),
        ],
        """【章节过渡，约 25 秒】
模型训好后，实验三解决线上部署的推理效率问题。我们先如实探索了动态 INT8 量化，测了 6 种配置，但最好也掉了 13 个百分点，达不到任务书 2% 以内的精度红线，因此果断冻结量化、把全部数据留档，主线转向 ONNX 导出加 TensorRT FP16 计算图加速。

最终我们在 GPU 训练机上做同硬件配对测速，实现延迟砍半、吞吐翻倍，同时在 934 条测试集上逐后端核对检索精度几乎无损。"""
    )

    # =========================================================================
    # SLIDE 8: 实验三流水线与延迟
    # =========================================================================
    s8 = prs.slides.add_slide(blank)
    add_header_footer(s8, 8, "EXPERIMENT 03 · ACCELERATION PIPELINE", "实验三：双塔 ONNX 导出与 TensorRT FP16 加速")

    add_img_fit(s8, FIGS5 / "14_推理加速流水线.png", 0.60, 1.24, 5.10, 4.30,
                bg_card=True, caption="双塔导出 → 图层级 FP16 转换 → TensorRT 引擎 → 配对测速")

    add_rect(s8, 0.60, 5.68, 5.10, 1.18, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_text(s8, 0.78, 5.76, 4.74, 0.28, "关键避坑与导出约束", size=12.5, bold=True, color=C_WARM)
    add_text(s8, 0.78, 6.06, 4.74, 0.74,
             "直接对 PyTorch 模型 .half() 会触发 LayerNorm 混合精度报错，故先导 ONNX FP32 再做图层级 FP16（keep_io_types=False）；图像塔固定 224×224，文本塔保留动态 batch 与序列长度。",
             size=11.0, color=C_DEEP, line_spacing=1.28)

    add_img_fit(s8, FIGS5 / "10_延迟对比.png", 5.92, 1.24, 6.81, 3.86,
                bg_card=True, caption="三种加速后端 × 两档 batch 的图像塔中位延迟配对对比（预热 10 次 / 计时 20 次）")

    add_kpi_card(s8, 5.92, 5.26, 3.30, 1.60, "−57.73%",
                 "batch=1 延迟降低（目标 ≥40%）",
                 "配对基线 4.59 → TRT FP16 1.94 ms\nbatch=32：50.43 → 23.84 ms（−52.73%）",
                 accent=C_TEAL, val_size=28)
    add_kpi_card(s8, 9.43, 5.26, 3.30, 1.60, "2.366×",
                 "batch=1 加速比（目标 ≥1.2×）",
                 "batch=32 加速比 2.115×\n统计口径：图像塔 forward（同硬件配对）",
                 accent=C_WARM, val_size=28)

    set_notes(s8, """【实验三流水线与延迟页，约 1 分 20 秒】
先看左边的加速流水线：从实验二产出的 epoch3.pt 出发，分别导出图像塔和文本塔的 FP32 ONNX，将训练框架与推理后端解耦；然后做图层级 FP16 转换——这里踩过一个坑，直接调 PyTorch 的 .half() 会导致 LayerNorm 混合精度报错，所以改用图层级转换并保留输入输出兼容；最后交给 TensorRT 做算子融合和 kernel 重写。

看右边的延迟对比柱状图，涵盖 ORT-CPU、ORT-CUDA 和 TensorRT 三个后端在 batch=1 与 batch=32 下的配对实测。所有 GPU 速度对比都在同一台 GPU 训练机（torch 2.7.1+cu128、TensorRT 10.x）上，采用各组配对的同精度 PyTorch 基线、预热 10 次取 20 次中位数（原始 JSON 未独立记录 GPU 型号，按实验三报告口径不补写）。可以看到 ORT-CPU 和 ORT-CUDA 提速有限（甚至大 batch 下受访存回退影响略慢），而 TensorRT FP16 带来实质飞跃：batch=1 延迟从 4.59 毫秒降至 1.94 毫秒，降低 57.73%、加速 2.366 倍；batch=32 从 50.43 降至 23.84 毫秒，降低 52.73%、加速 2.115 倍，远超任务书延迟降低 ≥40% 和加速比 ≥1.2 倍的要求。

需要强调统计边界：这组数字统计的是图像塔 forward 耗时，不扩写为完整 HTTP 请求耗时。""")

    # =========================================================================
    # SLIDE 9: 实验三收益与精度代价
    # =========================================================================
    s9 = prs.slides.add_slide(blank)
    add_header_footer(s9, 9, "EXPERIMENT 03 · TRADE-OFF ANALYSIS", "实验三：加速收益、文件体积与精度一致性核验")

    add_img_fit(s9, FIGS5 / "11_吞吐对比.png", 0.60, 1.24, 3.92, 2.74,
                bg_card=True, caption="图像塔吞吐对比（samples/s）")
    add_img_fit(s9, FIGS5 / "12_精度误差热力图.png", 4.70, 1.24, 3.92, 2.74,
                bg_card=True, caption="后端 × R@K 精度误差热力图（±1pp 色标）")
    add_img_fit(s9, FIGS5 / "13_模型文件大小.png", 8.81, 1.24, 3.92, 2.74,
                bg_card=True, caption="文本塔 ONNX 与双塔纯权重体积（MiB）")

    add_kpi_card(s9, 0.60, 4.14, 3.92, 1.56, "+136.58%",
                 "batch=1 吞吐提升（目标 ≥50%）",
                 "batch=32 吞吐提升 +111.52%\n算子融合与 kernel 重写驱动",
                 accent=C_TEAL, val_size=28)
    add_kpi_card(s9, 4.70, 4.14, 3.92, 1.56, "−0.4283pp",
                 "TRT FP16 双塔 R@1 净差",
                 "自研 FP32 基线 58.5653% → 58.1370%\n同时满足 3.1.4（≤1pp）与 3.2.1（≤0.5pp）",
                 accent=C_WARM, val_size=28)
    add_kpi_card(s9, 8.81, 4.14, 3.92, 1.56, "≈ 50.0%",
                 "FP16 权重文件体积减半",
                 "双塔纯权重 718.29 → 359.21 MiB\n文本塔 ONNX 389.58 → 194.97 MiB",
                 accent=C_TEAL, val_size=28)

    add_rect(s9, 0.60, 5.84, 12.133, 1.04, C_TEAL_SOFT, border=C_TEAL, radius=0.06, border_pt=0.8)
    add_text(s9, 0.80, 5.93, 11.73, 0.88,
             "严谨口径声明：① 精度对比以自研评测同源 PyTorch FP32（R@1 58.5653%）为共同基线，不混用实验二官方脚本 58.67%；速度对比在 GPU 训练机做同精度配对测速（源 JSON 未单独记录 GPU 型号，按原凭证口径不补写）。② 推理加速不改网络架构（双塔 1.88 亿参数、42.63 GFLOPs，图像塔占 FLOPs 约 79%）。③ 3.1.1 动态 INT8 最好掉 13.06pp 已冻结；TRT 逐样本排名未测不声称。",
             size=11.2, color=C_DEEP, line_spacing=1.30)

    set_notes(s9, """【实验三收益与代价页，约 1 分 10 秒】
这页把加速带来的收益与精度代价放在一起权衡。

先看三项收益：左上吞吐图，batch=1 吞吐提升 136.58%，batch=32 提升 111.52%，均大幅超过 50% 的目标；右上体积图，模型文件体积严格区分对象标注——双塔纯权重从 718.29 MiB 降到 359.21 MiB，文本塔 ONNX 从 389.58 降到 194.97 MiB，均缩小一半，部署分发更轻便（注：文件体积不等于运行时峰值显存）。

再看精度代价：中间的热力图基于 934 条测试查询，以自研同源 PyTorch FP32（R@1 58.5653%）为共同基线逐后端核验。ORT-CPU FP32 误差为 0；TensorRT FP16 的 R@1 净差只有 -0.4283 个百分点（相当于 934 条里净差约 4 条），R@5 误差为 0，同时满足 3.1.4 的 ≤1pp 和 3.2.1 的 ≤0.5pp 要求。

底部我们守住三条诚实口径：第一，速度对比用同精度配对基线，精度对比用同源 FP32 基线，不混用；第二，推理加速不改网络架构，1.88 亿参数和 42.63 GFLOPs 保持不变，其中图像塔占理论计算量约 79%，所以优先加速图像塔收益最高；第三，历史探索的动态 INT8 掉点 13.06pp 已冻结留档，且现有凭证不含 TRT 逐样本排名，我们不做未测声称。""")

    # =========================================================================
    # SLIDE 10: 章节页 04 实验四
    # =========================================================================
    add_section_divider(
        prs, 10, "04", "实验四 · Web 全栈系统与 API 工程化",
        "将跨模态模型与向量索引封装为高可测、可替换、带异步队列的全栈应用",
        [
            ("前后端分层架构：", "React 19 + Ant Design 8 页面前端（含实验五对话导购页）+ FastAPI 四层后端（接入/服务/能力/索引）"),
            ("稳定契约与错误码：", "全接口统一 {code, result, msg} 返回体；5 位错误码前三位即 HTTP 状态码（400xx / 404xx / 500xx）"),
            ("双接缝与异步队列：", "Encoder 占位/ONNX 一行配置切换，入库强制 ONNX 防脏向量；Celery + Redis 承接批量耗时任务"),
            ("测试与交付完备：", "12 个 OpenAPI 路径随包交付（openapi.json + API文档.md）；前端 npm test 21/21 与生产构建全通过"),
        ],
        """【章节过渡，约 25 秒】
前面三个实验都在模型与索引层，实验四把它们真正做成可点击、可联调、可部署的 Web 全栈系统。

后端采用 FastAPI 分层架构，统一返回体与 400/404/500 三档 5 位错误码，接入 Celery + Redis 异步队列，并在扩展实验五 Agent 后形成 12 个标准 API 路径；前端采用 React 19 + Ant Design 实现 8 个功能页面，也成了实验五对话导购的直接运行底座。"""
    )

    # =========================================================================
    # SLIDE 11: 实验四架构与接口
    # =========================================================================
    s11 = prs.slides.add_slide(blank)
    add_header_footer(s11, 11, "EXPERIMENT 04 · SYSTEM ARCHITECTURE", "实验四：四层系统架构与 12 路径 API 契约")

    add_img_fit(s11, FIGS5 / "01_系统架构.png", 0.60, 1.24, 7.15, 3.92,
                bg_card=True, caption="四层架构：浏览器（React 19）→ Vite 代理 → FastAPI 接入/服务/能力层 → ONNX 双塔与 512 维索引")

    add_rect(s11, 0.60, 5.30, 7.15, 1.58, C_WHITE, border=C_LINE, radius=0.06)
    add_bullets(s11, 0.78, 5.40, 6.80, 1.40, [
        ("双同形接缝：", "PlaceholderEncoder（SHA-256 确定性种子）与 OnnxEncoder 接口一致，改 .env 一行切换，前后端可并行开发"),
        ("数据卫生纪律：", "商品增量入库（/admin/items）强制校验真 ONNX，占位模式拒绝写入（50001），防随机向量污染真索引"),
        ("一键启停与质检：", "scripts/start_all.py 支持 --lan 局域网演示；CI 集成 black/ruff/mypy/pytest，前端 npm test 21/21 通过"),
    ], size=10.6, spacing=4.0, line_spacing=1.20)

    # 右侧：数字卡 + 接口清单
    add_kpi_card(s11, 7.98, 1.24, 2.28, 1.30, "12", "OpenAPI 路径数", "含同步/异步/Agent", accent=C_TEAL, val_size=30)
    add_kpi_card(s11, 10.45, 1.24, 2.28, 1.30, "8", "前端页面数", "React 19 + Antd", accent=C_WARM, val_size=30)

    add_rect(s11, 7.98, 2.70, 4.75, 4.16, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s11, 8.18, 2.82, 4.35, 0.34, "接口分组清单（统一前缀 /api/v1）",
             size=14, bold=True, color=C_DEEP)
    add_bullets(s11, 8.18, 3.22, 4.35, 2.85, [
        ("同步检索与核验（3）：", "/image（图像分类）、/text（文本检索）、/match（双链独立判类图文匹配）"),
        ("异步任务队列（3）：", "POST /tasks/image、POST /tasks/batch（上限 12 张）、GET /tasks/{task_id}，Celery + Redis 轮询，Redis 离线不影响同步接口"),
        ("对话 Agent（3）：", "POST /agent/chat、POST /agent/image、DELETE /agent/session/{session_id}"),
        ("入库与运维（3）：", "POST /admin/items、POST /admin/categories、GET /health；静态图片挂载直出"),
    ], size=11.5, spacing=7.5, line_spacing=1.25)

    add_rect(s11, 8.18, 6.18, 4.35, 0.52, C_TEAL_SOFT, radius=0.08)
    add_text(s11, 8.30, 6.23, 4.12, 0.42,
             "离线 openapi.json 与 API文档.md 随包入库，评审无需起服务即可查阅",
             size=10.2, bold=True, color=C_TEAL, valign=MSO_ANCHOR.MIDDLE)

    set_notes(s11, """【实验四架构页，约 1 分 20 秒】
实验四把模型封装成真正的四层工程架构：最左是 React 19 前端（经实验五扩展共 8 个页面），通过 Vite 代理和统一 Axios 拦截器访问后端 /api/v1；中间接入层负责参数校验与统一返回体 {code, result, msg}；服务层 MatchService 编排「编码 → 检索 → 组装」，完全不感知 HTTP，所以可以脱离网络做单元测试；底层通过 Encoder 和 IndexStore 两个可替换接缝读取 754MB 双塔 ONNX 与 512 维索引。

这里有三个核心工程设计：第一，错误码单一来源——5 位业务码前三位直接等于 HTTP 状态码，例如 40000/40001 对应 HTTP 400 参数或图像格式错，40400/40401/40403 对应 HTTP 404 资源、类别或工具不存在，50000/50001 对应 HTTP 500 服务端或模型不可用，前后端和文档共用一份 ErrorCode 枚举。

第二，编码器双同形接缝：占位编码器用输入内容 SHA-256 派生随机种子，改一行 .env 就能切换到真 ONNX，并且商品增量入库强制校验 ONNX 模式，防止占位随机向量污染索引。

第三，异步队列与同步解耦：批量图片分类走 Celery + Redis，单批上限 12 张，测试环境可配 ALWAYS_EAGER 同步跑单测；即使 Redis 不可达，只有异步提交报 50001，核心同步检索照常运行。后端测试历史记录 100 条、最新实测口径 83 条，前端 npm test 21/21 与构建全通过。""")

    # =========================================================================
    # SLIDE 12: 实验四真实页面展示（换掉旧 PPT 的两张空态图 + 彻底修正错误码口径！）
    # =========================================================================
    s12 = prs.slides.add_slide(blank)
    add_header_footer(s12, 12, "EXPERIMENT 04 · FRONTEND UI & ERROR HANDLING", "实验四：多模态工作台、真实识别与双链图文匹配")

    add_img_fit(s12, FIGURES / "01_首页.png", 0.60, 1.24, 3.86, 4.18,
                bg_card=True, caption="工作台首页：Find Similar + 9 类 9,393 索引概览")
    add_img_fit(s12, FIGURES / "02_图像分类_识别结果.png", 4.74, 1.24, 3.86, 4.18,
                bg_card=True, caption="图像分类实测：上传鞋图 → 判「鞋」+ 相似商品卡片")
    add_img_fit(s12, FIGURES / "04_图文匹配_并排.png", 8.87, 1.24, 3.86, 4.18,
                bg_card=True, caption="图文匹配并排：一致（鞋+白鞋）vs 不一致（鞋+包）")

    add_rect(s12, 0.60, 5.58, 12.133, 1.28, C_WHITE, border=C_LINE, radius=0.06)
    add_bullets(s12, 0.80, 5.68, 11.73, 1.10, [
        ("双链独立判类防循环论证：", "图文匹配页故意演示「鞋图 + 白色运动鞋（一致）」与「鞋图 + 双肩包（不一致）」——图像与文本两条链路各自独立判类后再比对大类，不用图去限文，真实体现双塔跨模态对齐机制。"),
        ("统一错误码中文映射（前三位 = HTTP 状态码）：", "400xx 参数/输入问题（如 40000 参数错、40001 图像损坏、40003 维度不匹配）；404xx 目标不存在（40401 类别不存在、40403 白名单外工具）；500xx 服务端异常（50001 模型或队列不可用），前端全部转为可读中文提示。"),
    ], size=11.6, spacing=6, line_spacing=1.26)

    set_notes(s12, """【实验四页面页，约 1 分钟】
这一页展示我们实际跑出来的三个代表性前端页面，风格统一采用 ShopVision 极简瓷青工作台设计。

左边是工作台首页，顶部展示 9,393 条索引、9 个类目和 512 维向量信息，支持直接从全局搜索框或类目卡片进入检索。

中间是图像分类页实测：上传一张白色运动鞋图片后，系统走真实 ONNX 图像塔编码并查询 FAISS，右侧直接给出识别大类「鞋」、各类置信度条以及按相似度排序的相似商品推荐卡片。

右边是图文匹配页的左右对照实测：左侧传鞋图配「白色运动鞋」，两条链路各自判类均为「鞋」，绿框提示「图文一致」；右侧故意传同一张鞋图但配文「双肩包」，图链路判「鞋」、文链路判「包」，橙框精准拦截「图文不一致」并列出各自参考商品。这里的关键设计是“不做以图限文”，两条链路独立编码独立判类，所以不会和稀泥。

同时前端 Axios 拦截器接管了全部异常：前三位直接对应 HTTP 状态码——400xx 如 40001 表示图像格式损坏、404xx 如 40401 表示类别不存在、40403 表示白名单外工具、500xx 如 50001 表示模型或队列不可用，页面绝不甩原始报错，全部映射为中文友好提示。""")

    # =========================================================================
    # SLIDE 13: 章节页 05 实验五
    # =========================================================================
    add_section_divider(
        prs, 13, "05", "实验五 · Qwen3-4B 对话导购 Agent",
        "小参数大模型 QLoRA 微调 + 受控四工具路由，实现事实可靠的多轮导购",
        [
            ("基座与微调选型：", "Qwen3-4B-Instruct-2507 + 4-bit NF4 QLoRA（r=16 / alpha=32 / dropout=0.05），8GB 显存可推理部署"),
            ("核心架构铁律：", "模型只负责意图解析、JSON 动作路由与结果点评；所有商品名称与属性一律由实验四双塔检索返回，绝不编造价格/销量"),
            ("三道运行时防线：", "四工具白名单 + 编辑距离纠错 + 类目/数量/查询词规范化 + 模型离线自动规则降级"),
            ("四代数据迭代与多轮能力：", "v1→v2→v3→v4 持续演进；同会话 8 条窗口 + ≤6 句摘要 + 类目槽位继承 + 图搜接话"),
        ],
        """【章节过渡，约 25 秒】
最后进入实验五：对话导购 Agent，也是整个项目的收官与亮点所在。

在这里我们才真正用到 QLoRA：基于 Qwen3-4B-Instruct-2507 做 4-bit 微调，配合 LangChain 封装实验四的检索接口。贯穿实验五最核心的原则只有一句——大模型只当“大脑”做意图路由和点评，商品事实完全交给双塔检索，绝不允许大模型凭空编造价格或商品信息。"""
    )

    # =========================================================================
    # SLIDE 14: 实验五微调与协议（彻底换上新绘 agent_pipeline_v2.png + 删掉价格穿帮口播！）
    # =========================================================================
    s14 = prs.slides.add_slide(blank)
    add_header_footer(s14, 14, "EXPERIMENT 05 · AGENT QLORA & PROTOCOL", "实验五：Qwen3-4B QLoRA 微调与两轮决策流水线")

    # 左侧：全新绘制的真正 Agent 流水线图（彻底替换错贴的实验二 LMDB 图！）
    add_img_fit(s14, ASSETS / "agent_pipeline_v2.png", 0.60, 1.24, 5.45, 5.62,
                bg_card=True, caption="实验五 Qwen3-4B QLoRA 微调与两轮安全决策流水线")

    # 右上：数据版本演进
    add_rect(s14, 6.26, 1.24, 6.47, 2.16, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s14, 6.46, 1.34, 6.07, 0.32, "四代 SFT 数据演进（问题驱动迭代）", size=14, bold=True, color=C_DEEP)
    add_bullets(s14, 6.46, 1.70, 6.07, 1.64, [
        ("v1（100 条）：", "tool_call 仅 15 条且全部明写「限制在X类」，模型只学会照抄且把 text_search 拼成 tool_search，纯模型 10 轮仅 10%"),
        ("v2（163 条）：", "扩充至 78 条无类目提示样本，逼模型从商品名推断 9 大类目 → 纯模型跃升至 90%，类目 100%"),
        ("v3 / v4 多轮：", "v3 引入四工具动作协议（440 条单轮）；v4 扩至 549 段 / 1,029 轮多轮对话（max_len 升至 2048，工具结果以「检索结果：」注入）"),
    ], size=11.4, spacing=5.5, line_spacing=1.24)

    # 右中：训练环境与跨机复验
    add_rect(s14, 6.26, 3.54, 6.47, 1.74, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s14, 6.46, 3.64, 6.07, 0.32, "云端训练与本地跨机复验（凭证见 docs/实验五/03, 09, 11, 12）",
             size=13.2, bold=True, color=C_DEEP)
    add_bullets(s14, 6.46, 3.98, 6.07, 1.24, [
        ("AutoDL 训练：", "v1 / v3 / v4 均在 AutoDL RTX 4090 48GB 完成（适配器约 64 MB）；v2 重训在 AutoDL RTX 3080Ti 12GB"),
        ("跨机稳定性：", "v2 在 RTX 3080Ti 与本组 RTX 5060 8GB 上评测结果完全一致，消除了 v1 时代的边界样本漂移"),
    ], size=11.4, spacing=5.5, line_spacing=1.24)

    # 右下：三张紧凑成本/耗时卡
    add_kpi_card(s14, 6.26, 5.42, 2.04, 1.44, "57.53 s", "v1 训练耗时", "3 epoch / 18 步", accent=C_TEAL, val_size=24)
    add_kpi_card(s14, 8.48, 5.42, 2.04, 1.44, "≈ ¥0.13", "v1 训练成本", "RTX 4090 ¥2.88/时", accent=C_WARM, val_size=24)
    add_kpi_card(s14, 10.69, 5.42, 2.04, 1.44, "520.2 s", "v4 多轮训练", "549 段 / max_len 2048", accent=C_TEAL, val_size=24)

    set_notes(s14, """【实验五微调页，约 1 分 40 秒】
实验五选型 Qwen3-4B-Instruct-2507：任务书里的候选大模型动辄几十 GB 显存，超出我们本地条件；4B 模型配合 4-bit NF4 QLoRA（r=16、alpha=32、dropout=0.05），训完适配器只有 64MB，本地 8GB 显存即可运行。

看左边这张实验五专属流水线图，核心铁律是两轮解耦：第一轮模型只负责听懂意图并输出结构化 JSON 动作，绝不直接生成商品；经过四工具白名单、编辑距离纠错和参数规范化后，通过 HTTP 回调实验四检索 API 查出真实商品；第二轮把真实商品以「检索结果：」前缀回喂给模型生成简短点评，并经过安全闸拦截。特别说明：我们商品表 12 列里本来就没有价格和销量字段，所以每一件展示商品的名称、类目与属性都来自真实商品库，缺失的价格与销量绝不编造。

右边是四代数据的迭代故事：v1 时 tool_call 只有 15 条而且句子里都明写了“限制在某类”，导致口语场景纯模型只有 10%，还常把 text_search 拼成 tool_search；v2 我们专门构造了 78 条去掉明写类目的样本，纯模型立刻飙到 90%；v3 加入四工具协议（440 条），v4 进一步构建 549 段共 1,029 轮多轮对话，把 max_len 从 512 提到 2048。训练都在 AutoDL 租卡完成：v1 只跑了 57.53 秒、花了一毛三，v4 多轮跑了 520.2 秒；v2 还在 3080Ti 和本组 5060 两台机器上做了跨机复验，结果完全一致。""")

    # =========================================================================
    # SLIDE 15: 工具调用评测
    # =========================================================================
    s15 = prs.slides.add_slide(blank)
    add_header_footer(s15, 15, "EXPERIMENT 05 · TOOL CALL EVALUATION", "工具调用评测：纯模型 90%，加参数规范化 100%")

    add_img_fit(s15, FIGS5 / "03_工具调用评测_纯模型90%.png", 0.60, 1.24, 5.95, 4.08,
                bg_card=True, caption="纯模型模式（无后处理）：9/10 = 90%（类目 10/10 = 100%）")
    add_img_fit(s15, FIGS5 / "03_工具调用评测_混合100%.png", 6.78, 1.24, 5.95, 4.08,
                bg_card=True, caption="模型 + 参数规范化（混合模式）：10/10 = 100%")

    add_rect(s15, 0.60, 5.48, 12.133, 1.38, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_bullets(s15, 0.80, 5.58, 11.73, 1.20, [
        ("严格口径红线：", "100% 是参数规范化（后处理清洗查询词、统一类目与数量词）的工程增益，不是纯模型能力——所有材料统一表述为「纯模型 90%，加参数规范化后 100%」。"),
        ("跨机一致与失败定位：", "RTX 3080Ti 与 RTX 5060 8GB 两机实测结果完全一致；纯模型唯一失败项为第 5 轮「有没有灰色的双肩包」，仅因查询词保留了助词「的」。"),
        ("小样本诚实注记：", "5.2 阶段验证集总体 75.76% 仅含 11 条样本（其中 tool_call 仅 1 条），不具统计代表性，工具调用准确率一律以本页 10 轮评测为准。"),
    ], size=11.3, lead_color=C_WARM, bullet_color=C_WARM, spacing=4.5, line_spacing=1.24)

    set_notes(s15, """【工具调用评测页，约 1 分 10 秒】
这一页是 v2 模型的 10 轮工具调用终端实测截图，也是我们口径纪律最严的一页。

左边是纯模型模式——不加任何后处理规则，模型输出什么直接评什么：10 轮对 9 轮，90%，已经达到任务书 ≥90% 的硬指标，且工具名、类目、top_k 三项全部 10/10。唯一扣分的是第 5 轮「有没有灰色的双肩包」，模型把「灰色的双肩包」里的「的」字带进了 query。

右边是加上运行时参数规范化后的混合模式——后处理把助词、量词和同义类目清洗归一后，10 轮全对，100%。

这里我们专门在页面下方标明红线：100% 是参数规范化后处理的功劳，绝不能写成模型本身能力，永远双口径并报。另外我们在 RTX 3080Ti 和本组 RTX 5060 8GB 上跑了完全一致的跨机复验，连失败项都是同一条。也顺带说明：5.2 节记录的验证集总体 75.76% 因为验证集只有 11 条、tool_call 仅 1 条，没有统计意义，工具调用准确率统一以这里 10 轮评测为准。""")

    # =========================================================================
    # SLIDE 16: 多轮对话评测（彻底纠偏 82.5% 指标含义与 7 条真实失败归因！）
    # =========================================================================
    s16 = prs.slides.add_slide(blank)
    add_header_footer(s16, 16, "EXPERIMENT 05 · DIALOGUE EVALUATION", "多轮对话评测：v3 单轮 vs v4 多轮（40 条协议集）")

    add_text(s16, 0.60, 1.18, 6.0, 0.30, "v4 多轮模型评测（40 条，凭证：data/agent/eval_v4_dialogue.json）",
             size=12.5, bold=True, color=C_DEEP)

    add_kpi_card(s16, 0.60, 1.54, 2.86, 1.54, "100%", "JSON 解析率", "40/40 全部合法\nv3 单轮为 95%（38/40）", accent=C_TEAL, val_size=30)
    add_kpi_card(s16, 3.64, 1.54, 2.86, 1.54, "90.0%", "动作准确率", "36/40 tool/reply 正确\nv3 单轮为 92.5%（37/40）", accent=C_TEAL, val_size=30)
    add_kpi_card(s16, 0.60, 3.24, 2.86, 1.54, "82.5%", "综合任务通过率", "33/40 工具参数+回复全达标\n（注：脚本级协议校验，非搜库）", accent=C_WARM, val_size=30)
    add_kpi_card(s16, 3.64, 3.24, 2.86, 1.54, "100%", "安全通过率", "36/36 无价格/销量臆测\n安全闸与回复策略零违规", accent=C_TEAL, val_size=30)

    add_rect(s16, 0.60, 4.94, 5.90, 1.92, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s16, 0.78, 5.04, 5.54, 0.28, "v3 vs v4 对比与剩余 7 条未通过的真实归因", size=12.5, bold=True, color=C_DEEP)
    add_bullets(s16, 0.78, 5.36, 5.54, 1.44, [
        ("格式彻底消除崩溃：", "v3 曾出现多轮指代输出 77 位幻觉 item_id 导致 JSON 损坏；v4 经多轮上下文训练后 JSON 解析率升至 100%，零格式错乱。"),
        ("7 条失败明确归因：", "3 条属严格字面差（多留量词「一双」）、3 条列类目直接 reply 未调 list_categories、1 条需后端注入多轮历史。"),
    ], size=11.0, spacing=5, line_spacing=1.24)

    # 右侧两张卡片截图 + 共享 session 说明
    add_img_fit(s16, FIGS5 / "18_Agent首轮卡片.png", 6.72, 1.24, 2.92, 4.02,
                bg_card=True, caption="首轮检索：正文与商品卡片渲染")
    add_img_fit(s16, FIGS5 / "19_图搜接话.png", 9.81, 1.24, 2.92, 4.02,
                bg_card=True, caption="图搜接话：图像结果并入同会话")

    add_rect(s16, 6.72, 5.42, 6.01, 1.44, C_TEAL_SOFT, border=C_TEAL, radius=0.06, border_pt=0.8)
    add_text(s16, 6.90, 5.52, 5.65, 1.24,
             "跨模态会话贯通：首轮文本检索、上传图片搜同款与后续多轮追问共享同一 session_id。图搜走真实 ONNX 图像塔（图中首位相似度 0.9573），返回类目并入会话历史后，后续纯文本轮次可直接继承该类目继续筛选。",
             size=11.5, color=C_DEEP, line_spacing=1.32)

    set_notes(s16, """【多轮评测页，约 1 分 25 秒】
v3 和 v4 把模型从单轮指令升级到了完整对话协议。左边是 v4 在 40 条对话评测集上的实测数据（脚本 eval_v3_dialogue.py，含 10 条文搜、10 条图搜/列类目/详情、10 条结果点评、10 条闲聊澄清）：

第一，JSON 解析率从 v3 的 95% 提升到 100%，40 条全部合法——v3 时代最严重的多轮指代产生 77 位幻觉 item_id 导致 JSON 崩掉的问题，在 v4 上彻底消失了。

第二，动作准确率 90%（36/40），相比 v3 单轮的 92.5% 微降 2.5 个百分点，这是一个诚实的权衡：v4 注入了多轮上下文，格式更稳，但有 3 条询问“库里有什么品类”的题模型直接用自然语言 reply 回答而没调 list_categories 工具。

第三，综合任务通过率 82.5%（33/40）——这里要严格说清口径，这 82.5% 是评测脚本检查模型输出的动作、工具名、参数字面值和安全回复全部达标的综合通过率，并不是拿商品库做线上检索的召回率。剩下的 7 条失败每一条都有明确归因：3 条是参数字面多带了“一双”这类量词（线上规范化即可清洗）、3 条是列类目直接 reply、1 条指代详情需要后端注入多轮历史，没有一条是模型崩溃。

第四，安全通过率 100%，全程零价格、零销量编造。右边展示首轮检索卡片和图搜接话，两者共享同一 session_id。""")

    # =========================================================================
    # SLIDE 17: 多轮会话管理与安全闸
    # =========================================================================
    s17 = prs.slides.add_slide(blank)
    add_header_footer(s17, 17, "EXPERIMENT 05 · SESSION & SAFETY GUARD", "多轮会话管理：槽位继承、图搜接话与安全闸")

    add_img_fit(s17, FIGS5 / "20_多轮追问.png", 0.60, 1.24, 2.98, 4.30,
                bg_card=True, caption="多轮追问：刷新后会话历史保持")
    add_img_fit(s17, FIGS5 / "21_清空会话.png", 3.76, 1.24, 2.98, 4.30,
                bg_card=True, caption="清空会话：前后端同步释放状态")

    add_rect(s17, 6.96, 1.24, 5.77, 4.30, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s17, 7.18, 1.38, 5.33, 0.34, "五大后端会话与安全治理机制", size=14.5, bold=True, color=C_DEEP)
    add_bullets(s17, 7.18, 1.80, 5.33, 3.60, [
        ("滑动窗口 + 原话摘要：", "单会话保留最近 8 条消息 + 最多 6 句用户原话摘要，在 2048 token 内平衡上下文记忆与推理延迟。"),
        ("类目槽位继承与查询合并：", "上轮查「运动鞋」、本轮仅说「要白色的」→ 自动继承 category=鞋 并合并为「运动鞋 白色」，防止搜偏。"),
        ("图搜结果入历史：", "POST /api/v1/agent/image 复用真实 ONNX 图像塔（回归实测首位相似度 0.9573），类目写入会话供后续追问。"),
        ("生命周期与内存保护：", "前端清空触发 DELETE /agent/session/{id} 同步释放；30 分钟 TTL 自动过期 + 500 会话 LRU 上限防内存泄漏。"),
        ("结果安全闸：", "拦截价格（如 XX 元 / 几折）与销量断言，纠正主语口误、剥离量词客套话，确保回复只基于检索事实。"),
    ], size=11.8, spacing=8, line_spacing=1.26)

    add_rect(s17, 0.60, 5.72, 12.133, 1.14, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_text(s17, 0.80, 5.82, 11.73, 0.94,
             "诚实边界说明：左侧前端回归截图执行于未加载 Qwen3-4B 权重的本机（Agent 走规则降级模式，图搜走真实 ONNX 图像塔），验证了五条主链路交互、localStorage 刷新保持与渲染安全；say 过渡语与 v4 模型驱动的多轮槽位继承端到端复测清单已归档在「演示机验证checklist.md」，不在本页提前声称已完成。",
             size=11.5, color=C_DEEP, line_spacing=1.32)

    set_notes(s17, """【多轮会话管理页，约 1 分 15 秒】
要让对话导购真正稳定可用，后端会话管理同样关键。右边总结了五项工程机制：

第一，上下文窗口控制：保留最近 8 条消息加最多 6 句用户原话摘要，既省显存又记住关键偏好。

第二，类目槽位继承：上一轮用户说「找运动鞋」，下一轮只说「要白色的」，后端不会拿孤零零的「白色」全库乱搜，而是继承类目「鞋」并把查询词合并成「运动鞋 白色」。

第三，图搜接话：图片检索走真实 ONNX 图像塔，结果直接并入会话历史，下一轮文字追问可以继续沿着图片判出来的类目细化。

第四，生命周期管理：点击清空会调用 DELETE /agent/session/{id} 同步释放前后端状态，同时配了 30 分钟 TTL 过期和 500 段 LRU 淘汰，防止内存无限增长。

第五，安全闸：专门拦截价格和销量幻觉断言、纠正主语口误、剥离客套量词。

底部我们如实标注了测试边界：这几张前端回归截图是在无 Qwen 权重的本机规则降级模式下跑的，验证了前端渲染、刷新保持、图搜 ONNX 和清空释放；v4 模型的 say 过渡语与多轮槽位继承端到端复测清单已做成 checklist 交付，待在 GPU 演示机上完整走查。""")

    # =========================================================================
    # SLIDE 18: 总结、评测台账与展望
    # =========================================================================
    s18 = prs.slides.add_slide(blank)
    add_header_footer(s18, 18, "SUMMARY & OUTLOOK", "项目总结：全链路评测台账、工程沉淀与展望")

    # 左侧原生表格：全项目 6 行评测台账
    rows_data = [
        ("指标维度", "核心实测结果", "严格统计口径"),
        ("三源数据清洗", "10,165 → 9,393 条（92.4%）", "MUGE + 苏宁 + Amazon 9 类"),
        ("双塔全参微调", "R@1 37.37% → 58.67%", "test 934 对；微调 +13.6 / 清洗 +7.7pp"),
        ("TRT FP16 加速", "4.59→1.94 ms（−57.73%）", "GPU 训练机 batch=1 配对；R@1 差 −0.43pp"),
        ("Agent 工具调用", "纯模型 90% → 规范化 100%", "v2 十轮，3080Ti & 5060 两机一致"),
        ("v4 多轮对话", "JSON 100% / 动作 90% / 通过 82.5%", "40 条协议集；安全通过率 100%"),
        ("端到端暖机均值", "文本 46.4 / 图片 115.8 ms", "ONNX CPU 30 次压测（Agent 48.2/128.1）"),
    ]
    tbl_shape = s18.shapes.add_table(len(rows_data), 3, Inches(0.60), Inches(1.26), Inches(7.15), Inches(5.52))
    tbl = tbl_shape.table
    tbl.columns[0].width = Inches(1.62)
    tbl.columns[1].width = Inches(2.68)
    tbl.columns[2].width = Inches(2.85)

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
                txt_c, bld, fsz = C_WHITE, True, 12.0
            else:
                cell.fill.fore_color.rgb = C_WHITE if r_idx % 2 == 1 else C_TEAL_SOFT
                txt_c = C_DEEP if c_idx == 0 else (C_WARM if (r_idx in (3, 4) and c_idx == 1) else C_TEXT)
                bld = (c_idx == 0 or (c_idx == 1 and r_idx in (2, 3, 4)))
                fsz = 11.0
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

    # 右上：沉淀的核心工程能力
    add_rect(s18, 7.98, 1.26, 4.75, 2.66, C_WHITE, border=C_LINE, radius=0.06)
    add_text(s18, 8.18, 1.36, 4.35, 0.32, "已沉淀的核心工程能力", size=14, bold=True, color=C_DEEP)
    add_bullets(s18, 8.18, 1.72, 4.35, 2.12, [
        ("端到端全链路闭环：", "数据 → 全参微调 → TRT 加速 → Web 服务 → 对话 Agent，全部凭证入库可复现。"),
        ("三同源一致性：", "MD5 防泄漏切分、统一 build_product_text 模板与同源索引贯穿全流程。"),
        ("工程化安全架构：", "白名单 + 规范化 + 规则降级 + 安全闸，从机制上杜绝编造商品事实。"),
        ("可演示全栈交付：", "一键启动（支持 --lan）、8 页面 React 工作台与离线 OpenAPI 规范齐备。"),
    ], size=10.8, spacing=4.5, line_spacing=1.22)

    # 右下：已知局限与后续展望
    add_rect(s18, 7.98, 4.08, 4.75, 2.70, C_WARM_SOFT, border=C_WARM_LIGHT, radius=0.06, border_pt=0.9)
    add_text(s18, 8.18, 4.18, 4.35, 0.32, "已知边界与后续优化方向", size=14, bold=True, color=C_WARM)
    add_bullets(s18, 8.18, 4.54, 4.35, 2.14, [
        ("多轮语料扩充：", "补充人工审核的否定条件、价格区间、多属性组合与更长记忆样本。"),
        ("会话持久化：", "当前会话存于进程内存，后续迁至 Redis 或 SQLite 支持重启恢复。"),
        ("库外拒识阈值：", "当前 FAISS 无相似度下限，后续引入类目过滤与阈值降误命中。"),
        ("演示机端到端复测：", "按交付 checklist 在 GPU 演示机完成 v4 say 过渡语与多轮槽位演练。"),
    ], size=10.8, lead_color=C_DEEP, bullet_color=C_WARM, spacing=4.5, line_spacing=1.22)

    set_notes(s18, """【总结页，约 1 分 10 秒】
最后做全项目总结。左边是六个维度的数字台账，每一条都能在仓库里找到对应的 JSON 或日志凭证：

第一，三源数据 10,165 条清洗通过 9,393 条（92.4%）；第二，双塔全参微调让 test 934 对 R@1 从 37.37% 升至 58.67%，其中微调贡献 +13.6pp、清洗净增 +7.7pp；第三，GPU 训练机同硬件配对测速下，TensorRT FP16 将 batch=1 图像塔延迟从 4.59 降到 1.94 毫秒（−57.73%），双塔 R@1 净差 −0.4283pp；第四，v2 工具调用纯模型 90%、加参数规范化 100%，在 RTX 3080Ti 与 RTX 5060 两机一致；第五，v4 多轮 40 条协议集 JSON 100%、动作 90%、综合通过率 82.5%、安全 100%；第六，本机 ONNX CPU 30 次暖机均值文本 46.4 ms、图片 115.8 ms。

右边上面是我们沉淀下来的四项工程能力，下面是坦诚列出的四个已知边界与后续方向：扩充否定条件等难例多轮语料、把内存会话迁到 Redis 持久化、给 FAISS 增加库外相似度阈值、以及在 GPU 演示机按 checklist 完成端到端复测。""")

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
    add_text(s19, 0.8, 2.98, 11.733, 0.48, "欢迎批评指正  ·  仓库全部代码、日志与评测凭证均可复查",
             size=18, color=C_LIGHT_TXT, align=PP_ALIGN.CENTER)

    add_rect(s19, 2.2, 3.88, 8.933, 0.025, C_WARM_LIGHT)

    add_text(s19, 0.8, 4.26, 11.733, 0.36, "ShopVision · 第 23 组团队成员",
             size=14, bold=True, color=C_WARM_LIGHT, align=PP_ALIGN.CENTER)
    add_text(s19, 0.8, 4.74, 11.733, 0.46,
             "何朝杨   ·   杜军博   ·   王陆洲   ·   张梓萱   ·   刘凡思雨   ·   秦鑫洋",
             size=21, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    add_text(s19, 0.8, 5.75, 11.733, 0.36, "西安邮电大学  ·  AI 全栈开发课程设计  ·  2026 年 11 月",
             size=13, color=RGBColor(0x95, 0xB4, 0xB8), align=PP_ALIGN.CENTER)

    set_notes(s19, """【收尾与答辩追问预案，约 30 秒】
以上就是第 23 组的全部汇报内容，谢谢各位老师和同学，欢迎提问！

【高频答辩追问标准预案（已按仓库源码与实验一~五原报告全面核实）】
1. 问：实验二 Chinese-CLIP 是用 LoRA 还是全参微调？在哪训的？
   答：实验二采用全参数微调（freeze_vision=False，启用 AMP 混合精度 + grad_checkpointing，lr=1e-5），没有用 LoRA；是在本组训练机 Win11 + WSL2 + Docker + RTX 5060 Ti 8GB 上单卡跑的，3 epoch 705 步约 6 分钟；LoRA/QLoRA 用在实验五的 Qwen3-4B 上。
2. 问：你们数据清洗到底起了多大作用？
   答：三组对照在固定 934 条 test 集上测得：零样本 37.37% → 未清洗直训（10,165 条）50.96% → 清洗微调（9,393 条）58.67%。总提升 +21.30pp 中，微调本身贡献 +13.59pp（约 64%），数据清洗在样本少 772 条的情况下仍额外净增 +7.71pp（约 36%）。
3. 问：TensorRT 加速为什么不用 INT8 量化？基线口径是什么？
   答：我们实测了 6 种动态量化配置（3.1.1），最好仍掉点 −13.06pp，不满足 ≤2% 要求，故冻结留档并改走 ONNX + TensorRT FP16。速度在 GPU 训练机（torch 2.7.1+cu128 / TensorRT 10.x）上做同精度配对测速（batch=1 延迟 4.59→1.94 ms，−57.73%，源 JSON 未记录具体型号故不补写）；精度以自研同源 PyTorch FP32（R@1 58.5653%）为共同基线，TRT FP16 净差仅 −0.4283pp。
4. 问：后端错误码是怎么设计的？
   答：统一返回 {code, result, msg}，5 位码前三位直接对应 HTTP 状态码：400xx（如 40000 参数错、40001 图像损坏、40003 维度不匹配）、404xx（如 40401 类别不存在、40403 白名单外工具）、500xx（如 50001 模型或 Redis 队列不可用）。
5. 问：工具调用 100% 是纯模型能力吗？
   答：不是，纯模型在 10 轮上为 90%（9/10，唯一差错是查询词保留了助词「的」），加上运行时参数规范化后达到 100%，两机一致；两者永远分开报告。
6. 问：v4 评测的 82.5% 是什么意思？剩下 7 条错在哪？
   答：82.5%（33/40）是 40 条协议测试集上的综合任务通过率（校验 JSON、action、工具名、参数字面值与安全回复），不是线上 FAISS 检索召回率。失败的 7 条全部归因明确：3 条参数多带量词「一双」、3 条列类目直接用 reply 回答、1 条缺多轮历史注入，无一条格式崩溃。
7. 问：为什么商品点评不提价格？
   答：我们清洗表固定 12 列本身没有价格与销量字段，为杜绝大模型胡编价格，专门在后端部署了安全闸拦截价格/销量断言，商品事实一律由双塔检索接口提供。""")

    OUT_PPTX.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT_PPTX))
    print(f"PPTX 生成成功: {OUT_PPTX} ({OUT_PPTX.stat().st_size / 1024 / 1024:.2f} MB, {len(prs.slides)} 页)")


if __name__ == "__main__":
    build()
