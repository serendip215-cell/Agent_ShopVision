import { useMemo, useState } from 'react'
import { App as AntApp, Button, Input, Popconfirm, Segmented, Tag } from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PictureOutlined,
  SearchOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { MODE_META } from '../constants/catalog'
import { EmptyState, PageHeader, StatBlock } from '../components/common/Ui'
import RunRow from '../components/common/RunRow'

const FILTERS = [
  { value: 'all', label: '全部' },
  { value: 'image', label: MODE_META.image.label },
  { value: 'text', label: MODE_META.text.label },
  { value: 'match', label: MODE_META.match.label },
]

export default function History() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const { history, clearHistory } = useApp()
  const { stageText } = useWorkflow()
  const [filter, setFilter] = useState('all')
  const [keyword, setKeyword] = useState('')

  const stats = useMemo(() => {
    const success = history.filter((run) => run.status === 'ok').length
    const failed = history.length - success
    const avg = history.length
      ? history.reduce((sum, run) => sum + (run.durationMs || 0), 0) / history.length
      : 0
    return { success, failed, avg }
  }, [history])

  const filtered = useMemo(() => {
    const term = keyword.trim().toLowerCase()
    return history.filter((run) => {
      if (filter !== 'all' && run.mode !== filter) return false
      if (!term) return true
      const haystack = [
        run.input?.fileName,
        run.input?.query,
        run.input?.text,
        run.input?.category,
        run.summary?.category,
        run.summary?.topItem,
        run.summary?.imageCategory,
        run.summary?.textCategory,
        run.message,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return haystack.includes(term)
    })
  }, [history, filter, keyword])

  function replay(run) {
    if (run.mode === 'text') {
      navigate(`/text?q=${encodeURIComponent(run.input?.query || '')}`)
      return
    }
    if (run.mode === 'match') {
      stageText(run.input?.text || '')
      navigate('/match')
      return
    }
    message.info('图片文件只存在于本次会话，请到图像分类页重新选择原图。')
    navigate('/image')
  }

  function exportHistory() {
    if (!history.length) {
      message.warning('还没有可导出的记录')
      return
    }
    const blob = new Blob([JSON.stringify(history, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `shopvision-history-${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    message.success('运行记录已导出')
  }

  function clear() {
    clearHistory()
    message.success('本地运行记录已清空')
  }

  return (
    <div className="sv-history-page">
      <header className="sv-page-head">
        <div className="sv-page-head-lines" aria-hidden="true">
          <svg viewBox="0 0 800 200" preserveAspectRatio="none">
            <path
              d="M 0 100 C 200 60, 400 120, 800 80"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.15"
              strokeWidth="1.5"
            />
            <path
              d="M 0 130 C 250 90, 500 150, 800 110"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.1"
              strokeWidth="1"
            />
            <circle cx="300" cy="95" r="3" fill="#5fa8b0" fillOpacity="0.25" />
            <circle cx="500" cy="120" r="2.5" fill="#5fa8b0" fillOpacity="0.2" />
          </svg>
        </div>
        <div className="sv-page-head-copy">
          <span className="sv-eyebrow">RUN HISTORY</span>
          <h1>View Your Queries</h1>
          <div className="sv-page-head-modes">
            <button
              type="button"
              className="sv-page-mode-chip"
              onClick={() => navigate('/image')}
            >
              <PictureOutlined />
              <span>Image</span>
            </button>
            <button
              type="button"
              className="sv-page-mode-chip"
              onClick={() => navigate('/text')}
            >
              <FileTextOutlined />
              <span>Text</span>
            </button>
            <button
              type="button"
              className="sv-page-mode-chip"
              onClick={() => navigate('/match')}
            >
              <SwapOutlined />
              <span>Similar</span>
            </button>
          </div>
        </div>
        <div className="sv-page-head-actions">
          <Button icon={<DownloadOutlined />} onClick={exportHistory}>
            导出 JSON
          </Button>
          <Popconfirm
            title="清空全部运行记录？"
            description="清空后无法恢复，已导出的 JSON 不受影响。"
            okText="清空"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={clear}
            disabled={!history.length}
          >
            <Button danger icon={<DeleteOutlined />} disabled={!history.length}>
              清空
            </Button>
          </Popconfirm>
        </div>
      </header>

      <div className="sv-history-stats sv-reveal">
        <div className="sv-card">
          <StatBlock value={history.length} label="累计运行" hint="当前浏览器" />
        </div>
        <div className="sv-card">
          <StatBlock value={stats.success} label="成功" hint="code = 0" />
        </div>
        <div className="sv-card">
          <StatBlock value={stats.failed} label="失败" hint="含网络 / 业务错误" />
        </div>
        <div className="sv-card">
          <StatBlock
            value={stats.avg ? `${(stats.avg / 1000).toFixed(2)} s` : '—'}
            label="平均耗时"
            hint="前端实测"
          />
        </div>
      </div>

      <section className="sv-card sv-reveal">
        <div className="sv-history-toolbar">
          <Segmented
            value={filter}
            onChange={setFilter}
            options={FILTERS}
          />
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索查询词、商品名或错误信息"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            style={{ maxWidth: 320 }}
          />
        </div>

        {filtered.length ? (
          <div className="sv-run-list">
            {filtered.map((run) => (
              <RunRow key={run.id} run={run} onReplay={replay} />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<HistoryOutlined />}
            title={history.length ? '没有匹配的记录' : '还没有运行记录'}
            description={
              history.length
                ? '换一个关键词，或把筛选切回「全部」。'
                : '去图像分类、文本检索或图文匹配页完成一次请求，这里会自动记录。'
            }
            action={
              <Button type="primary" onClick={() => navigate('/image')}>
                去做一次图像分类
              </Button>
            }
          />
        )}
      </section>
    </div>
  )
}
