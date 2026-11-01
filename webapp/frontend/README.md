# webapp/frontend — React 应用

负责人：张梓萱（zzx）+ 刘凡思雨（lfsy），两人共同完成（页面架构/组件、三页面交互、兼容与测试分担）。三个页面、公共组件、Axios 封装与运行命令见 [上级文档](../README.md)。

## 运行

```bash
cd webapp/backend && uvicorn app.main:app --reload --port 8000
cd webapp/frontend && npm install && npm run dev   # http://localhost:5173
```

Vite 已配置 `/api` → `http://localhost:8000` 代理，前端不需要改 baseURL。

## 页面

| 路由 | 页面 | 接口 |
| --- | --- | --- |
| `/` | 工作台（系统概览、索引规模、演示路线、最近运行） | `GET /health` |
| `/image` | 图像分类（上传/示例图 → 类别 + 置信度 + 前三类别） | `POST /image` |
| `/text` | 文本检索（查询词 + 类别 + top_k → 商品列表） | `POST /text` |
| `/match` | 图文匹配（图 + 文分别判类，再比对一致性） | `POST /match` |
| `/history` | 运行记录（localStorage 保存，可重放/导出 JSON） | — |
| `/status` | 系统状态（health、索引明细、接口契约、错误码表） | `GET /health` |

跨页交接：文本走 URL 参数 `q`，图片走 `WorkflowContext`（内存中 File + 预览地址）。

## 视觉

浅松石绿 `#DDEFEF` / 柔和湖蓝 `#5FA8B0` / 暖橙 `#F7D9C4` / 薄荷 `#DFF3E4` / 珊瑚 `#F7D7D7`，背景 `#FAFBFC`、卡片 `#FFFFFF`、文字 `#2F353A` / `#6B7280`、边框 `#ECEFF1`。AntD token 见 `src/theme/antdTheme.js`，全局样式变量见 `src/styles/global.css`。