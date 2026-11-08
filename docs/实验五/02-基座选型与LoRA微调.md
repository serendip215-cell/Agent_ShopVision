# 实验五 5.2 基座模型选型与 LoRA 微调

负责人：刘凡思雨。前置：5.1 产出的 `data/agent/agent_finetune_data.json`（100 条，已入库）。

本文写于 2026-11-08，对应任务书 5.2.1（选型与评估）与 5.2.2（LoRA 微调）。

## 一、先说结论

**基座选 `Qwen/Qwen3-4B-Instruct-2507`（4.02B，Apache-2.0），QLoRA 4-bit，单卡 16GB 即可跑完。**

选它有四个硬理由，逐条对应我们的实际约束：

| 理由 | 具体数字 |
|---|---|
| 任务书点名的三个候选，本地全都训不了 | DeepSeek-V4.1-Flash **763B**、GLM-5.3 **753B**、GLM-5.3-Flash **321B**（HuggingFace 实际参数量，2026-11-08 核实）。这是几百 B 的 MoE，全参微调要几十张 A800 |
| 我们只有 100 条数据 | 折算约 9.3k token。4B 在这个量级刚好能学格式，再大就严重过拟合 |
| 本组机器只有 4GB 显存 | RTX 3050 Ti Laptop / 4GB。本地连 4B 的 4-bit（约 2.3GB 权重）都紧张，所以训练放 SCNet |
| SCNet 上最便宜 | 异构加速卡AI 64GB ¥2.53/时。4B QLoRA 单卡 10-20 分钟跑完，**单次成本不到 ¥1** |

## 二、候选对比（2026-11-08 HuggingFace 实测参数量）

| 候选 | 实际参数量 | 许可 | 本地可微调 | 单卡最低显存（QLoRA 4-bit） | 判定 |
|---|---:|---|---|---:|---|
| `deepseek-ai/DeepSeek-V4.1-Flash-1017` | **763.2B** | MIT | ❌ | 数百 GB | 方案点名但不可行 |
| `zai-org/GLM-5.3` | **753.3B** | other | ❌ | 数百 GB | 同上 |
| `zai-org/GLM-5.3-Flash` | **321.3B** | MIT | ❌ | 150GB+ | 同上 |
| `Qwen/Qwen3.5-4B` | 4.7B | — | ⚠️ 多模态 | ~12GB | 备用；只做文本任务用不上视觉塔 |
| **`Qwen/Qwen3-4B-Instruct-2507`** | **4.02B** | **Apache-2.0** | ✅ | **~8GB** | **采用** |
| `Qwen/Qwen3-8B` | 8.2B | — | ✅ | ~14GB | 数据量太小，8B 更容易过拟合 |
| `Qwen/Qwen3-1.7B` | 2.03B | Apache-2.0 | ✅ | ~5GB | 兜底；JSON 格式约束力弱于 4B |
| `Qwen/Qwen2.5-3B-Instruct` | 3.09B | other | ✅ | ~7GB | 备选；许可不如 Apache-2.0 干净 |

**为什么不用更大的**：100 条数据训 8B，验证损失会在第 2 epoch 就开始回升。这是参数越多、越容易记住训练集的问题。用 4B 是为了让「学格式」而不是「背数据」发生。

**为什么不用多模态的 Qwen3.5-4B**：我们的三类任务（属性抽取、意图解析、工具调用）全是纯文本进纯文本出，视觉塔纯属浪费显存和下载时间。实验 1–4 的图像能力已经固化成实验 4 的 `/api/v1/image` 接口，5.2 不需要再持有视觉模型。

## 三、基座与微调后的对比怎么测

任务书要求「完成基线与微调后的对比」，我们的口径写死在 `eval_baseline_vs_lora.py` 里，机器判定，不靠人眼：

| 任务 | 判定方式 | 满分构成 |
|---|---|---|
| attribute | 从「商品大类：X；细分类：Y；颜色：Z；材质：W」模板串抽四字段比对 | 命中字段数 / 4 |
| intent | 解析 JSON，比对 `intent` / `category` / `top_k` | 命中项 / 3 |
| tool_call | 解析 JSON，比对 `tool` 名与 `arguments.{query,category,top_k}` | 工具名错整条 0 分；对则 (1+参数命中) / 4 |

**额外单列「输出是否合法 JSON」**：因为 5.3 的 `_parse_intent` 直接吃 JSON，模型输出「好的，我来帮您…」就等于不可用。这个指标比准确率更硬，报告里要单独写。

评测用贪心解码（`do_sample=False`），保证任何人重跑得到同一个分数。

## 四、LoRA 超参设计依据

| 参数 | 取值 | 依据 |
|---|---|---|
| `r` | 16 | 100 条数据 + 格式学习任务，r=8 欠拟合、r=32 过拟合；16 是这类 SFT 的常用中点 |
| `lora_alpha` | 32 | 与 r 保持 2:1，是 peft 官方示例的稳定配比 |
| `lora_dropout` | 0.05 | 数据量小，需要一点正则防记忆 |
| `target_modules` | q/k/v/o + gate/up/down | 注意力与 MLP 全覆盖；只训 attention 在格式任务上收敛慢 |
| `lr` | 1e-4 | LoRA 常用区间 1e-4~3e-4 的低端，小数据取低值更稳 |
| `batch_size` × `grad_accum` | 2 × 8 = 16 | 等效 batch 16；显存不足时降到 1×16 |
| `epochs` | 3 | 100 条 × 3 = 300 步，配合 valid 每 20 步评测；超过 3 轮必过拟合 |
| `max_seq_len` | 1024 | 数据最长 189 字符，1024 留足余量且不浪费显存 |
| 4-bit | nf4 + double quant | 显存减半，精度损失在 SFT 场景可忽略 |

