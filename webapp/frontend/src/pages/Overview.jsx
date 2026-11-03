import { useState } from 'react'
import { Button, Tooltip } from 'antd'
import {
  ArrowRightOutlined,
  InfoCircleOutlined,
  NodeIndexOutlined,
  SearchOutlined,
  TagsOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  CATEGORY_MAP,
  CATEGORY_PHOTOS,
  SAMPLE_QUERIES,
  categoryStyle,
} from '../constants/catalog'
import { useApp } from '../context/AppContext'
import { CategoryGlyph, EmptyState, SectionLabel } from '../components/common/Ui'
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
        {categories.map((key) => {
          const meta = CATEGORY_MAP[key] || { key, hint: '新增类别' }
          const style = categoryStyle(key)
          const photo = CATEGORY_PHOTOS[key]
          return (
            <button
              type="button"
              key={key}
              className={`sv-category-tile ${CATEGORY_SIZE[key] || 'is-size-s'}`}
              style={{ background: style.bg, color: style.ink }}
              onClick={() => navigate(`/text?category=${encodeURIComponent(key)}`)}
            >
              {photo ? (
                <img
                  src={photo}
                  alt=""
                  loading="lazy"
                  onError={(event) => {
                    event.currentTarget.closest('.sv-category-tile').classList.add('is-broken')
                    event.currentTarget.remove()
                  }}
                />
              ) : (
                <span className="sv-category-glyph" aria-hidden="true">
                  <CategoryGlyph category={key} size={56} />
                </span>
              )}
              <span className="sv-category-shade" aria-hidden="true" />
              <span className="sv-category-copy">
                <span className="sv-category-name">{key}</span>
                <span className="sv-category-hint">{meta.hint}</span>
                <span className="sv-category-count sv-mono">
                  {health?.category_counts?.[key] != null
                    ? `${health.category_counts[key].toLocaleString('zh-CN')} 商品`
                    : '数量未知'}
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
