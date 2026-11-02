import { Button } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

export function ImageHistorySection({
  history,
  currentResult,
  isPlaceholder,
  onReviewHistory,
  onClearAll,
}) {
  return (
    <section className="sv-il-history-block">
      <div className="sv-il-history-head">
        <div className="sv-il-history-title">
          <h2>本次会话识别历史</h2>
          <span>
            {history.length > 0
              ? `${history.length} 条记录 · 刷新页面后清空`
              : '还没有识别记录'}
          </span>
        </div>
        <div className="sv-il-history-tools">
          {isPlaceholder && (
            <span className="sv-il-placeholder-note">占位编码器：结果无参考意义</span>
          )}
          {history.length > 0 && (
            <Button size="small" type="text" icon={<ReloadOutlined />} onClick={onClearAll}>
              重新上传图片
            </Button>
          )}
        </div>
      </div>

      {history.length > 0 && (
        <div className="sv-il-history">
          {history.map((entry) => {
            const confidence = entry.confidence || 0
            return (
              <button
                type="button"
                key={entry.id}
                className={`sv-il-history-card ${currentResult === entry.result ? 'is-active' : ''}`}
                onClick={() => onReviewHistory(entry)}
              >
                <img src={entry.thumb} alt={entry.fileName} />
                <span className="sv-il-history-cat">{entry.category || '未判定'}</span>
                <span className="sv-il-history-meter">
                  <i style={{ width: `${Math.max(3, confidence * 100)}%` }} />
                </span>
                <span className="sv-il-history-pct sv-mono">
                  {(confidence * 100).toFixed(1)}%
                </span>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}
