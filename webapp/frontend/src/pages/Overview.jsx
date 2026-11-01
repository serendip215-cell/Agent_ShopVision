import { Fragment, useState } from 'react'
import { Button, Tooltip } from 'antd'
import {
  ArrowRightOutlined,
  ExperimentOutlined,
  InfoCircleOutlined,
  LockOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  CATEGORIES,
  CATEGORY_PHOTOS,
  DEMO_PAIRS,
  INDEX_TOTAL,
  SAMPLE_QUERIES,
  TOTAL_PRODUCTS,
  categoryStyle,
} from '../constants/catalog'
import { useApp } from '../context/AppContext'
import { useAuth } from '../context/AuthContext'
import { EmptyState, SectionLabel } from '../components/common/Ui'
import RunRow from '../components/common/RunRow'

const INSTRUMENTS = [
  {
    key: 'image',
    step: '第一步',
    title: '图像分类',
    text: '上传商品图片，图像塔输出预测类别与置信分数。',
    to: '/image',
  },
  {
    key: 'text',
    step: '第二步',
    title: '文本检索',
    text: '输入中文描述，文本塔检索商品库，召回相似商品。',
    to: '/text?q=白色运动鞋',
  },
  {
    key: 'match',
    step: '第三步',
    title: '图文匹配',
    text: '图像、文本两路独立推理，交叉验证图文是否匹配。',
    to: '/match?demo=mismatch',
  },
]

// 分类矩阵的大小错落：大卡 2x2、中卡 2x1、小卡 1x1，正好填满 6 列 3 行
const CATEGORY_SIZE = {
  鞋: 'is-size-l',
  水杯: 'is-size-m',
  包: 'is-size-m',
  男装: 'is-size-m',
  运动服: 'is-size-m',
  手机壳: 'is-size-m',
  厨房用品: 'is-size-m',
  女装: 'is-size-s',
  家居用品: 'is-size-s',
}

