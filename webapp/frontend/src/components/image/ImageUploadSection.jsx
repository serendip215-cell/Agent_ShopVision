import { Button, Tooltip } from 'antd'
import {
  CameraOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { DEMO_IMAGES } from '../../constants/catalog'
import { validateImageFile } from '../../utils/samples'

export function ImageUploadSection({
  file,
  previewUrl,
  loading,
  batch,
  validation,
  onSelect,
  onClear,
  onLoadSample,
  onBatchClick,
  batchInputRef,
}) {
  function handleDragOver(e) {
    e.preventDefault()
  }

  function handleDrop(e) {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files?.[0]
    if (droppedFile) onSelect(droppedFile)
  }

  if (loading) {
    return (
      <section className="sv-il-upload sv-il-glass">
        <div className="sv-il-loading" role="status">
          <span className="sv-il-ring" aria-hidden="true" />
          <strong>
            {batch ? `AI 正在识别第 ${batch.index} / ${batch.total} 张...` : 'AI 正在解析图片特征...'}
          </strong>
          <span className="sv-il-loading-note">模型正在提取图像向量，对比商品类别库</span>
        </div>
      </section>
    )
  }

  return (
    <section className="sv-il-upload sv-il-glass">
      <div className="sv-il-upload-head">
        <h2>上传商品图</h2>
        <span className="sv-il-upload-limit">支持 PNG / JPG / WEBP · 单张 ≤ 10MB</span>
      </div>

      <label
        className={`sv-il-dropzone ${previewUrl ? 'has-file' : ''}`}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          disabled={false}
          onChange={(event) => {
            onSelect(event.target.files?.[0])
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
            onClick={() => onLoadSample(sample)}
          >
            <img src={sample.src} alt={sample.label} loading="lazy" />
            <span>{sample.label}</span>
          </button>
        ))}
        <button type="button" className="sv-il-sample is-more" onClick={onBatchClick}>
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
            const files = event.target.files
            event.target.value = ''
            if (files?.length) {
              const validated = [...files]
                .slice(0, 12)
                .filter((f) => {
                  const err = validateImageFile(f)
                  if (err) console.warn(`跳过「${f.name}」：${err}`)
                  return !err
                })
              if (validated.length) onBatchClick(validated)
            }
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
          onClick={() => file && onSelect(file)}
          disabled={!file}
        >
          开始识别
        </Button>
      </div>
    </section>
  )
}

export function ImageUploadSectionWithHeader({ eyebrow, title, description }) {
  return (
    <header className="sv-il-head">
      <div className="sv-il-head-copy">
        <span className="sv-eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <Tooltip title="模型一共识别 9 类商品，会给出最匹配结果 + 备选猜测">
        <button type="button" className="sv-il-help" aria-label="使用帮助">
          <QuestionCircleOutlined />
        </button>
      </Tooltip>
    </header>
  )
}
