# -*- coding: utf-8 -*-
"""生成实验二报告插图（docs/typ/figs/*.png）。
用法: python docs/scripts/gen_figures_exp2.py
配色遵循 dataviz 规程：双系列用已验证分类色 slot-1 蓝 #2a78d6 / slot-2 橙 #eb6834
（validate_palette.js 全项通过），水平细网格 #e1e0d9、基线 #c3c2b7、刻度 #898781、
数值标签 #0b0b0b。双子图代替双轴，绝不共用 y 轴。
数据来源：docs/finetune/03-微调结果.md 与 docs/finetune/runs/2026-10-18_bs32_lr1e-5/。
"""
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "SimSun"],
    "axes.unicode_minus": False,
})

BLUE = "#2a78d6"        # categorical slot 1（已验证）
ORANGE = "#eb6834"      # categorical slot 2（已验证）
GREEN = "#5b8d62"       # categorical slot 3（对照组用）
GRID = "#e1e0d9"
BASE = "#c3c2b7"
MUTED = "#898781"
INK = "#0b0b0b"

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "typ" / "figs"
# 主实验：检索评测归档（含 summary.json 与 9 张图）
RUN_DIR = ROOT / "evaluation" / "retrieval" / "results" / "runs" / "finetuned_epoch3_test_20261019"
# 对照组：入库凭证目录
CTRL_DIR = ROOT / "docs" / "finetune" / "runs" / "2026-10-20_uncleaned_bs32_lr1e-5"
PILOT_DIR = ROOT / "evaluation" / "retrieval" / "results" / "runs" / "deepseekv4_1_flash_pilot_20261018"
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


# 图1 Recall@K 对比：预训练基线 / 未清洗直训 / 清洗微调（test 934 条，候选池 934）
def fig_recall():
    labels = ["R@1", "R@5", "R@10"]
    baseline = [37.37, 70.77, 82.44]
    control = [50.96, 84.48, 93.04]
    finetuned = [58.67, 89.08, 96.90]
    x = range(len(labels))
    w = 0.26
    fig, ax = plt.subplots(figsize=(6.6, 3.0), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    b1 = ax.bar([i - w for i in x], baseline, width=w, color=BLUE, zorder=3, label="预训练基线")
    b2 = ax.bar(list(x), control, width=w, color=ORANGE, zorder=3, label="未清洗数据直训")
    b3 = ax.bar([i + w for i in x], finetuned, width=w, color=GREEN, zorder=3, label="清洗数据微调")
    style(ax)
    ax.set_ylim(0, 112)
    ax.set_ylabel("Recall@K（%）", color=MUTED, fontsize=10)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    for bars in (b1, b2, b3):
        for b in bars:
            v = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.1f}",
                    ha="center", va="bottom", fontsize=7.5, color=INK)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK, ncol=3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_recall.png", facecolor="#fcfcfb")
    plt.close(fig)
    print("saved", OUT / "fig_recall.png")


