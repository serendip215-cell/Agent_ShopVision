# MUGE_data 数据说明

本目录保存 MUGE 中文商品图文数据集的当前整理版本，商品标题和类别保留中文原文。

## 文件

- `products.csv`：商品信息、主图路径和图片尺寸；
- `images/`：与 `products.csv` 中 `local_image_path` 对应的实际图片；
- `image_quality_report.csv`：图片读取、尺寸、格式、文件大小和 SHA-256 检查结果。

## `products.csv` 字段

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

缺失的品牌、颜色和材质等字段保持为空，不根据图片或标题推断。

## `image_quality_report.csv` 字段

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

所有路径均为仓库根目录相对路径，并使用 `/` 分隔符。

## 当前检查结果

- 商品记录：4,704 条；
- 图片文件：4,704 张；
- 图片路径全部可定位；
- 图片尺寸与 `products.csv` 中的尺寸一致；
- 图片质量报告：4,704 张 `pass`，0 张 `review`，0 张 `failed`。

## 来源说明

数据来源标记为 MUGE。当前整理记录标注为 CC BY-NC 4.0，正式使用前仍需核对数据集最新许可证和使用条款。
