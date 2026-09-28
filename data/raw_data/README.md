# Amazon_data 数据说明

当前数据目录只保留三项内容：

```text
Amazon_data/
├── products.csv
├── images/
└── image_quality_report.csv
```

## 文件说明

- `products.csv`：商品信息、主图路径和图片尺寸。
- `images/`：与 `products.csv` 中 `local_image_path` 对应的实际图片。
- `image_quality_report.csv`：图片是否可读取、尺寸核对、格式和质量标记。

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

标题和属性保留来源原文。缺失的颜色、材质等字段保持为空，不从图片或标题推断。

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

报告只使用项目中的本地 `image_path`，不保留来源图片路径或来源图片 ID。

## 当前检查结果

- 商品记录：1,158 条；
- 图片文件：1,158 张；
- 图片路径全部可定位；
- 图片尺寸与来源尺寸一致；
- 图片质量报告中 1,153 张为 `pass`，5 张为 `review`，0 张为 `failed`。

后续接入新数据集时，在 `raw_data/` 下新增数据集目录。处理后的统一数据放入 `processed_data/`，不按商品类别拆分目录。

