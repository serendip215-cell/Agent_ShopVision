# raw_data 数据说明

本目录保存当前使用的原始数据集，以及 Amazon 中文翻译暂存数据。每个数据集单独存放，暂不合并。

```text
raw_data/
├── Amazon_data/
│   ├── products.csv
│   ├── images/
│   ├── image_quality_report.csv
│   └── README.md
├── Amazon_data_translated/
│   └── README.md
├── MUGE_data/
│   ├── products.csv
│   ├── images/
│   ├── image_quality_report.csv
│   └── README.md
├── GoodsCls_data/          # Kaggle 竞赛原始格式（train/test 划分）
│   ├── train.csv
│   ├── test.csv
│   ├── sample_submission_products.csv
│   ├── train_images/
│   ├── test_images/
│   └── README.md
└── Suning_data/
    ├── products.csv
    ├── images/
    ├── image_quality_report.csv
    └── README.md
```

`Amazon_data/` 是原始 Amazon 数据；`Amazon_data_translated/` 是翻译结果的暂存位置，暂时与原始数据放在同一层级。翻译暂存数据完成后还要继续整理和检查，不能直接作为正式训练数据。通过检查后再放入 `data/processed_data/`。

## 各数据集的共同文件

- `products.csv`：商品信息、图片路径和图片尺寸；
- `images/`：与 `products.csv` 中 `local_image_path` 对应的实际图片；
- `image_quality_report.csv`：图片可读取性、尺寸、格式、文件大小、SHA-256 和质量状态；
- `README.md`：该数据集的来源、字段和检查结果说明。

GoodsCls_data 保留 Kaggle 竞赛原始格式，不套用上述共同结构；如需统一格式，
处理后的数据放入 `processed_data/`，不在 `raw_data/` 下改写。
Suning_data 在共同字段之外另含 `price`、`description`、`source_url`、`crawl_date` 列。

## `products.csv` 当前字段

```text
item_id
product_type
item_name
brand
color
material
main_image_id
local_image_path
image_height
image_width
```

标题和属性保留来源原文。缺失的字段保持为空，不根据图片或标题臆造商品属性。

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

报告只使用项目内的 `image_path`，不依赖外部图片目录。

## 当前数据集概况

| 数据集 | 商品记录 | 图片文件 | `pass` | `review` | `failed` | 说明 |
|---|---:|---:|---:|---:|---:|---|
| Amazon_data | 1,158 | 1,158 | 1,153 | 5 | 0 | 手机壳/厨具/鞋子/家具 |
| MUGE_data | 4,704 | 4,704 | 4,704 | 0 | 0 | 中文：运动鞋/水杯/双肩包 |
| GoodsCls_data | 42,000 | 42,000 | — | — | — | 竞赛原始格式，含 title/description |
| Suning_data | 30 | 30 | 30 | 0 | 0 | 公开搜索页采集样本（手机壳） |

各数据集分别处理、分别维护质量报告（GoodsCls_data 暂无质量报告，且无价格字段）。
后续如需统一检索或训练，再单独设计合并流程。
