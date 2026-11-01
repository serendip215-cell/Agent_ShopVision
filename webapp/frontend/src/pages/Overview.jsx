import { Button, Skeleton, Tag } from 'antd'
import {
  ArrowRightOutlined,
  BlockOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  PictureOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  CATEGORIES,
  DEMO_PAIRS,
  INDEX_TOTAL,
  SAMPLE_QUERIES,
  TOTAL_PRODUCTS,
} from '../constants/catalog'
import { useApp } from '../context/AppContext'
import {
  CategoryGlyph,
  EmptyState,
  PageHeader,
  SectionLabel,
  StatBlock,
} from '../components/common/Ui'
import RunRow from '../components/common/RunRow'

const CAPABILITIES = [
  {
    key: 'image',
    title: '图像分类',
    description: '上传一张商品图，图像塔编码后与 9 类索引比对，给出最可能的类别与置信度。',
    icon: <PictureOutlined />,
    meta: 'POST /api/v1/image',
    action: '开始识别',
    to: '/image',
  },
  {
    key: 'text',
    title: '文本检索',
    description: '输入中文描述，文本塔编码后在商品库中找相似条目，可按类别缩小范围。',
    icon: <FileSearchOutlined />,
    meta: 'POST /api/v1/text',
    action: '搜索商品',
    to: '/text',
  },
  {
    key: 'match',
    title: '图文匹配',
    description: '图和文各自独立判断类别，再比对一致性，用来检验双塔是否真的“看懂”同一条商品。',
    icon: <BlockOutlined />,
    meta: 'POST /api/v1/match',
    action: '做一次比对',
    to: '/match',
  },
]

const DEMO_STEPS = [
  { index: '01', title: '图像分类', text: '传一张鞋图，看模型判成哪一类、置信度多少。', to: '/image' },
  { index: '02', title: '文本检索', text: '搜「白色运动鞋」，看 5 条最相似的商品。', to: '/text?q=白色运动鞋' },
  { index: '03', title: '图文匹配', text: '用同一张鞋图配「双肩包」，故意做出不一致结果。', to: '/match?demo=mismatch' },
]

