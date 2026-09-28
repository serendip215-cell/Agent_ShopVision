# Suning_data 数据说明

本目录为苏宁易购公开搜索页采集的商品数据样本。

- 来源：https://search.suning.com/ （未登录可见的公开搜索页）
- 采集日期：2026-09-28
- 采集脚本：`scripts/crawl_suning.py`（单线程、限速 3 秒/请求、限量、失败自动停）
- 用途：仅课程学习使用，不对外分发。

## 目录结构

```text
Suning_data/
├── products.csv
├── images/
└── image_quality_report.csv
```

## 文件说明

- `products.csv`：商品信息、主图路径和图片尺寸；另含 `price`、`description`、
  `source_url`、`crawl_date` 列。标题和属性保留来源原文，缺失字段保持为空，
  不从图片或标题推断。
- `images/`：与 `products.csv` 中 `local_image_path` 对应的实际图片（原图，非缩略图）。
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
price
description
source_url
crawl_date
```

说明：`brand` 与 `material` 取自搜索卡片「品牌|材质/规格」结构化展示位；
`price` 当前留空（苏宁价格走独立 JS 接口，未采集）。

## 当前检查结果

- 商品记录：30 条（手机壳）；
- 图片文件：30 张，全部下载成功；
- 图片质量报告中 30 张为 `pass`，0 张为 `review`，0 张为 `failed`；
- 品牌、材质、卖点描述字段填充完整。

## 后续扩充

按 `scripts/crawl_suning.py` 中 4 个品类（手机壳、水杯、双肩包、运动鞋）的
搜索词矩阵继续采集，支持断点续传，总量上限 3,000 条。搜索翻页受站点前端
门控，仅首页可稳定获取，数量靠搜索词组合扩充。
