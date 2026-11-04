import { Button, Descriptions, Progress, Table, Tag } from 'antd'
import {
  ApiOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  PictureOutlined,
  ReloadOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import {
  CategoryGlyph,
  SectionLabel,
} from '../components/common/Ui'

const ENDPOINTS = [
  {
    method: 'GET',
    path: '/api/v1/health',
    title: '健康检查',
    description: '读取当前编码器后端、索引目录、类别与向量维度。',
    request: '无请求体',
    response: `{
  "code": 0,
  "result": {
    "model_loaded": true,
    "backend": "onnx",
    "index_dir": "data/index_data_finetuned",
    "categories": ["包", "厨房用品", "…"],
    "dimension": 512,
    "category_counts": { "鞋": 3219, "…": 0 },
    "total_items": 9393,
    "category_ready": { "鞋": true, "…": true },
    "updated_at": "2026-10-18T13:50:44Z",
    "model_name": "ViT-B-16",
    "model_checkpoint": "…/checkpoints/epoch3.pt"
  },
  "msg": "ok"
}`,
  },
  {
    method: 'POST',
    path: '/api/v1/image',
    title: '图像分类',
    description: '上传商品图，返回最可能类别、置信度和前三类别分数。',
    request: 'multipart/form-data: file',
    response: `{
  "code": 0,
  "result": {
    "category": "鞋",
    "confidence": 0.42,
    "score": 0.31,
    "attributes": { "type": "女士小板鞋", "color": "白色", "material": "网面" },
    "topk": [
      { "category": "鞋", "similarity": 0.31, "confidence": 0.42 },
      { "category": "包", "similarity": 0.28, "confidence": 0.33 }
    ],
    "items": [ { "category": "鞋", "similarity": 0.92, "item_name": "…" } ]
  },
  "msg": "ok"
}`,
  },
  {
    method: 'POST',
    path: '/api/v1/text',
    title: '文本检索',
    description: '中文查询在指定类别或全部类别中检索相似商品。',
    request: `application/json:
{ "query": "白色运动鞋", "top_k": 5, "category": "鞋" }`,
    response: `{
  "code": 0,
  "result": {
    "query": "白色运动鞋",
    "category": "鞋",
    "query_category": "鞋",
    "query_score": 0.63,
    "items": [
      {
        "category": "鞋",
        "similarity": 0.63,
        "item_name": "…",
        "item_id": "…"
      }
    ]
  },
  "msg": "ok"
}`,
  },
  {
    method: 'POST',
    path: '/api/v1/match',
    title: '图文匹配',
    description: '图像与文本各自判类别，返回是否一致及文本侧证据。',
    request: 'multipart/form-data: file + text + top_k',
    response: `{
  "code": 0,
  "result": {
    "match": false,
    "image_category": "鞋",
    "text_category": "包",
    "items": [ "…" ]
  },
  "msg": "ok"
}`,
  },
  {
    method: 'POST',
    path: '/api/v1/admin/items',
    title: '上传商品入库',
    description:
      '只传 file 返回建议，不写库；confirm=true 且带 category 才写；create_category=true 自动建类。',
    request: `multipart/form-data:
{ "file": "…", "category": "鞋", "confirm": "true", "create_category": "false", "item_name": "…" }`,
    response: `{
  "code": 0,
  "result": {
    "created": true,
    "duplicate": false,
    "item_id": "upload_…",
    "category": "鞋",
    "similarity": 0.92,
    "suggested_category": "鞋",
    "suggested_score": 0.31,
    "suggested_attributes": { "type": "女士小板鞋", "color": "白色", "material": "网面" },
    "topk": [ { "category": "鞋", "similarity": 0.31 } ],
    "created_at": "…",
    "item": { "item_id": "upload_…", "item_name": "…" }
  },
  "msg": "ok"
}`,
  },
  {
    method: 'POST',
    path: '/api/v1/admin/categories',
    title: '新建空类别',
    description: '只建类别、不写商品；空类别不参与自动判类，显式检索返回空。',
    request: `application/json:
{ "name": "测试类" }`,
    response: `{
  "code": 0,
  "result": { "created": true, "name": "测试类" },
  "msg": "ok"
}`,
  },
  {
    method: 'POST',
    path: '/api/v1/tasks/image',
    title: '提交单张异步分类',
    description: '大图改走任务队列：先拿 task_id，再轮询 GET /tasks/{task_id}。',
    request: 'multipart/form-data: file',
    response: `{
  "code": 0,
  "result": { "task_id": "…", "status": "PENDING", "total": null },
  "msg": "ok"
}`,
  },
  {
    method: 'POST',
    path: '/api/v1/tasks/batch',
    title: '提交批量异步分类',
    description: '单批上限 12 张，任意一张校验失败整批拒绝。',
    request: 'multipart/form-data: files（可重复）',
    response: `{
  "code": 0,
  "result": { "task_id": "…", "status": "PENDING", "total": 5 },
  "msg": "ok"
}`,
  },
  {
    method: 'GET',
    path: '/api/v1/tasks/{task_id}',
    title: '轮询任务状态',
    description: 'PENDING / PROGRESS / SUCCESS / FAILURE 四态；SUCCESS 后取 result。',
    request: '路径参数 task_id',
    response: `{
  "code": 0,
  "result": {
    "task_id": "…",
    "status": "PROGRESS",
    "progress": { "done": 2, "total": 5 },
    "result": null,
    "error": null
  },
  "msg": "ok"
}`,
  },
]

const ERROR_CODES = [
  {
    code: 40000,
    http: 400,
    scene: '参数校验失败（入库时 confirm=true 必须带 category）',
    ui: '输入框标红，提示检查查询词、top_k 或类别名',
  },
  { code: 40001, http: 400, scene: '图像格式错误 / 损坏', ui: '上传区提示 PNG / JPG / WEBP' },
  { code: 40002, http: 400, scene: '上传内容为空', ui: '提示重新选择图片' },
  { code: 40003, http: 400, scene: '向量维度与索引不一致', ui: '提示模型与索引不同源，引导状态页' },
  { code: 40004, http: 400, scene: '上传文件过大', ui: '提示压缩到 10 MB 以内' },
  { code: 40400, http: 404, scene: '路径 / 资源不存在', ui: '提示接口路径或版本不匹配' },
  {
    code: 40401,
    http: 404,
    scene: '类别不存在（入库先建类或选已有类别）',
    ui: '重置类别筛选，或先调 POST /admin/categories 建类',
  },
  { code: 40402, http: 404, scene: '索引文件缺失', ui: '提示检查索引目录' },
  { code: 50000, http: 500, scene: '未捕获服务器错误', ui: '提示稍后重试，保留重试按钮' },
  {
    code: 50001,
    http: 500,
    scene: '模型 / 依赖不可用（占位模式禁止入库）',
    ui: '提示切 ONNX，或检查 ONNX 依赖',
  },
]

const CATEGORY_COLUMNS = [
  {
    title: '类别',
    dataIndex: 'key',
    render: (value) => (
      <span className="sv-table-category">
        <CategoryGlyph category={value} size={28} />
        {value}
      </span>
    ),
  },
  {
    title: '索引条数',
    dataIndex: 'count',
    align: 'right',
    render: (value) => (
      <span className="sv-mono">{value == null ? '—' : value.toLocaleString('zh-CN')}</span>
    ),
  },
  {
    title: '占索引总量',
    dataIndex: 'share',
    width: 180,
    responsive: ['md'],
    render: (value) =>
      value == null ? (
        <span className="sv-muted">—</span>
      ) : (
        <Progress percent={value} size="small" strokeColor="#5FA8B0" showInfo={false} />
      ),
  },
  {
    title: '状态',
    dataIndex: 'ready',
    align: 'right',
    render: (value, row) =>
      row.empty ? (
        <Tag bordered={false}>空类别</Tag>
      ) : value == null ? (
        <Tag bordered={false}>未知</Tag>
      ) : value ? (
        <Tag bordered={false} color="green">可检索</Tag>
      ) : (
        <Tag bordered={false} color="red">不可检索</Tag>
      ),
  },
]

const ERROR_COLUMNS = [
  { title: '业务码', dataIndex: 'code', render: (value) => <span className="sv-mono">{value}</span> },
  { title: 'HTTP', dataIndex: 'http', align: 'center', render: (value) => <span className="sv-mono">{value}</span> },
  { title: '场景', dataIndex: 'scene' },
  { title: '前端处理', dataIndex: 'ui' },
]

export default function Status() {
  const navigate = useNavigate()
  const {
    health,
    healthLoading,
    healthError,
    refreshHealth,
    isPlaceholder,
    categories,
  } = useApp()

  const categoryRows = categories.map((key) => {
    const count = health?.category_counts?.[key] ?? null
    return {
      key,
      count,
      ready: health?.category_ready?.[key] ?? null,
      empty: count === 0,
    }
  })
  const indexTotal = health?.total_items ?? null
  const rowsWithShare = categoryRows.map((item) => ({
    ...item,
    share:
      item.count != null && indexTotal
        ? Math.round((item.count / indexTotal) * 1000) / 10
        : null,
  }))

  return (
    <div className="sv-status-page">
      <header className="sv-page-head">
        <div className="sv-page-head-lines" aria-hidden="true">
          <svg viewBox="0 0 800 200" preserveAspectRatio="none">
            <path
              d="M 0 100 C 200 60, 400 120, 800 80"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.15"
              strokeWidth="1.5"
            />
            <path
              d="M 0 130 C 250 90, 500 150, 800 110"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.1"
              strokeWidth="1"
            />
            <circle cx="300" cy="95" r="3" fill="#5fa8b0" fillOpacity="0.25" />
            <circle cx="500" cy="120" r="2.5" fill="#5fa8b0" fillOpacity="0.2" />
          </svg>
        </div>
        <div className="sv-page-head-copy">
          <span className="sv-eyebrow">SYSTEM STATUS</span>
          <h1>Check Backend Health</h1>
          <div className="sv-page-head-modes">
            <button
              type="button"
              className="sv-page-mode-chip"
              onClick={() => navigate('/image')}
            >
              <PictureOutlined />
              <span>Image</span>
            </button>
            <button
              type="button"
              className="sv-page-mode-chip"
              onClick={() => navigate('/text')}
            >
              <FileTextOutlined />
              <span>Text</span>
            </button>
            <button
              type="button"
              className="sv-page-mode-chip"
              onClick={() => navigate('/match')}
            >
              <SwapOutlined />
              <span>Similar</span>
            </button>
          </div>
        </div>
        <div className="sv-page-head-actions">
          <Button icon={<ReloadOutlined spin={healthLoading} />} onClick={refreshHealth}>
            刷新状态
          </Button>
        </div>
      </header>

      <div className="sv-status-grid sv-reveal">
        <section className="sv-card">
          <SectionLabel index="01" title="模型与索引" extra={<CloudServerOutlined />} />
          {healthError ? (
            <div className="sv-health-error">
              <strong>无法读取 /health</strong>
              <p>请确认后端已启动：uvicorn app.main:app --reload --port 8000。</p>
              <Button size="small" onClick={refreshHealth}>重新检查</Button>
            </div>
          ) : (
            <Descriptions
              column={1}
              size="small"
              items={[
                {
                  key: 'state',
                  label: '当前状态',
                  children: (
                    <Tag
                      bordered={false}
                      color={!health ? 'default' : isPlaceholder ? 'orange' : 'green'}
                    >
                      {!health ? '检查中' : isPlaceholder ? '占位模式' : '模型在线'}
                    </Tag>
                  ),
                },
                {
                  key: 'backend',
                  label: '编码器后端',
                  children: <span className="sv-mono">{health?.backend || '—'}</span>,
                },
                {
                  key: 'loaded',
                  label: '模型已加载',
                  children: health ? (health.model_loaded ? '是' : '否') : '—',
                },
                {
                  key: 'dim',
                  label: '向量维度',
                  children: <span className="sv-mono">{health?.dimension ?? '—'}</span>,
                },
                {
                  key: 'categories',
                  label: '类别数量',
                  children: (
                    <span className="sv-mono">{health?.categories?.length ?? '—'}</span>
                  ),
                },
                {
                  key: 'index',
                  label: '索引目录',
                  children: <span className="sv-mono sv-break">{health?.index_dir || '—'}</span>,
                },
              ]}
            />
          )}
        </section>

        <section className="sv-card">
          <SectionLabel index="02" title="运行环境说明" extra={<DatabaseOutlined />} />
          <div className="sv-env-list">
            <div>
              <span>运行模式</span>
              <strong>
                {health
                  ? health.backend === 'onnx'
                    ? 'ONNX Runtime'
                    : '占位编码器'
                  : '—'}
              </strong>
            </div>
            <div>
              <span>索引版本</span>
              <strong>
                {[
                  health?.model_name,
                  health?.model_checkpoint
                    ? String(health.model_checkpoint).split(/[\\/]/).pop()
                    : null,
                ]
                  .filter(Boolean)
                  .join(' · ') || '—'}
              </strong>
            </div>
            <div>
              <span>索引条数</span>
              <strong className="sv-mono">
                {indexTotal == null ? '—' : indexTotal.toLocaleString('zh-CN')}
              </strong>
            </div>
            <div>
              <span>构建时间</span>
              <strong className="sv-mono">{health?.updated_at || '—'}</strong>
            </div>
          </div>
          <div className="sv-note sv-note-warm">
            <strong>报告口径红线</strong>
            <p>
              占位模式下不写实测推理延迟与检索指标。真实 ONNX 上线后，再记录 CPU ORT 或 GPU TRT
              的机器与耗时，CPU / GPU 数字不混算。
            </p>
          </div>
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
            <Button block icon={<ApiOutlined />}>打开 FastAPI 自动文档 /docs</Button>
          </a>
        </section>
      </div>

      <section className="sv-card sv-reveal">
        <SectionLabel
          index="03"
          title={`${rowsWithShare.length} 类索引明细`}
          extra={<span className="sv-muted">来自 /health：静态索引 + 上传入库</span>}
        />
        <Table
          rowKey="key"
          columns={CATEGORY_COLUMNS}
          dataSource={rowsWithShare}
          pagination={false}
          size="middle"
        />
      </section>

      <section className="sv-card sv-reveal">
        <SectionLabel index="04" title="接口清单" extra={<ApiOutlined />} />
        <div className="sv-endpoint-grid">
          {ENDPOINTS.map((endpoint) => (
            <article className="sv-endpoint-card" key={endpoint.path}>
              <div className="sv-endpoint-head">
                <span className={`sv-method ${endpoint.method === 'GET' ? 'is-get' : 'is-post'}`}>
                  {endpoint.method}
                </span>
                <span className="sv-mono sv-endpoint-path">{endpoint.path}</span>
              </div>
              <h3>{endpoint.title}</h3>
              <p>{endpoint.description}</p>
              <div className="sv-endpoint-block">
                <span>请求</span>
                <pre>{endpoint.request}</pre>
              </div>
              <div className="sv-endpoint-block">
                <span>返回</span>
                <pre>{endpoint.response}</pre>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="sv-card sv-reveal">
        <SectionLabel index="05" title="错误码与前端处理" extra={<span className="sv-muted">业务码前三位 = HTTP</span>} />
        <Table
          rowKey="code"
          columns={ERROR_COLUMNS}
          dataSource={ERROR_CODES}
          pagination={false}
          size="middle"
          scroll={{ x: 720 }}
        />
      </section>
    </div>
  )
}
