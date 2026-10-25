"""Recalculate experiment 3 acceptance from accepted teammate measurements.

This is an evidence replay, not a model inference runner. No checkpoint, API,
CUDA, ONNX Runtime or TensorRT is required. Model inference remains in
scripts/optimize. All stored paths are relative to the repository root.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_ROOT = REPO_ROOT / "evaluation/retrieval/results/runs"
DEFAULT_CONFIG = "evaluation/retrieval/configs/exp3_acceleration.json"
METRICS = ("r1", "r5", "r10", "mean_recall")


def resolve_relative(value: str, root: Path = REPO_ROOT) -> Path:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or PureWindowsPath(value).drive:
        raise ValueError(f"请使用仓库相对路径：{value}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"路径不能超出仓库：{value}")
    return resolved


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"不能写出空表：{path.name}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def positive(value, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} 必须是有限正数")
    return number


def runtime_rows(payload: dict, group: dict, thresholds: dict) -> list[dict]:
    """Use each backend's own paired PyTorch run, never another run's baseline."""
    if payload["provider"] != group["provider"]:
        raise ValueError("配置的 provider 与测速凭证不一致")
    expected_device = "cpu" if group["provider"] == "CPUExecutionProvider" else "cuda"
    if payload["device"] != expected_device:
        raise ValueError("禁止跨 CPU/GPU 计算加速比")
    if expected_device == "cpu" and payload["torch_threads"] != payload["ort_intra_op_threads"]:
        raise ValueError("CPU 对比必须对齐 PyTorch / ORT 线程数")
    rows = []
    for record in payload["results"]:
        torch, engine = record["torch"], record["ort"]
        if not engine.get("provider_ok") or group["provider"] not in engine["actual_providers"]:
            raise ValueError("测速发生后端回退，不能作为正式结果")
        if torch["device"] != expected_device or torch["precision"] != engine["precision"]:
            raise ValueError("测速的设备或精度不一致")
        batch = record["batch"]
        if torch["batch"] != batch or engine["batch"] != batch:
            raise ValueError("测速批大小不一致")
        tm = positive(torch["median_ms"], "PyTorch median")
        em = positive(engine["median_ms"], "engine median")
        tt = positive(torch["throughput_per_s"], "PyTorch throughput")
        et = positive(engine["throughput_per_s"], "engine throughput")
        reduction, gain = (1 - em / tm) * 100, (et / tt - 1) * 100
        rows.append({
            "group": group["id"], "backend": group["name"], "device": expected_device,
            "precision": payload["precision"], "batch": batch,
            "torch_median_ms": tm, "engine_median_ms": em,
            "torch_p90_ms": torch["p90_ms"], "engine_p90_ms": engine["p90_ms"],
            "torch_throughput_per_s": tt, "engine_throughput_per_s": et,
            "speedup": tm / em, "latency_reduction_pct": reduction,
            "throughput_gain_pct": gain,
            "latency_pass": reduction + 1e-9 >= thresholds["latency_reduction_pct"],
            "throughput_pass": gain + 1e-9 >= thresholds["throughput_gain_pct"],
            "warmup": payload["method"]["warmup"], "torch_iters": torch["iters"],
            "engine_iters": engine["iters"], "source": group["source"],
        })
    return rows


def accuracy_row(payload: dict, baseline: dict, group: dict, thresholds: dict) -> dict:
    if (payload["n_texts"], payload["candidate_pool"], payload["dataset"]) != (
        baseline["n_texts"], baseline["candidate_pool"], baseline["dataset"]
    ):
        raise ValueError("精度对比必须使用同一数据集与同样大小的候选池")
    if payload.get("pytorch_baseline") != baseline["scores"]:
        raise ValueError("精度记录中的基线与配置选定的基线不一致")
    row = {"group": group["id"], "backend": group["name"],
           "n_texts": payload["n_texts"], "candidate_pool": payload["candidate_pool"]}
    for metric in METRICS:
        row[metric] = payload["scores"][metric]
        row[f"delta_{metric}_pp"] = payload["scores"][metric] - baseline["scores"][metric]
    error = abs(row["delta_r1_pp"])
    row.update(accuracy_pass=error <= thresholds["accuracy_delta_pp"] + 1e-9,
               graph_accuracy_pass=error <= thresholds["graph_accuracy_delta_pp"] + 1e-9,
               source=group["source"])
    return row


def acceptance_rows(runtime: list[dict], accuracy: list[dict], primary: str, thresholds: dict) -> list[dict]:
    measured = {int(row["batch"]): row for row in runtime if row["group"] == primary}
    if set(measured) != {1, 32}:
        raise ValueError("主线必须同时提供 batch=1 与 batch=32")
    arows = [row for row in accuracy if row["group"] == primary]
    if len(arows) != 1:
        raise ValueError("主线必须提供唯一的双塔精度结果")
    result = []
    for batch in (1, 32):
        row = measured[batch]
        for key, limit, label, unit in (
            ("latency_reduction_pct", "latency_reduction_pct", "延迟降低", "%"),
            ("throughput_gain_pct", "throughput_gain_pct", "吞吐提升", "%"),
            ("speedup", "graph_speedup", "计算图加速比", "倍"),
        ):
            result.append({"task": "3.2.1" if key == "speedup" else "3.1.4",
                           "metric": f"{label} batch={batch}", "value": row[key],
                           "operator": ">=", "threshold": thresholds[limit], "unit": unit,
                           "passed": row[key] + 1e-9 >= thresholds[limit]})
    error = abs(arows[0]["delta_r1_pp"])
    for task, key in (("3.1.4", "accuracy_delta_pp"), ("3.2.1", "graph_accuracy_delta_pp")):
        result.append({"task": task, "metric": "模型级 R@1 绝对差", "value": error,
                       "operator": "<=", "threshold": thresholds[key], "unit": "pp",
                       "passed": error <= thresholds[key] + 1e-9})
    return result


def replay_reference(sources: dict, output: Path) -> dict:
    # Reuse the project's actual metric implementation, without initializing an encoder.
    from evaluate_retrieval import calculate_metrics

    queries = read_csv(sources["reference_queries"])
    qrels = read_csv(sources["reference_qrels"])
    rankings = read_csv(sources["reference_rankings"])
    rankings.sort(key=lambda row: (row["query_id"], int(row["rank"])))
    metadata = read_json(sources["reference_metadata"])
    top_k = int(metadata["top_k"])
    rankings = [row for row in rankings if int(row["rank"]) <= top_k]
    metrics = calculate_metrics(queries, rankings, qrels, int(metadata["relevance_threshold"]), top_k)
    keys = ("precision@10", "recall@10", "ndcg@10", "mrr@10")
    groups = []
    for mode in ("all", "text", "image", "multimodal"):
        subset = metrics if mode == "all" else [row for row in metrics if row["mode"] == mode]
        if not subset:
            continue
        item = {"mode": mode, "query_count": len(subset)}
        for key in keys:
            values = [float(row[key]) for row in subset if row[key] != ""]
            item[key] = sum(values) / len(values) if values else None
        groups.append(item)
    write_csv(output / "reference_retrieval/query_metrics.csv", metrics)
    write_csv(output / "reference_retrieval/metrics_by_mode.csv", groups)
    summary = {
        "scope": "historical_ranking_metric_replay",
        "source_run_id": metadata["run_id"], "query_count": len(queries), "qrels_count": len(qrels),
        "index_dir": metadata["index_dir"], "top_k": top_k,
        "metrics_by_mode": groups,
        "new_inference_executed": False, "used_for_tensorrt_acceptance": False,
        "interpretation": "沿用已核验的旧索引历史排序和 AI 标签，仅复算指标；不是微调/TRT 的新查询结果，不能推断端到端加速或调优收益。",
    }
    write_json(output / "reference_retrieval/summary.json", summary)
    return summary


def markdown_table(rows, fields):
    return "\n".join(["| " + " | ".join(fields) + " |", "|" + "|".join("---" for _ in fields) + "|"] +
                     ["| " + " | ".join(str(row[field]) for field in fields) + " |" for row in rows])


def report_text(summary: dict, runtime: list[dict], accuracy: list[dict], checks: list[dict]) -> str:
    base = next(r for r in accuracy if r["group"] == "baseline")
    main = next(r for r in accuracy if r["group"] == summary["primary_group"])
    cuda = [r for r in runtime if r["group"] == "cuda"]
    cuda_ratios = " / ".join(f'{r["speedup"]:.3f}×' for r in cuda)
    sample_count = summary["n_texts"]
    total = next(r for r in summary["model_scale"] if r["tower"] == "total")
    visual = next(r for r in summary["model_scale"] if r["tower"] == "visual")
    text = next(r for r in summary["model_scale"] if r["tower"] == "text")
    size_values = {(r["object"], r["precision"]): r["size_mib"] for r in summary["model_sizes"]}
    onnx_sizes = f'{size_values[("text_onnx", "fp32")]:.2f} / {size_values[("text_onnx", "fp16")]:.2f}'
    weight_sizes = f'{size_values[("pure_weights", "fp32w")]:.2f} / {size_values[("pure_weights", "fp16")]:.2f}'
    speed_rows = [{"后端": r["backend"], "批次": r["batch"],
                   "PyTorch/ms": f'{r["torch_median_ms"]:.2f}',
                   "引擎/ms": f'{r["engine_median_ms"]:.2f}',
                   "加速/倍": f'{r["speedup"]:.3f}',
                   "延迟降低/%": f'{r["latency_reduction_pct"]:.2f}',
                   "吞吐提升/%": f'{r["throughput_gain_pct"]:.2f}'} for r in runtime]
    acc_rows = [{"后端": r["backend"], "R@1/%": f'{r["r1"]:.4f}',
                "R@5/%": f'{r["r5"]:.4f}', "R@10/%": f'{r["r10"]:.4f}',
                "ΔR@1/pp": f'{r["delta_r1_pp"]:+.4f}'} for r in accuracy]
    check_rows = [{"任务": c["task"], "项目": c["metric"],
                   "实测": f'{c["value"]:.4f} {c["unit"]}',
                   "目标": f'{c["operator"]} {c["threshold"]} {c["unit"]}',
                   "判定": "通过" if c["passed"] else "未通过"} for c in checks]
    ref = summary["reference_retrieval"]
    ref_table = [{"模式": r["mode"], "查询数": r["query_count"],
                  **{k: f'{r[k]:.6f}' if r[k] is not None else "无有效标签"
                     for k in ("precision@10", "recall@10", "ndcg@10", "mrr@10")}}
                 for r in ref["metrics_by_mode"]]
    return f"""# 实验三推理加速评测结果（杜军博任务交付）

