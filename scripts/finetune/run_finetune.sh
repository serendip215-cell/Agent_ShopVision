#!/usr/bin/env bash
# ShopVision 中文商品检索 - Chinese-CLIP 微调训练脚本
#
# 基于官方模板 run_scripts/muge_finetune_vit-b-16_rbt-base.sh 修改。
# 单机单卡 GPU 即可运行（数据集仅 7,520 条）。
#
# 用法:
#   bash scripts/finetune/run_finetune.sh
#
# 前置条件:
#   1. 已 clone Chinese-CLIP 官方仓库到仓库根目录(Chinese-CLIP/)
#   2. 预训练权重在 models/chinese_clip/clip_cn_vit-b-16.pt
#   3. LMDB 数据集已生成在 data/processed_data_retrieval/datasets/ShopVision/lmdb/
#      (本地运行 scripts/build_retrieval_dataset.py 后再用官方脚本打包)
#
# 输出:
#   data/processed_data_retrieval/experiments/shopvision_finetune_vit-b-16/
#   ├── checkpoints/epoch_K.pt   <- 微调后的权重,训练完下载这个
#   └── out.log                  <- 训练日志

set -e

# ========== 路径配置(相对仓库根目录,脚本会自动切到根目录) ==========
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${REPO_ROOT}"

DATAPATH=data/processed_data_retrieval
LMDB_DIR=${DATAPATH}/datasets/ShopVision/lmdb
RESUME=models/chinese_clip/clip_cn_vit-b-16.pt

# Chinese-CLIP 官方代码加入 PYTHONPATH
export PYTHONPATH=${PYTHONPATH}:`pwd`/Chinese-CLIP/

# ========== 分布式配置(单机单卡) ==========
GPUS_PER_NODE=1
WORKER_CNT=1
export MASTER_ADDR=localhost
export MASTER_PORT=8514
export RANK=0

# ========== 数据 ==========
train_data=${LMDB_DIR}/train
val_data=${LMDB_DIR}/valid

# ========== 输出 ==========
output_base_dir=${DATAPATH}/experiments
name=shopvision_finetune_vit-b-16_bs32_lr1e-5
save_step_frequency=999999    # 不按 step 保存
save_epoch_frequency=1        # 每个 epoch 保存一次权重
log_interval=10
report_training_batch_acc="--report-training-batch-acc"

# ========== 训练超参数 ==========
# 数据量小(7,520 条),用小 batch + 小学习率微调,避免冲坏预训练权重
context_length=52      # 官方默认;我们的文本中位数 55 字符,token 后约在此范围内
warmup=100
batch_size=32          # 单卡 GPU 显存 16GB+ 够用;OOM 就改成 16 并加 --grad-checkpointing
valid_batch_size=32
accum_freq=1
lr=1e-5                # 比官方 5e-5 小,微调小步慢走
wd=0.001
max_epochs=3           # 先跑 3 轮;不够再改成 5 重跑
valid_step_interval=150
valid_epoch_interval=1
vision_model=ViT-B-16
text_model=RoBERTa-wwm-ext-base-chinese
use_augment="--use-augment"

# ========== 启动训练 ==========
python3 -m torch.distributed.launch --use_env \
          --nproc_per_node=${GPUS_PER_NODE} --nnodes=${WORKER_CNT} --node_rank=${RANK} \
          --master_addr=${MASTER_ADDR} --master_port=${MASTER_PORT} \
          Chinese-CLIP/cn_clip/training/main.py \
          --train-data=${train_data} \
          --val-data=${val_data} \
          --resume=${RESUME} \
          --reset-data-offset \
          --reset-optimizer \
          --logs=${output_base_dir} \
          --name=${name} \
          --save-step-frequency=${save_step_frequency} \
          --save-epoch-frequency=${save_epoch_frequency} \
          --log-interval=${log_interval} \
          ${report_training_batch_acc} \
          --context-length=${context_length} \
          --warmup=${warmup} \
          --batch-size=${batch_size} \
          --valid-batch-size=${valid_batch_size} \
          --valid-step-interval=${valid_step_interval} \
          --valid-epoch-interval=${valid_epoch_interval} \
          --accum-freq=${accum_freq} \
          --lr=${lr} \
          --wd=${wd} \
          --max-epochs=${max_epochs} \
          --vision-model=${vision_model} \
          ${use_augment} \
          --text-model=${text_model}
