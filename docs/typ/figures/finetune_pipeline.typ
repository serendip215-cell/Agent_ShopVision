// 图1 Chinese-CLIP 微调训练流水线（独立 CeTZ 图，编译为 SVG 后以原尺寸嵌入报告）
// 白底透明框、灰阶线条、图表内文字五号（10.5pt）。
#import "@preview/cetz:0.3.4"

#set page(width: auto, height: auto, margin: 2mm)
#set text(font: ("Times New Roman", "SimSun"), size: 10.5pt)

#cetz.canvas(length: 1cm, {
  import cetz.draw: *
  set-style(stroke: 0.7pt + luma(30%))

  let stages = (
    "实验一清洗数据（9 类 9,393 条图文对）",
    "属性模板文本构建 + MD5 哈希 8:1:1 划分",
    "LMDB 打包（train 7520 / valid 939 / test 934）",
    "Chinese-CLIP ViT-B-16 微调（单卡 3 轮 705 步）",
    "test 评测（基线 / 未清洗直训 / 清洗微调 三组对照）",
    "用 epoch3.pt 重编码并重建 FAISS 索引",
  )
  let n = stages.len()
  for (i, s) in stages.enumerate() {
    let y = -i * 1.5
    rect((-5.4, y + 0.35), (5.4, y - 0.35), fill: none, name: "s" + str(i))
    content((0, y), s, anchor: "center")
  }
  for i in range(n - 1) {
    line("s" + str(i) + ".south", "s" + str(i + 1) + ".north", mark: (end: ">"))
  }
})