本轮目录：{summary['run_id']}。生成日期：{summary['generated_at']}。

## 1. 执行范围与数据来源

用户确认沿用队友已经核验的训练机结果。本轮实际执行的是：读取凭证、重新计算加速比与验收条件、复算历史查询指标、导出表格与论文图。本轮没有加载模型、重新导出 ONNX、发起 API 调用或新增 GPU 测速。

当前主任务是 3.1.4 ONNX + TensorRT 推理加速，兼顾 3.2.1 计算图优化。INT8、4-bit、剪枝均不在本轮执行范围内；历史量化结果仍在 docs/optimize/ 中留档。

原始测量的预热/正式次数逐组保存在 tables/runtime_comparison.csv，本轮为预热10次、计时20次。中位数为主，P90为描述性尾延迟；没有多轮独立实验的置信区间。统计对象是图像塔 forward，不含预处理、FAISS、商品过滤、重排、网络和界面。精度数据则来自双塔文搜图测试：{sample_count} 条查询，候选池 {summary['candidate_pool']}。

## 2. 速度结果

{markdown_table(speed_rows, list(speed_rows[0]))}

各行使用其自身文件内的 PyTorch 对照。CPU线程数对齐；GPU采用各组配对的同精度基线，不能拿CPU和GPU绝对耗时计算加速比。ORT-CUDA本轮按JSON为 {cuda_ratios}；本文统一使用已归档JSON，而不使用旧文档的手填数值。

