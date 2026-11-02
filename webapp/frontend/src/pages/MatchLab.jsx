import { useEffect, useRef, useState } from 'react'
import { App as AntApp, Button, Tooltip } from 'antd'
import {
  ArrowRightOutlined,
  CameraOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  DeleteOutlined,
  FileTextOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { matchImageText } from '../api/client'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { DEMO_PAIRS, categoryStyle } from '../constants/catalog'
import { isCanceled } from '../utils/errors'
import { fileFromUrl, validateImageFile } from '../utils/samples'
import { formatDuration, formatPercent } from '../utils/format'
import { resolveItemImage } from '../utils/itemImage'
import { ErrorNotice } from '../components/common/Ui'
import { DetailDrawer } from '../components/result/Results'

const TOPK_PRESETS = [3, 5, 10]
const TEXT_SAMPLES = ['白色运动鞋', '黑色双肩包', '粉色连衣裙']

// 后端还没回传双塔置信度 / 细分类时用的示例值；页面会挂「示例数值」标识。
// 换到真实模型后 image_confidence / text_confidence / text_type 一到位就自动显示真值。
const SAMPLE_FILL = {
  imageConfidence: 0.91,
  imageType: '女士小板鞋',
  textConfidence: 0.88,
  textType: '休闲鞋',
}

function fixed2(value) {
  return Number.isFinite(value) ? value.toFixed(2) : '—'
}

export default function MatchLab() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const { addRun, isPlaceholder } = useApp()
  const { stageImage, stageText, takeImage, takeText } = useWorkflow()
  const [searchParams] = useSearchParams()

  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [text, setText] = useState('')
  const [topK, setTopK] = useState(5)
  const [result, setResult] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [demoLoading, setDemoLoading] = useState(null)
  const [error, setError] = useState(null)
  const [validation, setValidation] = useState(null)
  const [duration, setDuration] = useState(null)
  const [dragOver, setDragOver] = useState(false)

  const previewRef = useRef('')
  const abortRef = useRef(null)
  const initRef = useRef(false)
  const fileInputRef = useRef(null)

  function replacePreview(nextFile) {
    const next = URL.createObjectURL(nextFile)
    if (previewRef.current && previewRef.current.startsWith('blob:')) {
      URL.revokeObjectURL(previewRef.current)
    }
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

  function clearImage() {
    if (previewRef.current && previewRef.current.startsWith('blob:')) {
      URL.revokeObjectURL(previewRef.current)
    }
    previewRef.current = ''
    setFile(null)
    setPreviewUrl('')
    setResult(null)
    setDuration(null)
  }

  async function runMatch(fileArg, textArg, topKArg) {
    const activeFile = fileArg || file
    const activeText = String(textArg ?? text).trim()
    const activeTopK = topKArg ?? topK

    if (!activeFile) {
      setValidation('先放一张商品图')
      return
    }
    if (!activeText) {
      setValidation('再写一句中文描述，比如「白色运动鞋」')
      return
    }
    setValidation(null)

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    setResult(null)
    setSelected(null)
    const startedAt = performance.now()

    try {
      const data = await matchImageText(
        { file: activeFile, text: activeText, topK: activeTopK },
        controller.signal,
      )
      const elapsed = performance.now() - startedAt
      setResult(data)
      setDuration(elapsed)
      addRun({
        mode: 'match',
        input: { fileName: activeFile.name, text: activeText, topK: activeTopK },
        summary: {
          match: data.match,
          imageCategory: data.image_category,
          textCategory: data.text_category,
          itemCount: data.items?.length || 0,
        },
        status: 'ok',
        code: 0,
        durationMs: elapsed,
        placeholder: isPlaceholder,
      })
      message.success(data.match ? '图文一致' : '图文不一致，见下方证据')
    } catch (requestError) {
      if (isCanceled(requestError)) return
      setError(requestError)
      addRun({
        mode: 'match',
        input: { fileName: activeFile.name, text: activeText, topK: activeTopK },
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

  async function applyDemo(kind) {
    const pair = DEMO_PAIRS.find((item) => item.key === kind)
    if (!pair) return
    setDemoLoading(kind)
    setValidation(null)
    setError(null)
    try {
      const demoFile = await fileFromUrl(pair.image.src, `${pair.image.key}.jpg`)
      setFile(demoFile)
      replacePreview(demoFile)
      setText(pair.text)
      await runMatch(demoFile, pair.text)
    } catch (demoError) {
      if (!isCanceled(demoError)) setError(demoError)
    } finally {
      setDemoLoading(null)
    }
  }

  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    const pendingImage = takeImage()
    if (pendingImage?.file) {
      setFile(pendingImage.file)
      setPreviewUrl(pendingImage.previewUrl || '')
      previewRef.current = pendingImage.previewUrl || ''
    }

    const pendingText = takeText()
    const textFromUrl = searchParams.get('text') || ''
    const initialText = pendingText || textFromUrl
    if (initialText) setText(initialText)

    const demo = searchParams.get('demo')
    if (demo === 'match' || demo === 'mismatch') {
      applyDemo(demo)
    }
    // 只在首次进入时读取跨页交接与 URL 参数
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => () => {
    if (previewRef.current && previewRef.current.startsWith('blob:')) {
      URL.revokeObjectURL(previewRef.current)
    }
  }, [])

  function useImageInClassification() {
    if (!file) return
    stageImage({ file, previewUrl, name: file.name, size: file.size })
    navigate('/image')
  }

  function useTextInSearch() {
    if (!text.trim()) return
    stageText(text)
    navigate(`/text?q=${encodeURIComponent(text.trim())}`)
  }

  function searchItemName(name) {
    const keyword = String(name || '').trim()
    if (!keyword) return
    stageText(keyword)
    navigate(`/text?q=${encodeURIComponent(keyword)}`)
  }

  const imageSample = !Number.isFinite(result?.image_confidence)
  const textSample = !Number.isFinite(result?.text_confidence) || !result?.text_type
  const imageConfidence = Number.isFinite(result?.image_confidence)
    ? result.image_confidence
    : SAMPLE_FILL.imageConfidence
  const textConfidence = Number.isFinite(result?.text_confidence)
    ? result.text_confidence
    : SAMPLE_FILL.textConfidence
  const imageType = result?.image_type || SAMPLE_FILL.imageType
  const textType = result?.text_type || result?.items?.[0]?.type || SAMPLE_FILL.textType

  return (
    <div className="sv-mm">
      <div className="sv-mm-glow" aria-hidden="true">
        <i />
        <i />
      </div>

      {/* 标题区 */}
      <header className="sv-mm-head">
        <div>
          <span className="sv-eyebrow">Chinese-CLIP 双塔 · 图文匹配</span>
          <h1>
            <i className="sv-mm-dot is-green" aria-hidden="true" />
            图文匹配页
          </h1>
          <p>
            <i className="sv-mm-dot is-blue" aria-hidden="true" />
            POST /match · 输入图片和句子，看两个模型分别怎么判，再核对它们是否指向同一个类别。
          </p>
        </div>
        <div className="sv-mm-head-actions">
          <Tooltip title="图像塔与文本塔各自独立判类，只比顶层大类，不比细分类">
            <button type="button" className="sv-mm-help" aria-label="使用帮助">
              <QuestionCircleOutlined />
            </button>
          </Tooltip>
        </div>
      </header>

      {/* 模块 1：输入区 */}
      <section className="sv-mm-card sv-mm-input">
        <div className="sv-mm-card-head">
          <h2>输入区</h2>
          <span>左图右文，同时喂给两条链路</span>
          <div className="sv-mm-demos">
            <button type="button" onClick={() => applyDemo('match')} disabled={Boolean(demoLoading)}>
              <ThunderboltOutlined /> 一致示例
            </button>
            <button type="button" onClick={() => applyDemo('mismatch')} disabled={Boolean(demoLoading)}>
              <ThunderboltOutlined /> 不一致示例
            </button>
          </div>
        </div>

        <div className="sv-mm-input-grid">
          {/* 图像输入 */}
          <div className="sv-mm-slot">
            <div className="sv-mm-slot-head">
              <span className="sv-mm-slot-title">
                <CameraOutlined /> 图像输入
              </span>
              <span className="sv-mm-slot-note">图像塔的输入源</span>
            </div>

            <div
              className={`sv-mm-drop ${previewUrl ? 'has-file' : ''} ${dragOver ? 'is-drag' : ''}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(event) => {
                event.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragOver(false)
                const dropped = event.dataTransfer.files?.[0]
                if (dropped) selectFile(dropped)
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') fileInputRef.current?.click()
              }}
            >
              {previewUrl ? (
                <>
                  <img src={previewUrl} alt="待匹配商品图" />
                  <span className="sv-mm-drop-actions">
                    <button type="button" onClick={(event) => {
                      event.stopPropagation()
                      fileInputRef.current?.click()
                    }}>
                      更换
                    </button>
                    <button type="button" className="is-danger" onClick={(event) => {
                      event.stopPropagation()
                      clearImage()
                    }}>
                      <DeleteOutlined /> 移除
                    </button>
                  </span>
                </>
              ) : (
                <span className="sv-mm-drop-empty">
                  <i className="sv-mm-drop-icon">
                    <CameraOutlined />
                  </i>
                  <strong>拖入商品图，或点击上传</strong>
                  <small>PNG / JPG / WEBP · 单张 ≤ 10MB</small>
                </span>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              style={{ display: 'none' }}
              onChange={(event) => {
                const picked = event.target.files?.[0]
                if (picked) selectFile(picked)
                event.target.value = ''
              }}
            />
          </div>

          {/* 文本输入 */}
          <div className="sv-mm-slot">
            <div className="sv-mm-slot-head">
              <span className="sv-mm-slot-title">
                <FileTextOutlined /> 文本输入
              </span>
              <span className="sv-mm-slot-note">文本塔的输入源</span>
            </div>

            <div className="sv-mm-text">
              <textarea
                value={text}
                rows={5}
                maxLength={200}
                placeholder="例如：白色运动鞋"
                onChange={(event) => {
                  setText(event.target.value)
                  if (validation) setValidation(null)
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    runMatch()
                  }
                }}
              />
              <div className="sv-mm-text-foot">
                <span>Enter 运行 · Shift + Enter 换行</span>
                <span className="sv-mono">{text.length} / 200</span>
              </div>
            </div>

            <div className="sv-mm-text-samples">
              {TEXT_SAMPLES.map((item) => (
                <button
                  type="button"
                  key={item}
                  className={text === item ? 'is-active' : ''}
                  onClick={() => {
                    setText(item)
                    setResult(null)
                  }}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          {/* 运行区 */}
          <div className="sv-mm-run">
            <span className="sv-mm-run-label">证据条数</span>
            <div className="sv-mm-topk">
              {TOPK_PRESETS.map((preset) => (
                <button
                  type="button"
                  key={preset}
                  className={topK === preset ? 'is-active' : ''}
                  onClick={() => setTopK(preset)}
                >
                  {preset}
                </button>
              ))}
            </div>
            <Button
              type="primary"
              size="large"
              className="sv-mm-run-btn"
              loading={loading}
              disabled={!file || !text.trim()}
              onClick={() => runMatch()}
            >
              运行推理 <ArrowRightOutlined />
            </Button>
            {validation && <span className="sv-mm-validate">{validation}</span>}
          </div>
        </div>
      </section>

      {error && !loading && (
        <ErrorNotice error={error} onRetry={() => runMatch()} onDismiss={() => setError(null)} />
      )}

      {/* 模块 2：双塔判断 */}
      <section className="sv-mm-card">
        <div className="sv-mm-bar is-blue">
          <span className="sv-mm-bar-title">双塔判断</span>
          <span className="sv-mm-bar-note">两条独立编码链路，分开预测，再比对结果</span>
          {duration != null && !loading && (
            <span className="sv-mm-bar-time sv-mono">{formatDuration(duration)}</span>
          )}
        </div>

        {loading ? (
          <div className="sv-mm-loading" role="status" aria-live="polite">
            <span className="sv-mm-ring" aria-hidden="true" />
            <strong>双塔正在分别编码...</strong>
            <span>图像塔判一次类别，文本塔再判一次，最后核对是否一致</span>
          </div>
        ) : (
          <>
            <div className="sv-mm-towers">
              <div className="sv-mm-tower is-image">
                <div className="sv-mm-tower-head">
                  <i className="sv-mm-dot is-teal" aria-hidden="true" />
                  图像塔
                  {imageSample && result && <em>示例数值</em>}
                </div>
                <div className="sv-mm-tower-thumb">
                  {previewUrl ? <img src={previewUrl} alt="图像塔输入" /> : <i><CameraOutlined /></i>}
                </div>
                <dl className="sv-mm-facts">
                  <div>
                    <dt>类别</dt>
                    <dd>{result?.image_category || '—'}</dd>
                  </div>
                  <div>
                    <dt>细分类</dt>
                    <dd>{result ? imageType : '—'}</dd>
                  </div>
                  <div>
                    <dt>置信度</dt>
                    <dd className="sv-mm-figure sv-mono">{result ? fixed2(imageConfidence) : '—'}</dd>
                  </div>
                </dl>
              </div>

              <div className="sv-mm-link" aria-hidden="true">
                <span className="sv-mm-link-line" />
                <span className="sv-mm-link-badge">各自判类</span>
                <span className="sv-mm-link-line" />
              </div>

              <div className="sv-mm-tower is-text">
                <div className="sv-mm-tower-head">
                  <i className="sv-mm-dot is-blue" aria-hidden="true" />
                  文本塔
                  {textSample && result && <em>示例数值</em>}
                </div>
                <div className="sv-mm-tower-thumb is-text">
                  {result ? (
                    <>
                      <FileTextOutlined />
                      <span>{result.text_category || '未判定'}</span>
                    </>
                  ) : (
                    <i><FileTextOutlined /></i>
                  )}
                </div>
                <dl className="sv-mm-facts">
                  <div>
                    <dt>类别</dt>
                    <dd>{result?.text_category || '—'}</dd>
                  </div>
                  <div>
                    <dt>细分类</dt>
                    <dd>{result ? textType : '—'}</dd>
                  </div>
                  <div>
                    <dt>置信度</dt>
                    <dd className="sv-mm-figure sv-mono">{result ? fixed2(textConfidence) : '—'}</dd>
                  </div>
                </dl>
              </div>
            </div>

            {result ? (
              <div className={`sv-mm-verdict ${result.match ? 'is-match' : 'is-mismatch'}`}>
                <span className="sv-mm-verdict-icon">
                  {result.match ? <CheckCircleFilled /> : <CloseCircleFilled />}
                </span>
                <div>
                  <strong>{result.match ? '一致' : '不一致'}</strong>
                  <span>
                    {result.match
                      ? '图像类别与文本类别相同'
                      : `图像判「${result.image_category || '—'}」，文本判「${result.text_category || '—'}」`}
                  </span>
                </div>
              </div>
            ) : (
              <div className="sv-mm-verdict is-idle">
                <span className="sv-mm-verdict-icon">
                  <QuestionCircleOutlined />
                </span>
                <div>
                  <strong>等待一次比对</strong>
                  <span>放图、写句，点右上角「运行推理」；只比顶层大类，不比细分类</span>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {/* 模块 3：证据列表 */}
      <section className="sv-mm-card sv-mm-evidence">
        <div className="sv-mm-bar is-green">
          <span className="sv-mm-bar-title">证据列表</span>
          <span className="sv-mm-bar-note">
            文本检索结果，用于解释判断：这句话在文本塔的向量空间里最像哪些商品
          </span>
          {isPlaceholder && <span className="sv-mm-bar-warm">占位模式</span>}
        </div>

        {result?.items?.length ? (
          <>
            <div className="sv-mm-table">
              <div className="sv-mm-tr is-head">
                <span>预览图</span>
                <span>相似度</span>
                <span>类别</span>
                <span>细分类</span>
              </div>
              {result.items.map((item, index) => {
                const style = categoryStyle(item.category)
                const isSame = item.category === result.text_category
                return (
                  <button
                    type="button"
                    key={`${item.item_id || 'item'}-${index}`}
                    className="sv-mm-tr"
                    style={{ animationDelay: `${Math.min(index, 10) * 55}ms` }}
                    onClick={() => setSelected(item)}
                  >
                    <span className="sv-mm-ev-photo" style={{ background: style.bg }}>
                      <img
                        src={resolveItemImage(item)}
                        alt={item.item_name || '商品图'}
                        loading="lazy"
                        onError={(event) => {
                          event.currentTarget.closest('.sv-mm-ev-photo').classList.add('is-broken')
                          event.currentTarget.remove()
                        }}
                      />
                    </span>
                    <span className="sv-mm-ev-sim">
                      <span className="sv-mm-ev-track">
                        <i style={{ '--w': `${Math.max(0, Math.min(1, item.similarity)) * 100}%` }} />
                      </span>
                      <span className="sv-mono">{formatPercent(item.similarity)}</span>
                    </span>
                    <span className="sv-mm-ev-cat" style={{ background: style.bg, color: style.ink }}>
                      {item.category || '未分类'}
                      {isSame && <CheckCircleFilled />}
                    </span>
                    <span className="sv-mm-ev-type">{item.type || '—'}</span>
                  </button>
                )
              })}
            </div>
            <span className="sv-mm-float-tip">图像类别 == 文本类别 → 一致</span>
          </>
        ) : (
          <div className="sv-mm-ev-empty">
            <FileTextOutlined />
            <div>
              <strong>还没有证据</strong>
              <span>运行一次推理后，文本塔检索到的商品会按相似度排在这里。</span>
            </div>
          </div>
        )}

        {result && (
          <div className="sv-mm-actions">
            <Button size="small" onClick={useImageInClassification} disabled={!file}>
              单独分析这张图
            </Button>
            <Button size="small" onClick={useTextInSearch} disabled={!text.trim()}>
              单独检索这句话
            </Button>
          </div>
        )}
      </section>

      <DetailDrawer
        item={selected}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        onSearch={searchItemName}
      />
    </div>
  )
}
