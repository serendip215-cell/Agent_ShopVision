// AI全栈开发实验一：数据采集与预处理
// 排版基准（逐项核对自 docs/AI全栈开发实验1报告模板 的 Word 渲染结果）：
//   封面：校名/实验名 26pt 粗体（"AI" Times New Roman、"全栈开发实验"黑体）、
//         "题目" 20pt、题目内容 22pt、组号/组员信息/时间 14pt 粗体、组员表 14pt 粗体表头；
//   正文：汉字小四宋体、英文 Times New Roman，行距 20 磅；
//   章标题与"1．需求分析"类小节：14pt 宋体常规；
//   图表中标题和文字字号均为五号（10.5pt）。
// 文献引用使用 refs.bib（全部经 DOI/官网溯源核实），正文 @key 交叉引用。

#set document(title: "AI全栈开发实验一：数据采集与预处理")
#set text(font: ("Times New Roman", "SimSun"), lang: "zh", size: 12pt)
#set par(leading: 11.8pt, spacing: 11.8pt, justify: true, first-line-indent: 2em)
#set figure(supplement: [表])
#show figure.where(kind: image): set figure(supplement: [图])
#show figure.caption: it => align(center, text(size: 10.5pt)[
  #it.supplement #it.counter.display(it.numbering)#h(0.5em)#it.body
])
#show raw: set text(font: ("Consolas", "SimSun"), size: 9pt)

