export async function fileFromUrl(url, name) {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error('示例图片加载失败，请检查 public/samples 目录')
  }
  const blob = await response.blob()
  const type = blob.type || 'image/jpeg'
  return new File([blob], name.endsWith('.jpg') ? name : `${name}.jpg`, { type })
}

export function validateImageFile(file) {
  if (!file) return '请先选择一张商品图'
  const typeAccepted =
    ['image/png', 'image/jpeg', 'image/webp'].includes(file.type) ||
    /\.(png|jpg|jpeg|webp)$/i.test(file.name || '')
  if (!typeAccepted) return '图片格式不支持，请上传 PNG / JPG / WEBP'
  if (file.size > 10 * 1024 * 1024) return '图片超过 10 MB，请压缩后重试'
  if (file.size === 0) return '图片内容为空，请重新选择'
  return null
}
