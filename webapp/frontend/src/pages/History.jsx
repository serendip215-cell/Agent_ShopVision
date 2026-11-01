import { useMemo, useState } from 'react'
import { App as AntApp, Button, Input, Popconfirm, Segmented, Tag } from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  HistoryOutlined,
  SearchOutlined,
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
      <PageHeader
        eyebrow="Local Trace · Run History"
        title="运行记录"
        description="三次检索的输入、结果摘要和耗时都保存在浏览器本地，用于联调、答辩回看和报告截图。"
        meta={
          <>
            <Tag bordered={false}>localStorage</Tag>
            <Tag bordered={false}>最多保留 50 条</Tag>
            <Tag bordered={false}>不上传服务器</Tag>
          </>
        }
        actions={
          <>
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
          </>
        }
      />

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
