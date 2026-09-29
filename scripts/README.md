# 数据处理脚本

当前先处理字段和图片路径，再构建中文图文检索数据。检索数据生成和模型训练脚本尚未编写。

通用约定：

- 除特别说明外，命令都在项目根目录执行；
- 输入 CSV 编码自动识别，依次尝试 `utf-8-sig`、`utf-8`、`gb18030`；
- 输出 CSV 一律 `utf-8-sig`（带 BOM，Excel 直接打开不乱码）；
- `classify_products.py` 的 CSV/JSONL 输出和 `cutout_images.py` 的 PNG 输出为原子写入（先写临时文件再改名），中断不留半截文件。

## 文件概览

| 文件 | 作用 |
|---|---|
| `classify_products.py` | 按 `product_type` 整理 CSV 和图片，生成正式数据目录；支持增量合并 |
| `check_product_fields.py` | 检查字段、空值、商品 ID、图片路径和 `image_status` 对账 |
| `translate_amazon_products_deepl.py` | 用 DeepL 翻译 Amazon 商品 CSV 的 5 个文本字段 |
| `crawl_suning.py` | 小规模限量采集苏宁公开商品数据，输出到 `Suning_data` |
| `cutout_images.py` | 用 rembg 批量抠图，输出透明底 PNG |
| `attribute_cleaning/` | 商品属性识别与清洗（GPT 视觉清洗管线），自带 `README.md`，见该目录 |
| `README.md` | 本目录脚本说明 |

## 1. 整理商品数据：`classify_products.py`

**是数据整理器，不是识图分类模型**——它使用输入 CSV 里已经存在的 `product_type` 列把记录和图片归入类别目录，不看图、不补写描述。输出布局：

```text
data/processed_data/<product_type>/
├── products.csv                # 12 列正式数据
├── images/                     # 商品图片（内容去重后复用）
└── image_quality_report.csv    # 12 列图片质检
data/processed_data/
├── dataset_summary.csv         # 5 列汇总统计
└── merge_index.jsonl           # 合并索引（不进 products.csv 的溯源信息）
```

输出列名精确如下（按此顺序）：

| 文件 | 列 |
|---|---|
| `products.csv` | `item_id`, `product_type`, `item_name`, `description`, `brand`, `color`, `material`, `local_image_path`, `image_status`, `image_height`, `image_width`, `is_readed` |
| `image_quality_report.csv` | `item_id`, `product_type`, `image_path`, `source_image_path`, `decode_ok`, `actual_height`, `actual_width`, `format`, `file_size_bytes`, `sha256`, `quality_status`, `quality_reason` |
| `dataset_summary.csv` | `product_type`, `record_count`, `image_ok`, `image_missing`, `image_failed` |
| `merge_index.jsonl` 每行 | `dataset_id`, `item_id`, `source_key`, `category`, `record_hash`, `image_hash`, `local_image_path`, `image_copied` |

`is_readed` 为处理状态：输入含 `true`/`1`/`yes`/`y`（不区分大小写）记为 `true`，其余或缺失记为 `false`；它表示记录是否已经完成读取或处理，不表示属性清洗是否通过。

### 输入要求

- 输入 CSV 必需 4 列：`item_id`、`product_type`、`item_name`、`local_image_path`，缺一即报错退出；
- `local_image_path` 允许相对路径，按「项目根目录相对」→「输入 CSV 所在目录相对」顺序解析；解析不到不崩溃，该条记为 `image_status=missing`；
- 默认使用 `local_image_path` 指向的原图；加 `--cutout` 后，会按原图路径推导抠图路径：原图所在目录的上一级目录 / `--cutout-dir-name` / 原文件名主体加 `--cutout-suffix`；抠图文件不存在时记为 `missing`；
- 空 `product_type` 归为 `UNKNOWN`；类别目录名会清洗非法字符（`<>:"/\|?*` → `_`），空名归为 `UNKNOWN`。

### 三种运行模式