export default function Overview() {
  const navigate = useNavigate()
  const { health, healthLoading, healthError, refreshHealth, isPlaceholder, history } = useApp()

  const recentRuns = history.slice(0, 5)

  function replay(run) {
    if (run.mode === 'text') {
      navigate(`/text?q=${encodeURIComponent(run.input?.query || '')}`)
      return
    }
    navigate(run.mode === 'match' ? `/match?text=${encodeURIComponent(run.input?.text || '')}` : '/image')
  }

  return (
    <div className="sv-overview">
      <PageHeader
        eyebrow="Experiment 04 · Multimodal Retrieval"
        title="把一张商品图，变成一条可检索的线索"
        description="图像分类、中文检索、图文匹配三台仪器，接在同一套 Chinese-CLIP 双塔与 9 类商品索引上。先看状态，再开始一次检索。"
        meta={
          <>
            <Tag bordered={false} color="cyan">React 19</Tag>
            <Tag bordered={false}>Chinese-CLIP 双塔</Tag>
            <Tag bordered={false}>9 类 · 9,393 条索引</Tag>
            {isPlaceholder && <Tag color="orange">占位模式</Tag>}
          </>
        }
        actions={
          <>
            <Button type="primary" size="large" onClick={() => navigate('/image')}>
              上传一张商品图
            </Button>
            <Button size="large" onClick={() => navigate('/text?q=白色运动鞋')}>
              从文本检索开始
            </Button>
          </>
        }
      />

      <section className="sv-hero sv-reveal">
        <div className="sv-hero-copy">
          <span className="sv-hero-kicker">Product Intelligence Studio</span>
          <h2>一图一文，九类商品，<br />各自编码，再一起判断。</h2>
          <p>
            前端不做业务判断，只把你的输入交给后端双塔模型。图像塔和文本塔各自输出 512 维向量，
            系统再在类别与商品层面给出可解释的结果。
          </p>
          <div className="sv-hero-actions">
            <Button type="primary" onClick={() => navigate('/image')}>
              进入图像分类
            </Button>
            <Button type="text" onClick={() => navigate('/match?demo=mismatch')}>
              看一次“不一致”示例 <ArrowRightOutlined />
            </Button>
          </div>
        </div>
        <div className="sv-hero-stats">
          <StatBlock value={TOTAL_PRODUCTS.toLocaleString('zh-CN')} label="原始商品" hint="MUGE / Amazon / 苏宁" />
          <StatBlock value={INDEX_TOTAL.toLocaleString('zh-CN')} label="检索索引" hint="清洗后 9 类" />
          <StatBlock value="9" label="商品类别" hint="从鞋到家居" />
          <StatBlock value="512" label="向量维度" hint="L2 归一化" />
        </div>
        <div className="sv-hero-orbit" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </section>

      <div className="sv-overview-grid sv-reveal">
        <section className="sv-card">
          <SectionLabel index="01" title="系统状态" extra={<Tag bordered={false}>GET /health</Tag>} />
          {healthLoading && !health ? (
            <Skeleton active paragraph={{ rows: 4 }} />
          ) : healthError ? (
            <div className="sv-health-error">
              <strong>后端暂时没有响应</strong>
              <p>页面可以继续浏览，但检索不可用。请确认 uvicorn 已在 8000 端口运行。</p>
              <Button size="small" onClick={refreshHealth}>
                重新检查
              </Button>
            </div>
          ) : (
            <div className="sv-health-grid">
              <div className="sv-health-main">
                <span className="sv-status-pill is-online">
                  <span className="sv-dot" />
                  {isPlaceholder ? '占位模式' : '模型在线'}
                </span>
                <strong>{health?.backend?.toUpperCase() || 'UNKNOWN'}</strong>
                <span>当前后端编码器</span>
              </div>
              <div className="sv-health-item">
                <em>模型加载</em>
                <strong>{health?.model_loaded ? '已加载' : '未加载'}</strong>
              </div>
              <div className="sv-health-item">
                <em>向量维度</em>
                <strong className="sv-mono">{health?.dimension ?? '—'}</strong>
              </div>
              <div className="sv-health-item">
                <em>类别数</em>
                <strong className="sv-mono">{health?.categories?.length ?? 0}</strong>
              </div>
              <div className="sv-health-item sv-health-wide">
                <em>索引目录</em>
                <strong className="sv-mono" title={health?.index_dir}>
                  {health?.index_dir || '—'}
                </strong>
              </div>
            </div>
          )}
        </section>

        <section className="sv-card sv-demo-card">
          <SectionLabel index="02" title="三分钟演示路线" extra={<ExperimentOutlined />} />
          <div className="sv-demo-steps">
            {DEMO_STEPS.map((step) => (
              <button type="button" key={step.index} className="sv-demo-step" onClick={() => navigate(step.to)}>
                <span className="sv-demo-index sv-mono">{step.index}</span>
                <span className="sv-demo-copy">
                  <strong>{step.title}</strong>
                  <span>{step.text}</span>
                </span>
                <ArrowRightOutlined />
              </button>
            ))}
          </div>
          <div className="sv-demo-pairs">
            {DEMO_PAIRS.map((pair) => (
              <button
                type="button"
                key={pair.key}
                className={`sv-demo-pair ${pair.key === 'mismatch' ? 'is-warm' : ''}`}
                onClick={() => navigate(`/match?demo=${pair.key}`)}
              >
                <ThunderboltOutlined />
                <span>
                  <strong>{pair.label}</strong>
                  <em>{pair.description}</em>
                </span>
              </button>
            ))}
          </div>
        </section>
      </div>

      <div className="sv-overview-grid sv-reveal">
        <section className="sv-card">
          <SectionLabel
            index="03"
            title="九类商品索引"
            extra={<span className="sv-muted">点击类别直接去检索</span>}
          />
          <div className="sv-category-grid">
            {CATEGORIES.map((category) => (
              <button
                type="button"
                key={category.key}
                className="sv-category-tile"
                onClick={() => navigate(`/text?category=${encodeURIComponent(category.key)}`)}
              >
                <CategoryGlyph category={category.key} size={46} />
                <span className="sv-category-copy">
                  <strong>{category.key}</strong>
                  <em>{category.hint}</em>
                  <span className="sv-mono">{category.count.toLocaleString('zh-CN')} 条</span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="sv-card">
          <SectionLabel
            index="04"
            title="最近运行"
            extra={<Button type="link" size="small" onClick={() => navigate('/history')}>全部记录</Button>}
          />
          {recentRuns.length ? (
            <div className="sv-run-list">
              {recentRuns.map((run) => (
                <RunRow key={run.id} run={run} onReplay={replay} />
              ))}
            </div>
          ) : (
            <EmptyState
              compact
              title="还没有运行记录"
              description="完成一次图像分类或文本检索后，这里会自动留下最近 5 条轨迹。"
              action={
                <Button type="primary" onClick={() => navigate('/image')}>
                  先做一次图像分类
                </Button>
              }
            />
          )}
          <div className="sv-quick-queries">
            <span>快捷查询</span>
            {SAMPLE_QUERIES.slice(0, 4).map((query) => (
              <button key={query} type="button" onClick={() => navigate(`/text?q=${encodeURIComponent(query)}`)}>
                {query}
              </button>
            ))}
          </div>
        </section>
      </div>

      <section className="sv-capability-grid sv-reveal">
        {CAPABILITIES.map((item) => (
          <article className="sv-capability-card" key={item.key}>
            <div className="sv-capability-icon">{item.icon}</div>
            <div className="sv-capability-copy">
              <span className="sv-mono">{item.meta}</span>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
            </div>
            <Button type="text" onClick={() => navigate(item.to)}>
              {item.action} <ArrowRightOutlined />
            </Button>
          </article>
        ))}
      </section>
    </div>
  )
}
