# 电商商品多模态推荐与上架 Agent 开发文档

## 1. 项目概述

### 1.1 项目名称

基于本地视觉语言模型的电商商品多模态推荐与上架 Agent。

### 1.2 项目目标

构建一个能够读取本地商品图片、商品文字和结构化元数据的 Agent。用户通过自然语言或上传图片提出需求后，系统完成商品属性识别、候选商品检索、商品推荐、标题与描述生成，并将结果导出为 JSON/CSV。

本项目对应课程中的连续实验：实验 1 负责数据集采集与预处理；实验 2 负责模型设计和训练；实验 3 负责量化、剪枝和推理优化；实验 4 负责前后端；实验 5 负责大模型 Agent 部署、工具调用和端到端评测。

### 1.3 非目标

- 不从零训练视觉语言大模型；
- 不直接修改 Qwen-VL 等基础模型的网络结构；
- 第一版不接入真实电商平台下单、支付和库存写入接口；
- 不把模型生成结果视为商品事实，关键属性必须经过元数据校验。

## 2. 用户场景与功能范围

### 2.1 目标用户

- 商品运营人员：批量生成和检查商品上架信息；
- 普通用户：根据文字或图片寻找相似商品；
- 项目评测人员：检查 Agent 的识别、检索、工具调用和回答质量。

### 2.2 核心功能

1. **商品图片理解**：识别类别、颜色、材质、款式和可见文字。
2. **商品信息抽取**：读取本地商品 CSV/JSON 元数据，并统一字段。
3. **文字检索推荐**：根据类别、颜色、价格、材质和使用场景筛选商品。
4. **图片相似推荐**：根据上传图片检索相似商品。
5. **标题与描述生成**：生成指定长度、风格和字段格式的上架信息。
6. **结果校验**：检查缺失字段、标题长度、属性冲突和敏感词。
7. **多轮修改**：处理“突出通勤”“标题不超过 30 字”等后续要求。
8. **结果导出**：导出 JSON、CSV、Markdown；展示商品图片和推荐理由。

### 2.3 示例对话

```text
用户：请根据这张图片推荐黑色、防水、适合通勤的双肩包，预算 200 元以内。
Agent：先分析图片属性，再查询本地商品库，返回候选商品、价格、匹配属性和推荐理由。

用户：把第一件商品生成 30 字以内的上架标题，并突出轻便。
Agent：调用标题生成与长度校验工具，返回合规标题。
```

## 3. 总体架构

```text
React 前端
  ├─ 上传图片 / 输入需求 / 展示结果
  ↓
FastAPI 后端
  ├─ 会话与任务管理
  ├─ Agent 编排器
  ├─ 本地商品数据库与向量检索
  ├─ OCR、图像分析、标题生成、敏感词检查工具
  └─ 本地视觉语言模型推理服务
  ↓
商品图片 + 商品元数据 + 文本描述 + 对话轨迹
```

### 3.1 模型与工具分工

- **视觉语言模型**：Qwen2.5-VL-3B-Instruct 4-bit，负责图片理解和自然语言生成；硬件不足时先使用 Qwen2-VL-2B 或云端 API 做功能验证。
- **OCR**：PaddleOCR 或其他本地 OCR，负责图片中文字识别。
- **结构化检索**：SQLite/CSV，负责价格、类别、颜色、材质等精确过滤。
- **向量检索**：FAISS 或 Chroma，负责图片/文本相似商品召回。
- **Agent 编排**：先用 Python 自定义状态机；任务复杂后可迁移到 LangGraph。
- **后端**：FastAPI。
- **前端**：React。

模型不会自动读取本地文件。Agent 必须通过工具读取数据库、图片路径和向量检索结果，再把结果放入模型上下文。

## 4. 数据方案（实验 1）

### 4.1 数据来源

