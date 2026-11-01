# webapp/frontend — React 应用

负责人：张梓萱（zzx）+ 刘凡思雨（lfsy），两人共同完成（页面架构/组件、三页面交互、兼容与测试分担）。三个页面、公共组件、Axios 封装与运行命令见 [上级文档](../README.md)。

## 运行

```bash
cd webapp/frontend && npm install && npm run dev   # http://localhost:5173
npm run build                                       # 产物输出 dist/
```

Vite 已配置 `/api` → `http://localhost:8000` 代理，前端不用改 baseURL。

## 技术栈

React 19 · Vite 5 · Ant Design 5 · React Router 7 · Axios；样式为纯 CSS 设计令牌（不依赖 CSS 框架），动效全部 CSS/rAF 手写。

## 页面与路由

| 路由 | 页面 | 作用 | 接口 |
| --- | --- | --- | --- |
| `/` | [Overview.jsx](src/pages/Overview.jsx) | 首页：搜索横幅 + 指标栏（计数动画）+ 9 类商品照片矩阵 + 最近运行 | `GET /health` |
| `/image` | [ImageLab.jsx](src/pages/ImageLab.jsx) | 图像分类：拖拽上传/示例图 → 置信度结果卡、Top3 候选条形图、通俗解读、批量连续测试与页内历史 | `POST /image` |
| `/text` | [TextSearch.jsx](src/pages/TextSearch.jsx) | 文本检索：中文查询 + 类别限定 + top_k → 商品列表 | `POST /text` |
| `/match` | [MatchLab.jsx](src/pages/MatchLab.jsx) | 图文匹配：图/文两路独立判类 + 一致性结论 + 检索证据 | `POST /match` |
| `/history` | [History.jsx](src/pages/History.jsx) | 运行记录（管理员）：localStorage 持久化，可重放/导出 JSON | — |
| `/status` | [Status.jsx](src/pages/Status.jsx) | 系统状态（管理员）：health、索引明细、接口契约、错误码表 | `GET /health` |

`/history`、`/status` 由 [RequireAdmin](src/components/auth/RequireAdmin.jsx) 包裹，未登录展示解锁入口。跨页交接：文本走 URL 参数 `q`，图片走 WorkflowContext（内存 File + 预览地址）。

## 目录结构

```
src/
├── api/client.js            # Axios 实例：统一返回体 {code, result, msg} 拦截，错误翻成 AppError
├── components/
│   ├── auth/                # 登录弹窗、管理员路由守卫
│   ├── common/              # Ui.jsx（空态/分区标签等原子件）、RunRow 运行轨迹行
│   ├── input/               # 上传/查询输入组件
│   ├── layout/AppShell.jsx  # 顶栏（全局搜索、健康徽标、导航、面包屑）+ 出口
│   └── result/Results.jsx   # 检索结果卡片（/items/{item_id}.jpg 图源 + 兜底色块）
├── constants/catalog.js     # 9 类目数据、类别识别色、示例图/示例查询（图与类属经双重核验）
├── context/
│   ├── AppContext.jsx       # 健康状态、模型占位标记、运行历史（localStorage）
│   ├── AuthContext.jsx      # 管理员登录态
│   └── WorkflowContext.jsx  # 图像分类 → 图文匹配 的图片交接
├── pages/                   # 上表 6 个路由页 + NotFound
├── styles/global.css        # 全部样式：设计令牌 + 分区注释（壳/首页/三功能页/动效）
├── theme/antdTheme.js       # AntD 主题 token（主色/圆角/字体对齐设计令牌）
└── utils/                   # errors/samples/format/storage + useCountUp（计数动画，首页与图像页共用）
```

## 视觉与动效约定

- 设计令牌集中在 `global.css` 顶部 `:root`：主色 `#5FA8B0` 系（soft/deep/ink）、暖橙警示、背景 `#FBFCFE`、文字/边框灰阶、圆角与阴影三档。
- 动效克制：入场 `sv-fade-up`/`sv-pop`、悬浮只变色不放大、数字一律 `useCountUp` 缓动；`prefers-reduced-motion` 全局降级。
- 玻璃拟态（图像分类页）：`rgba 白 + backdrop-filter blur`，仅 `sv-il-glass` 一处体系。

## 当前状态

后端 `SHOPVISION_MODEL_BACKEND=placeholder` 时页面正常出数，但结果无参考意义（页内挂暖色提示）；真模型产物切换见仓库根 `scripts/fetch_model_assets.py`。
