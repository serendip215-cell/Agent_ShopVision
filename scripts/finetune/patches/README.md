# Chinese-CLIP 单卡补丁

对官方 `Chinese-CLIP/` 的 3 处改动。该目录被 `.gitignore` 排除，所以补丁单独存一份入库。

| 文件 | 作用 |
|---|---|
| `no_ddp.py` | 复制到 `cn_clip/training/no_ddp.py`；单卡用的 DDP 替身，保留 `model.module` 和 `module.` 前缀 |
| `apply.sh` | 一键施加 3 处改动，幂等、带 `ast.parse` 语法自检 |

```bash
bash scripts/finetune/patches/apply.sh
```

已经打过时会输出「跳过」，不会重复改。验证：训练日志里出现
`world_size == 1: DDP disabled, using NoDDP wrapper.`

**为什么需要补丁、改了哪三处、改前改后代码、`apply.sh` 报错时怎么手工处理** ——
全部见 [`docs/finetune/04-Chinese-CLIP补丁说明.md`](../../../docs/finetune/04-Chinese-CLIP补丁说明.md)。
