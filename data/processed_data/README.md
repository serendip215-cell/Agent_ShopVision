# processed_data 数据说明

本目录用于保存完成字段整理、路径统一、质量审核和训练数据构建后的正式处理数据。

当前目录先建立结构，暂不放入 Amazon 翻译暂存数据。Amazon 翻译完成后，还需要经过字段检查、图片对应检查和质量审核，确认合格后再进入本目录。

计划中的数据集目录：

```text
processed_data/
└── Amazon_data/
    ├── products.csv
    ├── images/
    ├── image_quality_report.csv
    └── README.md
```

## 当前状态

- `data/raw_data/Amazon_data/`：Amazon 原始数据；
- `data/raw_data/Amazon_data_translated/`：Amazon 中文翻译暂存数据；
- `data/processed_data/`：正式处理数据目录，当前尚未导入 Amazon 数据。

翻译暂存数据不能直接视为训练数据。只有完成整理、路径检查、图片和商品记录对应检查后，才可以复制或生成到本目录。
