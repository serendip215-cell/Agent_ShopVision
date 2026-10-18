#!/usr/bin/env bash
# 消融实验：3 轮 vs 5 轮（其余超参完全一致，只改 max_epochs）
#
# 目的：valid 在 705 步时 loss 仍在下降、准确率仍在上升，判断 3 轮欠训练。
# 做法：从同一份预训练权重重新训 5 轮（单条 cosine 调度，与 3 轮那次严格可比），
#       不续训——续训会继承 705 步的调度位置，LR 只能从 4e-6 起步，学不动。
#
# 存储：--save-epoch-frequency=0，只保留最后一个 epoch 的权重 + 每轮覆盖的 latest，
#       共 2 个文件约 4.1GB（否则 5 轮会有 6 个文件约 13GB）。
#
# 用法（容器内）：
#   tr -d '\r' < /workspace/scripts/finetune/run_train_5epoch.sh > /tmp/run5.sh && bash /tmp/run5.sh
set -euo pipefail

cd /workspace

export PYTHONPATH=/workspace/Chinese-CLIP
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export MASTER_ADDR=127.0.0.1
export MASTER_PORT=8514
export RANK=0
export WORLD_SIZE=1
export LOCAL_RANK=0

D=/workspace/data/processed_data_retrieval
RUN_ID=2026-10-18_bs32_lr1e-5_5ep     # 新 ID，绝不覆盖 3 轮那次的结果

python -u Chinese-CLIP/cn_clip/training/main.py \
  --train-data=$D/datasets/ShopVision/lmdb/train \
  --val-data=$D/datasets/ShopVision/lmdb/valid \
  --resume=/workspace/models/chinese_clip/clip_cn_vit-b-16.pt \
  --reset-data-offset \
  --reset-optimizer \
  --logs=$D/experiments \
  --name=$RUN_ID \
  --save-step-frequency=999999 \
  --save-epoch-frequency=0 \
  --log-interval=10 \
  --report-training-batch-acc \
  --context-length=52 \
  --warmup=100 \
  --batch-size=32 \
  --valid-batch-size=32 \
  --valid-step-interval=150 \
  --valid-epoch-interval=1 \
  --accum-freq=1 \
  --lr=1e-5 \
  --wd=0.001 \
  --max-epochs=5 \
  --vision-model=ViT-B-16 \
  --text-model=RoBERTa-wwm-ext-base-chinese \
  --grad-checkpointing \
  --num-workers=2 \
  --skip-aggregate \
  2>&1 | tee /tmp/train_5epoch.log
