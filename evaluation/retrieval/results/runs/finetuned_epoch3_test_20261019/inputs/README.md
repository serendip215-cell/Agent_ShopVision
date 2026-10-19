# 评测输入说明

本轮是 Chinese-CLIP checkpoint 级文本检索图片评估。截图中展示的 `queries.csv`、`qrels.csv`、`queries_generated.csv`、`query_manifest.csv` 和 `retrieval_config.json` 属于 AI 复核的端到端商品检索评测；本轮 `scripts/finetune/run_test_eval.sh` 不读取或生成这些文件，所以不能从其他 run 复制过来，否则会把不同评测的数据混在一起。

本轮实际评测输入是 `run_manifest.json` 记录的 ShopVision held-out 测试集：934 条测试文本及对应图像 LMDB。测试文本 JSONL 与 LMDB 是外部/大型实验数据，未复制进本结果归档，当前环境也没有这些文件。因此 `inputs/` 只保存可用的训练参数快照和本说明，不包含原始测试样本。

- `params_2026-10-18-12-27-38.txt`：本次微调训练参数快照。
- `run_manifest.json`：记录测试集位置、样本数、候选池、评估参数和权重来源。
- manifest 中的 `/workspace/...` 是原 Docker 容器路径，用于追溯，不是本机 Windows 路径。
