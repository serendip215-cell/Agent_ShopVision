import { useEffect, useRef, useState } from 'react'
import { App as AntApp, Button, Tooltip } from 'antd'
import {
  ArrowRightOutlined,
  CameraOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  DeleteOutlined,
  FileTextOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { matchImageText } from '../api/client'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { DEMO_PAIRS, SAMPLE_QUERIES } from '../constants/catalog'
import { isCanceled } from '../utils/errors'
import { fileFromUrl, validateImageFile } from '../utils/samples'
import { formatDuration } from '../utils/format'
import {
  CategoryBadge,
  EmptyState,
  ErrorNotice,
  LoadingState,
  PageHeader,
  SimilarityBar,
} from '../components/common/Ui'
import { DetailDrawer, ResultList } from '../components/result/Results'

const TOPK_PRESETS = [3, 5, 10]
const TEXT_SAMPLES = SAMPLE_QUERIES.slice(0, 3)
const IDLE_STEPS = ['上传商品图', '填写描述', '查看是否一致']

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
  const [matchedText, setMatchedText] = useState('')
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
      setMatchedText(activeText)
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
      message.success(data.match ? '图文一致' : '图文不一致')
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

  const imageConfidence = Number.isFinite(result?.image_confidence) ? result.image_confidence : null
  const textConfidence = Number.isFinite(result?.text_confidence) ? result.text_confidence : null
  const textType = result?.text_type || result?.items?.[0]?.type || null
  const submittedText = matchedText || text
  const items = result?.items || []

  return (
    <div className="sv-mm">
      <div className="sv-mm-glow" aria-hidden="true">
        <i />
        <i />
      </div>

      <PageHeader
        eyebrow="图文一致性校验"
        title="这张图和描述说的是同一件商品吗"
        description="上传一张商品图、写一句中文描述，分别识别两侧的类别，再核对它们是否指向同一类商品。"
        actions={
          <Tooltip title="两侧只比对顶层大类是否相同，不比较细分类。">
            <button type="button" className="sv-mm-help" aria-label="使用帮助">
              <QuestionCircleOutlined />
            </button>
          </Tooltip>
        }
      />

      <div className="sv-mm-body">
        {/* 左栏：比对准备 */}
        <section className="sv-mm-card sv-mm-input">
          <div className="sv-mm-card-head">
            <h2>比对准备</h2>
            <span>先准备图片和描述，再开始比对</span>
          </div>

          <div className="sv-mm-slot">
            <div className="sv-mm-slot-head">
              <span className="sv-mm-slot-title">
                <CameraOutlined /> 图片内容
              </span>
              <span className="sv-mm-slot-note">拖拽或点击上传</span>
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
                  <img src={previewUrl} alt="待比对商品图" />
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

          <div className="sv-mm-slot">
            <div className="sv-mm-slot-head">
              <span className="sv-mm-slot-title">
                <FileTextOutlined /> 文字描述
              </span>
              <span className="sv-mm-slot-note">一句话说清是什么商品</span>
            </div>

            <div className="sv-mm-text">
              <textarea
                value={text}
                rows={3}
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
                <span>Enter 比对 · Shift + Enter 换行</span>
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

          <div className="sv-mm-run-row">
            <div className="sv-mm-run-head">
              <span className="sv-mm-run-label">参考商品条数</span>
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
            </div>
            <Button
              type="primary"
              size="large"
              block
              className="sv-mm-run-btn"
              icon={<ArrowRightOutlined />}
              iconPosition="end"
              loading={loading}
              onClick={() => runMatch()}
            >
              开始比对
            </Button>
            {validation && <span className="sv-mm-validate">{validation}</span>}
          </div>
        </section>

        {/* 右栏：结论 / 判断 / 证据 */}
        <div className="sv-mm-result">
          {!loading && result && (
            <div className={`sv-match-verdict ${result.match ? 'is-match' : 'is-mismatch'}`}>
              <span className="sv-match-verdict-icon">
                {result.match ? <CheckCircleFilled /> : <CloseCircleFilled />}
              </span>
              <div className="sv-match-verdict-copy">
                <strong>{result.match ? '图文一致' : '图文不一致'}</strong>
                <span>
                  图片判断为「{result.image_category || '—'}」，描述判断为「{result.text_category || '—'}」
                  {result.match ? '，二者一致' : '，不是同一类商品'}
                </span>
              </div>
              <div className="sv-match-verdict-side">
                {duration != null && (
                  <span className="sv-match-verdict-time">
                    <ClockCircleOutlined /> 耗时 <em className="sv-mono">{formatDuration(duration)}</em>
                  </span>
                )}
                <div className="sv-match-verdict-actions">
                  <Button size="small" onClick={useImageInClassification} disabled={!file}>
                    单独分析这张图
                  </Button>
                  <Button size="small" onClick={useTextInSearch} disabled={!text.trim()}>
                    单独检索这句描述
                  </Button>
                </div>
              </div>
            </div>
          )}

          {loading ? (
            <>
              <LoadingState
                title="正在比对图片与描述"
                description="分别识别图片与描述的类别，完成后自动展示是否一致。"
              />
              <section className="sv-mm-card sv-mm-evidence">
                <div className="sv-mm-bar is-green">
                  <span className="sv-mm-bar-title">参考商品证据</span>
                  <span className="sv-mm-bar-note">与描述语义相近的商品，用于查看判断依据</span>
                </div>
                <ResultList items={[]} loading />
              </section>
            </>
          ) : result ? (
            <>
              <div className="sv-mm-compare">
                <div className="sv-mm-subhead">
                  <span className="sv-mm-bar-title">两侧判断对照</span>
                </div>
                <div className="sv-match-facts">
                  <div className="sv-match-fact-card">
                    <h3>图片判断</h3>
                    <div className="sv-match-fact-photo">
                      {previewUrl ? <img src={previewUrl} alt="待比对商品图" /> : <CameraOutlined />}
                    </div>
                    <div className="sv-match-fact-tags">
                      <CategoryBadge category={result.image_category} small />
                    </div>
                    {imageConfidence != null ? (
                      <SimilarityBar label="判断置信度" value={imageConfidence} compact />
                    ) : (
                      <span className="sv-mm-na">等待结果</span>
                    )}
                  </div>

                  <div className="sv-match-fact-card">
                    <h3>描述判断</h3>
                    <div className="sv-match-fact-text">
                      <span className="sv-match-quote">“</span>
                      {submittedText || '尚未填写描述'}
                    </div>
                    <div className="sv-match-fact-tags">
                      <CategoryBadge category={result.text_category} small />
                      {textType && <span className="sv-match-type-tag">{textType}</span>}
                    </div>
                    {textConfidence != null ? (
                      <SimilarityBar label="判断置信度" value={textConfidence} compact />
                    ) : (
                      <span className="sv-mm-na">等待结果</span>
                    )}
                  </div>
                </div>
              </div>

              <section className="sv-mm-card sv-mm-evidence">
                <div className="sv-mm-bar is-green">
                  <span className="sv-mm-bar-title">参考商品证据</span>
                  <span className="sv-mm-bar-note">与这句描述语义相近的商品，按相似度排列，用于查看判断依据</span>
                </div>
                <ResultList
                  items={items}
                  loading={false}
                  onSelect={setSelected}
                  highlightCategory={result.text_category}
                  emptyTitle="暂无参考商品"
                  emptyDescription="这次比对没有返回相近商品，可以换一句描述再试。"
                />
              </section>
            </>
          ) : error ? (
            <ErrorNotice error={error} onRetry={() => runMatch()} onDismiss={() => setError(null)} />
          ) : (
            <section className="sv-mm-card sv-mm-idle">
              <EmptyState
                icon={<QuestionCircleOutlined />}
                title="还没有比对结果"
                description="在左侧准备好图片和描述，或直接用示例快速体验一次比对。"
                action={
                  <>
                    <div className="sv-idle-steps">
                      {IDLE_STEPS.map((step, index) => (
                        <div className="sv-idle-step" key={step}>
                          <b>{index + 1}</b>
                          <span>{step}</span>
                        </div>
                      ))}
                    </div>
                    <div className="sv-idle-actions">
                      <Button
                        type="primary"
                        ghost
                        size="middle"
                        onClick={() => applyDemo('match')}
                        disabled={Boolean(demoLoading)}
                      >
                        一致示例
                      </Button>
                      <Button
                        type="text"
                        size="middle"
                        onClick={() => applyDemo('mismatch')}
                        disabled={Boolean(demoLoading)}
                      >
                        不一致示例
                      </Button>
                    </div>
                  </>
                }
              />
            </section>
          )}
        </div>
      </div>

      <DetailDrawer
        item={selected}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        onSearch={searchItemName}
      />
    </div>
  )
}
