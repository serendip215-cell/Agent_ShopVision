import { useState } from 'react'
import { Button, Tooltip } from 'antd'
import {
  ArrowRightOutlined,
  InfoCircleOutlined,
  LockOutlined,
  NodeIndexOutlined,
  SearchOutlined,
  ShoppingOutlined,
  TagsOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  CATEGORIES,
  CATEGORY_PHOTOS,
  INDEX_TOTAL,
  SAMPLE_QUERIES,
  TOTAL_PRODUCTS,
  categoryStyle,
} from '../constants/catalog'
import { useApp } from '../context/AppContext'
import { useAuth } from '../context/AuthContext'
import { EmptyState, SectionLabel } from '../components/common/Ui'
import RunRow from '../components/common/RunRow'
import useCountUp from '../utils/useCountUp'

// 指标栏：大号数字是视觉重心，图标只做低饱和点缀
const HERO_STATS = [
  { key: 'raw', icon: ShoppingOutlined, value: TOTAL_PRODUCTS, label: '原始商品' },
  { key: 'index', icon: SearchOutlined, value: INDEX_TOTAL, label: '检索索引' },
  { key: 'cat', icon: TagsOutlined, value: 9, label: '商品类别' },
  { key: 'dim', icon: NodeIndexOutlined, value: 512, label: '向量维度' },
]

function StatUnit({ icon: Icon, value, label, index }) {
  const animated = useCountUp(value, { delay: 360 + index * 120, duration: 900 })
  return (
    <div className="sv-hero-stat" style={{ animationDelay: `${index * 90}ms` }}>
      <span className="sv-hero-stat-icon" aria-hidden="true">
        <Icon />
      </span>
      <span className="sv-hero-stat-copy">
        <strong className="sv-mono">{Math.round(animated).toLocaleString('zh-CN')}</strong>
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
        {HERO_STATS.map((stat, index) => (
          <StatUnit key={stat.key} {...stat} index={index} />
        ))}
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
      <RecentRuns />
    </div>
  )
}
