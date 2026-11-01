import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

const WorkflowContext = createContext(null)

export function WorkflowProvider({ children }) {
  const imageRef = useRef(null)
  const textRef = useRef('')
  const [pendingImage, setPendingImageState] = useState(null)
  const [pendingText, setPendingTextState] = useState('')

  const stageImage = useCallback((payload) => {
    imageRef.current = payload
    setPendingImageState(payload)
  }, [])

  const stageText = useCallback((text) => {
    textRef.current = text
    setPendingTextState(text)
  }, [])

  const takeImage = useCallback(() => {
    const value = imageRef.current
    imageRef.current = null
    setPendingImageState(null)
    return value
  }, [])

  const takeText = useCallback(() => {
    const value = textRef.current
    textRef.current = ''
    setPendingTextState('')
    return value
  }, [])

  const clearPending = useCallback(() => {
    imageRef.current = null
    textRef.current = ''
    setPendingImageState(null)
    setPendingTextState('')
  }, [])

  const value = useMemo(
    () => ({
      pendingImage,
      pendingText,
      stageImage,
      stageText,
      takeImage,
      takeText,
      clearPending,
    }),
    [pendingImage, pendingText, stageImage, stageText, takeImage, takeText, clearPending],
  )

  return <WorkflowContext.Provider value={value}>{children}</WorkflowContext.Provider>
}

export function useWorkflow() {
  const context = useContext(WorkflowContext)
  if (!context) throw new Error('useWorkflow 必须在 WorkflowProvider 内使用')
  return context
}
