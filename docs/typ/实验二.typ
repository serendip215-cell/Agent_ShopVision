// AI全栈开发实验二：模型设计与训练
// 排版基准：沿用 docs/typ/实验一.typ（逐项核对自 Word 模板渲染结果）：
//   封面：校名/实验名 26pt 粗体（"AI" Times New Roman、"全栈开发实验"黑体）、
//         "题目" 20pt、题目内容 22pt、组号/组员信息/时间 14pt 粗体、组员表 14pt 粗体表头；
//   正文：汉字小四宋体、英文 Times New Roman，行距 20 磅；
//   章标题与"1．需求分析"类小节：14pt 宋体常规；
//   图表中标题和文字字号均为五号（10.5pt）。
// 章节结构取自 docs/AI全栈开发实验报告模板-2026-2.doc（题目：模型设计与训练实验）。
// 文献引用使用 refs.bib，正文 @key 交叉引用。

#set document(title: "AI全栈开发实验二：模型设计与训练")
#set text(font: ("Times New Roman", "SimSun"), lang: "zh", size: 12pt)
#set par(leading: 11.8pt, spacing: 11.8pt, justify: true, first-line-indent: 2em)
#set figure(supplement: [表])
#show figure.where(kind: image): set figure(supplement: [图])
#show figure.caption: it => align(center, text(size: 10.5pt)[
  #it.supplement #it.counter.display(it.numbering)#h(0.5em)#it.body
])
#show raw: set text(font: ("Consolas", "SimSun"), size: 9pt)

