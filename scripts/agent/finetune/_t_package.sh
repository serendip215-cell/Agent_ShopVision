#!/usr/bin/env bash
# 端到端验证上传包：模拟 SCNet 上「只有这个包、没有整个仓库」的情形，
# 实际跑通 定位 -> 数据转换 -> 评分自检 这一段（跳过装依赖和训练，那需要 GPU）。

set -uo pipefail
PKG="$1"
T=$(mktemp -d)
echo "=== 模拟环境：$T（干净的临时目录）==="
cp -r "$PKG" "$T/exp5-5.2-upload"
cd "$T/exp5-5.2-upload"

echo
echo "=== 1. 定位逻辑 ==="
REPO=""
for cand in \
    "$(pwd)" \
    "$(pwd)/exp5-5.2-upload" \
    /workspace /workspace/exp5-5.2-upload ; do
  [ -f "$cand/scripts/agent/finetune/train_lora.py" ] && { REPO="$cand"; break; }
done
if [ -z "$REPO" ]; then
  found=$(find "$T" -maxdepth 8 -name train_lora.py 2>/dev/null | head -n 1)
  [ -n "$found" ] && REPO=$(cd "$(dirname "$found")/../../.." && pwd)
fi
[ -n "$REPO" ] || { echo "FAIL: 定位失败"; rm -rf "$T"; exit 1; }
echo "✅ 定位到：$REPO"
cd "$REPO"

echo
echo "=== 2. 数据转换（真实运行）==="
python scripts/agent/finetune/prepare_sft_data.py > /tmp/pkg_prep.log 2>&1
if [ $? -ne 0 ]; then
  echo "FAIL: 数据转换失败"; tail -10 /tmp/pkg_prep.log; rm -rf "$T"; exit 1
fi
train_n=$(wc -l < data/agent/sft/train.jsonl)
valid_n=$(wc -l < data/agent/sft/valid.jsonl)
echo "✅ train=$train_n valid=$valid_n"

echo
echo "=== 3. 评分自检（真实运行）==="
if python scripts/agent/finetune/_selfcheck.py > /tmp/pkg_sc.log 2>&1; then
  echo "✅ 自检通过 $(grep -c PASS /tmp/pkg_sc.log) 项"
else
  echo "FAIL: 自检未过"; tail -10 /tmp/pkg_sc.log; rm -rf "$T"; exit 1
fi

echo
echo "=== 4. 训练脚本 CLI 可用性 ==="
python scripts/agent/finetune/train_lora.py --help > /dev/null 2>&1 \
  && echo "✅ train_lora.py --help OK" || { echo "FAIL: CLI 挂了"; rm -rf "$T"; exit 1; }
python scripts/agent/finetune/eval_baseline_vs_lora.py --help > /dev/null 2>&1 \
  && echo "✅ eval --help OK" || { echo "FAIL: eval CLI 挂了"; rm -rf "$T"; exit 1; }

echo
echo "=== 5. 上传包不依赖仓库其他部分 ==="
miss=""
for need in data/agent/sft/train.jsonl data/agent/sft/valid.jsonl; do
  [ -f "$need" ] || miss="$miss $need"
done
[ -z "$miss" ] && echo "✅ 训练所需数据齐备" || echo "FAIL: 缺少$miss"

rm -rf "$T"
echo
echo "=== 全部通过：这个包单独上传到 SCNet 就能跑 ==="