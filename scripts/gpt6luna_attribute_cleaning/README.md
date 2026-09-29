# GPT6Luna 商品属性识别与清洗

本目录是一次独立的数据处理任务，读取仓库中的 data/processed_data/*/products.csv，调用 OpenAI 兼容接口识别商品图片，并同步清洗/补充：

- product_type：商品大类，仅接受 包、水杯、鞋；
- type：模型识别出的细分类；
- tpye：type 的同值兼容列，按需求保留该拼写；
- color：图片识别出的颜色，无法确认时留空；
- material：图片识别出的材质，无法确认时留空；
- description：按“商品大类：{product_type}；细分类：{type}；颜色：{color}；材质：{material}”生成。

脚本不会修改当前的 data/processed_data。默认输出到 data/processed_data_gpt6luna，包括各大类的 products.csv、review_candidates.csv、excluded_samples.csv、model_audit.jsonl、dataset_summary.csv 和 README.md。

## 环境

复制本目录的 .env.example 为 .env，填写中转站密钥。 .env 已被 Git 忽略，不应提交。默认模型名为 gpt6luna，默认接口为 https://ai-pixel.online/v1/chat/completions。脚本只使用 Python 标准库，建议 Python 3.10 或更高版本。

## 运行

在仓库根目录执行：

    python scripts/gpt6luna_attribute_cleaning/run_gpt6luna_cleaning.py

常用参数：

    python scripts/gpt6luna_attribute_cleaning/run_gpt6luna_cleaning.py --workers 4 --min-confidence 0.72 --image-detail high --output-dir data/processed_data_gpt6luna

重复运行时会读取 output 目录中的 model_audit.jsonl 并跳过已经完成的记录；需要重新识别时使用 --force。脚本只会重建候选输出目录，不会覆盖正式数据目录。
