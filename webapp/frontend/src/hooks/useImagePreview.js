import { useCallback, useRef, useState } from 'react'

export function useImagePreview() {
  const previewRef = useRef('')
  const [previewUrl, setPreviewUrl] = useState('')

  const replace = useCallback((file) => {
    const next = URL.createObjectURL(file)
    if (previewRef.current?.startsWith('blob:')) {
      URL.revokeObjectURL(previewRef.current)
    }
    previewRef.current = next
    setPreviewUrl(next)
  }, [])

  const clear = useCallback(() => {
    if (previewRef.current?.startsWith('blob:')) {
      URL.revokeObjectURL(previewRef.current)
    }
    previewRef.current = ''
    setPreviewUrl('')
  }, [])

  return { previewUrl, replace, clear }
}
