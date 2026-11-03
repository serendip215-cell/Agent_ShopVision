import { useState } from 'react'
import { Button, Tooltip } from 'antd'
import {
  InfoCircleOutlined,
  NodeIndexOutlined,
  SearchOutlined,
  TagsOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { CATEGORY_PHOTOS, CATEGORY_QUERY, SAMPLE_QUERIES } from '../constants/catalog'
import { useApp } from '../context/AppContext'
import { EmptyState, SectionLabel } from '../components/common/Ui'
import RunRow from '../components/common/RunRow'
import useCountUp from '../utils/useCountUp'

// 指标栏：所有数字都来自 /health；拿不到时显示“—”，不用前端快照兜底。
function buildHeroStats(categoryCount, dimension, indexTotal) {
  return [
    { key: 'index', icon: SearchOutlined, value: indexTotal, label: '检索索引' },
    { key: 'cat', icon: TagsOutlined, value: categoryCount, label: '商品类别' },
    { key: 'dim', icon: NodeIndexOutlined, value: dimension, label: '向量维度' },
  ]
}

function StatUnit({ icon: Icon, value, label, index }) {
  const animated = useCountUp(value ?? 0, { delay: 360 + index * 120, duration: 900 })
  return (
    <div className="sv-hero-stat" style={{ animationDelay: `${index * 90}ms` }}>
      <span className="sv-hero-stat-icon" aria-hidden="true">
        <Icon />
      </span>
      <span className="sv-hero-stat-copy">
        <strong className="sv-mono">
          {value == null ? '—' : Math.round(animated).toLocaleString('zh-CN')}
        </strong>
        <span>{label}</span>
      </span>
    </div>
  )
}

function Hero() {
  const navigate = useNavigate()
  const { health } = useApp()
  const [query, setQuery] = useState('')
  const heroStats = buildHeroStats(
    health?.categories?.length ?? null,
    health?.dimension ?? null,
    health?.total_items ?? null,
  )

  function goSearch(value) {
    const q = String(value || '').trim()
    navigate(q ? `/text?q=${encodeURIComponent(q)}` : '/text')
  }

  return (
    <section className="sv-hero sv-reveal">
      <div className="sv-hero-banner">
        <div className="sv-hero-copy">
          <span className="sv-hero-kicker">
            Chinese-CLIP 双塔
            {heroStats[1].value != null && ` · ${heroStats[1].value} 类`}
            {heroStats[0].value != null &&
              ` · ${heroStats[0].value.toLocaleString('zh-CN')} 条索引`}
          </span>
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
        {heroStats.map((stat, index) => (
          <StatUnit key={stat.key} {...stat} index={index} />
        ))}
      </div>
    </section>
  )
}

function CategorySection() {
  const navigate = useNavigate()
  const { health, categories } = useApp()

  // 当前轮播到第几个类别，默认 0 = 第一个
  const [index, setIndex] = useState(0)

  const total = categories.length
  // 类别由 health 异步填充，首次渲染可能为空，先不渲染
  if (!total) return null

  // 切到上一个，到顶了就绕回最后一个
  const goPrev = () => setIndex((i) => (i - 1 + total) % total)
  // 切到下一个，到末尾了就绕回第一个
  const goNext = () => setIndex((i) => (i + 1) % total)

  // 当前类别、上一个类别、下一个类别（让旁边半露两张图）
  const cursor = index % total
  const current = categories[cursor]
  const prev = categories[(cursor - 1 + total) % total]
  const next = categories[(cursor + 1) % total]

  // 点「探索系列」跳到文本检索页，必须带描述词，否则语义检索页停在空态
  const goCategory = (key) => {
    const sample = CATEGORY_QUERY[key] || key
    navigate(`/text?q=${encodeURIComponent(sample)}&category=${encodeURIComponent(key)}`)
  }

  const count = health?.category_counts?.[current]

  return (
    <section className="sv-reveal">
      <div className="sv-strip-head">
        <h2>从类别进去逛</h2>
        <Tooltip title="点击任一类别，直接用该类别的热门查询开始检索">
          <span className="sv-strip-hint">
            <InfoCircleOutlined />
            左右切换类别，点「探索系列」直接检索
          </span>
        </Tooltip>
      </div>

      <div className="sv-category-showcase">
        {/* 左边：文字区 */}
        <div className="sv-showcase-text">
          <div className="sv-showcase-index">
            <span className="sv-showcase-index-cur">
              {String(cursor + 1).padStart(2, '0')}
            </span>
            <span className="sv-showcase-index-divider">/</span>
            <span className="sv-showcase-index-total">
              {String(total).padStart(2, '0')}
            </span>
          </div>

          <h2 className="sv-showcase-name">{current}</h2>

          <p className="sv-showcase-count">
            {count != null ? `${count.toLocaleString('zh-CN')} 件高品质商品` : '精选好货'}
          </p>

          <button type="button" className="sv-showcase-go" onClick={() => goCategory(current)}>
            探索系列 <span aria-hidden="true">→</span>
          </button>
        </div>

        {/* 右边：图区，三张图叠一起，中间大、两边半露 */}
        <div className="sv-showcase-stage">
          <img
            className="sv-showcase-img is-prev"
            src={CATEGORY_PHOTOS[prev]}
            alt=""
            loading="lazy"
          />
          <img
            key={index}
            className="sv-showcase-img is-current"
            src={CATEGORY_PHOTOS[current]}
            alt={current}
          />
          <img
            className="sv-showcase-img is-next"
            src={CATEGORY_PHOTOS[next]}
            alt=""
            loading="lazy"
          />

          {/* 左右箭头：浮在图区两侧中央 */}
          <button
            type="button"
            className="sv-showcase-arrow is-left"
            onClick={goPrev}
            aria-label="上一个类别"
          >
            ‹
          </button>
          <button
            type="button"
            className="sv-showcase-arrow is-right"
            onClick={goNext}
            aria-label="下一个类别"
          >
            ›
          </button>
        </div>
      </div>
    </section>
  )
}

function RecentRuns() {
  const navigate = useNavigate()
  const { history } = useApp()

  return (
    <section className="sv-card sv-reveal">
      <SectionLabel
        index=""
        title="最近运行"
        extra={
          <Button type="link" size="small" onClick={() => navigate('/history')}>
            全部记录
          </Button>
        }
      />
      {history.length ? (
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
      <RecentRuns />
    </div>
  )
}
