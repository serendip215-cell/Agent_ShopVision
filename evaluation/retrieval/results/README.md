# 检索评测结果与调优依据

每次评测保存在 `runs/<run-id>/`。一轮实验只维护一套最终 AI 复核输入、相关性标签和指标；所有调优都以该套结果为准。

## 实验三推理加速交付（2026-10-25）

[exp3_inference_acceleration_20261025](runs/exp3_inference_acceleration_20261025/测试结果说明.md) 使用用户认可的训练机结果，执行速度/精度验收复算和报告绘图，没有新增模型推理。INT8、4-bit、剪枝不纳入本轮。

    runs/exp3_inference_acceleration_20261025/
    ├── inputs/                 原始凭证、历史查询快照、配置及SHA-256来源记录
    ├── tables/                 速度/精度/验收/模型规模/文件大小/类别基线CSV
    ├── figures/                9张中文图：PNG/PDF/SVG/figure.json及逐图说明
    ├── reference_retrieval/    历史132查询的排序指标复算，单独保留
    ├── summary.json           主线判定、来源模式、范围和限制
    ├── run_metadata.json      源提交、生成时间、实际执行/未执行项目
    └── 测试结果说明.md         本轮结论、文件作用与复现方法

这是推理加速交付结构，不强行套用下面的AI生成查询结构。934条精度为双塔模型级测试；测速只覆盖图像塔forward；132条历史查询不作为TRT新测或端到端加速证据。未提供的TRT分类别损失不补造。现场演示仍需本人在训练机操作。

后续新的加速实验继续使用独立run-id；入口为 evaluation/retrieval/code/evaluate_acceleration.py，配置为 evaluation/retrieval/configs/exp3_acceleration.json。不要覆盖本轮或旧试点目录。

另外，`runs/finetuned_epoch3_test_20261019/` 是微调权重在固定图文测试集上的模型级评估归档。它用于保存 checkpoint 测试分数和训练曲线图，不属于下述 AI 复核查询/qrels 评测结构，也不与端到端商品索引检索指标混算。见 [该轮测试结果说明](runs/finetuned_epoch3_test_20261019/测试结果说明.md)。

## 目录结构

```text
runs/<run-id>/
├─ inputs/
│  ├─ queries.csv                 # AI 复核通过、实际参与指标计算的查询
│  ├─ qrels.csv                   # AI 候选判断和文字查询源商品锚点组成的最终标签
│  ├─ queries_generated.csv       # AI 生成的全部查询，包含被排除项
│  ├─ query_manifest.csv          # query 与源商品、查询模式的对应关系
│  └─ retrieval_config.json       # 本轮检索权重和参数快照
├─ contact_sheets/                # 查询图及 Top-K 候选图，供 AI 视觉评审追溯
├─ ai_review.csv                  # AI 候选判断、源商品锚点、依据和置信度
├─ query_audit.csv                # 每条查询的有效性、纳入状态和 AI 评审理由
├─ ranked_results.csv             # 有效查询的固定 Top-K 排名及分项分数
├─ query_metrics.csv              # 每条有效查询的指标
├─ summary.json                   # 汇总指标、评审模型和调优用途
├─ run_metadata.json              # 索引、编码模型、权重、输入和运行参数
├─ api_usage.json                 # AI 模型调用次数及服务返回的 token 统计
├─ metrics_by_mode.png            # 不同查询模式的指标图
├─ first_relevant_rank.png        # 首个相关结果位置图
├─ sample_topk_scores.png         # 示例查询分数图
└─ 测试结果说明.md                 # 本轮结论、限制和文件说明
```

运行中的检查点暂存在 `work/`；本轮成功完成后会自动删除。失败或中断时可以用同一个 `run-id` 加 `-Resume` 继续。

## 文件职责

| 文件 | 内容与用途 | 后续调优是否使用 |
|---|---|---|
| `inputs/queries.csv` | AI 判定有效、进入本轮指标计算的文字/图片/图文查询。 | **使用**；调权重时固定不变。 |
| `inputs/qrels.csv` | 对候选商品的最终 0–3 级相关性标签；候选由 AI 评审，文字查询另保留确定性源商品锚点。 | **使用**；必须和同轮 `queries.csv` 配套。 |
| `inputs/queries_generated.csv` | 全部生成查询，包括被 AI 判为无效的查询，便于追溯筛选过程。 | 不直接参与指标。 |
| `inputs/query_manifest.csv` | 查询 ID、源商品、类别、模式及生成来源的映射。 | 用于追溯和按源商品分组切分。 |
| `inputs/retrieval_config.json` | 本轮使用的索引和检索参数快照。 | 调参对比时作为基线记录。 |
| `ai_review.csv` | AI 对每个 query-item 候选的等级、置信度和理由；同时标记确定性源商品锚点及查询是否纳入。 | **作为 qrels 的解释与审计明细**；指标以 `qrels.csv` 为准。 |
| `query_audit.csv` | AI 对查询有效性的判断；被排除的查询保留理由但不进入 `queries.csv`。 | 用于排查查询构造问题。 |
| `ranked_results.csv` | 检索候选排序和图片/文本分项分数；只保留有效查询。 | **用于复现排序、分析权重影响**。 |
| `query_metrics.csv` | 每条查询的 Precision、Recall、nDCG、MRR 等。 | **用于定位调参收益或退化**。 |
| `summary.json` | 分模式汇总指标、相关度口径、AI 评审来源和试点用途。 | **用于实验间对比**。 |
| `run_metadata.json` | Chinese-CLIP 模型、索引、权重、Top-K、输入快照位置等。 | 用于确认各轮实验是否可比。 |
| `api_usage.json` | 记录 AI 评审模型、网关地址、调用数和 token 用量，不含 API Key。 | 仅用于成本和运行追踪。 |
| `contact_sheets/` | 每张图对应一条图片/图文查询及其 Top-K 候选。 | 可用于抽查 AI 视觉判断；不替代 qrels。 |
| `metrics_*.png` | 从最终 `query_metrics.csv` 生成的图表。 | 展示用途；重绘时以 CSV/JSON 为准。 |
| `测试结果说明.md` | 当前实验的指标、发现、限制和文件说明。 | 阅读入口，不作为机器输入。 |

## 相关度口径

- `0`：不相关；
- `1`：弱相关；
- `2`：相关替代；
- `3`：高度符合。

AI 按商品视觉/类别意图和查询明确提出的条件评分。未提供的颜色、材质或型号信息视为未知；只有查询明确提出的条件才作为硬约束。文字查询由目录商品字段生成，因此会把来源商品保留为确定性相关锚点；AI 负责审核查询是否有效，并评审返回候选商品。每轮只维护这一套最终 qrels，避免多个口径造成调优目标不一致。

## 调优使用规则

1. 将当前试点作为**验证/调优集**，在比较权重时固定 `inputs/queries.csv`、`inputs/qrels.csv`、索引、模型、Top-K 和候选数。
2. 每组权重使用新的 `run-id`，保留结果并排比较；不要覆盖已有实验。
3. 查询由 AI 生成、相关度由 AI 评审，因此指标适合初步权重选择和错误分析，不等同于人工真值或独立泛化测试结果。
4. 确定权重后，另建来源商品不重叠的留出查询集，使用相同 AI 评审口径单独报告最终测试结果；不要用最终测试集反复调参。

## 当前归档

当前试点目录：`runs/deepseekv4_1_flash_pilot_20261018/`。该轮包含 9 个类别、135 条生成查询，AI 复核后再按查询有效性筛选；最终使用的有效查询数、相关性判断数和指标见其 `summary.json` 与 `测试结果说明.md`。
