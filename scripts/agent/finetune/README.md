# scripts/agent/finetune — 实验5 5.2 模型选型与 LoRA 微调

> 对应任务书 5.2.1（选型与评估）与 5.2.2（LoRA 微调）。
> 负责人：刘凡思雨。前置：5.1 的 `data/agent/agent_finetune_data.json`。
> 选型结论与对比数据见 [`docs/实验五/02-基座选型与LoRA微调.md`](../../../docs/实验五/02-基座选型与LoRA微调.md)。

## 结论一句话

基座用 **`Qwen/Qwen3-4B-Instruct-2507`**（4.02B，Apache-2.0），QLoRA 4-bit，SCNet 单卡 10–20 分钟、成本不到 ¥1。

方案文档点名的 DeepSeek-V4.1-Flash（763B）与 GLM-5.3（753B）是几百 B 的 MoE，全参与 LoRA 都超出本组资源，**不可行**。

## 文件

| 文件 | 作用 |
|---|---|
| `prepare_sft_data.py` | 5.1 的 instruction/input/output → OpenAI messages，按 `item_id` 哈希切 train/valid |
| `train_lora.py` | SFTTrainer + peft QLoRA 训练入口，trl 新旧版本自适应 |
| `eval_baseline_vs_lora.py` | 基座 vs LoRA 评测 + `--compare` 出对比表 |
| `scnet_start.sh` | **SCNet「模型训练」启动脚本**，整段贴进控制台即可 |
| `_selfcheck.py` | 评分函数自检（不加载模型，纯逻辑，11 项） |
| `requirements.txt` | 5.2 训练侧依赖（在上级 `requirements.txt` 基础上补 trl/bitsandbytes） |

## 三步跑完

```bash
# 1. 数据转换（本机已验证：train 89 / valid 11）
python scripts/agent/finetune/prepare_sft_data.py

# 2. 训练（SCNet 上；本地 4GB 显存跑不动）
bash scripts/agent/finetune/scnet_start.sh

# 3. 评测与对比
python scripts/agent/finetune/eval_baseline_vs_lora.py --tag baseline
python scripts/agent/finetune/eval_baseline_vs_lora.py \
    --adapter data/agent/finetune/scnet_run1/final_adapter --tag lora
python scripts/agent/finetune/eval_baseline_vs_lora.py --compare \
    data/agent/finetune/eval_baseline.json data/agent/finetune/eval_lora.json
```

## 验证

```bash
# 评分逻辑自检，11 项全 PASS 才可信
python scripts/agent/finetune/_selfcheck.py

# 数据格式
python -c "import json; d=[json.loads(l) for l in open('data/agent/sft/train.jsonl',encoding='utf-8')]; assert d and d[0]['messages']; print('数据格式通过', len(d))"
```

## 常见问题

**Q：为什么不用 8B / 更大的？**
100 条数据训 8B，valid loss 从第 2 epoch 就回升。4B 刚好能学格式而不背数据。

**Q：为什么不用 Qwen3.5-4B（多模态）？**
三类任务全是纯文本进纯文本出。视觉能力已在实验 1–4 固化成实验 4 的 `/api/v1/image`，5.2 不需要再持有视觉塔。

**Q：`bitsandbytes` 装不上？**
脚本会自动 `--no-4bit` 重跑一次。纯 LoRA 显存需求翻倍，A800 80GB 仍然够。

**Q：国产 DTK 卡能跑吗？**
不能跑 QLoRA（bitsandbytes 只支持 CUDA）。选 NVIDIA 的 A800 / L20 / 4090。

**Q：HF 下载卡住？**
脚本默认 `HF_ENDPOINT=https://hf-mirror.com`；要换别的镜像改这个环境变量。

## 交付给 5.3

`final_adapter/` 整个目录（约 30–60MB）。5.3 的 `_parse_intent` 用 peft 挂载，实现可复用本目录 `eval_baseline_vs_lora.py` 里的 `load_model()`。

**注意口轻**：valid 只 11 条，其中 tool_call 仅 1 条。这个单项分数不具统计意义，不能拿来汇报「工具调用准确率 ≥90%」——那要在 5.4 用 10 轮真实对话测。
## 实跑结果（2026-11-08，AutoDL RTX 4090 48GB）

| 任务 | 基座 | LoRA | 样本 |
|---|---:|---:|---:|
| attribute | 28.33% | **100.00%** | 5 |
| intent | 0.00% | **66.67%** | 5 |
| tool_call | 0.00% | 0.00% | 1 |
| **总体** | **12.88%** | **75.76%** | 11 |

训练 57.53 秒 / 3 epoch / 18 步 / train_loss 2.161。完整记录见
[`docs/实验五/03-微调结果实跑记录.md`](../../../docs/实验五/03-微调结果实跑记录.md)。

## 关键坑：HuggingFace 下不动模型

国内机器上 `HF_ENDPOINT=https://hf-mirror.com` **不一定管用**：
`huggingface_hub 2.4.0` 对它的处理变了，`AutoConfig.from_pretrained("Qwen/...")` 照样报
`OSError: Can't load the configuration`，`hf_hub_download` 还会报
`TypeError: process() takes no keyword arguments`。

**可行解法：走 ModelScope，然后把本地路径喂给 `--model`。**

```python
from modelscope import snapshot_download
p = snapshot_download('Qwen/Qwen3-4B-Instruct-2507', cache_dir='/root/models')
# /root/models/models/Qwen--Qwen3-4B-Instruct-2507/snapshots/master
```

```bash
python scripts/agent/finetune/train_lora.py --model /root/models/.../snapshots/master --output /root/runs/run1
```

约 8GB，5–19 MB/s，实测 9 分 17 秒。

## tool_call 为 0 的原因（别当成评测 bug）

唯一验证样本把 `text_search` 写成了 `tool_search`，三个参数全对。训练集 tool_call 仅 14 条，
4B 记不牢专有名词。该单项 n=1，**不具统计意义**，不能汇报成「工具调用准确率」。
改进方向：补样本到 40–60 条 / system prompt 列白名单 / `_parse_intent` 加编辑距离纠错。