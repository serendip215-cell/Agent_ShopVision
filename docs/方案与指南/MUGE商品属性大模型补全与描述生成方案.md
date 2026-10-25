# MUGE 商品属性大模型补全与描述生成方案

## 1. 文档目的

当前 MUGE 正式处理数据已经按三个大类整理：

```text
data/processed_data/
├── 包/
├── 水杯/
└── 鞋/
```

每个类别的 `products.csv` 已经包含图片路径和基础商品字段，但以下字段仍需要补充或完善：

- `description`：商品的中文事实描述；
- `color`：商品主色或可确认的颜色；
- `material`：能够从标题或图片可靠确认的材质。

本方案使用本地部署的 `qwen3-vl:4b` 读取商品标题和图片，生成候选字段，再经过程序校验和人工抽查后进入正式数据。大模型生成的内容先视为草稿，不能直接覆盖原始处理结果。

## 2. 目标和边界

### 2.1 目标

1. 为每条商品记录生成简洁、事实性的中文描述；
2. 从标题和图片中提取颜色；
3. 仅在证据充分时填写材质；
4. 保存模型原始输出、置信度和审核状态，保证结果可追溯；
5. 保留原始字段和图片路径，支持失败重试和重复运行。

### 2.2 边界

- 不让模型修改 `item_id`、`product_type` 和 `local_image_path`；
- 不根据图片臆测价格、品牌、尺寸、功能或防水等属性；
- 不能从图片可靠判断材质时，`material` 保持空字符串；
- 颜色不清楚或图片存在明显光照偏差时，`color` 保持空字符串并进入人工复核；
- 模型输出不能替代人工事实审核；
- 当前不训练 Qwen3-VL，只使用它进行本地推理和字段补全。

## 3. 输入和输出

### 3.1 输入

输入文件为类别目录中的：

```text
data/processed_data/包/products.csv
data/processed_data/水杯/products.csv
data/processed_data/鞋/products.csv
```

图片路径由 CSV 的 `local_image_path` 指定，例如：

```text
data/processed_data/水杯/images/741.jpg
```

程序从项目根目录解析相对路径，不使用任何个人电脑绝对路径。

### 3.2 草稿输出

建议将模型结果写入单独目录，避免覆盖当前已通过检查的 `products.csv`：

```text
data/enriched_data/
├── 包/
│   ├── products_llm_draft.csv
│   └── attribute_enrichment_audit.jsonl
├── 水杯/
└── 鞋/
```

`products_llm_draft.csv` 保留统一的 11 个字段：

```text
item_id
product_type
item_name
description
brand
color
material
local_image_path
image_status
image_height
image_width
```

`attribute_enrichment_audit.jsonl` 每行保存一次模型处理记录，建议字段如下：

```json
{
  "item_id": "muge_741",
  "model": "qwen3-vl:4b",
  "input_image": "data/processed_data/水杯/images/741.jpg",
  "raw_output": "{...}",
  "confidence": {
    "description": 0.91,
    "color": 0.88,
    "material": 0.42
  },
  "needs_review": true,
  "review_status": "pending"
}
```

审核通过后，再将草稿复制为正式版本，例如：

```text
data/processed_data/水杯/products.csv
```

原始 CSV 应先备份，不能让一次模型运行直接覆盖全部数据。

## 4. 本地模型调用

Windows 上使用 Ollama 的接口：

```text
URL: http://localhost:11434/api/chat
模型: qwen3-vl:4b
API Key: 不需要
```

调用前确认模型服务已经启动：

```powershell
curl.exe http://localhost:11434/api/tags
```

请求中需要把图片读取为 Base64，并放入 `images` 数组。接口结构示例：

```json
{
  "model": "qwen3-vl:4b",
  "stream": false,
  "format": "json",
  "messages": [
    {
      "role": "user",
      "content": "请按指定 JSON 格式分析商品。",
      "images": ["BASE64_IMAGE_DATA"]
    }
  ]
}
```

## 5. 提示词规范

每条请求都要同时提供商品标题和商品图片。推荐使用以下规则：

