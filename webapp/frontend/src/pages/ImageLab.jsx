import { useEffect, useRef, useState } from 'react'
import { App as AntApp, Button, Tag, Tooltip } from 'antd'
import {
  ExperimentOutlined,
  PictureOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { classifyImage } from '../api/client'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { DEMO_IMAGES } from '../constants/catalog'
import { isCanceled } from '../utils/errors'
import { fileFromUrl, validateImageFile } from '../utils/samples'
import { formatDuration, formatPercent, formatScore } from '../utils/format'
import { DemoImageStrip, UploadDropzone } from '../components/input/Inputs'
import {
  CategoryGlyph,
  ConfidenceRing,
  EmptyState,
  ErrorNotice,
  LoadingState,
  PageHeader,
  SectionLabel,
  SimilarityBar,
} from '../components/common/Ui'

export default function ImageLab() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const { addRun, isPlaceholder } = useApp()
  const { stageImage, takeImage } = useWorkflow()

  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [validation, setValidation] = useState(null)
  const [loadingSample, setLoadingSample] = useState(null)
  const [duration, setDuration] = useState(null)

  const previewRef = useRef('')
  const abortRef = useRef(null)
  const initRef = useRef(false)

  useEffect(() => {
    if (initRef.current) return
    initRef.current = true
    const pendingImage = takeImage()
    if (pendingImage?.file) {
      setFile(pendingImage.file)
      if (pendingImage.previewUrl) {
        previewRef.current = pendingImage.previewUrl
        setPreviewUrl(pendingImage.previewUrl)
      }
    }
    // 只在首次进入时消费跨页交接的图片
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function replacePreview(nextFile) {
    const next = URL.createObjectURL(nextFile)
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    previewRef.current = next
    setPreviewUrl(next)
  }

  function selectFile(nextFile) {
    const invalid = validateImageFile(nextFile)
    setValidation(invalid)
    if (invalid) return
    setFile(nextFile)
    replacePreview(nextFile)
    setResult(null)
    setError(null)
    setDuration(null)
  }

  function clearAll() {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current)
      previewRef.current = ''
    }
    setFile(null)
    setPreviewUrl('')
    setResult(null)
    setError(null)
    setValidation(null)
    setDuration(null)
  }

  async function loadSample(sample) {
    setLoadingSample(sample.key)
    setValidation(null)
    try {
      const sampleFile = await fileFromUrl(sample.src, `${sample.key}.jpg`)
      selectFile(sampleFile)
    } catch (loadError) {
      setError(loadError)
    } finally {
      setLoadingSample(null)
    }
  }

  async function analyze() {
    if (!file) {
      setValidation('请先选择一张商品图')
      return
    }
    if (validation) return

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    setResult(null)
    setValidation(null)
    const startedAt = performance.now()

    try {
      const data = await classifyImage(file, controller.signal)
      const elapsed = performance.now() - startedAt
      setResult(data)
      setDuration(elapsed)
      addRun({
        mode: 'image',
        input: { fileName: file.name, size: file.size },
        summary: {
          category: data.category,
          confidence: data.confidence,
          score: data.score,
          topk: data.topk,
        },
        status: 'ok',
        code: 0,
        durationMs: elapsed,
        placeholder: isPlaceholder,
      })
      message.success(`已判定为「${data.category || '未分类'}」`)
    } catch (requestError) {
      if (isCanceled(requestError)) return
      setError(requestError)
      addRun({
        mode: 'image',
        input: { fileName: file.name, size: file.size },
        status: 'error',
        code: requestError.code,
        message: requestError.message,
        durationMs: performance.now() - startedAt,
        placeholder: isPlaceholder,
      })
    } finally {
      if (abortRef.current === controller) setLoading(false)
    }
  }

  function useInMatch() {
    if (!file || !previewUrl) return
    stageImage({ file, previewUrl, name: file.name, size: file.size })
    navigate('/match')
  }

  return (
    <div className="sv-image-page">
      <PageHeader
        eyebrow="Instrument 01 · Image Classification"
        title="图像分类"
        description="把一张商品图交给图像塔，先看它落在 9 类中的哪一类，再看前三类别的分数分布。"
        meta={
          <>
            <Tag bordered={false} color="cyan">POST /api/v1/image</Tag>
            <Tag bordered={false}>multipart/form-data</Tag>
            <Tag bordered={false}>类别级 top3</Tag>
            {isPlaceholder && <Tag color="orange">结果仅联调</Tag>}
          </>
        }
        actions={
          <Button icon={<SwapOutlined />} onClick={clearAll} disabled={!file}>
            重新开始
          </Button>
        }
      />

      <div className="sv-work-grid">
        <section className="sv-card sv-reveal">
          <SectionLabel index="01" title="输入一张商品图" extra={<PictureOutlined />} />
          <UploadDropzone
            file={file}
            previewUrl={previewUrl}
            onSelect={selectFile}
            onClear={clearAll}
            error={validation}
            disabled={loading}
          />
          <DemoImageStrip images={DEMO_IMAGES} onPick={loadSample} loadingKey={loadingSample} />
          <Button
            type="primary"
            size="large"
            block
            icon={<ExperimentOutlined />}
            loading={loading}
            onClick={analyze}
            disabled={!file}
          >
            开始分析图片
          </Button>
          <div className="sv-input-note">
            <span>图片仅用于本次请求 · 后端上限 10 MB</span>
          </div>
        </section>

        <section className="sv-card sv-reveal">
          <SectionLabel
            index="02"
            title="分类结果"
            extra={duration != null ? <Tag bordered={false}>{formatDuration(duration)}</Tag> : null}
          />

          {error && <ErrorNotice error={error} onRetry={analyze} onDismiss={() => setError(null)} />}

          {loading && (
            <LoadingState
              title="图像塔正在编码"
              description="后端会把图片压成 512 维向量，再与 9 类索引逐个比对。"
            />
          )}

          {!loading && !error && !result && (
            <EmptyState
              icon={<PictureOutlined />}
              title="结果会出现在这里"
              description="选一张商品图点「开始分析」，类别、置信度与前三类别会显示在这里。"
            />
          )}

          {!loading && result && (
            <div className="sv-image-result">
              <div className="sv-result-hero">
                <CategoryGlyph category={result.category} size={82} />
                <div className="sv-result-copy">
                  <span className="sv-result-kicker">最可能的类别</span>
                  <h2>{result.category || '未判定'}</h2>
                  <div className="sv-result-tags">
                    <Tooltip title="接口只返回类别级分数，不返回商品明细">
                      <Tag bordered={false}>类别级 top3</Tag>
                    </Tooltip>
                    <Tag bordered={false} className="sv-mono">
                      score {formatScore(result.score)}
                    </Tag>
                  </div>
                </div>
                <ConfidenceRing value={result.confidence} label="置信度" />
              </div>

              <div className="sv-topk">
                <div className="sv-subhead">
                  <h3>前三类别</h3>
                  <span>最高相似度排序</span>
                </div>
                {(result.topk || []).map((row) => (
                  <div className="sv-topk-row" key={row.category}>
                    <CategoryGlyph category={row.category} size={34} />
                    <div className="sv-topk-main">
                      <div className="sv-topk-head">
                        <span>{row.category}</span>
                        <span className="sv-mono">{formatPercent(row.similarity)}</span>
                      </div>
                      <SimilarityBar value={row.similarity} compact />
                    </div>
                  </div>
                ))}
              </div>

              <div className="sv-note">
                <strong>怎么读这个结果</strong>
                <p>
                  置信度来自 9 类最高相似度做 softmax；分数低不代表图坏了，只是不同类别之间拉不开差距。
                  需要看具体商品时，去文本检索或图文匹配页。
                </p>
              </div>

              <div className="sv-result-actions">
                <Button type="primary" onClick={useInMatch} disabled={!file}>
                  用这张图做图文匹配
                </Button>
                <Button onClick={() => navigate(`/text?category=${encodeURIComponent(result.category || '')}`)}>
                  看看「{result.category}」类商品
                </Button>
                <Button type="text" onClick={clearAll}>
                  换一张图
                </Button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
