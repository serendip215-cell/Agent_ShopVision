import { useEffect, useRef, useState } from 'react'
import { App as AntApp } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { fileFromUrl, validateImageFile } from '../utils/samples'
import { isCanceled } from '../utils/errors'
import { useImagePreview } from '../hooks/useImagePreview'
import { useAsyncRequest } from '../hooks/useAsyncRequest'
import { classifyImage } from '../api/client'
import { ImageUploadSectionWithHeader, ImageUploadSection } from '../components/image/ImageUploadSection'
import { ImageResultsSection, ImageErrorNotice } from '../components/image/ImageResultsSection'
import { ImageHistorySection } from '../components/image/ImageHistorySection'

export default function ImageLab() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const { addRun, isPlaceholder } = useApp()
  const { stageImage, takeImage } = useWorkflow()

  const { previewUrl, replace: replacePreview, clear: clearPreview } = useImagePreview()
  const { loading, error, result, duration, execute } = useAsyncRequest(classifyImage)

  const [file, setFile] = useState(null)
  const [validation, setValidation] = useState(null)
  const [history, setHistory] = useState([])
  const [batch, setBatch] = useState(null)
  const batchInputRef = useRef(null)
  const initRef = useRef(false)

  useEffect(() => {
    if (initRef.current) return
    initRef.current = true
    const pendingImage = takeImage()
    if (pendingImage?.file) {
      setFile(pendingImage.file)
      if (pendingImage.previewUrl) {
        replacePreview(pendingImage.file)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(
    () => () => {
      clearPreview()
    },
    [clearPreview]
  )

  function selectFile(nextFile) {
    const invalid = validateImageFile(nextFile)
    setValidation(invalid)
    if (invalid) return
    setFile(nextFile)
    replacePreview(nextFile)
  }

  function clearAll() {
    clearPreview()
    setFile(null)
    setValidation(null)
  }

  function rememberRun(fileName, fileObj, thumb, data) {
    const entry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      fileName,
      file: fileObj,
      thumb,
      result: data,
      category: data.category,
      confidence: data.confidence,
    }
    setHistory((prev) => [entry, ...prev])
    return entry
  }

  async function analyze(inputFile = file) {
    const activeFile = inputFile || file
    if (!activeFile) {
      setValidation('请先选择一张商品图')
      return
    }

    setValidation(null)
    try {
      const data = await execute(activeFile)
      rememberRun(activeFile.name, activeFile, previewUrl, data)
      addRun({
        mode: 'image',
        input: { fileName: activeFile.name, size: activeFile.size },
        summary: {
          category: data.category,
          confidence: data.confidence,
          score: data.score,
          topk: data.topk,
        },
        status: 'ok',
        code: 0,
        durationMs: duration,
        placeholder: isPlaceholder,
      })
      message.success(`已判定为「${data.category || '未分类'}」`)
    } catch (requestError) {
      if (isCanceled(requestError)) return
      addRun({
        mode: 'image',
        input: { fileName: activeFile.name, size: activeFile.size },
        status: 'error',
        code: requestError.code,
        message: requestError.message,
        durationMs: duration,
        placeholder: isPlaceholder,
      })
    }
  }

  async function loadSample(sample) {
    setValidation(null)
    try {
      const sampleFile = await fileFromUrl(sample.src, `${sample.key}.jpg`)
      replacePreview(sampleFile)
      setFile(sampleFile)
      await analyze(sampleFile)
    } catch (loadError) {
      if (!isCanceled(loadError)) {
        // error handled by execute
      }
    }
  }

  async function runBatch(fileList) {
    const list = [...fileList].filter(Boolean).slice(0, 12)
    if (!list.length) return

    let index = 0
    for (const batchFile of list) {
      index += 1
      const invalid = validateImageFile(batchFile)
      if (invalid) {
        setValidation(`「${batchFile.name}」${invalid}`)
        continue
      }
      setBatch({ index, total: list.length })
      replacePreview(batchFile)
      setFile(batchFile)
      // eslint-disable-next-line no-await-in-loop
      await analyze(batchFile)
    }
    setBatch(null)
  }

  function reviewHistory(entry) {
    replacePreview(entry.file)
    setFile(entry.file)
  }

  function useInMatch() {
    if (!file || !previewUrl) return
    stageImage({ file, previewUrl, name: file.name, size: file.size })
    navigate('/match')
  }

  return (
    <div className="sv-il">
      <div className="sv-il-glow" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>

      <ImageUploadSectionWithHeader
        eyebrow="Chinese-CLIP 双塔 · 图像分类"
        title="上传商品图片，AI 识别商品类别"
        description="上传一张商品照片，AI 自动判断它属于哪一类，同时告诉你模型的判断把握与备选猜测。"
      />

      <ImageUploadSection
        file={file}
        previewUrl={previewUrl}
        loading={loading}
        batch={batch}
        validation={validation}
        onSelect={selectFile}
        onClear={clearAll}
        onLoadSample={loadSample}
        onBatchClick={() => batchInputRef.current?.click()}
        batchInputRef={batchInputRef}
      />

      {error && (
        <ImageErrorNotice
          error={error}
          onRetry={() => analyze()}
          onDismiss={() => undefined}
        />
      )}

      <ImageResultsSection
        result={result}
        previewUrl={previewUrl}
        onUseInMatch={useInMatch}
        onViewCategory={() =>
          navigate(`/text?q=${encodeURIComponent(result?.category || '')}`)
        }
      />

      <ImageHistorySection
        history={history}
        currentResult={result}
        isPlaceholder={isPlaceholder}
        onReviewHistory={reviewHistory}
        onClearAll={clearAll}
        onBatchClick={() => batchInputRef.current?.click()}
      />
    </div>
  )
}
