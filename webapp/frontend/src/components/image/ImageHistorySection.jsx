import { Button } from 'antd'
import { FolderOpenOutlined, ReloadOutlined } from '@ant-design/icons'

export function ImageHistorySection({
  history,
  currentResult,
  isPlaceholder,
  onReviewHistory,
  onClearAll,
  onBatchClick,
}) {
  return (
    <section className="sv-il-more sv-il-glass">
      <div className="sv-il-section-head">
        <h2>继续测试其他商品图</h2>
        <span>{history.length > 0 ? `已识别 ${history.length} 次` : '还没有识别记录'}</span>
      </div>
      <div className="sv-il-more-actions">
        <Button icon={<ReloadOutlined />} onClick={onClearAll}>
          重新上传图片
        </Button>
        <Button icon={<FolderOpenOutlined />} onClick={onBatchClick}>
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
              className={`sv-il-history-card ${currentResult === entry.result ? 'is-active' : ''}`}
              onClick={() => onReviewHistory(entry)}
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
  )
}