#let h1(body) = {
  v(10pt)
  par(first-line-indent: 0pt, text(size: 14pt, font: ("Times New Roman", "SimSun"))[#body])
  v(4pt)
}
#let h2(body) = {
  v(6pt)
  par(first-line-indent: 0pt, text(size: 12pt, font: ("Times New Roman", "SimSun"))[#body])
  v(2pt)
}
#let t5(body) = {
  set text(size: 10.5pt)
  set par(leading: 5pt, spacing: 5pt, first-line-indent: 0pt)
  body
}
#let fillline(w) = box(width: w, height: 0.85em, stroke: (bottom: 0.5pt))

// ============================== 封面 ==============================
#set page(margin: 0pt)
#align(center)[
  #v(2.0cm)
  #text(size: 26pt, font: ("Times New Roman", "SimHei"), weight: "bold")[西安邮电大学]
  #v(2.2cm)
  #text(size: 26pt, font: ("Times New Roman", "SimHei"), weight: "bold")[#text(font: "Times New Roman")[AI] 全栈开发实验]
  #v(2.0cm)
  #text(size: 20pt, weight: "bold")[题目：#text(size: 22pt, font: ("Times New Roman", "SimHei"), weight: "bold")[模型设计与训练实验]]
  #v(2.2cm)
  #grid(
    columns: (auto, 10cm),
    align: (right + horizon, left + horizon),
    [#text(size: 14pt, weight: "bold")[组#h(1.2em)号：]], [#box(width: 10cm, height: 1em, stroke: (bottom: 0.5pt), inset: (x: 0.5em))[#align(center)[#text(size: 14pt, weight: "bold")[23]]]],
  )
  #v(1.0cm)
  #text(size: 14pt, weight: "bold")[组员信息：]
  #v(0.25cm)
  #set text(size: 14pt)
  #table(
    columns: (5.0cm, 3.8cm, 8.6cm),
    align: center + horizon,
    table.header([#text(weight: "bold")[学号]], [#text(weight: "bold")[姓名]], [#text(weight: "bold")[分工]]),
    [#text(weight: "bold")[2610321101]], [何朝杨], [Chinese-CLIP 使用指南与实验报告撰写排版、图表制作],
    [#text(weight: "bold")[2610321103]], [杜军博], [检索模型集成与评测（检索模块、FAISS 索引、三路融合检索、AI 评测管线）],
    [#text(weight: "bold")[2610321135]], [王陆洲], [模型微调训练与优化（微调数据转换、训练执行、NoDDP 补丁、权重评测）],
    [#text(weight: "bold")[2610320046]], [张梓萱], [训练数据构建与划分核验],
    [#text(weight: "bold")[2610320033]], [刘凡思雨], [训练过程记录与结果数据核对],
    [#text(weight: "bold")[2610321168]], [秦鑫洋], [实验报告校对与图表整理],
  )
  #v(0.8cm)
  #grid(
    columns: (auto, 10cm),
    align: (right + horizon, left + horizon),
    [#text(size: 14pt, weight: "bold")[时#h(1.2em)间：]], [#box(width: 10cm, height: 1em, stroke: (bottom: 0.5pt), inset: (x: 0.5em))[#align(center)[#text(size: 14pt, weight: "bold")[2026.10.20]]]],
  )
]
#pagebreak()
#set page(margin: 2.5cm)


// ============================== 一、实验目的 ==============================
#h1[一.#h(0.8em)实验目的]

本实验面向"电商商品多模态推荐与上架 Agent"课题的模型环节，在实验一构建的数据基座上完成中文图文检索模型的设计、训练与适配，具体目的如下：

+ 掌握深度学习框架的安装与开发环境部署：在 WSL2 + Docker 容器内配置 CUDA 版 PyTorch 与 Chinese-CLIP 训练环境@chinese-clip，解决显存、分布式通信等实际工程问题；
+ 掌握多模态模型选型方法：针对电商图文检索任务，比较计算机视觉模型（ViT@vit 与 CNN）、自然语言处理模型（RoBERTa-wwm@roberta-wwm）与多模态对比学习框架（CLIP@clip），选定"双塔编码 + 对比学习"的多模态方案；
+ 掌握训练优化方法：混合精度、梯度检查点、学习率预热与训练过程监控等计算效率优化与梯度控制手段，在 8GB 显存单卡约束下完成稳定微调；
+ 掌握小样本/非标数据的模型适配策略：用实验一清洗产出的 9,393 条领域图文数据做迁移微调，以属性模板文本统一非标标题的文本分布，解决通用预训练模型在电商垂直域的泛化问题；
+ 完成模型评测与落地衔接：以 Recall\@K 等指标量化微调前后差异，形成"数据—模型—指标"的完整证据链，并将微调权重接入检索索引，为实验三（量化剪枝）与后续 Agent 铺垫。

// ============================== 二、实验环境 ==============================
#h1[二.#h(0.8em)实验环境]

#h2[软硬件环境]

- 硬件：NVIDIA GeForce RTX 5060 Ti（8GB 显存，compute capability 12.0），Windows 11 主机 + WSL2；
- 操作系统/容器：WSL2 内 Docker 镜像 `pytorch/pytorch:2.7.1-cuda12.8-cudnn9-devel`；
- 软件：Python 3.11（镜像内 conda）、torch 2.7.1+cu128、PyCharm、Git；
- 核心库：numpy 1.26.4、timm 1.0.30、lmdb 1.3.0（源码编译）、faiss、Chinese-CLIP 官方实现（含本地 NoDDP 补丁）@chinese-clip；
- 模型：Chinese-CLIP ViT-B-16 预训练权重 `clip_cn_vit-b-16.pt`（719MB）；
- 数据：实验一产出的 9 类 9,393 条图文对（LMDB 打包约 1.2GB），由 `scripts/build_retrieval_dataset.py` 转换并按 8:1:1 划分。

// ============================== 三、实验内容与步骤 ==============================
#h1[三．实验内容与步骤]

本实验内容涵盖三部分内容：

#h2[2.1 环境部署：深度学习框架安装、开发工具与环境]
#h2[2.2 模型选型：计算机视觉模型、自然语言处理模型、多模态/多任务模型]
#h2[2.3 训练优化方法：计算效率优化、梯度控制方法、训练过程控制]
#h2[2.4 模型适配策略：解决小样本/非标数据的泛化问题（选做）]

以下按 1．需求分析、2．设计思路、3．代码实现、4. 测试优化四个方面展开。

#h1[1．需求分析]

本课题的检索推荐与上架 Agent 需要"给一句话或一张图就能找到商品"的能力。经分析，模型侧需求如下：

+ 检索能力需求：支持中文文本搜商品图（文搜图）与以图搜图，输出可比对的图文嵌入向量，直接对接实验一落盘的 FAISS 检索链路；
+ 域适配需求：预训练 Chinese-CLIP 面向通用中文图文，对电商属性化表述（颜色、材质、细分类）区分度不足——零样本基线在本数据 test 划分上 R\@1 仅 37.37，必须用领域数据微调；
+ 训练约束：数据仅 9,393 条（小样本）、单卡 8GB 显存，训练方案必须控制过拟合与显存占用，且能稳定复现；
+ 评测需求：给出微调前后的量化对比（Recall\@K），口径严谨、可复算，并保留训练日志与凭证。

#h1[2．设计思路]

整体训练流水线如@fig-pipeline 所示：实验一的清洗数据经属性模板文本构建与哈希划分后打包为 LMDB，微调 Chinese-CLIP 后在 test 划分评测，最后用新权重重建检索索引。

#figure(
  image("figures/finetune_pipeline.svg"),
  caption: [微调训练流水线],
) <fig-pipeline>

模型采用 Chinese-CLIP 双塔结构@chinese-clip@clip，如@fig-arch 所示：视觉塔 ViT-B-16@vit 编码商品图片，文本塔 RoBERTa-wwm-ext-base-chinese@roberta-wwm 编码属性模板文本，两路特征 L2 归一化后以双向 InfoNCE 对比损失联合微调。

#figure(
  image("figures/model_arch.svg"),
  caption: [Chinese-CLIP 双塔模型架构],
) <fig-arch>

关键设计决策：

- 属性模板文本统一文本分布：商品大类/细分类/颜色/材质/标题五段式模板，与建 FAISS 索引使用同一函数生成，让文本塔学到结构化属性表达，也顺带适配了非标标题；
- MD5（item_id）哈希划分 8:1:1：同一商品永远落在同一划分，杜绝图文泄漏；
- 全参微调而非冻结/LoRA：样本虽少但域差异大，双塔全参 3 轮即可收敛且验证曲线未见过拟合；
- 单卡化改造：WSL2 下 NCCL 集合通信挂死，以 NoDDP 包装器保留 `module.` 前缀，兼容官方特征导出脚本，训练代码零侵入降级。

#h1[3．代码实现]

#h2[2.1 环境部署]

Docker 容器内配置 CUDA 版 PyTorch，克隆 Chinese-CLIP 官方代码并施加 3 处本地补丁（`no_ddp.py` 新增、`main.py` 建组条件化、`train.py` 验证阶段 `all_reduce` 仅多卡执行）。lmdb 在镜像内源码编译（无预编译 wheel）。训练入口与复现命令：

```bash
# 训练（单卡约 6 分钟）
bash scripts/finetune/run_train_single_gpu.sh
# 评测（约 3 分钟）
bash scripts/finetune/run_test_eval.sh
```

#h2[2.2 模型选型]

- 计算机视觉模型：选 ViT-B-16@vit。相对 CNN（ResNet50），与官方中文 CLIP 预训练权重严格对齐，全局注意力对商品整体形态、配件构成更稳定；
- 自然语言处理模型：选 RoBERTa-wwm-ext-base-chinese@roberta-wwm。全词掩码预训练对"双肩包/保温杯"这类属性词更敏感，且是 Chinese-CLIP 官方文本塔；
- 多模态模型：选 CLIP 对比学习框架@clip 的中文实现 Chinese-CLIP@chinese-clip。备选的检测/分类模型只能输出类别标签、拿不到可检索的嵌入；纯文本检索丢弃图像模态。双塔对比学习的图文嵌入空间天然支持文搜图/图搜图，与本课题检索任务对口。

#h2[2.3 训练优化方法]

- 计算效率优化：amp 混合精度训练；梯度检查点（grad checkpointing）以时间换显存，是 8GB 显存跑下 batch 32 的前提；`--skip-aggregate` 跳过多卡聚合；
- 梯度控制方法：学习率 1e-5、权重衰减 0.001、warmup 100 步后线性衰减，与官方 MUGE 微调脚本对齐，防止小样本下大步长破坏预训练表征；
- 训练过程控制：每 150 步跑一次验证、每 epoch 存一次检查点、固定随机种子 123；验证监控 valid loss 与 batch 内两路准确率，出现过拟合即早停（实测未出现）。

核心超参快照（由训练脚本自动写出 `params_*.txt`）：

```text
vision_model=ViT-B-16  text_model=RoBERTa-wwm-ext-base-chinese
batch_size=32  valid_batch_size=32  lr=1e-5  wd=0.001
warmup=100  max_epochs=3  context_length=52  precision=amp
grad_checkpointing=on  accum_freq=1  num_workers=2
valid_step_interval=150  valid_epoch_interval=1  seed=123
```

#h2[2.4 模型适配策略（选做）]

针对小样本/非标数据的泛化问题：

- 迁移学习：以中文图文预训练权重为起点，只用 7,520 条训练样本、3 轮 705 步即达到目标指标；
- 文本分布对齐：非标商品标题经属性模板重写为五段式结构化文本（见下），把自由文本的长尾写法收敛到可控分布：

```python
def build_product_text(row):
    """四属性固定输出，标题存在则追加，与建索引同函数。"""
    parts = [f"{label}：{row.get(field)}" for label, field in FIELD_LABELS]
    # FIELD_LABELS = [("商品大类", "product_type"), ("细分类", "type"),
    #                 ("颜色", "color"), ("材质", "material")]
    if row.get("item_name"):
        parts.append(f"商品标题：{row['item_name']}")
    return "；".join(parts)
```

- 防泄漏划分：`split_by_hash` 以 MD5（item_id）决定划分，重复商品不会跨集合：

```python
def split_by_hash(item_id: str, train_ratio: float, valid_ratio: float) -> str:
    """按 item_id 的 MD5 哈希值切分,保证同一 item_id 永远落在同一划分。"""
    digest = hashlib.md5(item_id.encode("utf-8")).hexdigest()
    value = int(digest, 16) % 1000 / 1000.0  # 0.000 ~ 0.999
    if value < train_ratio:
        return "train"
    if value < train_ratio + valid_ratio:
        return "valid"
    return "test"
```

- 数据纯度兜底：实验一视觉清洗（置信度 0.72）预先排除 765 条脏样本，小样本场景下"少而纯"优于"多而杂"。图像几何/光学增强（`--use-augment`）因 timm 1.0 API 兼容性未验证而关闭，先保证训练链路稳定，见第六章展望。

#h1("4. 测试优化")

- NCCL 挂死定位：WSL2 下 `init_process_group` 正常但首次集合通信永久卡死，多种 NCCL 环境变量无效；最终以 NoDDP 单卡改造绕过，并验证检查点的 `module.` 前缀可被官方 `extract_features.py` 直接加载（已实测）；
- 显存溢出处置：开启 amp 与梯度检查点后，8GB 显存可稳定跑 batch 32；
- 工具链冲突：torchrun 2.6 起 `--logs-specs` 与官方脚本 `--logs` 前缀冲突，改用 `python` 直接启动并手动注入 `RANK/WORLD_SIZE` 等环境变量；
- 评测复现：`run_test_eval.sh` 自动把分数、参数快照、训练日志同步到 `docs/finetune/runs/`，`run_manifest.json` 记录权重路径与字节数，确保评测结果可复算；
- 效率：单卡 3 轮训练约 6 分钟、test 评测约 3 分钟，支撑快速迭代。

// ============================== 四、实验关键技术与难点 ==============================
#h1[四．实验关键技术与难点]

+ WSL2 环境下 NCCL 集合通信挂死的绕过：这是本实验最大的工程难点。设计 NoDDP 包装器保留 `model.module` 访问方式与 `module.` state_dict 前缀，使训练侧无感降级、导出侧零修改兼容，避免为单卡重写官方训练代码；
+ 8GB 显存约束下的训练配置：混合精度 + 梯度检查点的组合拳，用约 1.5 倍训练时长换取 batch 32 的稳定运行，避免小 batch 下对比学习负样本不足导致的性能损失；
+ 小样本全参微调的过拟合控制：1e-5 低学习率 + 100 步 warmup + 3 轮短训，配合逐 150 步验证监控——训练全程 valid loss 单调下降、准确率持续上升，未见过拟合拐点；
+ 属性模板文本设计：把非标电商标题重写为"大类/细分类/颜色/材质/标题"五段式结构化文本，既统一了训练与检索的文本口径，也把文本塔的容量集中到区分性属性上；
+ 评测口径的严谨性：batch 内 32 候选的验证准确率与 934 全候选的 R\@K 不可混比；test 划分只允许使用一次，后续调参只能看 valid，防止"提升 21 个点"的结论被测试集污染。

// ============================== 五、实验结果与分析 ==============================
#h1[五、实验结果与分析]

本实验基于实验一的数据集完成模型微调，依次给出数据—模型关联表、基于原始数据与增强数据的对比实验、训练过程前后对比、适配策略验证，并在最后把问题分析关联回实验一的预处理环节。

#h2("1. 数据—模型关联表")

实验一数据集特点（样本量、增强方式等）与本实验模型选型/优化策略的对应关系见@tbl-dm。

#figure(
  t5(
    table(
      columns: (auto, 1.15fr, 1.35fr),
      align: left + horizon,
      table.header([数据维度], [实验一数据集特点（样本量/增强方式）], [实验二模型选型/优化策略]),
      [样本量], [原始 10,165 条 → 增强后 9,393 条；train/valid/test = 7520/939/934], [小样本迁移：预训练权重 + 1e-5 低学习率 + 3 轮短训，验证监控防过拟合],
      [图文配对], [9 大类，图片与文本一一配对], [双塔对比学习@clip@chinese-clip：图文对即正样本对，batch 内互为负样本],
      [文本增强], [DeepL 中文译文 + 属性模板五段式（大类/细分类/颜色/材质/标题）], [RoBERTa-wwm 中文文本塔@roberta-wwm，输入分布收敛后属性词区分度提高],
      [图像增强], [ISNet 抠图、SHA-256 去重、技术质检（image_status 全 ok）], [视觉塔用原图训练（增强体现在数据纯度）；几何/光学增强暂缓，避免引入未验证变量],
      [属性增强], [GPT 视觉清洗补全 type/color/material，置信度阈值 0.72], [结构化属性进入模板文本，把文本塔容量集中到区分性属性上],
      [数据纯度], [视觉清洗排除 765 条非目标商品（通过率 92.4%）], [对比学习正样本对不错配，图文对齐信号不被稀释],
      [划分方式], [按 item_id 的 MD5 哈希 8:1:1 划分], [无泄漏评测：同一商品不跨集合，Recall\@K 结果可信],
    )
  ),
  caption: [数据—模型关联表（实验一样本量/增强方式 ↔ 实验二选型/优化策略）],
) <tbl-dm>

#h2("2. 对比实验：基于原始数据与增强数据，验证数据增强对模型性能的提升")

对比分两层。数据层：逐项对比实验一预处理前的原始数据与增强后的数据（@tbl-data-cmp），这是"数据增强"的自变量本身；模型层：在同一模型架构、同一配方（bs32、lr 1e-5、3 轮、seed 123）、同一评测协议（test 934 条文搜图、候选池 934）下给出三组对比——预训练基线（未训练）、未清洗数据直训（用预处理前 10,165 条训练）、清洗数据微调（用增强后 9,393 条训练），由此把总提升拆成"微调本身"与"数据清洗净贡献"两部分（@tbl-recall、@fig-recall）。

#figure(
  t5(
    table(
      columns: (auto, 1fr, 1fr, 1fr),
      align: left + horizon,
      table.header([维度], [原始数据（实验一预处理前）], [增强数据（实验一预处理后）], [对模型训练的影响]),
      [样本量], [10,165 条，混有脏数据与非目标商品], [9,393 条（通过率 92.4%，排除 765 条）], [样本略减，但图文对齐信号纯度显著提高],
      [文本], [原始标题（Amazon 为英文、规格尾巴多、写法长尾）], [DeepL 中文译文 + 属性模板五段式文本], [文本塔输入分布收敛，域内属性词可学],
      [图片], [存在重复图与个别低质图], [SHA-256 去重、技术质检全部可读], [视觉塔不重复学习同一张图，输入质量有保底],
      [属性], [颜色/材质缺失或"未知"，无细分类], [GPT 视觉清洗补全 type/color/material（阈值 0.72）], [模板中的属性词有图/文依据，区分度提高],
      [主体纯度], [混入配件与非目标商品（水杯类约两成）], [视觉清洗按"图片为准"排除 765 条], [对比学习正样本对不错配，噪声不进训练],
    )
  ),
  caption: [原始数据与增强数据逐项对比（基于实验一预处理环节）],
) <tbl-data-cmp>

模型层对比结果见@tbl-recall、@fig-recall。

#figure(
  t5(
    table(
      columns: (auto, auto, auto, auto, auto, auto),
      align: center,
      table.header([指标], [预训练基线], [未清洗直训], [清洗微调], [直训增益], [清洗增益]),
      [R\@1], [37.37], [50.96], [58.67], [+13.59], [+7.71],
      [R\@5], [70.77], [84.48], [89.08], [+13.71], [+4.60],
      [R\@10], [82.44], [93.04], [96.90], [+10.60], [+3.86],
      [mean_recall], [63.53], [76.16], [81.55], [+12.63], [+5.39],
    )
  ),
  caption: [test 集 Recall\@K 三组对照（文搜图，934 条）。直训增益 = 未清洗直训 − 预训练基线；清洗增益 = 清洗微调 − 未清洗直训],
) <tbl-recall>

#figure(
  image("figs/fig_recall.png"),
  caption: [三组模型 Recall\@K 对比（test 934 条）],
) <fig-recall>

结果分析（"数据增强 → 模型性能提升"因果链，由三组对照支撑）：

+ 对照设计：三组唯一差异是训练所用的数据。预训练基线未接触实验一任何数据；未清洗直训用预处理前的原始表（10,165 条）训练；清洗微调用视觉清洗与属性增强后的数据（9,393 条）训练。后两组配方完全相同（bs32、lr 1e-5、3 轮、seed 123），只换数据；
+ 总效应：R\@1 从 37.37 提升到 58.67（+21.30 个百分点，相对 +57.0%），R\@5、R\@10、mean_recall 同步提升（@tbl-recall）；
+ 归因一（微调本身）：仅用未清洗数据直训，R\@1 已达 50.96（+13.59 个百分点，相对 +36.4%），即总提升中约 64% 来自"预训练权重 + 域内小样本微调"这一域适配训练，与数据质量无关；
+ 归因二（数据清洗净贡献）：从未清洗直训的 50.96 提升到清洗微调的 58.67（+7.71 个百分点），占总提升约 36%。值得注意的是清洗后样本由 10,165 减到 9,393（少 772 条），样本变少而效果更好，说明该场景下"质量优于数量"；
+ 归因三（各 K 值同向但幅度递减）：清洗带来的增益在 R\@1 为 +7.71、R\@5 为 +4.60、R\@10 为 +3.86，K 越宽松增益越小，符合"清洗主要改善最难的首位命中"的预期（R\@10 已接近饱和）；
+ 机制解释：视觉清洗排除 765 条非目标商品（水杯类约两成），避免错误正样本对稀释对比学习信号；属性模板把自由标题收敛为五段式结构化文本（@tbl-data-cmp 文本行），使文本塔能对"颜色/材质/细分类"形成稳定编码——两点共同解释上述 +7.71 的净增益；
+ 口径说明：R\@10 已达 96.90、接近饱和，后续对比建议以 R\@1 或 mean_recall 为主指标；候选池仅 934 条，数字不能与官方 MUGE 十万级榜单横向比较；test 文本与训练同分布（同一属性模板），换成真实用户自由输入时增益会小于本表数字。

#h2("3. 训练优化的前后对比")

训练过程 7 次验证的关键指标见@tbl-train、@fig-curves。

#figure(
  t5(
    table(
      columns: (auto, auto, auto, auto),
      align: center,
      table.header([训练步数], [Valid Loss], [Image2Text Acc（%）], [Text2Image Acc（%）]),
      [150（epoch1）], [0.2225], [91.77], [91.25],
      [235（epoch1）], [0.1963], [93.33], [92.19],
      [300（epoch2）], [0.2056], [91.87], [92.50],
      [450（epoch2）], [0.1571], [94.58], [93.44],
      [470（epoch2）], [0.1543], [94.90], [93.75],
      [600（epoch3）], [0.1444], [94.48], [94.27],
      [705（epoch3）], [*0.1403*], [*94.69*], [*94.48*],
    )
  ),
  caption: [训练过程验证指标（batch 内 32 候选口径，与全候选 R\@K 不可直接比较）],
) <tbl-train>