| 输出目录状态 | 用法 | 行为 |
|---|---|---|
| 不存在或为空 | 直接运行 | 首次生成 |
| 已有内容 | 必须二选一 | `--append` 增量追加 或 `--clean-output` 全量重建；不选则报错，**绝不默认覆盖** |
| 已有内容 | `--dry-run`（配 `--append`） | 只打印新增/重复/冲突数量，不写任何文件 |

参数互斥关系：`--append` 与 `--clean-output` 不能同用；`--dry-run` 与 `--clean-output` 不能同用；`--backup-dir` 只能配 `--append`、且不能配 `--dry-run`；`--append` 必须带 `--dataset-id`。

### 去重规则（精确）

1. `source_key = dataset_id::item_id`。同一 `source_key` 已存在且内容哈希相同 → 计入 `duplicate` 跳过；内容哈希不同 → 计入 `conflict` 跳过（同编号不同内容视为冲突，不覆盖旧记录）；
2. `record_hash`（内容指纹）= SHA-256（`product_type`、`item_name`、`description`、`brand`、`color`、`material` 六字段按 `\x1f` 连接，再接图片 SHA-256）。文本和图片都相同才算相同记录，跨数据集同样去重（计入 `duplicate`）；
3. 图片按 SHA-256 复用：同内容图片只存一份，新记录指向已有文件（`image_copied=false`）；同名不同内容的图片改名 `原名_<sha256前12位>.<扩展名>`，再冲突追加 `_1`、`_2`……**绝不覆盖旧图片**；
4. 旧输出里的已有记录在追加时会写入 `merge_index.jsonl`（`dataset_id=legacy/<类别>`），保证索引完整可续。

### 图片状态语义

| `image_status` | 触发条件 | `quality_status` | `quality_reason` |
|---|---|---|---|
| `ok` | Pillow 解码成功，记录宽高与格式 | `pass` | 空 |
| `missing` | 图片文件不存在 | `missing` | `图片文件不存在` |
| `failed` | 文件存在但解码失败 | `failed` | 具体错误信息 |

### 参数

| 参数 | 是否必需 | 默认值或说明 |
|---|---|---|
| `--input-file` | **必需** | 输入商品 CSV |
| `--output-dir` | 可选 | 默认 `data/processed_data` |
| `--repo-root` | 可选 | 默认按脚本位置自动定位项目根目录 |
| `--category-map` | 可选 | 类别归一化，语法 `双肩包=包,运动鞋=鞋`（逗号分隔、`原类别=目标类别`；格式错即报错） |
| `--append` | 可选 | 增量追加模式 |
| `--dataset-id` | 配 `--append` **必需** | 数据集标识，如 `Amazon_data`；不带 `--append` 时默认取输入 CSV 所在目录名 |
| `--dry-run` | 可选 | 预览新增/重复/冲突数量，不写文件 |
| `--backup-dir` | 可选 | 追加前把整个输出目录备份到 `<backup-dir>/processed_data_<UTC时间戳>` |
| `--clean-output` | 可选 | 删除整个输出目录后全量重建（先确认目录里没有要留的东西） |
| `--cutout` | 可选 | 使用抠图；不写时使用原图 |
| `--cutout-dir-name` | 可选 | 抠图目录名，默认 `images_cutout` |
| `--cutout-suffix` | 可选 | 抠图文件扩展名，默认 `png`；可写 `jpg` 或 `.jpg` |

### 用法

首次生成（MUGE，类别归一化）：

```powershell
python scripts/classify_products.py `
  --input-file data/raw_data/MUGE_data/products.csv `
  --category-map "双肩包=包,运动鞋=鞋"
```

使用抠图结果（无需生成或读取路径对照 CSV）：

```powershell
python scripts/classify_products.py `
  --input-file data/raw_data/Suning_data/products.csv `
  --output-dir data/processed_data `
  --cutout `
  --cutout-dir-name images_cutout `
  --cutout-suffix png `
  --category-map "双肩包=包,运动鞋=鞋" `
  --append `
  --dataset-id Suning_data
```

例如 `local_image_path` 为 `data/raw_data/Suning_data/images/123.jpg` 时，脚本会查找 `data/raw_data/Suning_data/images_cutout/123.png`。若抠图输出为 JPG，则设置 `--cutout-suffix jpg`。目录名和后缀均可配置，脚本不依赖具体数据集名称。

