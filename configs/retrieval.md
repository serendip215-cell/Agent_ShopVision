# 中文图文检索配置与使用说明

## 1. 目标

本阶段使用已经人工审核的商品数据构建中文图文检索索引。脚本只读取审核数据，
不会修改 `data/processed_data_cleaning/`；生成文件统一放在独立的
`data/index_data/`，便于重新构建、备份和替换索引。

所有脚本参数默认使用**相对项目根目录**的路径。其他开发者先进入项目根目录，
再运行脚本即可，不需要修改代码中的本机绝对路径。

## 2. 输入目录约定

### 配置文件

默认配置文件为 [`retrieval.json`](retrieval.json)。`build` 对象配置索引构建，
`search` 对象配置查询。字段名称与命令行参数对应，将连字符替换为下划线，
细分类查询参数 `--type` 对应 `sub_type`。

两个脚本默认读取该文件；显式命令行参数优先于 JSON 配置。也可以通过
`--config configs/my_retrieval.json` 指定其他配置文件。所有非空路径相对于项目根目录。
查询中的 `model_name` 和 `model_download_root` 留空时读取索引注册表，避免使用不同模型。
`categories` 使用逗号分隔的字符串，留空表示自动发现；布尔值必须使用 JSON 的
`true` 或 `false`。`overwrite` 默认关闭，确认重建时可通过 `--overwrite` 开启。

```powershell
python scripts/retrieval/build_category_index.py --config configs/retrieval.json
python scripts/retrieval/search_category_index.py "白色运动鞋" --config configs/retrieval.json --category "鞋"
```

当前输入目录为：

```text
data/processed_data_cleaning/
├── 鞋/
│   ├── products.csv
│   └── images/
├── 包/
│   ├── products.csv
│   └── images/
└── 其他类别/
    ├── products.csv
    └── images/
```

每个类别目录必须有一个 `products.csv`。图片路径优先使用 CSV 中的
`local_image_path`，脚本也会尝试从类别目录的 `images/` 中按 `item_id` 或
`item_id__*` 查找图片，也支持 JSON 图片路径列表。
CSV 至少需要 `item_id` 或 `product_id`；推荐保留以下字段：

- `item_id`
- `product_type`
- `type`
- `item_name`
- `description`
- `color`
- `material`
- `local_image_path`

`failed_images/` 等没有 `products.csv` 的目录会被自动忽略。缺失图片、空 `item_id`
和重复 `item_id` 的记录会写入对应类别的 `errors.csv`，不会进入索引。

## 3. 输出目录约定

运行后生成：

```text
data/index_data/
├── index_registry.json
├── 鞋/
│   ├── items.csv
│   ├── image_embeddings.npy
│   ├── text_embeddings.npy
│   ├── image_index.faiss
│   ├── text_index.faiss
│   ├── build_report.json
│   └── errors.csv              # 有跳过记录时才生成
└── 包/
    └── ...
```

`items.csv` 的 `vector_id` 与同一次构建生成的 FAISS 向量位置一一对应；重建后该编号可能变化，业务关联应使用 `item_id`；
`local_image_path` 保存为项目根目录下的相对路径。`index_registry.json` 记录模型、
类别、索引文件和数量，查询脚本只依赖这个注册表定位文件。`items.csv` 会保留源
CSV 字段，并额外写入 `vector_id` 和 `text`。

## 4. 文本模板

每条商品文本统一生成：

```text
商品大类：{product_type}；细分类：{type}；颜色：{color}；材质：{material}；商品标题：{item_name}；商品描述：{description}
```

字段缺失时保留字段标签并填空，保证同一模型的输入格式一致。图片向量和文本向量
都进行 L2 归一化，FAISS 使用内积索引 `IndexFlatIP`，归一化后内积就是余弦相似度。
如果 `description` 已经是同一四属性模板，脚本不会重复追加它；如果描述包含额外
商品信息，则会作为“商品描述”追加。
构建和查询必须使用同一个 Chinese-CLIP 模型名称。

## 5. 安装环境

