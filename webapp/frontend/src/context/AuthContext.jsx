import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const SESSION_KEY = 'shopvision.session.v1'

// 演示级鉴权：账号密码写死在前端，仅用于区分游客与管理员视图
const ADMIN_ACCOUNT = { username: 'admin', password: 'admin888', name: '管理员' }

function readSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed?.role === 'admin' ? parsed : null
  } catch {
    return null
  }
}

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => readSession())
  const [loginOpen, setLoginOpen] = useState(false)

  const login = useCallback((username, password) => {
    if (username === ADMIN_ACCOUNT.username && password === ADMIN_ACCOUNT.password) {
      const next = { role: 'admin', name: ADMIN_ACCOUNT.name, at: new Date().toISOString() }
      localStorage.setItem(SESSION_KEY, JSON.stringify(next))
      setSession(next)
      setLoginOpen(false)
      return { ok: true }
    }
    return { ok: false, message: '账号或密码不对，请重试' }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(SESSION_KEY)
    setSession(null)
  }, [])

  const openLogin = useCallback(() => setLoginOpen(true), [])
  const closeLogin = useCallback(() => setLoginOpen(false), [])

  const value = useMemo(
    () => ({
      session,
      isAdmin: session?.role === 'admin',
      login,
      logout,
      loginOpen,
      openLogin,
      closeLogin,
    }),
    [session, login, logout, loginOpen, openLogin, closeLogin],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return context
}
