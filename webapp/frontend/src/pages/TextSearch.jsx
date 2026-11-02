import { useEffect, useMemo, useRef, useState } from 'react'
import { App as AntApp, Button, Slider, Tooltip } from 'antd'
import {
  CloseCircleFilled,
  QuestionCircleOutlined,
  SearchOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { searchText } from '../api/client'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { SAMPLE_QUERIES, categoryStyle } from '../constants/catalog'
import { isCanceled } from '../utils/errors'
import { formatDuration } from '../utils/format'
import { EmptyState, ErrorNotice } from '../components/common/Ui'
import { DetailDrawer, ResultList } from '../components/result/Results'

const TOPK_PRESETS = [5, 10, 20, 50]
// 类别 / 条数变化后自动重搜的防抖间隔
const AUTO_SEARCH_DELAY = 280

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

export default function TextSearch() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const { addRun, isPlaceholder, categories, health } = useApp()
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
  const [distFilter, setDistFilter] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [validation, setValidation] = useState(null)
  const [duration, setDuration] = useState(null)

  const abortRef = useRef(null)
  const resultRef = useRef(null)
  const hasResultRef = useRef(false)
  const skipAutoSearchRef = useRef(false)
  const autoSearchTimerRef = useRef(null)
  const latestQueryRef = useRef(query)
  // 上一次真正发出去的检索条件；URL 与它比对，避免把「输入框已改但还没搜」误判成已同步
  const lastSearchRef = useRef({ query: '', category: '', topK: null })

  async function runSearch(options = {}) {
    const nextQuery = String(options.query ?? query).trim()
    const nextCategory = options.category ?? category
    const nextTopK = options.topK ?? topK

    if (!nextQuery) {
      setValidation('先写一句你想找的商品描述，比如「白色运动鞋」')
      return
    }
    setValidation(null)
    hasResultRef.current = true
    lastSearchRef.current = { query: nextQuery, category: nextCategory, topK: nextTopK }

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
    setDistFilter(null)
    const startedAt = performance.now()

    try {
      const data = await searchText(
        { query: nextQuery, topK: nextTopK, category: nextCategory },
        controller.signal,
      )
      if (abortRef.current !== controller) return
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
      if (isCanceled(requestError) || abortRef.current !== controller) return
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

  // 输入框最新值给防抖定时器读，避免 280ms 内改过 query 后仍用旧闭包
  useEffect(() => {
    latestQueryRef.current = query
  }, [query])

  // URL 是检索的唯一入口：首次进入、全局搜索、浏览器前进后退都走这里
  useEffect(() => {
    const nextQuery = searchParams.get('q') || ''
    const nextCategory = searchParams.get('category') || ''
    const nextTopK = Math.min(50, Math.max(1, Number(searchParams.get('top_k')) || 5))

    if (nextQuery !== query || nextCategory !== category || nextTopK !== topK) {
      if (nextCategory !== category || nextTopK !== topK) {
        skipAutoSearchRef.current = true
      }
      setQuery(nextQuery)
      setCategory(nextCategory)
      setTopK(nextTopK)
    }

    if (!nextQuery) {
      lastSearchRef.current = { query: '', category: nextCategory, topK: nextTopK }
      if (autoSearchTimerRef.current) {
        window.clearTimeout(autoSearchTimerRef.current)
        autoSearchTimerRef.current = null
      }
      abortRef.current?.abort()
      abortRef.current = null
      setLoading(false)
      setResult(null)
      setSelected(null)
      setDistFilter(null)
      setDuration(null)
      setError(null)
      setValidation(null)
      hasResultRef.current = false
      return
    }

    const last = lastSearchRef.current
    if (nextQuery === last.query && nextCategory === last.category && nextTopK === last.topK) {
      return
    }
    runSearch({
      query: nextQuery,
      category: nextCategory,
      topK: nextTopK,
      updateUrl: false,
    })
    // URL 变化才触发；query/category/topK 只做比较，不参与依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  // 检索开始过之后，切换类别 / 条数自动重搜（防抖，重复请求由 AbortController 取消）
  useEffect(() => {
    if (skipAutoSearchRef.current) {
      skipAutoSearchRef.current = false
      return undefined
    }
    if (!hasResultRef.current) return undefined
    const timer = window.setTimeout(() => {
      autoSearchTimerRef.current = null
      if (!hasResultRef.current) return
      // 定时器里读最新 query：防抖窗口内用户可能已经改了输入或提交过
      const latestQuery = latestQueryRef.current.trim()
      if (!latestQuery) return
      const last = lastSearchRef.current
      if (latestQuery === last.query && category === last.category && topK === last.topK) {
        return
      }
      runSearch({ query: latestQuery })
    }, AUTO_SEARCH_DELAY)
    autoSearchTimerRef.current = timer
    return () => {
      window.clearTimeout(timer)
      if (autoSearchTimerRef.current === timer) autoSearchTimerRef.current = null
    }
    // 只有类别与条数变化才触发；改筛选时用当前输入重搜
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, topK])

  useEffect(
    () => () => {
      abortRef.current?.abort()
      abortRef.current = null
      // StrictMode 会模拟一次卸载再挂载；清掉已发出的条件，让第二次 setup 重新检索
      lastSearchRef.current = { query: '', category: '', topK: null }
    },
    []
  )

  function useInMatch() {
    const text = result?.query || query
    if (!text.trim()) {
      message.warning('先输入一句查询词')
      return
    }
    stageText(text)
    navigate('/match')
  }

  const items = useMemo(() => result?.items || [], [result])
  const distribution = useMemo(() => categoryDistribution(items), [items])
  const visibleItems = useMemo(
    () => (distFilter ? items.filter((item) => item.category === distFilter) : items),
    [items, distFilter],
  )
  const rankedCategory = result?.category
  const scopeText = category
    ? `当前限定：${category} · ${items.length} 条`
    : `${distribution.length} 类 · ${items.length} 条`

  return (
    <div className="sv-tx">
      <div className="sv-tx-glow" aria-hidden="true">
        <i />
        <i />
      </div>

      {/* 区块 1：页面头部 */}
      <header className="sv-tx-head">
        <div className="sv-tx-head-copy">
          <span className="sv-eyebrow">文本检索 · 语义搜索</span>
          <h1>用一句中文描述找商品</h1>
          <p>
            写清颜色、品类、材质会更准，比如「黑色真皮双肩包」；结果按相似度排序，
            点开任意商品可查看完整档案。
          </p>
          <span className="sv-tx-head-meta">
            {health?.total_items != null
              ? `已索引 ${health.total_items.toLocaleString('zh-CN')} 件商品`
              : '索引统计暂不可用'}
            {isPlaceholder && <em>联调模式 · 结果仅验证链路</em>}
          </span>
        </div>
        <Tooltip title="描述越具体越容易命中：颜色 + 品类 + 材质，例如「白色透气运动鞋」。不限类别时会在全库跨类别检索。">
          <button type="button" className="sv-tx-help" aria-label="使用帮助">
            <QuestionCircleOutlined />
          </button>
        </Tooltip>
      </header>

      {/* 区块 2：检索控制台 */}
      <section className="sv-tx-console sv-tx-card">
        <div className="sv-tx-query-row">
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
            {query && (
              <Tooltip title="清空">
                <button
                  type="button"
                  className="sv-tx-clear"
                  aria-label="清空查询"
                  onClick={() => {
                    setQuery('')
                    setValidation(null)
                  }}
                >
                  <CloseCircleFilled />
                </button>
              </Tooltip>
            )}
            <div className="sv-tx-field-foot">
              <span>Enter 开始检索 · Shift + Enter 换行</span>
              <span className="sv-mono">{query.length} / 200</span>
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
                {health?.category_counts?.[key] != null && (
                  <em>{health.category_counts[key].toLocaleString('zh-CN')}</em>
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="sv-tx-tools">
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
        </div>

        {validation && <div className="sv-tx-tip is-warn">{validation}</div>}
      </section>

      {/* 区块 3：错误态 */}
      {error && !loading && (
        <ErrorNotice error={error} onRetry={() => runSearch()} onDismiss={() => setError(null)} />
      )}

      {/* 区块 4：加载态（与结果同结构的骨架卡） */}
      {loading && (
        <section className="sv-tx-result" ref={resultRef}>
          <div className="sv-tx-result-head">
            <div>
              <h2>正在检索</h2>
              <p>把这句描述与全库商品逐一比对，稍等一下</p>
            </div>
          </div>
          <ResultList items={[]} loading />
        </section>
      )}

      {/* 区块 5：结果 */}
      {!loading && result && (
        <section className="sv-tx-result" ref={resultRef}>
          <div className="sv-tx-result-head">
            <div>
              <h2>最相似的商品</h2>
              <p>按相似度从高到低排序 · 点击卡片查看完整档案</p>
            </div>
            <Button size="small" icon={<SwapOutlined />} onClick={useInMatch}>
              用这句做图文匹配
            </Button>
          </div>

          <div className="sv-tx-summary">
            <div className="sv-tx-summary-cell is-query">
              <span>查询词</span>
              <strong>
                {result.query}
                <em className="sv-tx-scope-badge">{rankedCategory || '全部类别'}</em>
              </strong>
            </div>
            <div className="sv-tx-summary-cell">
              <span>命中商品</span>
              <strong className="sv-mono">{items.length}</strong>
            </div>
            <div className="sv-tx-summary-cell">
              <span>耗时</span>
              <strong className="sv-mono">{formatDuration(duration)}</strong>
            </div>
          </div>

          <div className="sv-tx-dist">
            <div className="sv-tx-dist-head">
              <span>命中的类别分布</span>
              {distFilter ? (
                <button
                  type="button"
                  className="sv-tx-dist-reset"
                  onClick={() => setDistFilter(null)}
                >
                  已在结果内筛选「{distFilter}」 · 取消
                </button>
              ) : (
                <span className="sv-muted">{scopeText}</span>
              )}
            </div>
            {distribution.length > 0 ? (
              <>
                <div className="sv-tx-dist-bar">
                  {distribution.map((row, index) => (
                    <i
                      key={row.category}
                      className={distFilter && distFilter !== row.category ? 'is-dim' : ''}
                      style={{
                        width: `${row.share}%`,
                        background: categoryStyle(row.category).ink,
                        animationDelay: `${index * 70}ms`,
                      }}
                      title={`${row.category} ${row.count} 条`}
                    />
                  ))}
                </div>
                <div className="sv-tx-dist-legend">
                  {distribution.map((row) => (
                    <button
                      type="button"
                      key={row.category}
                      className={distFilter === row.category ? 'is-active' : ''}
                      onClick={() =>
                        setDistFilter((prev) => (prev === row.category ? null : row.category))
                      }
                    >
                      <i style={{ background: categoryStyle(row.category).ink }} />
                      {row.category}
                      <em className="sv-mono">{row.count}</em>
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <p className="sv-tx-dist-none">本次结果没有类别信息</p>
            )}
          </div>

          <ResultList
            items={visibleItems}
            loading={false}
            onSelect={setSelected}
            highlightCategory={distFilter || rankedCategory}
            emptyTitle="这一类里没有找到商品"
            emptyDescription="换一个描述方式，或者把检索范围切回「全部类别」再试一次。"
          />
        </section>
      )}

      {/* 区块 6：空态（还没检索过） */}
      {!loading && !result && !error && (
        <section className="sv-tx-idle">
          <EmptyState
            icon={<SearchOutlined />}
            title="还没有检索过"
            description="写下你要找的东西，比如「白色运动鞋」；也可以直接点一句示例开始。"
          />
          <div className="sv-tx-idle-samples">
            <span className="sv-tx-label">热门示例</span>
            <div className="sv-tx-samples-row">
              {SAMPLE_QUERIES.map((item) => (
                <button
                  type="button"
                  key={item}
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