# 图2 训练过程验证曲线：loss 与两路准确率（双子图，不同量纲不共轴）
def fig_curves():
    steps = [150, 235, 300, 450, 470, 600, 705]
    loss = [0.2225, 0.1963, 0.2056, 0.1571, 0.1543, 0.1444, 0.1403]
    i2t = [91.77, 93.33, 91.87, 94.58, 94.90, 94.48, 94.69]
    t2i = [91.25, 92.19, 92.50, 93.44, 93.75, 94.27, 94.48]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.8, 2.8), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")

    style(ax1)
    ax1.plot(steps, loss, color=BLUE, linewidth=2, marker="o", markersize=5, zorder=3)
    ax1.set_title("验证集 Loss", color=INK, fontsize=10)
    ax1.set_xlabel("训练步数", color=MUTED, fontsize=9)
    ax1.annotate(f"{loss[-1]:.4f}", (steps[-1], loss[-1]), textcoords="offset points",
                 xytext=(-8, 8), fontsize=9, color=INK, ha="right")

    style(ax2)
    ax2.plot(steps, i2t, color=BLUE, linewidth=2, marker="o", markersize=5, zorder=3, label="图→文准确率")
    ax2.plot(steps, t2i, color=ORANGE, linewidth=2, marker="s", markersize=5, zorder=3, label="文→图准确率")
    ax2.set_title("验证集准确率（batch 内 32 候选口径）", color=INK, fontsize=10)
    ax2.set_xlabel("训练步数", color=MUTED, fontsize=9)
    ax2.annotate(f"{i2t[-1]:.2f}", (steps[-1], i2t[-1]), textcoords="offset points",
                 xytext=(-6, 8), fontsize=9, color=INK, ha="right")
    ax2.annotate(f"{t2i[-1]:.2f}", (steps[-1], t2i[-1]), textcoords="offset points",
                 xytext=(-6, -14), fontsize=9, color=INK, ha="right")
    ax2.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=INK)

    fig.tight_layout()
    fig.savefig(OUT / "fig_curves.png", facecolor="#fcfcfb")
    plt.close(fig)
    print("saved", OUT / "fig_curves.png")


def read_scores():
    """返回 (预训练基线, 未清洗直训, 清洗微调) 三组分数。"""
    baseline = json.loads((RUN_DIR / "baseline_test_score.json").read_text(encoding="utf-8"))
    tuned = json.loads((RUN_DIR / "finetuned_epoch3_test_score.json").read_text(encoding="utf-8"))
    control = json.loads((CTRL_DIR / "finetuned_epoch3_test_score.json").read_text(encoding="utf-8"))
    return baseline["scoreJson"], control["scoreJson"], tuned["scoreJson"]


def read_validation_log():
    pattern = re.compile(
        r"Validation Result \(epoch\s*(\d+)\s*@\s*(\d+) steps\).*?"
        r"Valid Loss:\s*([0-9.]+)\s*\|\s*Image2Text Acc:\s*([0-9.]+)\s*\|\s*"
        r"Text2Image Acc:\s*([0-9.]+)"
    )
    rows = []
    log_path = RUN_DIR / "out_2026-10-18-12-27-38.log"
    for line in log_path.read_text(encoding="utf-8").splitlines():
        match = pattern.search(line)
        if match:
            epoch, step, loss, i2t, t2i = match.groups()
            rows.append({
                "epoch": int(epoch),
                "step": int(step),
                "loss": float(loss),
                "i2t": float(i2t),
                "t2i": float(t2i),
            })
    if len(rows) != 7:
        raise RuntimeError(f"验证日志应有 7 条记录，实际读取 {len(rows)} 条")
    return rows


