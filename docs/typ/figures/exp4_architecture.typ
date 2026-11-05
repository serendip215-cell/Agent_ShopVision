// 实验四：前后端总体架构与数据流（独立 CeTZ 图，编译为 SVG 后以原尺寸嵌入报告）
// 风格沿用 docs/typ/figures/acceleration_pipeline.typ：浅填充 + 灰阶描边、图内文字五号。
// 编译：docs/typst/typst.exe compile docs/typ/figures/exp4_architecture.typ docs/typ/figures/exp4_architecture.svg
#import "@preview/cetz:0.3.4"

#set page(width: auto, height: auto, margin: 2mm)
#set text(font: ("Times New Roman", "SimSun"), size: 10.5pt, lang: "zh")

#cetz.canvas(length: 1cm, {
  import cetz.draw: *

  let c-browser = rgb("#E8F3F5")
  let c-api     = rgb("#EAF0F8")
  let c-svc     = rgb("#F3F0E8")
  let c-core    = rgb("#EFEAF6")
  let c-data    = rgb("#E9F2E9")
  let c-edge    = rgb("#4C7C86")
  let c-gray    = rgb("#8A8A8A")
  let t5 = 10.5pt

  // ---------------- 浏览器（表现层） ----------------
  rect((-8.2, 0.2), (-4.0, -8.4), fill: c-browser, stroke: (paint: c-edge, thickness: 0.9pt))
  content((-6.1, -0.1), anchor: "center", text(size: t5, weight: "bold")[浏览器（React 19 单页应用）])

  let pages = ("工作台 / 检索入口", "图像分类页", "文本检索页", "图文匹配页", "商品入库", "运行记录 · 系统状态")
  for (i, p) in pages.enumerate() {
    let y = -1.15 - i * 1.02
    rect((-7.8, y + 0.33), (-4.4, y - 0.33), fill: white, stroke: (paint: c-gray, thickness: 0.6pt))
    content((-6.1, y), anchor: "center", text(size: t5)[#p])
  }
  rect((-7.8, -7.95), (-4.4, -7.45), fill: white, stroke: (paint: c-gray, thickness: 0.6pt))
  content((-6.1, -7.7), anchor: "center", text(size: t5 - 1pt)[Axios 拦截器 · 统一返回体解包])

  // ---------------- Vite 代理 ----------------
  rect((-3.5, -3.55), (-2.1, -4.75), fill: white, stroke: (paint: c-gray, thickness: 0.7pt))
  content((-2.8, -4.15), anchor: "center", text(size: t5 - 0.5pt)[Vite 代理\n/api])

  // ---------------- 后端 ----------------
  rect((-1.6, 0.2), (7.6, -8.4), fill: c-api, stroke: (paint: c-edge, thickness: 0.9pt))
  content((3.0, -0.1), anchor: "center", text(size: t5, weight: "bold")[后端（FastAPI + Uvicorn）])

  // 接入层
  rect((-1.2, -0.55), (7.2, -1.95), fill: white, stroke: (paint: c-gray, thickness: 0.6pt))
  content((3.0, -1.25), anchor: "center", text(size: t5 - 0.5pt)[
    接入层：/api/v1 参数校验 · 统一返回体 · 错误码\
    health · image · text · match · tasks · admin
  ])

  // 服务层
  rect((-1.2, -2.3), (7.2, -3.35), fill: white, stroke: (paint: c-gray, thickness: 0.6pt))
  content((3.0, -2.82), anchor: "center", text(size: t5 - 0.5pt)[
    服务层：MatchService（编码 → 检索 → 组装） · UploadStore（增量入库）\
  ])

  // 能力层
  rect((-0.95, -3.7), (1.95, -5.25), fill: c-core, stroke: (paint: c-gray, thickness: 0.6pt))
  content((0.5, -4.47), anchor: "center", text(size: t5 - 0.5pt)[
    Encoder 接缝\
    占位 / ONNX 双塔\
  ])
  rect((2.35, -3.7), (5.55, -5.25), fill: c-core, stroke: (paint: c-gray, thickness: 0.6pt))
  content((3.95, -4.47), anchor: "center", text(size: t5 - 0.5pt)[
    IndexStore\
    9 类 · 9,393 条 · 512 维\
  ])

  // Celery
  rect((5.9, -2.4), (7.4, -3.3), fill: c-svc, stroke: (paint: c-gray, thickness: 0.6pt))
  content((6.65, -2.85), anchor: "center", text(size: t5 - 0.5pt)[Celery +\nRedis])

  // ---------------- 数据与模型 ----------------
  rect((-0.95, -5.75), (1.95, -7.05), fill: c-data, stroke: (paint: c-gray, thickness: 0.6pt))
  content((0.5, -6.4), anchor: "center", text(size: t5 - 0.5pt)[
    双塔 ONNX（图塔 / 文本塔）\
    ≈754 MB · CPU ORT\
  ])
  rect((2.35, -5.75), (5.55, -7.05), fill: c-data, stroke: (paint: c-gray, thickness: 0.6pt))
  content((3.95, -6.4), anchor: "center", text(size: t5 - 0.5pt)[
    index_data_finetuned\
    items.csv + 向量 .npy\
  ])

  // ---------------- 数据流 ----------------
  // 浏览器 → 代理 → 接入层
  line((-4.0, -3.3), (-3.5, -3.9), stroke: (paint: c-edge, thickness: 1.1pt), mark: (end: ">"))
  line((-2.1, -3.9), (-1.2, -3.3), stroke: (paint: c-edge, thickness: 1.1pt), mark: (end: ">"))
  // 响应：虚线回程
  line((-1.2, -1.5), (-2.8, -3.5), stroke: (paint: c-gray, thickness: 0.7pt, dash: "dashed"), mark: (end: ">"))
  content((-2.35, -2.15), anchor: "center", text(size: t5 - 1.5pt, fill: rgb("#555"))[{code,result,msg}])

  // 接入层 → 服务层 → 能力层
  line((3.0, -1.95), (3.0, -2.3), stroke: (paint: c-gray, thickness: 0.8pt), mark: (end: ">"))
  line((0.5, -3.35), (0.5, -3.7), stroke: (paint: c-gray, thickness: 0.8pt), mark: (end: ">"))
  line((3.95, -3.35), (3.95, -3.7), stroke: (paint: c-gray, thickness: 0.8pt), mark: (end: ">"))
  // 能力层 → 数据/模型
  line((0.5, -5.25), (0.5, -5.75), stroke: (paint: c-gray, thickness: 0.8pt), mark: (end: ">"))
  line((3.95, -5.25), (3.95, -5.75), stroke: (paint: c-gray, thickness: 0.8pt), mark: (end: ">"))
  // 接入层 ↔ Celery
  line((6.65, -1.95), (6.65, -2.4), stroke: (paint: c-gray, thickness: 0.7pt), mark: (end: ">"))

  // 图例
  content((3.0, -8.75), anchor: "center", text(size: t5 - 1.5pt, fill: rgb("#555"))[
    实线＝请求方向　虚线＝响应　「接缝」＝由 SHOPVISION_MODEL_BACKEND 切换的两档实现
  ])
})