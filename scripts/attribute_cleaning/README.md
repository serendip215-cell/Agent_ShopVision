# 商品属性识别与清洗

本目录包含一次可复用的商品图片识别和数据清洗任务。

## 输入与输出

默认输入：

    data/processed_data

默认输出：

    data/processed_data_cleaning

正式数据目录不会被覆盖。输出目录的主要结构与 data/processed_data 一致：

    data/processed_data_cleaning/
    ├── 包/
    │   ├── products.csv
    │   └── images/
    ├── 水杯/
    │   ├── products.csv
    │   └── images/
    ├── 鞋/
    │   ├── products.csv
    │   └── images/
    ├── dataset_summary.csv
    ├── cleaning_report.json
    ├── excluded_samples.csv
    ├── review_candidates.csv
    ├── model_audit.jsonl
    └── README.md

## 字段

输出 products.csv 保留原 products.csv 的字段，并增加一个 type 字段：

- product_type：包、水杯或鞋；
- type：图片识别的细分类；
- color：识别并规范后的颜色，无法确认时留空；
- material：识别并规范后的材质，无法确认时留空；
- description：商品大类、细分类、颜色和材质的模板描述。

不会生成 tpye 或其他重复字段。

## 环境

复制 .env.example 为 .env，填写中转站 API 密钥。 .env 已被 Git 忽略，不应提交。
脚本只使用 Python 标准库，建议使用 Python 3.10 或更高版本。

默认配置：

- 接口：OpenAI 兼容 chat completions 接口；
- 模型：gpt6luna；
- 并发：4；
- 图片路径：仓库根目录相对路径。

## 使用

在仓库根目录执行：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py

提高并发时：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --workers 20 --image-detail low

中断后继续：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --workers 20 --retry-failed --image-detail low

完成识别后复制图片并更新类别目录中的 products.csv：

    py -3 scripts/attribute_cleaning/copy_output_images.py

默认运行会读取 output 目录中的 model_audit.jsonl，跳过已有结果；retry-failed 只重试接口或解析失败的记录；force 会重新处理全部记录。

