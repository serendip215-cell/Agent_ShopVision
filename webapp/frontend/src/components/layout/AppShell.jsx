import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Avatar, Button, Drawer, Dropdown, Tooltip } from 'antd'
import {
  AppstoreOutlined,
  BlockOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  LockOutlined,
  LogoutOutlined,
  MenuOutlined,
  PictureOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useApp } from '../../context/AppContext'
import { useAuth } from '../../context/AuthContext'
import { CATEGORIES } from '../../constants/catalog'
import { ErrorNotice } from '../common/Ui'
import LoginModal from '../auth/LoginModal'

const PUBLIC_NAV = [
  { to: '/', label: '工作台', icon: <AppstoreOutlined />, end: true },
  { to: '/image', label: '图像分类', icon: <PictureOutlined /> },
  { to: '/text', label: '文本检索', icon: <FileSearchOutlined /> },
  { to: '/match', label: '图文匹配', icon: <BlockOutlined /> },
]

const ADMIN_NAV = [
  { to: '/history', label: '运行记录', icon: <HistoryOutlined /> },
  { to: '/status', label: '系统状态', icon: <DashboardOutlined /> },
]

function Brand() {
  return (
    <NavLink to="/" className="sv-brand">
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
      <span className="sv-brand-copy">
        <strong>ShopVision</strong>
        <span>商品多模态检索台</span>
      </span>
    </NavLink>
  )
}

function HeaderSearch() {
  const navigate = useNavigate()
  const [value, setValue] = useState('')

  function submit() {
    const query = value.trim()
    if (!query) return
    navigate(`/text?q=${encodeURIComponent(query)}`)
    setValue('')
  }

  return (
    <div className="sv-header-search">
      <SearchOutlined className="sv-header-search-icon" />
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') submit()
        }}
        placeholder="搜一句中文描述，例如「白色运动鞋」"
        aria-label="全局文本检索"
      />
      <button type="button" onClick={submit} disabled={!value.trim()}>
        检索
      </button>
    </div>
  )
}

function HealthPill() {
  const { health, healthLoading, healthError, refreshHealth, isPlaceholder, isOffline } = useApp()
  const tone = isOffline ? 'is-offline' : isPlaceholder ? 'is-warm' : 'is-online'
  const label = isOffline ? '后端未连接' : isPlaceholder ? '占位模式' : '模型在线'

  return (
    <Tooltip
      title={
        healthError
          ? '无法连接 8000 端口，点击重新检查'
          : `${health?.backend || 'unknown'} · dim ${health?.dimension ?? '—'} · 点击刷新`
      }
    >
      <button type="button" className={`sv-health-pill ${tone}`} onClick={refreshHealth}>
        <span className="sv-dot" />
        <span>{healthLoading && !health ? '检查中' : label}</span>
        <ReloadOutlined spin={healthLoading} className="sv-health-pill-reload" />
      </button>
    </Tooltip>
  )
}

function AccountZone() {
  const { isAdmin, session, openLogin, logout } = useAuth()

  if (!isAdmin) {
    return (
      <Button className="sv-login-btn" icon={<LockOutlined />} onClick={openLogin}>
        管理员登录
      </Button>
    )
  }

  return (
    <Dropdown
      trigger={['click']}
      menu={{
        items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: logout }],
      }}
    >
      <button type="button" className="sv-account">
        <Avatar size={30} style={{ background: '#5FA8B0', fontSize: 13 }}>
          {session?.name?.slice(0, 1) || '管'}
        </Avatar>
        <span className="sv-account-name">{session?.name || '管理员'}</span>
      </button>
    </Dropdown>
  )
}

function NavLinks({ items, onNavigate }) {
  return (
    <>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) => `sv-topnav-item ${isActive ? 'is-active' : ''}`}
        >
          {item.icon}
          <span>{item.label}</span>
        </NavLink>
      ))}
    </>
  )
}

function SystemBanner() {
  const { health, healthError, healthLoading, refreshHealth, isPlaceholder } = useApp()
  if (healthLoading && !health && !healthError) return null

  if (healthError) {
    return (
      <div className="sv-system-banner">
        <ErrorNotice error={healthError} onRetry={refreshHealth} />
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

function Breadcrumb() {
  const location = useLocation()
  if (location.pathname === '/') return null
  const current = [...PUBLIC_NAV, ...ADMIN_NAV].find(
    (item) => item.to !== '/' && location.pathname.startsWith(item.to),
  )
  if (!current) return null
  return (
    <nav className="sv-breadcrumb" aria-label="面包屑">
      <NavLink to="/">首页</NavLink>
      <span className="sv-breadcrumb-sep">/</span>
      <strong>{current.label}</strong>
    </nav>
  )
}

export default function AppShell({ children }) {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()
  const { isAdmin } = useAuth()
  const { health } = useApp()

  useEffect(() => {
    window.scrollTo(0, 0)
    setDrawerOpen(false)
  }, [location.pathname])

  const navItems = isAdmin ? [...PUBLIC_NAV, ...ADMIN_NAV] : PUBLIC_NAV

  return (
    <div className="sv-shell">
      <header className="sv-topbar">
        <div className="sv-topbar-row">
          <Brand />
          <HeaderSearch />
          <div className="sv-topbar-side">
            <HealthPill />
            <AccountZone />
            <Button
              className="sv-menu-btn"
              type="text"
              icon={<MenuOutlined />}
              onClick={() => setDrawerOpen(true)}
              aria-label="打开导航"
            />
          </div>
        </div>
        <nav className="sv-topnav" aria-label="主导航">
          <NavLinks items={navItems} />
          {isAdmin && <span className="sv-topnav-badge">管理员视图</span>}
        </nav>
      </header>

      <div className="sv-content">
        <Breadcrumb />
        <SystemBanner />
        <main key={location.pathname} className="sv-page sv-reveal">{children}</main>
        <footer className="sv-footer">
          <span>Agent ShopVision · 实验四前后端</span>
          <span>
            数据来源：MUGE / Amazon / 苏宁 · {health?.categories?.length ?? CATEGORIES.length}{' '}
            类商品图文索引
          </span>
        </footer>
      </div>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        placement="left"
        width={280}
        styles={{ body: { padding: '18px 14px' } }}
        title={null}
      >
        <nav className="sv-drawer-nav" aria-label="移动端导航">
          <NavLinks items={navItems} onNavigate={() => setDrawerOpen(false)} />
        </nav>
      </Drawer>

      <LoginModal />
    </div>
  )
}
