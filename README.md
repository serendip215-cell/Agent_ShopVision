<p align="center">
  <img alt="Agent ShopVision" src="https://img.shields.io/badge/Agent__ShopVision-电商多模态商品_Agent-111111?style=for-the-badge&logo=github&logoColor=white">
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="stage" src="https://img.shields.io/badge/阶段-检索与微调已完成-2EA44F?style=flat-square&logo=checkmarx&logoColor=white">
  <img alt="records" src="https://img.shields.io/badge/正式商品-10%2C165-1F6FEB?style=flat-square&logo=databricks&logoColor=white">
  <img alt="categories" src="https://img.shields.io/badge/类别-9-F0883E?style=flat-square&logo=stackshare&logoColor=white">
  <img alt="accepted" src="https://img.shields.io/badge/清洗通过-9%2C393-3FB950?style=flat-square&logo=githubactions&logoColor=white">
  <img alt="sources" src="https://img.shields.io/badge/数据源-MUGE_%7C_Amazon_%7C_苏宁-6E40C9?style=flat-square&logo=datacamp&logoColor=white">
</p>

<h2 align="center">拉取项目后，先把下面这段发给 AI</h2>

<p align="center">
  克隆或 <code>git pull</code> 之后，不要先改代码。<br>
  整段复制到对话框，让 AI 自己读 git 和仓库，再告诉你项目是什么、进度到哪、现在该做什么。
</p>

```text
你在 Agent_ShopVision 仓库里工作。先不要改代码，也不要提交或推送。

请先自己查清现状，再回答：
1. 读 git 记录：当前分支、是否和远端一致、工作区有没有未提交改动、最近提交各自做了什么。
2. 扫仓库目录，读根 README、data/raw_data/README.md、scripts/README.md，以及 data/processed_data 和 data/processed_data_cleaning 里的汇总文件。
3. 文档和 git 记录、实际数据对不上时，以 git 记录和实际文件为准，并指出哪份文档过时。

然后用中文说明四件事：
- 这个项目是做什么的
- 现在进度到哪一步，哪些已经完成，哪些还没开始
- 我们现在应该做什么
- 仓库里大致有什么：数据、脚本、文档

只汇报，等我确认后再动手。
```

<p align="center">
  读取本地商品图片和结构化字段，做属性识别、检索推荐、标题描述生成。<br>
  当前已完成实验 1 数据清洗、中文图文检索基线（含 FAISS 索引）和 Chinese-CLIP 微调（test R@1 37.4→58.7）；<br>
  量化剪枝、前后端和 Agent 仍待继续。
</p>

## ✨ 当前进度

| 步骤 | 状态 | 说明 |
|---|---|---|
| 原始数据采集与入库 | ✅ 完成 | MUGE、Amazon、苏宁，合计 10,165 条，图片均可读 |
| Amazon 中文翻译 | ✅ 完成 | DeepL，结果在 `Amazon_data_translated/` |
| 字段统一与分类合并 | ✅ 完成 | `data/processed_data/`，9 个大类 |
| 图片技术质检 | ✅ 完成 | 正式表 `image_status` 全部为 `ok` |
| 视觉属性清洗 | ✅ 完成 | `data/processed_data_cleaning/`，无待处理、无接口失败 |
| 中文图文检索基线 | ✅ 已实现 | `scripts/retrieval/`，输入 `data/processed_data_cleaning/`，输出 `data/index_data/` |
| 检索 JSON 配置 | ✅ 已完成 | `configs/retrieval.json`，构建和查询脚本默认读取 |
| 实验 1 报告 | ✅ 完成 | `docs/typ/实验一.typ`，编译方法见下文「实验报告编译」 |
| Chinese-CLIP 微调 | ✅ 完成 | 3 轮 / 705 步，test R@1 37.37→58.67、R@5 70.77→89.08；记录见 [`docs/finetune/03-微调结果.md`](docs/finetune/03-微调结果.md) |
| 未清洗数据对照组 | ✅ 完成 | 同一配方只换数据（10,165 条），test R@1 **50.96**；据此拆分出"微调本身 +13.59 / 数据清洗 +7.71"，记录见 [`05-未清洗数据对照组.md`](docs/finetune/05-未清洗数据对照组.md) |
| 微调权重接入检索 | ✅ 完成 | `data/index_data_finetuned/`，9 类 9,393 条，由 `epoch3.pt` 编码；旧索引 `data/index_data/` 保留作基线 |
| 量化剪枝、前后端、Agent | ⏳ 未开始 | 实验 3–5 |

