#!/usr/bin/env bash
# ============================================================
# SCNet「模型训练」启动脚本 —— 实验5 5.2 LoRA 微调
#
# 平台特征（实测 2026-11-08）：
#   - 网页「模型训练」提交后由 Slurm 调度，脚本在计算节点上执行
#   - 主目录 /public/home/keiraee，登录节点 zz-login01
#   - 计算节点自带 CUDA 镜像环境，但 PyTorch/transformers 需自装
#
# 本脚本假设训练包已上传到 ~/exp5-5.2-upload
# （实测已在服务器上，数据转换与自检均已跑通）
# ============================================================

set -uo pipefail

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { log "❌ FATAL: $*"; exit 1; }

log "===== 5.2 LoRA 微调 ====="
log "节点: $(hostname)  作业: ${SLURM_JOB_ID:-N/A}"

# ---------- 1. 定位训练包 ----------
REPO=""
for cand in \
    "$HOME/exp5-5.2-upload" \
    "$HOME" \
    "$(pwd)" \
    "$(pwd)/exp5-5.2-upload" \
    /public/home/keiraee/exp5-5.2-upload ; do
  if [ -f "$cand/scripts/agent/finetune/train_lora.py" ]; then REPO="$cand"; break; fi
done

if [ -z "$REPO" ]; then
  log "常规路径未找到，搜索 train_lora.py …"
  found=$(find "$HOME" -maxdepth 6 -name train_lora.py 2>/dev/null | head -n 1)
  [ -n "$found" ] && REPO=$(cd "$(dirname "$found")/../../.." && pwd)
fi

if [ -z "$REPO" ]; then
  log "------ 诊断 ------"
  log "HOME=$HOME"
  ls -la "$HOME" 2>/dev/null | head -25
  die "找不到训练包，请确认 ~/exp5-5.2-upload 存在"
fi
log "✅ 训练包: $REPO"
cd "$REPO" || die "cd 失败"

# ---------- 2. Python 环境 ----------
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
log "Python: $($PY -V 2>&1)"

# 平台若提供 module，优先加载带 CUDA 的 Python
if command -v module >/dev/null 2>&1; then
  module load anaconda3/2023.09 2>/dev/null || true
  command -v conda >/dev/null 2>&1 && log "conda: $(conda --version 2>&1)"
fi

# ---------- 3. GPU 检查 ----------
if command -v nvidia-smi >/dev/null 2>&1; then
  log "--- nvidia-smi ---"
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>&1 | head -5
else
  log "⚠️  没有 nvidia-smi，可能是国产卡或纯 CPU 节点"
fi

# ---------- 4. 装依赖 ----------
log "安装依赖…"
$PY -m pip install -q --upgrade pip 2>/dev/null || true

# 平台镜像通常已带 torch，先检测，避免重复下载 2GB
if $PY -c "import torch" 2>/dev/null; then
  log "✅ 镜像已带 torch: $($PY -c 'import torch;print(torch.__version__)')"
else
  log "镜像无 torch，安装中（这一步最慢）…"
  $PY -m pip install -q torch --index-url https://download.pytorch.org/whl/cu121 \
    || $PY -m pip install -q torch || die "torch 安装失败"
fi

$PY -m pip install -q transformers peft datasets accelerate sentencepiece safetensors 2>&1 | tail -3
$PY -m pip install -q trl 2>&1 | tail -2
$PY -m pip install -q bitsandbytes 2>&1 | tail -2 || log "⚠️  bitsandbytes 不可用，将退回纯 LoRA"

$PY -c "
import torch, transformers, peft, datasets
print('torch', torch.__version__, 'cuda', torch.cuda.is_available())
print('transformers', transformers.__version__)
print('peft', peft.__version__)
" || die "依赖导入失败"

# ---------- 5. 数据（幂等）----------
if [ ! -f data/agent/sft/train.jsonl ]; then
  log "生成 SFT 数据…"
  $PY scripts/agent/finetune/prepare_sft_data.py || die "数据转换失败"
else
  log "SFT 数据已存在：$(wc -l < data/agent/sft/train.jsonl) train / $(wc -l < data/agent/sft/valid.jsonl) valid"
fi

# ---------- 6. 下载加速 ----------
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export TOKENIZERS_PARALLELISM=false
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
log "HF_ENDPOINT=$HF_ENDPOINT"

# ---------- 7. 训练 ----------
OUT_DIR="${OUT_DIR:-$HOME/runs/5.2_lora}"
mkdir -p "$OUT_DIR"

log "开始训练 → $OUT_DIR"
log "基座 Qwen/Qwen3-4B-Instruct-2507（4.02B），QLoRA 4-bit"
log "预计 10-20 分钟"

$PY -u scripts/agent/finetune/train_lora.py \
  --model Qwen/Qwen3-4B-Instruct-2507 \
  --output "$OUT_DIR" \
  --train-file data/agent/sft/train.jsonl \
  --valid-file data/agent/sft/valid.jsonl \
  --epochs 3 \
  --batch-size 2 \
  --grad-accum 8 \
  --lr 1e-4 \
  --lora-r 16 \
  --lora-alpha 32 \
  2>&1 | tee "$OUT_DIR/train.log"

# 失败降级重试
if [ ! -f "$OUT_DIR/final_adapter/adapter_config.json" ]; then
  log "⚠️  首轮未产出 adapter，尝试关闭 4-bit 重跑"
  $PY -u scripts/agent/finetune/train_lora.py \
    --model Qwen/Qwen3-4B-Instruct-2507 \
    --output "$OUT_DIR" --no-4bit \
    --train-file data/agent/sft/train.jsonl \
    --valid-file data/agent/sft/valid.jsonl \
    --epochs 3 --batch-size 1 --grad-accum 16 --lr 1e-4 \
    2>&1 | tee -a "$OUT_DIR/train.log"
fi

# ---------- 8. 结果 ----------
log ""
if [ -f "$OUT_DIR/final_adapter/adapter_config.json" ]; then
  log "✅ 训练成功"
  ls -lh "$OUT_DIR/final_adapter"
  du -sh "$OUT_DIR/final_adapter"
  log ""
  log "产物路径（SSH 可直接下载）："
  log "  $OUT_DIR/final_adapter"
else
  log "❌ 未产出 adapter，日志最后 40 行："
  tail -40 "$OUT_DIR/train.log" 2>/dev/null
  exit 1
fi
