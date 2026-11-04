import { useState } from 'react'
import { Button, Tooltip } from 'antd'
import {
  CameraOutlined,
  FileTextOutlined,
  PictureOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SwapOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { DEMO_IMAGES } from '../../constants/catalog'
import { useApp } from '../../context/AppContext'
import { validateImageFile } from '../../utils/samples'

export function ImageUploadSection({
  file,
  previewUrl,
  loading,
  progress,
  validation,
  onSelect,
  onLoadSample,
  onAnalyze,
  onBatchClick,
  onBatchFiles,
  batchInputRef,
}) {
  const [dragging, setDragging] = useState(false)

  function handleDragOver(e) {
    e.preventDefault()
    setDragging(true)
  }

  function handleDragLeave(e) {
    // 指针移到子元素上也会触发 dragleave，这里只在真正离开拖拽框时取消高亮
    if (e.currentTarget.contains(e.relatedTarget)) return
    setDragging(false)
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    const droppedFile = e.dataTransfer.files?.[0]
    if (droppedFile) onSelect(droppedFile)
  }

  return (
    <section className="sv-il-upload sv-il-glass">
      <div className="sv-il-upload-head">
        <h2>工作台</h2>
        <span className="sv-il-upload-limit">PNG / JPG / WEBP · ≤ 10MB</span>
      </div>

      {loading ? (
        <div className="sv-il-loading" role="status">
          <span className="sv-il-ring" aria-hidden="true" />
          <strong>
            {progress && progress.total > 1
              ? `AI 正在识别第 ${Math.min(progress.done + 1, progress.total)} / ${progress.total} 张...`
              : 'AI 正在解析图片特征...'}
          </strong>
          <span className="sv-il-loading-note">模型正在提取图像向量，对比商品类别库</span>
        </div>
      ) : (
        <>
          <label
            className={`sv-il-dropzone ${previewUrl ? 'has-file' : ''} ${dragging ? 'is-drag' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
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
            {DEMO_IMAGES.slice(0, 4).map((sample) => (
              <Tooltip key={sample.key} title={`用「${sample.label}」示例图试试`}>
                <button
                  type="button"
                  className="sv-il-sample"
                  aria-label={`使用示例图 ${sample.label}`}
                  onClick={() => onLoadSample(sample)}
                >
                  <img src={sample.src} alt={sample.label} loading="lazy" />
                </button>
              </Tooltip>
            ))}
            <Tooltip title="批量识别多张商品图">
              <button
                type="button"
                className="sv-il-sample is-add"
                aria-label="批量识别"
                onClick={onBatchClick}
              >
                <PlusOutlined />
              </button>
            </Tooltip>
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
                    .filter((f) => !validateImageFile(f))
                  if (validated.length) onBatchFiles(validated)
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
              <span className="sv-il-upload-hint">
                {file ? `已选择：${file.name}` : '拖入图片或点一张示例图即可开始'}
              </span>
            )}
            <Button type="primary" size="large" onClick={onAnalyze}>
              开始识别
            </Button>
          </div>
        </>
      )}
    </section>
  )
}

export function ImageUploadSectionWithHeader({ eyebrow, title, description }) {
  const navigate = useNavigate()
  const { categories } = useApp()
  return (
    <header className="sv-il-head">
      <div className="sv-il-head-lines" aria-hidden="true">
        <svg viewBox="0 0 800 200" preserveAspectRatio="none">
          <path
            d="M 0 100 C 200 60, 400 120, 800 80"
            fill="none"
            stroke="#5fa8b0"
            strokeOpacity="0.15"
            strokeWidth="1.5"
          />
          <path
            d="M 0 130 C 250 90, 500 150, 800 110"
            fill="none"
            stroke="#5fa8b0"
            strokeOpacity="0.1"
            strokeWidth="1"
          />
          <circle cx="300" cy="95" r="3" fill="#5fa8b0" fillOpacity="0.25" />
          <circle cx="500" cy="120" r="2.5" fill="#5fa8b0" fillOpacity="0.2" />
          <circle cx="650" cy="90" r="2" fill="#5fa8b0" fillOpacity="0.15" />
        </svg>
      </div>
      <div className="sv-il-head-copy">
        <span className="sv-eyebrow">IMAGE CLASSIFICATION</span>
        <h1>Recognize Product Category</h1>
        <div className="sv-il-head-modes">
          <button
            type="button"
            className="sv-il-mode-chip"
            onClick={() => navigate('/image')}
          >
            <PictureOutlined />
            <span>Image</span>
          </button>
          <button
            type="button"
            className="sv-il-mode-chip"
            onClick={() => navigate('/text')}
          >
            <FileTextOutlined />
            <span>Text</span>
          </button>
          <button
            type="button"
            className="sv-il-mode-chip"
            onClick={() => navigate('/match')}
          >
            <SwapOutlined />
            <span>Similar</span>
          </button>
        </div>
      </div>
      <Tooltip
        title={`模型一共识别 ${categories.length} 类商品，会给出最匹配结果 + 备选猜测`}
      >
        <button type="button" className="sv-il-help" aria-label="使用帮助">
          <QuestionCircleOutlined />
        </button>
      </Tooltip>
    </header>
  )
}