当前数据规模和字段以本页、[`data/raw_data/README.md`](data/raw_data/README.md) 和 `data/processed_data/dataset_summary.csv` 为准。除 [`docs/finetune/`](docs/finetune/)（已完成步骤的实际记录）外，`docs/` 里的方案和指南写于对应步骤之前，不代表仓库已经做到那一步。

## 📦 数据

三份原始数据各自存放，合并只发生在 `processed_data`。

| 来源 | 记录 | 图片 | 说明 |
|---|---:|---:|---|
| MUGE | 4,704 | 4,704 | 中文图文：运动鞋、水杯、双肩包 |
| 苏宁公开搜索页 | 4,303 | 4,303 | 2026-09 采集：男装、运动鞋、水杯、运动服、双肩包、女装 |
| Amazon | 1,158 | 1,158 | 英文原表；中文译文复用同一批图片 |
| **合计** | **10,165** | **10,165** | 翻译暂存不重复计图片 |

### 正式表 `data/processed_data/`

按大类分目录。图片按内容哈希去重，所以部分类别的图片文件数少于记录数。

| 类别 | 记录 | 图片文件 | 可读 |
|---|---:|---:|---:|
| 鞋 | 3,401 | 3,367 | 3,401 |
| 水杯 | 2,523 | 2,505 | 2,523 |
| 包 | 1,330 | 1,315 | 1,330 |
| 男装 | 1,000 | 982 | 1,000 |
| 运动服 | 684 | 673 | 684 |
| 女装 | 361 | 361 | 361 |
| 手机壳 | 300 | 300 | 300 |
| 厨房用品 | 296 | 296 | 296 |
| 家居用品 | 270 | 270 | 270 |

`products.csv` 固定 12 列：

`item_id` · `product_type` · `item_name` · `description` · `brand` · `color` · `material` · `local_image_path` · `image_status` · `image_height` · `image_width` · `is_readed`

`is_readed` 只表示模型是否成功读过这条并完成解析。当前 10,165 条都是 `true`。颜色、材质、细分类和模板描述写在清洗目录，没有回写到这张正式表。

### 清洗结果 `data/processed_data_cleaning/`

模型补了 `type`，并改写 `description` / `color` / `material`。置信度阈值 `0.72`。排除原因是「模型判断为非目标商品或其他类别」。

| 类别 | 覆盖 | 通过 | 待复核 | 排除 | 通过率 |
|---|---:|---:|---:|---:|---:|
| 鞋 | 3,401 | 3,219 | 0 | 182 | 94.6% |
| 水杯 | 2,523 | 2,016 | 3 | 504 | 79.9% |
| 包 | 1,330 | 1,291 | 0 | 39 | 97.1% |
| 男装 | 1,000 | 999 | 1 | 0 | 99.9% |
| 运动服 | 684 | 668 | 0 | 16 | 97.7% |
| 女装 | 358 | 357 | 0 | 1 | 99.7% |
| 手机壳 | 300 | 300 | 0 | 0 | 100% |
| 厨房用品 | 296 | 279 | 0 | 17 | 94.3% |
| 家居用品 | 270 | 264 | 0 | 6 | 97.8% |
| **合计** | **10,162** | **9,393** | **4** | **765** | **92.4%** |