#let h1(body) = {
  v(10pt)
  par(first-line-indent: 0pt, text(size: 14pt, font: ("Times New Roman", "SimSun"))[#body])
  v(4pt)
}
#let h2(body) = {
  v(6pt)
  par(first-line-indent: 0pt, text(size: 12pt, font: ("Times New Roman", "SimSun"))[#body])
  v(2pt)
}
#let t5(body) = {
  set text(size: 10.5pt)
  set par(leading: 5pt, spacing: 5pt, first-line-indent: 0pt)
  body
}
#let fillline(w) = box(width: w, height: 0.85em, stroke: (bottom: 0.5pt))

// ============================== 封面 ==============================
#v(24pt)
#align(center)[#text(size: 26pt, weight: "bold")[西 安 邮 电 大 学]]
#v(40pt)
#align(center)[#text(size: 26pt, weight: "bold", font: ("Times New Roman", "SimHei"))[AI 全栈开发实验]]
#v(50pt)
#align(left)[#h(3em)#text(size: 20pt)[题目：]#text(size: 22pt)[#box(stroke: (bottom: 0.5pt), inset: (x: 2pt, y: 1pt))[#h(1em)数据采集与预处理#h(4em)]]]
#v(70pt)
#align(left)[#h(3em)#text(size: 14pt, weight: "bold")[组#h(2em)号：#fillline(14em)]]
#v(8pt)
#align(left)[#h(3em)#text(size: 14pt, weight: "bold")[组员信息：]]
#v(4pt)
#align(center)[
  #text(size: 14pt, weight: "bold")[
    #table(
      columns: (14em, 10em, 12em),
      align: center + horizon,
      table.header([学号], [姓名], [分工]),
      [#v(0.9em)], [], [],
      [#v(0.9em)], [], [],
      [#v(0.9em)], [], [],
      [#v(0.9em)], [], [],
      [#v(0.9em)], [], [],
    )
  ]
]
#v(10pt)
#align(left)[#h(3em)#text(size: 14pt, weight: "bold")[时#h(2em)间：#fillline(14em)]]

#pagebreak()

// ============================== 一、实验目的 ==============================
#h1[一.#h(0.8em)实验目的]

本实验面向"电商商品多模态推荐与上架 Agent"课题，完成其数据基座建设，具体目的如下：

+ 掌握多源数据（结构化、非结构化、特殊场景）的获取方法：围绕电商商品场景，独立完成结构化商品元数据、非结构化标题/描述文本、商品图像三类数据的采集，理解不同数据源（公开数据集与站点爬取）的特点与获取逻辑；
+ 熟练运用数据清洗技术处理缺失值、异常值、重复值等质量问题，掌握结构化/非结构化数据增强方法，实践"规则质检 + 大模型视觉审核"的自动化数据策展思路；
+ 完成数据集标准化与构建：统一字段规范、按类目组织图文配对数据集并完成文档化，理解数据隐私合规要求，具备基础的数据集评估能力；
+ 初步树立 Data-Centric AI 理念@dcai-manifesto，理解数据质量对 AI 系统性能上限的决定性作用，以数据质量报告的形式量化评估数据集。

// ============================== 二、实验环境 ==============================
#h1[二.#h(0.8em)实验环境]

#h2[软硬件环境]

- 硬件：计算机（8GB 以上内存，支持图像处理，多核 CPU 用于抠图与批量翻译并发）；
- 操作系统：Windows 11（Git Bash / PowerShell），脚本兼容 macOS/Linux；
- 软件：Python 3.12、PyCharm、Git；
- 核心库：pandas（数据处理）、numpy（数值计算）、requests（网络请求）、beautifulsoup4（页面解析）、Pillow/OpenCV（图像处理）、onnxruntime（ISNet 抠图推理@isnet）、deepl（官方翻译 SDK@deepl）、openai 兼容客户端（GPT 视觉模型清洗）；
- 数据源：MUGE 公开商品数据集、Amazon 商品数据集、苏宁易购公开搜索页（合规爬取）；公开数据集获取方式参考 Kaggle@kaggle、UCI@uci 等平台的组织惯例；
- 外部服务：DeepL API@deepl、GPT 视觉大模型 API。

// ============================== 三、实验内容与步骤 ==============================
#h1[三．实验内容与步骤]

本实验内容涵盖三部分内容：

#h2[1.1 多源数据获取：结构化数据获取、非结构化数据获取、特殊场景数据]
#h2[1.2 数据清洗与增强：数据质量问题处理、数据增强方法]
#h2[1.3 数据集建设：数据标准化、数据集构建]

以下按 1．需求分析、2．设计思路、3．代码实现、4. 测试优化四个方面展开。

#h1[1．需求分析]

本课题后续的检索推荐与上架 Agent 均以高质量商品数据为前提。经分析，数据侧需求如下：

+ 多源数据获取需求：需要获取至少 2-3 类模态的数据。本实验获取三类：结构化数据（商品表格元数据：类别、标题、品牌、颜色、材质等字段）、非结构化文本（商品标题与描述）、非结构化图像（商品封面图），并保证图文一一配对（即任务书中的"特殊场景数据"：多模态图文对）。来源覆盖 2 个公开数据集（MUGE、Amazon）与 1 个站点爬取来源（苏宁易购），共 9 个商品大类。
+ 数据清洗与增强需求：原始数据存在图片无法解码、重复采集、标题冗余变体、属性缺失/错误（如颜色材质"未知"）等质量问题，需要系统化处理；并需对商品图像做主体化处理（抠图）、对文本做规范化与补全。
+ 数据集建设需求：三源数据字段异构，必须统一为标准 schema，按类目组织成图文配对数据集，编写数据字典文档，并完成隐私合规检查。

#h1[2．设计思路]

整体流水线设计如@fig-pipeline 所示，原始数据经翻译统一、质检增强后落盘为标准化数据集，各阶段脚本解耦、产出落盘、可断点续跑：

#figure(
  image("figures/pipeline.svg"),
  caption: [数据采集与预处理流水线],
) <fig-pipeline>

关键设计决策：

- 两层去重：标题规范化判重（剥离容量/型号/颜色尾巴后比较）+ 封面图指纹判重 + 全库 SHA-256 图片指纹复用，同一张图只落盘一次；
- 两层清洗：规则质检（字段完整性、图片可解码）打底，大模型视觉审核（置信度阈值 0.72）做属性补全与"是否目标商品"判定，排除样本单独保存可追溯；
- 健壮性：翻译与清洗均支持断点续跑（is_readed 标记、审计 JSONL），API 失败自动重试，图片下载失败不写入元数据；
- 合规优先：爬取遵守 robots.txt 与站点条款、控制频率，遵守《网络数据安全管理条例》@netsec 等法规要求；公开数据集遵守其授权协议，数据不含任何个人信息；
- 文档化：README.md 作为数据字典，记录字段定义、清洗步骤与数据来源授权。

#h1[3．代码实现]

#h2[1.1 多源数据获取]

（1）结构化与非结构化数据获取——公开数据集。MUGE 数据集提供中文商品图文对（运动鞋、水杯、双肩包等，4704 条），Amazon 商品数据集提供英文商品表格与主图（1158 条）。两者均以 CSV/图片文件形式合法获取（平台惯例同 Kaggle@kaggle、UCI@uci 公开仓库），解析入库后记录字段说明。

（2）非结构化数据获取——站点爬取。苏宁易购来源使用自研爬虫 crawl_suning.py，4 线程并发抓取搜索页，代理池失败自动降级直连，限速与翻页上限保护站点。核心参数与判重逻辑如下：

```python
DELAY = 3.0          # 每批页面之间的间隔，别调低
WORKERS = 4          # 同时使用的 IP 和线程数
FAIL_LIMIT = 3       # 连续 3 批都失败才停止
PAGE_RETRY = 3       # 同一个 IP 失败 3 次才换下一个
FETCH_TIMEOUT = 45
MAX_PAGES = 20       # 每个搜索词最多翻页
PER_CATEGORY = 1000  # 每类最多 1000，实验 1 建议区间是 300–1000
HARD_CAP = 6000      # 6 个品类 × 1000。可调低，但不要高于这个数
SEARCH_URL = "https://search.suning.com/{kw}/&iy=0&isNoResult=0&cp={page}"
```

标题判重公式（同一款商品只留第一次见到的封面，剥离容量/型号/颜色尾巴后比较）：

```python
def title_key(name):
    """去掉空格、容量、型号和末尾颜色后再比较。同一款只留第一次见到的封面。"""
    parts = re.sub(r"\s+", " ", (name or "").strip()).split(" ")
    while parts and _VARIANT_TOKEN.match(parts[-1].strip("，,。/")):
        parts.pop()
    s = "".join(parts)
    s = re.sub(r"\d+(?:\.\d+)?(?:ml|mL|ML|l|L)", "", s)
    s = re.sub(r"[A-Za-z]{2,}[-_]?[A-Za-z]?\d{2,}[A-Za-z0-9-]*", "", s)
    s = re.sub(r"(?:雪山落日|磨砂黑|梦幻黑|象牙白|米白|[白黑红蓝绿粉灰银金黄紫橙棕青]色)", "", s)
    return re.sub(r"[()（）\[\]【】]", "", s)
```

爬虫启动时自动清理历史重复行与缺图行，封面下载失败的记录不写入元数据，保证入库即有效。

（3）特殊场景数据获取（图文对）。三源数据均以"图片路径 + 文本描述"配对形式存储（local_image_path 与 title/description 字段一一对应），并校验配对完整性，满足多模态图文对齐要求。

（4）跨语言统一。Amazon 英文字段（product_type / item_name / brand / color / material）经 DeepL 翻译为中文@deepl，分字段定制翻译提示（保留型号品牌、不补写事实），类别名使用固定译法映射：

```python
AMAZON_TRANSLATION_FIELDS = ["product_type", "item_name", "brand", "color", "material"]
KNOWN_PRODUCT_TYPE_MAP = {
    "CELLULAR_PHONE_CASE": "手机壳",
    "KITCHEN": "厨房用品",
    "SHOES": "鞋",
    "HOME": "家居用品",
}
FIELD_CONTEXT = {
    "item_name": "这是电商商品标题。翻译为自然、简洁的中文标题，保留型号、品牌和原文明确的商品属性，不补写事实。",
    "brand": "这是商品品牌。优先保留官方品牌拼写；只有存在稳定公认的中文品牌名时才使用中文。",
    ...
}
```

翻译全程写审计 JSONL，支持断点续译，中断后重跑只补未完成条目。

#h2[1.2 数据清洗与增强]

（1）数据质量问题处理。针对缺失值、异常值、重复值分层处理：

- 图片技术质检：check_product_fields.py 校验 12 个标准字段，逐图验证可解码性、记录实际尺寸与格式，写入 image_status（ok/missing/failed）；
- 重复值：爬虫端标题+封面双判重；入库端 SHA-256 图片指纹去重，重复图片复用已有文件不重复落盘；
- 文本规范化：清洗特殊字符、统一空白与全半角、颜色/材质归一化（如"酒红/深红→红"）；
- 大模型视觉清洗：run_gpt6luna_cleaning.py 调用 GPT 视觉模型逐条审核图片主体，识别细分类、颜色、材质并生成描述，"无法确认"类值强制置空，防止幻觉填充：

```python
SYSTEM_PROMPT = """你是中文电商商品数据清洗员。你必须同时观察商品图片，并参考标题和当前类别作为弱提示。
当前类别可能错误，不能只复制当前类别。只把图片中真正作为商品主体的物品作为结果。
请只返回一个 JSON 对象，不要 Markdown、解释文字或代码围栏，字段必须是：
{
  "is_product": true,
  "product_type": "目标类别列表|其他|无法判断",
  "type": "细分类名称，无法判断时为空字符串",
  "color": "主色或配色，无法确认时为空字符串",
  "material": "能从图片或标题可靠判断的主要材质，无法确认时为空字符串",
  "confidence": 0.0,
  "reason": "一句简短中文理由"
}
不要凭空猜颜色或材质。配件、包装盒、货架、食品、书籍、家具等不是目标商品时，is_product=false 或 product_type=其他。
"""
```

置信度低于 0.72 或非目标商品的记录移入排除集（保留图片与原因，可追溯复核），图片与文字冲突时以图片为准。

（2）数据增强方法。本实验采用的增强策略：商品抠图（ISNet 语义分割@isnet 去除背景，突出商品主体，输出 cutout_map.csv 对照表）、文本描述生成（基于识别属性模板化补全 description，扩充文本模态）、颜色/材质同义归一（等效于受控同义词替换，避免语义失真）。更强的几何/光学图像增强（torchvision@pytorch 旋转裁剪加噪）与增强效果量化对比（CNN 准确率/BLEU）安排在模型训练阶段，见第六章展望。

（3）输出。清洗后的数据集落盘 processed_data_cleaning/，并记录清洗前后关键指标（通过数、排除数、待复核数、通过率），见@tbl-clean。

#h2[1.3 数据集建设]

（1）数据标准化。统一 schema 为 12 个标准字段，字段名小写下划线分隔（规范同 scikit-learn 数据预处理惯例@sklearn）：

```python
FINAL_FIELDS = [
    "item_id", "product_type", "item_name", "description", "brand", "color",
    "material", "local_image_path", "image_status", "image_height", "image_width",
    "is_readed",
]
```

三源字段统一映射到该 schema；图片路径统一为仓库相对路径（跨平台可移植）；is_readed 为流水线断点标记。图片指纹实现：

```python
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
```

（2）数据集构建。按 9 个商品大类（鞋、水杯、包、男装、运动服、女装、手机壳、厨房用品、家居用品）归并组织，每类一份 products.csv + 图片目录，合并全程写 merge_index.jsonl 索引（记录来源数据集与原始 id，可溯源）。目录分层：raw_data（原始）→ processed_data（标准化）→ processed_data_cleaning（清洗后）→ processed_data_retrieval（检索任务数据集），处理链路即 Data Provenance，对应 EU AI Act 第 50 条对数据溯源与机器可读标记的要求@euai。

（3）数据集文档化。根目录 README.md 作为数据集文档，含数据来源与授权协议（MUGE/Amazon 公开数据集协议、苏宁公开页面合规爬取）、数据格式说明（字段定义、图像尺寸、配对关系）、清洗与增强步骤记录、隐私说明（无敏感个人信息），并按《个人信息保护合规审计管理办法》@pipl-audit 的思路留有隐私合规自查清单。

#h1("4. 测试优化")

- 字段自检：check_product_fields.py 全量校验 9 类目 CSV，12 字段完整性与图片可解码性全部通过（image_status 均为 ok）；
- 脚本自检：爬虫与抠图脚本内置 --selftest 离线自检，不发网络请求即可验证解析/推理逻辑；
- 审计抽查：翻译审计 JSONL 与清洗 model_audit.jsonl 逐条记录模型输入输出与错误（如 API 404），人工抽查译文与识别结果一致性；
- 断点续跑测试：清洗中途强制中断后重启，仅续跑未处理条目（is_readed 标记），结果与一次跑完一致；
- 优化点：代理失败降级直连、CSV 原子写入（write_csv_atomic）、图片下载失败不写元数据、启动时清理脏数据，均显著减少返工。

// ============================== 四、实验关键技术与难点 ==============================
#h1[四．实验关键技术与难点]

+ 多源异构字段统一：三源数据字段命名、取值粒度、语言各异。通过 12 字段标准 schema 与映射规则统一，类别名固定译法表保证跨源一致性，是后续一切任务的基础。
+ 判重公式设计：电商标题存在大量变体尾巴（容量/型号/颜色）。title_key 用正则剥离变体 token 后再判重，配合封面指纹与 SHA-256 图片指纹，三层去重兼顾召回与精度——这是采集阶段的核心难点。
+ 大模型视觉清洗的可靠性控制：大模型会产生幻觉属性。通过"图片为主、类别弱提示"的提示词约束、强制 JSON 结构输出、"无法确认置空"规则、置信度阈值 0.72、排除集留存与审计日志，将不可靠输出转化为可复核的确定性流程。
+ 大规模翻译的一致性与断点续译：1158 条×5 字段的翻译若中断需从头付费。审计 JSONL + 已完成索引实现断点续译；分字段上下文提示保证译文风格统一且不编造事实。
+ 隐私与合规：爬取前核查 robots.txt 与 AI 训练数据 opt-out 声明，限速降压；公开数据集遵守授权协议（课程作业范围）；全库字段不含姓名/联系方式等个人信息，符合《网络数据安全管理条例》@netsec 与《个人信息保护合规审计管理办法》@pipl-audit 的要求。
+ Data-Centric AI 实践：以"数据质量报告"量化评估完整性（字段/图片缺失率）、一致性（颜色材质归一）、代表性（九类目分布）、时效性（2026 年在售商品），用数据质量而非模型规模定义系统上限@dcai-manifesto。

// ============================== 五、实验结果与分析 ==============================
#h1[五、实验结果与分析]

本实验获取了至少 2-3 类数据：结构化商品元数据（CSV 表格）、非结构化文本（标题/描述）、非结构化图像（商品图片），且三者以商品为键一一配对，共 10165 条商品、10165 张图片，覆盖 9 个商品大类。各阶段结果见@tbl-src、@tbl-cls、@tbl-clean，规模与通过率分布见@fig-src、@fig-cls、@fig-pass。

#figure(
  t5(
    table(
      columns: (auto, auto, auto, auto, 1fr),
      align: center + horizon,
      table.header([数据来源], [获取方式], [记录数], [图片数], [模态构成]),
      [MUGE], [公开数据集下载], [4704], [4704], [结构化字段 + 中文文本 + 图像（图文对）],
      [Amazon], [公开数据集下载 + DeepL 翻译], [1158], [1158], [结构化字段 + 文本（英→中） + 图像],
      [苏宁易购], [自研爬虫合规爬取], [4303], [4303], [结构化字段 + 文本 + 图像],
      [合计], [—], [10165], [10165], [三类模态齐全、图文配对],
    )
  ),
  caption: [多源数据获取结果],
) <tbl-src>

#figure(
  image("figs/fig_sources.png"),
  caption: [多源数据获取规模对比],
) <fig-src>

