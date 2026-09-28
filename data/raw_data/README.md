# raw_data 数据说明

本目录保存当前使用的原始数据集。每个数据集单独存放，暂不合并。

```text
raw_data/
├── Amazon_data/
│   ├── products.csv
│   ├── images/
│   ├── image_quality_report.csv
│   └── README.md
└── MUGE_data/
    ├── products.csv
    ├── images/
    ├── image_quality_report.csv
    └── README.md
```

## 各数据集的共同文件

- `products.csv`：商品信息、图片路径和图片尺寸；
- `images/`：与 `products.csv` 中 `local_image_path` 对应的实际图片；
- `image_quality_report.csv`：图片可读取性、尺寸、格式、文件大小、SHA-256 和质量状态；
- `README.md`：该数据集的来源、字段和检查结果说明。

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

| 数据集 | 商品记录 | 图片文件 | `pass` | `review` | `failed` |
|---|---:|---:|---:|---:|---:|
| Amazon_data | 1,158 | 1,158 | 1,153 | 5 | 0 |
| MUGE_data | 4,704 | 4,704 | 4,704 | 0 | 0 |

Amazon 和 MUGE 目前分别处理、分别维护质量报告。后续如需统一检索或训练，再单独设计合并流程。
