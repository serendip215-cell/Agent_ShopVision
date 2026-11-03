import { useEffect, useRef, useState } from 'react'
import { App as AntApp, AutoComplete, Button, Input, Progress, Segmented, Tag } from 'antd'
import { CameraOutlined, CloudUploadOutlined, ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { ingestAdminItem, suggestAdminItem } from '../api/client'
import { useApp } from '../context/AppContext'
import { useImagePreview } from '../hooks/useImagePreview'
import { useAsyncRequest } from '../hooks/useAsyncRequest'
import { validateImageFile } from '../utils/samples'
import { isCanceled } from '../utils/errors'
import { formatScore } from '../utils/format'
import {
  CategoryGlyph,
  ErrorNotice,
  PageHeader,
  SectionLabel,
  SimilarityBar,
  SuccessNote,
} from '../components/common/Ui'

const EMPTY_META = {
  item_name: '',
  type: '',
  color: '',
  material: '',
  brand: '',
  description: '',
}

const META_FIELDS = [
  { key: 'item_name', label: '商品标题', placeholder: '例如：白色轻便运动鞋' },
  { key: 'type', label: '细分类', placeholder: '例如：女士小板鞋' },
  { key: 'color', label: '颜色', placeholder: '例如：白色' },
  { key: 'material', label: '材质', placeholder: '例如：网面' },
  { key: 'brand', label: '品牌', placeholder: '可留空' },
]

export default function Admin() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const { categories, healthLoading, isPlaceholder, refreshHealth } = useApp()
  const { previewUrl, replace, clear, releaseAll } = useImagePreview()

  const [mode, setMode] = useState('single')
  const [file, setFile] = useState(null)
  const [validation, setValidation] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [category, setCategory] = useState('')
  const [meta, setMeta] = useState(EMPTY_META)
  const [result, setResult] = useState(null)
  const [batchFiles, setBatchFiles] = useState([])
  const [batchSkipped, setBatchSkipped] = useState(0)
  const [batchResults, setBatchResults] = useState([])
  const [batchRunning, setBatchRunning] = useState(false)
  const batchAbortRef = useRef(null)

  const suggestion = useAsyncRequest(suggestAdminItem)
  const ingest = useAsyncRequest(ingestAdminItem)
  const abortSuggestion = suggestion.abort
  const abortIngest = ingest.abort

  useEffect(() => {
    if (mode !== 'single' || !file || isPlaceholder) return undefined
    suggestion.execute(file).catch(() => {
      // 错误已由 useAsyncRequest 收进 error，页面用 ErrorNotice 展示
    })
    return () => suggestion.abort()
    // 只在换图时重新建议；execute 是稳定回调
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, mode])

  useEffect(
    () => () => {
      abortSuggestion()
      abortIngest()
      batchAbortRef.current?.abort()
      releaseAll()
    },
    [abortSuggestion, abortIngest, releaseAll]
  )

  function selectFile(nextFile) {
    const invalid = validateImageFile(nextFile)
    setValidation(invalid)
    if (invalid) return
    setFile(nextFile)
    replace(nextFile)
    setResult(null)
    ingest.clearError()
  }

  function reset() {
    clear()
    setFile(null)
    setValidation(null)
    setCategory('')
    setMeta(EMPTY_META)
    setResult(null)
    setBatchFiles([])
    setBatchSkipped(0)
    setBatchResults([])
    suggestion.clearResult()
    suggestion.clearError()
    ingest.clearResult()
    ingest.clearError()
  }

  function changeMode(next) {
    if (batchRunning || ingest.loading) return
    setMode(next)
    reset()
  }

  function selectBatchFiles(list) {
    const picked = Array.from(list || [])
    const valid = picked.filter((item) => !validateImageFile(item))
    setBatchFiles(valid)
    setBatchSkipped(picked.length - valid.length)
    setBatchResults([])
    batchAbortRef.current?.abort()
    ingest.clearError()
  }

  async function submitBatch() {
    const trimmed = category.trim()
    if (!batchFiles.length || !trimmed || isPlaceholder || batchRunning) return
    const controller = new AbortController()
    batchAbortRef.current = controller
    setBatchRunning(true)
    setBatchResults([])
    const rows = []
    const createCategory = !categories.includes(trimmed)
    try {
      for (const current of batchFiles) {
        if (controller.signal.aborted) break
        try {
          const data = await ingestAdminItem(
            {
              file: current,
              category: trimmed,
              createCategory,
              metadata: { item_name: current.name.replace(/\.[^.]+$/, '') },
            },
            controller.signal
          )
          rows.push({
            name: current.name,
            status: data.duplicate ? 'duplicate' : 'created',
            itemId: data.item_id,
          })
        } catch (err) {
          if (isCanceled(err)) break
          rows.push({ name: current.name, status: 'failed', message: err?.message })
        }
        setBatchResults([...rows])
      }
    } finally {
      batchAbortRef.current = null
      setBatchRunning(false)
      refreshHealth()
    }
  }

  function handleDragOver(event) {
    event.preventDefault()
    setDragging(true)
  }

  function handleDragLeave(event) {
    if (event.currentTarget.contains(event.relatedTarget)) return
    setDragging(false)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    const dropped = Array.from(event.dataTransfer.files || [])
    if (!dropped.length) return
    if (mode === 'batch') selectBatchFiles(dropped)
    else selectFile(dropped[0])
  }

  const suggested = suggestion.result
  const trimmedCategory = category.trim()
  const isNewCategory = Boolean(trimmedCategory && !categories.includes(trimmedCategory))
  const canSubmit = Boolean(file && trimmedCategory && !isPlaceholder && !ingest.loading)
  const canSubmitBatch = Boolean(
    batchFiles.length && trimmedCategory && !isPlaceholder && !batchRunning
  )
  const batchDone = batchResults.length
  const batchCreated = batchResults.filter((row) => row.status === 'created').length
  const batchDuplicate = batchResults.filter((row) => row.status === 'duplicate').length
  const batchFailed = batchResults.filter((row) => row.status === 'failed').length
  const batchTotalMb = (
    batchFiles.reduce((sum, item) => sum + item.size, 0) /
    1048576
  ).toFixed(1)

  async function submit() {
    if (!canSubmit) return
    try {
      const data = await ingest.execute({
        file,
        category: trimmedCategory,
        createCategory: isNewCategory,
        metadata: meta,
      })
      setResult(data)
      refreshHealth()
      message[data.duplicate ? 'info' : 'success'](
        data.duplicate
          ? `这张图已经入过库：${data.item_id}`
          : `已入库「${data.category}」：${data.item_id}`
      )
    } catch {
      // 错误由 useAsyncRequest 收进 error
    }
  }

  return (
    <div className="sv-admin">
      <PageHeader
        eyebrow="Admin · Incremental Ingest"
        title="商品入库"
        description="把商品图追加到已有类别，或新建类别后写入首条商品；单张可先看模型建议，批量可一次选多张，入库后立即参与图像分类与文本检索。"
        meta={<Tag bordered={false}>POST /api/v1/admin/items</Tag>}
        actions={
          <div className="sv-admin-mode">
            <Segmented
              value={mode}
              onChange={changeMode}
              disabled={batchRunning || ingest.loading}
              options={[
                { label: '单张入库', value: 'single' },
                { label: '批量导入', value: 'batch' },
              ]}
            />
            <Button
              icon={<ReloadOutlined spin={healthLoading} />}
              onClick={refreshHealth}
            >
              刷新索引
            </Button>
          </div>
        }
      />

      {isPlaceholder && (
        <div className="sv-note sv-note-warm">
          <strong>占位模式禁止入库</strong>
          <p>
            占位编码器的向量没有检索意义，写入会污染真实索引。请在
            webapp/backend/.env 里设 SHOPVISION_MODEL_BACKEND=onnx 后重启。
          </p>
        </div>
      )}

      <div className="sv-admin-grid">
        <section className="sv-card sv-admin-upload">
          <SectionLabel
            index="01"
            title={mode === 'batch' ? '选择商品图（可多选）' : '选择商品图'}
            extra={
              <span className="sv-muted">
                PNG / JPG / WEBP · {mode === 'batch' ? '单张 ≤ 10MB' : '≤ 10MB'}
              </span>
            }
          />
          <label
            className={`sv-admin-drop ${mode === 'single' && previewUrl ? 'has-file' : ''} ${
              dragging ? 'is-drag' : ''
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <input
              type="file"
              multiple={mode === 'batch'}
              accept="image/png,image/jpeg,image/webp"
              disabled={batchRunning}
              onChange={(event) => {
                const picked = Array.from(event.target.files || [])
                if (mode === 'batch') selectBatchFiles(picked)
                else selectFile(picked[0])
                event.target.value = ''
              }}
            />
            {mode === 'single' ? (
              previewUrl ? (
                <img src={previewUrl} alt="待入库商品图预览" />
              ) : (
                <span className="sv-admin-drop-empty">
                  <CameraOutlined />
                  <strong>拖拽图片到这里，或点击选择</strong>
                  <small>选图后模型会先给出建议类别，不会自动写库</small>
                </span>
              )
            ) : batchFiles.length ? (
              <span className="sv-admin-drop-empty">
                <CloudUploadOutlined />
                <strong>{batchFiles.length} 张图片待入库</strong>
                <small>
                  共 {batchTotalMb} MB · 点击或拖拽可重新选择
                </small>
              </span>
            ) : (
              <span className="sv-admin-drop-empty">
                <CloudUploadOutlined />
                <strong>拖拽多张图片到这里，或点击选择</strong>
                <small>全部写入右侧的同一个类别；不逐张给建议</small>
              </span>
            )}
          </label>

          {mode === 'batch' && batchFiles.length > 0 && (
            <div className="sv-admin-batch-picked">
              <span className="sv-muted">
                已选 {batchFiles.length} 张 · 合计 {batchTotalMb} MB
              </span>
              <div className="sv-admin-batch-names">
                {batchFiles.map((item, index) => (
                  <span key={`${item.name}-${index}`} className="sv-mono">
                    {item.name}
                  </span>
                ))}
              </div>
            </div>
          )}
          {mode === 'batch' && batchSkipped > 0 && (
            <div className="sv-admin-tip is-warn">
              已跳过 {batchSkipped} 张不支持的文件：只收 PNG / JPG / WEBP，单张不超过 10 MB。
            </div>
          )}

          {validation && <div className="sv-admin-tip is-warn">{validation}</div>}
          {mode === 'single' && suggestion.loading && (
            <div className="sv-admin-tip">模型正在判断建议类别…</div>
          )}
          {mode === 'single' && suggestion.error && (
            <ErrorNotice
              error={suggestion.error}
              onRetry={() => file && suggestion.execute(file).catch(() => undefined)}
              onDismiss={suggestion.clearError}
            />
          )}

          {mode === 'single' && suggested && (
            <div className="sv-admin-suggestion">
              <SectionLabel
                index="02"
                title="模型建议"
                extra={<span className="sv-muted">只给建议，不写库</span>}
              />
              <div className="sv-admin-suggest-main">
                <CategoryGlyph category={suggested.suggested_category} size={44} />
                <div>
                  <strong>{suggested.suggested_category || '暂无建议'}</strong>
                  <span>
                    相似度 {formatScore(suggested.suggested_score)}
                    {suggested.topk?.length ? ' · 见下方候选' : ''}
                  </span>
                </div>
                {suggested.suggested_category && (
                  <Button
                    size="small"
                    onClick={() => setCategory(suggested.suggested_category)}
                  >
                    采用
                  </Button>
                )}
              </div>
              <div className="sv-admin-topk">
                {suggested.topk?.map((row) => (
                  <div key={row.category} className="sv-admin-topk-row">
                    <span>{row.category}</span>
                    <SimilarityBar value={row.similarity} compact />
                    <span className="sv-mono">{formatScore(row.similarity)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="sv-card sv-admin-form">
          <SectionLabel
            index="03"
            title={mode === 'batch' ? '确认批量入库' : '确认入库'}
            extra={<span className="sv-muted">确认前不会写库</span>}
          />
          <div className="sv-field">
            <div className="sv-field-head">
              <label htmlFor="admin-category">目标类别</label>
              <span>选已有类别，或直接输入新名称</span>
            </div>
            <AutoComplete
              id="admin-category"
              value={category}
              options={categories.map((key) => ({ value: key, label: key }))}
              onChange={setCategory}
              disabled={batchRunning || ingest.loading}
              placeholder="例如：鞋 / 测试类"
              filterOption={(input, option) =>
                String(option?.value || '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
            {isNewCategory && (
              <Tag color="gold" className="sv-admin-new-tag">
                将新建类别「{trimmedCategory}」
              </Tag>
            )}
          </div>

          {mode === 'batch' && (
            <div className="sv-admin-tip">
              批量模式按文件名写入商品标题，不逐张填元数据；所有图片写入下面这一个类别。
              成百上千张时改用 backend/scripts/bulk_ingest.py 更快。
            </div>
          )}

          {mode === 'single' && (
            <>
              {META_FIELDS.map((field) => (
                <div className="sv-field" key={field.key}>
                  <div className="sv-field-head">
                    <label htmlFor={`admin-${field.key}`}>{field.label}</label>
                  </div>
                  <Input
                    id={`admin-${field.key}`}
                    value={meta[field.key]}
                    placeholder={field.placeholder}
                    maxLength={field.key === 'item_name' ? 200 : 100}
                    onChange={(event) =>
                      setMeta((prev) => ({ ...prev, [field.key]: event.target.value }))
                    }
                  />
                </div>
              ))}

              <div className="sv-field">
                <div className="sv-field-head">
                  <label htmlFor="admin-description">商品文案</label>
                  <span>可选</span>
                </div>
                <Input.TextArea
                  id="admin-description"
                  value={meta.description}
                  rows={3}
                  maxLength={1000}
                  placeholder="例如：白色网面轻便运动鞋，适合日常通勤"
                  onChange={(event) =>
                    setMeta((prev) => ({ ...prev, description: event.target.value }))
                  }
                />
              </div>
            </>
          )}

          <div className="sv-admin-actions">
            {mode === 'single' ? (
              <Button
                type="primary"
                size="large"
                icon={<CloudUploadOutlined />}
                loading={ingest.loading}
                disabled={!canSubmit}
                onClick={submit}
              >
                确认入库
              </Button>
            ) : (
              <Button
                type="primary"
                size="large"
                icon={<CloudUploadOutlined />}
                loading={batchRunning}
                disabled={!canSubmitBatch}
                onClick={submitBatch}
              >
                批量入库{batchFiles.length ? `（${batchFiles.length} 张）` : ''}
              </Button>
            )}
            {mode === 'batch' && batchRunning && (
              <Button onClick={() => batchAbortRef.current?.abort()}>停止</Button>
            )}
            <Button onClick={reset} disabled={ingest.loading || batchRunning}>
              清空
            </Button>
          </div>

          {mode === 'single' && ingest.error && (
            <ErrorNotice
              error={ingest.error}
              onRetry={submit}
              onDismiss={ingest.clearError}
            />
          )}

          {mode === 'batch' && (batchRunning || batchDone > 0) && (
            <div className="sv-admin-result">
              <Progress
                percent={
                  batchFiles.length
                    ? Math.round((batchDone / batchFiles.length) * 100)
                    : 0
                }
                status={batchFailed ? 'exception' : batchRunning ? 'active' : 'success'}
                size="small"
              />
              <div className="sv-admin-batch-summary">
                <span>
                  已处理 {batchDone}/{batchFiles.length}
                </span>
                <span>新增 {batchCreated}</span>
                <span>重复 {batchDuplicate}</span>
                <span>失败 {batchFailed}</span>
              </div>
              <div className="sv-admin-batch-list">
                {batchResults.map((row, index) => (
                  <div className="sv-admin-batch-row" key={`${row.name}-${index}`}>
                    <span className="sv-admin-batch-name sv-mono">{row.name}</span>
                    {row.status === 'created' ? (
                      <Tag bordered={false} color="green">新增</Tag>
                    ) : row.status === 'duplicate' ? (
                      <Tag bordered={false}>重复</Tag>
                    ) : (
                      <Tag bordered={false} color="red">失败</Tag>
                    )}
                    {row.itemId ? (
                      <span className="sv-muted sv-mono">{row.itemId}</span>
                    ) : row.message ? (
                      <span className="sv-admin-batch-msg">{row.message}</span>
                    ) : null}
                  </div>
                ))}
              </div>
              {!batchRunning && batchDone > 0 && (
                <div className="sv-admin-result-actions">
                  <Button onClick={reset}>继续导入</Button>
                  {trimmedCategory && (
                    <Button
                      type="primary"
                      onClick={() =>
                        navigate(`/text?category=${encodeURIComponent(trimmedCategory)}`)
                      }
                    >
                      去检索
                    </Button>
                  )}
                </div>
              )}
            </div>
          )}

          {mode === 'single' && result && (
            <div className="sv-admin-result">
              <SuccessNote>
                {result.duplicate
                  ? '这张图已经入过库，没有重复写入。'
                  : `已写入「${result.category}」，现在就能被检索到。`}
              </SuccessNote>
              <dl className="sv-admin-result-grid">
                <div>
                  <dt>item_id</dt>
                  <dd className="sv-mono">{result.item_id || '—'}</dd>
                </div>
                <div>
                  <dt>类别</dt>
                  <dd>{result.category || '—'}</dd>
                </div>
                <div>
                  <dt>入库时间</dt>
                  <dd className="sv-mono">{result.created_at || '—'}</dd>
                </div>
                <div>
                  <dt>类别内最近邻</dt>
                  <dd className="sv-mono">
                    {result.similarity == null ? '—' : formatScore(result.similarity)}
                  </dd>
                </div>
              </dl>
              <div className="sv-admin-result-actions">
                <Button onClick={reset}>继续入库</Button>
                {result.category && (
                  <Button
                    type="primary"
                    onClick={() =>
                      navigate(`/text?category=${encodeURIComponent(result.category)}`)
                    }
                  >
                    去检索
                  </Button>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}