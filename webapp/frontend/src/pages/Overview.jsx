import { Button } from 'antd'
import { ArrowRightOutlined, ExperimentOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  CATEGORIES,
  DEMO_PAIRS,
  HERO_PHOTOS,
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
    text: '传一张商品图，图像塔给出最可能的类别与置信度。',
    to: '/image',
  },
  {
    key: 'text',
    step: '第二步',
    title: '文本检索',
    text: '输一句中文描述，文本塔在商品库里找最相似的条目。',
    to: '/text?q=白色运动鞋',
  },
  {
    key: 'match',
    step: '第三步',
    title: '图文匹配',
    text: '图和文各自独立判断，再比对是否说的是同一类商品。',
    to: '/match?demo=mismatch',
  },
]

function HeroPhoto({ photo, className }) {
  const style = categoryStyle(photo.category)
  return (
    <figure className={`sv-collage-item ${className}`}>
      <img
        src={photo.src}
        alt={photo.caption}
        loading="lazy"
        onError={(event) => {
          event.currentTarget.closest('.sv-collage-item').classList.add('is-broken')
          event.currentTarget.remove()
        }}
      />
      <figcaption style={{ background: style.bg, color: style.ink }}>
        {photo.caption}
      </figcaption>
    </figure>
  )
}

function Hero() {
  const navigate = useNavigate()
  return (
    <section className="sv-hero sv-reveal">
      <div className="sv-hero-copy">
        <span className="sv-hero-kicker">Chinese-CLIP 双塔 · 9 类 · 9,393 条索引</span>
        <h2>
          拍一张商品图，
          <br />
          剩下的交给<em>向量</em>。
        </h2>
        <p>
          图像塔和文本塔各自编码成 512 维向量，再在同一个商品索引里相遇。
          分类、检索、匹配，其实是一次编码的三种看法。
        </p>
        <div className="sv-hero-actions">
          <Button type="primary" size="large" onClick={() => navigate('/image')}>
            上传一张商品图
          </Button>
          <Button size="large" type="text" onClick={() => navigate('/match?demo=mismatch')}>
            看一次「不一致」示例 <ArrowRightOutlined />
          </Button>
        </div>
      </div>
      <div className="sv-collage" aria-hidden="true">
        <HeroPhoto photo={HERO_PHOTOS[0]} className="c1" />
        <HeroPhoto photo={HERO_PHOTOS[1]} className="c2" />
        <HeroPhoto photo={HERO_PHOTOS[2]} className="c3" />
        <HeroPhoto photo={HERO_PHOTOS[3]} className="c4" />
        <HeroPhoto photo={HERO_PHOTOS[4]} className="c5" />
        <HeroPhoto photo={HERO_PHOTOS[5]} className="c6" />
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
        <span>点一块颜色，直接用该类别的热门查询开始检索</span>
      </div>
      <div className="sv-category-grid">
        {CATEGORIES.map((category) => {
          const style = categoryStyle(category.key)
          return (
            <button
              type="button"
              key={category.key}
              className="sv-category-tile"
              style={{ background: style.bg, color: style.ink }}
              onClick={() => navigate(`/text?category=${encodeURIComponent(category.key)}`)}
            >
              <span className="sv-category-glyph">{category.glyph}</span>
              <span className="sv-category-name">{category.key}</span>
              <span className="sv-category-count sv-mono">
                {category.count.toLocaleString('zh-CN')}
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
        <span>按顺序做一遍，正好是一次完整演示</span>
      </div>
      <div className="sv-instrument-grid">
        {INSTRUMENTS.map((item) => (
          <button
            type="button"
            key={item.key}
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
