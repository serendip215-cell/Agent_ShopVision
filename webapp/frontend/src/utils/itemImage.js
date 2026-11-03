const RAW_PREFIX = 'data/raw_data/'
const DATASET_PREFIX = 'data/processed_data_cleaning/'

function normalize(path) {
  return String(path || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
}

/**
 * 商品缩略图地址。静态索引的 local_image_path 指向清洗/增强后的图，
 * 后端另有 original_image_path（原始商品图）时优先用它走 /item-originals；
 * 上传条目没有原始副本，继续走 /item-images。老数据缺字段时退回 public/items。
 */
export function resolveItemImage(item) {
  const original = normalize(item?.original_image_path)
  if (original.startsWith(RAW_PREFIX)) {
    return `/item-originals/${original.slice(RAW_PREFIX.length)}`
  }
  const path = normalize(item?.local_image_path)
  if (path) {
    const relative = path.startsWith(DATASET_PREFIX) ? path.slice(DATASET_PREFIX.length) : path
    return `/item-images/${relative}`
  }
  return item?.item_id ? `/items/${item.item_id}.jpg` : ''
}