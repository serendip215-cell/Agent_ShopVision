# 商品属性识别与清洗

本目录包含一次可复用的商品图片识别和数据清洗任务。

## 输入与输出

默认输入：

    data/processed_data

默认输出：

    data/processed_data_cleaning

正式数据目录不会被覆盖。输出目录的主要结构与 data/processed_data 一致：

    data/processed_data_cleaning/
    ├── <类别1>/
    │   ├── products.csv
    │   └── images/
    ├── <类别2>/
    │   ├── products.csv
    │   └── images/
    ├── dataset_summary.csv
    ├── cleaning_report.json
    ├── excluded_samples.csv
    ├── review_candidates.csv
    ├── model_audit.jsonl
    └── README.md

## 字段

输出 products.csv 保留原 products.csv 的字段，并增加 type 和 is_cleaned 字段。分类范围不写死：默认自动读取输入目录下所有包含 products.csv 的类别文件夹，也可以用 --categories 指定；没有类别时会直接报错，不使用固定类别兜底。

- product_type：模型根据当前数据集类别识别的大类；
- type：图片识别的细分类；
- color：识别并规范后的颜色，无法确认时留空；
- material：识别并规范后的材质，无法确认时留空；
- description：商品大类、细分类、颜色和材质的模板描述；
- is_cleaned：通过类别和置信度检查为 true，待复核、排除或失败为 false。

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

也可以直接指定某一个类别目录，脚本会自动把目录名作为类别，不需要再写 --categories：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --input-dir data/processed_data/包

指定其他数据集的类别（留空时自动发现）：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --input-dir data/other_processed --categories "服装,家具,食品"

提高并发时：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --workers 20 --image-detail low

中断后继续：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --workers 20 --retry-failed --image-detail low

完成识别后复制图片并更新类别目录中的 products.csv：

    py -3 scripts/attribute_cleaning/copy_output_images.py

默认运行会读取 output 目录中的 model_audit.jsonl，跳过已有结果；retry-failed 只重试接口或解析失败的记录；force 会重新处理全部记录。

## 清洗逻辑

脚本支持两种输入方式：

1. 指定数据集根目录，例如 `data/processed_data`。脚本扫描该目录下所有 `<类别>/products.csv`，并将各类别文件夹名称作为模型的候选大类。
2. 指定单个类别目录，例如 `data/processed_data/包`。脚本检测到目录本身存在 `products.csv` 后，只处理这一类，并自动使用目录名作为候选大类。

每条记录按以下顺序处理：

1. 根据 `local_image_path`、类别目录下的 `images` 目录和 `item_id` 查找图片。
2. 将图片、商品标题、原有颜色、原有材质和描述发送给视觉模型。
3. 模型判断图片主体是否为可售商品，并在当前数据集的候选类别中选择商品大类。
4. 模型补充细分类 `type`、颜色 `color` 和材质 `material`。无法从图片或文字可靠判断的属性留空，不强行猜测。
5. 对商品大类、颜色、材质和置信度进行程序校验。
6. 通过校验的记录写入对应类别的 `products.csv`；不确定的记录写入 `review_candidates.csv`；非商品或不属于候选类别的记录写入 `excluded_samples.csv`。
7. `description` 按以下模板重新生成：

       商品大类：{product_type}；细分类：{type}；颜色：{color}；材质：{material}

8. `is_cleaned=true` 只表示该记录已经通过商品类别和置信度检查；`is_cleaned=false` 表示待复核、排除或处理失败。

分类范围始终来自输入数据集的类别目录或 `--categories` 参数，代码不预设具体商品类别。没有发现任何类别时，脚本会停止并提示检查目录结构。

## 目录要求

标准数据集目录应满足以下任一种形式：

    data/processed_data/
    ├── 包/products.csv
    ├── 水杯/products.csv
    └── 鞋/products.csv

或只处理单个类别：

    data/processed_data/包/
    ├── products.csv
    └── images/

`products.csv` 至少应包含 `item_id`、`item_name`、`local_image_path` 等字段。其他字段会原样保留，脚本会去除重复的 `tpye` 字段，并只保留一个 `type` 字段。