首选 Amazon Berkeley Objects（ABO）小规模子集，包含商品图片、商品标题、类别和元数据。课程项目只下载 1,000–5,000 个商品，并在 README 中记录许可证、下载日期和来源。也可加入自己拍摄并人工标注的商品图片作为中文测试集。

### 4.2 数据字段

`products.csv`：

```csv
product_id,image_path,title,description,category,color,material,price,tags,source
```

`dialogues.jsonl`：

```json
{
  "id": "dlg_0001",
  "image": "images/001.jpg",
  "metadata": {"category": "双肩包", "color": "黑色", "material": "尼龙"},
  "messages": [
    {"role": "user", "content": "生成30字以内的通勤标题"},
    {"role": "assistant", "content": "黑色轻便防水通勤双肩包"}
  ]
}
```

### 4.3 数据预处理

#### 图片

- 检查损坏文件和无法读取的图片；
- 统一 JPG/PNG 格式，按比例缩放；
- 生成 SHA-256 或感知哈希，去除重复图片；
- 检查图片与 `product_id` 的对应关系；
- 删除不属于目标品类的图片；
- 记录处理前后的图片数量、尺寸和损坏数量。

#### 文字与元数据

- 统一字段名和类别名称；
- 清除 HTML、重复空格和无意义特殊字符；
- 检查价格、颜色、材质和标题缺失；
- 检查标题与图片/元数据是否冲突；
- 清理敏感词和未经证实的夸大表述；
- 将商品属性整理为 JSON，保证字段类型一致。

#### 数据划分

按商品 ID 划分训练集、验证集和测试集，比例为 8:1:1。相同商品的不同图片不能跨集合，以避免数据泄漏。

### 4.4 实验 1 交付物

```text
data/
└── raw_data/
    ├── Amazon_data/
    │   ├── products.csv
    │   ├── images/
    │   └── image_quality_report.csv
    └── MUGE_data/
        ├── products.csv
        ├── images/
        └── image_quality_report.csv
```

每个数据集分别保存商品信息、图片和图片质量报告，暂不合并。各数据集的说明集中在自己的 `README.md` 中；后续处理后的统一数据放入 `data/processed_data/`，不按商品类别拆分目录。

## 5. 模型设计与训练（实验 2）

### 5.1 训练目标

训练的是面向商品任务的视觉语言/工具调用适配能力，不是从零训练大模型。基础模型保持不变，使用 LoRA 对商品对话和工具调用样本做参数高效微调。

### 5.2 训练样本类型

- 图片属性识别：图片 → 类别、颜色、材质；
- 商品标题生成：属性和图片 → 规定长度的标题；
- 描述生成：属性和图片 → 结构化商品描述；
- 推荐解释：用户偏好 + 检索结果 → 推荐理由；
- 工具调用：用户需求 → `search_products`、`analyze_image` 等工具及参数；
- 错误恢复：工具报错或字段缺失 → 重新调用、澄清或明确告知用户。

### 5.3 训练输出

- LoRA adapter；
- 训练配置和版本；
- 基础模型与 adapter 的对应关系；
- 训练/验证损失曲线；
- 数据—模型关联表；
- 微调前后对比报告。

### 5.4 评测指标

- 属性识别准确率/F1；
- 商品检索 Recall@K、MRR；
- 标题字段完整率和长度合规率；
- 推荐结果的属性匹配率；
- 工具调用成功率和参数准确率；
- 多轮任务成功率；
- 人工评价：相关性、事实一致性、可读性。

## 6. 算法优化（实验 3）

对比以下方案：

1. FP16/BF16 基线；
2. 4-bit 量化模型；
3. 可选的剪枝或 KV cache 优化。

记录模型大小、启动时间、单次响应时间、峰值内存、显存占用和上述任务指标。优化目标是在可接受的质量下降范围内降低资源占用。

## 7. 前后端开发（实验 4）

### 7.1 后端 API

