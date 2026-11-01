import { Button, Tag } from 'antd'
import {
  CheckCircleFilled,
  CloseCircleFilled,
  RedoOutlined,
} from '@ant-design/icons'
import { MODE_META } from '../../constants/catalog'
import { formatPercent, formatTime } from '../../utils/format'

function inputLabel(run) {
  if (run.mode === 'image') return run.input?.fileName || '未记录图片'
  if (run.mode === 'text') {
    const parts = [run.input?.query || '未记录查询']
    if (run.input?.category) parts.push(`类别：${run.input.category}`)
    return parts.join(' · ')
  }
  if (run.mode === 'match') {
    return `${run.input?.fileName || '图片'} + 「${run.input?.text || '未记录文本'}」`
  }
  return '未记录输入'
}

function summaryLabel(run) {
  const summary = run.summary || {}
  if (run.status === 'error') return run.message || '请求失败'
  if (run.mode === 'image') {
    return summary.category
      ? `判定为「${summary.category}」 · 置信度 ${formatPercent(summary.confidence)}`
      : '已完成图像分类'
  }
  if (run.mode === 'text') {
    const count = summary.itemCount ?? 0
    return summary.topItem
      ? `${count} 条结果 · 首条「${summary.topItem}」`
      : `${count} 条结果`
  }
  if (run.mode === 'match') {
    return summary.match
      ? `图文一致 · ${summary.imageCategory || '—'}`
      : `图文不一致 · 图判「${summary.imageCategory || '—'}」/ 文判「${summary.textCategory || '—'}」`
  }
  return '已完成'
}

export default function RunRow({ run, onReplay }) {
  const meta = MODE_META[run.mode] || { label: '运行', tone: 'teal' }
  return (
    <div className={`sv-run-row ${run.status === 'error' ? 'is-error' : ''}`}>
      <div className={`sv-run-mode tone-${meta.tone}`}>{meta.label}</div>
      <div className="sv-run-main">
        <div className="sv-run-input">{inputLabel(run)}</div>
        <div className="sv-run-summary">{summaryLabel(run)}</div>
        <div className="sv-run-meta">
          <span className="sv-mono">{formatTime(run.at)}</span>
          {run.placeholder && <Tag color="orange">占位模式</Tag>}
          {run.durationMs != null && <span>{(run.durationMs / 1000).toFixed(2)} s</span>}
        </div>
      </div>
      <div className="sv-run-side">
        <span className={`sv-run-status ${run.status}`}>
          {run.status === 'error' ? <CloseCircleFilled /> : <CheckCircleFilled />}
          {run.status === 'error' ? '失败' : '完成'}
        </span>
        {onReplay && (
          <Button size="small" type="text" icon={<RedoOutlined />} onClick={() => onReplay(run)}>
            重放
          </Button>
        )}
      </div>
    </div>
  )
}
