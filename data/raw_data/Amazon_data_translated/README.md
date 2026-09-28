# Amazon_data_translated 数据说明

本目录用于暂存 Amazon 数据的中文翻译结果。

它与原始数据位于同一层级，但不覆盖原始目录：

```text
raw_data/
├── Amazon_data/
├── Amazon_data_translated/
└── MUGE_data/
```

## 当前状态

该目录目前只建立位置，尚未导入翻译后的商品数据。

翻译后的数据仍然需要继续完成：

- 字段顺序和字段值检查；
- 中文标题、类别、颜色和材质规范化；
- 图片路径和图片尺寸检查；
- 商品记录与图片对应检查；
- 图片质量报告核对。

完成上述整理并通过检查后，才进入 `data/processed_data/`，作为正式训练数据使用。

## 计划中的文件

```text
Amazon_data_translated/
├── products.csv
├── images/
├── image_quality_report.csv
└── README.md
```

`products.csv` 的字段顺序与当前 MUGE 数据集一致。该目录不改变 `data/raw_data/Amazon_data/` 中的原始文件。