```text
POST /api/chat                 多轮文字/图片对话
POST /api/products/search      商品检索
POST /api/products/analyze     图片属性分析
POST /api/products/generate    生成标题和描述
POST /api/products/export      导出 JSON/CSV
GET  /api/health               健康检查
```

### 7.2 Agent 工具接口

```python
analyze_image(image_path) -> ProductAttributes
search_products(filters, query, top_k=5) -> list[Product]
read_metadata(product_id) -> ProductMetadata
generate_listing(product, constraints) -> ListingDraft
validate_listing(draft) -> ValidationReport
export_listing(draft, format) -> FilePath
```

每个工具都要返回结构化 JSON，并记录输入、输出、耗时和错误，便于调试与评测。

### 7.3 前端页面

- 图片上传区；
- 商品属性和检索条件表单；
- 对话区；
- 推荐商品卡片；
- 标题/描述编辑区；
- 数据来源和校验结果展示；
- 导出按钮。

## 8. Agent 部署与评测（实验 5）

### 8.1 典型工作流

```text
接收用户请求
→ 判断是否需要图片分析
→ 读取本地元数据或检索商品库
→ 调用视觉/检索/生成工具
→ 校验属性、长度和敏感词
→ 返回推荐或上架信息
→ 保存可复现的工具调用轨迹
```

### 8.2 端到端测试集

至少准备以下任务：

- 文字条件推荐；
- 图片相似商品推荐；
- 图片与元数据冲突；
- 缺少价格或材质；
- 标题长度限制；
- 多轮修改；
- 商品检索为空；
- 工具调用失败；
- 批量生成并导出。

### 8.3 端到端报告

报告应包含成功率、平均响应时间、工具调用准确率、推荐 Recall@K、标题合规率、错误类型、显存/内存使用和人工评价。展示微调前后、量化前后的对比。

## 9. 硬件与软件

课程材料给出的基础配置为 CPU 至少 4 核、内存至少 8GB，可满足基础数据处理、轻量训练和前后端开发；推荐配置为 8 核 CPU、16GB 内存和至少 4GB 显存。没有独显时先使用小型量化模型或云端 GPU 完成 LoRA，再下载 adapter 做本地推理。

软件建议：Python 3.12、Anaconda、Docker 24.0+、PyTorch、Transformers、Pillow/OpenCV、PaddleOCR、pandas、FAISS/Chroma、FastAPI、React。

## 10. 项目目录

```text
ecommerce-agent/
├── data/
│   ├── raw_data/
│   │   ├── Amazon_data/
│   │   │   ├── products.csv
│   │   │   ├── images/
│   │   │   └── image_quality_report.csv
│   │   └── MUGE_data/
│   │       ├── products.csv
│   │       ├── images/
│   │       └── image_quality_report.csv
│   └── processed_data/       # 后续统一处理结果，扁平存放
├── models/
│   ├── base_model/       # 不提交大模型权重
│   └── lora_adapter/
├── agent/
│   ├── orchestrator.py
│   ├── prompts.py
│   └── tools/
├── backend/
├── frontend/
├── training/
├── evaluation/
├── configs/
├── scripts/
├── README.md
└── requirements.txt
```

## 11. 里程碑

| 周期 | 目标 | 验收标准 |
|---|---|---|
| 第 1 周 | 数据集下载与预处理 | 图片、文字、元数据一一对应，README 完成 |
| 第 2 周 | 商品检索和图片分析 | 能返回 Top-5 商品及属性 |
| 第 3 周 | 对话和工具调用 | 能完成推荐、生成、校验、导出流程 |
| 第 4 周 | LoRA 微调和量化 | 有微调前后、量化前后指标 |
| 第 5 周 | 前后端集成 | 页面可上传图片并完成对话 |
| 第 6 周 | 端到端评测 | 测试报告、演示和最终文档齐全 |

## 12. 小组分工

按课程建议的 5–6 人分工：