#figure(
  t5(
    table(
      columns: (auto, auto, auto, auto, auto),
      align: center,
      table.header([类目], [记录数], [类目], [记录数], [类目记录数合计]),
      [鞋], [3401], [水杯], [2523], [包 1330 / 男装 1000 / 运动服 684],
      [女装], [361], [手机壳], [300], [厨房用品 296 / 家居用品 270],
      [合计], [10165], [—], [—], [9 类目],
    )
  ),
  caption: [标准化数据集类目分布（processed_data）],
) <tbl-cls>

#figure(
  image("figs/fig_categories.png"),
  caption: [九类目数据量分布],
) <fig-cls>

#figure(
  t5(
    table(
      columns: (auto, auto, auto, auto, auto, auto),
      align: center,
      table.header([类目], [清洗前], [通过], [排除], [待复核], [通过率]),
      [鞋], [3401], [3219], [182], [0], [94.6%],
      [水杯], [2523], [2016], [504], [3], [79.9%],
      [包], [1330], [1291], [39], [0], [97.1%],
      [男装], [1000], [999], [0], [1], [99.9%],
      [运动服], [684], [668], [16], [0], [97.7%],
      [女装], [358], [357], [1], [0], [99.7%],
      [手机壳], [300], [300], [0], [0], [100%],
      [厨房用品], [296], [279], [17], [0], [94.3%],
      [家居用品], [270], [264], [6], [0], [97.8%],
      [合计], [10162], [9393], [765], [4], [92.4%],
    )
  ),
  caption: [数据清洗前后质量指标对比],
) <tbl-clean>

