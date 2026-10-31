# -*- coding: utf-8 -*-
"""校验 docs/typ/实验三.typ 中的关键数字与冻结结果一致。
用法: python docs/scripts/check_exp3_typ_numbers.py
数据源（只读，不改）:
  evaluation/retrieval/results/runs/exp3_inference_acceleration_20261025/ 下的 tables/*.csv 与 reference_retrieval/
  docs/optimize/runs/2026-10-23_exp3-quant/accuracy/by_category_{fp32,int8-pc}.json 与 quantize_report.json
若报告被手工改动而与源数据不符，脚本会列出所有失配项并以非零码退出。
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "evaluation" / "retrieval" / "results" / "runs" / "exp3_inference_acceleration_20261025"
QNT = ROOT / "docs" / "optimize" / "runs" / "2026-10-23_exp3-quant"
TYP_PATH = ROOT / "docs" / "typ" / "实验三.typ"


def csv_rows(path):
    with open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


# 交付 README 手工抄了一遍报告的关键表，同样要防漂移；只校验它确实承载的数值族。
DELIVERY_README = ROOT / "docs" / "交付材料" / "实验三_第23组" / "README.md"


def main():
    # 报告把 R@K 写成 R\@K（转义 @），比较前还原，避免把转义当成数字缺失。
    typ = TYP_PATH.read_text(encoding="utf-8").replace("\\@", "@")
    missing = []

    def need(text, where):
        if text not in typ:
            missing.append(f"[{where}] 报告中缺少: {text!r}")

    # 1) 图像塔速度：加速比 / 延迟降低 / 吞吐提升 / 中位延迟
    for r in csv_rows(RUN / "tables" / "runtime_comparison.csv"):
        tag = f"{r['backend']}-b{r['batch']}"
        need(f"{float(r['speedup']):.3f}×", f"加速比 {tag}")
        need(f"{float(r['latency_reduction_pct']):.2f}%", f"延迟降低 {tag}")
        need(f"{float(r['throughput_gain_pct']):+.2f}%", f"吞吐提升 {tag}")
        need(f"{float(r['torch_median_ms']):.2f}", f"PyTorch 中位 {tag}")
        need(f"{float(r['engine_median_ms']):.2f}", f"引擎中位 {tag}")

    # 2) 双塔精度一致性与 R@K
    for r in csv_rows(RUN / "tables" / "accuracy_comparison.csv"):
        tag = r["backend"]
        for key in ("r1", "r5", "r10", "mean_recall"):
            need(f"{float(r[key]):.4f}", f"{tag} {key}")
        if r["group"] != "baseline":
            need(f"{float(r['delta_r1_pp']):+.4f}", f"{tag} ΔR@1")

    # 3) 验收：8 项全部通过
    checks = csv_rows(RUN / "tables" / "acceptance_checks.csv")
    if not all(c["passed"] == "True" for c in checks):
        missing.append("[验收] 存在未通过的验收项")
    for c in checks:
        need(c["metric"], f"验收项 {c['metric']}")
    if "通过" not in typ:
        missing.append("[验收] 报告中未出现“通过”判定")

    # 4) 参数与理论计算量
    for r in csv_rows(RUN / "tables" / "model_scale.csv"):
        need(f"{int(r['params']):,}", f"参数量 {r['tower']}")
        need(f"{float(r['flops']) / 1e9:.2f}", f"FLOPs {r['tower']}")

    # 5) 文件体积
    for r in csv_rows(RUN / "tables" / "model_sizes.csv"):
        need(f"{float(r['size_mib']):.2f}", f"体积 {r['object']}-{r['precision']}")

    # 6) 九类别 FP32 基线
    for r in csv_rows(RUN / "tables" / "category_baseline.csv"):
        need(f"{float(r['r1']):.2f}", f"类别 R@1 {r['category']}")

    # 7) 历史 132 查询分模式指标
    for r in csv_rows(RUN / "reference_retrieval" / "metrics_by_mode.csv"):
        for key in ("precision@10", "recall@10", "ndcg@10", "mrr@10"):
            need(f"{float(r[key]):.4f}", f"历史查询 {r['mode']} {key}")

    # 8) 冻结量化：纯权重 INT8 体积与九类别精度差（关联分析表）
    size = load_json(QNT / "quantize_report.json")
    int8_mb = next(x["mb"] for x in size["results"] if x["mode"] == "int8")
    need(f"{float(int8_mb):.2f}", "INT8 纯权重体积")
    fp32 = load_json(QNT / "accuracy" / "by_category_fp32.json")["by_category"]
    int8 = load_json(QNT / "accuracy" / "by_category_int8-pc.json")["by_category"]
    for cat, row in int8.items():
        need(f"{float(row['r1']):.2f}", f"INT8 类别 R@1 {cat}")
        delta = row["r1"] - fp32[cat]["r1"]
        need(f"{delta:.2f}", f"INT8 类别 ΔR@1 {cat}")

    # 9) 交付 README 的表格数字（速度/精度/规模/体积/验收）与同一批冻结源一致
    if DELIVERY_README.exists():
        rd = DELIVERY_README.read_text(encoding="utf-8")
        for r in csv_rows(RUN / "tables" / "runtime_comparison.csv"):
            tag = f"{r['backend']}-b{r['batch']}"
            for key, fmt in (("torch_median_ms", "{:.2f}"), ("engine_median_ms", "{:.2f}")):
                if fmt.format(float(r[key])) not in rd:
                    missing.append(f"[交付README 速度 {tag}] 缺少 {fmt.format(float(r[key]))}")
        for r in csv_rows(RUN / "tables" / "accuracy_comparison.csv"):
            for key in ("r1", "mean_recall"):
                if f"{float(r[key]):.4f}" not in rd:
                    missing.append(f"[交付README 精度 {r['backend']} {key}] 缺少 {float(r[key]):.4f}")
        for r in csv_rows(RUN / "tables" / "model_scale.csv"):
            if f"{int(r['params']):,}" not in rd:
                missing.append(f"[交付README 参数 {r['tower']}] 缺少 {int(r['params']):,}")
        for r in csv_rows(RUN / "tables" / "model_sizes.csv"):
            if f"{float(r['size_mib']):.2f}" not in rd:
                missing.append(f"[交付README 体积 {r['object']}-{r['precision']}] 缺少 {float(r['size_mib']):.2f}")

    if missing:
        print("报告数字与冻结结果不一致，共 %d 处：" % len(missing))
        for item in missing:
            print("  -", item)
        return 1
    print("校验通过：实验三.typ 的关键数字与冻结结果一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())