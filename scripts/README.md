# 数据处理脚本

当前先处理字段和图片路径，再构建中文图文检索数据。检索数据生成和模型训练脚本尚未编写。

## 1. 整理商品数据：`classify_products.py`

读取商品 CSV，按 `product_type` 分类，复制图片，生成统一的 11 字段 `products.csv`、`image_quality_report.csv` 和 `dataset_summary.csv`。它使用已有类别字段，不会识图或补写商品描述。

在项目根目录运行 MUGE：

```powershell
python scripts/classify_products.py `
  --input-file data/raw_data/MUGE_data/products.csv `
  --output-dir data/processed_data `
  --category-map "双肩包=包,运动鞋=鞋"
```

参数说明：

| 参数 | 是否必需 | 默认值或说明 |
|---|---|---|
| `--input-file` | **必需** | 要处理的商品 CSV |
| `--output-dir` | 可选 | 默认 `data/processed_data` |
| `--category-map` | 可选 | MUGE 建议填写，用于归一化类别 |
| `--repo-root` | 可选 | 默认自动识别项目根目录 |
| `--clean-output` | 可选 | 删除旧输出后重新生成 |

因此，MUGE 也可以简写为：

```powershell
python scripts/classify_products.py --input-file data/raw_data/MUGE_data/products.csv --category-map "双肩包=包,运动鞋=鞋"
```

如需完整重建输出，可加 `--clean-output`。此参数会删除整个指定输出目录，请确认其中没有需要保留的文件后再用。

## 2. 检查整理结果：`check_product_fields.py`

检查必需字段、空值、重复商品 ID、图片路径和 `image_status`。发现问题时退出码为 `1`，通过时为 `0`。

依次检查 MUGE 三类：

```powershell
python scripts/check_product_fields.py --input-file data/processed_data/包/products.csv --report data/processed_data/包/field_check_report.json
python scripts/check_product_fields.py --input-file data/processed_data/水杯/products.csv --report data/processed_data/水杯/field_check_report.json
python scripts/check_product_fields.py --input-file data/processed_data/鞋/products.csv --report data/processed_data/鞋/field_check_report.json
```

检查脚本中只有 `--input-file` 必需；`--report` 可选，不填写时只在终端显示结果。

## 处理顺序

```text
classify_products.py → check_product_fields.py → 中文图文检索数据构建（待开发）
```

不同数据集字段不同时，先完成该数据集的字段映射，再运行整理脚本。图片能正常读取不代表图片内容与商品描述匹配；当前脚本不做语义审核。