#figure(
  image("figs/fig_passrate.png"),
  caption: [各类目清洗通过率（虚线为总体 92.4%）],
) <fig-pass>

结果分析：

+ 整体清洗通过率 92.4%（9393/10162），字段完整率 100%（12 字段校验全通过），图片可解码率 100%（image_status 均为 ok），重复图片经 SHA-256 去重后为零，达成数据标准化与质量目标；
+ 水杯类通过率最低（79.9%，见@fig-pass），主因是搜索来源混入杯盖、杯刷等配件与非水杯商品，视觉清洗将其正确排除——这正体现"以图片为准"清洗策略的价值，宁缺毋滥保证训练数据纯度；男装、手机壳通过率接近 100%，图像主体清晰、类目边界明确；
+ 4 条待复核记录源于清洗期间视觉模型 API 临时 404，已入审计日志与待复核队列（见@tbl-clean），属可恢复的工程问题而非数据问题；
+ 数据质量报告（四维度）：完整性——字段与图片缺失率为 0；一致性——颜色/材质归一化后取值词表收敛，跨源类别命名统一；代表性——覆盖 9 类目、3 数据源、中外文商品，头部类目（鞋/水杯）样本充足；时效性——商品为近年在售款，来源更新至 2026 年。四维度汇总见@tbl-quality。

