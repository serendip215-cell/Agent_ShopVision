# 优化脚本（实验三）

本目录服务于实验三（算法优化）。**当前主线是 3.1.4 推理加速**（ONNX + TensorRT），3.1.1 量化已冻结但脚本保留。

## 七个模型侧脚本

| 脚本 | 用途 | 输入 | 产物 |
|---|---|---|---|
| `quantize.py` | 把 `epoch3.pt` 落盘成 fp32w / fp16 / int8 三份并量体积 | 微调权重 | `data/optimize/<RUN>/quantized/` + `quantize_report.json` |
| `eval_quant.py` | 在 934 条 test 上评某个精度的 R@K（PyTorch 侧） | 权重 + 数据集 | `data/optimize/<RUN>/accuracy/test_<quant>.json` |
| `export_onnx.py` | 把单塔导出成 ONNX（先 fp32，可选在图层面转 fp16） | 微调权重 | `data/optimize/<RUN>/onnx/{visual,text}_{fp32,fp16}.onnx` |
| `bench_runtime.py` | 延迟/吞吐基准：PyTorch vs ORT-CPU / ORT-CUDA / TensorRT | ONNX + 权重 | `data/optimize/<RUN>/bench/*.json` |
| `bench_flops.py` | 两个塔的参数量与理论前向 FLOPs（报告表 1 的"计算量"） | 微调权重 | `data/optimize/<RUN>/bench/flops.json` |
| `eval_onnx.py` | 两个 ONNX 塔跑 934 条，算 R@K 并与 PyTorch 基线比 | ONNX + 数据集 | `data/optimize/<RUN>/accuracy/onnx_*.json` |
| `eval_by_category.py` | 按 9 个类别拆分的 R@K（误差热力图的数据源） | 权重 + 数据集 | `data/optimize/<RUN>/accuracy/by_category_<quant>.json` |

所有脚本都会把 KB 级 JSON **自动复制**到 `docs/optimize/runs/<RUN_ID>/` 作为入库凭证；大产物留在 `data/optimize/`（该目录已 gitignore）。

结果复算与报告绘图不需要模型环境，独立入口是 evaluation/retrieval/code/evaluate_acceleration.py，配置和依赖见 evaluation/retrieval/README.md。统一交付位于 evaluation/retrieval/results/runs/exp3_inference_acceleration_20261025/，源凭证仍保留在 docs/optimize/。

本轮正式报告使用同一源JSON里的PyTorch配对基线，warmup=10、iters=20。下文“默认50次”是脚本默认值，不是已经提交凭证的实际计时次数。ORT-CUDA正式JSON给出1.097×/0.933×；测速范围仅图像塔forward，不是用户请求总延迟。原有evaluate_retrieval.py仍用PyTorch编码器，不能把它称为TRT端到端新测。

## 典型流程

```bash
# 3.1.4 主线
python scripts/optimize/export_onnx.py                      # 图像塔 fp32
python scripts/optimize/export_onnx.py --precision fp16     # 图像塔 fp16（图层面转换）
python scripts/optimize/export_onnx.py --tower text         # 文本塔 fp32
python scripts/optimize/export_onnx.py --tower text --precision fp16

python scripts/optimize/bench_runtime.py --device cuda --precision fp16 \
  --provider TensorrtExecutionProvider --batch 1 32         # 测速

python scripts/optimize/eval_onnx.py --precision fp16 \
  --provider TensorrtExecutionProvider                      # 精度一致性

python scripts/optimize/bench_flops.py                      # 参数量 + FLOPs

python scripts/optimize/eval_by_category.py --quant fp32 --device cpu       # 分类别（基线）
python scripts/optimize/eval_by_category.py --quant int8-pc --device cpu    # 分类别（量化）

# 3.1.1（已冻结，保留）
python scripts/optimize/quantize.py --all
python scripts/optimize/eval_quant.py --quant int8 --device cpu
```

## 依赖

| 包 | 版本要求 | 说明 |
|---|---|---|
| torch | 2.7.1+cu128 | 镜像自带 |
| onnx | 1.23.2 | 导出与图层面转换 |
| **onnxruntime-gpu** | **1.22.0** | ⚠️ 1.31 需要 CUDA 13，我们是 12.8，装了会加载失败 |
| **tensorrt** | **10.x（cu12）** | ⚠️ ORT 1.22 链接的是 `libnvinfer.so.10`；装 TRT 11 会回退到 CPU |

运行前要挂库路径（新 shell 必做）：

```bash
export LD_LIBRARY_PATH=$(python -c "
import glob, os
d = []
try:
    import tensorrt_libs; d.append(os.path.dirname(tensorrt_libs.__file__))
except ImportError: pass
d += ['/usr/local/cuda/lib64', '/usr/lib/x86_64-linux-gnu', '/opt/conda/lib']
d += sorted(glob.glob('/opt/conda/lib/python3.11/site-packages/nvidia/*/lib'))
print(':'.join(x for x in d if os.path.isdir(x)))
")
```

## 四个坑（都踩过，别再踩）

1. **不能把 PyTorch 模型 `.half()` 再导 ONNX**：cn_clip 的 `LayerNorm`（`model.py:176`）写死 `x.type(torch.float32)`，
   半精度权重会报 `mixed dtype`。FP16 必须在 **ONNX 图层面**转（`convert_float_to_float16`）。
2. **fp16 模型输入也得 fp16**：喂 float32 会报 `Unexpected input data type`。
3. **ORT / TensorRT 版本必须对齐 CUDA**：见上表。
4. **TensorRT 要显式给 provider_options**：`trt_fp16_enable`、`trt_engine_cache_enable`、`trt_engine_cache_path`，
   否则第一次跑会反复建引擎（很慢）。首次建引擎 5–20 分钟，之后走缓存。

## 结果文件命名

`bench_runtime.py` 的输出名带全部关键配置，互不覆盖：

```
bench_visual_<device>_<precision>_<provider>_t<threads>_<graphopt>.json
例：bench_visual_cuda_fp16_tensorrt_tauto_all.json
```

**测量口径**：只计模型 forward（不含预处理）、warmup 10 次、取中位数、同硬件对比。
PyTorch 与 ORT 的线程数必须一致，否则加速比是假的（我们曾因 PyTorch 只用 4 线程而虚高到 1.66×，对齐后只有 1.06×）。

## 实测结论（详见 `docs/optimize/`）

| 后端 | 相对 PyTorch | 说明 |
|---|---|---|
| ORT-CPU | 1.06× | 无实质收益 |
| ORT-CUDA | 1.097× / 0.933× | 正式JSON复算值，未达目标；图里有Memcpy与CPU回退 |
| **TensorRT-FP16** | **2.37× / 2.12×** | 延迟 −57.7% / −52.7%，吞吐 +136.6% / +111.5% |
| 精度一致性 | ORT-FP32 **0.00pp** / TRT-FP16 **−0.43pp** | 均满足 ≤1pp |
