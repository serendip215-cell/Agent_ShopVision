# GoodsCls 数据说明

本目录为 Kaggle 竞赛「classification-of-goods（平台商品分类）」数据集，
已按项目统一版式整理。

- 来源：https://www.kaggle.com/competitions/classification-of-goods
- 下载日期：2026-09-28
- 整理日期：2026-09-28（train/test 合并为 `products.csv`，划分保留在 `split` 列）
- 用途：仅课程学习使用，遵循竞赛数据条款，不对外分发。

## 目录结构

```text
GoodsCls_data/
├── products.csv
├── images/
├── image_quality_report.csv
└── README.md
```

## 文件说明

- `products.csv`：商品信息、主图路径和图片尺寸；含 `description`、`split` 列。
  标题和描述保留来源原文，缺失字段保持为空，不从图片推断。
- `images/`：42,000 张商品图，文件名 = `item_id` + `.jpg`，与 `products.csv`
  中 `local_image_path` 对应。
- `image_quality_report.csv`：与其余数据集同列格式的质量报告。

## `products.csv` 当前字段

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
description
split
```

说明：

- `item_id`、`item_name`、`description` 来自竞赛 `id`、`title`、`description`；
- `product_type` 为竞赛类目编号（数字），与项目品类不直接对应，映射表待后续统一整理；
- `brand`、`color`、`material`、`domain_name` 来源缺失，保持为空；
- `split` 取值 `train` / `test`，保留原竞赛划分，供实验 2/3 直接使用；
- 无价格字段。

## 当前检查结果

- 商品记录：42,000 条（train 33,633 + test 8,367）；
- 图片文件：42,000 张，与记录一一对应，全部下载/迁移成功；
- 图片质量报告中 42,000 张为 `pass`，0 张为 `review`，0 张为 `failed`；
- 标题、描述字段完整。