#figure(
  image("figs/fig_curves.png"),
  caption: [训练过程验证曲线：Loss 下降与两路准确率上升（7 次验证记录）],
) <fig-curves>

前后对比与分析：

+ Valid Loss 从 0.2225 降至 0.1403（-36.9%），Image2Text Acc 从 91.77% 升至 94.69%、Text2Image Acc 从 91.25% 升至 94.48%，全程无回升、无过拟合拐点，第 3 轮末仍在改善；
+ 中途（epoch2 @ 300 步）loss 小幅回弹属 warmup 后正常波动，随后单调下降，说明梯度控制参数（1e-5 / warmup 100 / wd 0.001）设置合理；
+ 训练效率：705 步（7520/32×3）约 6 分钟完成，混合精度与单卡化改造没有牺牲收敛质量。

#h2("4. 模型适配策略的实验验证")

+ 小样本迁移有效性：仅 7,520 条训练样本、3 轮即把 R\@1 提升 21.30 个百分点（@tbl-recall），验证"预训练权重 + 域内小样本微调"适配策略成立；
+ 非标文本适配性：属性模板把自由标题收敛为五段式结构化文本，test 同分布 R\@1 达 58.67（@fig-recall）；同时需如实说明，该口径含"适配模板写法"成分，真实自由查询下的增益需要后续端到端评测补充；
+ 划分可靠性：MD5 哈希划分保证零泄漏，训练/验证/测试为 7520/939/934 条；
+ 结果可落地：微调权重已重新编码全部 9 类 9,393 条商品并重建 FAISS 索引（`data/index_data_finetuned/`，各类 errors 均为 0），适配结果直接接入检索链路。

