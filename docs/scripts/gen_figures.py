# -*- coding: utf-8 -*-
"""生成实验一报告插图（docs/typ/figs/*.png）。
用法: python docs/scripts/gen_figures.py
配色遵循 dataviz 规程：单系列用已验证的 categorical slot-1 蓝 #2a78d6，
水平细网格 #e1e0d9、基线 #c3c2b7、刻度 #898781、数值标签 #0b0b0b。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "SimSun"],
    "axes.unicode_minus": False,
})

BLUE = "#2a78d6"        # categorical slot 1（已验证）
GRID = "#e1e0d9"
BASE = "#c3c2b7"
MUTED = "#898781"
INK = "#0b0b0b"

OUT = Path(__file__).resolve().parent.parent / "typ" / "figs"
OUT.mkdir(parents=True, exist_ok=True)


def style(ax):
    ax.set_facecolor("#fcfcfb")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.grid(axis="y", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelsize=10, length=0)


def bar_chart(labels, values, fname, ylabel, fmt="{:.0f}", refline=None, reflabel=None):
    fig, ax = plt.subplots(figsize=(6.2, 3.0), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    bars = ax.bar(labels, values, width=0.55, color=BLUE, zorder=3)
    style(ax)
    ymax = max(values) * 1.18
    ax.set_ylim(0, ymax)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=10)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + ymax * 0.015, fmt.format(v),
                ha="center", va="bottom", fontsize=10, color=INK)
    if refline is not None:
        ax.axhline(refline, color=MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=2)
        ax.text(1.0, refline + ymax * 0.02, reflabel,
                ha="center", va="bottom", fontsize=9, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / fname, facecolor="#fcfcfb")
    plt.close(fig)
    print("saved", OUT / fname)


# 图2 多源数据获取规模（记录数=图片数）
bar_chart(
    ["MUGE", "Amazon", "苏宁易购"],
    [4704, 1158, 4303],
    "fig_sources.png",
    "商品记录数（条）",
)

# 图3 标准化数据集类目分布
cats = ["鞋", "水杯", "包", "男装", "运动服", "女装", "手机壳", "厨房用品", "家居用品"]
counts = [3401, 2523, 1330, 1000, 684, 361, 300, 296, 270]
bar_chart(cats, counts, "fig_categories.png", "记录数（条）")

# 图4 各类目清洗通过率（总体 92.4% 参考线）
rates = [94.6, 79.9, 97.1, 99.9, 97.7, 99.7, 100.0, 94.3, 97.8]
bar_chart(cats, rates, "fig_passrate.png", "通过率（%）", fmt="{:.1f}%",
          refline=92.4, reflabel="总体 92.4%")