- 数据处理组 1 人：数据采集、清洗、标准化、README；
- 模型组 2 人：模型设计、LoRA、量化和指标；
- 开发组 2 人：React、FastAPI、Agent 工具与部署；
- 组长 1 人：流程、版本、实验记录、汇报和合规检查。

## 13. 风险与验收标准

### 主要风险

- 图片和商品文本错配；
- 模型臆造图片中不存在的属性；
- 商品数据许可证不适合当前用途；
- 8GB 内存运行多模态模型过慢；
- 推荐结果只相关但缺少可解释依据；
- 训练集和测试集存在同商品泄漏。

### 最终验收

- 能上传图片并用中文对话；
- 能从本地商品库检索商品；
- 能返回图片、属性、价格和推荐理由；
- 能生成并校验标题/描述；
- 能导出 JSON/CSV；
- 关键结果能追溯到本地数据记录；
- 有数据 README、Data Card、模型关联表和端到端测试报告。


# 详细实施补充

## 14. 产品任务定义

为了避免项目退化为单纯的图片识别器，将系统定义为四类可验证业务任务。

### 14.1 文字条件商品检索

输入“找黑色、防水、适合通勤、200元以内的双肩包”。

处理流程：

1. 解析类别、颜色、材质、功能、场景和价格上限；
2. 将自然语言条件映射为结构化过滤条件；
3. 使用SQLite或CSV完成精确过滤；
4. 使用BM25或向量检索补充同义词和语义结果；
5. 按属性匹配、价格差和相似度排序；
6. 返回Top-K商品及匹配理由。

### 14.2 图片条件商品检索

1. 检查图片质量；
2. 调用视觉语言模型提取类别、颜色、材质和风格；
3. 使用CLIP或其他图像编码器生成图片向量；
4. 使用FAISS召回相似商品；
5. 使用用户文字条件进行过滤和重排；
6. 展示候选商品与原图的相似和差异。

### 14.3 商品上架信息生成

1. 读取商品真实元数据；
2. 筛选图片中能确认的属性；
3. 按平台模板生成标题和描述；
4. 校验字数、必填字段、敏感词和属性一致性；
5. 不合格时自动重写；
6. 展示生成内容的事实依据。

### 14.4 批量上架审核

1. 创建批量任务；
2. 并行分析多件商品；
3. 生成标题和描述草稿；
4. 检查异常和缺失字段；
5. 允许逐条修改或批量确认；
6. 导出上架CSV和异常报告。

## 15. 数据集详细设计

### 15.1 商品主表字段

    product_id
    image_path
    image_paths
    title
    description
    category_lv1
    category_lv2
    brand
    color
    material
    style
    usage_scene
    feature_tags
    price
    stock_status
    source
    license
    quality_status

### 15.2 商品属性记录

    {
      "product_id": "p_000001",
      "attributes": {
        "category": "双肩包",
        "color": ["黑色"],
        "material": ["尼龙"],
        "style": ["简约", "通勤"],
        "features": ["轻便"]
      },
      "evidence": {
        "category": "metadata",
        "color": "image_and_metadata",
        "material": "metadata",
        "features": "description"
      },
      "confidence": {
        "category": 0.99,
        "color": 0.91,
        "material": 0.88,
        "features": 0.76
      }
    }

### 15.3 工具调用对话数据

每条样本包含用户需求、工具调用、工具结果和最终回答：

    用户：找一款200元以内的黑色通勤双肩包。
    Agent工具调用：
    search_products({
      category: "双肩包",
      color: "黑色",
      usage_scene: "通勤",
      max_price: 200,
      top_k: 5
    })
    工具返回：
    [{"product_id": "p_0001", "price": 159, "match_score": 0.92}]
    Agent回答：
    为你找到一款符合价格、颜色和场景要求的商品。

### 15.4 异常和负样本

加入：

- 图片和元数据不匹配；
- 价格、材质或类别缺失；
- 图片中无法确认某属性；
- 用户要求低于所有候选商品价格；
- 标题超过字数限制；
- 生成内容包含夸大宣传；
- 检索结果为空；
- 工具超时；
- 同一商品重复出现；
- 商品图片与文字描述冲突。

