import { useEffect, useRef, useState } from 'react'
import { App as AntApp, Button, Slider, Tooltip } from 'antd'
import {
  ArrowRightOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { searchText } from '../api/client'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { CATEGORY_MAP, SAMPLE_QUERIES, categoryStyle } from '../constants/catalog'
import { isCanceled } from '../utils/errors'
import { formatDuration, formatPercent, formatScore } from '../utils/format'
import { resolveItemImage } from '../utils/itemImage'
import { ErrorNotice } from '../components/common/Ui'
import { DetailDrawer } from '../components/result/Results'

const TOPK_PRESETS = [5, 10, 20, 50]

// 条形按本次结果集内的最高分归一化：第一名铺满，其余按比例。
// 右侧数字仍是原始余弦相似度，答辩时可直接对照。
function rankRows(items) {
  const best = items.reduce((acc, item) => Math.max(acc, Number(item.similarity) || 0), 0) || 1
  return items.map((item, index) => ({
    item,
    index,
    ratio: Math.max(0, Math.min(1, (Number(item.similarity) || 0) / best)),
  }))
}

// 命中结果落在哪些类别：全库检索时用来看「跨类别」的分布
function categoryDistribution(items) {
  const map = new Map()
  for (const item of items) {
    const key = item.category || '未分类'
    map.set(key, (map.get(key) || 0) + 1)
  }
  const total = items.length || 1
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([category, count]) => ({ category, count, share: (count / total) * 100 }))
}

function ItemThumb({ item }) {
  const style = categoryStyle(item.category)
  return (
    <span
      className="sv-tx-photo"
      style={{ background: style.bg }}
      data-fallback={item.category?.slice(0, 1) || '?'}
    >
      <img
        src={resolveItemImage(item)}
        alt={item.item_name || '商品图'}
        loading="lazy"
        onError={(event) => {
          event.currentTarget.closest('.sv-tx-photo').classList.add('is-broken')
          event.currentTarget.remove()
        }}
      />
    </span>
  )
}

