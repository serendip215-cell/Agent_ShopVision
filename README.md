# Agent_ShopVision

电商商品多模态推荐与上架 Agent。

## 当前数据

当前正式处理数据只使用 MUGE，位于 `data/processed_data/`，并按归一化后的 `product_type` 分为包、水杯和鞋三个类别。原始 MUGE 数据保存在 `data/raw_data/MUGE_data/`。

## 数据处理

```bash
python scripts/classify_products.py --input-file data/raw_data/MUGE_data/products.csv --output-dir data/processed_data --category-map "双肩包=包,运动鞋=鞋"
python scripts/check_product_fields.py --input-file data/processed_data/水杯/products.csv
```

更多项目设计见 `docs/电商商品多模态推荐与上架Agent开发文档.md`。

属性补全方案见 `docs/MUGE商品属性大模型补全与描述生成方案.md`。
