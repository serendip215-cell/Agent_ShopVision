import { Button, Descriptions, Divider, Drawer, Skeleton, Tag } from 'antd'
import {
  InboxOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { CategoryBadge, CopyButton, EmptyState, SimilarityBar } from '../common/Ui'
import { categoryStyle } from '../../constants/catalog'
import { formatPercent } from '../../utils/format'
import { resolveItemImage } from '../../utils/itemImage'

function ItemPhoto({ item, isTop = false }) {
  const style = categoryStyle(item.category)
  const imagePath = resolveItemImage(item)

  return (
    <span
      className="sv-photo"
      style={{ background: style.bg }}
      data-fallback={item.category?.slice(0, 1) || '?'}
    >
      <img
        src={imagePath}
        alt={item.item_name || '商品图'}
        loading="lazy"
        onError={(event) => {
          event.currentTarget.closest('.sv-photo').classList.add('is-broken')
          event.currentTarget.remove()
        }}
      />
      {isTop && <span className="sv-item-best">最佳匹配</span>}
      <span className="sv-photo-rank" style={{ background: style.ink }} />
    </span>
  )
}

export function ItemRow({ item, rank, onSelect, highlight = false, isTop = false }) {
  const style = categoryStyle(item.category)
  return (
    <button
      type="button"
      className={`sv-item-card ${highlight ? 'is-highlight' : ''}`}
      onClick={() => onSelect?.(item)}
    >
      <ItemPhoto item={item} isTop={isTop} />
      <span className="sv-item-card-body">
        <span className="sv-item-card-top">
          <span className="sv-item-rank sv-mono" style={{ color: style.ink }}>
            {String(rank).padStart(2, '0')}
          </span>
          <span className="sv-item-percent sv-mono">{formatPercent(item.similarity)}</span>
        </span>
        <span className="sv-item-title">{item.item_name || '未命名商品'}</span>
        <span className="sv-item-tags">
          {(item.type || item.product_type) && <span>{item.type || item.product_type}</span>}
          {item.brand && <span>{item.brand}</span>}
          {item.color && <span>{item.color}</span>}
        </span>
        <span className="sv-item-card-foot">
          <span
            className="sv-item-cat"
            style={{ background: style.bg, color: style.ink }}
          >
            {item.category || '未分类'}
          </span>
          <SimilarityBar value={item.similarity} compact />
        </span>
      </span>
    </button>
  )
}

export function ResultList({ items, loading, onSelect, highlightCategory, emptyTitle, emptyDescription }) {
  if (loading) {
    return (
      <div className="sv-item-grid">
        {[0, 1, 2, 3].map((key) => (
          <div className="sv-item-skeleton" key={key}>
            <Skeleton.Image active style={{ width: '100%', height: 150 }} />
            <Skeleton active paragraph={{ rows: 2 }} title={{ width: '60%' }} />
          </div>
        ))}
      </div>
    )
  }

  if (!items?.length) {
    return (
      <EmptyState
        icon={<InboxOutlined />}
        title={emptyTitle || '没有检索到商品'}
        description={emptyDescription || '换一个描述方式，或把类别筛选改成「全部类别」再试一次。'}
      />
    )
  }

  return (
    <div className="sv-item-grid">
      {items.map((item, index) => (
        <ItemRow
          key={`${item.item_id || 'item'}-${index}`}
          item={item}
          rank={index + 1}
          onSelect={onSelect}
          isTop={index === 0}
          highlight={highlightCategory ? item.category === highlightCategory : false}
        />
      ))}
    </div>
  )
}

export function DetailDrawer({ item, open, onClose, onSearch }) {
  if (!item) {
    return <Drawer open={open} onClose={onClose} width={520} />
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={520}
      title={
        <div className="sv-drawer-title">
          <CategoryBadge category={item.category} />
          <span>{item.item_name || '商品详情'}</span>
        </div>
      }
    >
      <div className="sv-drawer-body">
        <div className="sv-drawer-photo">
          <ItemPhoto item={item} />
        </div>
        <Descriptions column={1} size="small" items={[
          { key: 'id', label: '商品 ID', children: <span className="sv-mono">{item.item_id}</span> },
          { key: 'type', label: '细分类', children: item.type || item.product_type || '—' },
          { key: 'brand', label: '品牌', children: item.brand || '—' },
          { key: 'color', label: '颜色', children: item.color || '—' },
          { key: 'material', label: '材质', children: item.material || '—' },
        ]} />

        <Divider />

        <div className="sv-drawer-section">
          <h3>商品描述</h3>
          <p>{item.description || '这条商品没有可展示的描述字段。'}</p>
        </div>

        <div className="sv-drawer-section">
          <h3>检索相似度</h3>
          <SimilarityBar value={item.similarity} label="与当前查询的相似度" showScore />
        </div>

        <div className="sv-drawer-actions">
          {onSearch && (
            <Button icon={<SearchOutlined />} onClick={() => onSearch(item.item_name)}>
              以商品名再检索
            </Button>
          )}
          <CopyButton text={item.item_id || ''} label="复制商品 ID" type="default" />
          <Tag bordered={false} color="cyan">
            {item.category}
          </Tag>
        </div>
      </div>
    </Drawer>
  )
}
