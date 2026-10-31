// 图1 推理加速与双塔 ONNX 部署流水线（独立 CeTZ 图，编译为 SVG 后以原尺寸嵌入报告）
// 风格沿用 docs/typ/figures/finetune_pipeline.typ：灰阶线条、浅填充、图表内文字五号（10.5pt）。
// 编译：docs/typst/typst.exe compile --format svg docs/typ/figures/acceleration_pipeline.typ docs/typ/figures/acceleration_pipeline.svg
#import "@preview/cetz:0.3.4"

#set page(width: auto, height: auto, margin: 2mm)
#set text(font: ("Times New Roman", "SimSun"), size: 10.5pt)

#cetz.canvas(length: 1cm, {
  import cetz.draw: *
  set-style(stroke: 0.7pt + luma(30%))

  let stages = (
    "实验二微调权重 epoch3.pt（ViT-B-16 + RoBERTa 双塔）",
    "图像塔导出 ONNX（固定 224×224，batch 动态）",
    "文本塔导出 ONNX（batch 与序列长度动态）",
    "FP32 ONNX 图层面转 FP16（keep_io_types=False）",
    "推理后端：ORT-CPU（FP32）/ ORT-CUDA / TensorRT（FP16）",
    "同硬件配对测速：batch 1/32，预热 10 / 计时 20 取中位数",
    "934 条双塔文搜图 R@K，与同源 FP32 基线比对（≤1pp）",
    "生成表/图与复算入口，归档至 results/runs/",
  )
  let n = stages.len()

  // 白底：整图纯白——底层铺满不透明白，流程框内也用 white 填充（只留 0.7pt 灰描边分隔）。
  // 底层矩形与流程框外沿齐平，不撑大画布。
  rect((-6.1, 0.4), (6.1, -9.5), fill: white, stroke: none)

  for (i, s) in stages.enumerate() {
    let y = -i * 1.3
    rect((-6.1, y + 0.4), (6.1, y - 0.4), fill: white, name: "s" + str(i))
    content((0, y), s, anchor: "center")
  }
  for i in range(n - 1) {
    line("s" + str(i) + ".south", "s" + str(i + 1) + ".north", mark: (end: ">"))
  }
})