import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getHealth } from '../api/client'
import { CATEGORY_KEYS } from '../constants/catalog'
import { isCanceled } from '../utils/errors'
import { makeRunId } from '../utils/format'
import { HISTORY_LIMIT, readHistory, readPrefs, writeHistory, writePrefs } from '../utils/storage'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [health, setHealth] = useState(null)
  const [healthError, setHealthError] = useState(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [history, setHistory] = useState(() => readHistory())
  const [prefs, setPrefs] = useState(() => readPrefs())

  const refreshHealth = useCallback(async () => {
    setHealthLoading(true)
    setHealthError(null)
    try {
      const result = await getHealth()
      setHealth(result)
    } catch (error) {
      if (!isCanceled(error)) {
        setHealth(null)
        setHealthError(error)
      }
    } finally {
      setHealthLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshHealth()
  }, [refreshHealth])

  const addRun = useCallback((run) => {
    const entry = {
      id: makeRunId(),
      at: new Date().toISOString(),
      ...run,
    }
    setHistory((prev) => {
      const next = [entry, ...prev].slice(0, HISTORY_LIMIT)
      writeHistory(next)
      return next
    })
    return entry
  }, [])

  const clearHistory = useCallback(() => {
    setHistory([])
    writeHistory([])
  }, [])

  const savePrefs = useCallback((patch) => {
    setPrefs((prev) => {
      const next = { ...prev, ...patch }
      writePrefs(next)
      return next
    })
  }, [])

  const categories = useMemo(
    () => health?.categories?.length ? health.categories : CATEGORY_KEYS,
    [health],
  )

  const isPlaceholder = Boolean(health && (health.backend !== 'onnx' || !health.model_loaded))
  const isOffline = Boolean(healthError)

  const value = useMemo(
    () => ({
      health,
      healthError,
      healthLoading,
      refreshHealth,
      categories,
      isPlaceholder,
      isOffline,
      history,
      addRun,
      clearHistory,
      prefs,
      savePrefs,
    }),
    [
      health,
      healthError,
      healthLoading,
      refreshHealth,
      categories,
      isPlaceholder,
      isOffline,
      history,
      addRun,
      clearHistory,
      prefs,
      savePrefs,
    ],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const context = useContext(AppContext)
  if (!context) throw new Error('useApp 必须在 AppProvider 内使用')
  return context
}
