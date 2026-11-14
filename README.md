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
  当前已完成实验 1 数据清洗、中文图文检索基线（含 FAISS 索引）、Chinese-CLIP 微调（test R@1 37.4→58.7）和实验三推理加速（ONNX + TensorRT）；<br>
  实验一至实验三的报告与评测图表均已交付；实验四前后端已完成（双塔 ONNX 待切真模型）；实验五 5.1–5.3 已完成，5.3 工具调用准确率纯模型达 90%（任务书要求 ≥90%），剩 5.4 的 Agent 接口与前后端联调。另剩实验三现场演示/录屏、可选剪枝。
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
| 实验 2 报告 | ✅ 完成 | `docs/typ/实验二.typ` 已编译，交付材料见 [`docs/交付材料/实验二_第23组/`](docs/交付材料/实验二_第23组/) |
| 实验三 推理加速（3.1.4） | ✅ 完成 | ONNX + TensorRT：**延迟 −57.7%**（batch1）/ −52.7%（batch32）、**吞吐 +136.6%** / +111.5%、**精度一致性 −0.43pp**；记录见 [`docs/optimize/`](docs/optimize/) |
| 实验三 量化（3.1.1） | 🧊 冻结 | 6 种配置实测（FP32 / FP16 / INT8 / per-channel / 分塔），裸动态量化最好 −13.06pp，未达 ≤2% 要求；数据与文档保留在 [`docs/optimize/runs/`](docs/optimize/runs/) |
| 实验三评测与绘图交付 | ✅ 完成 | 杜军博沿用已核验训练机结果完成速度/精度判定、9张中文PNG/PDF/SVG与132历史查询指标复算；[统一结果](evaluation/retrieval/results/runs/exp3_inference_acceleration_20261025/测试结果说明.md)，[本人现场操作待办](docs/流程与交接/实验三杜军博任务交付.md) |
| 实验三报告整合 | ✅ 完成 | Typst 正文 `docs/typ/实验三.typ` 已编译；Word/PDF 版报告、9 张结果图表与测量凭证入库 [`docs/交付材料/实验三_第23组/`](docs/交付材料/实验三_第23组/) |
| 实验 4 前后端 | ✅ 基本完成 | **后端**：分层 FastAPI、统一 `{code, result, msg}` 与错误码表、4 个检索接口、占位/ONNX 编码器接缝、CI（black / ruff / mypy / unittest），接口文档 `/docs` `/scalar` `/redoc` 与离线 [`API文档.md`](docs/交付材料/实验四_第23组/api/API文档.md)。**前端**：React + Ant Design 已完成 8 个页面（工作台 `/`、图像分类 `/image`、文本检索 `/text`、图文匹配 `/match`、商品入库 `/admin`、运行记录 `/history`、系统状态 `/status`、对话导购 `/agent`），路由均已注册。双塔 ONNX 待训练机上传 Release 后切真模型。见 [`webapp/README.md`](webapp/README.md) |
| 实验五 5.1 环境与数据 | ✅ 完成 | 100 条微调数据（`data/agent/agent_finetune_data.json`），见 [`docs/实验五/01`](docs/实验五/01-环境与数据准备.md) |
| 实验五 5.2 模型选择与微调 | ✅ 完成 | 基座 Qwen3-4B-Instruct-2507，QLoRA 4-bit，LoRA 适配器 `dist/lora_adapter_v2/`（64MB）。验证集总体 12.88% → **75.76%**（验证集仅 11 条、tool_call 仅 1 条，不具统计意义；工具调用准确率以 5.3 十轮评测为准），见 [`docs/实验五/03`](docs/实验五/03-微调结果实跑记录.md) |
| 实验五 5.3 Agent 框架集成 | ✅ 完成 | LangChain `create_agent` 封装实验4接口 + 多轮槽位继承 + 10 轮准确率评测。**纯模型 90%**（类目 100%），加后处理 100%，见 [`docs/实验五/09`](docs/实验五/09-5.3优化实跑：扩充数据重训.md) |
| 实验五 5.4 部署与测试 | ✅ 完成 | 后端 `/agent/chat`、`/agent/image`、`/agent/session` 已实现入库，前端对话页已对接并通过回归（回归截图与 npm 三件套日志 2026-11-13 入库）；v4 多轮 40 条评测 JSON 100%/动作 90%/命中 82.5%。演示机端到端演练待做，见 [`docs/交付材料/期末_第23组/演示机验证checklist.md`](docs/交付材料/期末_第23组/演示机验证checklist.md) |

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
│   ├── 课程材料/                   # 课程发的：开课 PDF、实验任务书、报告模板 .doc
│   ├── 方案与指南/                 # 各阶段方案与使用指南（写于对应步骤之前）
│   ├── 流程与交接/                 # 各实验的流程与分工、训练机交接说明
│   ├── 交付材料/                   # 实验一/二/三的交付目录（报告 PDF、截图、下载链接、凭证）
│   ├── typ/                       # 实验报告 Typst 源：.typ、refs.bib、figures/、figs/
│   ├── scripts/                   # 报告编译脚本 build_typ.sh/.cmd、gen_figures.py
│   ├── finetune/                  # 微调数据/训练/结果/补丁说明与入库凭证
│   ├── typst/                     # Typst 编译器，首次运行自动下载
│   └── build/                     # 编译出的带时间戳 PDF
├── webapp/                        # 实验四前后端（后端 FastAPI 主体完成、前端 React 待落地，见 webapp/README.md）
└── README.md
```

不入库的本地文件：`.env`、`scripts/models/*.onnx`、`models/chinese_clip/`、`data/raw_data/*/images_cutout/`、`data/processed_backups/`、`docs/typst/`、`docs/build/`。

`data/index_data/`（FAISS 索引与商品向量，9 类 9,393 条，现 104 MB）和 `data/index_data_finetuned/`（78 MB，微调权重编码）**都纳入版本管理**，队友 clone 后即可直接检索。它们是派生数据：换模型权重（含微调）后必须重新提取向量并重建，见 [`configs/retrieval.md`](configs/retrieval.md) 第 5 节。

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
| `docs/scripts/typ_to_word.py` | 把 `docs/typ/实验三.typ` 转成 cli-anything-word 的项目 JSON |
| `docs/scripts/make_word_template.py` | 用 Word COM 造样式模板 `docs/typ/word/实验三报告-样式模板.docx`（字体、行距、缩进、表格线只能靠样式承载；该模板未入库，跑 Word 链前先生成一次） |
| `docs/scripts/refine_word_report.py` | 用 Word COM 补 CLI 块模型表达不了的排版：封面填空线、三线表、粗体/上标、页码 |
| `docs/scripts/check_word_vs_pdf.py` | 逐字比对 Word 版 PDF 与 Typst 版 PDF（相似度 < 0.995 即报错） |

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
| **[`docs/实验五/00-当前进度总览.md`](docs/实验五/00-当前进度总览.md)** | **实验五入口**：当前进度、谁该做什么、报告口径红线 |
| [`docs/实验五/01-环境与数据准备.md`](docs/实验五/01-环境与数据准备.md) | 5.1 数据生成（100 条 instruction/input/output） |
| [`docs/实验五/02-基座选型与LoRA微调.md`](docs/实验五/02-基座选型与LoRA微调.md) | 5.2 选型依据、超参设计、SCNet 表单对照 |
| [`docs/实验五/03-微调结果实跑记录.md`](docs/实验五/03-微调结果实跑记录.md) | 5.2 实跑数字（12.88% → 75.76%，验证集仅 11 条）与环境 |
| [`docs/实验五/04-5.2交接说明.md`](docs/实验五/04-5.2交接说明.md) | 5.2 → 5.3 交接、演示方案 |
| [`docs/实验五/05-5.3完成说明.md`](docs/实验五/05-5.3完成说明.md) | 5.3 任务书要求对照、测试覆盖 |
| [`docs/实验五/06-5.3在5060上执行指南.md`](docs/实验五/06-5.3在5060上执行指南.md) | 5060 机器上的操作手册 |
| [`docs/实验五/07-5.3优化方案.md`](docs/实验五/07-5.3优化方案.md) | 四阶段优化方案（ZXCcs231） |
| [`docs/实验五/08-5.3准确率根因与修复.md`](docs/实验五/08-5.3准确率根因与修复.md) | 20% 根因分析、报告红线 |
| [`docs/实验五/09-5.3优化实跑：扩充数据重训.md`](docs/实验五/09-5.3优化实跑：扩充数据重训.md) | **v2 重训全过程，纯模型 10% → 90%** |
| [`docs/流程与交接/实验五流程与分工.md`](docs/流程与交接/实验五流程与分工.md) | 实验五分工与交接（含 5.2/5.3 完成记录） |
| [`docs/finetune/01-数据转换脚本说明.md`](docs/finetune/01-数据转换脚本说明.md) | 微调第 1 步：数据转换脚本 |
| [`docs/finetune/02-微调训练.md`](docs/finetune/02-微调训练.md) | 微调第 2 步：训练环境与参数（含现状更正） |
| [`docs/finetune/03-微调结果.md`](docs/finetune/03-微调结果.md) | **本次微调实验结果**：超参、valid 曲线、test 前后对比 |
| [`docs/finetune/04-Chinese-CLIP补丁说明.md`](docs/finetune/04-Chinese-CLIP补丁说明.md) | 对官方 `Chinese-CLIP/` 的 3 处改动（含改前改后代码、重新施加步骤） |
| [`docs/finetune/05-未清洗数据对照组.md`](docs/finetune/05-未清洗数据对照组.md) | **对照组实验**：未清洗数据直训，用于拆分"微调"与"数据清洗"的贡献 |
| [`docs/流程与交接/实验三流程与分工.md`](docs/流程与交接/实验三流程与分工.md) | **实验三总流程**：任务切换（3.1.1 冻结 → 3.1.4 主线）、分工、命令与验收清单 |
| [`docs/流程与交接/实验四流程与分工.md`](docs/流程与交接/实验四流程与分工.md) | **实验四分工**：开发三人（何朝杨 主任务，前端 zzx+lfsy 共同）、文档（架构与成员表 何朝杨，其余 djb/wlz/qxy）、报告要求逐条对照 |
| [`docs/流程与交接/实验四模型产物上传说明.md`](docs/流程与交接/实验四模型产物上传说明.md) | 让 wlz 把双塔 ONNX 传到 GitHub Release 的执行说明 |
| [`webapp/README.md`](webapp/README.md) | **实验四前后端开发文档**：三个功能与用户操作、接口文档怎么用、目录结构、接口表、运行命令、模型接入接缝 |
| [`webapp/backend/README.md`](webapp/backend/README.md) | 后端分层说明、依赖与启动命令 |
| [`webapp/API约定.md`](webapp/API约定.md) | **接口契约**：统一返回体 `{code,result,msg}`、错误码表、请求格式、字段命名 |
| [`docs/交付材料/实验四_第23组/api/API文档.md`](docs/交付材料/实验四_第23组/api/API文档.md) | **实验四离线 API 文档**：路径/方法/参数/返回值字段表/错误码表，由 `webapp/backend/scripts/export_api_docs.py` 生成 |
| [`docs/optimize/README.md`](docs/optimize/README.md) | **实验三执行记录索引**：结论、进度、文档编号规则 |
| [`docs/optimize/02-推理加速（3.1.4）.md`](docs/optimize/02-推理加速（3.1.4）.md) | 主任务：指标、测量口径、导出/bench/一致性全套结果 |
| [`scripts/optimize/README.md`](scripts/optimize/README.md) | 实验三 7 个脚本的用途、依赖版本与四个已知坑 |
| [`docs/流程与交接/实验二模板要求.md`](docs/流程与交接/实验二模板要求.md) | 实验二的模板要求与训练机交接说明 |
| [`data/raw_data/README.md`](data/raw_data/README.md) | 当前原始数据说明 |
| [`data/raw_data/MUGE_data/README.md`](data/raw_data/MUGE_data/README.md) | 当前 MUGE 原始表说明 |
| [`data/raw_data/Amazon_data_translated/README.md`](data/raw_data/Amazon_data_translated/README.md) | 当前 Amazon 译文说明 |
| [`docs/方案与指南/Chinese-CLIP介绍与使用指南.md`](docs/方案与指南/Chinese-CLIP介绍与使用指南.md) | 预留。检索阶段再读 |
| [`docs/方案与指南/电商商品多模态推荐与上架Agent开发文档.md`](docs/方案与指南/电商商品多模态推荐与上架Agent开发文档.md) | 预留。实验 1–5 的总体设计 |
| [`docs/方案与指南/MUGE商品属性大模型补全与描述生成方案.md`](docs/方案与指南/MUGE商品属性大模型补全与描述生成方案.md) | 预留。早期属性补全方案 |
| [`docs/方案与指南/亚马逊数据中文化处理方案.md`](docs/方案与指南/亚马逊数据中文化处理方案.md) | 预留。Amazon 中文化方案 |
| [`docs/方案与指南/Qwen2.5-VL-Ollama安装配置.md`](docs/方案与指南/Qwen2.5-VL-Ollama安装配置.md) | 预留。本地 Qwen 安装 |
| [`data/raw_data/数据集训练阶段详细规划.md`](data/raw_data/数据集训练阶段详细规划.md) | 预留。早期阶段规划，正文仍是当时的 MUGE 三类 |

`docs/课程材料/` 里是开课 PDF、各实验任务书和报告模板；报告源在 `docs/typ/`（`实验一.typ`、`实验二.typ`、`实验三.typ`，编译方法见上文「实验报告编译」）。目录怎么分、每份文档什么状态，见 [`docs/README.md`](docs/README.md)。

## 🚧 还没做

- 实验三现场演示/录屏（具体命令与分工见杜军博任务交付说明）
- 检索融合权重调优（pilot 验证集已就绪，对比实验尚未做）
- 剪枝（可选；量化已实测并冻结，见上表）
- 实验四**前端**（React：三个页面、公共组件、Axios 数据流）：分工与开发文档已写，代码未开始；后端已完成主体，可先对占位模式联调
- 实验四真模型接入：双塔 ONNX 待训练机上传 GitHub Release，接入前前后端跑占位编码器（链路通，检索结果无意义）
- 实验四异步任务（Celery + Redis）与端到端/三浏览器测试记录
- Agent 工具调用和端到端评测

微调权重的索引已建好（`data/index_data_finetuned/`，9 类 9,393 条）。下一步是用同一套查询集对比新旧索引的端到端召回，再据此调整融合权重。

