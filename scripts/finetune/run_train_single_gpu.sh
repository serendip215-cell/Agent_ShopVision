#!/usr/bin/env bash
# 单卡微调训练入口（WSL2 + RTX 5060 Ti / 8GB）
#
# 与官方 run_scripts/muge_finetune_vit-b-16_rbt-base.sh 逐参数对齐，差异只有三处：
#   1) 不用 torchrun / torch.distributed.launch —— 本机 NCCL 集合通信会永久挂死；
#   2) 加 --skip-aggregate + NoDDP 包装 —— world_size == 1 时不需要任何集合通信；
#   3) 加 --grad-checkpointing —— 8GB 显存必需。
#
# 用法（WSL 宿主机）：
#   docker exec -it shopvision bash -c "tr -d '\r' < /workspace/scripts/finetune/run_train_single_gpu.sh > /tmp/run.sh && bash /tmp/run.sh"
#
# 产物（一个实验一个目录，全部内聚）：
#   data/processed_data_retrieval/experiments/<RUN_ID>/
#   ├── checkpoints/epoch1.pt epoch2.pt epoch3.pt epoch_latest.pt
#   ├── out_<UTC时间戳>.log
#   └── params_<UTC时间戳>.txt
set -euo pipefail

cd /workspace

export PYTHONPATH=/workspace/Chinese-CLIP
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
# main.py 只读这五个变量（见 cn_clip/training/main.py 第 51/55 行）：
export MASTER_ADDR=127.0.0.1
export MASTER_PORT=8514
export RANK=0
export WORLD_SIZE=1
export LOCAL_RANK=0

D=/workspace/data/processed_data_retrieval
RUN_ID=2026-10-18_bs32_lr1e-5          # 一次实验一个 ID，experiments/ 与 docs/finetune/runs/ 同名

python -u Chinese-CLIP/cn_clip/training/main.py \
  --train-data=$D/datasets/ShopVision/lmdb/train \
  --val-data=$D/datasets/ShopVision/lmdb/valid \
  --resume=/workspace/models/chinese_clip/clip_cn_vit-b-16.pt \
  --reset-data-offset \
  --reset-optimizer \
  --logs=$D/experiments \
  --name=$RUN_ID \
  --save-step-frequency=999999 \
  --save-epoch-frequency=1 \
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
  --max-epochs=3 \
  --vision-model=ViT-B-16 \
  --text-model=RoBERTa-wwm-ext-base-chinese \
  --grad-checkpointing \
  --num-workers=2 \
  --skip-aggregate \
  2>&1 | tee /tmp/train_stdout.log
