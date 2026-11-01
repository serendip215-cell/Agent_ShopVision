import { useEffect, useRef, useState } from 'react'
import { App as AntApp, Button, Tooltip } from 'antd'
import {
  ArrowRightOutlined,
  CameraOutlined,
  CheckCircleOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { classifyImage } from '../api/client'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { DEMO_IMAGES } from '../constants/catalog'
import { isCanceled } from '../utils/errors'
import { fileFromUrl, validateImageFile } from '../utils/samples'
import { formatScore } from '../utils/format'

/* ---------- 小工具 ---------- */

// 置信度大数字：识别完成时从 0 缓动跳到目标值
function useCountUp(target, { delay = 260, duration = 950 } = {}) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (target == null) {
      setValue(0)
      return
    }
    let raf
    const start = performance.now() + delay
    const tick = (now) => {
      const t = Math.min(1, Math.max(0, (now - start) / duration))
      const eased = 1 - Math.pow(1 - t, 3)
      setValue(target * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, delay, duration])
  return value
}

// 把接口错误翻成普通用户能懂的话，不露错误码
function friendlyError(error) {
  if (!error) return null
  if (error.code === 40004) return '图片超出 10MB 上限，请更换一张更小的图片'
  if (error.code === 40001 || error.code === 40002) return '文件格式不支持，请上传 PNG / JPG / WEBP 图片'
  return '识别没有成功，请重试或换一张商品图'
}

// Top3 相似度 -> 前端本地 softmax，得到能相加为 100% 的展示概率
function topkPercents(result) {
  const rows = result?.topk || []
  if (!rows.length) return []
  const values = rows.map((row) => Math.exp(Number(row.similarity) || 0))
  const sum = values.reduce((acc, value) => acc + value, 0) || 1
  return rows.map((row, index) => ({
    ...row,
    percent: (values[index] / sum) * 100,
  }))
}

function plainWords(result) {
  if (!result?.category) return null
  const percent = (result.confidence * 100).toFixed(1)
  const others = topkPercents(result)
    .filter((row) => row.category !== result.category)
    .slice(0, 2)
  const tail = others.length
    ? `，同时觉得它有一点「${others.map((row) => row.category).join('」「')}」的特征`
    : ''
  return `AI 第一眼认为这是「${result.category}」（${percent}% 把握）${tail}。`
}

