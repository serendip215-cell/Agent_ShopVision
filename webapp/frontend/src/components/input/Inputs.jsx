import { Button, Input, Select, Slider, Upload } from 'antd'
import {
  DeleteOutlined,
  InboxOutlined,
  SearchOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import { CATEGORIES } from '../../constants/catalog'
import { formatBytes } from '../../utils/format'

export function UploadDropzone({
  file,
  previewUrl,
  onSelect,
  onClear,
  error,
  compact = false,
  disabled = false,
}) {
  function handleChange(info) {
    const raw = info.file?.originFileObj || info.file
    if (raw) onSelect?.(raw)
  }

  return (
    <div className={`sv-upload ${compact ? 'is-compact' : ''} ${error ? 'has-error' : ''}`}>
      {previewUrl ? (
        <div className="sv-preview">
          <img src={previewUrl} alt="待分析商品图预览" />
          <div className="sv-preview-overlay">
            <span className="sv-preview-name" title={file?.name}>
              {file?.name}
            </span>
            <div className="sv-preview-actions">
              {!disabled && (
                <Upload
                  accept="image/png,image/jpeg,image/webp"
                  showUploadList={false}
                  beforeUpload={() => false}
                  onChange={handleChange}
                >
                  <Button size="small" icon={<SwapOutlined />}>
                    更换
                  </Button>
                </Upload>
              )}
              <Button size="small" danger icon={<DeleteOutlined />} onClick={onClear}>
                移除
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <Upload.Dragger
          className="sv-dropzone"
          accept="image/png,image/jpeg,image/webp"
          showUploadList={false}
          beforeUpload={() => false}
          onChange={handleChange}
          disabled={disabled}
        >
          <div className="sv-upload-icon">
            <InboxOutlined />
          </div>
          <p className="sv-upload-title">拖入一张商品图，或点击选择</p>
          <p className="sv-upload-hint">PNG / JPG / WEBP · 不超过 10 MB</p>
        </Upload.Dragger>
      )}

      {file && (
        <div className="sv-file-meta">
          <span className="sv-mono" title={file.name}>
            {file.name}
          </span>
          <span>{formatBytes(file.size)}</span>
        </div>
      )}

      {error && <div className="sv-inline-error">{error}</div>}
    </div>
  )
}

export function QueryInput({
  value,
  onChange,
  onSubmit,
  loading,
  label = '中文查询',
  placeholder = '例如：白色运动鞋、黑色双肩包、保温杯',
  actionLabel = '搜索商品',
  showHint = true,
}) {
  return (
    <div className="sv-query-input">
      <div className="sv-field-head">
        <label htmlFor="sv-query">{label}</label>
        <span>1–200 字</span>
      </div>
      <Input.TextArea
        id="sv-query"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoSize={{ minRows: 2, maxRows: 4 }}
        maxLength={200}
        showCount
        placeholder={placeholder}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            onSubmit?.()
          }
        }}
      />
      {showHint && <div className="sv-query-hint">Enter 提交 · Shift + Enter 换行</div>}
      <div className="sv-query-actions">
        <Button
          type="primary"
          icon={<SearchOutlined />}
          loading={loading}
          onClick={onSubmit}
        >
          {actionLabel}
        </Button>
      </div>
    </div>
  )
}

export function CategorySelect({ value, onChange, categories = CATEGORIES.map((item) => item.key) }) {
  return (
    <div className="sv-field">
      <div className="sv-field-head">
        <label>类别筛选</label>
        <span>可留空</span>
      </div>
      <Select
        value={value || ''}
        onChange={onChange}
        style={{ width: '100%' }}
        options={[{ value: '', label: '全部类别' }, ...categories.map((key) => ({ value: key, label: key }))]}
      />
    </div>
  )
}

export function TopKSlider({ value, onChange, max = 50 }) {
  return (
    <div className="sv-field">
      <div className="sv-field-head">
        <label>返回条数</label>
        <span className="sv-mono">{value} 条</span>
      </div>
      <Slider
        min={1}
        max={max}
        value={value}
        onChange={onChange}
        marks={{ 1: '1', 5: '5', 10: '10', 50: '50' }}
        tooltip={{ formatter: (next) => `${next} 条` }}
      />
    </div>
  )
}

export function SampleChips({ items, active, onPick, label = '试试这些查询' }) {
  return (
    <div className="sv-samples">
      <span className="sv-samples-label">{label}</span>
      <div className="sv-chip-row">
        {items.map((item) => (
          <button
            type="button"
            key={item}
            className={`sv-chip ${active === item ? 'is-active' : ''}`}
            onClick={() => onPick(item)}
          >
            {item}
          </button>
        ))}
      </div>
    </div>
  )
}

export function DemoImageStrip({ images, onPick, loadingKey }) {
  return (
    <div className="sv-demo-strip">
      <span className="sv-samples-label">没有图？用示例商品图</span>
      <div className="sv-demo-grid">
        {images.map((image) => (
          <button
            type="button"
            key={image.key}
            className="sv-demo-card"
            onClick={() => onPick?.(image)}
            disabled={Boolean(loadingKey)}
          >
            <img src={image.src} alt={image.label} />
            <div>
              <strong>{image.label}</strong>
              <span>{loadingKey === image.key ? '载入中…' : image.hint}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