#figure(
  t5(
    table(
      columns: (auto, 1fr, auto),
      align: center + horizon,
      table.header([维度], [评估结论], [关键指标]),
      [完整性], [字段与图片无缺失], [缺失率 0%，图片可解码率 100%],
      [一致性], [跨源字段/颜色/材质/类别归一], [12 字段 schema 统一，颜色词表收敛],
      [代表性], [9 类目 3 来源图文配对], [10165 条，头部类目 >3000 条],
      [时效性], [近年在售商品], [采集窗口 2026-09 ~ 2026-10],
    )
  ),
  caption: [数据质量报告（Data-Centric AI 四维度）],
) <tbl-quality>

// ============================== 六、实验总结与展望 ==============================
#h1[六、实验总结与展望]

总结：本实验完整走通了"多源获取 → 清洗增强 → 数据集建设"的数据流水线：从 MUGE、Amazon、苏宁三个来源获取结构化表格、非结构化文本、图像三类模态共 10165 条商品图文数据；经 DeepL 翻译统一语言、三层去重、图片质检与 GPT 视觉属性清洗，产出 9393 条高质量图文配对样本（通过率 92.4%）；按 12 字段标准 schema 组织为 9 类目标准化数据集并完成文档化与合规检查。小组成员分工见封面表格。

