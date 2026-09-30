# Chinese-CLIP 介绍与使用指南

> 在 Agent_ShopVision 中的应用：从概念到检索基线的完整路径，含分工安排

本文分三部分：前半部分介绍 Chinese-CLIP 是什么、怎么调用；中间讲怎么把它接到 Agent_ShopVision 的数据和流程上；最后给出可以分给多人的执行安排。每一步都给出可以直接复制的命令和输入输出示例。

---

## 目录

1. [Chinese-CLIP 是什么](#1-chinese-clip-是什么)
2. [几个必须懂的概念](#2-几个必须懂的概念)
3. [为什么选它做我们的检索底座](#3-为什么选它做我们的检索底座)
4. [模型选哪个](#4-模型选哪个)
5. [安装](#5-安装)
6. [第一个程序：算图文相似度](#6-第一个程序算图文相似度)
7. [数据格式详解](#7-数据格式详解)
8. [接入 Agent_ShopVision 的完整流程](#8-接入-agent_shopvision-的完整流程)
9. [分工与执行安排](#9-分工与执行安排)
10. [常见问题](#10-常见问题)
11. [术语表](#11-术语表)

---

## 1. Chinese-CLIP 是什么

**Chinese-CLIP 是一个"把图片和中文文字翻译成同一种语言"的模型。**

这种"语言"是一串数字（叫**向量**，比如 512 个小数）。它由阿里通义实验室开源，用约 2 亿对中文图文数据训练而成。项目名字里的 "CLIP" 原版是 OpenAI 做的英文版，Chinese-CLIP 是针对中文优化的版本。

它能干三件事，正好对应我们的需求：

| 能力 | 说明 | 对应 Agent_ShopVision |
|---|---|---|
| **图文相似度** | 给一张图和一段文字，算它们有多匹配 | 商品与描述的匹配度 |
| **跨模态检索** | 用文字搜图片、用图片搜文字 | 文字条件检索、图片相似推荐 |
| **零样本分类** | 不用训练，直接判断图片属于哪个类别 | 备用的类别校验手段 |

### 它是怎么工作的

```
   图片 ──→ [图片编码器] ──→ 向量 [0.02, -0.11, ..., 0.07] ┐
                                                            ├─→ 距离近 = 匹配
   文字 ──→ [文字编码器] ──→ 向量 [0.03, -0.10, ..., 0.06] ┘
```

训练时看了 2 亿对"图 + 中文描述"，模型学会了：**描述同一事物的图和文，向量应该靠近**。用的时候就反着用——越靠近，越可能是同一事物。

---

## 2. 几个必须懂的概念

看后面的命令之前，先花两分钟把这几个词弄明白，文档里会反复出现。

| 概念 | 解释 |
|---|---|
| **向量（特征 / embedding）** | 一张图或一段文字被压缩成的一串数字，例如 512 个浮点数。它是内容的"指纹"，向量之间可以算距离 |
| **余弦相似度** | 衡量两个向量方向的接近程度，值在 -1 到 1 之间，越大越相似。检索排序就是按它排的 |
| **编码（encode）** | 把图片/文字变成向量的过程。`encode_image` 管图，`encode_text` 管文字 |
| **Zero-shot（零样本）** | 不做任何训练，直接拿预训练模型用。我们做检索基线就是 zero-shot |
| **Finetune（微调）** | 拿预训练模型，在自己的数据上再训练一小段，让它更懂我们的商品。效果通常更好，但需要 GPU 和训练流程 |
| **Checkpoint（ckpt）** | 训练好的模型权重文件，后缀 `.pt`。加载它 = 把模型"读档" |
| **Tokenize（分词/编码文本）** | 把文字切成模型认识的小单位再转成数字。Chinese-CLIP 自带这一步，调 API 时传原句即可，**不需要**我们自己分词（见[常见问题](#10-常见问题)） |
| **LMDB** | 一种本地数据库格式，训练时随机读取图片比一张张读小文件快得多。所以训练前要把图片打包成 LMDB |
| **Recall@K** | 检索评测指标：正确答案出现在前 K 个结果里的比例。Recall@1 = 第一个结果就对的比例 |
| **MRR** | 平均倒数排名。正确答案排第 1 得 1 分，排第 2 得 0.5 分，取平均，综合衡量排序质量 |

---

## 3. 为什么选它做我们的检索底座

Agent_ShopVision 的检索需求是：**中文查询、商品图片库、文搜图 + 图搜图**。Chinese-CLIP 逐条对上：

1. **中文原生**。原版 CLIP 的文字端是英文，中文效果差；Chinese-CLIP 用 2 亿中文图文对训练，中文理解是它的主场。
2. **数据渊源近**。它的重要评测集就是 MUGE（中文电商图文），而我们的数据里恰好有 4,704 条 MUGE 商品——领域几乎重合，零样本效果有保障。
3. **开源免费、可本地离线运行**，不依赖外部 API（对比我们实验 1 里调用视觉模型清洗属性的流程，检索这条线是纯本地的）。
4. **一条链路吃下多个实验**：
   - 实验 2「检索基线 / 模型训练」→ 零样本基线 + finetune
   - 实验 2/3 评测指标 Recall@K、MRR → 它自带评测脚本直接出分
   - 实验 3「量化剪枝、推理优化」→ 官方提供 ONNX / TensorRT 导出
   - 实验 4/5 前后端与 Agent 的检索工具 → 抽好的向量丢进 FAISS 就是检索服务

---

## 4. 模型选哪个

官方开源 5 个规模。对我们来说**选 ViT-B-16**，理由见表后：

| 模型名 | 参数量 | 分辨率 | 特征维度 | 适用场景 |
|---|---:|---:|---:|---|
| **ViT-B-16**（推荐） | 188M | 224 | 512 | 日常检索、训练、部署，速度与效果平衡 |
| RN50 | 77M | 224 | 512 | 追求极致速度、机器较弱 |
| ViT-L-14 | 406M | 224 | 768 | 追求效果、显卡较好（≥16GB 显存） |
| ViT-L-14-336 | 407M | 336 | 768 | 同上，输入分辨率更高 |
| ViT-H-14 | 958M | 224 | 1024 | 大规模数据训练，一般用不到 |

**选 ViT-B-16 的理由**：我们约 1 万条商品、9 个类别，属于小数据。大模型在这种量级上速度慢、显存吃紧，效果提升有限。先把 ViT-B-16 的基线跑通，日后真需要再换大的——换模型只是改一个参数名，流程完全一样。

---

## 5. 安装

### 5.1 环境要求

| 项目 | 要求 | 检查命令 |
|---|---|---|
| Python | ≥ 3.8（我们项目用 3.11 没问题） | `python --version` |
| PyTorch | ≥ 1.8（建议 2.x） | `python -c "import torch; print(torch.__version__)"` |
| 显卡 | 有 NVIDIA 显卡最佳；没有也能跑（见[常见问题](#10-常见问题)） | `python -c "import torch; print(torch.cuda.is_available())"` |

PyTorch 安装（按是否有 NVIDIA 显卡二选一，官方选择器：<https://pytorch.org/get-started/locally/>）：

```powershell
# 有 NVIDIA 显卡（CUDA 版本以选择器查询结果为准）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 只用 CPU
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### 5.2 安装 cn_clip 库

两种方式任选其一（我们机器上已经有 Chinese-CLIP 源码，推荐第二种）：

```powershell
# 方式一：从 PyPI 安装
pip install cn_clip

# 方式二：从本地源码安装（H:\gitclone\Chinese-CLIP）
cd H:\gitclone\Chinese-CLIP
pip install -e .
```

### 5.3 验证安装

```powershell
python -c "import cn_clip.clip as clip; print(clip.available_models())"
# 期望输出: ['ViT-B-16', 'ViT-L-14', 'ViT-L-14-336', 'ViT-H-14', 'RN50']
```

### 5.4 模型权重

分两种用途，注意区别：

| 用途 | 文件 | 怎么拿 |
|---|---|---|
| 调 API 抽特征（第 6 节） | 自动下载 | 代码里 `load_from_name(...)` 会自动下载到指定目录 |
| 训练 / 评测脚本（第 8 节） | `clip_cn_vit-b-16.pt`（约 750MB） | 手动下载，放入 `data\processed_data_retrieval\pretrained_weights\` |

手动下载地址（下载其中的 `.pt` 文件即可）：

- Hugging Face: <https://huggingface.co/OFA-Sys/chinese-clip-vit-base-patch16>
- 魔搭 ModelScope: <https://www.modelscope.cn/models/AI-ModelScope/chinese-clip-vit-base-patch16>

> 国内网络建议用 ModelScope；代码里 `use_modelscope=True` 走魔搭下载通道（需 `pip install modelscope`），否则走 Hugging Face。

### 5.5 目录放哪：对齐本项目架构

新增的东西全部收进 `data/processed_data_retrieval/`——命名跟随已有的 `processed_data` → `processed_data_cleaning` 递进习惯，含义是"检索流水线的工作区"。完整看一遍 `data/`：

```text
Agent_ShopVision/
├── data/
│   ├── raw_data/                     # 只读原始数据（已有）
│   ├── processed_data/               # 正式合并表（已有）
│   ├── processed_data_cleaning/      # 视觉清洗结果（已有）
│   └── processed_data_retrieval/     # 检索流水线工作区（本次新增）
│       ├── datasets/
│       │   └── ShopVision/           # 检索样本：tsv / jsonl / lmdb
│       │       ├── train_imgs.tsv
│       │       ├── train_texts.jsonl
│       │       ├── valid_imgs.tsv
│       │       ├── valid_texts.jsonl
│       │       ├── test_imgs.tsv
│       │       ├── test_texts.jsonl
│       │       └── lmdb/             # build_lmdb_dataset.py 的产出
│       ├── pretrained_weights/
│       │   └── clip_cn_vit-b-16.pt   # 预训练权重（约 750MB）
│       ├── experiments/              # finetune 的日志与 ckpt
│       └── id_mapping.csv            # item_id ↔ 数字 id 映射表
├── scripts/
│   └── build_retrieval_dataset.py    # 本次新增脚本（第 8 节第①步）
└── docs/
    └── Chinese-CLIP介绍与使用指南.md  # 本文档
```

约定：

- **权重、LMDB、训练产出都是大文件，不入库**，已在 `.gitignore` 里排除；`id_mapping.csv` 和脚本入库。
- 下文命令中的 `${DATAPATH}` 一律指 `data\processed_data_retrieval`，PowerShell 里这样定义：

```powershell
cd H:\gitclone\Agent_ShopVision
$DATAPATH = "data\processed_data_retrieval"
```

---

## 6. 第一个程序：算图文相似度

安装完成后，跑通这段代码就算入门了。逻辑：给一张商品图和 4 个候选描述，看模型认为哪个最像。

```python
import torch
from PIL import Image

import cn_clip.clip as clip
from cn_clip.clip import load_from_name, available_models

print("可用模型:", available_models())

device = "cuda" if torch.cuda.is_available() else "cpu"
# 首次运行自动下载权重；本地已有则直接加载
model, preprocess = load_from_name(
    "ViT-B-16", device=device,
    download_root="data/processed_data_retrieval/pretrained_weights",
)
model.eval()

# 1) 图片 → 预处理成张量
image = preprocess(Image.open("examples/pokemon.jpeg")).unsqueeze(0).to(device)

# 2) 中文文字 → token序列（分词在内部自动完成，直接传原句）
text = clip.tokenize(["杰尼龟", "妙蛙种子", "小火龙", "皮卡丘"]).to(device)

with torch.no_grad():
    # 3) 各自编码成向量
    image_features = model.encode_image(image)   # 形状 [1, 512]
    text_features = model.encode_text(text)      # 形状 [4, 512]

    # 4) 归一化后算相似度（下游任务请用归一化后的特征）
    image_features /= image_features.norm(dim=-1, keepdim=True)
    text_features /= text_features.norm(dim=-1, keepdim=True)

    # 5) 得到"图对每段文字"的相似度，softmax 转成概率
    logits_per_image, logits_per_text = model.get_similarity(image, text)
    probs = logits_per_image.softmax(dim=-1).cpu().numpy()

print("各候选概率:", probs)
# 皮卡丘对应位置概率最大（约 0.94），模型认对了
```

**逐行讲一下发生了什么：**

1. `load_from_name` 加载模型和图片预处理流水线（缩放、裁剪、归一化都在里面）。
2. `clip.tokenize` 把中文句子切成 token 并转成数字 id——这一步是**自动的**，我们只管传原句。
3. `encode_image` / `encode_text` 各输出一个 512 维向量。
4. 归一化（除以自身长度）后，向量都在同一个"单位球面"上，此时点积 = 余弦相似度，可以直接比。
5. `get_similarity` 内部做了矩阵乘法：1 张图 × 4 段文字 → 1×4 的相似度矩阵。

换成我们自己的商品图和中文描述，把 `Image.open(...)` 和 `clip.tokenize([...])` 的内容替换掉即可。跑通后拿一张自己商品图试一试，找找感觉。

---

## 7. 数据格式详解

要让 Chinese-CLIP 在**我们自己的商品数据**上训练和评测，数据要整理成它规定的格式。一共两级：先是人可读的 `tsv + jsonl`，再转成机器读取快的 `LMDB`。

### 7.1 目标目录结构

```text
${DATAPATH}/datasets/ShopVision/
├── train_imgs.tsv          # 训练集图片
├── train_texts.jsonl       # 训练集文本（含图文配对关系）
├── valid_imgs.tsv          # 验证集图片
├── valid_texts.jsonl       # 验证集文本
├── test_imgs.tsv           # 测试集图片
└── test_texts.jsonl        # 测试集文本
```

（train/valid/test 即训练/验证/测试三个划分，建议按 **8:1:1** 切分。）

### 7.2 图片文件 `*_imgs.tsv`

每行一张图，**图片 id** 和**图片的 base64 编码**用 Tab 键隔开：

```text
1000002	/9j/4AAQSkZJR...YQj7314oA//2Q==
```

- 左边：图片 id，**整数**。
- 右边：图片文件内容的 base64 字符串（一串乱码一样的字符，是图片的另一种表示方式，方便塞进文本文件）。
- 之所以不直接存图片文件：训练时要随机读取几千上万张图，一个个小文件读取很慢，打包成一个大文件快得多。

图片转 base64 的代码（转换脚本里会用到）：

```python
import base64

with open("商品图.jpg", "rb") as f:
    base64_str = base64.b64encode(f.read()).decode("utf-8")
```

### 7.3 文本文件 `*_texts.jsonl`

每行一个 JSON 对象，字段如下：

```json
{"text_id": 8428, "text": "女士真皮小板鞋 白色 真皮", "image_ids": [1076345, 517602]}
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `text_id` | 整数 | 文本 id，全局唯一 |
| `text` | 字符串 | 中文检索文本（用户会拿来搜的词句） |
| `image_ids` | 整数列表 | 这段文字对应的图片 id（一条文字可配多张图） |

> 如果某个划分只有文字、不知道配对关系（比如纯测试），`image_ids` 写空列表 `[]`。

### 7.4 我们的数据怎么对上

输入是 `data/processed_data_cleaning/` 九个类别目录下各自的 `products.csv`（清洗通过的 9,393 条）：

| products.csv 的列 | 用在哪 |
|---|---|
| `item_id`（如 `muge_916`） | 与数字 id 的互查关系写入 `${DATAPATH}/id_mapping.csv` |
| `item_name` + `type` + `color` + `material` | 拼成 `text` 字段的检索文本 |
| `description`（清洗改写后的模板文本） | 备选文本或拼接素材 |
| `local_image_path` | 按路径读图，转 base64 进 `*_imgs.tsv` |

**示例**：`data/processed_data_cleaning/鞋/products.csv` 中的一行：

| 字段 | 值 |
|---|---|
| item_id | `muge_916` |
| item_name | 女士真皮小板鞋 |
| type | 女士小板鞋 |
| color | 白色、黑色 |
| material | 真皮 |
| local_image_path | `data/processed_data_cleaning/鞋/images/muge_916__916.jpg` |

应产出：

```text
（train_imgs.tsv 中）
2000001	/9j/4AAQSkZJR...

（train_texts.jsonl 中）
{"text_id": 2000001, "text": "女士真皮小板鞋，女士小板鞋，颜色：白色、黑色，材质：真皮", "image_ids": [2000001]}
```

**同一行在 `id_mapping.csv` 中的记录：**

```csv
numeric_id,item_id,product_type,split
2000001,muge_916,鞋,train
```

> **重要**：检索文本务必读 `processed_data_cleaning/`（清洗后的 color/material/description），不要读 `processed_data/` 正式表——正式表里这几个字段还是来源原文，没有清洗改写。这是 README 进度表里特意标注的点。

### 7.5 LMDB 打包

tsv/jsonl 准备好后，一条命令打包：

```powershell
python H:\gitclone\Chinese-CLIP\cn_clip\preprocess\build_lmdb_dataset.py `
    --data_dir "$DATAPATH\datasets\ShopVision" `
    --splits train,valid,test
```

完成后目录下多出 `lmdb/train`、`lmdb/valid`、`lmdb/test`，各含 `imgs` 和 `pairs` 两部分。到这一步，**「中文图文检索样本」就算做完了**。

---

## 8. 接入 Agent_ShopVision 的完整流程

整体路线图（前四步产出检索基线，即实验 2 的前半；后两步是进阶）：

```text
清洗通过的 9,393 条 (data/processed_data_cleaning/)
        │
        ① scripts/build_retrieval_dataset.py：拼检索文本、图片转 base64、8:1:1 切分
        ▼
   data/processed_data_retrieval/datasets/ShopVision/  (tsv + jsonl + id_mapping.csv)
        │
        ② build_lmdb_dataset.py 打包
        ▼
   LMDB 数据集
        │
        ③ extract_features.py 抽取图文特征（用预训练 ViT-B-16，zero-shot）
        ▼
   *.img_feat.jsonl / *.txt_feat.jsonl（每条一个 512 维向量）
        │
        ④ make_topk_predictions.py + evaluation.py
        ▼
   检索基线成绩（Recall@1/5/10、MRR）──→ 实验 2 基线部分完成
        │
        ⑤ （可选）finetune 微调 → 重复 ③④ 对比提升
        │
        ⑥ （实验 3）ONNX/TensorRT 导出加速 → 供前后端与 Agent 调用
```

### 第 ① 步：生成检索样本（待编写：`scripts/build_retrieval_dataset.py`）

这是目前唯一需要写代码的环节，README 进度表中的「中文图文检索样本」指的就是它。

**输入**：`data/processed_data_cleaning/*/products.csv`（九个类别）+ 对应 `images/` 目录
**输出**：`${DATAPATH}/datasets/ShopVision/` 下六个数据文件 + `${DATAPATH}/id_mapping.csv`
**要点**：

1. 检索文本拼接规则：`"{item_name}，{type}，颜色：{color}，材质：{material}"`，字段缺失就跳过该段；
2. `item_id` 与数字 id 的映射写入 `id_mapping.csv`（后续把检索结果翻译回商品要用）；
3. 切分建议按 `item_id` 哈希取模做 8:1:1，保证同一商品的图文永远落在同一划分，不泄漏；
4. 图片读不出来（`image_status != ok`）的行直接跳过并记日志。

### 第 ② 步：打包 LMDB

见 [7.5 节](#75-lmdb-打包)，一条命令。

### 第 ③ 步：抽取图文特征

```powershell
cd H:\gitclone\Chinese-CLIP
$env:PYTHONPATH = "$env:PYTHONPATH;H:\gitclone\Chinese-CLIP\cn_clip"

$split = "valid"   # 先跑验证集试流程，再换 test / train
$resume = "H:\gitclone\Agent_ShopVision\$DATAPATH\pretrained_weights\clip_cn_vit-b-16.pt"

python -u cn_clip\eval\extract_features.py `
    --extract-image-feats `
    --extract-text-feats `
    --image-data="H:\gitclone\Agent_ShopVision\$DATAPATH\datasets\ShopVision\lmdb\$split\imgs" `
    --text-data="H:\gitclone\Agent_ShopVision\$DATAPATH\datasets\ShopVision\${split}_texts.jsonl" `
    --img-batch-size=32 `
    --text-batch-size=32 `
    --context-length=52 `
    --resume=$resume `
    --vision-model=ViT-B-16 `
    --text-model=RoBERTa-wwm-ext-base-chinese
```

产出（默认在数据集目录下）：

- `valid_imgs.img_feat.jsonl`：每行 `{"image_id": ..., "feature": [512 个浮点数]}`
- `valid_texts.txt_feat.jsonl`：每行 `{"text_id": ..., "feature": [512 个浮点数]}`

这些向量就是商品库的"指纹库"，实验 4/5 的向量检索服务直接用它建 FAISS/Chroma 索引。

### 第 ④ 步：检索与评测（产出基线成绩）

**文搜图 top-k 召回：**

```powershell
python -u cn_clip\eval\make_topk_predictions.py `
    --image-feats="H:\gitclone\Agent_ShopVision\$DATAPATH\datasets\ShopVision\${split}_imgs.img_feat.jsonl" `
    --text-feats="H:\gitclone\Agent_ShopVision\$DATAPATH\datasets\ShopVision\${split}_texts.txt_feat.jsonl" `
    --top-k=10 `
    --eval-batch-size=32768 `
    --output="H:\gitclone\Agent_ShopVision\$DATAPATH\datasets\ShopVision\${split}_predictions.jsonl"
```

**算分：**

```powershell
python cn_clip\eval\evaluation.py `
    "H:\gitclone\Agent_ShopVision\$DATAPATH\datasets\ShopVision\${split}_texts.jsonl" `
    "H:\gitclone\Agent_ShopVision\$DATAPATH\datasets\ShopVision\${split}_predictions.jsonl" `
    output.json
cat output.json
```

输出示例：

```json
{"success": true, "score": 85.67, "scoreJson": {"score": 85.67, "mean_recall": 85.67, "r1": 71.2, "r5": 90.5, "r10": 95.3}}
```

`r1 / r5 / r10` 即 Recall@1/5/10，`mean_recall` 是三者平均。**记下这组数，它就是实验 2 的 zero-shot 基线。**

图搜文（图片召回文字）方向类似，脚本换成 `make_topk_predictions_tr.py` + `evaluation_tr.py`，评测前先用 `transform_ir_annotation_to_tr.py` 把标注翻转方向，命令详见 Chinese-CLIP 仓库 README。

> 想看全流程的可运行版本，Chinese-CLIP 仓库里有现成笔记本 `Chinese-CLIP-on-MUGE-Retrieval.ipynb`，从数据到评测一气呵成，可对照参考。

### 第 ⑤ 步（可选）：finetune 微调

当零样本基线不够用时，在我们自己的数据上微调。模板脚本：

```bash
# 注意：训练脚本是 bash，需在 Git Bash / WSL2 / Linux 下运行
cd H:/gitclone/Chinese-CLIP
bash run_scripts/muge_finetune_vit-b-16_rbt-base.sh ${DATAPATH}
```

改脚本开头的这几处即可：

| 配置项 | 改成 |
|---|---|
| `WORKER_CNT` / `GPUS_PER_NODE` | 机器数 / 每台 GPU 数（单机单卡就 1 和 1） |
| `--train-data` / `--val-data` | 我们的 LMDB 路径 |
| `--resume` | `clip_cn_vit-b-16.pt` 的路径 |
| `--name` | 输出名，如 `shopvision_finetune_vit-b-16` |

微调注意事项：

- **batch size 与样本量**：官方默认 128/卡 × 8 卡，我们只有 9,393 条，用默认配置一个 epoch 不满一个 batch 的量级是不够看的——**务必调小 batch-size（如 32）并相应调小学习率**（对比学习对总 batch size 敏感，官方也是这么建议的）；
- 显存不够：加 `--grad-checkpointing`（重计算换显存）或 `--mask-ratio 0.3`（FLIP 策略，随机遮盖部分图像块）；
- 训练完重复第 ③④ 步，把 `--resume` 换成微调产出的 ckpt（在 `${DATAPATH}/experiments/${name}/` 下），对比基线数字。

### 第 ⑥ 步（实验 3）：部署加速

导出 ONNX / TensorRT 模型、特征抽取加速、以及 iOS 的 CoreML 转换，官方都有现成脚本，见：

- Chinese-CLIP 仓库 `deployment.md`（ONNX/TensorRT，含预训练 TensorRT 模型下载）
- `cn_clip/deploy/pytorch_to_coreml.py`（CoreML 转换）

对应我们实验 3 的量化与推理优化，以及实验 4/5 服务的线上推理部分。

---

## 9. 分工与执行安排

这一节回答三个问题：**活分成哪几大类、哪些能同时干、谁必须等谁**。

### 9.1 按"用到 Chinese-CLIP 的什么"分大类

| 大类 | 用到的模块 | 干什么 | 对应本文 |
|---|---|---|---|
| 数据类 | 格式规范 + `cn_clip/preprocess/` | 转换脚本、检索样本、LMDB | 第 7 节、第 8 节 ①② |
| 特征类 | `cn_clip` API + `cn_clip/eval/extract_features.py` | 抽图文向量 | 第 6 节、第 8 节 ③ |
| 评测类 | `cn_clip/eval/make_topk_*`、`evaluation_*` | 检索召回、Recall/MRR 记分 | 第 8 节 ④ |
| 训练类 | `run_scripts/` + `cn_clip/training/` | finetune 微调 | 第 8 节 ⑤ |
| 部署类 | `deployment.md`、`cn_clip/deploy/` | ONNX/TensorRT（实验 3） | 第 8 节 ⑥ |

### 9.2 任务包一览

| 任务包 | 内容 | 依赖 | 产出 | 工作量 | 能否与他人同时干 |
|---|---|---|---|---|---|
| **A 环境与权重** | 装 PyTorch / cn_clip、下载 `clip_cn_vit-b-16.pt`、跑通第 6 节 demo | 无 | 可用环境 + 权重 | 半天内 | ✅ 与所有人并行 |
| **B 检索样本转换** | 写 `scripts/build_retrieval_dataset.py`，产出 tsv/jsonl/id_mapping | 无（先定文本拼接规则） | 6 个数据文件 + 映射表 | 1 人约 1 天 | ✅ 与 A/C 并行 |
| **C 评测方案** | 定查询口径、建实验记录模板（模型/划分/R@1/5/10/MRR/日期） | 无 | 记录模板 | 半天内，轻 | ✅ 可兼任 |
| **D LMDB 打包** | `build_lmdb_dataset.py` 一条命令 + 抽查 | **B** | `lmdb/` | 10 分钟 | 由 B 兼任 |
| **E 抽特征 + 基线** | 第 ③④ 步全流程，出基线数字 | **A + B + D** | 基线成绩（记入 C 的模板） | 半天（GPU） | ⛔ 合流点，之后才能分新活 |
| **F1 finetune** | 改训练脚本、调参、跑训练、对比基线 | **E** | 微调 ckpt + 对比数字 | 1 人盯 1–2 天 | 与 F2/F3 并行 |
| **F2 FAISS 检索原型** | 用 E 的特征建向量索引，写查询函数雏形 | **E** | 检索服务底子（实验 3/4 用） | 1 人 1–2 天 | 与 F1/F3 并行 |
| **F3 图搜文补齐** | 标注翻转 + `*_tr.py` 一套，补双向检索 | **E** | 图搜文成绩 | 半天 | 与 F1/F2 并行 |

### 9.3 依赖关系图（谁能同时干、谁要等）

```text
   ┌── A 环境与权重 ──────────────────┐
   │                                 │
开始 ├── B 样本转换 ──▶ D LMDB 打包 ──┴──▶ E 抽特征+基线 ──┬──▶ F1 finetune
   │                    （B 顺手做）     （合流点）      │
   ├── C 评测方案 ──────────────────┘（E 阶段用上）   ├──▶ F2 FAISS 原型
   │                                                  │
   └────────────（A、B、C 三条线互不干扰）──────────┴──▶ F3 图搜文
```

**硬顺序**（写代码/跑命令的先后，不可颠倒）：

```text
B → D → E → F1/F2/F3        A 必须在 E 之前就绪        C 随时可做，E 时用上
```

### 9.4 具体怎么分给人

**2 人的情况：**

| 人 | 前半程 | 后半程（E 之后） |
|---|---|---|
| 队友 1 | **B → D → E**（数据一条线顺下来，写转换的人最懂格式，后面排障快） | F1 finetune |
| 队友 2 | **A → C**（环境先跑通，顺手定评测模板，E 时帮忙核数） | F2 FAISS 原型（F3 有空再补） |

**3 人的情况：**

| 人 | 前半程 | 后半程 |
|---|---|---|
| 队友 1 | **B → D → E** | F1 finetune |
| 队友 2 | **A**（顺手把第 6 节 demo 写进文档里的示例图跑一遍） | F2 FAISS 原型 |
| 队友 3 | **C**（E 时负责记录和核对数字） | F3 图搜文 → 之后支援 F1 |

**4 人及以上**：F1 finetune 要有人全职盯（训练日志、调参、续跑），单独占一个人；其余按 3 人分。

**"一人能兼几个活" / "一人只能赶一个"：**

- 可兼任：A + C 都很轻，一个人顺手做完全没问题；D 永远由 B 兼（10 分钟的事）。
- 会占满一个人：**B**（写脚本要专注，别指望同时干别的）、**F1**（训练要盯，跑一轮几小时，中间要人看日志、决定要不要调参）。
- 名义上"占机器不占人"：E 在 GPU 上几十分钟、CPU 上 1–2 小时，挂机等就行，人可以去干 C 或 F 的准备工作。

**里程碑**：E 出基线数字 = 实验 2 基线部分完成，此时把数字填进 README 进度表。

---

## 10. 常见问题

**Q：需要自己做中文分词吗？**
不需要。`clip.tokenize(["红色男士运动鞋"])` 传原句即可，切词、转 id、定长补齐都在模型内部自动完成。只有当检索方案里用到 **BM25 这类关键词匹配**（见开发文档 14.1 节）时才需要分词工具（如 jieba）——那是另一条技术路线，与 Chinese-CLIP 无关。

**Q：特征向量有多长？**
ViT-B-16 是 **512 维**（512 个浮点数）。图片特征和文字特征长度相同、空间相同，所以能直接算距离。

**Q：没有 NVIDIA 显卡能跑吗？**
能。抽特征、检索、评测都支持 CPU，只是慢——9,393 张图 CPU 上约 1–2 小时（GPU 几分钟）。训练（第 ⑤ 步）CPU 基本不现实，需要 GPU。

**Q：显存不够怎么办？**
抽特征时把 `--img-batch-size` 调小（32 → 8）即可，速度慢一点不影响结果。训练时用 `--grad-checkpointing`。

**Q：Windows 上训练脚本跑不起来？**
训练脚本是 bash 写的，Windows 原生 PowerShell 跑不了。用 Git Bash 执行可以解决一部分；分布式训练（多卡）建议直接上 WSL2 或 Linux 机器。前面的 ①–④ 步不受影响，都是纯 Python，Windows 原生可跑。

**Q：文本字段用正式表还是清洗表？**
用**清洗表** `data/processed_data_cleaning/`。正式表的 color/material/description 是来源原文，未清洗；检索文本的质量直接决定文搜图的效果。

**Q：一条文字能对多张图吗？**
能，`image_ids` 是列表。比如同款不同色的几张图可以挂在同一段描述下。

**Q：换更大的模型要改哪里？**
下载对应 ckpt，脚本里 `--vision-model` 换成 `ViT-L-14` 等，API 里 `load_from_name` 第一个参数同步改。其他流程不变。

**Q：和 Hugging Face transformers 什么关系？**
Chinese-CLIP 的 API 也合入了 Hugging Face transformers（`ChineseCLIPModel`），习惯 HF 生态可以用那边。本项目统一用官方 `cn_clip` 包，功能一致且训练脚本配套。

**Q：为什么权重和 LMDB 不放进 git？**
体积大（权重约 750MB，LMDB 相当于全部图片打包），且都能由脚本/下载器重新生成。`.gitignore` 已排除，换机器按第 5.4 节重新下载、第 7.5 节重新打包即可。

---

## 11. 术语表

| 术语 | 又见 / 英文 | 一句话解释 |
|---|---|---|
| 向量 | 特征、embedding | 图/文内容压缩成的一串数字 |
| 编码 | encode | 图/文 → 向量的过程 |
| 归一化 | normalize | 向量缩放到长度 1，便于直接点积比较相似度 |
| 余弦相似度 | cosine similarity | 向量方向的接近程度，越大越像 |
| zero-shot | 零样本 | 不训练直接用预训练模型 |
| finetune | 微调 | 在自己数据上小步再训练 |
| checkpoint | ckpt、权重 | 模型权重存档文件（`.pt`） |
| tokenize | 分词、文本编码 | 文字切片转数字 id，模型内部自动做 |
| batch size | 批大小 | 一次前向处理的样本数，影响速度、显存、训练稳定性 |
| epoch | 轮 | 完整过一遍训练集 |
| LMDB | — | 训练用的本地键值数据库，随机读取快 |
| Recall@K | R@K | 正确答案进前 K 的比例 |
| MRR | 平均倒数排名 | 按正确答案的名次给分再平均 |
| FAISS / Chroma | 向量数据库 | 存向量、做最近邻检索的工具库 |
| ONNX / TensorRT | — | 模型导出与推理加速格式（实验 3 用） |

---

## 参考链接

| 资料 | 地址 |
|---|---|
| Chinese-CLIP 仓库（含 README、训练脚本） | <https://github.com/OFA-Sys/Chinese-CLIP> |
| 技术报告（论文） | <https://arxiv.org/abs/2211.01335> |
| 模型下载（Hugging Face） | <https://huggingface.co/OFA-Sys/chinese-clip-vit-base-patch16> |
| 模型下载（魔搭） | <https://www.modelscope.cn/models/AI-ModelScope/chinese-clip-vit-base-patch16> |
| 在线体验 Demo | <https://www.modelscope.cn/studios/damo/chinese_clip_applications/summary> |
| 本地源码（我们机器上已有） | `H:\gitclone\Chinese-CLIP` |
| 部署（ONNX/TensorRT） | 仓库内 `deployment.md` |
| 全流程笔记本（MUGE 检索示例） | 仓库内 `Chinese-CLIP-on-MUGE-Retrieval.ipynb` |

---

*本文档对应 Agent_ShopVision 进度表中的「中文图文检索样本」与「检索基线 / 模型训练」两步。检索流水线的全部产出收在 `data/processed_data_retrieval/`，脚本在 `scripts/build_retrieval_dataset.py`。*