export default function TextSearch() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const { addRun, isPlaceholder, categories } = useApp()
  const { stageText } = useWorkflow()
  const [searchParams, setSearchParams] = useSearchParams()

  const initialQuery = searchParams.get('q') || ''
  const initialCategory = searchParams.get('category') || ''
  const initialTopK = Math.min(50, Math.max(1, Number(searchParams.get('top_k')) || 5))

  const [query, setQuery] = useState(initialQuery)
  const [category, setCategory] = useState(initialCategory)
  const [topK, setTopK] = useState(initialTopK)
  const [result, setResult] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [validation, setValidation] = useState(null)
  const [duration, setDuration] = useState(null)

  const abortRef = useRef(null)
  const initialRunRef = useRef(false)
  const resultRef = useRef(null)

  async function runSearch(options = {}) {
    const nextQuery = String(options.query ?? query).trim()
    const nextCategory = options.category ?? category
    const nextTopK = options.topK ?? topK

    if (!nextQuery) {
      setValidation('先写一句你想找的商品描述，比如「白色运动鞋」')
      return
    }
    setValidation(null)

    if (options.updateUrl !== false) {
      const nextParams = { q: nextQuery, top_k: String(nextTopK) }
      if (nextCategory) nextParams.category = nextCategory
      setSearchParams(nextParams, { replace: true })
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    setResult(null)
    setSelected(null)
    const startedAt = performance.now()

    try {
      const data = await searchText(
        { query: nextQuery, topK: nextTopK, category: nextCategory },
        controller.signal,
      )
      const elapsed = performance.now() - startedAt
      setResult(data)
      setDuration(elapsed)
      addRun({
        mode: 'text',
        input: { query: nextQuery, category: nextCategory, topK: nextTopK },
        summary: {
          itemCount: data.items?.length || 0,
          topItem: data.items?.[0]?.item_name,
          category: data.category,
        },
        status: 'ok',
        code: 0,
        durationMs: elapsed,
        placeholder: isPlaceholder,
      })
      requestAnimationFrame(() => {
        resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    } catch (requestError) {
      if (isCanceled(requestError)) return
      setError(requestError)
      addRun({
        mode: 'text',
        input: { query: nextQuery, category: nextCategory, topK: nextTopK },
        status: 'error',
        code: requestError.code,
        message: requestError.message,
        durationMs: performance.now() - startedAt,
        placeholder: isPlaceholder,
      })
    } finally {
      if (abortRef.current === controller) setLoading(false)
    }
  }

  useEffect(() => {
    if (initialRunRef.current) return
    initialRunRef.current = true
    if (initialQuery) {
      runSearch({
        query: initialQuery,
        category: initialCategory,
        topK: initialTopK,
        updateUrl: false,
      })
    }
    // 只在首次进入时读取 URL 参数
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function useInMatch() {
    const text = result?.query || query
    if (!text.trim()) {
      message.warning('先输入一句查询词')
      return
    }
    stageText(text)
    navigate('/match')
  }

  const items = result?.items || []
  const rows = rankRows(items)
  const distribution = categoryDistribution(items)
  const rankedCategory = result?.category

  return (
    <div className="sv-tx">
      <div className="sv-tx-glow" aria-hidden="true">
        <i />
        <i />
      </div>

      {/* 区块 1：页面头部 */}
      <header className="sv-tx-head">
        <div className="sv-tx-head-copy">
          <span className="sv-eyebrow">Chinese-CLIP 双塔 · 文本检索</span>
          <h1>用一句话，搜遍 9,393 件商品</h1>
          <p>
            输入一句中文描述，AI 会把它编码成向量，在全库商品里按相似度排序，
            越像的越靠前，每条都带完整商品档案。
          </p>
        </div>
        <Tooltip title="不限类别就是全库跨类检索，命中的类别会标在每条结果上">
          <button type="button" className="sv-tx-help" aria-label="使用帮助">
            <QuestionCircleOutlined />
          </button>
        </Tooltip>
      </header>

      {/* 区块 2：检索控制台 */}
      <section className="sv-tx-console sv-tx-glass">
        <div className="sv-tx-field">
          <textarea
            className="sv-tx-input"
            value={query}
            rows={2}
            maxLength={200}
            placeholder="例如：白色运动鞋、黑色双肩包、轻便保温杯"
            onChange={(event) => {
              setQuery(event.target.value)
              if (validation) setValidation(null)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                runSearch()
              }
            }}
          />
          <div className="sv-tx-field-foot">
            <span>Enter 开始检索 · Shift + Enter 换行</span>
            <span className="sv-mono">{query.length} / 200</span>
          </div>
        </div>

        <div className="sv-tx-scope">
          <span className="sv-tx-label">检索范围</span>
          <div className="sv-tx-scope-chips">
            <button
              type="button"
              className={`sv-tx-chip ${category ? '' : 'is-active'}`}
              onClick={() => setCategory('')}
            >
              全部类别
              <em>跨类检索</em>
            </button>
            {categories.map((key) => (
              <button
                type="button"
                key={key}
                className={`sv-tx-chip ${category === key ? 'is-active' : ''}`}
                onClick={() => setCategory(key)}
              >
                {key}
                {CATEGORY_MAP[key] && <em>{CATEGORY_MAP[key].count.toLocaleString('zh-CN')}</em>}
              </button>
            ))}
          </div>
        </div>

        <div className="sv-tx-controls">
          <div className="sv-tx-topk">
            <span className="sv-tx-label">返回条数</span>
            <Slider
              className="sv-tx-slider"
              min={1}
              max={50}
              value={topK}
              onChange={setTopK}
              tooltip={{ formatter: (next) => `${next} 条` }}
            />
            <strong className="sv-tx-topk-value sv-mono">{topK}</strong>
            <div className="sv-tx-presets">
              {TOPK_PRESETS.map((preset) => (
                <button
                  type="button"
                  key={preset}
                  className={topK === preset ? 'is-active' : ''}
                  onClick={() => setTopK(preset)}
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>
          <Button
            type="primary"
            size="large"
            className="sv-tx-submit"
            icon={<SearchOutlined />}
            loading={loading}
            onClick={() => runSearch()}
          >
            开始检索
          </Button>
        </div>

        <div className="sv-tx-samples">
          <span className="sv-tx-label">试试这些句子</span>
          <div className="sv-tx-samples-row">
            {SAMPLE_QUERIES.map((item) => (
              <button
                type="button"
                key={item}
                className={query === item ? 'is-active' : ''}
                onClick={() => {
                  setQuery(item)
                  runSearch({ query: item })
                }}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        {validation && <div className="sv-tx-tip is-warn">{validation}</div>}
        <div className="sv-tx-console-foot">
          <span>POST /api/v1/text</span>
          <span>9,393 条索引 · 512 维向量</span>
          {isPlaceholder && <span className="sv-tx-tag-warm">当前为联调模式，结果仅验证链路</span>}
        </div>
      </section>

      {/* 区块 3：加载态 */}
      {loading && (
        <section className="sv-tx-loading sv-tx-glass" role="status" aria-live="polite">
          <span className="sv-tx-ring" aria-hidden="true" />
          <strong>AI 正在把这句话变成向量...</strong>
          <span>随后与商品库逐条比对相似度，按分数从高到低排好</span>
          <div className="sv-tx-shimmer" aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
        </section>
      )}

      {/* 区块 4：错误态 */}
      {error && !loading && (
        <ErrorNotice error={error} onRetry={() => runSearch()} onDismiss={() => setError(null)} />
      )}

      {/* 区块 5：结果 */}
      {!loading && result && (
        <section className="sv-tx-result" ref={resultRef}>
          <div className="sv-tx-summary">
            <div className="sv-tx-summary-cell is-query">
              <span>查询词</span>
              <strong>{result.query}</strong>
            </div>
            <div className="sv-tx-summary-cell">
              <span>检索范围</span>
              <strong>{rankedCategory || '全部类别'}</strong>
            </div>
            <div className="sv-tx-summary-cell">
              <span>命中商品</span>
              <strong className="sv-mono">{items.length}</strong>
            </div>
            <div className="sv-tx-summary-cell">
              <span>耗时</span>
              <strong className="sv-mono">{formatDuration(duration)}</strong>
            </div>
            <div className="sv-tx-summary-actions">
              <Button size="small" icon={<SwapOutlined />} onClick={useInMatch}>
                用这句做图文匹配
              </Button>
            </div>
          </div>

          {distribution.length > 1 && (
            <div className="sv-tx-dist">
              <div className="sv-tx-dist-head">
                <span>命中的类别分布</span>
                <span className="sv-muted">{distribution.length} 类 · 跨类别检索结果</span>
              </div>
              <div className="sv-tx-dist-bar">
                {distribution.map((row, index) => {
                  const style = categoryStyle(row.category)
                  return (
                    <i
                      key={row.category}
                      style={{
                        width: `${row.share}%`,
                        background: style.ink,
                        animationDelay: `${index * 70}ms`,
                      }}
                      title={`${row.category} ${row.count} 条`}
                    />
                  )
                })}
              </div>
              <div className="sv-tx-dist-legend">
                {distribution.map((row) => (
                  <span key={row.category}>
                    <i style={{ background: categoryStyle(row.category).ink }} />
                    {row.category}
                    <em className="sv-mono">{row.count}</em>
                  </span>
                ))}
              </div>
            </div>
          )}

          {items.length > 0 ? (
            <>
              <div className="sv-tx-list-head">
                <div>
                  <h2>最相似的商品，越靠前越像</h2>
                  <p>进度条按本次最高分归一化，右侧数字为原始余弦相似度。</p>
                </div>
                <span className="sv-muted">点击任意一行查看完整档案</span>
              </div>

              <ol className="sv-tx-list">
                {rows.map(({ item, index, ratio }) => {
                  const style = categoryStyle(item.category)
                  return (
                    <li key={`${item.item_id || 'item'}-${index}`}>
                      <button
                        type="button"
                        className={`sv-tx-row ${index === 0 ? 'is-top' : ''}`}
                        style={{ animationDelay: `${Math.min(index, 12) * 45}ms` }}
                        onClick={() => setSelected(item)}
                      >
                        <span className="sv-tx-rank sv-mono">{String(index + 1).padStart(2, '0')}</span>
                        <ItemThumb item={item} />
                        <span className="sv-tx-body">
                          <span className="sv-tx-title">{item.item_name || '未命名商品'}</span>
                          <span className="sv-tx-meta">
                            <span className="sv-tx-cat" style={{ background: style.bg, color: style.ink }}>
                              {item.category || '未分类'}
                            </span>
                            {item.type && <span>{item.type}</span>}
                            {item.brand && <span>{item.brand}</span>}
                            {item.color && <span>{item.color}</span>}
                            {item.material && <span>{item.material}</span>}
                          </span>
                          <span className="sv-tx-metric">
                            <span className="sv-tx-track">
                              <i
                                className={index === 0 ? 'is-top' : ''}
                                style={{ '--w': `${ratio * 100}%`, '--d': `${index * 45}ms` }}
                              />
                            </span>
                            <span className="sv-tx-score sv-mono">{formatPercent(item.similarity)}</span>
                            <span className="sv-tx-raw sv-mono">{formatScore(item.similarity)}</span>
                          </span>
                        </span>
                        <ArrowRightOutlined className="sv-tx-go" />
                      </button>
                    </li>
                  )
                })}
              </ol>
            </>
          ) : (
            <div className="sv-tx-empty">
              <span className="sv-tx-empty-icon">
                <SearchOutlined />
              </span>
              <h3>这一类里没有找到商品</h3>
              <p>换一个描述方式，或者把检索范围切回「全部类别」再试一次。</p>
              <Button size="small" icon={<ReloadOutlined />} onClick={() => setCategory('')}>
                改搜全部类别
              </Button>
            </div>
          )}
        </section>
      )}

      {/* 区块 6：空态（还没检索过） */}
      {!loading && !result && !error && (
        <section className="sv-tx-idle">
          <span className="sv-tx-idle-icon">
            <SearchOutlined />
          </span>
          <div>
            <h2>还没有检索过</h2>
            <p>写下你要找的东西，比如「白色运动鞋」；也可以直接点上面任意一句示例。</p>
          </div>
        </section>
      )}

      <DetailDrawer
        item={selected}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        onSearch={(name) => {
          if (!name) return
          setSelected(null)
          setQuery(name)
          runSearch({ query: name })
        }}
      />
    </div>
  )
}