`--append --dataset-id Suning_data` 用于把苏宁结果加入已有的 `data/processed_data`。如果要清空整个输出目录后重新生成全部数据，改用 `--clean-output`，不要和 `--append` 同时使用。

增量追加其他数据集（先预览再去掉 `--dry-run` 执行）：

```powershell
python scripts/classify_products.py `
  --input-file data/raw_data/Amazon_data_translated/products.csv `
  --append --dataset-id Amazon_data --dry-run
python scripts/classify_products.py `
  --input-file data/raw_data/Amazon_data_translated/products.csv `
  --append --dataset-id Amazon_data --backup-dir data/processed_backups
```

## 2. 检查整理结果：`check_product_fields.py`

输出完整 JSON 报告到 stdout（`--report` 可同时落盘）。发现任一问题退出码为 `1`，全部通过为 `0`。

检查 6 类问题，命中任一即 `valid=false`：

| 错误码 | 含义 |
|---|---|
| `missing_fields` | 缺少必需字段（默认 4 个：`item_id`、`product_type`、`item_name`、`local_image_path`，可用 `--required-fields` 覆盖） |
| `empty_required_fields` | 必需字段出现空值（逐列计数） |
| `duplicate_item_id` | `item_id` 重复（列出重复 ID） |
| `absolute_image_path` | `local_image_path` 使用了绝对路径（必须是仓库相对路径） |
| `missing_images` | 图片文件不存在或大小为 0 字节 |
| `image_status_mismatch` | 状态对不上：声明 `ok` 但文件缺失/为 0，或声明 `missing`/`failed` 但文件存在 |

12 列标准字段（含 `is_readed`）之外的列记入 `extra_fields`，只报告、不算错误。

### 参数

| 参数 | 是否必需 | 默认值或说明 |
|---|---|---|
| `--input-file` | **必需** | 要检查的商品 CSV |
| `--report` | 可选 | JSON 报告输出路径 |
| `--required-fields` | 可选 | 默认 `item_id,product_type,item_name,local_image_path` |
| `--skip-images` | 可选 | 跳过图片存在性检查 |
| `--repo-root` | 可选 | 默认自动定位 |

依次检查三类（每类各自出报告）：

```powershell
python scripts/check_product_fields.py --input-file data/processed_data/包/products.csv --report data/processed_data/包/field_check_report.json
python scripts/check_product_fields.py --input-file data/processed_data/水杯/products.csv --report data/processed_data/水杯/field_check_report.json
python scripts/check_product_fields.py --input-file data/processed_data/鞋/products.csv --report data/processed_data/鞋/field_check_report.json
```

## 3. 翻译 Amazon 商品字段：`translate_amazon_products_deepl.py`

Amazon 专用翻译入口，不是通用翻译器。固定翻译 5 个文本字段：`product_type`、`item_name`、`brand`、`color`、`material`；输出保留输入表的全部字段和顺序（Amazon 原表 12 列），不修改原始 CSV、图片和 `image_quality_report.csv`。

各字段翻译约束（脚本内 `FIELD_CONTEXT`）：类别只出简洁类别词；标题自然简洁、保留型号品牌、不补写事实；品牌优先官方拼写；颜色/材质为简洁中文词，多个用「、」分隔。

`product_type` 内置固定译法（`--product-type-map`、`--category-map-file` 可覆盖/扩展）：

| 原值 | 译文 |
|---|---|
| `SHOES` | `鞋` |
| `KITCHEN` | `厨房用品` |
| `HOME` | `家居用品` |
| `CELLULAR_PHONE_CASE` | `手机壳` |

### API Key

只从环境变量读取（默认变量名 `DEEPL_API_KEY`，可用 `--api-key-env` 改），不要写进脚本或 CSV：

```powershell
$env:DEEPL_API_KEY = "你的 DeepL API Key"
python -m pip install deepl
```

### 断点续译

