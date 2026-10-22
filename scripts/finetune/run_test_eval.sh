#!/usr/bin/env bash
# test 集最终评测：预训练基线 vs 本次实验的权重
#
# 评测集**固定**为清洗数据的 test 划分（934 条）：
#   不同训练数据来源（原始 / 清洗）的模型必须考同一批题，否则数字不可比。
#   因此这里不提供切换 test 集的开关。
#
# 输入 / 输出：
#   权重     data/processed_data_retrieval/experiments/<RUN_ID>/checkpoints/<CKPT_NAME>
#   大产物   data/processed_data_retrieval/experiments/<RUN_ID>/eval/
#              ├── baseline/                 预训练权重
#              └── finetuned_<CKPT>/         本次实验权重
#   凭证     docs/finetune/runs/<RUN_ID>/   （入 git，KB 级）
#
# 可用环境变量覆盖：
#   RUN_ID     实验名，决定读哪个 experiment 目录、凭证写到哪里
#   CKPT_NAME  用哪个权重，默认 epoch3.pt（5 轮实验则是 epoch5.pt）
#
# 用法（容器内）：bash /tmp/eval.sh
set -euo pipefail

cd /workspace
export PYTHONPATH=/workspace/Chinese-CLIP
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

D=/workspace/data/processed_data_retrieval
RUN_ID=${RUN_ID:-2026-10-18_bs32_lr1e-5}
CKPT_NAME=${CKPT_NAME:-epoch3.pt}
TAG=${CKPT_NAME%.pt}                 # epoch3 / epoch5
SUBDIR=finetuned_$TAG                # eval 子目录名，凭证文件名也用这个前缀

# 评测集固定：清洗数据的 test（934 条）。故意不做成参数，避免两组模型考不同的题。
DS=$D/datasets/ShopVision

EXP=$D/experiments/$RUN_ID
EVAL=$EXP/eval
DOCS=/workspace/docs/finetune/runs/$RUN_ID

PT=/workspace/models/chinese_clip/clip_cn_vit-b-16.pt
FT=$EXP/checkpoints/$CKPT_NAME

if [ ! -f "$FT" ]; then
  echo "找不到权重文件: $FT" >&2
  echo "先跑 run_train_single_gpu.sh，或检查 RUN_ID / CKPT_NAME。" >&2
  exit 1
fi
if [ ! -f "$DS/test_texts.jsonl" ]; then
  echo "找不到评测集: $DS/test_texts.jsonl" >&2
  exit 1
fi

echo "实验：    $RUN_ID"
echo "权重：    $CKPT_NAME"
echo "评测集：  $DS (test，固定)"
echo ""

mkdir -p "$EVAL/baseline" "$EVAL/$SUBDIR" "$DOCS"

run_one () {
  local tag="$1" ckpt="$2" dir="$3"

  echo ""
  echo "===================== $tag ====================="
  echo "checkpoint: $ckpt"

  python -u Chinese-CLIP/cn_clip/eval/extract_features.py \
    --extract-image-feats --extract-text-feats \
    --image-data="$DS/lmdb/test/imgs" \
    --text-data="$DS/test_texts.jsonl" \
    --image-feat-output-path="$dir/test_imgs.img_feat.jsonl" \
    --text-feat-output-path="$dir/test_texts.txt_feat.jsonl" \
    --img-batch-size=32 --text-batch-size=32 \
    --context-length=52 \
    --resume="$ckpt" \
    --vision-model=ViT-B-16 --text-model=RoBERTa-wwm-ext-base-chinese

  python -u Chinese-CLIP/cn_clip/eval/make_topk_predictions.py \
    --image-feats="$dir/test_imgs.img_feat.jsonl" \
    --text-feats="$dir/test_texts.txt_feat.jsonl" \
    --top-k=10 --eval-batch-size=32768 \
    --output="$dir/test_predictions.jsonl"

  python -u Chinese-CLIP/cn_clip/eval/evaluation.py \
    "$DS/test_texts.jsonl" \
    "$dir/test_predictions.jsonl" \
    "$dir/test_score.json"
}

run_one baseline "$PT" "$EVAL/baseline"
run_one "$SUBDIR" "$FT" "$EVAL/$SUBDIR"

# 写评测清单：权重路径+字节数、数据条数、参数、两套分数
python - "$RUN_ID" "$CKPT_NAME" "$SUBDIR" <<'PY'
import json, os, sys, time

RUN_ID, CKPT_NAME, SUBDIR = sys.argv[1], sys.argv[2], sys.argv[3]

D = "/workspace/data/processed_data_retrieval"
DS = os.path.join(D, "datasets/ShopVision")
EXP = os.path.join(D, "experiments", RUN_ID)
EVAL = os.path.join(EXP, "eval")

checkpoints = {
    "baseline_pretrained": "/workspace/models/chinese_clip/clip_cn_vit-b-16.pt",
    "finetuned": os.path.join(EXP, "checkpoints", CKPT_NAME),
}
scores = {}
for tag in ("baseline", SUBDIR):
    with open(os.path.join(EVAL, tag, "test_score.json"), encoding="utf-8") as f:
        scores[tag] = json.load(f)

manifest = {
    "run_id": RUN_ID,
    "checkpoint_name": CKPT_NAME,
    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "test_split": {
        "texts": os.path.join(DS, "test_texts.jsonl"),
        "images_lmdb": os.path.join(DS, "lmdb/test/imgs"),
        "text_count": sum(1 for _ in open(os.path.join(DS, "test_texts.jsonl"), encoding="utf-8")),
        "note": "评测集固定为清洗数据的 test（934 条）；不同训练数据来源的模型都考这一套。",
    },
    "params": {"top_k": 10, "eval_batch_size": 32768,
               "img_batch_size": 32, "text_batch_size": 32, "context_length": 52},
    "checkpoints": {k: {"path": v, "bytes": os.path.getsize(v)} for k, v in checkpoints.items()},
    "scores": scores,
    "notes": [
        "test 划分仅用于最终评测，不参与训练。",
        "候选池为本 test 的 934 条，不可与官方 MUGE 十万级候选池的 R@K 横比。",
        "R@10 已接近饱和，比较模型时优先看 R@1 或 mean_recall。",
    ],
}
out = os.path.join(EVAL, "run_manifest.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print("manifest ->", out)
PY

# 把凭证同步到入库目录（KB 级）：分数、清单、最新一次训练日志与参数快照
LATEST_LOG=$(ls -t "$EXP"/out_*.log 2>/dev/null | head -1 || true)
cp "$EVAL/baseline/test_score.json" "$DOCS/baseline_test_score.json"
cp "$EVAL/$SUBDIR/test_score.json"  "$DOCS/${SUBDIR}_test_score.json"
cp "$EVAL/run_manifest.json"        "$DOCS/run_manifest.json"
[ -n "$LATEST_LOG" ] && cp "$LATEST_LOG" "$DOCS/"
ls -t "$EXP"/params_*.txt 2>/dev/null | head -1 | xargs -r -I{} cp {} "$DOCS/"

echo ""
echo "===================== 结果对比 ====================="
echo "--- baseline（预训练 ViT-B-16）---"
cat "$EVAL/baseline/test_score.json"; echo
echo "--- $SUBDIR（实验 $RUN_ID）---"
cat "$EVAL/$SUBDIR/test_score.json"; echo
echo "==================================================="
echo ""
echo "大产物（不进 git）: $EVAL"
du -sh "$EVAL"/* 2>/dev/null || true
echo "凭证（进 git）: $DOCS"
ls -lh "$DOCS"