**梯度检查点默认开**（`use_reentrant=False`），这是 4GB~16GB 卡能跑起来的必要条件。

## 五、执行流程

### 1. 数据转换（已在本机验证跑通）

```bash
python scripts/agent/finetune/prepare_sft_data.py
```

产出 `data/agent/sft/{train,valid}.jsonl` + `manifest.json`。

- 切分按 `sha256(item_id) % 100 < 10`，与实验2 的 `item_id` 哈希口径一致，避免同商品跨集泄漏
- 实际切分：**train 89 条 / valid 11 条**（attribute 5、intent 5、tool_call 1）
- 格式：OpenAI messages，**不加 system prompt**（Qwen3 的 chat template 对 system 里的任务约束响应较弱）

### 2. 上传到 SCNet 并训练

启动脚本：`scripts/agent/finetune/scnet_start.sh`，整段贴进 SCNet「模型训练 → 创建训练 → 启动脚本」。

控制台配置对照：

| 表单项 | 填什么 |
|---|---|
| 加速卡 | **异构加速卡AI 64GB**（¥2.53/时，标"推荐"）或 **A800 80GB** |
| 每实例加速卡数量 / 实例数 | **1 / 1** |
| 系统盘 | 50GB 免费额度 |
| 训练镜像 | PyTorch + **CUDA 12.x**（卡是 12.4 就别选 13.0） |
| 自定义挂载 | 把仓库挂到 `/workspace` |
| 运行时限 | **1 小时**（实际 10-20 分钟） |
| 任务最大重启次数 | 1 或 2 |

**不要选 DTK 的国产卡**（异构加速卡 BW / AI 的 DTK 列）：`bitsandbytes` 只支持 CUDA，国产卡上 QLoRA 跑不了，脚本会自动退回纯 LoRA，但那样显存需求翻倍。

### 3. 评测

```bash
# 基座基线
python scripts/agent/finetune/eval_baseline_vs_lora.py --tag baseline

# LoRA 后
python scripts/agent/finetune/eval_baseline_vs_lora.py \
    --adapter data/agent/finetune/scnet_run1/final_adapter --tag lora

# 对比表
python scripts/agent/finetune/eval_baseline_vs_lora.py --compare \
    data/agent/finetune/eval_baseline.json data/agent/finetune/eval_lora.json
```

### 4. 交付给 5.3

`final_adapter/`（约 30–60MB）整个目录交出去。5.3 的 `_parse_intent` 用 peft 挂载即可，实现方式与本仓库 `eval_baseline_vs_lora.py` 的 `load_model()` 完全一致，可直接复用。

## 六、已知风险与应对

| 风险 | 应对 |
|---|---|
| SCNet 拉 HuggingFace 超时 | 脚本默认 `HF_ENDPOINT=https://hf-mirror.com`，可改环境变量覆盖 |
| `bitsandbytes` 在某镜像装不上 | 脚本训练失败后自动 `--no-4bit` 重跑一次 |
| 国产 DTK 卡不支持 CUDA | 换 NVIDIA 卡（A800 / L20 / 4090），或接受纯 LoRA + 更大显存 |
| valid 只有 11 条，指标波动大 | 报告里必须写明样本量；tool_call 只有 1 条验证样本，**该单项分数不具统计意义**，要如实标注 |
| 100 条数据容易过拟合 | 固定 3 epoch，看 valid loss 曲线；若第 2 轮就回升，报告里写 2 epoch 的结果 |

## 七、待如实标注的事项

- 验证集 11 条，其中 tool_call 只 1 条 —— 该项指标不具统计意义，不能当作「工具调用准确率」汇报。任务书要求的「10 轮准确率 ≥90%」应在 5.4 端到端联调时用完整 10 轮真实对话测，不是拿这 1 条验证样本充数。
- 微调前后的对比数字，待 SCNet 跑完后回填本文件第四节后的空表。
- 本地 `RTX 3050 Ti 4GB` 无法完成任何 4B 训练，所有训练数字必须标注来自 SCNet 哪台机器、哪张卡。

## 八、微调前后对比（已在 AutoDL RTX 4090 实跑，2026-11-08）

| 任务 | 基座 | LoRA 微调后 | 变化 | 样本数 |
|---|---:|---:|---:|---:|
| attribute（字段级） | 28.33% | **100.00%** | **+71.67pp** | 5 |
| intent（三键） | 0.00% | **66.67%** | **+66.67pp** | 5 |
| tool_call | 0.00% | 0.00% | 0 | **1** |
| 输出合法 JSON 率 | 100% | 100% | 0 | 6 |
| **总体** | **12.88%** | **75.76%** | **+62.88pp** | 11 |

训练：3 epoch / 18 步 / **57.53 秒** / train_loss 2.161 / eval_token_acc 0.6894。
机器 RTX 4090 48GB（AutoDL，¥2.88/时），总成本约 **¥0.13**。

**tool_call 为 0 的真实原因**：唯一验证样本把 `text_search` 写成 `tool_search`，
三个参数（query/category/top_k）全对，仅工具名错一个字母。训练集 tool_call 仅 14 条，
4B 模型没记牢专有名词。该单项 n=1，**不具统计意义**，不得作为工具调用准确率汇报。

完整记录（含 HF 下载失败的坑、复现步骤）见 [`03-微调结果实跑记录.md`](03-微调结果实跑记录.md)。