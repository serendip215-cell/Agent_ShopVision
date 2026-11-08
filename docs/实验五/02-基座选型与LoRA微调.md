# 实验五 5.2 基座模型选型与 LoRA 微调

> **2026-11-08 22:00 修订**：修正了本文多处与实际执行不符的内容
> （训练平台、超参、已完成项被写成待办）。实际执行以本文为准。

负责人：刘凡思雨（实际由 Alma 执行）。
前置：5.1 产出的 `data/agent/agent_finetune_data.json`。

本文对应任务书 **5.2.1（选型与评估）** 与 **5.2.2（LoRA 微调）**。

## 一、先说结论

**基座选 `Qwen/Qwen3-4B-Instruct-2507`（4.02B，Apache-2.0），QLoRA 4-bit。**
10GB 以上显存的单卡即可完成训练（实测在 RTX 4090 48GB 上跑，仅用 8-10GB）。

选它有四个硬理由，逐条对应我们的实际约束：

| 理由 | 具体数字 |
|---|---|
| 任务书点名的三个候选，全都训不了 | DeepSeek-V4.1-Flash **763.2B**、GLM-5.3 **753.3B**、GLM-5.3-Flash **321.3B**（HuggingFace 实际参数量，2026-11-08 核实）。这是几百 B 的 MoE，全参微调要几十张 A800 |
| 我们只有 100 条初始数据 | 折算约 9.3k token。4B 在这个量级刚好能学格式，再大就严重过拟合 |
| 本机只有 4GB 显存 | RTX 3050 Ti Laptop / 4GB，且装的是 CPU 版 torch，**本地完全跑不了 4B** |
| 租卡成本极低 | AutoDL 按量计费，v2 重训总共约 4 分钟，**成本不到 ¥1** |

## 二、候选对比（2026-11-08 HuggingFace 实测参数量）

| 候选 | 实际参数量 | 许可 | 可微调 | 单卡最低显存（QLoRA 4-bit） | 判定 |
|---|---:|---|---|---:|---|
| `deepseek-ai/DeepSeek-V4.1-Flash-1017` | **763.2B** | MIT | ❌ | 数百 GB | 方案点名但不可行 |
| `zai-org/GLM-5.3` | **753.3B** | other | ❌ | 数百 GB | 同上 |
| `zai-org/GLM-5.3-Flash` | **321.3B** | MIT | ❌ | 150GB+ | 同上 |
| `Qwen/Qwen3.5-4B` | 4.7B | — | ⚠️ 多模态 | ~12GB | 备用；纯文本任务用不上视觉塔 |
| **`Qwen/Qwen3-4B-Instruct-2507`** | **4.02B** | **Apache-2.0** | ✅ | **~10GB** | **采用** |
| `Qwen/Qwen3-8B` | 8.2B | — | ✅ | ~14GB | 数据量小，8B 更易过拟合 |
| `Qwen/Qwen3-1.7B` | 2.03B | Apache-2.0 | ✅ | ~5GB | 兜底；JSON 格式约束力弱于 4B |
| `Qwen/Qwen2.5-3B-Instruct` | 3.09B | other | ✅ | ~7GB | 备选；许可不如 Apache-2.0 干净 |

**为什么不用更大的**：初始只有 100 条数据，训 8B 的验证损失会在第 2 epoch 就开始回升。
用 4B 是为了让「学格式」而非「背数据」发生。

**为什么不用多模态的 Qwen3.5-4B**：三类任务（属性抽取、意图解析、工具调用）全是
纯文本进纯文本出，视觉塔纯属浪费显存与下载时间。图像能力已固化成实验 4 的
`/api/v1/image` 接口，5.2 不需要再持有视觉模型。

## 三、基座与微调后的对比怎么测

任务书要求「完成基线与微调后的对比」。口径写死在
`scripts/agent/finetune/eval_baseline_vs_lora.py`，机器判定，不靠人眼：

| 任务 | 判定方式 | 满分构成 |
|---|---|---|
| attribute | 从「商品大类：X；细分类：Y；颜色：Z；材质：W」模板串抽四字段比对 | 命中字段数 / 4 |
| intent | 解析 JSON，比对 `intent` / `category` / `top_k` | 命中项 / 3 |
| tool_call | 解析 JSON，比对 `tool` 名与 `arguments.{query,category,top_k}` | 工具名错整条 0 分；对则 (1+参数命中) / 4 |

**额外单列「输出是否合法 JSON」**：因为 5.3 的 `_parse_intent` 直接吃 JSON，
模型输出「好的，我来帮您…」就等于不可用。这个指标比准确率更硬。

评测用贪心解码（`do_sample=False`）。**注意**：即便贪心，换机器/换 torch 版本后
浮点累加顺序不同，边界样本仍可能漂移（实测 v1 在 5060 是 20%、在 3080Ti 是 10%），
所以报告里引用数字要注明机器。

