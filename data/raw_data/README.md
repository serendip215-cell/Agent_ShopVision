# raw_data 数据说明

本目录保存当前使用的原始数据集，以及 Amazon 中文翻译暂存数据。每个数据集单独存放，暂不合并。

```text
raw_data/
├── Amazon_data/
│   ├── products.csv
│   ├── images/                  # 原始图片 1,158 张
│   ├── images_cutout/           # 抠图试跑输出（5 张 PNG）
│   └── image_quality_report.csv
├── Amazon_data_translated/
│   ├── products.csv             # 中文翻译结果，图片路径指向 Amazon_data/images/
│   ├── translation_audit.jsonl  # 翻译审计、断点续译记录
│   └── README.md
├── MUGE_data/
│   ├── products.csv
│   ├── images/
│   ├── image_quality_report.csv
│   └── README.md
├── Suning_data/
│   ├── products.csv
│   ├── images/                  # 封面图 4,303 张
│   ├── images_cutout/           # 抠图输出 PNG
│   └── image_quality_report.csv
├── 数据集训练阶段详细规划.md      # 从原始数据到中文图文检索训练数据的处理顺序
└── README.md
```

`Amazon_data/` 是原始 Amazon 数据；`Amazon_data_translated/` 是翻译结果的暂存位置，暂时与原始数据放在同一层级。翻译暂存数据完成后还要继续整理和检查，不能直接作为正式训练数据。通过检查后再放入 `data/processed_data/`。

## 各数据集的共同文件

- `products.csv`：商品信息、图片路径和图片尺寸；
- `images/`：与 `products.csv` 中 `local_image_path` 对应的实际图片；
- `image_quality_report.csv`：图片可读取性、尺寸、格式、文件大小、SHA-256 和质量状态；
- `README.md`：该数据集的来源、字段和检查结果说明（当前 MUGE_data、Amazon_data_translated 有，Amazon_data、Suning_data 暂缺）。

差异：

- Amazon_data_translated/ 不带 `images/` 和 `image_quality_report.csv`，`products.csv` 的 `local_image_path` 直接指向 `Amazon_data/images/`（图片不重复存）；
- Amazon_data/images_cutout/ 是抠图试跑输出，分类时可通过 `--cutout` 按路径规则直接使用；
- Suning_data 在共同字段之外另含 `price`、`description`、`source_url`、`crawl_date` 列（价格接口未开放，`price` 留空）。

## `products.csv` 当前字段

12 列（所有数据集一致，顺序固定）：

```text
item_id
product_type
item_name
brand
color
material
main_image_id
domain_name
local_image_path
image_status
image_height
image_width
```

Suning_data 在末尾另有 `price`、`description`、`source_url`、`crawl_date` 4 列，共 16 列。

标题和属性保留来源原文（Amazon_data_translated 的 5 个文本字段为中文译文）。缺失的字段保持为空，不根据图片或标题臆造商品属性。当前全部记录 `image_status=ok`。

## `image_quality_report.csv` 当前字段

```text
dataset_id
source_product_id
image_path
decode_ok
actual_height
actual_width
declared_height
declared_width
format
file_size_bytes
sha256
quality_status
quality_reason
```

报告只使用项目内的 `image_path`，不依赖外部图片目录。`quality_status` 取值 `pass` / `review` / `failed`，非 `pass` 时 `quality_reason` 记录原因（如 `low_resolution`、`extreme_aspect_ratio`）。

## 当前数据集概况

| 数据集 | 商品记录 | 图片文件 | `pass` | `review` | `failed` | 说明 |
|---|---:|---:|---:|---:|---:|---|
| Amazon_data | 1,158 | 1,158 | 1,153 | 5 | 0 | 原始类别 CELLULAR_PHONE_CASE 300 / KITCHEN 296 / SHOES 292 / HOME 270 |
| Amazon_data_translated | 1,158 | （复用上行图片） | — | — | — | 类别已译为中文：手机壳 300 / 厨房用品 296 / 鞋 292 / 家居用品 270 |
| MUGE_data | 4,704 | 4,704 | 4,704 | 0 | 0 | 中文：运动鞋 2,295 / 水杯 1,745 / 双肩包 664 |
| Suning_data | 4,303 | 4,303 | 4,303 | 0 | 0 | 公开搜索页采集（2026-09）：男装 1,000 / 运动鞋 814 / 水杯 778 / 运动服 684 / 双肩包 666 / 女装 361 |

- Amazon_data 的 5 条 `review`：3 条 `low_resolution`、1 条 `extreme_aspect_ratio`、1 条两者兼有，无 `failed`；
- Suning_data 每类上限 1,000 条，除男装外各类未收满即停（搜索词翻页到顶或去重）；
- 各数据集分别处理、分别维护质量报告。后续合并、检索训练流程见 `数据集训练阶段详细规划.md`。
