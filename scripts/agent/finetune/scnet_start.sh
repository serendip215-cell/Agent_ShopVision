#!/usr/bin/env bash
# ============================================================
# SCNet「模型训练」启动脚本 —— 实验5 5.2 LoRA 微调
#
# 用法：整段复制，粘贴到 SCNet 控制台
#       模型训练 → 创建训练 → 启动脚本（必填）
#
# 前提：把「最小上传包」传到 SCNet 文件管理的任意目录，
#       本脚本会自动在常见位置找到它，不需要改路径。
#
# ---- 提交前只需要核对三处 ----
#   1. 加速卡：异构加速卡AI 64GB（¥2.53/时，标"推荐"）或 A800 80GB
#      不要选 DTK 列的国产卡（bitsandbytes 只支持 CUDA）
#   2. 训练镜像：PyTorch + CUDA 12.x（卡是 12.4 就别选 13.0）
#   3. 运行时限：1 小时（实际 10-20 分钟）
#
# ---- 想换基座，只改下面这一行 ----
MODEL="${MODEL:-Qwen/Qwen3-4B-Instruct-2507}"
# ============================================================

set -uo pipefail

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { log "❌ FATAL: $*"; exit 1; }

log "===== 实验5 5.2 LoRA 微调 ====="
log "基座模型：$MODEL"

# ---------- 1. Python / CUDA 自检 ----------
command -v python >/dev/null 2>&1 || die "镜像里没有 python，检查镜像选择"
python - <<'PY' || die "torch 或 CUDA 不可用。若卡是国产 DTK，QLoRA 无法运行，请换 NVIDIA 卡"
import sys
try:
    import torch
except ImportError:
    print("torch 未安装 —— 镜像不对，请选 PyTorch 镜像")
    sys.exit(1)
print(f"torch {torch.__version__}  cuda_available={torch.cuda.is_available()}")
if not torch.cuda.is_available():
    sys.exit(1)
print(f"GPU: {torch.cuda.get_device_name(0)} "
      f"{torch.cuda.get_device_properties(0).total_memory / 2**30:.1f} GiB")
PY

# ---------- 2. 自动定位上传包（不假设固定路径）----------
REPO=""
for cand in \
    "$(pwd)" \
    "$(pwd)/exp5-5.2-upload" \
    /workspace /workspace/exp5-5.2-upload \
    /data /data/exp5-5.2-upload \
    /root /root/exp5-5.2-upload \
    "$HOME" "$HOME/exp5-5.2-upload" \
    /mnt /mnt/exp5-5.2-upload ; do
  if [ -f "$cand/scripts/agent/finetune/train_lora.py" ]; then
    REPO="$cand"; break
  fi
done

# 兜底：在常见根目录下浅层搜索（防止上传到了别的子目录）
if [ -z "$REPO" ]; then
  log "常规路径没找到，开始浅层搜索 train_lora.py …"
  found=$(find /workspace /data /root /home /mnt -maxdepth 8 \
            -name train_lora.py 2>/dev/null | head -n 1)
  # train_lora.py -> finetune -> agent -> scripts -> 仓库根，要向上 4 层
  [ -n "$found" ] && REPO=$(cd "$(dirname "$found")/../../.." && pwd)
fi

if [ -z "$REPO" ]; then
  log "------ 诊断信息 ------"
  log "当前目录：$(pwd)"
  ls -la
  for d in /workspace /data /root /home; do
    [ -d "$d" ] && { log "--- $d ---"; ls -la "$d" 2>/dev/null | head -20; }
  done
  die "找不到上传包。请确认「自定义挂载」或「文件管理」里有 exp5-5.2-upload 目录"
fi
log "✅ 找到上传包：$REPO"
cd "$REPO"

# ---------- 3. 装依赖 ----------
log "安装依赖（首次约 2-4 分钟）…"
python -m pip install -q --upgrade pip 2>/dev/null || true
if ! python -m pip install -q -r scripts/agent/finetune/requirements.txt; then
  log "⚠️  完整依赖安装失败，尝试最小依赖集（不含 trl/bitsandbytes）"
  python -m pip install -q torch transformers peft datasets accelerate sentencepiece safetensors \
    || die "最小依赖也装不上，检查镜像源或网络"
  python -m pip install -q trl bitsandbytes 2>/dev/null || log "⚠️  trl/bitsandbytes 缺失，将走降级路径"
fi

python - <<'PY' || die "依赖导入失败"
import transformers, peft, datasets
print("transformers", transformers.__version__)
print("peft", peft.__version__)
try:
    import trl; print("trl", trl.__version__)