- 每批结果追加写入审计文件（JSONL，默认为输出同目录的 `translation_audit.jsonl`）；
- 重跑时只跳过审计中满足全部三个条件的记录：`status=ok` 且 `dataset=Amazon_data` 且 `provider=deepl`；其余重新翻译；
- 已有输出文件与输入表头不一致时报错（换输出路径或加 `--no-resume`）；
- `--no-resume` 忽略已有输出和审计，从头翻译。

### 参数

| 参数 | 是否必需 | 默认值或说明 |
|---|---|---|
| `--input-file` | **必需** | Amazon 原始 `products.csv` |
| `--output-file` | **必需** | 翻译结果 CSV（不覆盖输入） |
| `--audit-file` | 可选 | 审计 JSONL，默认 `<输出目录>/translation_audit.jsonl` |
| `--product-type-map` | 可选 | 追加类别映射，语法 `SHOES=鞋,KITCHEN=厨房用品` |
| `--category-map-file` | 可选 | 类别映射 JSON 文件，覆盖内置映射 |
| `--source-lang` | 可选 | 源语言代码，不填自动检测 |
| `--target-lang` | 可选 | 默认 `ZH` |
| `--api-key-env` | 可选 | API Key 环境变量名，默认 `DEEPL_API_KEY` |
| `--batch-size` | 可选 | 每批文本数，默认 50（同一字段内文本去重后批量翻译） |
| `--max-retries` | 可选 | 批量失败重试次数，默认 2 |
| `--repo-root` | 可选 | 默认自动定位 |
| `--no-resume` | 可选 | 忽略已有输出和审计，从头翻译 |

### 用法

```powershell
python scripts/translate_amazon_products_deepl.py `
  --input-file data/raw_data/Amazon_data/products.csv `
  --output-file data/raw_data/Amazon_data_translated/products.csv `
  --audit-file data/raw_data/Amazon_data_translated/translation_audit.jsonl
```

## 4. 采集苏宁商品数据：`crawl_suning.py`

小规模限量采集苏宁「未登录可见」搜索页的公开字段。价格接口未抓包逆向，`price` 列留空；每条记录带 `source_url`、`crawl_date`，缺失字段留空、不从图片或标题臆造。4 线程并发抓搜索页，每批之间停约 3 秒，不绕过验证码/登录。

### 运行条件

- 代理二选一：仓库根目录 `.env` 写 `PROXY_POOL_URL=代理池链接`（脚本启动读取），或命令行 `--proxy-file`/`--proxy-api`；
- 执行前人工确认 https://www.suning.com/robots.txt 允许范围内收集（当前被 WAF 拦截无法脚本读取）。

```powershell
python scripts/crawl_suning.py              # 采集
python scripts/crawl_suning.py --selftest   # 离线解析自检，不发请求
```

### 参数

| 参数 | 是否必需 | 默认值或说明 |
|---|---|---|
| `--max-items` | 可选 | 总量硬上限，默认 6000（可调低，不要调高） |
| `--delay` | 可选 | 每批页面之间的间隔秒数，默认 3.0；低于 3 会被自动改回 3 |
| `--proxy-file` | 可选 | 代理列表文件，每行 `ip:port`、`http://ip:port` 或 `ip:port:用户名:密码` |
| `--proxy-api` | 可选 | 代理池 API，默认读 `.env` 的 `PROXY_POOL_URL` |
| `--selftest` | 可选 | 只跑离线解析自检 |

### 采集规则（精确）

