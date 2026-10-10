// 图1 数据采集与预处理流水线（独立 CeTZ 图，编译为 SVG 后以原尺寸嵌入报告）
// 灰阶风格、图表内文字五号（10.5pt），依据 apaper-creating-figures 规程。
#import "@preview/cetz:0.3.4"

#set page(width: auto, height: auto, margin: 2mm)
#set text(font: ("Times New Roman", "SimSun"), size: 10.5pt)

#cetz.canvas(length: 1cm, {
  import cetz.draw: *
  set-style(stroke: 0.6pt + luma(35%))

  let stages = (
    "原始数据（MUGE / Amazon / 苏宁）",
    "Amazon 英文字段 DeepL 中文翻译",
    "字段统一与九类归并（SHA-256 去重）",
    "图片技术质检（image_status）",
    "商品抠图（ISNet 背景移除）",
    "视觉属性清洗（GPT 审核，阈值 0.72）",
    "标准化数据集（九类目 products.csv）",
  )
  let n = stages.len()
  for (i, s) in stages.enumerate() {
    let y = -i * 1.2
    rect((-4.8, y + 0.4), (4.8, y - 0.4), fill: luma(88%), name: "s" + str(i))
    content((0, y), s, anchor: "center")
  }
  for i in range(n - 1) {
    line("s" + str(i) + ".south", "s" + str(i + 1) + ".north", mark: (end: ">"))
  }
})
