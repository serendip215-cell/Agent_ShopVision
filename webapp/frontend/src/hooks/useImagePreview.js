import { useCallback, useRef, useState } from 'react'

export function useImagePreview() {
  const previewRef = useRef('')
  // 批量结果缩略图等额外创建的 URL，统一在这里回收
  const ownedRef = useRef(new Set())
  const [previewUrl, setPreviewUrl] = useState('')

  const replace = useCallback((file) => {
    const next = URL.createObjectURL(file)
    if (previewRef.current?.startsWith('blob:')) {
      URL.revokeObjectURL(previewRef.current)
    }
    previewRef.current = next
    setPreviewUrl(next)
  }, [])

  const create = useCallback((file) => {
    const url = URL.createObjectURL(file)
    ownedRef.current.add(url)
    return url
  }, [])

  const clear = useCallback(() => {
    if (previewRef.current?.startsWith('blob:')) {
      URL.revokeObjectURL(previewRef.current)
    }
    previewRef.current = ''
    setPreviewUrl('')
  }, [])

  const releaseAll = useCallback(() => {
    clear()
    ownedRef.current.forEach((url) => URL.revokeObjectURL(url))
    ownedRef.current.clear()
  }, [clear])

  // 历史记录被裁掉时，把对应的缩略图 URL 也回收掉
  const release = useCallback((url) => {
    if (url && ownedRef.current.delete(url)) URL.revokeObjectURL(url)
  }, [])

  return { previewUrl, replace, create, clear, release, releaseAll }
}
