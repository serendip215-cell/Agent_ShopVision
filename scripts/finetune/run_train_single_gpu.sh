#!/usr/bin/env bash
# 单卡微调训练入口（WSL2 + RTX 5060 Ti / 8GB）
#
# 与官方 run_scripts/muge_finetune_vit-b-16_rbt-base.sh 逐参数对齐，差异只有三处：
#   1) 不用 torchrun / torch.distributed.launch —— 本机 NCCL 集合通信会永久挂死；
#   2) 加 --skip-aggregate + NoDDP 包装 —— world_size == 1 时不需要任何集合通信；
#   3) 加 --grad-checkpointing —— 8GB 显存必需。
#
# 输入 / 输出：
#   输入数据  data/processed_data_retrieval/datasets/<DATASET>/lmdb/{train,valid}
#   输出目录  data/processed_data_retrieval/experiments/<RUN_ID>/
#             ├── checkpoints/epoch1.pt epoch2.pt epoch3.pt epoch_latest.pt
#             ├── out_<UTC时间戳>.log
#             └── params_<UTC时间戳>.txt
#
# 可用环境变量覆盖（默认值 = 清洗数据那次实验，行为与之前完全一致）：
#   RUN_ID    实验名，同时决定输出目录；experiments/ 与 docs/finetune/runs/ 同名
#   DATASET   数据集目录名，决定读哪份 lmdb
#
# 例：用未清洗数据（data/processed_data 转换而来）跑对照组，其余超参不动
#   RUN_ID=2026-10-20_uncleaned_bs32_lr1e-5 DATASET=ShopVision_uncleaned bash run_train_single_gpu.sh
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
RUN_ID=${RUN_ID:-2026-10-18_bs32_lr1e-5}
DATASET=${DATASET:-ShopVision}
LMDB=$D/datasets/$DATASET/lmdb
OUT=$D/experiments/$RUN_ID

# 先确认输入齐全，别训练跑到一半才发现路径错
for split in train valid; do
  if [ ! -d "$LMDB/$split" ]; then
    echo "找不到训练数据：$LMDB/$split" >&2
    echo "先跑 build_retrieval_dataset.py 和 build_lmdb_dataset.py 生成 $DATASET" >&2
    exit 1
  fi
done

if [ -e "$OUT/checkpoints/epoch_latest.pt" ]; then
  echo "警告：$OUT 里已有 checkpoint，本次训练会覆盖它。" >&2
  echo "      如需保留旧结果，请换一个 RUN_ID。" >&2
fi

echo "数据集：$DATASET  ($LMDB)"
echo "输出：  $OUT"
echo ""

python -u Chinese-CLIP/cn_clip/training/main.py \
  --train-data=$LMDB/train \
  --val-data=$LMDB/valid \
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
