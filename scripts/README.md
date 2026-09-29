# 数据处理脚本

当前先处理字段和图片路径，再构建中文图文检索数据。检索数据生成和模型训练脚本尚未编写。

## 文件概览

| 文件 | 作用 |
|---|---|
| `classify_products.py` | 按商品类别整理 CSV 和图片，生成正式数据目录 |
| `check_product_fields.py` | 检查字段、空值、商品 ID、图片路径和图片状态 |
| `translate_amazon_products_deepl.py` | 使用 DeepL 翻译 Amazon 商品字段，当前入口 |
| `translate_amazon_products.py` | 旧的 Ollama Amazon 翻译脚本，仅作历史保留 |
| `crawl_suning.py` | 小规模采集苏宁公开商品数据，输出到 `Suning_data` |
| `cutout_images.py` | 用开源 rembg 批量抠图，输出透明底 PNG 到 `images_cutout` |
| `README.md` | 本目录脚本说明 |

## 1. 整理商品数据：`classify_products.py`

读取商品 CSV，按 `product_type` 分类，复制图片，生成统一的 11 字段 `products.csv`、`image_quality_report.csv` 和 `dataset_summary.csv`。它使用已有类别字段，不会识图或补写商品描述。当前版本是单次整理脚本，增量追加规则见第 4 节。

在项目根目录运行 MUGE：

```powershell
python scripts/classify_products.py `
  --input-file data/raw_data/MUGE_data/products.csv `
  --output-dir data/processed_data `
  --category-map "双肩包=包,运动鞋=鞋"
```

参数说明：

| 参数 | 是否必需 | 默认值或说明 |
|---|---|---|
| `--input-file` | **必需** | 要处理的商品 CSV |
| `--output-dir` | 可选 | 默认 `data/processed_data` |
| `--category-map` | 可选 | MUGE 建议填写，用于归一化类别 |
| `--repo-root` | 可选 | 默认自动识别项目根目录 |
| `--clean-output` | 可选 | 删除旧输出后重新生成 |

因此，MUGE 也可以简写为：

```powershell
python scripts/classify_products.py --input-file data/raw_data/MUGE_data/products.csv --category-map "双肩包=包,运动鞋=鞋"
```

首次生成一个空的输出目录时直接运行即可。已有输出目录时，必须明确使用 `--append` 或 `--clean-output`；脚本不会默认覆盖已有结果。

如需完整重建输出，可加 `--clean-output`。此参数会删除整个指定输出目录，请确认其中没有需要保留的文件后再用。

增量追加其他数据集时使用 `--append` 和 `--dataset-id`：

```powershell
python scripts/classify_products.py `
  --input-file data/raw_data/Amazon_data_translated/products.csv `
  --output-dir data/processed_data `
  --append `
  --dataset-id Amazon_data `
  --dry-run
```

确认预览结果后，去掉 `--dry-run` 执行实际追加；可以加 `--backup-dir data/processed_backups` 保存追加前备份。
追加会保留旧 CSV 和图片，去重后把新记录追加到对应类别末尾；图片按 SHA-256 复用，文件名冲突时使用哈希后缀。

## 2. 检查整理结果：`check_product_fields.py`

检查必需字段、空值、重复商品 ID、图片路径和 `image_status`。发现问题时退出码为 `1`，通过时为 `0`。

依次检查 MUGE 三类：

```powershell
python scripts/check_product_fields.py --input-file data/processed_data/包/products.csv --report data/processed_data/包/field_check_report.json
python scripts/check_product_fields.py --input-file data/processed_data/水杯/products.csv --report data/processed_data/水杯/field_check_report.json
python scripts/check_product_fields.py --input-file data/processed_data/鞋/products.csv --report data/processed_data/鞋/field_check_report.json
```

检查脚本中只有 `--input-file` 必需；`--report` 可选，不填写时只在终端显示结果。

## 3. 翻译 Amazon 商品字段：`translate_amazon_products_deepl.py`

这是当前的 Amazon 专用翻译入口。它读取 Amazon `products.csv`，调用 DeepL，翻译
`product_type`、`item_name`、`brand`、`color`、`material` 五个字段，并保留原表全部 12 个字段和顺序。
脚本不处理图片、`image_quality_report.csv` 或 `description`，也不覆盖原始文件。

安装 SDK 并设置 API Key：

```powershell
python -m pip install deepl
```