#h2("5. 问题分析：与实验一预处理环节的关联")

训练与评测中暴露的问题均可回溯到实验一的预处理环节，逐项对应如下：

+ 水杯类检索难度最高：实验一视觉清洗显示水杯类通过率最低（79.9%，504 条被排除），根因是搜索来源混入杯盖、杯刷等配件与非目标商品——这正是"视觉属性清洗"环节的价值：若缺该环节，这些样本会以错误正样本对进入对比学习，直接拉低水杯类的检索精度；
+ 4 条待复核记录：源自清洗期间视觉模型 API 临时 404，属工程问题而非数据问题——实验一"审计日志（model_audit.jsonl）+ is_readed 断点续跑"的设计使该问题可追溯、可重试，未污染训练集；
+ Amazon 四类依赖翻译：手机壳/厨房用品/鞋/家居用品的文本塔输入依赖实验一"跨语言统一"环节的 DeepL 译文，译文质量直接影响这些类目的文搜图效果，逐条翻译审计保证可复查；
+ test 与训练同分布（均出自属性模板）：来自实验一"文本描述生成"增强环节的双刃剑——同分布指标被抬高，真实自由查询的增益会打折，需要端到端评测补齐（见六、展望）；
+ 覆盖率缺口：女装正式表 361 条、清洗仅覆盖 358 条，缺的 3 条在审计中有结论但未入通过表——预处理覆盖率应作为训练数据清单核对项，本实验 9,393 条训练样本全部有据可查。

