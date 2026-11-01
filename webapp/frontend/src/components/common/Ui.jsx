import { useEffect, useState } from 'react'
import { App as AntApp, Button, Spin, Tooltip } from 'antd'
import {
  CheckCircleFilled,
  CopyOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { CATEGORY_MAP } from '../../constants/catalog'
import { describeError } from '../../utils/errors'
import { clamp01, formatPercent, formatScore } from '../../utils/format'

export function PageHeader({ eyebrow, title, description, actions, meta }) {
  return (
    <header className="sv-page-head sv-reveal">
      <div className="sv-page-head-copy">
        {eyebrow && <div className="sv-eyebrow">{eyebrow}</div>}
        <h1 className="sv-page-title">{title}</h1>
        {description && <p className="sv-page-desc">{description}</p>}
        {meta && <div className="sv-page-meta">{meta}</div>}
      </div>
      {actions && <div className="sv-page-actions">{actions}</div>}
    </header>
  )
}

export function SectionLabel({ index, title, extra }) {
  return (
    <div className="sv-section-label">
      <div className="sv-section-title-wrap">
        {index && <span className="sv-section-index">{index}</span>}
        <h2 className="sv-section-title">{title}</h2>
      </div>
      {extra && <div className="sv-section-extra">{extra}</div>}
    </div>
  )
}

export function CategoryGlyph({ category, size = 44, muted = false, className = '' }) {
  const glyph = CATEGORY_MAP[category]?.glyph || (category ? String(category).slice(0, 1) : '?')
  return (
    <span
      aria-hidden="true"
      className={`sv-glyph ${muted ? 'is-muted' : ''} ${className}`}
      style={{ width: size, height: size, fontSize: Math.max(14, size * 0.42) }}
    >
      {glyph}
    </span>
  )
}

export function CategoryBadge({ category, small = false }) {
  return (
    <span className={`sv-cat-badge ${small ? 'is-small' : ''}`}>
      <CategoryGlyph category={category} size={small ? 20 : 24} muted />
      <span>{category || '未分类'}</span>
    </span>
  )
}

export function ConfidenceRing({ value, size = 148, label = '置信度', tone = 'auto' }) {
  const target = clamp01(value)
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    const frame = requestAnimationFrame(() => setDisplay(target))
    return () => cancelAnimationFrame(frame)
  }, [target])

  const radius = size / 2 - 14
  const stroke = 9
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - display)
  const color = tone === 'warm' || target < 0.35 ? 'var(--warm-ink)' : 'var(--primary)'

  return (
    <div
      className="sv-ring"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${label} ${formatPercent(value)}`}
    >
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--divider)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 700ms cubic-bezier(.2,.7,.2,1)' }}
        />
        {Array.from({ length: 24 }).map((_, index) => {
          const angle = (index / 24) * Math.PI * 2
          const x1 = size / 2 + Math.cos(angle) * (radius - 13)
          const y1 = size / 2 + Math.sin(angle) * (radius - 13)
          const x2 = size / 2 + Math.cos(angle) * (radius - 10)
          const y2 = size / 2 + Math.sin(angle) * (radius - 10)
          return (
            <line
              key={index}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="var(--border)"
              strokeWidth="1"
            />
          )
        })}
      </svg>
      <div className="sv-ring-center">
        <strong>{formatPercent(value)}</strong>
        <span>{label}</span>
      </div>
    </div>
  )
}

export function SimilarityBar({ value, label, showScore = false, compact = false, tone = 'auto' }) {
  const ratio = clamp01(value)
  return (
    <div className={`sv-sim ${compact ? 'is-compact' : ''}`}>
      {label && (
        <div className="sv-sim-head">
          <span className="sv-sim-label">{label}</span>
          <span className="sv-sim-value">{formatPercent(value)}</span>
        </div>
      )}
      <div className="sv-sim-track">
        <span
          className={`sv-sim-fill ${tone === 'warm' ? 'is-warm' : ''}`}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
      {showScore && <div className="sv-sim-score">原始相似度 {formatScore(value)}</div>}
    </div>
  )
}

export function EmptyState({ icon = <InfoCircleOutlined />, title, description, action, compact = false }) {
  return (
    <div className={`sv-empty ${compact ? 'is-compact' : ''}`}>
      <div className="sv-empty-icon">{icon}</div>
      <h3>{title || '这里还没有内容'}</h3>
      {description && <p>{description}</p>}
      {action && <div className="sv-empty-action">{action}</div>}
    </div>
  )
}

export function LoadingState({ title = '正在请求模型', description = '结果返回后会自动展示在这里。' }) {
  return (
    <div className="sv-loading" role="status" aria-live="polite">
      <div className="sv-loading-head">
        <Spin size="small" />
        <div>
          <strong>{title}</strong>
          <p>{description}</p>
        </div>
      </div>
      <div className="sv-loading-bars">
        <span />
        <span />
        <span />
      </div>
    </div>
  )
}

export function ErrorNotice({ error, onRetry, onDismiss }) {
  const detail = describeError(error)
  if (!detail) return null
  return (
    <div className="sv-error-notice" role="alert">
      <div className="sv-error-icon">
        <ExclamationCircleOutlined />
      </div>
      <div className="sv-error-copy">
        <div className="sv-error-title">
          {detail.title}
          {detail.code !== undefined && <span className="sv-error-code">{detail.code}</span>}
        </div>
        <p>{detail.message || detail.hint}</p>
        <span className="sv-error-hint">{detail.hint}</span>
      </div>
      <div className="sv-error-actions">
        {onRetry && (
          <Button size="small" type="primary" icon={<ReloadOutlined />} onClick={onRetry}>
            重试
          </Button>
        )}
        {onDismiss && (
          <Button size="small" onClick={onDismiss}>
            关闭
          </Button>
        )}
      </div>
    </div>
  )
}

export function SuccessNote({ children }) {
  return (
    <div className="sv-success-note">
      <CheckCircleFilled />
      <span>{children}</span>
    </div>
  )
}

export function CopyButton({ text, label = '复制', size = 'small', type = 'text' }) {
  const { message } = AntApp.useApp()

  async function copy() {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const helper = document.createElement('textarea')
        helper.value = text
        helper.style.position = 'fixed'
        helper.style.opacity = '0'
        document.body.appendChild(helper)
        helper.select()
        document.execCommand('copy')
        document.body.removeChild(helper)
      }
      message.success('已复制到剪贴板')
    } catch {
      message.error('复制失败，请手动选择复制')
    }
  }

  return (
    <Tooltip title={text}>
      <Button type={type} size={size} icon={<CopyOutlined />} onClick={copy}>
        {label}
      </Button>
    </Tooltip>
  )
}

export function StatBlock({ value, label, hint }) {
  return (
    <div className="sv-stat">
      <strong>{value}</strong>
      <span>{label}</span>
      {hint && <em>{hint}</em>}
    </div>
  )
}
