const HISTORY_KEY = 'shopvision.history.v1'
const PREFS_KEY = 'shopvision.prefs.v1'
const HISTORY_LIMIT = 50

export function readHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.slice(0, HISTORY_LIMIT) : []
  } catch {
    return []
  }
}

export function writeHistory(items) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, HISTORY_LIMIT)))
  } catch {
    // localStorage 写满时静默失败，页面仍可正常使用
  }
}

export function readPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export function writePrefs(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
  } catch {
    // 忽略写入失败
  }
}

export { HISTORY_LIMIT }