# 图3：测试指标、验证损失和批内准确率合为一张中文证据图。
def fig_evidence():
    baseline, control, tuned = read_scores()
    validation = read_validation_log()
    steps = [row["step"] for row in validation]

    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.35), dpi=220)
    fig.patch.set_facecolor("#fcfcfb")
    fig.suptitle("模型微调训练与测试证据总览", color=INK, fontsize=14, fontweight="bold", y=0.98)

    labels = ["R@1", "R@5", "R@10"]
    keys = ["r1", "r5", "r10"]
    x = range(len(keys))
    width = 0.26
    ax = axes[0]
    style(ax)
    bars_a = ax.bar([i - width for i in x], [baseline[k] for k in keys],
                    width=width, color=BLUE, zorder=3, label="预训练基线")
    bars_b = ax.bar(list(x), [control[k] for k in keys],
                    width=width, color=ORANGE, zorder=3, label="未清洗直训")
    bars_c = ax.bar([i + width for i in x], [tuned[k] for k in keys],
                    width=width, color=GREEN, zorder=3, label="清洗微调")
    ax.set_title("测试集 Recall@K", color=INK, fontsize=11)
    ax.set_ylim(0, 108)
    ax.set_xticks(list(x), labels)
    ax.set_ylabel("召回率（%）", color=MUTED, fontsize=9)
    for bars in (bars_a, bars_b, bars_c):
        for bar in bars:
            value = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, value + 1.2, f"{value:.0f}",
                    ha="center", va="bottom", fontsize=7, color=INK)
    ax.legend(frameon=False, fontsize=7, loc="upper left", labelcolor=INK)

    ax = axes[1]
    style(ax)
    loss = [row["loss"] for row in validation]
    ax.plot(steps, loss, color=BLUE, linewidth=2, marker="o", markersize=4.5, zorder=3)
    ax.set_title("验证集损失", color=INK, fontsize=11)
    ax.set_xlabel("训练步数", color=MUTED, fontsize=9)
    ax.set_ylabel("验证损失", color=MUTED, fontsize=9)
    ax.annotate(f"{loss[0]:.4f}", (steps[0], loss[0]), xytext=(2, 8),
                textcoords="offset points", fontsize=8, color=INK)
    ax.annotate(f"{loss[-1]:.4f}", (steps[-1], loss[-1]), xytext=(-5, 8),
                textcoords="offset points", fontsize=8, color=INK, ha="right")

    ax = axes[2]
    style(ax)
    ax.plot(steps, [row["i2t"] for row in validation], color=BLUE,
            linewidth=2, marker="o", markersize=4.5, zorder=3, label="图→文准确率")
    ax.plot(steps, [row["t2i"] for row in validation], color=ORANGE,
            linewidth=2, marker="s", markersize=4.5, zorder=3, label="文→图准确率")
    ax.set_title("批内双向检索准确率", color=INK, fontsize=11)
    ax.set_xlabel("训练步数", color=MUTED, fontsize=9)
    ax.set_ylabel("准确率（%）", color=MUTED, fontsize=9)
    ax.set_ylim(90, 96)
    ax.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=INK)

    fig.text(0.5, 0.01, "证据口径：test 934 对图文样本、候选池 934；训练 705 步；共 7 次验证记录",
             ha="center", color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.055, 1, 0.94))
    fig.savefig(OUT / "fig_evidence.png", facecolor="#fcfcfb")
    plt.close(fig)
    print("saved", OUT / "fig_evidence.png")


# 图4：将 AI 试点指标改成中文三组柱状图，保留标准指标名称。
def fig_pilot_metrics():
    summary = json.loads((PILOT_DIR / "summary.json").read_text(encoding="utf-8"))
    modes = ["text", "image", "multimodal"]
    mode_labels = ["文字查询", "图片查询", "图文查询"]
    metric_keys = ["precision@10", "ndcg@10", "mrr@10"]
    metric_labels = ["Precision@10", "nDCG@10", "MRR@10"]

    fig, ax = plt.subplots(figsize=(6.4, 3.1), dpi=220)
    fig.patch.set_facecolor("#fcfcfb")
    x = range(len(mode_labels))
    width = 0.22
    colors = [BLUE, ORANGE, "#5b8d62"]
    for index, (key, label, color) in enumerate(zip(metric_keys, metric_labels, colors)):
        values = [summary["metrics_by_mode"][mode][key] for mode in modes]
        offset = (index - 1) * width
        bars = ax.bar([i + offset for i in x], values, width=width,
                      color=color, zorder=3, label=label)
        for bar in bars:
            value = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.012, f"{value:.3f}",
                    ha="center", va="bottom", fontsize=7.5, color=INK)
    style(ax)
    ax.set_title("不同查询模式的检索指标", color=INK, fontsize=12, fontweight="bold")
    ax.set_ylim(0, 1.08)
    ax.set_xticks(list(x), mode_labels)
    ax.set_ylabel("指标值", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_pilot_metrics.png", facecolor="#fcfcfb")
    plt.close(fig)
    print("saved", OUT / "fig_pilot_metrics.png")


if __name__ == "__main__":
    fig_recall()
    fig_curves()
    fig_evidence()
    fig_pilot_metrics()