## 16. 实验1：数据采集与预处理细则

### 16.1 推荐数据规模

先选择3个品类，降低标注难度：

    双肩包
    运动鞋
    水杯

每类准备300—1000个商品。每件商品至少有一张图片、标题、价格和类别，尽量补充颜色、材质、场景和功能标签。

### 16.2 图片流水线

    scan_images
        ↓
    check_readability
        ↓
    convert_format
        ↓
    resize_and_normalize
        ↓
    perceptual_hash_dedup
        ↓
    quality_score
        ↓
    save_processed_images

记录：

- 图片总数；
- 损坏图片数；
- 重复图片数；
- 分辨率不足图片数；
- 模糊图片数；
- 缺少元数据图片数。

### 16.3 文本和元数据流水线

    remove_html
        ↓
    normalize_whitespace
        ↓
    normalize_price
        ↓
    normalize_category
        ↓
    remove_sensitive_words
        ↓
    check_attribute_conflict
        ↓
    save_clean_metadata

### 16.4 数据增强

图片增强：

- 轻微旋转；
- 随机裁剪；
- 亮度和对比度变化；
- 背景扰动；
- 不改变商品语义的水平翻转。

文本增强：

- 同义表达改写；
- 价格条件改写；
- 使用场景改写；
- 多轮追问；
- 否定和对比表达。

增强数据保留is_augmented、augmentation_method和source_id。

## 17. 实验2：模型设计与LoRA训练细则

### 17.1 模型层级

1. 感知层：预训练视觉语言模型和图像编码器；
2. 任务层：LoRA学习商品属性、推荐、生成和工具调用；
3. 业务层：检索、校验和Agent状态机。

不从零训练视觉语言模型，LoRA只训练任务适配参数。

### 17.2 训练样本比例

    属性识别：25%
    标题生成：20%
    描述生成：15%
    推荐解释：15%
    工具调用：15%
    异常处理：10%

### 17.3 LoRA训练步骤

1. 固定基础模型和版本；
2. 检查训练样本事实字段；
3. 划分训练集和验证集；
4. 使用4-bit量化加载基础模型；
5. 配置LoRA模块；
6. 训练适配器；
7. 保存日志和配置；
8. 在固定测试集评估；
9. 比较微调前后效果。

建议初始参数：

    lora_r: 8或16
    lora_alpha: 16或32
    lora_dropout: 0.05
    learning_rate: 1e-4
    num_train_epochs: 2或3
    max_seq_length: 2048
    gradient_accumulation_steps: 8或16

### 17.4 事实一致性约束

生成内容只能使用：

- 商品主表字段；
- 置信度足够高的视觉属性；
- 检索工具返回的商品事实；
- 用户明确补充的信息。

不得直接生成未验证品牌、功能、折扣或“全网最低”等宣传。

## 18. 实验3：检索和算法优化

### 18.1 检索方案

文字条件：

    SQLite精确过滤
    + BM25或TF-IDF文本检索

图片条件：

    CLIP图像向量
    + FAISS余弦相似度

混合排序：

    final_score =
      0.35 * text_score
      + 0.30 * image_score
      + 0.20 * attribute_match
      + 0.10 * price_match
      + 0.05 * quality_score

权重使用验证集调整并记录。

### 18.2 优化内容

- FP16和4-bit量化；
- 动态批处理；
- KV Cache；
- 图片缩放策略；
- 重复图片结果缓存；
- 向量索引优化；
- ONNX或TorchScript导出。

至少比较模型大小、启动时间、平均延迟、峰值显存、Recall@K和属性匹配率。

## 19. Agent工具和状态机

