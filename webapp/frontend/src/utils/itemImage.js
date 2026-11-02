const DATASET_PREFIX = 'data/processed_data_cleaning/'

/**
 * 商品缩略图地址。后端结果带 local_image_path（数据集真实文件名），
 * 统一走 /item-images；只有老数据缺字段时才退回 public/items 的演示图。
 */
export function resolveItemImage(item) {
  const path = String(item?.local_image_path || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
  if (path) {
    const relative = path.startsWith(DATASET_PREFIX) ? path.slice(DATASET_PREFIX.length) : path
    return `/item-images/${relative}`
  }
  return item?.item_id ? `/items/${item.item_id}.jpg` : ''
}