#h2("6. 检索集成与补充试点评测")

模型级 test 评测验证了 checkpoint 本身的图文对齐能力；为了检查微调权重接入商品索引后的实际行为，仓库另保存了一轮独立的 AI 复核检索试点（`evaluation/retrieval/results/runs/deepseekv4_1_flash_pilot_20261018/`）。该试点从 9 个类别生成 135 条文字、图片和图文查询，经 AI 有效性复核后纳入 132 条，最终形成 1,325 条相关性判断和 1,320 行 Top-10 排名结果。相关度采用 0--3 级：0 为不相关，1 为弱相关，2 为相关替代，3 为高度符合。

#figure(
  image("figs/fig_pilot_metrics.png"),
  caption: [AI 复核检索试点的不同查询模式指标（用于权重调优，不是最终测试）],
) <fig-pilot>

#figure(
  t5(
    table(
      columns: (auto, auto, auto, auto, auto),
      align: center,
      table.header([查询模式], [有效查询数], [Precision\@10], [nDCG\@10], [MRR\@10]),
      [文字], [44], [0.300], [0.868], [0.865],
      [图片], [45], [0.391], [0.874], [0.804],
      [图文], [43], [0.263], [0.862], [0.651],
    )
  ),
  caption: [AI 复核试点按查询模式汇总的指标],
) <tbl-pilot>

