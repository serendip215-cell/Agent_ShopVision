#!/usr/bin/env bash
# SCNet「模型训练」启动脚本（实验5 5.2 LoRA 微调）
#
# 用途：贴进 SCNet 控制台 → 模型训练 → 创建训练 → 启动脚本 输入框。
# 特点：幂等，可重复执行；任何一步失败立刻退出并把原因打到 stdout（网页日志可见）。
#
# ---- 提交前必须核对的三处 ----
#   1. 挂载：把项目仓库和数据集挂到本脚本假设的 /workspace
#      高级配置 → 自定义挂载 → 宿主机 <你的数据目录> 挂到 /workspace
#   2. 镜像：选 PyTorch + CUDA 12.x 的官方镜像（卡是 CUDA 12.4 就别选 13.0）
#   3. 运行时限：留足余量（100 条数据 + 4B QLoRA，实际 10-20 分钟；设 1 小时足够）
#
# ---- 想换基座只改这一行 ----
MODEL="${MODEL:-Qwen/Qwen3-4B-Instruct-2507}"

set -euo pipefail

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "===== 5.2 LoRA 微调开始 ====="
log "基座：$MODEL"
log "工作目录：$(pwd)"

# ---------- 1. 环境自检 ----------
command -v python  || { log "FATAL: 镜像里没有 python"; exit 1; }
python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())" \
  || { log "FATAL: torch 不可用，检查镜像"; exit 1; }

if ! python -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)"; then
  log "FATAL: CUDA 不可用。要么卡没分配上，要么镜像版本与卡不匹配。"
  log "       国产 DTK 卡不支持 --no-4bit 之外的 CUDA 路径，请改选 NVIDIA A800/L20/4090"
  exit 1
fi

nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

# ---------- 2. 定位仓库 ----------
# SCNet 挂载点不固定，逐个探测，避免硬编码错路径
REPO=""
for cand in /workspace /workspace/Agent_ShopVision /data /root/Agent_ShopVision "$(pwd)"; do
  if [ -f "$cand/scripts/agent/finetune/train_lora.py" ]; then REPO="$cand"; break; fi
done
if [ -z "$REPO" ]; then
  log "FATAL: 找不到仓库根目录（需要 scripts/agent/finetune/train_lora.py）"
  log "       当前目录树："
  ls -la
  log "       请确认自定义挂载把项目挂到了 /workspace"
  exit 1
fi
log "仓库根：$REPO"
cd "$REPO"

# ---------- 3. 装依赖（每次装，保证干净；已有则秒过）----------
log "安装微调依赖…"
pip install -q --upgrade pip
pip install -q -r scripts/agent/finetune/requirements.txt \
  || { log "FATAL: 依赖安装失败（常见原因：网络访问 HF 超时）"; exit 1; }

python - <<'PY' || { echo "FATAL: 依赖导入失败"; exit 1; }
import torch, transformers, peft, datasets, trl
print("transformers", transformers.__version__)
print("peft", peft.__version__)
print("trl", trl.__version__)
PY

# ---------- 4. 数据准备（幂等）----------
if [ ! -f data/agent/sft/train.jsonl ]; then
  log "生成 SFT 数据集…"
  python scripts/agent/finetune/prepare_sft_data.py
else
  log "SFT 数据集已存在，跳过生成"
fi

# ---------- 5. 加速下载（可选，HF 被墙时很关键）----------
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
log "HF_ENDPOINT=$HF_ENDPOINT"

# ---------- 6. 训练 ----------
OUT_DIR="${OUT_DIR:-data/agent/finetune/scnet_run1}"
log "开始训练，输出到 $OUT_DIR"
log "显存不足时：调小 --batch-size，调大 --grad-accum"

python -u scripts/agent/finetune/train_lora.py \
  --model "$MODEL" \
  --output "$OUT_DIR" \
  --epochs 3 \
  --batch-size 2 \
  --grad-accum 8 \
  --lr 1e-4 \
  --lora-r 16 \
  --lora-alpha 32 \
  2>&1 | tee "$OUT_DIR.train.log"

# 若因 bitsandbytes 装不上而失败，自动退回纯 LoRA 重试一次
if [ ! -f "$OUT_DIR/final_adapter/adapter_config.json" ]; then
  log "WARN: 首次训练未产出 adapter，尝试关闭 4-bit 重跑"
  pip install -q bitsandbytes || log "WARN: bitsandbytes 仍不可用"
  python -u scripts/agent/finetune/train_lora.py \
    --model "$MODEL" --output "$OUT_DIR" --no-4bit \
    --epochs 3 --batch-size 2 --grad-accum 8 --lr 1e-4 \
    2>&1 | tee -a "$OUT_DIR.train.log"
fi

# ---------- 7. 交付物清点 ----------
log "===== 训练结束，产物清单 ====="
if [ -d "$OUT_DIR/final_adapter" ]; then
  ls -lh "$OUT_DIR/final_adapter"
  du -sh "$OUT_DIR/final_adapter"
  log "OK: LoRA 权重就绪。下载 final_adapter 整个目录，传 GitHub Release 或直接交给 5.3"
else
  log "FAIL: 没有 final_adapter。往上看 $OUT_DIR.train.log 的最后 50 行。"
  tail -50 "$OUT_DIR.train.log" || true
  exit 1
fi