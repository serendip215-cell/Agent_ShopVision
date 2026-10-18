# 商品检索离线评测包

本目录集中存放检索评测代码、运行脚本、测试输入和本次测试结果。评测只读取索引与商品数据，不会修改它们。

## 目录结构

```text
evaluation/retrieval/
├─ code/
│  ├─ evaluate_retrieval.py       # 编码查询、检索重排、计算指标、绘图
│  └─ run_gpt61sol_pilot.py        # 调用 .env 中配置的模型生成查询、AI 复核并运行评测
├─ scripts/
│  ├─ run_smoke_test.ps1           # 本地演示样例冒烟测试
│  └─ run_gpt_pilot.ps1            # 模型辅助试点评测启动脚本
├─ test_data/
│  ├─ queries_template.csv         # 正式查询集模板
│  ├─ qrels_template.csv           # 通用相关性标签输入模板（AI 试点评测无需填写）
│  ├─ queries_smoke.csv            # 流程演示查询
│  └─ qrels_smoke.csv               # 对应的示例标注
├─ results/
│  ├─ README.md                    # 结果归档规则和已有实验说明
│  └─ runs/<run-id>/                # 每次运行独立归档，不覆盖其他实验
│     ├─ inputs/                    # 查询、qrels 和检索配置快照
│     ├─ ai_review.csv              # AI 对查询候选的最终相关性判断
│     ├─ query_audit.csv             # AI 查询有效性和纳入/排除记录
│     ├─ ranked_results.csv
│     ├─ query_metrics.csv
│     ├─ summary.json
│     └─ run_metadata.json          # 模型、索引、权重和运行设置
└─ README.md
```

## 环境和运行

使用已配置 Chinese-CLIP 的 Python 环境，并确保模型权重和项目索引已准备好。默认索引位于 `data/index_data/`，融合权重读取 `configs/retrieval.json`。

在仓库根目录运行，已激活对应 Conda 环境时：

```powershell
.\evaluation\retrieval\scripts\run_smoke_test.ps1 -Python python -Device cuda
```

运行前先激活已安装项目依赖的 Python 或 Conda 环境。命令默认使用当前环境中的 `python`，不依赖某位开发者机器上的解释器安装路径。

需要 CPU 时将 `-Device cuda` 改成 `-Device cpu`。每次结果默认写入 `results/runs/<自动生成的实验名>/`，不会把多个实验的文件混在一起。查看具体目录时，以命令结束时显示的路径为准。

## 用 AI 生成并复核调优查询集

`run_gpt_pilot.ps1` 会从索引商品生成文字、图片和图文查询，运行检索，再由配置模型核验查询有效性并为 Top-K 候选打相关度分。AI 判为无效的查询写入 `query_audit.csv` 并从最终指标中排除。文字查询的来源商品作为确定性相关锚点，其余候选相关度由 AI 评审；不需要人工填写审核模板。

```powershell
.\evaluation\retrieval\scripts\run_gpt_pilot.ps1 `
  -Python python `
  -Device cuda `
  -PerCategory 5
```

唯一正式评测输入是本轮结果目录下的 `inputs/queries.csv` 和 `inputs/qrels.csv`。统一相关度等级：0 不相关、1 弱相关、2 相关替代、3 高度符合。AI 依据视觉商品检索意图和查询明确提出的约束评分；未提供的颜色、材质或型号信息不作为隐含条件。

本试点结果用于后续验证集调优。AI 生成查询并评审查询有效性和候选相关性，文字查询另保留来源商品锚点；因此它不能当作独立最终测试集或人工真值。权重确定后，仍需建立来源商品不重叠的留出查询集，并用同一套 AI 评审口径单独评估。

查询文件字段：

- `query_id`：唯一查询编号；
- `mode`：`text`、`image` 或 `multimodal`；
- `query_text`、`query_image`：根据模式填写；
- `category`：类别名，留空表示跨已建索引类别查询；
- `exclude_item_id`：可选的查询源商品编号，相似商品评测建议填写。

## 输出和指标

- `inputs/queries.csv`、`inputs/qrels.csv`、`inputs/retrieval_config.json`：本次输入快照；没有 qrels 时不生成其快照；
- `ranked_results.csv`：Top-K 商品、分项相似度、融合分数和商品字段；
- `query_metrics.csv`：逐查询 Recall@K、Precision@K、nDCG@10、MRR@10 和首个相关结果排名；
- `summary.json`：按模式聚合的指标、权重和查询数；
- `run_metadata.json`：实验名、时间、模型、索引、输入文件、阈值和归一化后的最终权重；
- `metrics_by_mode.png`、`first_relevant_rank.png`、`sample_topk_scores.png`：结果图表。

已有结果的说明和归档目录见 `results/README.md`。冒烟数据只验证索引读取、查询编码、排序、指标计算和绘图流程，图片查询使用索引内商品图片，不能作为真实检索效果结论。

## 使用同一脚本比较未调优与调优结果

正式调优时，固定同一份验证查询、qrels、索引和评测参数；每组权重使用不同的 `--run-id`。脚本会把查询、qrels 和配置复制到该实验的 `inputs/`，并将最终权重写入 `run_metadata.json` 和 `summary.json`。这样结果可以并排比较，也能还原当时的输入和参数。

在仓库根目录运行，并按实际验证集文件名替换下面的路径：

```powershell
py -3 evaluation\retrieval\code\evaluate_retrieval.py `
  --queries evaluation/retrieval/test_data/validation_queries.csv `
  --qrels evaluation/retrieval/test_data/validation_qrels.csv `
  --run-id val_text_img_070_desc_030_v1 `
  --top-k 10 --candidate-k 50 `
  --image-weight 0.7 --text-weight 0.3
```

下一组权重换一个实验名，并只改要对比的权重，例如 `--run-id val_text_img_080_desc_020_v1 --image-weight 0.8 --text-weight 0.2`。图文查询通道可通过 `--image-to-image-weight`、`--text-to-image-weight`、`--text-to-description-weight` 调整。权重会在各自通道内自动归一化。

也可以准备独立配置并用 `--config configs/retrieval_tuned.json` 指定。每次运行读取该配置，再由命令行参数覆盖；配置快照和最终权重都会记录在结果目录。每个新实验使用新的 `--run-id`；只有明确要重新生成已有实验时才传 `--overwrite`。

权重只用验证集选择。选定方案后，用同一脚本、同一参数和独立 `--run-id` 在留出的测试集上运行一次，避免用测试集反复调参。

## AI 复核结果的文件组织

`code/run_gpt61sol_pilot.py` 负责生成查询、检索候选、AI 复核和汇总。模型、Base URL 和 API Key 可通过进程环境变量覆盖，或放在仓库根目录 `.env` 的 `PIXEL_API_MODEL`、`PIXEL_API_BASE_URL`、`PIXEL_API_KEY` 中；密钥不会写入结果或日志。不要提交 `.env`。

单轮结果全部在 `results/runs/<run-id>/`：`inputs/queries.csv` 和 `inputs/qrels.csv` 是唯一指标输入；`ai_review.csv` 保存 query-item 评分及理由；`query_audit.csv` 记录查询是否纳入；`ranked_results.csv`、`query_metrics.csv`、`summary.json` 和图表均基于这套最终 AI 评审数据。联系表在同级 `contact_sheets/`。中断检查点位于临时 `work/`，成功完成后自动清除。

运行中断后可使用同一个 `-RunId` 加 `-Resume`；脚本会复用查询、固定排名和 AI 复核检查点。每次新实验使用新的 `-RunId`，避免覆盖已有调优依据。
