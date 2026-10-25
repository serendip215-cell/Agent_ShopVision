# 实验三：算法优化

本文件回答两件事：**实验三做了什么**、**每一项结果存在哪里**。

## 一、做了什么

| 任务 | 状态 | 说明 |
|---|---|---|
| **3.1.4 推理加速**（主线） | ✅ **三项指标全达标** | 导出 ONNX（双塔，fp32/fp16）→ 三条后端对比（ORT-CPU / ORT-CUDA / TensorRT） |
| 3.1.1 模型量化 | 🧊 **冻结** | 6 种精度配置完整实测，裸动态量化最好 −13.06pp，未达任务书 ≤2% 要求；数据全部保留 |
| 3.2.1 计算图优化（阶段 2 选做） | ✅ 随主任务满足 | ONNX + ORT/TRT，提速远超 20%、精度误差 0.00 / −0.43pp |

**核心数字**：TensorRT 相对 PyTorch 推理 —— 延迟 **−57.7%**（batch1）/ −52.7%（batch32）、吞吐 **+136.6%** / +111.5%、精度一致性 **−0.43pp**。

## 二、四条报告要求的对应结果

| 报告要求 | 需要的表/图 | 数据来源 |
|---|---|---|
| 1. 成员构成与分工 | 文字 | `docs/流程与交接/实验三流程与分工.md` §七 分工表 |
| 2. 模型优化对比分析 | **表 1** 参数量/计算量/体积 | `runs/2026-10-24_exp3-speed/flops.json` + `runs/2026-10-23_exp3-quant/quantize_report.json` |
| 2. 精度损失分析 | **表 2** | `runs/2026-10-23_exp3-quant/accuracy/test_*.json`（6 个配置） |
| 2. 误差分布热力图 | **图** | `runs/2026-10-23_exp3-quant/accuracy/by_category_*.json`（9 类别 × 2 配置） |
| 3. 推理加速验证 | **表 3** 速度 | `runs/2026-10-24_exp3-speed/bench_visual_*.json` |
| 3. 异构精度一致性 | **表 4** | `runs/2026-10-24_exp3-speed/onnx_*.json` |
| 4. 关联分析 | 文字 | `runs/2026-10-23_exp3-quant/02-精度评测.md` 第 3 节（分塔 / 粒度）+ 本文档第三节末的分类别观察 |

> 四张表的关键数字都已整理成表，见 [`02-推理加速（3.1.4）.md`](02-推理加速（3.1.4）.md) 第 7 节，可直接抄进报告。

## 三、结果存放在哪里

### 3.1 入库凭证（`docs/optimize/`，KB 级，git 跟踪）

| 文件 | 内容 |
|---|---|
| `runs/2026-10-23_exp3-quant/01-量化转换.md` | 体积表、为什么 INT8 只降 56%、两个坑 |
| `runs/2026-10-23_exp3-quant/02-精度评测.md` | 六配置精度矩阵、分塔分析、**分类别热力图数据与解读** |
| `runs/2026-10-23_exp3-quant/quantize_report.json` | 三份权重的参数量与体积 |
| `runs/2026-10-23_exp3-quant/accuracy/test_{none,fp32,int8,int8-pc,int8-text,int8-visual}.json` | 六种精度的 R@K |
| `runs/2026-10-23_exp3-quant/accuracy/by_category_{fp32,int8-pc}.json` | **9 类别 R@K（热力图数据源）** |
| `runs/2026-10-24_exp3-speed/flops.json` | 参数量 + FLOPs（图像塔 33.70G / 文本塔 8.93G / 合计 42.63G） |
| `runs/2026-10-24_exp3-speed/export_report_{fp32,fp16}.json` | 导出体积与一致性校验 |
| `runs/2026-10-24_exp3-speed/bench_visual_cpu_fp32_t8_all.json` | CPU 加速（**线程对齐**，1.06×） |
| `runs/2026-10-24_exp3-speed/bench_visual_cuda_fp16_cuda_tauto_all.json` | ORT-CUDA（1.05× / 0.95×） |
| `runs/2026-10-24_exp3-speed/bench_visual_cuda_fp16_tensorrt_tauto_all.json` | **TensorRT（2.37× / 2.12×）← 报告表 3 用这个** |
| `runs/2026-10-24_exp3-speed/onnx_fp32_CPUExecutionProvider.json` | ONNX 精度一致性（**0.00pp**） |
| `runs/2026-10-24_exp3-speed/onnx_fp16_TensorrtExecutionProvider.json` | TRT 精度一致性（**−0.43pp**）← 报告表 4 用这个 |

