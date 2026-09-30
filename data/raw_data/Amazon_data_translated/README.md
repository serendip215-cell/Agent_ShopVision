# Amazon_data_translated 数据说明

本目录暂存 Amazon 商品的中文翻译结果，不覆盖 `Amazon_data/`，也不复制图片。

```text
raw_data/
├── Amazon_data/                 # 英文原表和图片
├── Amazon_data_translated/      # 本目录
├── MUGE_data/
└── Suning_data/
```

## 本目录文件

```text
Amazon_data_translated/
├── products.csv
├── translation_audit.jsonl
└── README.md
```

`products.csv` 保留原始 Amazon 表的 12 列和顺序，包括 `main_image_id`、`domain_name`。不增加 `description`，也不删除来源列。`local_image_path` 指向 `data/raw_data/Amazon_data/images/`。

脚本只翻译 `product_type`、`item_name`、`brand`、`color`、`material`。类别译名是：`SHOES`→鞋、`KITCHEN`→厨房用品、`HOME`→家居用品、`CELLULAR_PHONE_CASE`→手机壳。审计文件用于断点续译。

```powershell
python -m pip install deepl
$env:DEEPL_API_KEY = "你的 DeepL API Key"
python scripts/translate_amazon_products_deepl.py `
  --input-file data/raw_data/Amazon_data/products.csv `
  --output-file data/raw_data/Amazon_data_translated/products.csv `
  --audit-file data/raw_data/Amazon_data_translated/translation_audit.jsonl
```

## 和正式表的关系

这 1,158 条已经并入 `data/processed_data/` 的手机壳、厨房用品、鞋、家居用品。正式表是另一套 12 列：有 `description` 和 `is_readed`，没有 `main_image_id` 和 `domain_name`，图片在各类的 `images/` 里。

本目录仍然只是翻译暂存，不能直接当训练集。模型改写的描述在 `data/processed_data_cleaning/`。
