import { Button, Descriptions, Divider, Drawer, Skeleton, Tag } from 'antd'
import {
  ArrowRightOutlined,
  InboxOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { CategoryBadge, CopyButton, EmptyState, SimilarityBar } from '../common/Ui'
import { formatPercent } from '../../utils/format'

export function ItemRow({ item, rank, onSelect, highlight = false }) {
  return (
    <button
      type="button"
      className={`sv-item-row ${highlight ? 'is-highlight' : ''}`}
      onClick={() => onSelect?.(item)}
    >
      <span className="sv-item-rank sv-mono">{String(rank).padStart(2, '0')}</span>
      <span className="sv-item-main">
        <span className="sv-item-title">{item.item_name || '未命名商品'}</span>
        <span className="sv-item-tags">
          <CategoryBadge category={item.category} small />
          {(item.type || item.product_type) && <span>{item.type || item.product_type}</span>}
          {item.brand && <span>品牌：{item.brand}</span>}
          {item.color && <span>颜色：{item.color}</span>}
          {item.material && <span>材质：{item.material}</span>}
        </span>
        <span className="sv-item-id sv-mono">{item.item_id}</span>
      </span>
      <span className="sv-item-score">
        <SimilarityBar value={item.similarity} compact />
        <span className="sv-item-percent">{formatPercent(item.similarity)}</span>
      </span>
      <ArrowRightOutlined className="sv-item-arrow" />
    </button>
  )
}

export function ResultList({ items, loading, onSelect, highlightCategory, emptyTitle, emptyDescription }) {
  if (loading) {
    return (
      <div className="sv-result-list">
        {[0, 1, 2].map((key) => (
          <div className="sv-item-skeleton" key={key}>
            <Skeleton active paragraph={{ rows: 1 }} title={{ width: '40%' }} />
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
    <div className="sv-result-list">
      {items.map((item, index) => (
        <ItemRow
          key={`${item.item_id || 'item'}-${index}`}
          item={item}
          rank={index + 1}
          onSelect={onSelect}
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
