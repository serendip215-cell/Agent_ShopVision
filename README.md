<p align="center">
  <img alt="Agent ShopVision" src="https://img.shields.io/badge/Agent__ShopVision-电商多模态商品_Agent-111111?style=for-the-badge&logo=github&logoColor=white">
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="stage" src="https://img.shields.io/badge/阶段-实验1_·_数据清洗-2EA44F?style=flat-square&logo=checkmarx&logoColor=white">
  <img alt="records" src="https://img.shields.io/badge/正式商品-10%2C165-1F6FEB?style=flat-square&logo=databricks&logoColor=white">
  <img alt="categories" src="https://img.shields.io/badge/类别-9-F0883E?style=flat-square&logo=stackshare&logoColor=white">
  <img alt="accepted" src="https://img.shields.io/badge/清洗通过-9%2C393-3FB950?style=flat-square&logo=githubactions&logoColor=white">
  <img alt="sources" src="https://img.shields.io/badge/数据源-MUGE_%7C_Amazon_%7C_苏宁-6E40C9?style=flat-square&logo=datacamp&logoColor=white">
</p>

<p align="center">
  读取本地商品图片和结构化字段，做属性识别、检索推荐、标题描述生成。<br>
  当前停在实验 1：三源数据已并进正式表，视觉属性清洗已跑完。检索、训练、前后端和 Agent 还没开始。
</p>

## ✨ 当前进度

| 步骤 | 状态 | 说明 |
|---|---|---|
| 原始数据采集与入库 | ✅ 完成 | MUGE、Amazon、苏宁，合计 10,165 条，图片均可读 |
| Amazon 中文翻译 | ✅ 完成 | DeepL，结果在 `Amazon_data_translated/` |
| 字段统一与分类合并 | ✅ 完成 | `data/processed_data/`，9 个大类 |
| 图片技术质检 | ✅ 完成 | 正式表 `image_status` 全部为 `ok` |
| 视觉属性清洗 | ✅ 完成 | `data/processed_data_cleaning/`，无待处理、无接口失败 |
| 中文图文检索样本 | ⏳ 未开始 | 脚本还没写 |
| 检索基线 / 模型训练 | ⏳ 未开始 | 实验 2 |
| 量化剪枝、前后端、Agent | ⏳ 未开始 | 实验 3–5 |

课程对应关系见 [`docs/电商商品多模态推荐与上架Agent开发文档.md`](docs/电商商品多模态推荐与上架Agent开发文档.md)。该文档里「正式数据只有 MUGE」的说法已过时，以本页和 [`data/raw_data/README.md`](data/raw_data/README.md) 为准。

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
│   └── processed_data_cleaning/   # 视觉清洗结果、审计、未通过样本
├── scripts/                       # 采集、翻译、整理、质检、抠图、清洗
│   └── attribute_cleaning/
├── docs/                          # 方案、安装说明、实验材料
└── README.md
```

不入库的本地文件：`.env`、`scripts/models/*.onnx`、`data/raw_data/*/images_cutout/`、`data/processed_backups/`。

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
中文图文检索数据           （待写）
```

| 脚本 | 作用 |
|---|---|
| `scripts/crawl_suning.py` | 限量采集苏宁公开搜索页 |
| `scripts/translate_amazon_products_deepl.py` | DeepL 翻译 Amazon 的 5 个文本字段 |
| `scripts/classify_products.py` | 按类别整理 CSV 和图片，支持增量合并 |
| `scripts/check_product_fields.py` | 检查字段、重复 ID、图片路径和状态 |
| `scripts/cutout_images.py` | rembg 批量抠透明底 PNG，需要 Python 3.11+ |
| `scripts/attribute_cleaning/run_gpt6luna_cleaning.py` | 视觉模型补类别、颜色、材质和描述 |

参数、断点续跑和字段规则见 [`scripts/README.md`](scripts/README.md)。清洗脚本见 [`scripts/attribute_cleaning/README.md`](scripts/attribute_cleaning/README.md)。

常用命令（在仓库根目录执行）：

```powershell
python scripts/classify_products.py `
  --input-file data/raw_data/MUGE_data/products.csv `
  --category-map "双肩包=包,运动鞋=鞋"

python scripts/check_product_fields.py `
  --input-file data/processed_data/鞋/products.csv

py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py `
  --input-dir data/processed_data/包
```

清洗脚本只使用 Python 标准库。密钥放在 `scripts/attribute_cleaning/.env`（由 `.env.example` 复制），不要提交。

## 📖 文档

| 文档 | 内容 |
|---|---|
| [`scripts/README.md`](scripts/README.md) | 脚本参数和当前处理顺序 |
| [`data/raw_data/README.md`](data/raw_data/README.md) | 三份原始数据的字段和规模 |
| [`docs/电商商品多模态推荐与上架Agent开发文档.md`](docs/电商商品多模态推荐与上架Agent开发文档.md) | 实验 1–5 的总体设计 |
| [`docs/Chinese-CLIP介绍与使用指南.md`](docs/Chinese-CLIP介绍与使用指南.md) | 检索模型原理、数据格式、基线流程与分工安排 |
| [`docs/MUGE商品属性大模型补全与描述生成方案.md`](docs/MUGE商品属性大模型补全与描述生成方案.md) | 属性补全方案 |
| [`docs/亚马逊数据中文化处理方案.md`](docs/亚马逊数据中文化处理方案.md) | Amazon 翻译方案 |
| [`docs/Qwen2.5-VL-Ollama安装配置.md`](docs/Qwen2.5-VL-Ollama安装配置.md) | 本地视觉模型安装 |
| [`data/raw_data/数据集训练阶段详细规划.md`](data/raw_data/数据集训练阶段详细规划.md) | 早期阶段规划，仍写着只有 MUGE 三类，尚未改到现在的九类 |

`docs/` 里还有实验 1 任务书和开课 PDF，以及实验报告模板。

## 🚧 还没做

- 中文图文检索样本和检索基线
- 模型训练、量化与剪枝
- FastAPI / React
- Agent 工具调用和端到端评测

下一件该做的事是：用清洗通过的 9,393 条生成中文图文检索数据。正式表里的 `color` / `material` / `description` 仍多半是来源原文，检索文本应读 `processed_data_cleaning/`。