女装正式表有 361 条，清洗汇总只盖住 358 条。缺的 3 条苏宁商品在 `model_audit.jsonl` 里有结论，但没有进入通过表或 `unprocessed_samples.csv`：

| item_id | 审计结论 |
|---|---|
| `12436049566` | 待复核，置信度 0.58，圆领卫衣 |
| `12445265326` | 待复核，置信度 0.45，短袖 T 恤 |
| `12445265605` | 排除，模型看成袜子 |

水杯排除最多，约两成被判成非水杯。

## 📂 目录

```text
Agent_ShopVision/
├── data/
│   ├── raw_data/                  # 只读原始数据
│   │   ├── MUGE_data/
│   │   ├── Amazon_data/
│   │   ├── Amazon_data_translated/
│   │   └── Suning_data/
│   ├── processed_data/            # 正式合并表，9 个类别
│   ├── processed_data_cleaning/   # 视觉清洗结果和人工审核数据
│   ├── processed_data_retrieval/  # 微调数据、实验权重与评测结果（不入库）
│   ├── index_data/                # 预训练权重生成的图文向量和 FAISS 索引
│   └── index_data_finetuned/      # 微调权重（epoch3.pt）生成的索引
├── configs/                       # 检索配置和使用说明
├── scripts/                       # 采集、翻译、整理、质检、抠图、清洗、检索、微调
│   ├── attribute_cleaning/
│   ├── retrieval/
│   └── finetune/
├── models/chinese_clip/           # 预训练权重（不入库）
├── docs/
│   ├── typ/                       # 实验报告 Typst 源：.typ、refs.bib、figures/、figs/
│   ├── scripts/                   # 报告编译脚本 build_typ.sh/.cmd、gen_figures.py
│   ├── finetune/                  # 微调数据/训练/结果/补丁说明与入库凭证
│   ├── typst/                     # Typst 编译器，首次运行自动下载
│   └── build/                     # 编译出的带时间戳 PDF
└── README.md
```

不入库的本地文件：`.env`、`scripts/models/*.onnx`、`models/chinese_clip/`、`data/raw_data/*/images_cutout/`、`data/processed_backups/`、`docs/typst/`、`docs/build/`。

`data/index_data/`（FAISS 索引与商品向量，约 40–80MB）**纳入版本管理**，队友 clone 后即可直接检索。它是派生数据：换模型权重（含微调）后必须重新提取向量并重建，见 [`configs/retrieval.md`](configs/retrieval.md) 第 5 节。

## 🧰 脚本

处理顺序：

```text
crawl_suning.py
        ↓
translate_amazon_products_deepl.py
        ↓
classify_products.py  →  check_product_fields.py
        ↓
attribute_cleaning/run_gpt6luna_cleaning.py
        ↓
cutout_images.py          （可选，抠图不入库）
        ↓
scripts/retrieval/build_category_index.py
        ↓
data/index_data/<类别>/
        ↓
scripts/retrieval/search_category_index.py
```

| 脚本 | 作用 |
|---|---|
| `scripts/crawl_suning.py` | 限量采集苏宁公开搜索页 |
| `scripts/translate_amazon_products_deepl.py` | DeepL 翻译 Amazon 的 5 个文本字段 |
| `scripts/classify_products.py` | 按类别整理 CSV 和图片，支持增量合并 |
| `scripts/check_product_fields.py` | 检查字段、重复 ID、图片路径和状态 |
| `scripts/cutout_images.py` | rembg 批量抠透明底 PNG，需要 Python 3.11+ |
| `scripts/attribute_cleaning/run_gpt6luna_cleaning.py` | 视觉模型补类别、颜色、材质和描述 |
| `scripts/retrieval/build_category_index.py` | 使用 Chinese-CLIP 和 FAISS 建立类别索引 |
| `scripts/retrieval/search_category_index.py` | 使用中文查询词搜索商品图片 |
| `scripts/build_retrieval_dataset.py` | 把清洗数据转成微调用的 tsv/jsonl，按 `item_id` 哈希 8:1:1 切分 |
| `scripts/finetune/run_train_single_gpu.sh` | 单卡微调训练（本机唯一可用入口），产出 `epoch*.pt` |
| `scripts/finetune/run_test_eval.sh` | test 集最终评测（预训练基线 vs 微调权重） |