1. 品类与搜索词取自苏宁搜索页类目筛选项（2026-09-28 公开页核对），共 6 类：水杯（保温杯/塑料杯/玻璃杯/马克杯/水杯/户外水具）、双肩包（双肩背包/双肩包/书包/女士双肩包/登山包）、运动鞋（跑步鞋/运动鞋/篮球鞋/训练鞋/运动休闲鞋/羽毛球鞋/网球鞋）、女装（连衣裙/女士毛衣/女士针织衫/女士羽绒服/女装）、男装（男士衬衫/男士T恤/男士牛仔裤/男士夹克/男装）、运动服（运动套装/运动夹克/卫衣/运动T恤/休闲运动套装）；
2. 每类写满 1000 条即停（`PER_CATEGORY`）；每个搜索词最多翻 20 页（`MAX_PAGES`）；总量硬上限 6000 条（`HARD_CAP`）；
3. 标题过滤：必须命中本类 `ACCEPT` 词表（如水杯需含 杯/壶/水具），命中 `REJECT` 词表即丢弃（如杯垫/杯套/鞋垫/单肩包），标题对不上不入库；
4. 去重三层：商品编号已收过跳过；标题判重先剥掉末尾规格词（容量 ml/L、个/只/套/组、型号、颜色），再删掉标题里的容量/型号/颜色词后比较（`title_key`），同款不同色/容量只留第一条；同一张封面图（URL 中图文件名相同）只留第一条；
5. 断点续传与启动清理：重跑读取已有 `products.csv`，先删掉 `image_status` 不是 `ok` 的行和同款重复行（只留每款第一条），**并删除这些行对应的本地图片文件**；已成功商品和已见标题都跳过；封面下载失败的记录不写入、回滚去重记录，重跑时再收；
6. 并发与代理降级：启动时向代理池要 4 个 IP 各开 1 个线程（`WORKERS`），每批同时拉多页；搜索页先走分配的代理（12 秒超时），传不完或没商品卡就改直连（20 秒超时），该线程后续固定直连；封面图一律直连下载（代理下图常在约 32KB 断流，半截文件不算成功，超时 45 秒 `FETCH_TIMEOUT`）；代理接口要不到 IP 重试 3 次（`PAGE_RETRY`）；连续 3 批全部失败才停止（`FAIL_LIMIT`）；请求头在 6 份常见浏览器配置间轮换。

### 输出

写入 `data/raw_data/Suning_data/`：

| 文件 | 列（按此顺序） |
|---|---|
| `products.csv` | `item_id`, `product_type`, `item_name`, `brand`, `color`, `material`, `main_image_id`, `domain_name`, `local_image_path`, `image_status`, `image_height`, `image_width`, `price`, `description`, `source_url`, `crawl_date` |
| `image_quality_report.csv` | `dataset_id`, `source_product_id`, `image_path`, `decode_ok`, `actual_height`, `actual_width`, `declared_height`, `declared_width`, `format`, `file_size_bytes`, `sha256`, `quality_status`, `quality_reason` |
| `images/` | `images/<商品编号>.<扩展名>`；封面下载失败的记录**不写入** `products.csv`（日志记「图片失败，本条不计入」），重跑时再收 |

## 5. 批量抠图：`cutout_images.py`

