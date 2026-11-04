import { useState } from 'react'
import { Button, Tooltip } from 'antd'
import {
  FileTextOutlined,
  InfoCircleOutlined,
  NodeIndexOutlined,
  PictureOutlined,
  SearchOutlined,
  SwapOutlined,
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
        <div className="sv-hero-lines" aria-hidden="true">
          <svg viewBox="0 0 800 300" preserveAspectRatio="none">
            <path
              d="M 10 150 C 150 100, 280 120, 380 150 S 600 160, 750 140"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.25"
              strokeWidth="1.5"
            />
            <path
              d="M 20 180 C 180 140, 300 160, 400 175 S 620 180, 760 165"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.15"
              strokeWidth="1"
              strokeDasharray="5 5"
            />
            <path
              d="M 30 220 C 200 190, 320 200, 430 210 S 650 215, 780 200"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.12"
              strokeWidth="1"
            />
            <path
              d="M 5 120 C 140 80, 260 90, 370 130 S 580 145, 740 125"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.1"
              strokeWidth="0.8"
            />
            <circle cx="300" cy="135" r="4" fill="#5fa8b0" fillOpacity="0.35" />
            <circle cx="380" cy="150" r="3" fill="#5fa8b0" fillOpacity="0.3" />
            <circle cx="450" cy="172" r="3.5" fill="#5fa8b0" fillOpacity="0.25" />
            <circle cx="280" cy="195" r="2.5" fill="#5fa8b0" fillOpacity="0.2" />
            <circle cx="340" cy="230" r="4" fill="#5fa8b0" fillOpacity="0.15" />
          </svg>
        </div>
        <h1 className="sv-hero-title">
          <span className="sv-hero-title-letter">F</span>ind{" "}
          <span className="sv-hero-title-letter">S</span>imilar
        </h1>
        <div className="sv-hero-search-wrap">
          <div className="sv-hero-search-field">
            <PictureOutlined aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') goSearch(query)
              }}
              placeholder="描述图片、商品特征或关键词"
              aria-label="搜索商品"
            />
            <Button type="primary" onClick={() => goSearch(query)}>
              搜索
            </Button>
          </div>
          <div className="sv-hero-modes">
            <button
              type="button"
              className="sv-mode-chip"
              onClick={() => navigate('/image')}
            >
              <PictureOutlined />
              <span>Image</span>
            </button>
            <button
              type="button"
              className="sv-mode-chip"
              onClick={() => navigate('/text')}
            >
              <FileTextOutlined />
              <span>Text</span>
            </button>
            <button
              type="button"
              className="sv-mode-chip"
              onClick={() => navigate('/match')}
            >
              <SwapOutlined />
              <span>Similar</span>
            </button>
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

  const [index, setIndex] = useState(0)

  const total = categories.length
  if (!total) return null

  const goPrev = () => setIndex((i) => (i - 1 + total) % total)
  const goNext = () => setIndex((i) => (i + 1) % total)

  const cursor = index % total
  const current = categories[cursor]
  const prev = categories[(cursor - 1 + total) % total]
  const next = categories[(cursor + 1) % total]

  const goCategory = (key) => {
    const sample = CATEGORY_QUERY[key] || key
    navigate(`/text?q=${encodeURIComponent(sample)}&category=${encodeURIComponent(key)}`)
  }

  const count = health?.category_counts?.[current]

  return (
    <section className="sv-reveal">
      <div className="sv-strip-head">
        <h2>从类别进去逛</h2>
      </div>

      <div className="sv-category-carousel">
        {/* 左侧箭头：极小极淡 */}
        <button
          type="button"
          className="sv-carousel-arrow is-left"
          onClick={goPrev}
          aria-label="上一个类别"
        >
          ‹
        </button>

        {/* 轮播轨道 */}
        <div className="sv-carousel-track">
          {/* 左侧半露卡片 */}
          <div className="sv-carousel-card is-side is-left" aria-hidden="true">
            <img src={CATEGORY_PHOTOS[prev]} alt="" loading="lazy" />
          </div>

          {/* 中间主卡片 */}
          <div className="sv-carousel-card is-main">
            <img
              key={index}
              src={CATEGORY_PHOTOS[current]}
              alt={current}
            />
            <div className="sv-carousel-info">
              <h3 className="sv-carousel-name">{current}</h3>
              <p className="sv-carousel-count">
                {count != null ? `${count.toLocaleString('zh-CN')} 件商品` : '精选好货'}
              </p>
              <button
                type="button"
                className="sv-carousel-go"
                onClick={() => goCategory(current)}
              >
                探索系列 <span aria-hidden="true">→</span>
              </button>
            </div>
          </div>

          {/* 右侧半露卡片 */}
          <div className="sv-carousel-card is-side is-right" aria-hidden="true">
            <img src={CATEGORY_PHOTOS[next]} alt="" loading="lazy" />
          </div>
        </div>

        {/* 右侧箭头：极小极淡 */}
        <button
          type="button"
          className="sv-carousel-arrow is-right"
          onClick={goNext}
          aria-label="下一个类别"
        >
          ›
        </button>
      </div>
    </section>
  )
}

export default function Overview() {
  return (
    <div className="sv-overview">
      <Hero />
      <CategorySection />
    </div>
  )
}
