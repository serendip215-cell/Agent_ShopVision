import { Button } from 'antd'
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  PictureOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { CATEGORIES, CATEGORY_PHOTOS, categoryStyle } from '../../constants/catalog'
import { ConfidenceRing } from '../common/Ui'
import { formatScore } from '../../utils/format'
import { resolveItemImage } from '../../utils/itemImage'

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

function itemImagePath(item) {
  return resolveItemImage(item)
}

// 后端目前只返回类别级 topk；等 /image 补上商品级 items 后，这里会自动改用真实商品图
function buildRecommendations(result, topk) {
  const items = result?.items || []
  if (items.length) {
    return items.slice(0, 4).map((item) => ({
      key: `${item.item_id || item.item_name}-${item.similarity}`,
      label: item.item_name || '未命名商品',
      category: item.category,
      percent: Number(item.similarity) > 1 ? 100 : (Number(item.similarity) || 0) * 100,
      image: itemImagePath(item),
    }))
  }
  return topk.slice(0, 4).map((row) => ({
    key: row.category,
    label: `${row.category}·参考图`,
    category: row.category,
    percent: row.percent,
    image: CATEGORY_PHOTOS[row.category],
  }))
}

function EmptyResult() {
  return (
    <section className="sv-il-empty sv-il-glass">
      <div className="sv-il-empty-icon">
        <PictureOutlined />
      </div>
      <h2>识别结果会显示在这里</h2>
      <p>
        选一张商品图点「开始识别」，这里会给出判定的类别、置信度与备选类别，
        下方再推荐外形相似的商品。
      </p>
      <div className="sv-il-palette">
        {CATEGORIES.map((category) => {
          const style = categoryStyle(category.key)
          return (
            <span
              key={category.key}
              className="sv-il-palette-chip"
              style={{ background: style.bg, color: style.ink }}
            >
              {category.key}
            </span>
          )
        })}
      </div>
      <small className="sv-il-empty-note">模型可识别以上 9 类商品</small>
    </section>
  )
}

function RecommendationCard({ item }) {
  const style = categoryStyle(item.category)
  return (
    <article className="sv-il-reco-card">
      <div className="sv-il-reco-photo" style={{ background: style.bg }}>
        {item.image && (
          <img
            src={item.image}
            alt={item.label}
            loading="lazy"
            onError={(event) => {
              event.currentTarget.remove()
            }}
          />
        )}
      </div>
      <div className="sv-il-reco-body">
        <span className="sv-il-reco-name">{item.label}</span>
        <span className="sv-il-reco-bar">
          <i style={{ width: `${Math.max(2, item.percent)}%`, background: style.ink }} />
        </span>
        <span className="sv-il-reco-meta">
          <span>{item.category}</span>
          <span className="sv-mono">{item.percent.toFixed(1)}%</span>
        </span>
      </div>
    </article>
  )
}

export function ImageResultsSection({ result, previewUrl, onUseInMatch, onViewCategory }) {
  if (!result) return <EmptyResult />

  const topk = topkPercents(result)
  const recommendations = buildRecommendations(result, topk)

  return (
    <>
      <section className="sv-il-result-card sv-il-glass">
        <div className="sv-il-result-top">
          <div className="sv-il-result-thumb">
            {previewUrl && <img src={previewUrl} alt="本次识别的商品图" />}
          </div>
          <div className="sv-il-result-info">
            <span className="sv-il-result-kicker">
              <CheckCircleOutlined /> 图像分类
            </span>
            <strong className="sv-il-result-name">{result.category || '未判定'}</strong>
            <div className="sv-il-result-actions">
              <Button size="small" type="text" onClick={onUseInMatch}>
                用这张图做图文匹配 <ArrowRightOutlined />
              </Button>
              <Button size="small" type="text" onClick={onViewCategory}>
                看「{result.category}」类商品
              </Button>
            </div>
            <span className="sv-il-score sv-mono">原始相似度 {formatScore(result.score)}</span>
          </div>
          <ConfidenceRing value={result.confidence ?? 0} size={98} />
        </div>

        {topk.length > 0 && (
          <div className="sv-il-topbars">
            {topk.slice(0, 4).map((row, index) => (
              <div className={`sv-il-topbar ${index === 0 ? 'is-top' : ''}`} key={row.category}>
                <span className="sv-il-topbar-name">{row.category}</span>
                <span className="sv-il-topbar-track">
                  <i style={{ '--w': `${row.percent}%`, '--d': `${index * 160}ms` }} />
                </span>
                <span className="sv-il-topbar-value sv-mono">{row.percent.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="sv-il-reco sv-il-glass">
        <div className="sv-il-section-head">
          <h2>相似商品推荐</h2>
          <span>
            {result.items?.length ? '按与上传图的相近程度排序' : '当前为类别级参考图，等后端返回商品级结果后替换'}
          </span>
        </div>
        {recommendations.length > 0 ? (
          <div className="sv-il-reco-grid">
            {recommendations.map((item) => (
              <RecommendationCard key={item.key} item={item} />
            ))}
          </div>
        ) : (
          <p className="sv-il-reco-empty">这张图没有可推荐的相似商品。</p>
        )}
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
