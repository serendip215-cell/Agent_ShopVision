import { useEffect, useRef, useState } from 'react'
import { App as AntApp, Button, Tag } from 'antd'
import { FileSearchOutlined, SwapOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { searchText } from '../api/client'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { SAMPLE_QUERIES } from '../constants/catalog'
import { isCanceled } from '../utils/errors'
import { formatDuration } from '../utils/format'
import {
  CategorySelect,
  QueryInput,
  SampleChips,
  TopKSlider,
} from '../components/input/Inputs'
import {
  EmptyState,
  ErrorNotice,
  LoadingState,
  PageHeader,
  SectionLabel,
} from '../components/common/Ui'
import { DetailDrawer, ResultList } from '../components/result/Results'
import { useAsyncRequest } from '../hooks/useAsyncRequest'
import { useQuerySync } from '../hooks/useQuerySync'

export default function TextSearch() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const { addRun, isPlaceholder, categories } = useApp()
  const { stageText } = useWorkflow()
  const { sync, get, searchParams } = useQuerySync(['q', 'category', 'top_k'])

  const initialQuery = get('q') || ''
  const initialCategory = get('category') || ''
  const initialTopK = Math.min(50, Math.max(1, Number(get('top_k')) || 5))

  const [query, setQuery] = useState(initialQuery)
  const [category, setCategory] = useState(initialCategory)
  const [topK, setTopK] = useState(initialTopK)
  const [selected, setSelected] = useState(null)
  const [validation, setValidation] = useState(null)

  const { loading, error, result, duration, execute } = useAsyncRequest(searchText)
  const initialRunRef = useRef(false)

  async function runSearch(options = {}) {
    const nextQuery = String(options.query ?? query).trim()
    const nextCategory = options.category ?? category
    const nextTopK = options.topK ?? topK

    if (!nextQuery) {
      setValidation('请输入一个中文查询词，例如「白色运动鞋」')
      return
    }
    setValidation(null)

    if (options.updateUrl !== false) {
      sync({ q: nextQuery, category: nextCategory, top_k: nextTopK }, true)
    }

    try {
      const data = await execute({ query: nextQuery, topK: nextTopK, category: nextCategory })
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
        durationMs: duration,
        placeholder: isPlaceholder,
      })
    } catch (requestError) {
      if (isCanceled(requestError)) return
      addRun({
        mode: 'text',
        input: { query: nextQuery, category: nextCategory, topK: nextTopK },
        status: 'error',
        code: requestError.code,
        message: requestError.message,
        durationMs: duration,
        placeholder: isPlaceholder,
      })
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function pickSample(value) {
    setQuery(value)
    runSearch({ query: value })
  }

  function useInMatch() {
    const text = result?.query || query
    if (!text.trim()) {
      message.warning('先输入一句查询词')
      return
    }
    stageText(text)
    navigate('/match')
  }

  function searchItemName(name) {
    if (!name) return
    setSelected(null)
    setQuery(name)
    runSearch({ query: name })
  }

  return (
    <div className="sv-text-page">
      <PageHeader
        eyebrow="Instrument 02 · Text Retrieval"
        title="文本检索"
        description="一句中文描述，交给文本塔编码，在 9 类商品库中找最相似的商品条目。"
        meta={
          <>
            <Tag bordered={false} color="cyan">
              POST /api/v1/text
            </Tag>
            <Tag bordered={false}>JSON</Tag>
            <Tag bordered={false}>top_k 1–50</Tag>
            {isPlaceholder && <Tag color="orange">结果仅联调</Tag>}
          </>
        }
        actions={
          <Button icon={<SwapOutlined />} onClick={useInMatch}>
            用当前查询做图文匹配
          </Button>
        }
      />

      <section className="sv-card sv-reveal">
        <SectionLabel index="01" title="检索条件" extra={<FileSearchOutlined />} />
        <div className="sv-search-grid">
          <QueryInput
            value={query}
            onChange={setQuery}
            onSubmit={() => runSearch()}
            loading={loading}
            label="中文查询"
          />
          <div className="sv-search-side">
            <CategorySelect value={category} onChange={setCategory} categories={categories} />
            <TopKSlider value={topK} onChange={setTopK} />
          </div>
        </div>
        <SampleChips items={SAMPLE_QUERIES} active={query} onPick={pickSample} />
        {validation && <div className="sv-inline-error">{validation}</div>}
      </section>

      <section className="sv-card sv-reveal">
        <SectionLabel
          index="02"
          title="检索结果"
          extra={
            result ? (
              <span className="sv-muted">
                {result.items?.length || 0} 条 · {formatDuration(duration)}
              </span>
            ) : (
              <span className="sv-muted">等待检索</span>
            )
          }
        />

        {error && (
          <ErrorNotice error={error} onRetry={() => runSearch()} onDismiss={() => setError(null)} />
        )}

        {loading && (
          <LoadingState
            title="文本塔正在编码查询"
            description="查询词会变成 512 维向量，再与目标类别下的商品向量逐一比对。"
          />
        )}

        {!loading && result && (
          <>
            <div className="sv-result-meta">
              <div>
                <span>查询词</span>
                <strong>{result.query}</strong>
              </div>
              <div>
                <span>解析类别</span>
                <strong>{result.category || '全部'}</strong>
              </div>
              <div>
                <span>命中商品</span>
                <strong className="sv-mono">{result.items?.length || 0}</strong>
              </div>
              <div>
                <span>前端耗时</span>
                <strong className="sv-mono">{formatDuration(duration)}</strong>
              </div>
              {isPlaceholder && <Tag color="orange">占位模式</Tag>}
            </div>

            <div className="sv-list-toolbar">
              <span>点击任意一行查看商品详情与完整描述。</span>
              <Button size="small" onClick={useInMatch}>
                用「{result.query}」做图文匹配
              </Button>
            </div>

            <ResultList
              items={result.items}
              onSelect={setSelected}
              emptyTitle="这一类里没有找到商品"
              emptyDescription="试试换一个描述，或把类别筛选改成「全部类别」。"
            />
          </>
        )}

        {!loading && !result && !error && (
          <EmptyState
            icon={<FileSearchOutlined />}
            title="还没有检索结果"
            description="输入「白色运动鞋」或点一个示例查询，结果会按相似度从高到低排在这里。"
          />
        )}
      </section>

      <DetailDrawer
        item={selected}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        onSearch={searchItemName}
      />
    </div>
  )
}