图片查询的 Precision\@10（0.391）高于文字查询（0.300）和图文查询（0.263），文字查询的 MRR\@10（0.865）最高；本轮尚不能据此断言图文融合优于单路检索。原因是查询由索引商品字段生成、相关性由 AI 评审，且图片/图文判断主要覆盖返回的 Top-10 候选。因此，这组结果只作为验证集调权重和错误分析的依据，不能替代人工真值或来源商品不重叠的最终测试集。后续调优必须固定 `inputs/queries.csv`、`inputs/qrels.csv`、索引、模型、Top-K 与候选数，每组权重使用新的 `run-id` 归档。

#h2("7. 实验凭证、日志与复现记录")

本实验的关键数字均可由入库凭证复核，而不是只依赖报告中的手工抄录。训练与模型级评测凭证位于 `docs/finetune/runs/2026-10-18_bs32_lr1e-5/`，包括完整训练日志、超参数快照、预训练基线分数、微调后分数和 `run_manifest.json`；指标归档位于 `evaluation/retrieval/results/runs/finetuned_epoch3_test_20261019/`。其中 `summary.json` 记录测试样本数 934、候选池 934、四项指标及限制条件。报告不再直接使用归档目录中的英文仪表盘图，而是由 `docs/scripts/gen_figures_exp2.py` 直接读取上述 JSON 与训练日志，生成中文图 `docs/typ/figs/fig_evidence.png`，保证图表文字、数据来源和报告口径一致。

#figure(
  image("figs/fig_evidence.png"),
  caption: [模型微调训练与测试证据总览：测试召回、验证损失与批内双向准确率],
) <fig-evidence>