### 3.2 本地大产物（`data/optimize/`，已 gitignore，可由脚本重建）

| 路径 | 内容 | 体积 |
|---|---|---|
| `2026-10-23_exp3-quant/quantized/epoch3_{fp32w,fp16,int8}.pt` | 三份量化权重 | 718 / 359 / 314 MB |
| `2026-10-24_exp3-speed/onnx/visual_{fp32,fp16}.onnx` | 图像塔 | 329 / 165 MB |
| `2026-10-24_exp3-speed/onnx/text_{fp32,fp16}.onnx` | 文本塔 | 410 / 195 MB |
| `2026-10-24_exp3-speed/trt_cache/` | TensorRT 引擎缓存 | 数百 MB |
| 各级 `bench/`、`accuracy/` | 与 docs 下凭证同内容的原始输出 | KB 级 |

重建方式：`scripts/optimize/` 下 7 个脚本，用法见 [`scripts/optimize/README.md`](../../scripts/optimize/README.md)。

## 四、关键数字速查

| 项 | 值 |
|---|---|
| 参数量 | 188,262,912（图像塔 86.19M + 文本塔 102.07M） |
| FLOPs（batch=1） | 42.63 G（图像塔 33.70 G + 文本塔 8.93 G，文本按 52 token） |
| 模型体积 | FP32 718.29 MB / FP16 359.21 MB / INT8 313.88 MB |
| 精度（934 条 test，R@1） | PyTorch-FP32 **58.57**；ORT-FP32 58.57；TRT-FP16 58.14 |
| 速度（图像塔，batch 1 / 32） | TRT 相对 PyTorch-FP16：**2.37× / 2.12×** |
| 精度一致性 | ORT-FP32 **0.00pp**；TRT-FP16 **−0.43pp**（要求 ≤1pp） |

## 五、文档索引

| 文件 | 内容 |
|---|---|
| [`00-方案与口径.md`](00-方案与口径.md) | 体积/精度/延迟的口径定义、三条硬约束、自研评测与官方脚本差 0.21pp 的说明 |
| [`01-代码改动清单.md`](01-代码改动清单.md) | 量化相关代码改动的作用与必要性（review 用） |
| [`02-推理加速（3.1.4）.md`](02-推理加速（3.1.4）.md) | 主任务全文：指标、测量口径、V1–V5、**第 7 节全部实测结果** |
| [`runs/2026-10-23_exp3-quant/`](runs/2026-10-23_exp3-quant/) | 3.1.1 量化的执行记录与凭证 |
| [`runs/2026-10-24_exp3-speed/`](runs/2026-10-24_exp3-speed/) | 3.1.4 加速的凭证（bench / export / accuracy / flops） |
| [`scripts/optimize/README.md`](../../scripts/optimize/README.md) | 7 个脚本的用途、依赖版本、四个已知坑 |

> 编号规则：顶层 `00/01/02` 是方法类文档；`runs/<RUN_ID>/` 内的 `01/02` 是**每轮执行记录**，各自独立编号。

## 六、两个注意事项

1. **`bench_visual_cuda_fp16_tauto_all.json` 是历史遗留**：文件名缺 provider，内容是 TensorRT 首跑（2.50×）。
   报告请用 `bench_visual_cuda_fp16_tensorrt_tauto_all.json`（2.37×）或 `..._cuda_...`（1.05×），两者命名规范、可对应。
2. **`data/optimize/2026-10-23_exp3-quant/quantized/epoch3_int8_statedict.pt`** 是早期诊断产物（约 314 MB），
   结论已取得，可随时删除。
