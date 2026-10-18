# Chinese-CLIP 本地补丁说明（单卡绕开 NCCL）

> 本文记录我们对官方 `Chinese-CLIP/` 的**全部**改动。官方目录被 `.gitignore` 排除，
> 所以这些改动不会随仓库分发，换机器重新 clone 官方代码后必须按本文重新施加。
>
> 涉及 3 个文件：**新增 1 个，修改 2 个**。评测代码 `cn_clip/eval/` **完全未改**。

## 1. 为什么需要改

官方训练入口 `cn_clip/training/main.py` 固定走 `torch.distributed` + DDP：

```python
dist.init_process_group(backend="nccl")                      # 第 55 行
model = torch.nn.parallel.DistributedDataParallel(model, ...) # 第 135 行
```

在本机环境（Windows + WSL2 + Docker，RTX 5060 Ti 单卡）下，**NCCL 集合通信会永久挂死**：

| 现象 | 观察 |
|---|---|
| `dist.init_process_group(backend="nccl")` | **正常返回**，`INIT OK` |
| 第一次 `dist.all_reduce(tensor)` | **永久卡住**，进程 `State: S`，GPU 利用率 0%，显存 1.7GB |
| 训练进程表现 | 日志停在 `Grad-checkpointing activated.` 之后，不再输出；`Params:` 那行都打不出来 |

已尝试且**均无效**的环境变量：

```
NCCL_P2P_DISABLE=1
NCCL_SHM_DISABLE=1
NCCL_CUMEM_ENABLE=0        # 这一项甚至导致进程被 SIGKILL（exit 137）
```

单卡训练本质上不需要任何集合通信，因此选择**完全绕开 DDP**，而不是继续调 NCCL。

## 2. 改动一：新增 `cn_clip/training/no_ddp.py`

文件：`Chinese-CLIP/cn_clip/training/no_ddp.py`（新建）

```python
# -*- coding: utf-8 -*-
"""Single-GPU stand-in for ``DistributedDataParallel``.

On this WSL2 + RTX 5060 Ti setup every NCCL collective (``all_reduce``,
``all_gather``) hangs forever, so single-GPU training cannot use DDP at all.

``NoDDP`` keeps the two things the rest of the training code relies on:

* ``model.module``            - ``train.py`` 直接使用 ``model.module``。
* ``"module."`` key prefixing - 把被包裹的模型注册成 ``module`` 子模块后，
  ``nn.Module.state_dict()`` / ``load_state_dict()`` 产生和接受的键名与 DDP 完全一致，
  因此保存出的 ckpt 与官方 DDP 保存的权重格式兼容。
"""

from contextlib import nullcontext

import torch


class NoDDP(torch.nn.Module):
    def __init__(self, module):
        super().__init__()
        self.module = module

    def forward(self, *args, **kwargs):
        return self.module(*args, **kwargs)

    # DDP API used by the training / evaluation loop.
    def no_sync(self):
        return nullcontext()

    def _set_static_graph(self):
        return None

    def __getattr__(self, name):
        # Fall back to the wrapped module for anything not defined here
        # (e.g. ``model.visual``, ``model.logit_scale``).
        try:
            return super().__getattr__(name)
        except AttributeError:
            if name == "module":
                raise
            return getattr(self.module, name)
```

**为什么必须保留 `module.` 前缀**：官方预训练权重 `clip_cn_vit-b-16.pt` 的 `state_dict` 键名带
`module.`（因为原本由 DDP 保存），`main.py` 第 216 行 `resize_pos_embed(sd, model, prefix="module.")`
也按这个前缀取值。`NoDDP` 把模型注册成 `module` 子模块后，`state_dict()` 天然就带这个前缀，
`load_state_dict()` 也天然接受它，所以训练侧不需要任何额外转换。

## 3. 改动二：`cn_clip/training/main.py`

文件：`Chinese-CLIP/cn_clip/training/main.py`，第 135 行附近（原文 132–138 行）

**改前：**

