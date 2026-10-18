#!/usr/bin/env bash
# 把「单卡绕开 NCCL」的 3 处补丁打到官方 Chinese-CLIP 代码上。
#
# 用法（在仓库根目录或任意目录执行都可以）：
#   bash scripts/finetune/patches/apply.sh
#
# 幂等：已经打过补丁时会识别出来并跳过，不会重复改。
# 失败时明确报错并给出人工修改指引，不会静默改错。
#
# 补丁内容与原因见 docs/finetune/04-Chinese-CLIP补丁说明.md
set -euo pipefail

PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$PATCH_DIR/../../.." && pwd)"
CLIP="$ROOT/Chinese-CLIP"

if [ ! -d "$CLIP" ]; then
  echo "❌ 找不到 $CLIP" >&2
  echo "   先把官方代码放到仓库根的 Chinese-CLIP/，见 docs/finetune/04-Chinese-CLIP补丁说明.md 第 7 节" >&2
  exit 1
fi

echo "补丁目录: $PATCH_DIR"
echo "目标代码: $CLIP"
echo ""

python - "$CLIP" "$PATCH_DIR" <<'PY'
import ast
import pathlib
import shutil
import sys

clip = pathlib.Path(sys.argv[1])
patch_dir = pathlib.Path(sys.argv[2])

# ---------------------------------------------------------------- 补丁 1
src_no_ddp = patch_dir / "no_ddp.py"
dst_no_ddp = clip / "cn_clip" / "training" / "no_ddp.py"
shutil.copyfile(src_no_ddp, dst_no_ddp)
print(f"[1/3] 写入 {dst_no_ddp.relative_to(clip)}")

# ---------------------------------------------------------------- 补丁 2
main_py = clip / "cn_clip" / "training" / "main.py"
src = main_py.read_text(encoding="utf-8")

if "NoDDP(model)" in src:
    print("[2/3] main.py 已有 NoDDP 分支，跳过")
else:
    old = (
        "    model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[args.local_device_rank], find_unused_parameters=find_unused_parameters)\n"
        "    # Have to set this when activating grad checkpointing in Pytorch >= 2.0.0\n"
        '    if args.grad_checkpointing and not torch_version_str_compare_lessequal(torch.__version__, "1.14.0"):\n'
        "        model._set_static_graph()\n"
    )
    new = (
        "    if args.world_size > 1:\n"
        "        model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[args.local_device_rank], find_unused_parameters=find_unused_parameters)\n"
        "        # Have to set this when activating grad checkpointing in Pytorch >= 2.0.0\n"
        '        if args.grad_checkpointing and not torch_version_str_compare_lessequal(torch.__version__, "1.14.0"):\n'
        "            model._set_static_graph()\n"
        "    else:\n"
        "        # Single-GPU: NCCL collectives hang on this WSL2 setup, so DDP is skipped.\n"
        '        # NoDDP keeps model.module and the "module." state_dict prefix.\n'
        "        from cn_clip.training.no_ddp import NoDDP\n"
        "        model = NoDDP(model)\n"
        '        logging.info("world_size == 1: DDP disabled, using NoDDP wrapper.")\n'
    )
    if src.count(old) != 1:
        sys.exit(
            "❌ main.py 里没找到预期代码块（可能官方版本已变）。\n"
            "   请按 docs/finetune/04-Chinese-CLIP补丁说明.md 第 3 节手工修改。"
        )
    main_py.write_text(src.replace(old, new), encoding="utf-8")
    print("[2/3] main.py 已改为 world_size > 1 才建 DDP")

# ---------------------------------------------------------------- 补丁 3
train_py = clip / "cn_clip" / "training" / "train.py"
src = train_py.read_text(encoding="utf-8")

marker = "if dist.get_world_size() > 1:\n            dist.all_reduce(cumulative_loss"
if marker in src:
    print("[3/3] train.py 已有 world_size > 1 判断，跳过")
else:
    old = (
        "        dist.all_reduce(cumulative_loss, op=dist.ReduceOp.SUM)\n"
        "        dist.all_reduce(cumulative_i2t_acc, op=dist.ReduceOp.SUM)\n"
        "        dist.all_reduce(cumulative_t2i_acc, op=dist.ReduceOp.SUM)\n"
        "        dist.all_reduce(num_elements, op=dist.ReduceOp.SUM)\n"
    )
    new = (
        "        if dist.get_world_size() > 1:\n"
        "            dist.all_reduce(cumulative_loss, op=dist.ReduceOp.SUM)\n"
        "            dist.all_reduce(cumulative_i2t_acc, op=dist.ReduceOp.SUM)\n"
        "            dist.all_reduce(cumulative_t2i_acc, op=dist.ReduceOp.SUM)\n"
        "            dist.all_reduce(num_elements, op=dist.ReduceOp.SUM)\n"
    )
    if src.count(old) != 1:
        sys.exit(
            "❌ train.py 里没找到预期的 4 次 all_reduce（可能官方版本已变）。\n"
            "   请按 docs/finetune/04-Chinese-CLIP补丁说明.md 第 4 节手工修改。"
        )
    train_py.write_text(src.replace(old, new), encoding="utf-8")
    print("[3/3] train.py 的 4 次 all_reduce 已加多卡判断")

# ---------------------------------------------------------------- 语法自检
for p in (main_py, train_py):
    ast.parse(p.read_text(encoding="utf-8"))
print("\n✅ 语法自检通过（ast.parse），补丁完成")
PY

cat <<'EOF'

下一步：
  1) 确认依赖齐全：python -c "import torch, cn_clip, lmdb"
  2) 跑训练：
     tr -d '\r' < scripts/finetune/run_train_single_gpu.sh > /tmp/run.sh && bash /tmp/run.sh
EOF
