import { useCallback, useRef, useState } from 'react'
import { isCanceled } from '../utils/errors'

export function useAsyncRequest(fn, options = {}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [duration, setDuration] = useState(null)
  const abortRef = useRef(null)

  const execute = useCallback(async (...args) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    setResult(null)
    const start = performance.now()

    try {
      const res = await fn(...args, controller.signal)
      if (abortRef.current !== controller) return res

      setResult(res)
      setDuration(performance.now() - start)
      return res
    } catch (err) {
      if (abortRef.current === controller && !isCanceled(err)) {
        setError(err)
      }
      throw err
    } finally {
      if (abortRef.current === controller) setLoading(false)
    }
  }, [fn])

  const abort = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  const clearResult = useCallback(() => {
    setResult(null)
  }, [])

  return { loading, error, result, duration, execute, abort, setError, setResult, clearError, clearResult }
}