```python
    # To make compatible with torch version <= 1.8.0, set find_unused_parameters to True
    # In other cases, set find_unused_parameters to False
    find_unused_parameters = torch_version_str_compare_lessequal(torch.__version__, "1.8.0")
    model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[args.local_device_rank], find_unused_parameters=find_unused_parameters)
    # Have to set this when activating grad checkpointing in Pytorch >= 2.0.0
    if args.grad_checkpointing and not torch_version_str_compare_lessequal(torch.__version__, "1.14.0"):
        model._set_static_graph()
```

**改后：**

```python
    # To make compatible with torch version <= 1.8.0, set find_unused_parameters to True
    # In other cases, set find_unused_parameters to False
    find_unused_parameters = torch_version_str_compare_lessequal(torch.__version__, "1.8.0")
    if args.world_size > 1:
        model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[args.local_device_rank], find_unused_parameters=find_unused_parameters)
        # Have to set this when activating grad checkpointing in Pytorch >= 2.0.0
        if args.grad_checkpointing and not torch_version_str_compare_lessequal(torch.__version__, "1.14.0"):
            model._set_static_graph()
    else:
        # Single-GPU: NCCL collectives hang on this WSL2 setup, so DDP is skipped.
        # NoDDP keeps model.module and the "module." state_dict prefix.
        from cn_clip.training.no_ddp import NoDDP
        model = NoDDP(model)
        logging.info("world_size == 1: DDP disabled, using NoDDP wrapper.")
```

要点：
- `args.world_size` 在第 57 行由 `dist.get_world_size()` 赋值，此处可直接使用；
- **多卡路径完全保持原样**，只有在 `world_size == 1` 时才走 `NoDDP`；
- `_set_static_graph()` 只在 DDP 分支里调用（`NoDDP` 也实现了空实现的同名方法，双保险）。

## 4. 改动三：`cn_clip/training/train.py`

文件：`Chinese-CLIP/cn_clip/training/train.py`，`evaluate()` 函数内第 387 行附近

`evaluate()` 里的 4 次 `all_reduce` 是**无条件执行**的，且作用在 **CUDA 张量**上，单卡也会触发集合通信：

**改前：**

```python
        dist.all_reduce(cumulative_loss, op=dist.ReduceOp.SUM)
        dist.all_reduce(cumulative_i2t_acc, op=dist.ReduceOp.SUM)
        dist.all_reduce(cumulative_t2i_acc, op=dist.ReduceOp.SUM)
        dist.all_reduce(num_elements, op=dist.ReduceOp.SUM)
```

**改后：**

```python
        if dist.get_world_size() > 1:
            dist.all_reduce(cumulative_loss, op=dist.ReduceOp.SUM)
            dist.all_reduce(cumulative_i2t_acc, op=dist.ReduceOp.SUM)
            dist.all_reduce(cumulative_t2i_acc, op=dist.ReduceOp.SUM)
            dist.all_reduce(num_elements, op=dist.ReduceOp.SUM)
```

单卡时这 4 次归约本来就是恒等操作（只有 1 份数据），跳过不改变数值。

## 5. 配套的启动参数（不改代码，但必须带上）

`scripts/finetune/run_train_single_gpu.sh` 里必须包含：

| 参数 | 原因 |
|---|---|
| `--skip-aggregate` | `train.py` 第 53 行 `if args.aggregate:` 里还有 2 次 `dist.all_gather`（第 72–73 行），单卡也会挂。`--skip-aggregate` 把 `args.aggregate` 设为 False，整段跳过；单卡本来也不需要跨卡聚合特征 |
| 手动设置 `RANK/WORLD_SIZE/LOCAL_RANK/MASTER_ADDR/MASTER_PORT` | `main.py` 第 51 行读 `os.environ["LOCAL_RANK"]`，第 55 行 `init_process_group` 读 `MASTER_*`；不用 `torchrun` 就得自己设 |
| 不用 `torchrun` | torch 2.6+ 的 `torchrun` 自带 `--logs-specs` 参数，会与训练脚本的 `--logs` 前缀冲突，报 `ambiguous option: --logs` |

