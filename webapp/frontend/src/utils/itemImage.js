// 商品图统一地址：优先用后端返回的本地图片路径，缺失时退回 public/items 演示图
export function resolveItemImage(item) {
  if (!item) return ''
  if (item.local_image_path) {
    return `/item-images/${item.local_image_path.replace(/^data\/processed_data_cleaning\//, '')}`
  }
  return item.item_id ? `/items/${item.item_id}.jpg` : ''
}