计算公式：加速比 = PyTorch 中位延迟 / 引擎中位延迟；延迟降低 = (1 − 引擎延迟 / PyTorch 延迟) × 100%；吞吐提升 = (引擎吞吐 / PyTorch 吞吐 − 1) × 100%。吞吐使用原记录已经四舍五入的 samples/s，因此与单纯由延迟反推的百分比可能有小数尾差。

## 3. 双塔精度一致性

{markdown_table(acc_rows, list(acc_rows[0]))}

共同基线来自自研评测的PyTorch FP32，R@1 = {base['r1']:.4f}%，不能混用实验二官方脚本的58.67%。{main['backend']}的净差为 {main['delta_r1_pp']:+.4f}pp，约相当于 {sample_count} 条中的 {abs(main['delta_r1_pp'])*sample_count/100:.0f} 条Top-1净命中差；现有凭证没有逐样本配对排名，不能据此说明到底多少条查询发生变化，也不能把所有差异归因于某一个算子或FP16本身。

现有后端精度凭证没有 MRR/nDCG 或 TensorRT 分类别排名，本文不从 R@K 推造这些指标。9 类图只展示已有 FP32 基线的类别分布，不代表 TensorRT 的各类别损失。

## 4. 验收结果

{markdown_table(check_rows, list(check_rows[0]))}