## 四、LoRA 超参设计依据

### v1（初始数据 100 条，tool_call 15 条）

| 参数 | 取值 | 依据 |
|---|---|---|
| `r` | 16 | 小数据 + 格式学习任务，r=8 欠拟合、r=32 过拟合；16 是常见中点 |
| `lora_alpha` | 32 | 与 r 保持 2:1，peft 官方示例的稳定配比 |
| `lora_dropout` | 0.05 | 数据量小，需要一点正则防记忆 |
| `target_modules` | q/k/v/o + gate/up/down | 注意力与 MLP 全覆盖；只训 attention 收敛慢 |
| `lr` | 1e-4 | LoRA 常用区间 1e-4~3e-4 的低端，小数据取低值更稳 |
| `batch_size` × `grad_accum` | 2 × 8 = 16 | 等效 batch 16；显存不足时降到 1×16 |
| `epochs` | **3** | 100 条 × 3 ≈ 300 步；超过 3 轮必过拟合 |
| `max_seq_len` | 1024 | 数据最长 189 字符，1024 留足余量且不浪费显存 |
| 4-bit | nf4 + double quant | 显存减半，精度损失在 SFT 场景可忽略 |

梯度检查点默认开（`use_reentrant=False`），这是 10-16GB 卡能跑起来的必要条件。

### v2（扩充数据 163 条，tool_call 78 条）

**只改一处：`epochs` 3 → 5**，其余与 v1 完全一致，保证可比。

为什么是 5：数据从 100 条增到 163 条（train 153），单 epoch 步数变多，
但 tool_call 样本的绝对数量仍少，需要多看几轮才能把「从商品名推断类目」学稳。

## 五、v1 数据集的致命缺陷（v2 已修）

这是 5.2 → 5.3 交接后才发现的问题，写在这里供报告「问题与解决方案」使用：

**5.1 生成的 tool_call 样本 15/15 都是这个句式**：

```
帮我搜索XXX，限制在X类，返回N个结果
        ↑ 类目明写在句子里，模型只要照抄
```

模型因此学到的是「**抽取句中已给的类目**」，而不是「**从商品名推断类目**」。
在口语评测集上类目准确率只有 10%。

v2 的做法见 [`09-5.3优化实跑：扩充数据重训.md`](09-5.3优化实跑：扩充数据重训.md)：
重建 78 条 tool_call，**query 里不含类目名**，逼模型自己推断。

## 六、执行流程（实际走过的路）

### 1. 数据转换

```bash
# v1
python scripts/agent/finetune/prepare_sft_data.py
# v2（扩充数据）
python scripts/agent/finetune/prepare_sft_data.py \
    --src data/agent/agent_finetune_data_expanded.json \
    --out-dir data/agent/sft_expanded
```

- 切分按 `sha256(item_id) % 100 < 10`，与实验2 的 `item_id` 哈希口径一致，避免同商品跨集泄漏
- v1：train 89 / valid 11（attribute 5、intent 5、tool_call 1）
- v2：train 153 / valid 10
- 格式：OpenAI messages，**不加 system prompt**（Qwen3 的 chat template 对 system 里的任务约束响应较弱）

### 2. 训练：实际用的是 AutoDL，不是 SCNet

**这一点必须如实记录。** 原计划用 SCNet，但**账户机时配额为 0**
（网页显示 `GPU 0 卡时`、`暂无存储资源`），购买「模型训练」时点挂载源码路径
会弹「当前区域暂未开通」。充值余额 ¥9.95 不转化为算力配额，
A800 需走包年包月审批。**最终改用 AutoDL**。

| 版本 | 机器 | 显存 | 耗时 | 成本 |
|---|---|---|---:|---:|
| v1 | AutoDL RTX 4090 48GB（vGPU 切分） | 48GB | **57.53 秒**（日志精确值） | 约 ¥0.13 |
| v2 | AutoDL RTX 3080 Ti 12GB | 12GB | 约 3-5 分钟（从启动到 adapter 落盘的观察值，训练日志未保存） | 约 ¥0.2 |

```bash
# 实际使用的命令（两份机器都一样）
python scripts/agent/finetune/train_lora.py \
    --model <模型本地路径> \
    --train-file data/agent/sft/train.jsonl \
    --valid-file data/agent/sft/valid.jsonl \
    --output runs/5.x_lora \
    --epochs <3 或 5> --batch-size 2 --grad-accum 8 \
    --lr 1e-4 --lora-r 16 --lora-alpha 32
```

### 3. 模型下载：必须走 ModelScope

AutoDL 上 **HuggingFace 直连不通**（curl 返回 000）。
`hf-mirror.com` 可达，但 `huggingface_hub 2.4.0` 对 `HF_ENDPOINT` 的处理变了，
`AutoConfig.from_pretrained` 仍报 `OSError`，`hf_hub_download` 报
`TypeError: process() takes no keyword arguments`。

**可行解法**：