except ImportError:
    print("trl 未安装 —— 训练会失败，请检查上一步日志")
PY

# ---------- 4. 生成 SFT 数据（幂等）----------
if [ ! -f data/agent/sft/train.jsonl ]; then
  log "生成 SFT 数据集…"
  python scripts/agent/finetune/prepare_sft_data.py || die "数据转换失败"
else
  log "SFT 数据已存在，跳过"
fi

# ---------- 5. 评分逻辑自检（快速，防止白跑训练）----------
log "评分逻辑自检…"
python scripts/agent/finetune/_selfcheck.py >/tmp/selfcheck.log 2>&1 \
  && log "✅ 自检通过" \
  || { log "⚠️  自检未全过，详情："; tail -5 /tmp/selfcheck.log; }

# ---------- 6. 训练 ----------
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
log "HF_ENDPOINT=$HF_ENDPOINT（国内下载加速）"
export TOKENIZERS_PARALLELISM=false

OUT_DIR="${OUT_DIR:-runs/5.2_lora}"
mkdir -p "$(dirname "$OUT_DIR")"

log "开始训练 → $OUT_DIR"
log "预计 10-20 分钟。显存不足时把 --batch-size 降到 1、--grad-accum 升到 16"

python -u scripts/agent/finetune/train_lora.py \
  --model "$MODEL" \
  --output "$OUT_DIR" \
  --train-file data/agent/sft/train.jsonl \
  --valid-file data/agent/sft/valid.jsonl \
  --epochs 3 \
  --batch-size 2 \
  --grad-accum 8 \
  --lr 1e-4 \
  --lora-r 16 \
  --lora-alpha 32 \
  2>&1 | tee "${OUT_DIR}.train.log"

TRAIN_RC=${PIPESTATUS[0]}

# ---------- 7. 失败自动降级重试 ----------
if [ ! -f "$OUT_DIR/final_adapter/adapter_config.json" ]; then
  log "⚠️  首次训练未产出 adapter（退出码 $TRAIN_RC），判断原因…"

  if grep -qi "bitsandbytes\|4bit\|quantiz" "${OUT_DIR}.train.log" 2>/dev/null; then
    log "→ 检测到 4-bit 相关错误，关闭 QLoRA 用纯 LoRA 重试"
    python -u scripts/agent/finetune/train_lora.py \
      --model "$MODEL" --output "$OUT_DIR" --no-4bit \
      --train-file data/agent/sft/train.jsonl \
      --valid-file data/agent/sft/valid.jsonl \
      --epochs 3 --batch-size 1 --grad-accum 16 --lr 1e-4 \
      2>&1 | tee -a "${OUT_DIR}.train.log"
  fi

  if grep -qi "out of memory\|OOM\|CUDA out" "${OUT_DIR}.train.log" 2>/dev/null; then
    log "→ 检测到显存不足，最小 batch 重试"
    python -u scripts/agent/finetune/train_lora.py \
      --model "$MODEL" --output "$OUT_DIR" --no-4bit \
      --train-file data/agent/sft/train.jsonl \
      --valid-file data/agent/sft/valid.jsonl \
      --epochs 3 --batch-size 1 --grad-accum 16 --lr 1e-4 --max-seq-len 512 \
      2>&1 | tee -a "${OUT_DIR}.train.log"
  fi
fi

# ---------- 8. 交付物清点 ----------
log ""
log "===== 结果 ====="
if [ -f "$OUT_DIR/final_adapter/adapter_config.json" ]; then
  log "✅ 训练成功"
  ls -lh "$OUT_DIR/final_adapter"
  du -sh "$OUT_DIR/final_adapter"
  log ""
  log "下一步："
  log "  1. 从文件管理下载整个 $OUT_DIR/final_adapter 目录"
  log "  2. 交给 5.3 补 _parse_intent"
  log ""
  log "（可选）在同一个任务里接着跑评测："
  log "  python scripts/agent/finetune/eval_baseline_vs_lora.py --tag baseline"
  log "  python scripts/agent/finetune/eval_baseline_vs_lora.py --adapter $OUT_DIR/final_adapter --tag lora"
  log "  python scripts/agent/finetune/eval_baseline_vs_lora.py --compare data/agent/finetune/eval_baseline.json data/agent/finetune/eval_lora.json"
else
  log "❌ 训练未产出 adapter"
  log "------ 日志最后 40 行 ------"
  tail -40 "${OUT_DIR}.train.log" 2>/dev/null || log "找不到训练日志 ${OUT_DIR}.train.log"
  exit 1
fi