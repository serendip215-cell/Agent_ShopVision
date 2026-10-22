// 图2 Chinese-CLIP 双塔模型架构（独立 CeTZ 图，编译为 SVG 后以原尺寸嵌入报告）
// 白底透明框、灰阶线条、图表内文字五号（10.5pt）。
#import "@preview/cetz:0.3.4"

#set page(width: auto, height: auto, margin: 2mm)
#set text(font: ("Times New Roman", "SimSun"), size: 10.5pt)

#cetz.canvas(length: 1cm, {
  import cetz.draw: *
  set-style(stroke: 0.7pt + luma(30%))

  // 双塔输入
  rect((-6.0, 0.4), (-0.8, -0.4), fill: none, name: "img")
  content((-3.4, 0), "商品图片", anchor: "center")
  rect((0.8, 0.4), (6.0, -0.4), fill: none, name: "txt")
  content((3.4, 0), "属性模板文本", anchor: "center")

  // 编码塔
  rect((-6.0, -1.7), (-0.8, -2.5), fill: none, name: "vt")
  content((-3.4, -2.1), "ViT-B-16 视觉塔", anchor: "center")
  rect((0.8, -1.7), (6.0, -2.5), fill: none, name: "tt")
  content((3.4, -2.1), "RoBERTa-wwm 文本塔", anchor: "center")

  // 特征
  rect((-6.0, -3.7), (-0.8, -4.5), fill: none, name: "if")
  content((-3.4, -4.1), "图像特征（512 维）", anchor: "center")
  rect((0.8, -3.7), (6.0, -4.5), fill: none, name: "tf")
  content((3.4, -4.1), "文本特征（512 维）", anchor: "center")

  // 归一化与损失
  rect((-4.2, -5.7), (4.2, -6.5), fill: none, name: "sim")
  content((0, -6.1), "L2 归一化 · 余弦相似度矩阵", anchor: "center")
  rect((-4.2, -7.7), (4.2, -8.5), fill: none, name: "loss")
  content((0, -8.1), "双向 InfoNCE 对比损失", anchor: "center")

  // 塔内与汇聚连线（汇聚线分别落在 sim 顶边两个入口，避免箭头叠穿）
  line("img.south", "vt.north", mark: (end: ">"))
  line("txt.south", "tt.north", mark: (end: ">"))
  line("vt.south", "if.north", mark: (end: ">"))
  line("tt.south", "tf.north", mark: (end: ">"))
  line("if.south", (-1.6, -5.7), mark: (end: ">"))
  line("tf.south", (1.6, -5.7), mark: (end: ">"))
  line("sim.south", "loss.north", mark: (end: ">"))

  // 微调回传（虚线经外侧通道从两塔侧边进入，不穿过任何框体）
  line("loss.west", (-6.8, -8.1), stroke: (dash: "dashed"))
  line((-6.8, -8.1), (-6.8, -2.1), stroke: (dash: "dashed"))
  line((-6.8, -2.1), "vt.west", stroke: (dash: "dashed"), mark: (end: ">"))
  line("loss.east", (6.8, -8.1), stroke: (dash: "dashed"))
  line((6.8, -8.1), (6.8, -2.1), stroke: (dash: "dashed"))
  line((6.8, -2.1), "tt.east", stroke: (dash: "dashed"), mark: (end: ">"))
  content((0, -9.3), "梯度回传 · 双塔全参微调", anchor: "center")
})
