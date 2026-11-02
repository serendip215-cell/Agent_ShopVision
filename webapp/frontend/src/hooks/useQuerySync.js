import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

export function useQuerySync(keys) {
  const [searchParams, setSearchParams] = useSearchParams()

  const sync = useCallback((values, replace = true) => {
    const nextParams = {}
    keys.forEach((key) => {
      const val = values[key]
      if (val != null && val !== '') {
        nextParams[key] = String(val)
      }
    })
    setSearchParams(nextParams, { replace })
  }, [keys, setSearchParams])

  const get = useCallback((key) => searchParams.get(key), [searchParams])

  return { sync, get, searchParams }
}
