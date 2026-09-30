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
    │   ├── model_failures.csv
    │   └── images/
    ├── <类别2>/
    │   ├── products.csv
    │   └── images/
    ├── unprocessed_samples.csv
    ├── failed_images/
    ├── model_audit.jsonl
    ├── dataset_summary.csv
    └── cleaning_report.json

## 字段

输出 products.csv 保留原 products.csv 的字段，并增加 type 字段；清洗输出不保留输入中的 is_readed。分类范围不写死：默认自动读取输入目录下所有包含 products.csv 的类别文件夹，也可以用 --categories 指定；没有类别时会直接报错，不使用固定类别兜底。

`cleaning_report.json` 是累积报告：顶层的 `input_rows`、`accepted_rows`、`review_rows`、`excluded_rows` 和 `pending_rows` 表示当前输出目录的总量，`runs` 数组按运行批次追加本次处理数量和类别统计。使用 `--append` 时保留历史批次；使用 `--clean-output` 时删除旧输出并从空报告重新开始。旧版没有 `runs` 字段的报告会在下一次运行时自动迁移为第一条历史记录。

`dataset_summary.csv` 在正常完成和 Ctrl+C 中断时都会写入检查点。`pending_count` 表示尚未完成模型处理的记录；强制结束进程或关闭终端导致 Python 进程没有机会执行清理代码时，无法保证生成新的检查点。

- product_type：模型根据当前数据集类别识别的大类；
- type：图片识别的细分类；
- color：识别并规范后的颜色，无法确认时留空；
- material：识别并规范后的材质，无法确认时留空；
- description：商品大类、细分类、颜色和材质的模板描述；
- is_readed：输入 processed_data 中的模型成功处理标记。模型成功返回并完成字段解析后，无论结果是通过、待复核还是排除，源 CSV 对应行都会写为 true；图片缺失、接口失败或解析失败时保持 false。该字段不会写入清洗输出 CSV。

不会生成 tpye 或其他重复字段。

## 环境

复制 .env.example 为 .env，填写中转站 API 密钥。 .env 已被 Git 忽略，不应提交。
脚本只使用 Python 标准库，建议使用 Python 3.10 或更高版本。

默认配置：

- 接口：OpenAI 兼容 chat completions 接口；
- 模型：gpt6luna；
- 并发：4；
- 图片路径：仓库根目录相对路径。

`.env` 中可调整以下运行参数：

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `REQUEST_TIMEOUT` | `120` | 单次接口请求的超时时间（秒）；每次重试都会重新计时 |
| `MAX_RETRIES` | `3` | 单条记录接口失败后的重试次数；加上第一次调用，最多调用 4 次 |
| `MAX_WORKERS` | `4` | 并发处理记录数 |
| `IMAGE_DETAIL` | `high` | 发给视觉接口的图片细节级别 |

`MAX_RETRIES` 适用于网络错误、HTTP 错误、超时、返回 JSON 无法解析等接口调用失败。它是单条记录的一轮调用内重试次数，不是整个数据集的重跑次数。

## 使用

在仓库根目录执行：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py

也可以直接指定某一个类别目录，脚本会自动把目录名作为类别，不需要再写 --categories：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --input-dir data/processed_data/包

例如只处理“手机壳”这一类：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py `
      --input-dir data/processed_data/手机壳 `
      --output-dir data/processed_data_cleaning `
      --workers 4 `
      --image-detail high

该命令读取 `data/processed_data/手机壳/products.csv`，输出到：

    data/processed_data_cleaning/手机壳/products.csv
    data/processed_data_cleaning/手机壳/model_failures.csv
    data/processed_data_cleaning/手机壳/images/
    data/processed_data_cleaning/unprocessed_samples.csv
    data/processed_data_cleaning/failed_images/
    data/processed_data_cleaning/model_audit.jsonl

模型成功返回并完成字段解析后，源文件 `data/processed_data/手机壳/products.csv` 中对应行的 `is_readed` 才会更新为 `true`；清洗输出 CSV 不保留 `is_readed`。接口、图片或解析失败时保持 `false`。
处理结果采用流式写入：每完成一条记录就立即更新对应类别的 `products.csv` 并复制成功图片到该类别的 `images/`；模型正常返回但规则未通过的记录立即写入统一的 `unprocessed_samples.csv`，并将能找到的图片复制到 `failed_images/`；接口、解析或图片失败的记录不写入 `unprocessed_samples.csv`，也不复制到 `failed_images/`，只写入失败队列等待重试。模型调用失败的记录写入源类别目录下的 `model_failures.csv`，包含失败原因、失败次数和最后失败时间；成功重试后会从该文件移除。CSV 中的 `local_image_path` 指向清洗输出中的图片或源图片路径。

