import { useEffect, useRef, useState } from 'react'
import { App as AntApp, Button, Input, Tag, Tooltip } from 'antd'
import {
  BlockOutlined,
  ExperimentOutlined,
  SwapOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { matchImageText } from '../api/client'
import { useApp } from '../context/AppContext'
import { useWorkflow } from '../context/WorkflowContext'
import { DEMO_IMAGES, DEMO_PAIRS } from '../constants/catalog'
import { isCanceled } from '../utils/errors'
import { fileFromUrl, validateImageFile } from '../utils/samples'
import { formatDuration } from '../utils/format'
import { DemoImageStrip, TopKSlider, UploadDropzone } from '../components/input/Inputs'
import {
  CategoryGlyph,
  EmptyState,
  ErrorNotice,
  LoadingState,
  PageHeader,
  SectionLabel,
} from '../components/common/Ui'
import { DetailDrawer, ResultList } from '../components/result/Results'

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

  const previewRef = useRef('')
  const abortRef = useRef(null)
  const initRef = useRef(false)

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

  function clearAll() {
    if (previewRef.current && previewRef.current.startsWith('blob:')) {
      URL.revokeObjectURL(previewRef.current)
    }
    previewRef.current = ''
    setFile(null)
    setPreviewUrl('')
    setText('')
    setResult(null)
    setError(null)
    setValidation(null)
    setDuration(null)
  }

  async function runMatch(fileArg, textArg, topKArg) {
    const activeFile = fileArg || file
    const activeText = String(textArg ?? text).trim()
    const activeTopK = topKArg ?? topK

    if (!activeFile) {
      setValidation('请先选择一张商品图')
      return
    }
    if (!activeText) {
      setValidation('请输入一句中文描述，例如「白色运动鞋」')
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

  return (
    <div className="sv-match-page">
      <PageHeader
        eyebrow="Instrument 03 · Cross-modal Match"
        title="图文匹配"
        description="同一件商品，图和文各自编码、各自判类别，再由系统比对一致性。文本检索不会被图片类别限制，避免循环论证。"
        meta={
          <>
            <Tag bordered={false} color="cyan">POST /api/v1/match</Tag>
            <Tag bordered={false}>file + text + top_k</Tag>
            {isPlaceholder && <Tag color="orange">结果仅联调</Tag>}
          </>
        }
        actions={
          <>
            <Button
              size="small"
              className="sv-demo-btn"
              icon={<ThunderboltOutlined />}
              loading={demoLoading === 'match'}
              onClick={() => applyDemo('match')}
            >
              一致示例
            </Button>
            <Button
              size="small"
              className="sv-demo-btn"
              icon={<ThunderboltOutlined />}
              loading={demoLoading === 'mismatch'}
              onClick={() => applyDemo('mismatch')}
            >
              不一致示例
            </Button>
          </>
        }
      />

      <div className="sv-match-input-grid">
        <section className="sv-card sv-reveal">
          <SectionLabel index="01" title="一张商品图" extra={<ExperimentOutlined />} />
          <UploadDropzone
            compact
            file={file}
            previewUrl={previewUrl}
            onSelect={selectFile}
            onClear={clearAll}
            error={validation}
            disabled={loading}
          />
          <DemoImageStrip images={DEMO_IMAGES} onPick={async (sample) => {
            try {
              const demoFile = await fileFromUrl(sample.src, `${sample.key}.jpg`)
              selectFile(demoFile)
              setText(sample.text)
            } catch (demoError) {
              setError(demoError)
            }
          }} loadingKey={null} />
        </section>

        <section className="sv-card sv-reveal">
          <SectionLabel index="02" title="一句中文描述" extra={<BlockOutlined />} />
          <div className="sv-field-head">
            <label htmlFor="sv-match-text">文本查询</label>
            <span>1–200 字</span>
          </div>
          <Input.TextArea
            id="sv-match-text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            autoSize={{ minRows: 4, maxRows: 6 }}
            maxLength={200}
            showCount
            placeholder="例如：白色运动鞋；也可以故意写成「双肩包」制造不一致。"
          />
          <TopKSlider value={topK} onChange={setTopK} />
          {validation && <div className="sv-inline-error">{validation}</div>}
          <Button
            type="primary"
            size="large"
            block
            icon={<SwapOutlined />}
            loading={loading}
            disabled={!file || !text.trim()}
            onClick={() => runMatch()}
          >
            开始比对
          </Button>
          <div className="sv-input-note">
            <span>两条链路独立编码 · 不做类别过滤，结果才可用于一致性检验</span>
          </div>
        </section>
      </div>

      <section className="sv-card sv-reveal">
        <SectionLabel
          index="03"
          title="比对结果"
          extra={duration != null ? <Tag bordered={false}>{formatDuration(duration)}</Tag> : null}
        />

        {error && <ErrorNotice error={error} onRetry={() => runMatch()} onDismiss={() => setError(null)} />}

        {loading && (
          <LoadingState
            title="双塔正在分别编码"
            description="图像塔判一次类别，文本塔再判一次；最后比对两个类别是否一致。"
          />
        )}

        {!loading && !error && !result && (
          <EmptyState
            icon={<BlockOutlined />}
            title="等待一次图文比对"
            description="左侧放图、右侧写一句描述，或直接点顶部的一致 / 不一致示例。"
          />
        )}

        {!loading && result && (
          <div className="sv-match-result">
            <div className={`sv-verdict ${result.match ? 'is-match' : 'is-mismatch'}`}>
              <div className="sv-verdict-panel">
                <span className="sv-verdict-label">图判类别</span>
                <CategoryGlyph category={result.image_category} size={66} />
                <strong>{result.image_category || '未判定'}</strong>
                <em>图像塔独立输出</em>
              </div>
              <div className={`sv-stamp ${result.match ? 'is-match' : 'is-mismatch'}`}>
                <span>{result.match ? '一致' : '不一致'}</span>
                <em>ShopVision</em>
              </div>
              <div className="sv-verdict-panel">
                <span className="sv-verdict-label">文判类别</span>
                <CategoryGlyph category={result.text_category} size={66} />
                <strong>{result.text_category || '未判定'}</strong>
                <em>文本塔独立输出</em>
              </div>
            </div>

            <div className="sv-verdict-note">
              <strong>{result.match ? '两条链路指向同一个类别' : '两条链路指向不同类别'}</strong>
              <p>
                {result.match
                  ? '这张图和这句描述在类别层面是一致的，下面的商品列表可作为文本侧的证据。'
                  : '不一致并不代表系统出错：图像和文本本来就可能描述商品的不同侧面。下方保留全类别文本检索结果，方便对照。'}
              </p>
              <div className="sv-result-tags">
                <Tag bordered={false} className="sv-mono">
                  top_k {result.items?.length || 0}
                </Tag>
                <Tooltip title="相似度来自文本检索；图像侧只提供类别判断">
                  <Tag bordered={false}>文本侧证据</Tag>
                </Tooltip>
                {isPlaceholder && <Tag color="orange">占位模式</Tag>}
              </div>
            </div>

            <div className="sv-subhead">
              <h3>文本检索证据</h3>
              <span>高亮行属于文判类别「{result.text_category || '—'}」</span>
            </div>
            <ResultList
              items={result.items}
              onSelect={setSelected}
              highlightCategory={result.text_category}
              emptyTitle="文本侧没有返回商品"
              emptyDescription="可以换一句更具体的描述，或检查后端索引。"
            />

            <div className="sv-result-actions">
              <Button onClick={useImageInClassification} disabled={!file}>
                单独分析这张图
              </Button>
              <Button onClick={useTextInSearch} disabled={!text.trim()}>
                单独检索这句话
              </Button>
              <Button type="text" onClick={clearAll}>
                重新开始
              </Button>
            </div>
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