/* ---------- 页面 ---------- */

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
  const [dragOver, setDragOver] = useState(false)
  const [duration, setDuration] = useState(null)
  // 本页历史：缩略图 + 结果标签，支持批量连续测试后回看
  const [history, setHistory] = useState([])
  const [batch, setBatch] = useState(null) // { index, total } 批量测试进度

  const previewRef = useRef('')
  const abortRef = useRef(null)
  const initRef = useRef(false)
  const batchInputRef = useRef(null)

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

  useEffect(() => () => {
    if (previewRef.current?.startsWith('blob:')) URL.revokeObjectURL(previewRef.current)
  }, [])

  function replacePreview(nextFile) {
    const next = URL.createObjectURL(nextFile)
    if (previewRef.current?.startsWith('blob:')) URL.revokeObjectURL(previewRef.current)
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
    if (previewRef.current?.startsWith('blob:')) URL.revokeObjectURL(previewRef.current)
    previewRef.current = ''
    setFile(null)
    setPreviewUrl('')
    setResult(null)
    setError(null)
    setValidation(null)
    setDuration(null)
  }

  function rememberRun(fileName, fileObj, thumb, data) {
    setHistory((prev) => [
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        fileName,
        file: fileObj,
        thumb,
        result: data,
        category: data.category,
        confidence: data.confidence,
      },
      ...prev,
    ])
  }

  async function analyze(inputFile = file) {
    const activeFile = inputFile || file
    if (!activeFile) {
      setValidation('请先选择一张商品图')
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    setResult(null)
    const startedAt = performance.now()

    try {
      const data = await classifyImage(activeFile, controller.signal)
      const elapsed = performance.now() - startedAt
      setResult(data)
      setDuration(elapsed)
      rememberRun(activeFile.name, activeFile, previewRef.current, data)
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
        durationMs: elapsed,
        placeholder: isPlaceholder,
      })
      message.success(`已判定为「${data.category || '未分类'}」`)
    } catch (requestError) {
      if (isCanceled(requestError)) return
      setError(requestError)
      addRun({
        mode: 'image',
        input: { fileName: activeFile.name, size: activeFile.size },
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

  async function loadSample(sample) {
    setValidation(null)
    try {
      const sampleFile = await fileFromUrl(sample.src, `${sample.key}.jpg`)
      const samplePreview = sample.src
      if (previewRef.current?.startsWith('blob:')) URL.revokeObjectURL(previewRef.current)
      previewRef.current = samplePreview
      setPreviewUrl(samplePreview)
      setFile(sampleFile)
      setResult(null)
      setError(null)
      setDuration(null)
      await analyze(sampleFile)
    } catch (loadError) {
      if (!isCanceled(loadError)) setError(loadError)
    }
  }

  // 批量连续测试：依次识别，每张都进历史
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
      // 逐张串行识别；历史里已带缩略图与结果
      // eslint-disable-next-line no-await-in-loop
      await analyze(batchFile)
    }
    setBatch(null)
  }

  function reviewHistory(entry) {
    setPreviewUrl(entry.thumb)
    setFile(entry.file)
    setResult(entry.result)
    setError(null)
    setValidation(null)
    setDuration(null)
  }

  function useInMatch() {
    if (!file || !previewUrl) return
    stageImage({ file, previewUrl, name: file.name, size: file.size })
    navigate('/match')
  }

  const confidenceValue = useCountUp(result?.confidence ?? null)
  const topk = topkPercents(result)
  const plain = plainWords(result)

  return (
    <div className="sv-il">
      {/* 背景柔光与粒子，不参与交互 */}
      <div className="sv-il-glow" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>

      {/* 区块 1：页面头部 */}
      <header className="sv-il-head">
        <div className="sv-il-head-copy">
          <span className="sv-eyebrow">Chinese-CLIP 双塔 · 图像分类</span>
          <h1>上传商品图片，AI 识别商品类别</h1>
          <p>
            上传一张商品照片，AI 自动判断它属于哪一类，
            同时告诉你模型的判断把握与备选猜测。
          </p>
        </div>
        <Tooltip title="模型一共识别 9 类商品，会给出最匹配结果 + 备选猜测">
          <button type="button" className="sv-il-help" aria-label="使用帮助">
            <QuestionCircleOutlined />
          </button>
        </Tooltip>
      </header>

      {/* 区块 2/3：上传核心区（识别中切换为加载态） */}
      <section className="sv-il-upload sv-il-glass">
        {loading ? (
          <div className="sv-il-loading" role="status">
            <span className="sv-il-ring" aria-hidden="true" />
            <strong>{batch ? `AI 正在识别第 ${batch.index} / ${batch.total} 张...` : 'AI 正在解析图片特征...'}</strong>
            <span className="sv-il-loading-note">模型正在提取图像向量，对比商品类别库</span>
          </div>
        ) : (
          <>
            <div className="sv-il-upload-head">
              <h2>上传商品图</h2>
              <span className="sv-il-upload-limit">支持 PNG / JPG / WEBP · 单张 ≤ 10MB</span>
            </div>
            <label
              className={`sv-il-dropzone ${previewUrl ? 'has-file' : ''} ${dragOver ? 'is-drag' : ''}`}
              onDragOver={(event) => {
                event.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragOver(false)
                selectFile(event.dataTransfer.files?.[0])
              }}
            >
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                disabled={false}
                onChange={(event) => {
                  selectFile(event.target.files?.[0])
                  event.target.value = ''
                }}
              />
              {previewUrl ? (
                <img src={previewUrl} alt="已选择的商品图预览" />
              ) : (
                <span className="sv-il-dropzone-empty">
                  <span className="sv-il-dropzone-icon">
                    <CameraOutlined />
                  </span>
                  <strong>拖拽图片到这里，或点击上传</strong>
                  <small>图片仅用于本次识别请求</small>
                </span>
              )}
            </label>
            <div className="sv-il-samples">
              {DEMO_IMAGES.map((sample) => (
                <button
                  type="button"
                  key={sample.key}
                  className="sv-il-sample"
                  title={`直接用「${sample.label}」试试识别`}
                  onClick={() => loadSample(sample)}
                >
                  <img src={sample.src} alt={sample.label} loading="lazy" />
                  <span>{sample.label}</span>
                </button>
              ))}
              <button
                type="button"
                className="sv-il-sample is-more"
                onClick={() => batchInputRef.current?.click()}
              >
                <FolderOpenOutlined />
                <span>批量测试</span>
              </button>
              <input
                ref={batchInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                hidden
                onChange={(event) => {
                  runBatch(event.target.files)
                  event.target.value = ''
                }}
              />
            </div>
            <div className="sv-il-upload-foot">
              {validation ? (
                <span className="sv-il-inline-error">
                  <WarningOutlined /> {validation}
                </span>
              ) : (
                <span className="sv-il-upload-hint">不确定选什么？点一张示例图直接看效果</span>
              )}
              <Button
                type="primary"
                size="large"
                icon={<ArrowRightOutlined />}
                onClick={() => analyze()}
                disabled={!file}
              >
                开始识别
              </Button>
            </div>
          </>
        )}
      </section>

      {/* 区块 8：兜底错误态 */}
      {error && (
        <div className="sv-il-error" role="alert">
          <WarningOutlined />
          <div className="sv-il-error-copy">
            <strong>{friendlyError(error)}</strong>
            <span>{error.message || ''}</span>
          </div>
          <div className="sv-il-error-actions">
            <Button size="small" onClick={() => analyze()}>
              重试
            </Button>
            <Button size="small" type="text" onClick={() => setError(null)}>
              知道了
            </Button>
          </div>
        </div>
      )}

      {/* 区块 4：识别结果主卡 */}
      {result && (
        <section className="sv-il-result sv-il-glass">
          <div className="sv-il-result-grid">
            <div className="sv-il-result-photo">
              <img src={previewUrl} alt="本次识别的商品图" />
            </div>
            <div className="sv-il-result-copy">
              <span className="sv-il-result-kicker">
                <CheckCircleOutlined /> 预测类别
              </span>
              <div className="sv-il-result-cat">
                <span className="sv-il-result-cat-name">{result.category || '未判定'}</span>
              </div>
              <div className="sv-il-confidence">
                <span className="sv-il-confidence-num sv-mono">
                  {(confidenceValue * 100).toFixed(1)}
                  <em>%</em>
                </span>
                <div className="sv-il-confidence-copy">
                  <strong>置信度</strong>
                  <small>AI 对这个结果的把握程度</small>
                </div>
              </div>
              <div className="sv-il-score sv-mono">
                原始相似度分数 {formatScore(result.score)}
              </div>
              <div className="sv-il-result-actions">
                <Button size="small" type="text" onClick={useInMatch}>
                  用这张图做图文匹配 <ArrowRightOutlined />
                </Button>
                <Button
                  size="small"
                  type="text"
                  onClick={() => navigate(`/text?category=${encodeURIComponent(result.category || '')}`)}
                >
                  看看「{result.category}」类商品
                </Button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 区块 5：Top3 候选条形图 */}
      {result && topk.length > 0 && (
        <section className="sv-il-topk sv-il-glass">
          <div className="sv-il-section-head">
            <h2>AI 还在考虑这些类别</h2>
            <span>模型的备选猜测，按可能性从高到低</span>
          </div>
          <div className="sv-il-bars">
            {topk.map((row, index) => (
              <div className={`sv-il-bar-row ${index === 0 ? 'is-top' : ''}`} key={row.category}>
                <span className="sv-il-bar-name">{row.category}</span>
                <div className="sv-il-bar">
                  <i style={{ '--w': `${row.percent}%`, '--d': `${index * 170}ms` }} />
                </div>
                <span className="sv-il-bar-value sv-mono">{row.percent.toFixed(1)}%</span>
              </div>
            ))}
          </div>
          <p className="sv-il-topk-note">
            百分比为前三类相对可能性的直观展示；预测类别取模型在全部 9 类中的最高响应。
          </p>
        </section>
      )}

      {/* 区块 6：通俗解读 */}
      {result && (
        <section className="sv-il-plain sv-il-glass">
          <div className="sv-il-section-head">
            <h2>简单看懂这个结果</h2>
          </div>
          <p className="sv-il-plain-main">{plain}</p>
          <p className="sv-il-plain-sub">
            置信度越高，代表 AI 越确定；如果几个类别的数值很接近，
            说明这件商品的特征比较模糊——可以把图换到「图文匹配」页进一步验证。
          </p>
        </section>
      )}

      {/* 区块 7：连续测试与历史 */}
      <section className="sv-il-more sv-il-glass">
        <div className="sv-il-section-head">
          <h2>继续测试其他商品图</h2>
          <span>{history.length > 0 ? `已识别 ${history.length} 次` : '还没有识别记录'}</span>
        </div>
        <div className="sv-il-more-actions">
          <Button icon={<ReloadOutlined />} onClick={clearAll}>
            重新上传图片
          </Button>
          <Button icon={<FolderOpenOutlined />} onClick={() => batchInputRef.current?.click()}>
            批量连续测试
          </Button>
          {isPlaceholder && (
            <span className="sv-il-placeholder-note">
              当前为占位编码器：链路可用，但识别结果无参考意义
            </span>
          )}
        </div>
        {history.length > 0 && (
          <div className="sv-il-history">
            {history.map((entry) => (
              <button
                type="button"
                key={entry.id}
                className={`sv-il-history-card ${result === entry.result ? 'is-active' : ''}`}
                onClick={() => reviewHistory(entry)}
              >
                <img src={entry.thumb} alt={entry.fileName} />
                <span className="sv-il-history-cat">{entry.category || '未判定'}</span>
                <span className="sv-il-history-pct sv-mono">
                  {((entry.confidence || 0) * 100).toFixed(1)}%
                </span>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
