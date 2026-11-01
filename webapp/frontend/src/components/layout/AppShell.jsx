import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Button, Drawer, Tooltip } from 'antd'
import {
  ApiOutlined,
  AppstoreOutlined,
  BlockOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  MenuOutlined,
  PictureOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useApp } from '../../context/AppContext'
import { ErrorNotice } from '../common/Ui'

const NAV_ITEMS = [
  { to: '/', label: '工作台', hint: '系统概览与快捷入口', icon: <AppstoreOutlined />, end: true },
  { to: '/image', label: '图像分类', hint: '上传商品图，判定类别', icon: <PictureOutlined /> },
  { to: '/text', label: '文本检索', hint: '中文查询，找相似商品', icon: <FileSearchOutlined /> },
  { to: '/match', label: '图文匹配', hint: '双塔独立判断，再比对', icon: <BlockOutlined /> },
  { to: '/history', label: '运行记录', hint: '本地保存的检索轨迹', icon: <HistoryOutlined /> },
  { to: '/status', label: '系统状态', hint: '模型、索引与接口', icon: <DashboardOutlined /> },
]

function Brand() {
  return (
    <div className="sv-brand">
      <svg className="sv-logo" viewBox="0 0 48 48" aria-hidden="true">
        <rect width="48" height="48" rx="14" fill="#DDEFEF" />
        <path
          d="M12 19h24l-3 18H15z"
          fill="none"
          stroke="#5FA8B0"
          strokeWidth="3.2"
          strokeLinejoin="round"
        />
        <path
          d="M18 19v-2.4a6 6 0 0 1 12 0V19"
          fill="none"
          stroke="#5FA8B0"
          strokeWidth="3.2"
          strokeLinecap="round"
        />
        <circle cx="34" cy="14" r="3.4" fill="#F7D9C4" />
      </svg>
      <div>
        <strong>ShopVision</strong>
        <span>商品多模态检索台</span>
      </div>
    </div>
  )
}

function NavContent({ onNavigate }) {
  const { health, isPlaceholder, isOffline } = useApp()
  const stateLabel = isOffline ? '后端未连接' : isPlaceholder ? '占位模式' : '模型在线'
  const stateTone = isOffline ? 'is-offline' : isPlaceholder ? 'is-warm' : 'is-online'

  return (
    <div className="sv-nav-content">
      <Brand />
      <nav className="sv-nav" aria-label="主导航">
        {NAV_ITEMS.map((item, index) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onNavigate}
            className={({ isActive }) => `sv-nav-item ${isActive ? 'is-active' : ''}`}
          >
            <span className="sv-nav-index">{String(index + 1).padStart(2, '0')}</span>
            <span className="sv-nav-icon">{item.icon}</span>
            <span className="sv-nav-copy">
              <strong>{item.label}</strong>
              <em>{item.hint}</em>
            </span>
          </NavLink>
        ))}
      </nav>
      <div className="sv-nav-footer">
        <div className={`sv-nav-state ${stateTone}`}>
          <span className="sv-dot" />
          <div>
            <strong>{stateLabel}</strong>
            <span>
              {health?.backend ? `backend: ${health.backend}` : '等待 /health 响应'}
            </span>
          </div>
        </div>
        <a
          className="sv-docs-link"
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noreferrer"
        >
          <ApiOutlined />
          打开后端 API 文档
        </a>
      </div>
    </div>
  )
}

function StatusStrip() {
  const { health, healthLoading, healthError, refreshHealth, categories, isPlaceholder } = useApp()
  const tone = healthError ? 'is-offline' : isPlaceholder ? 'is-warm' : 'is-online'
  const backend = health?.backend || (healthError ? 'unreachable' : 'checking')

  return (
    <div className="sv-status-strip">
      <div className={`sv-status-pill ${tone}`}>
        <span className="sv-dot" />
        <span>{healthError ? '后端未连接' : isPlaceholder ? '占位模式' : '模型在线'}</span>
      </div>
      <div className="sv-status-metrics">
        <span>
          <em>BACKEND</em>
          <strong className="sv-mono">{backend}</strong>
        </span>
        <span>
          <em>DIM</em>
          <strong className="sv-mono">{health?.dimension ?? '—'}</strong>
        </span>
        <span>
          <em>CATEGORIES</em>
          <strong className="sv-mono">{categories.length}</strong>
        </span>
        <span className="sv-status-index">
          <em>INDEX</em>
          <strong className="sv-mono">{health?.index_dir ? health.index_dir.split(/[\\/]/).pop() : '—'}</strong>
        </span>
      </div>
      <div className="sv-status-actions">
        <NavLink to="/status" className="sv-status-link">
          详情
        </NavLink>
        <Tooltip title="刷新 /health">
          <Button
            size="small"
            type="text"
            icon={<ReloadOutlined spin={healthLoading} />}
            onClick={refreshHealth}
            aria-label="刷新系统状态"
          />
        </Tooltip>
      </div>
    </div>
  )
}

function SystemBanner() {
  const { health, healthError, healthLoading, refreshHealth, isPlaceholder } = useApp()
  if (healthLoading && !health && !healthError) return null

  if (healthError) {
    return (
      <div className="sv-system-banner">
        <ErrorNotice
          error={healthError}
          onRetry={refreshHealth}
        />
      </div>
    )
  }

  if (isPlaceholder) {
    return (
      <div className="sv-system-banner sv-banner-warm">
        <span className="sv-banner-dot" />
        <div>
          <strong>当前为占位编码器</strong>
          <p>
            接口与数据流已经跑通，但检索结果仅用于联调。切到真实双塔 ONNX 之前，不要把这里的相似度、置信度写进报告。
          </p>
        </div>
      </div>
    )
  }

  return null
}

export default function AppShell({ children }) {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    window.scrollTo(0, 0)
    setDrawerOpen(false)
  }, [location.pathname])

  return (
    <div className="sv-shell">
      <aside className="sv-rail">
        <NavContent />
      </aside>

      <div className="sv-main">
        <header className="sv-mobile-bar">
          <Brand />
          <Button
            type="text"
            icon={<MenuOutlined />}
            onClick={() => setDrawerOpen(true)}
            aria-label="打开导航"
          />
        </header>

        <div className="sv-content">
          <StatusStrip />
          <SystemBanner />
          <main className="sv-page sv-reveal">{children}</main>
          <footer className="sv-footer">
            <span>Agent ShopVision · 实验四前后端</span>
            <span>数据来源：MUGE / Amazon / 苏宁 · 9 类商品图文索引</span>
          </footer>
        </div>
      </div>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        placement="left"
        width={288}
        styles={{ body: { padding: 0 } }}
        title={null}
      >
        <NavContent onNavigate={() => setDrawerOpen(false)} />
      </Drawer>
    </div>
  )
}
