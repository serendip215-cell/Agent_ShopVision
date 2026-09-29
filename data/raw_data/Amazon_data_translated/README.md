# Amazon_data_translated 数据说明

本目录用于暂存 Amazon 数据的中文翻译结果。

它与原始数据位于同一层级，但不覆盖原始目录：

```text
raw_data/
├── Amazon_data/
├── Amazon_data_translated/
└── MUGE_data/
```

## 用途

保存 Amazon 商品的第一阶段中文翻译结果。翻译阶段保留原始 `products.csv` 的 12 个字段，
后续再整理为 MUGE 的 11 个字段。

当前翻译脚本只用于 Amazon 数据：

```powershell
python -m pip install deepl
$env:DEEPL_API_KEY = "你的 DeepL API Key"
python scripts/translate_amazon_products_deepl.py `
  --input-file data/raw_data/Amazon_data/products.csv `
  --output-file data/raw_data/Amazon_data_translated/products.csv `
  --audit-file data/raw_data/Amazon_data_translated/translation_audit.jsonl
```

脚本只翻译 `product_type`、`item_name`、`brand`、`color`、`material`，不处理图片、
`image_quality_report.csv` 或 `description`，也不修改原始 Amazon 文件。审计文件用于断点续译。

翻译阶段的文件：

```text
Amazon_data_translated/
├── products.csv
└── translation_audit.jsonl
```

翻译阶段不复制图片，也不重新生成 `image_quality_report.csv`。`products.csv` 中的
`local_image_path` 继续指向原目录 `data/raw_data/Amazon_data/images/`；后续生成独立的正式处理数据时，
再按类别复制图片到 `data/processed_data/<product_type>/images/`。

正式处理目录的结构为：

```text
data/processed_data/<product_type>/
├── products.csv
├── images/
└── image_quality_report.csv
```

翻译阶段的 `products.csv` 暂时保留原始 12 个字段，不增加 `description`，也不删除 `main_image_id` 和 `domain_name`。完成翻译后，再按正式统一结构整理为 11 个字段并进入后续检查。该目录不改变 `data/raw_data/Amazon_data/` 中的原始文件。

后续与其他数据集合并时，使用 `classify_products.py --append`：旧分类记录和图片都保留，新记录按类别追加；
商品按数据集和商品 ID 去重，图片按 SHA-256 去重。追加前先使用 `--dry-run` 预览结果。
