# 第23组数据集资料

- 组号：23
- 日期：2026.10.10
- 论文：`../实验一-第23组-20261010.pdf`
- 当前仓库中的标准化数据集目录：`data/processed_data/`
- 数据集结构截图：`数据集结构.png`

## 当前数据集

本交付材料对应仓库中的 `data/processed_data/`。该目录按商品大类组织，每个类别包含 `products.csv` 和 `images/`，并保留图片相对路径。当前统计为 **10,165 条商品记录、10,069 个去重图片路径、9 个商品大类**。一张图片可能被多个商品记录复用，因此商品记录数与图片文件数不必相等。

| 类别 | 商品记录 | 去重图片路径 |
|---|---:|---:|
| 包 | 1,330 | 1,315 |
| 厨房用品 | 296 | 296 |
| 女装 | 361 | 361 |
| 家居用品 | 270 | 270 |
| 手机壳 | 300 | 300 |
| 水杯 | 2,523 | 2,505 |
| 男装 | 1,000 | 982 |
| 运动服 | 684 | 673 |
| 鞋 | 3,401 | 3,367 |
| 合计 | 10,165 | 10,069 |

## 标准目录结构

```text
data/processed_data/
├── dataset_summary.csv
├── merge_index.jsonl
├── 包/
│   ├── products.csv
│   ├── image_quality_report.csv
│   └── images/
├── 厨房用品/
│   ├── products.csv
│   ├── image_quality_report.csv
│   └── images/
├── 女装/
│   ├── products.csv
│   ├── image_quality_report.csv
│   └── images/
├── 家居用品/
│   ├── products.csv
│   ├── image_quality_report.csv
│   └── images/
├── 手机壳/
│   ├── products.csv
│   ├── image_quality_report.csv
│   └── images/
├── 水杯/
│   ├── products.csv
│   ├── image_quality_report.csv
│   └── images/
├── 男装/
│   ├── products.csv
│   ├── image_quality_report.csv
│   └── images/
├── 运动服/
│   ├── products.csv
│   ├── image_quality_report.csv
│   └── images/
├── 鞋/
│   ├── products.csv
│   ├── image_quality_report.csv
│   └── images/
```

`products.csv` 保存商品字段、图片相对路径和图片质量信息；`image_quality_report.csv` 保存图片可读取性、尺寸、格式和 SHA-256 检查结果；`images/` 保存与 CSV 配对的商品图片。

## 下载链接

- MUGE 原始数据集下载：<https://clip-cn-beijing.oss-cn-beijing.aliyuncs.com/datasets/MUGE.zip>
- MUGE 官方基线仓库：<https://github.com/MUGE-2021/image-retrieval-baseline>
- 本项目代码仓库：<https://github.com/serendip215-cell/Agent_ShopVision>

MUGE 下载链接用于获取原始公开数据。仓库中的 `data/processed_data/` 是本项目经过字段统一、图片质量检查和类别整理后的版本。使用前请按数据集页面和许可证要求进行核对。

## 说明

- 所有项目内路径使用仓库根目录相对路径，并使用 `/` 分隔符。
- `data/processed_data_cleaning/` 和 `data/index_data/` 属于后续清洗、向量化阶段的生成目录，是否存在取决于本机是否运行过对应脚本。
- 本文件夹没有复制完整图片数据，避免重复占用空间；完整数据仍位于项目根目录的 `data/processed_data/`。