参数、断点续跑和字段规则见 [`scripts/README.md`](scripts/README.md)。清洗脚本见 [`scripts/attribute_cleaning/README.md`](scripts/attribute_cleaning/README.md)。检索配置见 [`configs/retrieval.md`](configs/retrieval.md)，默认 JSON 配置见 [`configs/retrieval.json`](configs/retrieval.json)。

常用命令（在仓库根目录执行）：

```powershell
python scripts/classify_products.py `
  --input-file data/raw_data/MUGE_data/products.csv `
  --category-map "双肩包=包,运动鞋=鞋"

python scripts/check_product_fields.py `
  --input-file data/processed_data/鞋/products.csv

py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py `
  --input-dir data/processed_data/包

python scripts/retrieval/build_category_index.py \
  --config configs/retrieval.json \
  --categories "鞋" --overwrite

python scripts/retrieval/search_category_index.py "白色运动鞋" \
  --config configs/retrieval.json --category "鞋" --top-k 5
```

清洗脚本只使用 Python 标准库。密钥放在 `scripts/attribute_cleaning/.env`（由 `.env.example` 复制），不要提交。

## 📝 实验报告编译

实验报告用 Typst 写，源文件放 `docs/typ/`，一条命令编译成带时间戳的 PDF。Windows、macOS、Linux 通用。

| 路径 | 作用 |
|---|---|
| `docs/typ/实验一.typ` | 实验一报告源，排版按 `docs/` 里的实验报告模板（正文小四宋体 + Times New Roman、行距 20 磅、图表五号） |
| `docs/typ/refs.bib` | 参考文献库（已逐条溯源），正文用 `@引用键` 交叉引用 |
| `docs/typ/figures/` | CeTZ 插图源与编译出的 SVG（如流水线图） |
| `docs/typ/figs/` | matplotlib 数据图和 drawio / mermaid 图源 |
| `docs/scripts/build_typ.sh` | Mac / Linux / Git Bash 编译入口 |
| `docs/scripts/build_typ.cmd` | Windows 入口，双击即可运行 |
| `docs/scripts/gen_figures.py` | 重新生成数据图（图 2–图 4） |

**Windows**：双击 `docs\scripts\build_typ.cmd`；或在 cmd / PowerShell 里：

```powershell
docs\scripts\build_typ.cmd           # 列出 docs\typ\*.typ，输入编号回车编译
docs\scripts\build_typ.cmd 实验一     # 跳过交互，按编号或文件名关键字直接编译
```

**Mac / Linux**（Windows 也可用 Git Bash）：

```bash
bash docs/scripts/build_typ.sh
bash docs/scripts/build_typ.sh 2
```

编译结果写到 `docs/build/<名称>-<年月日-时分秒>.pdf`，不入 git。`docs/typst/` 里的 Typst 编译器首次运行会自动按当前系统下载，不入 git；Windows 入口依赖 Git Bash（装 Git for Windows 自带，脚本会从 `git.exe` 位置自动找到它）。

**新增实验**：把 `实验二.typ` 放进 `docs/typ/`，重跑编译脚本即可自动识别；文献加进 `refs.bib`，正文 `@引用键` 即可交叉引用。

**插图更新**：数据图改 `docs/scripts/gen_figures.py` 后运行 `python docs/scripts/gen_figures.py`；流水线图改 `docs/typ/figures/pipeline.typ` 后重新编译为 SVG（Mac 把 `typst.exe` 换成 `typst`）：