## 6. 兼容性验证（已实测）

| 验证项 | 结果 |
|---|---|
| `NoDDP` 保存的 ckpt 能否被官方 `extract_features.py` 加载 | ✅ 能。第 157 行 `if next(iter(sd.items()))[0].startswith('module'):` 会自动剥掉前缀 |
| 训练 → 评测全链路 | ✅ 跑通，test R@1 37.37 → 58.67 |
| 多卡行为 | 未改动，理论上不受影响（`world_size > 1` 时仍走原生 DDP） |

## 7. 重新施加的步骤

### 7.1 一键方式（推荐）

补丁已入库在 [`scripts/finetune/patches/`](../../scripts/finetune/patches/)，无需手工改代码。

**第一步：拿到官方代码**（容器内无 `git` 时用 tarball）

```bash
cd /workspace
rm -rf Chinese-CLIP
python - <<'PY'
import io, tarfile, urllib.request, pathlib
url = "https://codeload.github.com/OFA-Sys/Chinese-CLIP/tar.gz/refs/heads/master"
raw = urllib.request.urlopen(url, timeout=180).read()
dest = pathlib.Path("/workspace/_src"); dest.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
    try:
        tf.extractall(dest, filter="data")
    except TypeError:
        tf.extractall(dest)
PY
mv _src/Chinese-CLIP-master Chinese-CLIP && rmdir _src
```

有 `git` 时直接 `git clone https://github.com/OFA-Sys/Chinese-CLIP.git` 也可以。

**第二步：打补丁**

```bash
bash scripts/finetune/patches/apply.sh
```

脚本会复制 `no_ddp.py`、改掉 `main.py` / `train.py` 的两处、做 `ast.parse` 语法自检；
**幂等**，重复执行会显示「已打过，跳过」。若官方代码更新导致上下文变化，它会明确报错，
而不是静默改错。

**第三步：确认打上了**

```bash
grep -n "NoDDP" Chinese-CLIP/cn_clip/training/main.py
grep -n "get_world_size() > 1" Chinese-CLIP/cn_clip/training/train.py
ls -l Chinese-CLIP/cn_clip/training/no_ddp.py
```

真正生效的证据是训练日志里出现：

```
world_size == 1: DDP disabled, using NoDDP wrapper.
```

### 7.2 手工方式（apply.sh 报「没找到预期代码块」时）

说明官方仓库更新了，两处上下文变了。按第 2、3、4 节列出的**改前 / 改后代码**逐字修改，
然后做语法检查：

```bash
python -c "import ast;ast.parse(open('Chinese-CLIP/cn_clip/training/main.py').read())"
python -c "import ast;ast.parse(open('Chinese-CLIP/cn_clip/training/train.py').read())"
```

也可以把官方代码固定到本次验证过的 commit 再跑 `apply.sh`。

> 补丁目录的说明见 [`scripts/finetune/patches/README.md`](../../scripts/finetune/patches/README.md)，
> 其中解释了为什么用 `apply.sh` 的精确替换而不是 `.patch` 文件（`Chinese-CLIP/` 内部没有 git 仓库，
> 手写 diff 容易打不上，失败时还会留下半改状态）。

## 8. 如果换到多卡机器

不需要这些补丁：把 `Chinese-CLIP/` 重新 clone 成原始状态，改用官方的
`run_scripts/muge_finetune_vit-b-16_rbt-base.sh`（或 `torchrun`）即可，多卡下
`world_size > 1`，原生 DDP 会生效。本仓库的 `scripts/finetune/run_finetune.sh` 就是那份官方模板的移植版。

## 9. 相关文档

- [`scripts/finetune/patches/README.md`](../../scripts/finetune/patches/README.md) — 补丁本体与 `apply.sh` 用法
- [`scripts/finetune/README.md`](../../scripts/finetune/README.md) — 训练/评测入口与目录约定
- [`03-微调结果.md`](03-微调结果.md) 第 7 节 — 本次实验的简要记录
