#!/usr/bin/env bash
# 生成 SCNet 最小上传包（tgz），只含训练真正需要的文件。
#
# 为什么不做 git clone：本仓库 2.14 GiB（FAISS 索引 + 商品图），
# 训练用不上，从训练机 clone 会卡死。这个包只有 ~85 KB。
#
# 用法（仓库根目录）：bash scripts/agent/finetune/make_upload_package.sh
# 产出：dist/exp5-5.2-upload.tar.gz

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

PKG_NAME="exp5-5.2-upload"
OUT_DIR="dist"
STAGE="$OUT_DIR/$PKG_NAME"

FILES=(
  scripts/agent/finetune/prepare_sft_data.py
  scripts/agent/finetune/train_lora.py
  scripts/agent/finetune/eval_baseline_vs_lora.py
  scripts/agent/finetune/_selfcheck.py
  scripts/agent/finetune/requirements.txt
  scripts/agent/finetune/README.md
  data/agent/agent_finetune_data.json
)

echo "清理旧包…"
rm -rf "$STAGE" "$OUT_DIR/$PKG_NAME.tar.gz"

echo "复制文件…"
for f in "${FILES[@]}"; do
  [ -f "$f" ] || { echo "缺少文件：$f"; exit 1; }
  mkdir -p "$STAGE/$(dirname "$f")"
  cp "$f" "$STAGE/$f"
done

# 启动脚本也带上，方便训练机内直接看注释
mkdir -p "$STAGE/scripts/agent/finetune"
cp scripts/agent/finetune/scnet_start.sh "$STAGE/scripts/agent/finetune/"

# 附一份一页说明：SCNet 怎么用这个包
cat > "$STAGE/README-上传说明.md" <<'MD'
# SCNet 上传说明（实验5 5.2）

## 这个包是什么
只含 5.2 LoRA 微调需要的脚本与数据，约 85 KB。
**不要 clone 整个仓库**（2.14 GiB，含 FAISS 索引和商品图，训练用不上）。

## 怎么用
1. SCNet 控制台 →「文件管理」，把这个 `exp5-5.2-upload` 目录传到任意位置
   （如 `/workspace/exp5-5.2-upload`）。
2. 「模型训练」→「创建训练」，按下面填：

| 表单项 | 填什么 |
|---|---|
| 加速卡 | 异构加速卡AI 64GB（¥2.53/时，标"推荐"）或 A800 80GB |
| 每实例加速卡数量 / 实例数 | 1 / 1 |
| 系统盘 | 50GB 免费额度 |
| 训练镜像 | PyTorch + CUDA 12.x |
| 运行时限 | 1 小时 |
| 任务最大重启次数 | 1 |
| 自定义挂载 | 不需额外挂载，包已在文件管理里 |

**不要选 DTK 列的国产卡**（异构加速卡 BW / AI 的 DTK 版本）：
`bitsandbytes` 只支持 CUDA，国产卡上 QLoRA 跑不了。

3. 「启动脚本」把 `scripts/agent/finetune/scnet_start.sh` 全文贴进去。
   脚本会自动找到这个包，不用改路径。

## 跑完拿什么
`runs/5.2_lora/final_adapter/`（约 30-60 MB）。下载后交给 5.3 补 `_parse_intent`。

## 注意
验证集只 11 条，其中 tool_call 仅 1 条 —— 该单项分数不具统计意义，
不能当「工具调用准确率」汇报。
MD

echo "打包…"
tar -czf "$OUT_DIR/$PKG_NAME.tar.gz" -C "$OUT_DIR" "$PKG_NAME"

echo
echo "完成：$OUT_DIR/$PKG_NAME.tar.gz"
ls -lh "$OUT_DIR/$PKG_NAME.tar.gz"
echo
echo "包内清单："
tar -tzf "$OUT_DIR/$PKG_NAME.tar.gz"