用开源 [rembg](https://github.com/danielgatis/rembg)（MIT，`isnet-general-use` 模型）批量抠透明底 PNG。要求 Python 3.11+；缺依赖（rembg、pillow、numpy、onnxruntime、pooch、scipy、imagehash、filetype）自动 `pip install`，装不上打印可手动执行的命令。除 `--selftest` 自检外无命令行参数，运行后按提示交互选择：

```powershell
python scripts/cutout_images.py              # 一键运行
python scripts/cutout_images.py --selftest   # 离线自检解析逻辑，不处理图片
```

### 流程（终端逐步打印，日志每条带 `[HH:MM:SS]` 时间戳）

1. **环境检查**：Python 3.11+ 校验 + 依赖探测补装；
2. **选择数据集和并发数**（两问，输入无效都会重新询问并重述格式）：
   - 自动扫描 `data/raw_data/*/images/`，凡含图片（`.jpg`/`.jpeg`/`.png`/`.webp`）的目录按编号列出（含张数），输入编号选择——`1` 单个、`1,3` 或 `1 3` 多个、`all` 全部；建议一次处理一个目录；
   - 并发数（同时处理的图片张数）：提示推荐值（= `CPU 核数` 与 `可用内存÷2` 的较小值），**直接回车采用推荐值，或输入 1-128 的整数后回车**；
3. **准备模型**（三级获取，能离线就不联网）：`scripts/models/isnet-general-use.onnx` 有文件 → 复制到 rembg 缓存使用；缓存已有 → 直接用；都没有 → 在线下载约 170MB（失败提示手动放置路径）；
4. **逐目录并发抠图**：按选定并发数开多进程，每个推理进程限单线程；**每抠一张打印一行** `ok/skip/fail: 原因 + 文件名 + [n/总数]`，每 100 张打一行汇总（计数+耗时）；
5. **输出汇总**：打印成功/跳过/失败统计 + 各输出目录；不生成路径对照 CSV。

```text
[16:07:20]         ok     01sUPg0387L.jpg [1/1]
[16:07:20]         进度 1/1 (ok=1 skip=0 fail=0) 已用 6s
```

输入输出（每个数据集的输出放在自己目录下）：

```text
data/raw_data/<数据集>/images/          # 输入原图
data/raw_data/<数据集>/images_cutout/   # 输出 <原名>.png 透明底
```

### 交互怎么用（完整示例）

运行 `python scripts/cutout_images.py` 后有两次输入，每次都会写明输入格式，输错会重新问：

```text
[12:00:00] [2/5] 扫描到 3 个数据集:
      1) Amazon_data                    1158 张
      2) MUGE_data                      4704 张
      3) Suning_data                    2571 张
      输入编号选择要处理的数据集，如 1 或 1,3（all=全部；建议一次处理一个目录）
      > 3                                 ← 第一问：输入编号回车（选 Suning_data）
      输入 [3] -> 处理 1 个数据集
      并发数（同时处理的图片张数），推荐 8。直接回车采用推荐值，或输入 1-128 的整数后回车：
      > 4                                 ← 第二问：输入数字回车（4 并发），直接回车则用推荐值
      并发数 = 4
```

- 第一问的输入格式：`1`（一个）/ `1,3` 或 `1 3`（多个）/ `all`（全部）；编号从 1 开始，超出范围或输字母会重新问；
- 第二问的输入格式：直接回车（用推荐值）或 `1`-`128` 的整数；`abc`、`0`、`129` 都会重新问；
- 不想交互：用环境变量 `CUTOUT_SELECT` / `CUTOUT_WORKERS` 跳过对应提问（见下表）。

分类脚本可通过 `--cutout` 直接按 `local_image_path` 推导抠图路径，不需要 `cutout_map.csv`。如果抠图文件不存在，该商品的图片状态会记录为 `missing`。

断点续跑：输出已存在且非 0 字节则 `skip`；中断/失败后重跑接着抠；单张失败只记录原因不中断整批；先写 `.part` 临时文件再改名，不留半张图。

### 环境变量（可选，设置后跳过对应交互）

| 变量 | 作用 |
|---|---|
| `CUTOUT_SELECT=1,3` | 跳过数据集选择交互（数字格式同交互输入） |
| `CUTOUT_WORKERS=4` | 跳过并发数交互（1-128 的整数） |
| `CUTOUT_LIMIT=3` | 只跑前 3 张（试跑用，建议 20 以内） |

### 注意

- **模型不进 git**：单文件 170MB 超过 GitHub 100MB 上限，`scripts/models/*.onnx` 在 `.gitignore` 中，模型放本地目录或自行挂 Release/LFS；`images_cutout` 派生结果同样不入库；
- **首次运行需联网**装 pip 依赖（模型有本地获取路径，依赖装过一次后可离线）；
- **已知残留**：促销文字、品牌角标可能被当成前景保留（模型无法区分装饰图形和商品）；玻璃等透明商品边缘只做到可用级；分类/检索用途够用，做干净素材建议人工复查。

## 处理顺序

```text
crawl_suning.py（苏宁采集，可选）→ translate_amazon_products_deepl.py → 字段统一/类别整理 → classify_products.py 或增量合并 → check_product_fields.py → attribute_cleaning/（属性识别清洗，可选）→ cutout_images.py（抠图，可选）→ 中文图文检索数据构建（待开发）
```

不同数据集字段不同时，先完成该数据集的字段映射，再运行整理脚本。图片能正常读取不代表图片内容与商品描述匹配；当前脚本不做语义审核。