```python
from modelscope import snapshot_download
p = snapshot_download('Qwen/Qwen3-4B-Instruct-2507', cache_dir='/root/models')
# -> /root/models/models/Qwen--Qwen3-4B-Instruct-2507/snapshots/master
```

约 8GB，5-19 MB/s，实测 9 分 17 秒。拿到本地路径后 `--model <路径>` 即可，
完全绕开 HF。

### 4. 评测

```bash
# 基座基线
python scripts/agent/finetune/eval_baseline_vs_lora.py --tag baseline

# LoRA 后
python scripts/agent/finetune/eval_baseline_vs_lora.py \
    --adapter <output>/final_adapter --tag lora

# 对比表
python scripts/agent/finetune/eval_baseline_vs_lora.py --compare \
    data/agent/finetune/eval_baseline.json data/agent/finetune/eval_lora.json
```

### 5. 交付

`final_adapter/` 整个目录（64MB）。5.3 的 `_parse_intent` 用 peft 挂载，
方式与本仓库 `eval_baseline_vs_lora.py` 的 `load_model()` 一致，可直接复用。

**当前仓库里有两个版本**：

| 目录 | 说明 | 演示用 |
|---|---|---|
| `dist/lora_adapter/` | v1（原 100 条数据） | ❌ 纯模型只有 10% |
| **`dist/lora_adapter_v2/`** | **v2（扩充 163 条数据重训）** | ✅ **纯模型 90%** |

## 七、SCNet 启动脚本（保留供未来使用）

仓库里有两个脚本，都在 `scripts/agent/finetune/`：

| 脚本 | 用途 |
|---|---|
| `scnet_start.sh` | SCNet「模型训练」的完整启动脚本，含依赖安装、模型下载、失败降级 |
| `scnet_platform_start.sh` | 精简版，假设训练包已上传 |

**当前状态：未使用**（机时配额为 0）。若后续账户开通算力，可参考
`scnet_start.sh` 里的配置：加速卡选 **NVIDIA A800 / L20 / 4090**，
**不要选 DTK 国产卡**（`bitsandbytes` 只支持 CUDA，QLoRA 跑不了）。

## 八、已知风险与应对

| 风险 | 应对 |
|---|---|
| HF 下不动模型 | **走 ModelScope**（唯一实测可行方案） |
| `bitsandbytes` 装不上 | 脚本会自动 `--no-4bit` 重跑；但 8G 卡上全精度会 OOM，需换大卡 |
| 国产 DTK 卡不支持 CUDA | 换 NVIDIA 卡（A800 / L20 / 4090） |
| valid 样本少，指标波动大 | 报告必须写明样本量；v1 的 tool_call 只有 1 条，**该单项不具统计意义** |
| 小数据容易过拟合 | 固定 epoch 数，看 valid loss 曲线 |
| 换机器基线漂移 | 报告引用的数字必须注明机器（见第三节） |

## 九、微调前后对比

### v1（初始 100 条数据，AutoDL RTX 4090 实测）

| 任务 | 基座 | LoRA v1 | 变化 | 样本数 |
|---|---:|---:|---:|---:|
| attribute（字段级） | 28.33% | **100.00%** | +71.67pp | 5 |
| intent（三键） | 0.00% | **66.67%** | +66.67pp | 5 |
| tool_call | 0.00% | 0.00% | 0 | **1** |
| 输出合法 JSON 率 | 100% | 100% | 0 | 6 |
| **总体** | **12.88%** | **75.76%** | +62.88pp | 11 |

训练：3 epoch / 18 步 / 57.53 秒 / train_loss 2.161 / eval_token_acc 0.6894。

**tool_call 为 0 的原因**：唯一验证样本把 `text_search` 写成 `tool_search`，
三个参数全对，仅工具名错一个字母。训练集 tool_call 仅 14 条，4B 记不牢专有名词。
该单项 n=1，**不具统计意义**。

### v2（扩充 163 条数据，AutoDL RTX 3080Ti 实测）

5.3 的 10 轮评测集上，**纯模型 90%、加后处理 100%**（详见 `09` 文档）。
两份数据集的评测口径不同（v1 是 11 条混合任务，v2 是 10 轮工具调用），不能直接横比。

## 十、报告口径（红线）

| 可以写 | 不能写 |
|---|---|
| v1 的 75.76% 是 11 条验证集上的成绩，要注明样本量 | 把 75.76% 说成泛化能力 |
| v2 纯模型 90%，是扩充数据重训的真实提升 | 「微调后 100%」而不提后处理贡献多少 |
| 训练平台是 AutoDL（SCNet 因配额为 0 未用成） | 写成「在 SCNet 上训练」 |

完整实跑记录见 [`03-微调结果实跑记录.md`](03-微调结果实跑记录.md)，
v2 重训过程见 [`09-5.3优化实跑：扩充数据重训.md`](09-5.3优化实跑：扩充数据重训.md)。