3.1.4 的速度项在图像塔 forward 范围内满足目标，双塔整体 R@1 差满足 ≤1pp。3.2.1 按本轮明示口径（加速比 ≥1.2、R@1 差 ≤0.5pp）满足目标。上述结论不等同于 132 查询端到端延迟也降低 40%，也不能说明文本塔单独达到同样加速。

## 5. 模型规模与文件大小

两个塔共 {total['params']:,} 个参数、{total['flops']/1e9:.4f} GFLOPs（图像 {visual['flops']/1e9:.4f}G、文本 {text['flops']/1e9:.4f}G）。FLOPs为batch=1，图像224×224、文本长度52，只计MatMul/Conv，不包含全部算子。整模型权重还含一个logit_scale标量，因此历史体积报告中的参数量多1。

export_report_fp32 / fp16在队友执行中被最后导出的文本塔覆盖，因此它们只能证明文本塔ONNX的 {onnx_sizes} MiB；不能拿它们当成双塔总大小。纯权重FP32/FP16大小另取已核验quantize_report的文件字节，约 {weight_sizes} MiB。图表分别标明文件对象，文件大小也不等于峰值显存。推理加速不修改架构，本轮不宣称参数量或理论FLOPs下降。

## 6. 历史端到端查询参考（单独统计）

固定 {ref['query_count']} 条查询、{ref['qrels_count']} 条 AI 相关性标签，从旧索引历史 Top-10 排序复算：

{markdown_table(ref_table, list(ref_table[0]))}

这组资料属于预训练索引的 AI 试点验证集，不能与 934 条精确配对测试混算。相关度 ≥2 为相关，未标注商品按现有脚本当作不相关；无相关标签的查询不参与 Recall/nDCG 的有效分母，Precision/MRR 保留原有口径。AI 试点不是独立人工真值。reference_retrieval/summary.json 明确标记本轮没有重新编码或检索，不用于 TensorRT 达标判断。

## 7. 文件与目录职责