在项目根目录执行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -r scripts\retrieval\requirements.txt
py -3 -m pip install cn_clip --no-deps
py -3 -m pip install huggingface_hub safetensors
```

脚本需要 Python 3.10 或更高版本。`cn_clip` 1.6.0 的旧依赖会锁定 `lmdb==1.3.0`，
在 Windows Python 3.12 上可能触发源码编译失败，因此按上面的两条命令先安装基础依赖，
再使用 `--no-deps` 安装 `cn_clip`。Windows 如果无法安装 `faiss-cpu` wheel，可以在
Conda 环境中执行 `conda install -c conda-forge faiss-cpu lmdb`，再安装 `timm` 和
`cn_clip`。模型缓存目录和索引目录不需要提交到仓库。

Chinese-CLIP 首次运行需要 `huggingface_hub` 和 `safetensors`，并会下载模型缓存到 `models/chinese_clip/`。这个目录可以加入
`.gitignore`，不要把模型权重提交到仓库。没有 GPU 时使用 CPU 也可以运行，但建立全量
索引会更慢。

## 6. 建立索引

先进入仓库根目录：

```powershell
cd <项目根目录>
```

构建全部类别（自动发现包含 `products.csv` 的目录）：

```powershell
py -3 scripts\retrieval\build_category_index.py --overwrite
```

只构建一个类别：

```powershell
py -3 scripts\retrieval\build_category_index.py --categories "鞋" --overwrite
```

常用参数：

| 参数 | 默认值 | 作用 |
|---|---|---|
| `--input-dir` | `data/processed_data_cleaning` | 人工审核数据目录 |
| `--output-dir` | `data/index_data` | 索引输出目录 |
| `--categories` | 自动发现 | 类别名，多个类别用逗号分隔 |
| `--model-name` | `ViT-B-16` | Chinese-CLIP 模型 |
| `--model-download-root` | `models/chinese_clip` | 模型缓存目录 |
| `--batch-size` | `16` | 编码批大小 |
| `--device` | `auto` | `auto`、`cpu` 或 `cuda` |
| `--use-modelscope` | 关闭 | 使用 ModelScope 下载模型权重 |
| `--overwrite` | 关闭 | 允许覆盖同名类别的索引 |

默认不覆盖已有类别目录。重新构建某类别时必须明确加 `--overwrite`，脚本只删除该
类别在 `data/index_data/` 下的输出，不会删除输入数据。

如果使用 `--use-modelscope`，先额外安装 `modelscope`：

```powershell
py -3 -m pip install modelscope
```

## 7. 执行查询

限定类别查询：

```powershell
py -3 scripts\retrieval\search_category_index.py "白色运动鞋" --category "鞋" --top-k 5
```

不限定类别，在注册表中全部类别搜索：

```powershell
py -3 scripts\retrieval\search_category_index.py "适合通勤的黑色包" --top-k 10
```

可以叠加元数据过滤，过滤发生在候选召回之后：

```powershell
py -3 scripts\retrieval\search_category_index.py "白色鞋子" --category "鞋" --color "白" --type "运动" --top-k 5
```

输出为 JSON，包含 `item_id`、商品属性、相似度和相对图片路径；应用层可以根据
`local_image_path` 加载图片，也可以再用 `item_id` 回查商品主表。

## 8. 新增类别或新增数据

新增一个类别时，只需在 `data/processed_data_cleaning/` 下创建类别目录并放入
`products.csv` 和图片，然后重新运行构建命令。新增商品到已有类别后，重新构建该类别
并使用 `--overwrite`，避免旧向量与 CSV 行号不一致。

索引是派生数据，不把它当作人工审核源。审核源有变更时，先确认 CSV 和图片，再重建
对应类别，最后检查 `build_report.json` 和 `errors.csv`。

## 9. 验收清单

1. `index_registry.json` 中列出预期类别。
2. 每个类别的 `items.csv` 行数与 `build_report.json` 的 `items` 相同。
3. `errors.csv` 中的图片缺失和重复记录已人工确认。
4. 随机输入 3 至 5 条中文查询，返回结果的类别、图片和 `item_id` 能对应。
5. 重新构建同一类别后，查询脚本仍能根据注册表正常读取。





