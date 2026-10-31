# -*- coding: utf-8 -*-
"""校验 docs/typ/实验三.typ 编译出的 PDF 版式：去尾标题、图表与标题分离、正文越界、末页近空白。
用法: python docs/scripts/check_exp3_typ_layout.py [pdf路径]   （省略则取 docs/build/ 下最新的实验三 PDF）
不改任何文件，只报告；有问题以非零码退出。
"""
import glob
import re
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
TYP = ROOT / "docs" / "typ" / "实验三.typ"
MARGIN_PT = 2.5 / 2.54 * 72  # 正文页边距 2.5cm
EPS = 1.5                    # 字体/描边的亚像素容差
CAP = re.compile(r"^(图|表|代码)\s*\d+")     # 图表题注行首
HEAD = re.compile(r"^(一|二|三|四|五|六|七、|附录|[0-9]+\.[0-9]+)")
# 行末越界容差：中文标点悬挂约 6pt，混排两端对齐亦有约 3pt 溢出。
# 实验二（已验收）实测最大 6.0pt，故 6.5pt 以下视为模板固有行为，只报更严重的。
OVER_MAX = 6.5


def lines_of(page):
    """按视觉行归并文本，返回 [(text, bbox)]，剔除页脚（落在下边距里）。"""
    out = []
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            txt = "".join(s["text"] for s in ln["spans"]).strip()
            if not txt:
                continue
            box = fitz.Rect(ln["bbox"])
            if box.y0 > page.rect.height - MARGIN_PT:  # 页脚
                continue
            out.append((txt, box))
    return sorted(out, key=lambda t: (t[1].y0, t[1].x0))


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else max(
        (Path(p) for p in glob.glob(str(ROOT / "docs" / "build" / "实验三-*.pdf"))),
        key=lambda p: p.stat().st_mtime,
    )
    doc = fitz.open(pdf)
    headings = [l.lstrip("=").strip() for l in TYP.read_text(encoding="utf-8").splitlines()
                if re.match(r"^=\s", l)]
    bad = []

    for i, page in enumerate(doc, 1):
        ls = lines_of(page)
        if not ls:
            bad.append(f"p{i}: 空页")
            continue
        right = page.rect.width - MARGIN_PT
        for txt, box in ls:
            over = box.x1 - right
            if over > OVER_MAX:
                bad.append(f"p{i}: 正文右越过版心 {over:.1f}pt — {txt[:30]!r}")
        last = ls[-1][0]
        if any(last.endswith(h) for h in headings):
            bad.append(f"p{i}: 标题落在页末（孤行）— {last!r}")
        if i > 1 and CAP.match(ls[0][0]):
            # 图片不产生文本行，故"页首是题注"本身不算错；只有当本页题注之上没有图片时，才是图上一页、题注下一页的真拆页。
            img_above = any(b["bbox"][3] <= ls[0][1].y0
                            for b in page.get_text("dict")["blocks"] if b["type"] == 1)
            if not img_above:
                bad.append(f"p{i}: 页首是题注且本页无图，图表疑被拆到上一页 — {ls[0][0][:30]!r}")

    tail = "".join(t for t, _ in lines_of(doc[-1]))
    if len(tail) < 40:
        bad.append(f"末页 p{doc.page_count} 近空白（{len(tail)} 字）")

    print(f"检查 {pdf.name}：{doc.page_count} 页")
    if bad:
        print("版式问题 %d 处：" % len(bad))
        for b in bad:
            print("  -", b)
        return 1
    print("版式检查通过：无越界、无孤行标题、图表未跨页拆分、末页非空白。")
    return 0


if __name__ == "__main__":
    sys.exit(main())