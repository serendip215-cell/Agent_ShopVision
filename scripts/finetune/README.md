# 微调脚本

本目录是 Chinese-CLIP 微调在本仓库的入口。**日常只用前两个脚本**，第三个是历史留存。

| 脚本 | 用途 | 什么时候用 |
|---|---|---|
| `run_train_single_gpu.sh` | 单卡训练 3 轮，产出 `epoch*.pt` | 需要训练/重训时（当前定稿版本） |
| `run_test_eval.sh` | test 集最终评测（基线 vs 微调） | 训练完成、权重定稿后，**只用一次** |
| `run_train_5epoch.sh` | 5 轮消融实验（**未执行，备用**） | 想验证"3 轮是否欠训练"时才跑 |
| `run_finetune.sh` | 官方 MUGE 模板的移植版（`torch.distributed.launch` + DDP） | **本机跑不通**，仅作参数对照参考 |

## 为什么不用官方模板

官方模板走 `torch.distributed.launch` + DDP，本机 NCCL 的 `all_reduce` 会永久挂死（GPU 0%，
日志不动）。现改用 `NoDDP` + `--skip-aggregate`，完全不产生集合通信。补丁在 [`patches/`](patches/)：

```bash
bash scripts/finetune/patches/apply.sh
```

原因、3 处改动的改前改后代码、`apply.sh` 失效时怎么手工处理，见
[`docs/finetune/04-Chinese-CLIP补丁说明.md`](../../docs/finetune/04-Chinese-CLIP补丁说明.md)。

## 目录约定

**一次实验一个 `RUN_ID`，`experiments/` 与 `docs/finetune/runs/` 同名。**

```
data/processed_data_retrieval/            ← 全部 gitignore，可重建
├── datasets/<DATASET>/                    tsv / jsonl / id_mapping / lmdb
│     ShopVision        = 清洗数据 9,393 条（主实验）
│     ShopVision_uncleaned = 未清洗数据 10,165 条（对照组）
└── experiments/<RUN_ID>/
    ├── checkpoints/epoch{1,2,3}.pt, epoch_latest.pt
    ├── out_<UTC时间戳>.log               训练日志（注意不是 out.log）
    ├── params_<UTC时间戳>.txt            超参快照
    └── eval/                             评测产物（约 40MB，可重算）
        ├── baseline/{test_score.json, test_*.jsonl}
        ├── finetuned_<CKPT>/{test_score.json, test_*.jsonl}   ← 如 finetuned_epoch3
        └── run_manifest.json

docs/finetune/runs/<RUN_ID>/               ← 入库的凭证（KB 级）
├── baseline_test_score.json
├── finetuned_<CKPT>_test_score.json       ← 如 finetuned_epoch3_test_score.json
├── run_manifest.json
├── out_<UTC时间戳>.log
└── params_<UTC时间戳>.txt
```

`run_test_eval.sh` 跑完会自动把上面那 5 个凭证文件同步进 `docs/finetune/runs/<RUN_ID>/`，不需要手动复制。

## 用法

```bash
# 训练（约 6 分钟）
docker exec -it shopvision bash -c "tr -d '\r' < /workspace/scripts/finetune/run_train_single_gpu.sh > /tmp/run.sh && bash /tmp/run.sh"

# 评测（约 3 分钟）
docker exec -it shopvision bash -c "tr -d '\r' < /workspace/scripts/finetune/run_test_eval.sh > /tmp/eval.sh && bash /tmp/eval.sh"
```

`tr -d '\r'` 用于清掉 Windows 换行符，避免 `\r` 报错。

## 用环境变量切换实验（不复制脚本）

两个脚本的默认值就是「清洗数据 · 3 轮」那次实验，不加变量时行为与之前完全一致。
需要跑别的组合时用环境变量覆盖：

| 变量 | 脚本 | 作用 | 默认值 |
|---|---|---|---|
| `RUN_ID` | 两个都要 | 实验名；决定读哪个 `experiments/<RUN_ID>/`、凭证写到哪里 | `2026-10-18_bs32_lr1e-5` |
| `DATASET` | 仅训练 | 读哪份 lmdb：`datasets/<DATASET>/lmdb/{train,valid}` | `ShopVision` |
| `CKPT_NAME` | 仅评测 | 用哪个权重 | `epoch3.pt` |

**评测集不可切换**：`run_test_eval.sh` 固定用 `datasets/ShopVision` 的 test（934 条）。
不同训练数据来源的模型必须考同一批题，否则数字不可比。

### 例：未清洗数据直训对照组（已跑过，2026-10-20）

```bash
# 1) 用「预处理前」的正式表建数据集（必须显式指定 --output-dir，否则会覆盖清洗数据集）
python scripts/build_retrieval_dataset.py \
  --input-dir data/processed_data \
  --output-dir data/processed_data_retrieval/datasets/ShopVision_uncleaned

# 2) 打包 LMDB
python Chinese-CLIP/cn_clip/preprocess/build_lmdb_dataset.py \
  --data_dir=/workspace/data/processed_data_retrieval/datasets/ShopVision_uncleaned \
  --splits=train,valid,test

# 3) 同一配方训练（只换数据，超参/种子/轮数全同）
RUN_ID=2026-10-20_uncleaned_bs32_lr1e-5 DATASET=ShopVision_uncleaned \
  bash scripts/finetune/run_train_single_gpu.sh

# 4) 评测（评测集仍是清洗数据的 test）
RUN_ID=2026-10-20_uncleaned_bs32_lr1e-5 bash scripts/finetune/run_test_eval.sh
```

结果：test R@1 = 50.96（预训练基线 37.37，清洗数据微调 58.67）。记录见
[`docs/finetune/05-未清洗数据对照组.md`](../../docs/finetune/05-未清洗数据对照组.md)。

目录约定：一次实验 = 一个 `RUN_ID`，`experiments/<RUN_ID>/` 放权重与评测产物，
`docs/finetune/runs/<RUN_ID>/` 放入库凭证，两者同名。

## 新增一次实验

1. 用环境变量指定新的 `RUN_ID`（如 `2026-10-19_bs32_5ep`），不要复制脚本；
2. 训练完用同一个 `RUN_ID` 跑评测；
3. 结果写进新的 `docs/finetune/` 记录文件，不要覆盖已有记录。

## 注意

- **test 划分只能用于最终结论**。选 epoch、调参只能用 valid（939 条），否则 test 会被污染。
- 训练日志里每 150 步打印的 `Image2Text Acc` / `Text2Image Acc` 是 **batch 内 32 候选**口径，
  与最终 `evaluation.py` 的 934 候选 R@K 不可直接比较。
- 8GB 显存下 `bs=32` 必须配 `--grad-checkpointing`；再大就要靠 `--accum-freq` 而不是 `--batch-size`。