通过本次实验，加深了对 Data-Centric AI 的理解：水杯类近 20% 的"脏数据"如果直接进入训练，将直接拉低下游检索与推荐的上限，而清洗阶段每一分投入都在为后续模型效果兜底；也体会到工程健壮性（断点续跑、审计日志、原子写入）在数据流水线中的实际价值。

展望：

+ 数据增强效果量化：用 torchvision@pytorch 做几何/光学增强，以简单分类模型对比增强前后验证集准确率，文本侧评估 BLEU 相似度，形成增强对比实验报告；
+ 数据集划分与加载器：按 8:1:1 划分训练/验证/测试集，用 PyTorch Dataset 封装图文数据，补充 HuggingFace Data Card 格式数据集卡片；
+ 自动化策展流水线：引入 Data-Juicer@data-juicer 与手工清洗对比效率（去重、过滤、规范化、质量筛选、语言识别算子），亦可对比 NVIDIA NeMo Curator@nemo 的 GPU 加速流水线；
+ 服务后续实验：基于本数据集的 Chinese-CLIP@chinese-clip 图文检索基线（实验二）已在搭建，后续微调训练、量化部署、前后端与上架 Agent 均以本数据集为基座；并持续跟踪《版权工作"十五五"规划》@copyright5 对 AI 训练数据版权规则的落地要求。

// ============================== 七、参考文献 ==============================
#h1[七．参考文献]

#set par(first-line-indent: 0pt)
#bibliography("refs.bib", style: "ieee", title: none)