### 19.1 工具接口

    analyze_image(image_path)
    search_products(filters, query, top_k)
    compare_products(product_ids, criteria)
    read_metadata(product_id)
    generate_listing(product_id, constraints)
    validate_listing(product_id, draft)
    create_batch_task(product_ids)
    get_task_status(task_id)
    approve_item(task_id, product_id)
    export_listing(task_id, format)

每个工具返回结构化JSON，并记录输入、输出、耗时、版本和错误。

### 19.2 Agent状态

    CREATED
      ↓
    ANALYZING_IMAGE
      ↓
    SEARCHING_PRODUCTS
      ↓
    GENERATING_DRAFT
      ↓
    VALIDATING_DRAFT
      ↓
    WAITING_USER_CONFIRMATION
      ↓
    APPROVED / NEEDS_REVISION / FAILED
      ↓
    EXPORTED

每次状态变化记录task_id、时间、工具、输入、输出、错误和用户反馈。

## 20. 实验4：前后端细化

### 20.1 React页面

推荐页：

- 用户需求输入；
- 图片上传；
- 可修改的筛选条件；
- 推荐商品卡片；
- 匹配理由；
- 商品对比；
- 加入上架任务。

上架页：

- 商品图片；
- 原始元数据；
- AI标题和描述；
- 字数和敏感词检查；
- 属性证据；
- 修改记录；
- 确认和导出。

批量任务页：

- 任务状态；
- 成功、失败、待确认数量；
- 异常筛选；
- 批量确认；
- 导出报告。

### 20.2 API

    POST /api/chat
    POST /api/products/search
    POST /api/products/analyze
    POST /api/products/generate
    POST /api/products/validate
    POST /api/products/batch
    POST /api/products/export
    GET  /api/tasks/{task_id}
    GET  /api/health

## 21. 实验5：端到端测试

至少准备120条测试任务：

    20条文字条件检索
    20条图片条件检索
    20条标题生成
    15条描述生成
    15条属性冲突
    10条空检索结果
    10条工具报错
    10条多轮修改

每条记录：

    test_id
    input_image
    user_request
    expected_tools
    expected_constraints
    expected_result
    actual_result
    pass
    error_type

## 22. 评价指标

### 22.1 属性识别

    Attribute Accuracy
    Attribute Macro-F1
    Uncertain Attribute Precision
    Hallucination Rate

### 22.2 商品检索

    Recall@1
    Recall@5
    Recall@10
    MRR
    NDCG@K
    Attribute Match Rate
    Price Constraint Pass Rate

### 22.3 上架内容

    Required Field Completeness
    Title Length Pass Rate
    Sensitive Word Pass Rate
    Attribute Consistency Rate
    Human Preference Score

### 22.4 Agent

    Tool Selection Accuracy
    Argument Exact Match
    Invalid Tool Call Rate
    Recovery Success Rate
    Multi-turn Success Rate
    Batch Completion Rate
    Average Response Time

## 23. 失败处理

图片质量不足时要求重新上传；属性无法确认时使用“可能”并提示证据不足；检索为空时询问用户是否放宽价格或去掉非必要条件；工具失败时重试一次并切换备用检索，不得伪造商品结果。

## 24. 合规和数据安全

- 记录数据集来源、许可证和下载时间；
- 不下载超出授权范围的数据；
- 不保存用户未授权的私人图片；
- 导出前去除本地绝对路径；
- 商品品牌、价格和功能必须来自数据源；
- AI生成内容标记为草稿；
- 重要属性展示证据来源；
- 不接入真实下单、支付和库存写入。

## 25. 最终交付清单

1. 原始和处理后数据说明；
2. 数据字典和README；
3. Data Card和许可证记录；
4. 数据清洗、增强和划分脚本；
5. 商品检索模块；
6. 图片分析模块；
7. LoRA训练脚本和adapter；
8. 量化和优化脚本；
9. FastAPI后端；
10. React前端；
11. Agent工具和状态机；
12. API文档；
13. 端到端测试集；
14. 精度、延迟、显存对比报告；
15. 演示视频；
16. 五次实验报告。


