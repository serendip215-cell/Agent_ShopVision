import { categoryStyle } from '../../constants/catalog'
import { formatPercent } from '../../utils/format'
import { resolveItemImage } from '../../utils/itemImage'

/**
 * 对话页的紧凑结果条：一排小图，横向滚动，点击开详情抽屉。
 *
 * 用 108px 的卡片（图约 96px）而不是 72px 的缩略点：录屏和答辩投影下仍能看清商品，
 * 同时 5 条能在一屏里并排放下。
 */
export function ItemThumbRow({ items = [], onSelect, max = 5 }) {
  if (!items.length) return null
  const shown = items.slice(0, max)

  return (
    <div className="sv-thumb-row">
      {shown.map((item, index) => {
        const style = categoryStyle(item.category)
        return (
          <button
            type="button"
            key={`${item.item_id || 'item'}-${index}`}
            className="sv-thumb"
            title={item.item_name || '商品'}
            onClick={() => onSelect?.(item)}
          >
            <span
              className="sv-thumb-img"
              style={{ background: style.bg }}
              data-fallback={item.category?.slice(0, 1) || '?'}
            >
              <img
                src={resolveItemImage(item)}
                alt={item.item_name || '商品图'}
                loading="lazy"
                onError={(event) => {
                  event.currentTarget.closest('.sv-thumb-img').classList.add('is-broken')
                  event.currentTarget.remove()
                }}
              />
            </span>
            <span className="sv-thumb-title">{item.item_name || '未命名商品'}</span>
            <span className="sv-thumb-meta">
              <span className="sv-thumb-cat" style={{ color: style.ink }}>
                {item.category || '未分类'}
              </span>
              <span className="sv-mono">{formatPercent(item.similarity)}</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
