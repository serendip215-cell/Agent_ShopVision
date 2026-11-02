import { useCallback, useEffect, useRef, useState } from 'react'
import { App as AntApp } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { fileFromUrl, validateImageFile } from '../utils/samples'
import { isCanceled } from '../utils/errors'
import { useImagePreview } from '../hooks/useImagePreview'
import { useAsyncRequest } from '../hooks/useAsyncRequest'
import {
  classifyImage,
  enqueueBatchTask,
  enqueueImageTask,
  waitForTask,
} from '../api/client'
import { ImageUploadSectionWithHeader, ImageUploadSection } from '../components/image/ImageUploadSection'
import { ImageResultsSection, ImageErrorNotice } from '../components/image/ImageResultsSection'
import { ImageHistorySection } from '../components/image/ImageHistorySection'

const BATCH_MAX = 12
// 大图走异步任务（Celery）：同步接口容易撞 30s 超时，也挡住 worker 处理其他请求
const LARGE_IMAGE_BYTES = 2 * 1024 * 1024
// 历史卡片持有 ObjectURL，数量封顶，超出的连同 URL 一起回收
const HISTORY_MAX = 50

export default function ImageLab() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const { addRun, isPlaceholder } = useApp()
  const { stageImage, takeImage } = useWorkflow()

  const {
    previewUrl,
    replace: replacePreview,
    create: createThumb,
    clear: clearPreview,
    release,
    releaseAll,
  } = useImagePreview()

  // 大图/批量都走异步任务，progress 给上传区显示“第几张”
  const [taskProgress, setTaskProgress] = useState(null)
  const [batch, setBatch] = useState(null)
  const batchAbortRef = useRef(null)

  const classify = useCallback(async (inputFile, signal) => {
    if (inputFile.size <= LARGE_IMAGE_BYTES) {
      return classifyImage(inputFile, signal)
    }
    setTaskProgress({ done: 0, total: 1 })
    try {
      const submit = await enqueueImageTask(inputFile, signal)
      return await waitForTask(submit.task_id, { signal, onProgress: setTaskProgress })
    } finally {
      if (!signal.aborted) setTaskProgress(null)
    }
  }, [])

  const { loading, error, result, duration, execute, abort, setResult } = useAsyncRequest(classify)

  const [file, setFile] = useState(null)
  const [validation, setValidation] = useState(null)
  const [history, setHistory] = useState([])
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
      abort()
      batchAbortRef.current?.abort()
      releaseAll()
    },
    [abort, releaseAll]
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
    setHistory((prev) => {
      const next = [entry, ...prev]
      next.slice(HISTORY_MAX).forEach((old) => release(old.thumb))
      return next.slice(0, HISTORY_MAX)
    })
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
      rememberRun(activeFile.name, activeFile, createThumb(activeFile), data)
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
        setValidation(`示例图加载失败：${loadError.message || '请检查网络后重试'}`)
      }
    }
  }

  async function runBatch(fileList) {
    const list = [...fileList].filter((item) => !validateImageFile(item)).slice(0, BATCH_MAX)
    if (!list.length) {
      setValidation('没有可识别的图片：仅支持 PNG / JPG / WEBP，单张 ≤ 10MB')
      return
    }

    setValidation(null)
    batchAbortRef.current?.abort()
    const controller = new AbortController()
    batchAbortRef.current = controller

    setBatch({ done: 0, total: list.length })
    try {
      const submit = await enqueueBatchTask(list, controller.signal)
      const items = await waitForTask(submit.task_id, {
        signal: controller.signal,
        onProgress: (progress) => setBatch(progress),
      })

      const entries = []
      let lastGood = null
      items.forEach((item, index) => {
        // 先按原始文件名配，配不上就按顺序兜底（后端按上传顺序返回）
        const source = list.find((item2) => item2.name === item.file_name) || list[index] || list[0]
        if (item.code !== 0 || !item.result) {
          addRun({
            mode: 'image',
            input: { fileName: item.file_name },
            status: 'error',
            code: item.code,
            message: item.msg,
            placeholder: isPlaceholder,
          })
          return
        }
        const data = item.result
        const entry = rememberRun(item.file_name, source, createThumb(source), data)
        entries.push(entry)
        lastGood = { source, data }
        addRun({
          mode: 'image',
          input: { fileName: item.file_name, size: source.size },
          summary: {
            category: data.category,
            confidence: data.confidence,
            score: data.score,
            topk: data.topk,
          },
          status: 'ok',
          code: 0,
          placeholder: isPlaceholder,
        })
      })

      if (lastGood) {
        replacePreview(lastGood.source)
        setFile(lastGood.source)
        setResult(lastGood.data)
      }
      const failed = items.length - entries.length
      message.success(
        failed
          ? `批量识别完成：成功 ${entries.length} 张，失败 ${failed} 张`
          : `批量识别完成：${entries.length} 张`
      )
    } catch (batchError) {
      if (!isCanceled(batchError)) {
        setValidation(`批量识别失败：${batchError.message}`)
      }
    } finally {
      if (batchAbortRef.current === controller) {
        batchAbortRef.current = null
        setBatch(null)
      }
    }
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
        loading={loading || !!batch}
        progress={taskProgress || batch}
        validation={validation}
        onSelect={selectFile}
        onLoadSample={loadSample}
        onAnalyze={() => analyze()}
        onBatchClick={() => batchInputRef.current?.click()}
        onBatchFiles={runBatch}
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