function Hero() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')

  function goSearch(value) {
    const q = String(value || '').trim()
    navigate(q ? `/text?q=${encodeURIComponent(q)}` : '/text')
  }

  return (
    <section className="sv-hero sv-reveal">
      <div className="sv-hero-banner">
        <div className="sv-hero-copy">
          <span className="sv-hero-kicker">Chinese-CLIP 双塔 · 9 类 · 9,393 条索引</span>
          <h2>
            用图像和文字
            <br />
            找到<em>同款</em>商品。
          </h2>
          <p>
            上传图片、输入描述，跨模态检索同一个商品库。
            分类、检索、匹配，是一次向量编码的三种看法。
          </p>
        </div>
        <div className="sv-hero-search">
          <div className="sv-hero-search-field">
            <SearchOutlined aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') goSearch(query)
              }}
              placeholder="输入商品描述，如：白色运动鞋"
              aria-label="搜索商品"
            />
            <Button type="primary" onClick={() => goSearch(query)}>
              开始检索
            </Button>
          </div>
          <div className="sv-hero-chips">
            <span>试试：</span>
            {SAMPLE_QUERIES.slice(0, 4).map((item) => (
              <button
                key={item}
                type="button"
                className="sv-chip"
                onClick={() => goSearch(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="sv-hero-stats">
        <div>
          <strong>{TOTAL_PRODUCTS.toLocaleString('zh-CN')}</strong>
          <span>原始商品</span>
        </div>
        <div>
          <strong>{INDEX_TOTAL.toLocaleString('zh-CN')}</strong>
          <span>检索索引</span>
        </div>
        <div>
          <strong>9</strong>
          <span>商品类别</span>
        </div>
        <div>
          <strong className="sv-mono">512</strong>
          <span>向量维度</span>
        </div>
      </div>
    </section>
  )
}

function CategorySection() {
  const navigate = useNavigate()
  return (
    <section className="sv-reveal">
      <div className="sv-strip-head">
        <h2>从类别进去逛</h2>
        <Tooltip title="点击任一类别，直接用该类别的热门查询开始检索">
          <span className="sv-strip-hint">
            <InfoCircleOutlined />
            点击分类，直达热门检索
          </span>
        </Tooltip>
      </div>
      <div className="sv-category-grid">
        {CATEGORIES.map((category) => {
          const style = categoryStyle(category.key)
          return (
            <button
              type="button"
              key={category.key}
              className={`sv-category-tile ${CATEGORY_SIZE[category.key] || 'is-size-s'}`}
              style={{ background: style.bg, color: style.ink }}
              onClick={() => navigate(`/text?category=${encodeURIComponent(category.key)}`)}
            >
              <img
                src={CATEGORY_PHOTOS[category.key]}
                alt=""
                loading="lazy"
                onError={(event) => {
                  event.currentTarget.closest('.sv-category-tile').classList.add('is-broken')
                  event.currentTarget.remove()
                }}
              />
              <span className="sv-category-shade" aria-hidden="true" />
              <span className="sv-category-copy">
                <span className="sv-category-name">{category.key}</span>
                <span className="sv-category-hint">{category.hint}</span>
                <span className="sv-category-count sv-mono">
                  {category.count.toLocaleString('zh-CN')} 商品
                </span>
              </span>
              <span className="sv-category-go" aria-hidden="true">
                <ArrowRightOutlined />
              </span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

function InstrumentSection() {
  const navigate = useNavigate()
  return (
    <section className="sv-reveal">
      <div className="sv-strip-head">
        <h2>三台仪器，同一套索引</h2>
        <Tooltip title="按顺序做一遍，正好是一次完整演示：先分类、再检索、最后交叉验证">
          <span className="sv-strip-hint">
            <InfoCircleOutlined />
            三步走完一次完整演示
          </span>
        </Tooltip>
      </div>
      <div className="sv-instrument-grid">
        {INSTRUMENTS.map((item, index) => (
          <Fragment key={item.key}>
            {index > 0 && (
              <span className="sv-flow-arrow" aria-hidden="true">
                <ArrowRightOutlined />
              </span>
            )}
            <button
              type="button"
              className="sv-instrument"
              onClick={() => navigate(item.to)}
            >
              <span className="sv-instrument-step">{item.step}</span>
              <strong>{item.title}</strong>
              <p>{item.text}</p>
              <span className="sv-instrument-go">
                进入 <ArrowRightOutlined />
              </span>
            </button>
          </Fragment>
        ))}
      </div>
      <div className="sv-demo-row">
        <ExperimentOutlined />
        <span>图文匹配快演：</span>
        {DEMO_PAIRS.map((pair) => (
          <button
            type="button"
            key={pair.key}
            onClick={() => navigate(`/match?demo=${pair.key}`)}
          >
            {pair.label}
          </button>
        ))}
      </div>
    </section>
  )
}

function RecentRuns() {
  const navigate = useNavigate()
  const { history } = useApp()
  const { isAdmin, openLogin } = useAuth()

  return (
    <section className="sv-card sv-reveal">
      <SectionLabel
        index=""
        title="最近运行"
        extra={
          isAdmin ? (
            <Button type="link" size="small" onClick={() => navigate('/history')}>
              全部记录
            </Button>
          ) : null
        }
      />
      {isAdmin ? (
        history.length ? (
          <div className="sv-run-list">
            {history.slice(0, 5).map((run) => (
              <RunRow
                key={run.id}
                run={run}
                onReplay={(run) =>
                  navigate(
                    run.mode === 'text'
                      ? `/text?q=${encodeURIComponent(run.input?.query || '')}`
                      : run.mode === 'match'
                        ? `/match?text=${encodeURIComponent(run.input?.text || '')}`
                        : '/image',
                  )
                }
              />
            ))}
          </div>
        ) : (
          <EmptyState
            compact
            title="还没有运行记录"
            description="完成一次图像分类或文本检索后，这里会留下最近 5 条轨迹。"
            action={
              <Button type="primary" onClick={() => navigate('/image')}>
                先做一次图像分类
              </Button>
            }
          />
        )
      ) : (
        <button type="button" className="sv-locked-inline" onClick={openLogin}>
          <LockOutlined />
          <span>
            <strong>运行记录只对管理员开放</strong>
            <em>登录后可查看本机的检索轨迹</em>
          </span>
        </button>
      )}
      <div className="sv-quick-queries">
        <span>快捷查询</span>
        {SAMPLE_QUERIES.slice(0, 4).map((query) => (
          <button
            key={query}
            type="button"
            onClick={() => navigate(`/text?q=${encodeURIComponent(query)}`)}
          >
            {query}
          </button>
        ))}
      </div>
    </section>
  )
}

export default function Overview() {
  return (
    <div className="sv-overview">
      <Hero />
      <CategorySection />
      <InstrumentSection />
      <RecentRuns />
    </div>
  )
}