| 路径 | 用途与后续使用方法 |
|---|---|
| inputs/evaluation_config.json | 本轮配置快照，sources 已指向本轮输入副本；以后可用它生成新的 run。 |
| inputs/source_manifest.json | 每份输入的原位置、本轮副本路径、原始字节SHA-256和统一UTF-8/LF文本SHA-256；用于追溯来源。Git可能转换换行，跨系统应比较sha256_utf8_lf。 |
| inputs/runtime_*.json | 三条正式测速原始记录，含中位数、P90、实际 provider、batch 和计时次数。 |
| inputs/accuracy_*.json、baseline.json | 两条后端精度与同源 FP32 基线；用于表 4 和后端误差热力图。 |
| inputs/category_baseline.json | 9 类 FP32 基线；用于分析样本规模和类别难度，不是 TRT 类别差值。 |
| inputs/scale.json | 两塔参数量和理论 FLOPs。 |
| inputs/export_*.json、weight_sizes.json | 文本塔 ONNX 与纯权重文件大小原始凭证；不是运行内存测试。 |
| inputs/reference_*.csv / json | 历史 132 查询的排序、标签和配置；仅供 reference_retrieval/ 复算。 |
| tables/runtime_comparison.csv | 每组 batch 的配对速度、吞吐、加速比与目标判定；后续重绘与写表的主要数据。 |
| tables/accuracy_comparison.csv | 双塔 R@K、相对同源基线的百分点差。 |
| tables/acceptance_checks.csv | 3.1.4 / 3.2.1 的阈值、实际值与通过状态。 |
| tables/model_scale.csv、model_sizes.csv | 参数/FLOPs 以及不同对象的 FP32/FP16 文件大小，避免混用单位。 |
| tables/category_baseline.csv | 9 类的样本数、FP32 基线 R@K；候选池始终是完整 934。 |
| figures/*.png | 450 DPI RGB 中文图，适合直接插入报告。 |
| figures/*.pdf / svg | 同一图的矢量稿，便于排版和后期编辑。 |
| figures/*.figure.json | 图的结论、数据来源、口径、配色、变换与程序检查记录。 |
| figures/图表说明.md | 逐张图的内容、用途和推荐写法。 |
| reference_retrieval/query_metrics.csv | 历史排序复算的逐查询指标，定位既有查询问题。 |
| reference_retrieval/metrics_by_mode.csv、summary.json | 历史查询的分模式/总指标；与主线结果分开。 |
| summary.json | 本轮机器可读结论、各任务判定、限制。 |
| run_metadata.json | 源提交、生成时间、运行软件版本、执行范围。 |
| 测试结果说明.md | 本文，报告写作的阅读入口。 |

## 8. 复现与后续需要本人完成的行为

仓库根目录运行：

    python evaluation/retrieval/code/evaluate_acceleration.py

默认拒绝覆盖已有 run；重跑请指定新的 --run-id，或在确认后使用 --overwrite。只重绘已有结果：

    python evaluation/retrieval/code/render_acceleration_charts.py --run-dir evaluation/retrieval/results/runs/{summary['run_id']}

本轮使用现有 numpy、matplotlib、Pillow 即可；依赖见 evaluation/retrieval/requirements-report.txt，不需要模型权重和训练环境。

现场演示/录屏需在持有 epoch3.pt 和双塔 ONNX 的训练机完成。实际操作命令、环境约束、可交付项与未完成项见 docs/流程与交接/实验三杜军博任务交付.md。本轮没有现场录屏，不把演示脚本当作演示完成。正式实验三 Typst/PDF 由报告成员整合，本轮提供评测图、表及可直接引用的结论。
"""


def run(config_path: Path, run_id: str, overwrite: bool, plots: bool) -> Path:
    config = read_json(config_path)
    run_id = run_id or config["run_id"]
    if not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise ValueError("--run-id 必须是单层目录名")
    source_paths = {key: resolve_relative(value) for key, value in config["sources"].items()}
    # Check required files before creating an output directory.
    for path in source_paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"缺少凭证：{path.relative_to(REPO_ROOT).as_posix()}")
    loaded = {key: read_json(path) for key, path in source_paths.items() if path.suffix == ".json"}
    thresholds = config["thresholds"]
    runtime = [row for group in config["runtime_groups"]
               for row in runtime_rows(loaded[group["source"]], group, thresholds)]
    baseline = loaded["baseline"]
    accuracy = [{
        "group": "baseline", "backend": "PyTorch FP32", "n_texts": baseline["n_texts"],
        "candidate_pool": baseline["candidate_pool"],
        **{key: baseline["scores"][key] for key in METRICS},
        **{f"delta_{key}_pp": 0.0 for key in METRICS},
        "accuracy_pass": True, "graph_accuracy_pass": True, "source": "baseline",
    }]
    accuracy += [accuracy_row(loaded[g["source"]], baseline, g, thresholds) for g in config["accuracy_groups"]]
    checks = acceptance_rows(runtime, accuracy, config["primary_group"], thresholds)
    scale = loaded["scale"]
    scale_rows = [{"tower": tower, "params": scale["params"][tower],
                   "flops": scale["flops_forward_batch1"][tower]}
                  for tower in ("visual", "text", "total")]
    categories = [{"category": category, **values}
                  for category, values in loaded["category_baseline"]["by_category"].items()]
    sizes = [{"object": f'{loaded[key]["tower"]}_onnx', "precision": loaded[key]["precision"],
              "size_mib": loaded[key]["onnx_mb"], "source": key}
             for key in ("export_fp32", "export_fp16")]
    sizes += [{"object": "pure_weights", "precision": r["mode"], "size_mib": r["bytes"] / (1024 ** 2),
               "source": "weight_sizes"} for r in loaded["weight_sizes"]["results"] if r["mode"] in {"fp32w", "fp16"}]
    output = RUNS_ROOT / run_id
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise FileExistsError("结果目录已存在。请更换 --run-id 或显式使用 --overwrite。")
    if any(path.is_relative_to(output.resolve()) for path in source_paths.values()):
        raise ValueError("输入快照位于输出目录内，请改用新的 --run-id，避免覆盖输入。")
    output.mkdir(parents=True, exist_ok=True)
    inputs = output / "inputs"
    inputs.mkdir(exist_ok=True)
    manifest = []
    snapshot_config = json.loads(json.dumps(config))
    snapshot_config["run_id"] = run_id
    for key, original in source_paths.items():
        dest = inputs / (key + original.suffix)
        shutil.copy2(original, dest)
        saved_path = dest.relative_to(REPO_ROOT).as_posix()
        snapshot_config["sources"][key] = saved_path
        manifest.append({
            "id": key, "source": original.relative_to(REPO_ROOT).as_posix(),
            "snapshot": saved_path, "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            "sha256_utf8_lf": hashlib.sha256(dest.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest(),
        })
    write_json(inputs / "evaluation_config.json", snapshot_config)
    write_json(inputs / "source_manifest.json", manifest)
    for name, rows in (("runtime_comparison", runtime), ("accuracy_comparison", accuracy),
                       ("acceptance_checks", checks), ("model_scale", scale_rows),
                       ("category_baseline", categories), ("model_sizes", sizes)):
        write_csv(output / "tables" / f"{name}.csv", rows)
    ref = replay_reference(source_paths, output)
    timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    try:
        commit = subprocess.check_output(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unavailable"
    summary = {
        "run_id": run_id, "generated_at": timestamp, "source_mode": config["source_mode"],
        "new_model_inference_executed": False, "dataset_previously_verified": True,
        "main_scope": "visual_forward_speed_and_dual_encoder_recall_consistency",
        "n_texts": baseline["n_texts"], "candidate_pool": baseline["candidate_pool"],
        "thresholds": thresholds, "primary_group": config["primary_group"],
        "runtime": runtime, "accuracy": accuracy, "model_scale": scale_rows, "model_sizes": sizes,
        "acceptance_checks": checks,
        "task_3_1_4_pass": all(c["passed"] for c in checks if c["task"] == "3.1.4"),
        "task_3_2_1_pass": all(c["passed"] for c in checks if c["task"] == "3.2.1"),
        "reference_retrieval": ref,
        "limitations": [
            "使用用户认可的训练机凭证，未新增模型推理；源 JSON 未独立记录 GPU 型号。",
            "速度只覆盖图像塔 forward，不代表文本塔、FAISS 或端到端查询速度。",
            "精度一致性数据是整体 R@K，缺少 TRT 分类别及逐样本排名，不能生成对应误差结论。",
            "历史 132 查询仅复算原排序，未重新用微调权重或 TRT 查询。",
            "单轮 warmup=10、iters=20；没有重复实验的置信区间。",
            "export_report 仅保留最后导出的文本塔，不能推出双塔 ONNX 总体积。",
            "量化、4-bit、剪枝不在本轮主线；现场演示/录屏尚需本人在训练机执行。",
        ],
    }
    write_json(output / "summary.json", summary)
    write_json(output / "run_metadata.json", {
        "run_id": run_id, "generated_at": timestamp, "source_commit": commit,
        "config": config_path.relative_to(REPO_ROOT).as_posix(),
        "source_mode": config["source_mode"], "author_task": "杜军博：推理加速评测与交付",
        "python": platform.python_version(), "platform": platform.system(),
        "executed": ["accepted_measurement_replay", "historical_ranking_metric_replay", "report_generation"],
        "not_executed": ["onnx_export", "new_gpu_benchmark", "new_132_query_retrieval", "live_demo_recording"],
        "excluded_sources": config["excluded_sources"],
    })
    (output / "测试结果说明.md").write_text(report_text(summary, runtime, accuracy, checks), encoding="utf-8")
    if plots:
        from render_acceleration_charts import render
        render(output)
    print(f"结果：{output.relative_to(REPO_ROOT).as_posix()}")
    print(f"3.1.4：{'通过' if summary['task_3_1_4_pass'] else '未通过'}；"
          f"3.2.1：{'通过' if summary['task_3_2_1_pass'] else '未通过'}")
    return output


def main() -> int:
    ap = argparse.ArgumentParser(description="沿用已核验凭证评测实验三推理加速，生成表格、中文图与说明。")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--skip-plots", action="store_true")
    args = ap.parse_args()
    output = run(resolve_relative(args.config), args.run_id, args.overwrite, not args.skip_plots)
    summary = read_json(output / "summary.json")
    return 0 if summary["task_3_1_4_pass"] and summary["task_3_2_1_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