```text
你是电商商品数据清洗助手。请根据商品标题和商品图片，补全 description、color、material。

要求：
1. 只返回 JSON，不要 Markdown，不要解释过程；
2. product_type 由程序提供，不能修改；
3. description 使用中文，写 20～80 字的客观描述，只写标题和图片能支持的事实；
4. color 只填写图片中能确认的主色，可填写“黑色”“白色”“红色+黑色”等；无法确认时返回空字符串；
5. material 只有在标题明确说明或图片具有明显材质证据时填写，否则返回空字符串；
6. 不要编造价格、品牌、尺寸、防水、耐磨、功能和使用效果；
7. 具体款式、颜色、材质、场景和功能特点写入 description，不改变大类 product_type；
8. 对不确定结果设置 needs_review=true。

严格返回：
{
  "description": "",
  "color": "",
  "material": "",
  "confidence": {
    "description": 0.0,
    "color": 0.0,
    "material": 0.0
  },
  "needs_review": false
}
```

程序应把商品的 `item_name` 放在提示词文本中，并将图片作为视觉输入。不要把整张 CSV 作为提示词发送给模型。

## 6. 数据处理流程

```text
读取某个 product_type 的 products.csv
        ↓
解析 local_image_path，检查图片存在且可读取
        ↓
读取 item_name 和商品图片
        ↓
调用 qwen3-vl:4b
        ↓
解析 JSON，检查字段类型和允许值
        ↓
保存 products_llm_draft.csv
        ↓
保存 attribute_enrichment_audit.jsonl
        ↓
低置信度/异常记录进入人工复核
        ↓
复核通过后生成正式 products.csv
```

推荐按类别分批处理，每批 50～100 条，避免一次失败导致整批结果丢失。处理脚本应支持：

- `--input-file`：指定一个类别的 CSV；
- `--output-file`：指定草稿 CSV；
- `--audit-file`：指定 JSONL 审计文件；
- `--model`：默认为 `qwen3-vl:4b`；
- `--resume`：跳过审计文件中已经成功处理的 `item_id`；
- `--max-retries`：模型请求失败时重试；
- `--dry-run`：只处理前几条进行格式验证。

## 7. 输出校验规则

模型返回结果后，程序必须先校验，再写入 CSV：

1. 返回内容必须能解析为 JSON；
2. `description`、`color`、`material` 必须是字符串；
3. `confidence` 必须是 0 到 1 之间的数字；
4. `local_image_path`、`item_id`、`product_type` 必须保持原值；
5. `image_status` 不是 `ok` 时，不提交该条记录；
6. `material` 置信度低于 0.75 时置空并标记复核；
7. `color` 置信度低于 0.75 时置空并标记复核；
8. 描述包含价格、绝对化宣传或输入中没有的功能时标记复核；
9. 任何解析失败都写入审计文件，不覆盖旧结果。

字段检查仍使用：

```bash
python scripts/check_product_fields.py \
  --input-file data/enriched_data/水杯/products_llm_draft.csv \
  --report data/enriched_data/水杯/field_check_report.json
```

## 8. 人工复核和评估

第一次运行建议每个类别随机抽查 50 条，重点检查：

- 描述是否确实对应图片和标题；
- 颜色是否受到背景或光照干扰；
- 材质是否属于视觉猜测；
- 是否出现“防水、耐磨、真皮”等没有证据的词；
- 三个大类是否仍然是“包、鞋、水杯”；
- 图片路径是否仍然有效。

建议记录以下统计：

```text
总记录数
JSON 解析成功率
description 非空率
color 非空率
material 非空率
低置信度比例
人工复核通过率
属性事实错误率
```

`material` 的非空率不应作为单独的质量目标。对不确定材质保持为空，比生成一个错误材质更安全。

## 9. 与训练数据的关系

大模型字段补全属于数据预处理和推理阶段，不等同于模型训练。完成审核后，这些数据可以用于：

- 商品文本检索；
- 图片和文字属性匹配；
- 商品推荐 Agent 的本地知识库；
- 构造图片属性识别和商品描述生成的对话样本；
- 后续 LoRA 微调的监督数据。

只有人工确认或规则确认的字段，才应该作为 LoRA 训练标签。未经审核的模型草稿只能用于候选生成，不能直接作为高质量训练标签。

## 10. 当前执行顺序

1. 保留 `data/processed_data/` 中已经检查通过的原始字段表；
2. 实现 Ollama 批处理脚本；
3. 先用 `--dry-run` 处理每类 3～5 条；
4. 检查 JSON 格式和相对图片路径；
5. 分批处理包、水杯、鞋；
6. 抽查并修改错误结果；
7. 生成正式增强版 `products.csv`；
8. 再构造 `dialogues.jsonl` 和训练/验证/测试划分。
