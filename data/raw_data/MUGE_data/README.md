# MUGE 数据说明

本目录是从处理后的 MUGE 中文商品图文数据整理出的商品数据集。

- `products.csv`：商品信息、主图相对路径和图片尺寸。
- `images/`：与 `products.csv` 中 `local_image_path` 对应的图片。
- `image_quality_report.csv`：图片读取、尺寸、格式和 SHA-256 校验结果。
- 缺失商品属性保留为空，不根据图片推断。
- 所有路径均为仓库根目录相对路径，并使用 `/` 分隔符。
- 数据来源：MUGE；当前处理记录标记为 CC BY-NC 4.0，使用前请核对最新条款。
