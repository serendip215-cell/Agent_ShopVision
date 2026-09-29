# processed_data

本目录保存当前项目使用的 **MUGE 商品数据**。正式处理层不按数据来源建立目录，而是按 `product_type` 分类：

```text
processed_data/
├── dataset_summary.csv
├── merge_index.jsonl（增量模式生成）
├── 包/
├── 水杯/
└── 鞋/
```

每个类别目录包含：

- `products.csv`：该类别商品记录；
- `images/`：该类别商品图片；
- `image_quality_report.csv`：图片存在性、可读取性、尺寸、格式和 SHA-256 检查结果；
- `field_check_report.json`：字段、路径和图片对应检查结果。

`products.csv` 统一使用以下字段：

```text
item_id
product_type
item_name
description
brand
color
material
local_image_path
image_status
image_height
image_width
```

`local_image_path` 是相对于项目根目录的路径，例如：

```text
data/processed_data/水杯/images/741.jpg
```

## 当前数据

当前只处理 MUGE 数据，共 3 类、4704 条记录：

- 包：664 条（原始 `双肩包` 归一化）；
- 水杯：1745 条；
- 鞋：2295 条（原始 `运动鞋` 归一化）。

图片有效率为 100%，具体统计查看 `dataset_summary.csv`。

## 全量重新处理 MUGE 数据

在项目根目录执行：

```bash
python scripts/classify_products.py \
  --input-file data/raw_data/MUGE_data/products.csv \
  --output-dir data/processed_data \
  --category-map "双肩包=包,运动鞋=鞋" \
  --clean-output
```

已有输出目录时必须明确使用 `--clean-output` 全量重建，或使用 `--append` 增量追加；脚本不会默认覆盖已有结果。

## 追加其他数据集

先预览去重和新增数量：

```bash
python scripts/classify_products.py \
  --input-file data/raw_data/Amazon_data_translated/products.csv \
  --output-dir data/processed_data \
  --append \
  --dataset-id Amazon_data \
  --dry-run
```

确认后去掉 `--dry-run` 执行。增量模式保留旧商品和图片，新商品追加到类别 CSV 末尾，图片按 SHA-256 复用或以哈希后缀保存，
并在根目录维护 `merge_index.jsonl`。相同数据集重复运行不会重复追加。

脚本读取 CSV 中已有的 `product_type`，复制或复用对应图片，并将 `local_image_path` 写成相对于项目根目录的路径。

## 字段和路径检查

```bash
python scripts/check_product_fields.py \
  --input-file data/processed_data/水杯/products.csv \
  --report data/processed_data/水杯/field_check_report.json
```

检查器会检查必需字段、空值、重复商品 ID、绝对图片路径、缺失图片和 `image_status` 不一致。`valid` 为 `true` 才表示检查通过。

## 说明

`scripts/classify_products.py` 是按照已有 `product_type` 整理数据的工具，不会根据图片预测类别。若后续需要训练真正的图像分类模型，应把这三个类别目录作为训练数据，再编写独立的模型训练脚本。
