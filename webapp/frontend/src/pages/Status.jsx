import { Button, Descriptions, Progress, Table, Tag } from 'antd'
import {
  ApiOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useApp } from '../context/AppContext'
import { CATEGORIES, INDEX_TOTAL } from '../constants/catalog'
import {
  CategoryGlyph,
  PageHeader,
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
    "model_loaded": false,
    "backend": "placeholder",
    "index_dir": "data/index_data_finetuned",
    "categories": ["包", "厨房用品", "…"],
    "dimension": 512
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
    "topk": [
      { "category": "鞋", "similarity": 0.31 },
      { "category": "包", "similarity": 0.28 }
    ]
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
  { code: 40000, http: 400, scene: '参数校验失败', ui: '输入框标红，提示检查查询词或 top_k' },
  { code: 40001, http: 400, scene: '图像格式错误 / 损坏', ui: '上传区提示 PNG / JPG / WEBP' },
  { code: 40002, http: 400, scene: '上传内容为空', ui: '提示重新选择图片' },
  { code: 40003, http: 400, scene: '向量维度与索引不一致', ui: '提示模型与索引不同源，引导状态页' },
  { code: 40004, http: 400, scene: '上传文件过大', ui: '提示压缩到 10 MB 以内' },
  { code: 40400, http: 404, scene: '路径 / 资源不存在', ui: '提示接口路径或版本不匹配' },
  { code: 40401, http: 404, scene: '类别不存在', ui: '重置类别筛选为全部' },
  { code: 40402, http: 404, scene: '索引文件缺失', ui: '提示检查索引目录' },
  { code: 50000, http: 500, scene: '未捕获服务器错误', ui: '提示稍后重试，保留重试按钮' },
  { code: 50001, http: 500, scene: '模型 / 依赖不可用', ui: '提示占位模式或 ONNX 依赖未安装' },
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
    render: (value) => <span className="sv-mono">{value.toLocaleString('zh-CN')}</span>,
  },
  {
    title: '占索引总量',
    dataIndex: 'share',
    width: 180,
    render: (value) => (
      <Progress percent={value} size="small" strokeColor="#5FA8B0" showInfo={false} />
    ),
  },
  {
    title: '状态',
    dataIndex: 'status',
    align: 'right',
    render: () => <Tag bordered={false} color="green">可检索</Tag>,
  },
]

const ERROR_COLUMNS = [
  { title: '业务码', dataIndex: 'code', render: (value) => <span className="sv-mono">{value}</span> },
  { title: 'HTTP', dataIndex: 'http', align: 'center', render: (value) => <span className="sv-mono">{value}</span> },
  { title: '场景', dataIndex: 'scene' },
  { title: '前端处理', dataIndex: 'ui' },
]

export default function Status() {
  const { health, healthLoading, healthError, refreshHealth, isPlaceholder } = useApp()

  const categoryRows = CATEGORIES.map((item) => ({
    ...item,
    count: health?.category_counts?.[item.key] ?? item.count,
    status: 'ok',
  }))
  const indexTotal = health?.total_items ?? INDEX_TOTAL
  const rowsWithShare = categoryRows.map((item) => ({
    ...item,
    share: Math.round((item.count / indexTotal) * 1000) / 10,
  }))

  return (
    <div className="sv-status-page">
      <PageHeader
        eyebrow="System Console · API Contract"
        title="系统状态与接口"
        description="模型、索引和接口契约集中在这里。答辩前先看这一页，确认后端到底加载了什么。"
        meta={
          <>
            <Tag bordered={false}>GET /api/v1/health</Tag>
            <Tag bordered={false}>统一返回体 { '{ code, result, msg }' }</Tag>
            {isPlaceholder && <Tag color="orange">占位模式</Tag>}
          </>
        }
        actions={
          <Button icon={<ReloadOutlined spin={healthLoading} />} onClick={refreshHealth}>
            刷新状态
          </Button>
        }
      />

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
                    <Tag bordered={false} color={isPlaceholder ? 'orange' : 'green'}>
                      {isPlaceholder ? '占位模式' : '模型在线'}
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
                  children: health?.model_loaded ? '是' : '否',
                },
                {
                  key: 'dim',
                  label: '向量维度',
                  children: <span className="sv-mono">{health?.dimension ?? '—'}</span>,
                },
                {
                  key: 'categories',
                  label: '类别数量',
                  children: <span className="sv-mono">{health?.categories?.length ?? 0}</span>,
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
              <strong>{health?.backend === 'onnx' ? 'ONNX Runtime' : '占位编码器'}</strong>
            </div>
            <div>
              <span>索引版本</span>
              <strong>epoch3.pt 微调索引</strong>
            </div>
            <div>
              <span>索引条数</span>
              <strong className="sv-mono">{indexTotal.toLocaleString('zh-CN')}</strong>
            </div>
            <div>
              <span>数据来源</span>
              <strong>MUGE / Amazon / 苏宁</strong>
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
          extra={<span className="sv-muted">构建时快照，后端提供统计后自动更新</span>}
        />
        <Table
          rowKey="key"
          columns={CATEGORY_COLUMNS}
          dataSource={rowsWithShare}
          pagination={false}
          size="middle"
          scroll={{ x: 640 }}
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
