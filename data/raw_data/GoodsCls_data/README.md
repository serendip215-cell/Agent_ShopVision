# GoodsCls 数据说明

本目录为 Kaggle 竞赛「classification-of-goods（平台商品分类）」数据集原样保留。

- 来源：https://www.kaggle.com/competitions/classification-of-goods
- 下载日期：2026-09-28
- 用途：仅课程学习使用，遵循竞赛数据条款，不对外分发。

## 目录结构

```text
GoodsCls_data/
├── train.csv                  # 33,633 条：id, title, description, categories
├── test.csv                   # 8,367 条：id, title, description（无类别标签）
├── sample_submission_products.csv
├── train_images/train_images/ # 33,633 张，与 train.csv 按 id 一一对应
└── test_images/test_images/   # 8,367 张，与 test.csv 按 id 一一对应
```

## 文件说明

- `train.csv` / `test.csv`：商品标题和描述为来源原文，缺失字段保持为空，不从图片推断。
- 图片文件名 = `id` + 扩展名，与 CSV 主键对应。
- `categories` 为竞赛编号的类别 ID，与本项目品类不直接对应，映射表待后续统一整理。

## 统计

- 商品记录：42,000 条（train 33,633 + test 8,367）；
- 图片文件：42,000 张，与记录一一对应；
- 标题、描述字段完整；无价格字段。

后续如需统一为项目 `products.csv` 格式，处理后的数据放入 `processed_data/`，不在本目录改写。