API Key 只从环境变量 `DEEPL_API_KEY` 读取，不要写入脚本或 CSV。下面的设置只对当前 PowerShell 会话生效：

```powershell
$env:DEEPL_API_KEY = "你的 DeepL API Key"
```

```powershell
python scripts/translate_amazon_products_deepl.py `
  --input-file data/raw_data/Amazon_data/products.csv `
  --output-file data/raw_data/Amazon_data_translated/products.csv `
  --audit-file data/raw_data/Amazon_data_translated/translation_audit.jsonl
```

输出目录会自动创建。审计文件用于断点续译；重复运行会跳过本脚本已经成功翻译的记录，
中断或失败后可直接重跑，`--no-resume` 会从头翻译。

`product_type` 的固定译法包括：`SHOES` → `鞋`、`KITCHEN` → `厨房用品`、`HOME` → `家居用品`、
`CELLULAR_PHONE_CASE` → `手机壳`；其他类别交给 DeepL，并要求输出简洁类别词。

常用可选参数：`--category-map-file`、`--product-type-map`、`--batch-size`、`--max-retries`、`--no-resume`。

`translate_amazon_products.py` 是旧的 Ollama 实验脚本；当前使用 DeepL 脚本。其他数据集另建翻译入口。

## 4. 多数据集增量合并：`--append`

`classify_products.py --append` 会把新数据安全追加到已有分类结果。先使用 `--dry-run` 查看新增、重复和冲突数量，再去掉该参数执行。

1. 先把新数据转换为统一的 11 个字段，并将类别归一化为已有类别名称；
2. 旧记录全部保留，新记录按原有顺序追加到对应类别 CSV 的末尾；
3. 同一数据集使用 `dataset_id + item_id` 去重，重复运行同一数据集不会重复增加记录；
4. 不同数据集的 `item_id` 相同，不直接判定为重复；商品字段和图片完全相同的记录再按内容指纹去重；
5. 内容指纹由商品文本字段和图片 SHA-256 组成，只有内容和图片都相同才跳过；
6. 相同图片只保存一份，新商品记录指向已有图片；文件名相同但内容不同的图片使用哈希后缀，绝不覆盖旧图片；
7. `image_quality_report.csv` 只追加新商品的检查记录，`dataset_summary.csv` 根据合并后的全部数据重新统计；
8. 合并前支持预览新增数、重复数和冲突数，并保留备份；重复执行同一输入时应新增 0 条。

最终分类目录保持：

```text
data/processed_data/<product_type>/
├── products.csv
├── images/
└── image_quality_report.csv
```

为了保持 MUGE 的 11 个字段，数据集来源、记录指纹和图片指纹放入单独的合并索引文件，不直接增加到正式 `products.csv`。
每次追加都会在输出根目录维护 `merge_index.jsonl`，用于记录数据集来源、商品指纹和图片指纹。

## 5. 批量抠图：`cutout_images.py`

用开源 [rembg](https://github.com/danielgatis/rembg)（MIT 协议，`isnet-general-use` 模型）把商品图批量抠成透明底 PNG。支持多数据集，无命令行参数，在项目根目录一键运行：

```powershell
python scripts/cutout_images.py
```

运行流程分五步，终端逐步打印进度：

1. **环境检查**：要求 Python 3.11+；缺任何依赖（rembg、onnxruntime 等）自动 `pip install`，装不上会给出可手动执行的命令；
2. **扫描数据集**：自动扫描 `data/raw_data/*/images/`，把有图片的目录按编号列出（如 `1) Amazon_data 1158 张`），输入编号选择要处理的数据集——`1` 单个、`1,3` 或 `1 3` 多个、`all` 全部（建议一次处理一个目录）；输入无效会重新询问；
3. **准备模型**（约 170MB，三级获取，能离线就不联网）：
   - `scripts/models/isnet-general-use.onnx` 放了文件 → 直接复制到 rembg 缓存使用；
   - 本机已有缓存 → 直接用；
   - 都没有 → 自动在线下载（需联网），失败会提示手动放置模型的路径；
4. **逐目录并发抠图**：并发数自动取 `CPU 核数` 和 `可用内存÷2` 的较小值，每个推理进程限单线程（防止线程爆炸导致内存不足）；日志每条带时间戳，每抠一张打印一行结果（`ok`/`skip`/`fail: 原因` + 文件名 + 进度），每 100 张再打一行汇总：

```text
[16:07:20]         ok     01sUPg0387L.jpg [1/1]
[16:07:20]         进度 1/1 (ok=1 skip=0 fail=0) 已用 6s
```
5. **输出汇总**：每个数据集的输出放在自己的目录下，打印成功/跳过/失败统计：

```text
data/raw_data/<数据集>/images/          # 输入：原图（jpg/png/webp）
data/raw_data/<数据集>/images_cutout/   # 输出：<原名>.png 透明底
```

断点续跑：输出已存在则跳过，中断或失败后直接重跑即可接着抠；单张失败只记录文件名和原因，不中断整批；先写 `.part` 临时文件再改名，不会留下半张图。

环境变量（可选）：

| 变量 | 作用 |
|---|---|
| `CUTOUT_SELECT=1,3` | 跳过交互直接选数据集；非交互环境（管道/后台）默认处理全部 |
| `CUTOUT_WORKERS=4` | 覆盖并发数（内存不足时调小） |
| `CUTOUT_LIMIT=3` | 只跑前 3 张（试跑用） |

注意：

- **模型不进 git**：单文件 170MB 超过 GitHub 的 100MB 上限，`scripts/models/*.onnx` 已加进 `.gitignore`，模型放本地目录或自行挂 Release/LFS；`images_cutout` 是派生结果，同样不入库；
- **首次运行需联网**装 pip 依赖（模型已有本地获取路径，依赖装过一次后可离线）；
- **已知残留**：促销文字、品牌角标可能被当成前景保留（模型无法区分装饰图形和商品）；玻璃等透明商品边缘只做到可用级。分类/检索用途够用，做干净素材建议人工复查。

## 6. 采集苏宁商品数据：`crawl_suning.py`

小规模限量采集苏宁「未登录可见」搜索页的公开字段：标题、图片、品牌|材质、卖点描述。价格接口未抓包逆向，`price` 列留空；每条记录带 `source_url`、`crawl_date`，缺失字段留空、不从图片或标题臆造。单线程限速，不绕过验证码/登录。用法见脚本头部注释与参数表。

前置：代理从仓库根目录 `.env` 读取，或用参数传代理文件/接口：

```text
# .env
PROXY_POOL_URL=http://你的代理池链接
```

```powershell
python scripts/crawl_suning.py              # 采集
python scripts/crawl_suning.py --selftest   # 离线解析自检，不发请求
```

参数说明：

| 参数 | 是否必需 | 默认值或说明 |
|---|---|---|
| `--max-items` | 可选 | 总量硬上限，默认 6000（可调低） |
| `--delay` | 可选 | 请求间隔秒数，默认 3，不建议低于 3 |
| `--proxy-file` | 可选 | 代理列表文件，每行 `ip:port` 或 `http://ip:port` |
| `--proxy-api` | 可选 | 代理池 API，默认读 `.env` 的 `PROXY_POOL_URL` |
| `--selftest` | 可选 | 只跑离线解析自检 |

采集规则：

1. 品类与搜索词取自苏宁搜索页类目筛选项（2026-09-28 公开页核对）：水杯、双肩包、运动鞋、女装、男装、运动服；每类写满 1000 条即停，每个搜索词最多翻 20 页；
2. 标题必须命中本类词（`ACCEPT` 词表），并排除配件和串类（`REJECT` 词表），标题对不上不入库；
3. 去重：商品编号已收过、同一标题（去空白后相同）、同一张封面图，只保留第一条，不再下载；
4. 断点续传：重跑跳过已成功的商品，同标题也不再下；
5. 代理一个 IP 连续失败 3 次换下一个，连续 3 个 IP 都失败才停止；请求头在几份常见浏览器配置间轮换；
6. 执行前请人工确认 https://www.suning.com/robots.txt ，仅在允许范围内收集。

输出到 `data/raw_data/Suning_data/`：

```text
products.csv                 # 16 列，与现有数据集字段对齐
image_quality_report.csv     # 与现有数据集 image_quality_report.csv 同列格式
images/<商品编号>.<扩展名>
```

## 处理顺序

```text
crawl_suning.py（苏宁采集，可选）→ translate_amazon_products_deepl.py → 字段统一/类别整理 → classify_products.py 或增量合并 → check_product_fields.py → 中文图文检索数据构建（待开发）
```

不同数据集字段不同时，先完成该数据集的字段映射，再运行整理脚本。图片能正常读取不代表图片内容与商品描述匹配；当前脚本不做语义审核。