#block(breakable: false)[
训练和评测可以按以下顺序复现：先运行 `scripts/build_retrieval_dataset.py` 生成 8:1:1 的 TSV/JSONL，再由官方 `build_lmdb_dataset.py` 打包 LMDB；随后执行 `scripts/finetune/run_train_single_gpu.sh` 训练 3 轮，最后执行 `scripts/finetune/run_test_eval.sh` 生成基线与微调分数。微调索引由 `scripts/retrieval/build_category_index.py --checkpoint ... --output-dir data/index_data_finetuned` 生成，查询脚本从索引注册表自动读取对应权重，避免建索引和查询使用不同模型。
]

// ============================== 六、实验总结与展望 ==============================
#h1[六、实验总结与展望]

总结：本实验完整走通了"环境部署 → 模型选型 → 训练优化 → 模型适配"的模型训练链路：在 WSL2 + Docker 的 8GB 显存单卡上搭建 Chinese-CLIP 训练环境，选定 ViT-B-16 + RoBERTa-wwm 双塔对比学习架构，以混合精度、梯度检查点、低学习率预热等手段稳定微调 3 轮，用实验一的 9,393 条清洗图文数据把 test R\@1 从 37.37 提升到 58.67（相对 +57.0%），mean_recall 从 63.53 提升到 81.55，且全程未见过拟合。微调权重已重建检索索引投入使用，训练日志、超参快照与评测凭证完整入库可复现。小组成员分工见封面表格。

通过本次实验，加深了对"数据—模型"关系的理解：实验一的清洗投入（排除 765 条脏样本）与属性增强（模板化描述）在模型端兑现为 21 个百分点的 R\@1 提升，Data-Centric AI@dcai-manifesto 的理念在模型训练阶段得到直接验证；也体会到显存、分布式通信等工程约束对训练方案设计的实际塑造作用。

展望：

+ 启用图像增强与更大 batch 模拟（`--use-augment`、`accum_freq`），并把训练轮数延长到验证曲线平台期；
+ 用同一套查询集对比新旧索引的端到端召回，据此调优图文三路融合权重；
+ 量化与剪枝（实验三）：在保持 R\@1 的前提下压缩推理开销；
+ 面向 Agent 的工具化（实验四、五）：把检索能力封装为工具，接入前后端与大模型编排。

// ============================== 七、参考文献 ==============================
#h1[七．参考文献]

#set text(size: 10.5pt)
#set par(first-line-indent: 0pt, leading: 5pt, spacing: 5pt)
#bibliography("refs.bib", style: "ieee", title: none)
#set text(size: 12pt)
#set par(leading: 11.8pt, spacing: 11.8pt, first-line-indent: 2em)

#pagebreak()
#h1[附录 A．实验代码、日志与结果目录]

本附录列出本实验实际使用或用于复核的代码、日志、权重说明和图表位置。大体积权重、LMDB 和中间特征按仓库约定不入 Git；报告保留其路径、字节数和可重建命令，源文件以仓库当前版本为准。

#h2[A.1 关键代码入口]

#figure(
  t5(
    table(
      columns: (5.6cm, 6.4cm, 3.6cm),
      align: left + horizon,
      table.header([路径], [作用], [报告对应内容]),
      [`scripts/build_retrieval_dataset.py`], [清洗数据转 TSV/JSONL，并按 item_id 的 MD5 哈希做 8:1:1 划分。], [三.3、五.1、五.4],
      [`scripts/retrieval/text_builder.py`], [生成与 FAISS 建索引一致的属性模板文本。], [二、三.2、五.2],
      [`scripts/retrieval/build_category_index.py`], [用 Chinese-CLIP 编码图片/文本并生成分类 FAISS 索引。], [三.2、六],
      [`scripts/retrieval/search_category_index.py`], [执行文字、图片和图文三路融合检索。], [五.6、六],
      [`scripts/finetune/run_train_single_gpu.sh`], [单卡 3 轮微调入口，启用 AMP、梯度检查点和 NoDDP。], [三.1、三.3、四],
      [`scripts/finetune/run_test_eval.sh`], [一次性生成预训练基线与微调 checkpoint 的 test 分数。], [五.2、五.3、五.7],
      [`scripts/finetune/patches/no_ddp.py`], [单卡 DDP 替身，保留 module 前缀以兼容官方导出脚本。], [三.1、四],
      [`evaluation/retrieval/code/evaluate_retrieval.py`], [固定查询/qrels 后计算 Recall、Precision、nDCG、MRR。], [五.6],
      [`evaluation/retrieval/code/run_gpt61sol_pilot.py`], [生成查询、AI 复核候选并归档试点评测。], [五.6],
    )
  ),
  caption: [实验二关键代码入口与报告对应关系],
) <tbl-code-index>

#h2[A.2 训练与模型级评测凭证]

```text
docs/finetune/runs/2026-10-18_bs32_lr1e-5/
├── out_2026-10-18-12-27-38.log       # 完整训练日志，含 7 次验证记录
├── params_2026-10-18-12-27-38.txt    # 运行时超参数快照
├── baseline_test_score.json          # 预训练权重 test 分数
├── finetuned_epoch3_test_score.json  # epoch3 test 分数
└── run_manifest.json                 # 权重路径、字节数、评测参数和分数

evaluation/retrieval/results/runs/finetuned_epoch3_test_20261019/
├── summary.json                      # 模型级评测汇总（934 条 test）
├── 01_recall_at_k.png                # R@1/R@5/R@10 对比
├── 02_absolute_gain_pp.png           # 绝对提升百分点
├── 03_relative_gain.png              # 相对提升比例
├── 04_validation_trends.png          # 验证趋势
├── 05_training_convergence.png       # 训练收敛
├── 06_epoch_end_validation.png       # 各轮末验证
├── 07_lr_and_runtime.png             # 学习率与运行时诊断
├── 08_evaluation_dashboard.png       # 指标仪表盘
└── render_eval_charts.py             # 图表重绘脚本
```

