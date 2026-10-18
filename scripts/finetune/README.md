# 微调脚本

本目录是 Chinese-CLIP 微调在本仓库的入口。**日常只用前两个脚本**，第三个是历史留存。

| 脚本 | 用途 | 什么时候用 |
|---|---|---|
| `run_train_single_gpu.sh` | 单卡训练 3 轮，产出 `epoch*.pt` | 需要训练/重训时（当前定稿版本） |
| `run_test_eval.sh` | test 集最终评测（基线 vs 微调） | 训练完成、权重定稿后，**只用一次** |
| `run_train_5epoch.sh` | 5 轮消融实验（**未执行，备用**） | 想验证"3 轮是否欠训练"时才跑 |
| `run_finetune.sh` | 官方 MUGE 模板的移植版（`torch.distributed.launch` + DDP） | **本机跑不通**，仅作参数对照参考 |

## 为什么不用官方模板

官方 `Chinese-CLIP/run_scripts/muge_finetune_vit-b-16_rbt-base.sh` 走 `torch.distributed.launch` + DDP。
在 WSL2 + RTX 5060 Ti 环境下，NCCL 的 `all_reduce` 会**永久挂死**：`init_process_group` 正常返回，
第一次集合通信就卡住，GPU 利用率 0%，显存却已加载。已尝试且**无效**的开关：

```
NCCL_P2P_DISABLE=1
NCCL_SHM_DISABLE=1
NCCL_CUMEM_ENABLE=0
```

因此单卡训练改用 `NoDDP` 包装 + `--skip-aggregate`，完全不产生集合通信。相关改动位于
`Chinese-CLIP/cn_clip/training/`（该目录不入库，换机器需重新打补丁）：新增 `no_ddp.py`，
并在 `main.py` 只在 `world_size > 1` 时构造 DDP、在 `train.py` 给验证阶段的 `all_reduce` 加多卡判断。

`NoDDP` 保存的 ckpt 仍带 `module.` 前缀，官方 `extract_features.py`（第 157 行自动剥离）可直接加载，已实测。

**3 处改动的完整说明**（含改前/改后代码、为什么保留 `module.` 前缀、换机器如何重新施加）见
[`docs/finetune/04-Chinese-CLIP补丁说明.md`](../../docs/finetune/04-Chinese-CLIP补丁说明.md)。

补丁本体已入库在 [`patches/`](patches/)，重新 clone 官方代码后一条命令即可施加：

```bash
bash scripts/finetune/patches/apply.sh
```

## 目录约定

**一次实验一个 `RUN_ID`，`experiments/` 与 `docs/finetune/runs/` 同名。**

```
data/processed_data_retrieval/            ← 全部 gitignore，可重建
├── datasets/ShopVision/                  数据：tsv / jsonl / id_mapping / lmdb
└── experiments/<RUN_ID>/
    ├── checkpoints/epoch{1,2,3}.pt, epoch_latest.pt
    ├── out_<UTC时间戳>.log               训练日志（注意不是 out.log）
    ├── params_<UTC时间戳>.txt            超参快照
    └── eval/                             评测产物（约 40MB，可重算）
        ├── baseline/{test_score.json, test_*.jsonl}
        ├── finetuned_epoch3/{test_score.json, test_*.jsonl}
        └── run_manifest.json

docs/finetune/runs/<RUN_ID>/               ← 入库的凭证（KB 级）
├── baseline_test_score.json
├── finetuned_epoch3_test_score.json
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

## 新增一次实验

1. 复制 `run_train_single_gpu.sh`，改 `RUN_ID`（例如 `2026-10-19_bs32_5ep`）和要变的超参；
2. 训练完，把 `run_test_eval.sh` 里的 `RUN_ID` 改成同一个值再跑评测；
3. 结果写进新的 `docs/finetune/` 记录文件，不要覆盖已有记录。

## 注意

- **test 划分只能用于最终结论**。选 epoch、调参只能用 valid（939 条），否则 test 会被污染。
- 训练日志里每 150 步打印的 `Image2Text Acc` / `Text2Image Acc` 是 **batch 内 32 候选**口径，
  与最终 `evaluation.py` 的 934 候选 R@K 不可直接比较。
- 8GB 显存下 `bs=32` 必须配 `--grad-checkpointing`；再大就要靠 `--accum-freq` 而不是 `--batch-size`。
