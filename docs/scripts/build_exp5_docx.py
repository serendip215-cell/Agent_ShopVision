# -*- coding: utf-8 -*-
"""实验五（期末）项目总结报告 typ -> docx。

复用 docs/scripts/typ_to_docx.py 的语义化导出 + pandoc + python-docx 后处理管线
（exp4 已验证），针对 exp5 适配：
  1. COVER 换成 exp5 封面（成员分工与 20261113 版封面一致）；
  2. 两张 SVG 图改引 PNG 栅格件（figs_exp5/ 下同名 .png，pandoc docx writer
     不支持 SVG；闭环架构=旧版 Word 内栅格件提取、流水线=svglib 现栅格）；
  3. 裸下划线转义（pandoc typst reader 把标点后的 `_` 当强调开符号，正文里的
     tool_call / item_id 等裸标识符会导致解析失败，exp3/exp4 正文无裸下划线从未触发）；
  4. 交叉引用叠词折叠（exp5 行文是「如表 @tbl-x 所示」，语义化导出替换后成
     「如表 表 N」，折叠回「如表 N」；exp4 行文是「如 @tbl-x 所示」无此问题）；
  5. 图片路径改绝对路径（pandoc typst reader 按进程 cwd 解析相对路径）。

用法：
    python docs/scripts/build_exp5_docx.py
产物：docs/build/_word/实验五-第23组-YYYYMMDD.docx（复制到交付目录前人工检查）
"""
from __future__ import annotations

import datetime as _dt
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs" / "scripts"))

import typ_to_docx as t2d  # noqa: E402

SRC = ROOT / "docs" / "交付材料" / "期末_第23组" / "04_项目总结报告" / "项目总结报告_第23组.typ"
WORK = ROOT / "docs" / "build" / "_word" / "exp5_src"
FIGS = WORK / "figs_exp5"
TODAY = _dt.date.today().strftime("%Y%m%d")
OUT = ROOT / "docs" / "build" / "_word" / f"实验五-第23组-{TODAY}.docx"

# 封面（与 20261113 版封面成员表一致；题目/时间与 typ 封面一致）
t2d.COVER = {
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


def prepare_workdir() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    FIGS.mkdir(parents=True)
    orig = ROOT / "docs" / "typ" / "figs_exp5"
    for name in (
        "01_系统架构.png",
        "03_工具调用评测_纯模型90%.png",
        "03_工具调用评测_混合100%.png",
        "04_系统首页.png",
        "05_检索评测仪表盘.png",
    ):
        shutil.copy2(orig / name, FIGS / name)
    for png in PNG_STANDINS.values():
        shutil.copy2(orig / png, FIGS / png)
    print("工作目录就绪:", WORK)


def fix_semantic(semantic: Path) -> None:
    """语义化导出后修复两类 exp5 特有问题（详见模块 docstring 3/4 条）。"""
    text = semantic.read_text(encoding="utf-8")
    lines = text.split("\n")
    n_esc = 0
    for i, line in enumerate(lines):
        # 先按双引号切（image("...") 等路径串不转义），再按反引号切
        q_parts = line.split('"')
        new_q = []
        for qi, qseg in enumerate(q_parts):
            if qi % 2 == 1:          # 引号内：字符串字面量，原样保留
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
    n_dbl = len(re.findall(r"(?:如|见)([表图])\s*\1", text))
    text = re.sub(r"(如|见)([表图])\s*\2", r"\1\2", text)
    semantic.write_text(text, encoding="utf-8")
    print(f"下划线转义: {n_esc} 处；叠词折叠: {n_dbl} 处")


def semantic_export() -> Path:
    semantic = WORK / "report.typ"
    t2d.run([
        sys.executable, str(ROOT / "docs" / "scripts" / "typ_semantic_export.py"),
        "--src", str(SRC), "--out", str(semantic),
    ])
    text = semantic.read_text(encoding="utf-8")
    # SVG 引用替换成 PNG 替身（pandoc docx writer 不支持 SVG）
    n_svg = sum(text.count(k) for k in PNG_STANDINS)
    for svg, png in PNG_STANDINS.items():
        text = text.replace(svg, f"figs_exp5/{png}")
    # 图片路径改绝对路径：pandoc 的 typst reader 按进程 cwd 解析相对路径，
    # semantic 不在 docs/typ/ 时会全部丢失。必须在下划线转义之前做，
    # 否则 `(figs_exp5/` 匹配不到已转义的路径。
    text = text.replace("(figs_exp5/", f"({FIGS.as_posix()}/")
    semantic.write_text(text, encoding="utf-8")
    print(f"SVG 引用替换: {n_svg} 处；图片路径改绝对路径: {FIGS}")
    fix_semantic(semantic)
    return semantic


def pandoc_convert(semantic: Path) -> None:
    pandoc = t2d.find_pandoc()
    csl = t2d.ensure_csl()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    t2d.run([
        str(pandoc), "-f", "typst", "-t", "docx",
        "--citeproc", f"--csl={csl}", f"--bibliography={t2d.BIB}",
        "--resource-path", str(WORK),
        "-o", str(OUT), str(semantic),
    ])


def main() -> int:
    prepare_workdir()
    semantic = semantic_export()
    pandoc_convert(semantic)

    from docx import Document

    doc = Document(str(OUT))
    t2d.polish(doc)   # polish 末尾自带 build_cover，不要重复调用
    doc.save(str(OUT))

    heads = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
    print("\n=== 转换结果 ===")
    print("  输出  :", OUT)
    print("  大小  : {:.2f} MB".format(OUT.stat().st_size / 1024 / 1024))
    print("  标题  :", len(heads))
    print("  表格  :", len(doc.tables))
    print("  图片  :", len(doc.inline_shapes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