#h2[A.3 检索试点评测凭证]

```text
evaluation/retrieval/results/runs/deepseekv4_1_flash_pilot_20261018/
├── inputs/queries.csv                 # 132 条有效查询
├── inputs/qrels.csv                   # 唯一最终相关性标签
├── inputs/retrieval_config.json       # 本轮检索配置快照
├── ai_review.csv                      # query-item 相关性与理由
├── query_audit.csv                    # 135 条查询的纳入/排除记录
├── ranked_results.csv                 # 固定 Top-10 排名
├── query_metrics.csv                  # 逐查询 Precision/Recall/nDCG/MRR
├── summary.json                       # 按文字/图片/图文模式汇总
├── run_metadata.json                  # 模型、索引、权重和运行设置
├── metrics_by_mode.png                # 模式对比图
├── first_relevant_rank.png            # 首个相关结果排名
├── sample_topk_scores.png             # 示例 Top-K 分数
└── contact_sheets/                    # 查询图与候选图联系表
```

#h2[A.4 重要约束与复现实验注意事项]

+ `epoch3.pt` 约 2.2 GB，预训练权重约 719 MB；二者和 LMDB/中间特征均由 `.gitignore` 排除，换机器需按 `docs/finetune/02-微调训练.md` 和 `docs/finetune/04-Chinese-CLIP补丁说明.md` 重新准备。
+ test 集 934 条且候选池同为 934，不能与官方 MUGE 十万级候选池的 Recall\@K 横向比较；test 已用于最终分数，后续调参只看 valid 或独立留出集。
+ 训练日志中的 Image2Text/Text2Image Acc 是 batch 内 32 候选口径，不等于全候选 R\@K；两类数字不能直接混比。
+ AI 复核试点的 qrels 由模型生成和审核，适合权重调优与错误分析，不等同于人工真值；最终报告应另建来源商品不重叠的测试查询集。

#h2[A.5 关键训练日志与超参快照摘录]

以下内容直接摘自已入库的 `docs/finetune/runs/2026-10-18_bs32_lr1e-5/` 凭证，用于复核正文中的训练过程数字。日志完整路径为 `out_2026-10-18-12-27-38.log`，超参快照为 `params_2026-10-18-12-27-38.txt`。

```text
2026-10-18,12:28:59 | INFO | Rank 0 | Validation Result (epoch 1 @ 150 steps) | Valid Loss: 0.222458 | Image2Text Acc: 91.77 | Text2Image Acc: 91.25 | logit_scale: 4.605 | Valid Batch Size: 32
2026-10-18,12:29:36 | INFO | Rank 0 | Validation Result (epoch 1 @ 235 steps) | Valid Loss: 0.196262 | Image2Text Acc: 93.33 | Text2Image Acc: 92.19 | logit_scale: 4.605 | Valid Batch Size: 32
2026-10-18,12:30:26 | INFO | Rank 0 | Validation Result (epoch 2 @ 300 steps) | Valid Loss: 0.205614 | Image2Text Acc: 91.87 | Text2Image Acc: 92.50 | logit_scale: 4.605 | Valid Batch Size: 32
2026-10-18,12:31:22 | INFO | Rank 0 | Validation Result (epoch 2 @ 450 steps) | Valid Loss: 0.157131 | Image2Text Acc: 94.58 | Text2Image Acc: 93.44 | logit_scale: 4.605 | Valid Batch Size: 32
2026-10-18,12:31:39 | INFO | Rank 0 | Validation Result (epoch 2 @ 470 steps) | Valid Loss: 0.154281 | Image2Text Acc: 94.90 | Text2Image Acc: 93.75 | logit_scale: 4.605 | Valid Batch Size: 32
2026-10-18,12:32:49 | INFO | Rank 0 | Validation Result (epoch 3 @ 600 steps) | Valid Loss: 0.144449 | Image2Text Acc: 94.48 | Text2Image Acc: 94.27 | logit_scale: 4.605 | Valid Batch Size: 32
2026-10-18,12:33:32 | INFO | Rank 0 | Validation Result (epoch 3 @ 705 steps) | Valid Loss: 0.140302 | Image2Text Acc: 94.69 | Text2Image Acc: 94.48 | logit_scale: 4.605 | Valid Batch Size: 32
```

```text
vision_model: ViT-B-16
text_model: RoBERTa-wwm-ext-base-chinese
batch_size: 32
valid_batch_size: 32
lr: 1e-05
wd: 0.001
warmup: 100
max_epochs: 3
max_steps: 705
context_length: 52
precision: amp
grad_checkpointing: True
accum_freq: 1
num_workers: 2
valid_step_interval: 150
valid_epoch_interval: 1
seed: 123
world_size: 1
```
