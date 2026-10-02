# 商品图文检索脚本

这里的脚本把人工审核后的商品数据转换为可查询的中文图文向量索引。当前基线的输入是
`data/processed_data_cleaning/`，输出是 `data/index_data/`；输入目录只读，索引是可删除、
可重建的派生文件。

## 目录中的脚本

| 文件 | 作用 |
|---|---|
| `build_category_index.py` | 自动发现类别，编码图片和模板文本，生成 FAISS 索引和元数据表 |
| `search_category_index.py` | 用中文查询词召回商品图片，并返回 JSON 结果 |
| `text_builder.py` | 统一生成属性、商品标题和商品描述文本模板 |
| `encoder.py` | 延迟加载 Chinese-CLIP，提供图片和文本批量编码 |
| `registry.py` | 读写 `index_registry.json`，保存类别索引位置 |
| `requirements.txt` | 本模块的 Python 依赖 |

## 快速开始

两个入口默认读取 `configs/retrieval.json`；命令行参数覆盖配置中的值。
配置字段及自定义配置文件的使用方式见 [`configs/retrieval.md`](../../configs/retrieval.md)。

从项目根目录运行，命令中的路径都是相对路径：

```powershell
py -3 -m pip install -r scripts\retrieval\requirements.txt
py -3 -m pip install cn_clip --no-deps
py -3 scripts\retrieval\build_category_index.py --categories "鞋" --overwrite
py -3 scripts\retrieval\search_category_index.py "白色运动鞋" --category "鞋" --top-k 5
```

第一次运行会下载 `ViT-B-16` 权重到 `models/chinese_clip/`。也可以省略
`--categories`，让脚本自动处理所有包含 `products.csv` 的类别目录。

## 输入要求

每个类别目录有一个 `products.csv` 和图片目录。CSV 至少需要 `item_id` 或
`product_id`，推荐包含 `product_type`、`type`、`item_name`、`description`、`color`、
`material`、`local_image_path`。图片路径优先读取 `local_image_path`；找不到时会尝试
类别目录下的 `images/<item_id>.*` 或实际采集文件名常见的 `images/<item_id>__*`。
CSV 中的 JSON 图片路径列表也可以被读取。缺少图片、重复主键的行会记录到类别输出的
`errors.csv`。

没有 `products.csv` 的目录（例如 `failed_images`）会被忽略。新增类别不需要修改代码，
只需添加类别目录并重新运行构建命令。

## 输出和查询逻辑

每个类别会生成 `items.csv`、`image_embeddings.npy`、`text_embeddings.npy`、
`image_index.faiss`、`text_index.faiss` 和 `build_report.json`；全部类别由根目录的
`index_registry.json` 登记。`vector_id` 只在同一份索引文件内对应 FAISS 向量位置；重建后可能变化，业务关联应使用 `item_id`。

文本按下面的模板构造：

```text
商品大类：{product_type}；细分类：{type}；颜色：{color}；材质：{material}；商品标题：{item_name}；商品描述：{description}
```

图像和文本向量均做 L2 归一化，图像索引使用 FAISS `IndexFlatIP`。查询时将中文查询
编码后搜索一个或多个类别的图像索引，再按相似度合并排序，最后应用可选的类别、颜色、
材质和细分类过滤。若描述字段已经是四属性模板，脚本会避免重复追加。

详细参数、目录结构、重建规则和验收清单见项目根目录的 [`configs/retrieval.md`](../../configs/retrieval.md)。


