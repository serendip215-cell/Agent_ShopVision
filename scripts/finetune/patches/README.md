# Chinese-CLIP 单卡补丁

这里存放我们对官方 `Chinese-CLIP/` 的**全部改动**。因为 `Chinese-CLIP/` 整个目录被
`.gitignore` 排除（第三方代码，约 2.7MB），所以补丁必须单独存一份入库，否则换机器重新
clone 官方代码后改动就丢了，`run_train_single_gpu.sh` 会直接报错。

## 这个补丁解决什么问题

官方训练入口走 `torch.distributed` + DDP。在本机（Windows + WSL2 + Docker，RTX 5060 Ti 单卡）
环境下：

```
dist.init_process_group(backend="nccl")   → 正常返回
第一次 dist.all_reduce(tensor)            → 永久挂死（GPU 0%，显存已加载，日志不动）
```

单卡训练本来不需要任何集合通信，所以补丁的作用是**在 `world_size == 1` 时完全绕开 DDP**。

完整的原因、尝试过但无效的 NCCL 选项、以及每一处改动的改前/改后代码，见
[`docs/finetune/04-Chinese-CLIP补丁说明.md`](../../../docs/finetune/04-Chinese-CLIP补丁说明.md)。

## 目录内容

| 文件 | 作用 |
|---|---|
| `no_ddp.py` | 新增文件，会被复制到 `Chinese-CLIP/cn_clip/training/no_ddp.py`。单卡用的 DDP 替身，保留 `model.module` 和 `module.` 状态字典前缀 |
| `apply.sh` | 一键把 3 处补丁打到 `Chinese-CLIP/` 上，幂等、带语法自检 |
| `README.md` | 本文件 |

补丁一共 3 处：

| # | 文件 | 改动 |
|---|---|---|
| 1 | `cn_clip/training/no_ddp.py` | **新增** |
| 2 | `cn_clip/training/main.py` | `world_size > 1` 才建 DDP，否则用 `NoDDP` |
| 3 | `cn_clip/training/train.py` | 验证阶段 4 次 `all_reduce` 只在多卡时执行 |

评测代码 `cn_clip/eval/` 完全未改。

## 怎么用

前提：仓库根目录下已经有官方代码 `Chinese-CLIP/`（获取方式见 04 文档第 7 节）。

```bash
bash scripts/finetune/patches/apply.sh
```

成功时输出：

```
补丁目录: /workspace/scripts/finetune/patches
目标代码: /workspace/Chinese-CLIP

[1/3] 写入 cn_clip/training/no_ddp.py
[2/3] main.py 已改为 world_size > 1 才建 DDP
[3/3] train.py 的 4 次 all_reduce 已加多卡判断

✅ 语法自检通过（ast.parse），补丁完成
```

**重复执行是安全的**：已经打过时会输出「已有 NoDDP 分支，跳过」「已有 world_size > 1 判断，跳过」。

## 怎么确认打上了

```bash
grep -n "NoDDP" Chinese-CLIP/cn_clip/training/main.py
grep -n "get_world_size() > 1" Chinese-CLIP/cn_clip/training/train.py
ls -l Chinese-CLIP/cn_clip/training/no_ddp.py
```

三条都有输出即表示补丁已生效。真正验证要靠训练日志里出现这一行：

```
world_size == 1: DDP disabled, using NoDDP wrapper.
```

## 为什么用 apply.sh 而不是 .patch 文件

`Chinese-CLIP/` 是从 GitHub tarball 解压出来的，**内部没有 git 仓库**，无法 `git diff` 生成
可信的补丁，手写的 unified diff 又容易因空格/上下文行不一致而 `patch` 失败（那时你会得到一个
半改的状态，很难排查）。

`apply.sh` 的做法是：先判断是否已打过（幂等），再对**确切的代码块**做字符串替换；
如果目标代码块在官方新版本里变了，它会**明确报错并告诉你去看 04 文档第 3/4 节手工修改**，
而不是静默改错。最后用 `ast.parse` 做语法自检。

改前/改后的完整代码在 04 文档里逐字列出，可以对照 review。

## 如果 apply.sh 报「没找到预期代码块」

说明官方仓库更新了，那两处上下文变了。处理方式：

1. 打开 [`docs/finetune/04-Chinese-CLIP补丁说明.md`](../../../docs/finetune/04-Chinese-CLIP补丁说明.md) 第 3、4 节，按里面列出的改前/改后代码手工修改；
2. 或者先把官方代码固定到本次验证过的版本（commit/tag），再跑 `apply.sh`；
3. 改完用 `python -c "import ast,sys;ast.parse(open(p).read())"` 做语法检查，然后跑一次训练看日志里有没有
   `world_size == 1: DDP disabled`。

## 换到多卡机器怎么办

不需要这个补丁。重新 clone 干净版 `Chinese-CLIP/`，用官方
`run_scripts/muge_finetune_vit-b-16_rbt-base.sh`（或 `torchrun`）即可——
`world_size > 1` 时走的仍是原生 DDP，行为与官方一致。
