import { Button } from 'antd'
import { ArrowRightOutlined, CheckCircleOutlined, WarningOutlined } from '@ant-design/icons'
import useCountUp from '../../utils/useCountUp'
import { formatScore } from '../../utils/format'
import { CATEGORIES } from '../../constants/catalog'

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
  const topk = topkPercents(result)
  const others = topk.filter((row) => row.category !== result.category).slice(0, 2)
  const tail = others.length ? `，同时觉得它有一点「${others.map((row) => row.category).join('」「')}」的特征` : ''
  return `AI 第一眼认为这是「${result.category}」（${percent}% 把握）${tail}。`
}

export function ImageResultsSection({ result, previewUrl, onUseInMatch, onViewCategory }) {
  const confidenceValue = useCountUp(result?.confidence ?? null)
  const topk = topkPercents(result)
  const plain = plainWords(result)

  if (!result) return null

  return (
    <>
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
            <div className="sv-il-score sv-mono">原始相似度分数 {formatScore(result.score)}</div>
            <div className="sv-il-result-actions">
              <Button size="small" type="text" onClick={onUseInMatch}>
                用这张图做图文匹配 <ArrowRightOutlined />
              </Button>
              <Button size="small" type="text" onClick={onViewCategory}>
                看看「{result.category}」类商品
              </Button>
            </div>
          </div>
        </div>
      </section>

      {topk.length > 0 && (
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
            百分比为前三类相对可能性的直观展示；预测类别取模型在全部 {CATEGORIES.length}{' '}
            类中的最高响应。
          </p>
        </section>
      )}

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
    </>
  )
}

export function ImageErrorNotice({ error, onRetry, onDismiss }) {
  function friendlyError() {
    if (!error) return null
    if (error.code === 40004) return '图片超出 10MB 上限，请更换一张更小的图片'
    if (error.code === 40001 || error.code === 40002) return '文件格式不支持，请上传 PNG / JPG / WEBP 图片'
    return '识别没有成功，请重试或换一张商品图'
  }

  return (
    <div className="sv-il-error" role="alert">
      <WarningOutlined />
      <div className="sv-il-error-copy">
        <strong>{friendlyError()}</strong>
        <span>{error?.message || ''}</span>
      </div>
      <div className="sv-il-error-actions">
        <Button size="small" onClick={onRetry}>
          重试
        </Button>
        <Button size="small" type="text" onClick={onDismiss}>
          知道了
        </Button>
      </div>
    </div>
  )
}
