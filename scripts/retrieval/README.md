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
py -3 -m pip install huggingface_hub safetensors
py -3 scripts\retrieval\build_category_index.py --categories "鞋" --overwrite
py -3 scripts\retrieval\search_category_index.py "白色运动鞋" --category "鞋" --top-k 5
```

第一次运行会自动下载 `ViT-B-16` 权重到 `models/chinese_clip/`，本地已有缓存时直接复用。
如果使用 ModelScope，先执行 `py -3 -m pip install modelscope`，再在构建和查询命令中加入
`--use-modelscope`。也可以省略
`--categories`，让脚本自动处理所有包含 `products.csv` 的类别目录。

`models/chinese_clip/` 是索引构建和后续模型微调共用的预训练权重目录。微调完成后应将
新检查点放到独立目录，并使用新检查点重新提取全部向量、重建 FAISS 索引，不能混用不同
模型权重生成的向量。

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

图像和文本向量均做 L2 归一化，索引使用 FAISS `IndexFlatIP`。查询时将中文查询分别
编码后搜索图片索引和商品文本索引，再按下面的公式融合排序：

```text
最终分数 = image_weight × 文本-图片相似度
         + text_weight × 文本-商品描述相似度
```

默认权重为 `0.7/0.3`，可通过配置文件或 `--image-weight`、`--text-weight` 调整。
返回结果会同时给出融合分数、图片相似度和文本相似度，最后应用可选的类别、颜色、
材质和细分类过滤。若描述字段已经是四属性模板，脚本会避免重复追加。

### 以图搜图

当前脚本也支持直接输入商品图片：

```powershell
py -3 scripts\retrieval\search_category_index.py `
  --image "examples/query_shoe.jpg" `
  --category "鞋" `
  --top-k 10
```

脚本使用与建索引时相同的 Chinese-CLIP 图片预处理和图片编码器，查询对应的
`image_index.faiss`，再根据 `vector_id` 找回商品信息。省略 `--category` 时会查询所有
注册类别。图片查询也可以和文字同时提供，执行三路融合检索：

```powershell
py -3 scripts\retrieval\search_category_index.py "白色运动鞋" `
  --image "examples/query_shoe.jpg" --category "鞋" --top-k 10
```

默认分数为：

```text
0.5 × 图片-图片相似度
+ 0.3 × 文本-图片相似度
+ 0.2 × 文本-商品描述相似度
```

可通过 `--image-to-image-weight`、`--text-to-image-weight` 和
`--text-to-description-weight` 调整。

详细参数、目录结构、重建规则和验收清单见项目根目录的 [`configs/retrieval.md`](../../configs/retrieval.md)。


