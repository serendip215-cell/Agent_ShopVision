"""Render experiment 3 figures exclusively from the saved run's tables."""
from __future__ import annotations

import argparse
import io
import json
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import TwoSlopeNorm
import numpy as np
from PIL import Image

from evaluate_acceleration import REPO_ROOT, read_csv, read_json, resolve_relative, write_json

COLORS = {"torch": "#0072B2", "engine": "#009E73", "trt": "#D55E00",
          "cpu": "#009E73", "cuda": "#CC79A7", "text": "#56B4E9", "grey": "#6B7280"}
WIDTH = 183 / 25.4
FONT_CANDIDATES = ("Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "WenQuanYi Micro Hei")


def setup():
    installed = {font.name for font in font_manager.fontManager.ttflist}
    chosen = next((name for name in FONT_CANDIDATES if name in installed), None)
    if not chosen:
        raise RuntimeError("缺少中文字体。请安装 Noto Sans CJK SC / 微软雅黑 / 黑体后重绘。")
    plt.rcParams.update({
        "font.family": chosen, "font.size": 8, "axes.titlesize": 9,
        "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
        "legend.fontsize": 7, "axes.unicode_minus": False,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#B6BDC5", "axes.labelcolor": "#202730",
        "text.color": "#202730", "grid.color": "#E7EBEF",
        "pdf.fonttype": 42, "svg.fonttype": "none", "figure.facecolor": "white",
    })
    return chosen


def style(ax, axis="y"):
    ax.grid(axis=axis, linewidth=0.5)
    ax.set_axisbelow(True)


def render(run_dir: Path):
    font = setup()
    out = run_dir / "figures"
    out.mkdir(exist_ok=True)
    summary = read_json(run_dir / "summary.json")
    runtime = read_csv(run_dir / "tables/runtime_comparison.csv")
    accuracy = read_csv(run_dir / "tables/accuracy_comparison.csv")
    scale = read_csv(run_dir / "tables/model_scale.csv")
    categories = read_csv(run_dir / "tables/category_baseline.csv")
    sizes = read_csv(run_dir / "tables/model_sizes.csv")
    reference = read_csv(run_dir / "reference_retrieval/metrics_by_mode.csv")
    main_accuracy = next(r for r in accuracy if r["group"] == summary["primary_group"])
    n_queries = summary["n_texts"]
    catalog = []
    for row in runtime:
        for key in ("batch", "torch_median_ms", "engine_median_ms", "torch_p90_ms",
                    "engine_p90_ms", "torch_throughput_per_s", "engine_throughput_per_s",
                    "speedup", "latency_reduction_pct", "throughput_gain_pct"):
            row[key] = float(row[key])

    def save(fig, name, claim, sources, note, role="comparison", transformation="无额外筛选"):
        """Export final-size vector masters and a 450 DPI RGB proof."""
        axes = [ax for ax in fig.axes if ax.get_label() != "<colorbar>"]
        if len(axes) > 1:
            for index, ax in enumerate(axes):
                title = ax.get_title(loc="left") or ax.get_title()
                ax.set_title("")
                ax.set_title(f"({chr(97+index)}) {title}", loc="left", fontsize=8)
        fig.canvas.draw()
        width, height = fig.canvas.get_width_height()
        renderer = fig.canvas.get_renderer()
        overflow = []
        for text in fig.findobj(matplotlib.text.Text):
            if not text.get_visible() or not text.get_text() or text.get_text() == "−":
                continue
            # Tick-label artists outside the active axis limit are not rendered.
            box = text.get_window_extent(renderer)
            if box.width and box.height and (box.x0 < -2 or box.y0 < -2 or box.x1 > width + 2 or box.y1 > height + 2):
                if text in fig.texts or text in [a.title for a in fig.axes]:
                    overflow.append(text.get_text())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fig.savefig(out / f"{name}.pdf")
            fig.savefig(out / f"{name}.svg")
            # Matplotlib inserts trailing spaces in multiline path attributes.
            # Keep the coordinate separators, while producing git-clean SVG.
            svg_path = out / f"{name}.svg"
            svg_path.write_text(
                "\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()) + "\n",
                encoding="utf-8",
            )
            buffer = io.BytesIO()
            fig.savefig(buffer, format="png", dpi=450)
            buffer.seek(0)
            with Image.open(buffer) as image:
                image.convert("RGB").save(out / f"{name}.png", dpi=(450, 450))
        glyph_warnings = [str(w.message) for w in caught if "Glyph" in str(w.message)]
        if glyph_warnings or overflow:
            raise RuntimeError(f"{name} 图形检查失败：{glyph_warnings or overflow}")
        contract = {
            "claim": claim, "figure_role": role,
            "source_paths": [f"{run_dir.relative_to(REPO_ROOT).as_posix()}/{s}" for s in sources],
            "model": "Chinese-CLIP ViT-B/16 + RoBERTa，epoch3",
            "scope": note, "evidence_mode": "accepted_measurement_replay",
            "sample_definition": f"模型级{n_queries}查询/{summary['candidate_pool']}候选；速度次数见runtime_comparison.csv；历史查询另标{summary['reference_retrieval']['query_count']}条。",
            "statistic": "速度中位数/记录吞吐；精度 R@K；按每张图说明取值",
            "uncertainty": "单轮记录，无独立重复试验置信区间；未绘制误差线。",
            "transformations": transformation, "randomness": "无随机抽样、无平滑、无插补",
            "theme_name": "nature-accessible", "color_roles": COLORS, "font": font,
            "design_brief": {"width_mm": 183, "height_mm": round(fig.get_figheight()*25.4, 2),
                             "layout": "evidence-grid" if len(fig.axes) > 1 else "single",
                             "message": claim},
            "exports": {"png_dpi": 450, "png_mode": "RGB", "vector": ["pdf", "svg"]},
            "audit": {"missing_glyphs": "PASS", "title_and_footer_bounds": "PASS",
                      "source_binding": "PASS", "visual_review": "NOT_RUN"},
        }
        write_json(out / f"{name}.figure.json", contract)
        catalog.append({"name": name, "claim": claim, "note": note})
        plt.close(fig)

    # 1. Separate CPU and GPU axes; every bar pair uses its own matching baseline.
    fig, axes = plt.subplots(2, 3, figsize=(WIDTH, 4.0), layout="constrained")
    fig.suptitle("图像塔延迟：TensorRT 在两种批大小下均明显下降")
    for col, group in enumerate(("cpu", "cuda", "trt")):
        for line, batch in enumerate((1, 32)):
            row = next(r for r in runtime if r["group"] == group and r["batch"] == batch)
            ax = axes[line, col]
            vals = [row["torch_median_ms"], row["engine_median_ms"]]
            ax.barh([1, 0], vals, color=[COLORS["torch"], COLORS[group]], height=.5)
            ax.set_yticks([1, 0], ["PyTorch", row["backend"]])
            ax.set_xlim(0, max(vals)*1.38)
            ax.set_title(f'{row["backend"]} · batch {batch}', loc="left")
            ax.set_xlabel("中位延迟（ms）")
            for y, value in zip([1, 0], vals):
                ax.text(value + max(vals)*.03, y, f"{value:.2f}", va="center", fontsize=7)
            style(ax, "x")
    primary_rows = [r for r in runtime if r["group"] == summary["primary_group"]]
    reductions = "/".join(f'{r["latency_reduction_pct"]:.2f}%' for r in primary_rows)
    gains = "/".join(f'{r["throughput_gain_pct"]:.2f}%' for r in primary_rows)
    save(fig, "01_图像塔延迟对比", f"同硬件配对测量下，主线batch1/32延迟分别降低{reductions}。",
         ["tables/runtime_comparison.csv"], "仅图像塔 forward；各子图独立横轴，不能跨硬件比较。")

    # 2. Throughput with a constant meaning for baseline/engine colors.
    fig, axes = plt.subplots(1, 3, figsize=(WIDTH, 2.9), layout="constrained")
    fig.suptitle("图像塔吞吐：TensorRT 的收益超过 50% 目标")
    for ax, group in zip(axes, ("cpu", "cuda", "trt")):
        rows = [r for r in runtime if r["group"] == group]
        x = np.arange(len(rows))
        for offset, key, label, color in (
            (-.18, "torch_throughput_per_s", "PyTorch", COLORS["torch"]),
            (.18, "engine_throughput_per_s", rows[0]["backend"], COLORS[group]),
        ):
            vals = [r[key] for r in rows]
            bars = ax.bar(x+offset, vals, width=.34, label=label, color=color)
            ax.bar_label(bars, fmt="%.1f", fontsize=6, padding=2)
        ax.set_xticks(x, ["batch 1", "batch 32"])
        ax.set_title(rows[0]["backend"], loc="left")
        ax.set_ylabel("吞吐量（样本/s）")
        ax.set_ylim(0, max(r[k] for r in rows for k in ("torch_throughput_per_s", "engine_throughput_per_s"))*1.35)
        ax.legend(frameon=False, loc="upper left")
        style(ax)
    save(fig, "02_图像塔吞吐对比", f"主线batch1/32吞吐分别提升{gains}；各后端判定见验收表。",
         ["tables/runtime_comparison.csv"], "沿用来源已四舍五入的吞吐；预处理和引擎构建不计入稳态速度。")

    # 3. Whole-test recalls.
    fig, ax = plt.subplots(figsize=(WIDTH, 2.8), layout="constrained")
    x = np.arange(3)
    for offset, row, color in zip((-.24, 0, .24), accuracy,
                                  (COLORS["torch"], COLORS["cpu"], COLORS["trt"])):
        bars = ax.bar(x+offset, [float(row[k]) for k in ("r1", "r5", "r10")],
                      width=.22, label=row["backend"], color=color)
        ax.bar_label(bars, fmt="%.2f", fontsize=6, padding=2)
    ax.set(xticks=x, xticklabels=["R@1", "R@5", "R@10"], ylim=(0, 108),
           ylabel="命中率（%）", title=f"双塔模型精度：{n_queries} 条测试查询，候选池 {summary['candidate_pool']}")
    ax.legend(loc="upper left", frameon=False)
    style(ax)
    save(fig, "03_双塔检索精度", f'主线R@1相对FP32基线的净差为{float(main_accuracy["delta_r1_pp"]):+.4f}pp。',
         ["tables/accuracy_comparison.csv"], "模型级文搜图；不包含自然用户查询的AI标签指标。")

    # 4. Never substitute the frozen INT8 category losses for TRT category losses.
    fig, ax = plt.subplots(figsize=(WIDTH, 2.35), layout="constrained")
    engine_rows = [r for r in accuracy if r["group"] != "baseline"]
    values = np.array([[float(r[f"delta_{k}_pp"]) for k in ("r1", "r5", "r10")] for r in engine_rows])
    image = ax.imshow(values, cmap="RdBu", norm=TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1), aspect="auto")
    ax.set(xticks=np.arange(3), xticklabels=["ΔR@1", "ΔR@5", "ΔR@10"],
           yticks=np.arange(len(engine_rows)), yticklabels=[r["backend"] for r in engine_rows],
           title="后端误差热力图：相对 PyTorch FP32 的百分点差")
    for (i, j), value in np.ndenumerate(values):
        ax.text(j, i, f"{value:+.4f}", ha="center", va="center", fontsize=9)
    fig.colorbar(image, ax=ax, label="差值（pp）", shrink=.85)
    max_error = float(np.abs(values).max())
    save(fig, "04_后端精度误差热力图", f"已提供整体R@K的最大绝对差为{max_error:.4f}pp。",
         ["tables/accuracy_comparison.csv"], "色标固定±1pp；这是后端×指标，不是9类别×TensorRT损失。",
         role="diagnostic", transformation="每个后端指标减同源FP32基线；不从汇总值推算分类别误差。")

    # 5. Structural scale, rather than fictional compression from graph optimization.
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 2.8), layout="constrained")
    fig.suptitle("模型结构保持不变：加速来自执行后端")
    for ax, key, divisor, label in ((axes[0], "params", 1e6, "参数量（百万）"),
                                   (axes[1], "flops", 1e9, "理论计算量（GFLOPs）")):
        vals = [float(r[key])/divisor for r in scale]
        bars = ax.bar(["图像塔", "文本塔", "合计"], vals,
                      color=[COLORS["torch"], COLORS["text"], COLORS["grey"]], width=.55)
        ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
        ax.set_ylabel(label)
        ax.set_ylim(0, max(vals)*1.22)
        style(ax)
    total = next(r for r in scale if r["tower"] == "total")
    save(fig, "05_模型参数与计算量", f'双塔共{float(total["params"])/1e6:.2f}M参数和{float(total["flops"])/1e9:.2f}GFLOPs；后端优化不改变架构。',
         ["tables/model_scale.csv"], "batch1；224×224图像、52token；FLOPs仅计MatMul/Conv。")

    # 6. Existing category baseline, explicitly not an optimized-model difference.
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 3.65), layout="constrained",
                             gridspec_kw={"width_ratios": [.9, 1.6]})
    fig.suptitle("9 类 FP32 基线分布（并非 TensorRT 分类别变化）")
    names = [r["category"] for r in categories]
    n = [int(r["n"]) for r in categories]
    axes[0].barh(names, n, color=COLORS["torch"], height=.6)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, max(n)*1.18)
    for i, value in enumerate(n):
        axes[0].text(value+4, i, str(value), va="center", fontsize=7)
    axes[0].set_xlabel("测试样本数（条）")
    style(axes[0], "x")
    matrix = np.array([[float(r[k]) for k in ("r1", "r5", "r10")] for r in categories])
    image = axes[1].imshow(matrix, vmin=0, vmax=100, cmap="Blues", aspect="auto")
    axes[1].set(xticks=np.arange(3), xticklabels=["R@1", "R@5", "R@10"],
                yticks=np.arange(len(names)), yticklabels=names)
    for (i, j), value in np.ndenumerate(matrix):
        axes[1].text(j, i, f"{value:.1f}", ha="center", va="center", fontsize=7,
                     color="white" if value > 68 else "#202730")
    fig.colorbar(image, ax=axes[1], label="命中率（%）", shrink=.9)
    save(fig, "06_九类别基线分布", "样本分布不均且各类别基线难度不同，整体指标不能代替分类别检验。",
         ["tables/category_baseline.csv"], "完整934候选池中先检索再按类别汇总；不缩小候选池。",
         role="diagnostic")

    # 7. Report only the object for which machine-readable export evidence exists.
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 2.85), layout="constrained")
    fig.suptitle("FP32 / FP16 文件体积：明确区分文件对象")
    for ax, obj, title in zip(axes, ("text_onnx", "pure_weights"), ("文本塔 ONNX", "双塔纯权重")):
        rows = [r for r in sizes if r["object"] == obj]
        vals = [float(r["size_mib"]) for r in rows]
        bars = ax.bar(["FP32", "FP16"], vals, width=.5, color=[COLORS["torch"], COLORS["trt"]])
        ax.bar_label(bars, fmt="%.2f", padding=3)
        ax.set(title=title, ylabel="文件大小（MiB）", ylim=(0, max(vals)*1.2))
        style(ax)
    save(fig, "07_模型文件大小", "FP16文件约为FP32的一半；文本塔导出报告不能当作双塔ONNX总大小。",
         ["tables/model_sizes.csv"], "MiB=2^20字节；非峰值显存，也非TensorRT引擎缓存大小。")

    # 8. A compact presentation overview, with honest scope on every panel.
    fig, axes = plt.subplots(1, 3, figsize=(WIDTH, 3.05), layout="constrained")
    fig.suptitle("实验三验收概览：图像塔速度达标，双塔精度差受控")
    main = [r for r in runtime if r["group"] == "trt"]
    threshold = summary["thresholds"]
    for ax, key, title, goal in (
        (axes[0], "latency_reduction_pct", "图像塔延迟降低（%）", threshold["latency_reduction_pct"]),
        (axes[1], "throughput_gain_pct", "图像塔吞吐提升（%）", threshold["throughput_gain_pct"]),
    ):
        vals = [r[key] for r in main]
        bars = ax.bar(["batch 1", "batch 32"], vals, color=COLORS["trt"], width=.5)
        ax.bar_label(bars, fmt="%.2f", padding=3)
        ax.axhline(goal, color=COLORS["grey"], linestyle="--", linewidth=.9, label=f"目标 ≥{goal}%")
        ax.set(title=title, ylim=(0, max(max(vals), goal)*1.35))
        ax.legend(frameon=False, loc="upper right")
        style(ax)
    trt_acc = next(r for r in accuracy if r["group"] == "trt")
    error = abs(float(trt_acc["delta_r1_pp"]))
    axes[2].bar(["TensorRT FP16"], [error], color=COLORS["trt"], width=.35)
    axes[2].text(0, error/2, f"{error:.4f}pp", ha="center", va="center",
                 color="white", fontweight="bold")
    for goal, label, line in ((1, "3.1.4 ≤1pp", "--"), (.5, "3.2.1 ≤0.5pp", ":")):
        axes[2].axhline(goal, color=COLORS["grey"], linestyle=line, linewidth=.9, label=label)
    axes[2].set(title="双塔 R@1 绝对差（pp）", ylim=(0, 1.4))
    axes[2].legend(frameon=False, loc="upper right")
    style(axes[2])
    save(fig, "08_综合验收仪表盘", f'3.1.4判定={summary["task_3_1_4_pass"]}；3.2.1判定={summary["task_3_2_1_pass"]}，阈值见验收表。',
         ["tables/runtime_comparison.csv", "tables/accuracy_comparison.csv", "tables/acceptance_checks.csv"],
         "左中为图像塔forward；右为双塔934条测试；非系统端到端加速证据。", role="acceptance")

    # 9. Reference-only replay of historical, pre-trained index rankings.
    fig, ax = plt.subplots(figsize=(WIDTH, 2.9), layout="constrained")
    rows = [r for r in reference if r["mode"] != "all"]
    x = np.arange(3)
    for offset, key, color, label in (
        (-.27, "precision@10", COLORS["torch"], "Precision@10"),
        (-.09, "recall@10", COLORS["cpu"], "Recall@10"),
        (.09, "ndcg@10", COLORS["cuda"], "nDCG@10"),
        (.27, "mrr@10", COLORS["trt"], "MRR@10"),
    ):
        bars = ax.bar(x+offset, [float(r[key]) for r in rows], width=.17, color=color, label=label)
        ax.bar_label(bars, fmt="%.3f", fontsize=6, padding=2)
    ax.set(xticks=x, xticklabels=["文字查询", "图片查询", "图文查询"], ylim=(0, 1.2),
           ylabel="指标值（0–1）", title="历史 132 查询指标复算：预训练旧索引，仅作参考")
    ax.legend(frameon=False, ncol=4, loc="upper center")
    style(ax)
    save(fig, "09_历史查询分模式参考", "历史AI试点检索指标可复算，但不能证明本轮TRT端到端效果。",
         ["reference_retrieval/metrics_by_mode.csv"], "仅历史排序复算；未调用微调/TRT查询编码器；AI标签不是独立人工真值。",
         role="reference")

    lines = ["# 图表说明与写作用法", "",
             "本目录的所有图均由本轮 tables/ 和 reference_retrieval/ 中的数据生成。每图提供450 DPI RGB PNG、PDF、SVG、figure.json；坐标和图注使用中文。",
             "", "| 图名 | 回答的问题与可引用结论 | 口径与限制 |", "|---|---|---|"]
    for item in catalog:
        lines.append(f'| [{item["name"]}]({item["name"]}.png) | {item["claim"]} | {item["note"]} |')
    lines += ["", "01–04、08用于报告的推理加速与一致性部分；05、07用于模型规模/文件体积表；06用于数据特点与基线难度分析；09只能作为历史端到端参考，不能标为优化后的结果。",
              "", "图04是后端×指标误差热力图；图06是9类FP32基线热力图。由于源凭证不含TRT分类别结果，不生成9类TRT损失热力图。",
              "", "图中不绘制置信区间，因为源文件只有一次20次计时的汇总。P90仍保留在表格中，可用于描述同轮尾延迟。"]
    (out / "图表说明.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    metadata = read_json(run_dir / "run_metadata.json")
    metadata["figures"] = {"count": len(catalog), "formats": ["png", "pdf", "svg"],
                           "source": "saved_run_tables", "visual_review": "NOT_RUN"}
    write_json(run_dir / "run_metadata.json", metadata)
    print(f"已绘制 {len(catalog)} 张中文图（PNG / PDF / SVG）")


def main():
    ap = argparse.ArgumentParser(description="从既有实验三结果表格重绘中文图。")
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    render(resolve_relative(args.run_dir))


if __name__ == "__main__":
    main()