```bash
docs/typst/typst.exe compile --format svg docs/typ/figures/pipeline.typ docs/typ/figures/pipeline.svg
```

## 📖 文档

说明当前仓库的，是下面三份数据说明和 `scripts/README.md`。方案类文档按写作时的设计原样保留，给后面的检索、本地模型和 Agent 用，不要把里面的目录和步骤当成已经做完。

| 文档 | 性质 |
|---|---|
| [`scripts/README.md`](scripts/README.md) | 当前脚本说明 |
| [`configs/retrieval.json`](configs/retrieval.json) | 检索脚本默认 JSON 配置 |
| [`configs/retrieval.md`](configs/retrieval.md) | 检索环境、参数和运行流程 |
| [`scripts/finetune/README.md`](scripts/finetune/README.md) | 微调入口、目录约定、本机 NCCL 问题与解决 |
| [`docs/finetune/01-数据转换脚本说明.md`](docs/finetune/01-数据转换脚本说明.md) | 微调第 1 步：数据转换脚本 |
| [`docs/finetune/02-微调训练.md`](docs/finetune/02-微调训练.md) | 微调第 2 步：训练环境与参数（含现状更正） |
| [`docs/finetune/03-微调结果.md`](docs/finetune/03-微调结果.md) | **本次微调实验结果**：超参、valid 曲线、test 前后对比 |
| [`docs/finetune/04-Chinese-CLIP补丁说明.md`](docs/finetune/04-Chinese-CLIP补丁说明.md) | 对官方 `Chinese-CLIP/` 的 3 处改动（含改前改后代码、重新施加步骤） |
| [`docs/finetune/05-未清洗数据对照组.md`](docs/finetune/05-未清洗数据对照组.md) | **对照组实验**：未清洗数据直训，用于拆分"微调"与"数据清洗"的贡献 |
| [`data/raw_data/README.md`](data/raw_data/README.md) | 当前原始数据说明 |
| [`data/raw_data/MUGE_data/README.md`](data/raw_data/MUGE_data/README.md) | 当前 MUGE 原始表说明 |
| [`data/raw_data/Amazon_data_translated/README.md`](data/raw_data/Amazon_data_translated/README.md) | 当前 Amazon 译文说明 |
| [`docs/Chinese-CLIP介绍与使用指南.md`](docs/Chinese-CLIP介绍与使用指南.md) | 预留。检索阶段再读 |
| [`docs/电商商品多模态推荐与上架Agent开发文档.md`](docs/电商商品多模态推荐与上架Agent开发文档.md) | 预留。实验 1–5 的总体设计 |
| [`docs/MUGE商品属性大模型补全与描述生成方案.md`](docs/MUGE商品属性大模型补全与描述生成方案.md) | 预留。早期属性补全方案 |
| [`docs/亚马逊数据中文化处理方案.md`](docs/亚马逊数据中文化处理方案.md) | 预留。Amazon 中文化方案 |
| [`docs/Qwen2.5-VL-Ollama安装配置.md`](docs/Qwen2.5-VL-Ollama安装配置.md) | 预留。本地 Qwen 安装 |
| [`data/raw_data/数据集训练阶段详细规划.md`](data/raw_data/数据集训练阶段详细规划.md) | 预留。早期阶段规划，正文仍是当时的 MUGE 三类 |

`docs/` 里还有实验 1 任务书和开课 PDF、实验报告模板，以及已写好的实验一报告源（`docs/typ/实验一.typ`，编译方法见上文「实验报告编译」）。

## 🚧 还没做

- 检索融合权重调优（pilot 验证集已就绪，对比实验尚未做）
- 量化与剪枝
- FastAPI / React
- Agent 工具调用和端到端评测

微调权重的索引已建好（`data/index_data_finetuned/`，9 类 9,393 条）。下一步是用同一套查询集对比新旧索引的端到端召回，再据此调整融合权重。