如果清洗输出目录已有结果，需要保留旧结果并继续追加：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py `
      --input-dir data/processed_data/手机壳 `
      --output-dir data/processed_data_cleaning `
      --append `
      --workers 4

指定其他数据集的类别（留空时自动发现）：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --input-dir data/other_processed --categories "服装,家具,食品"

提高并发时：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --append --workers 20 --image-detail low

中断后继续，或重试上一次接口失败的记录：

如果输出目录已经存在，必须明确使用 `--append`（推荐用于续跑）：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py `
      --input-dir data/processed_data/手机壳 `
      --output-dir data/processed_data_cleaning `
      --append `
      --workers 20 `
      --image-detail low

追加新数据并保留已有清洗结果：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --append --workers 20 --image-detail low

清空已有清洗输出并重新生成：

    py -3 scripts/attribute_cleaning/run_gpt6luna_cleaning.py --clean-output

`--clean-output` 只清空清洗输出目录，不会把输入 CSV 的 `is_readed` 自动改回 `false`。如果目标是让模型重新调用全部记录，应先重置输入 CSV 中对应行的 `is_readed`，再执行该命令；如果只是接着处理中断或失败记录，使用上面的 `--append` 命令。

是否调用模型只看输入 CSV 的 `is_readed`：`false` 就调用，`true` 就跳过。`model_audit.jsonl` 只保存模型结果和错误记录，不参与是否调用模型的判断。

接口、超时或解析失败时，记录保持 `is_readed=false`，并写入源类别目录下的 `model_failures.csv`。文件中的 `attempt_count` 会累计失败次数，下一次运行会自动再次调用模型；不需要额外的 `--retry-failed` 参数。模型成功返回后，无论结果是 `accepted`、`review` 还是 `excluded`，都会把源记录改为 `is_readed=true`，并从失败队列中移除。

失败重试和规则不通过要区分：接口/解析/图片失败不写入 `unprocessed_samples.csv`，也不复制到 `failed_images/`，只保存在 `model_failures.csv` 中等待重试；模型正常返回但规则判定为 `review` 或 `excluded` 时，才写入 `unprocessed_samples.csv` 并把能找到的图片复制到 `failed_images/`，供人工复核，这类记录不会自动再次调用模型。接口错误仍会写入 `model_audit.jsonl` 和 `model_failures.csv`，但不会进入人工复核文件。

`--append` 会保留已有类别 CSV、失败队列、未处理记录和报告历史，并按 `item_id` 增量合并；输出目录已有内容时，常规续跑应使用它。`--force` 只用于明确允许在已有输出目录上运行，模型是否调用仍由输入 CSV 的 `is_readed` 决定。`--clean-output` 会删除清洗输出后重新写出，但不会修改输入 CSV 的 `is_readed`；如果要让模型重新处理已经标记为 `true` 的记录，必须先把对应输入 CSV 的 `is_readed` 改回 `false`。输出目录已有内容时，必须明确选择 `--append`、`--force` 或 `--clean-output`。

模型审计先写入并 flush，再写入结果 CSV；程序收到 Ctrl+C 时会保存检查点，已经处理并落盘的记录会保留，下一次使用 `--append` 继续。直接关闭进程或强制结束 Python 时无法保证最后一批任务有检查点。

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
6. 通过校验的记录立即写入对应类别的 `products.csv`，图片复制到该类别 `images/`；模型正常返回但未通过规则的记录（待复核、排除）立即写入统一的 `unprocessed_samples.csv`，能找到的图片复制到 `failed_images/`。图片缺失、接口失败和解析失败不写入 `unprocessed_samples.csv`，只写入源类别目录的 `model_failures.csv`，不复制到 `failed_images/`，用于下一次重试；模型成功后从该失败队列移除。
7. `description` 按以下模板重新生成：

       商品大类：{product_type}；细分类：{type}；颜色：{color}；材质：{material}

8. 输入 CSV 中的 `is_readed=true` 表示模型已经成功处理过该记录，脚本会跳过模型调用；`is_readed=false` 的记录每次运行都会调用模型。模型成功返回后，无论结果是接受、待复核还是排除，源 `processed_data` CSV 对应行才更新为 `true`；图片缺失、接口失败和解析失败保持 `false`。清洗输出 CSV 不保留 `is_readed`，模型结果和错误记录保存在 `model_audit.jsonl`，其中接口失败记录同时进入 `model_failures.csv`；`unprocessed_samples.csv` 只保存模型正常返回但未通过规则的记录。

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

