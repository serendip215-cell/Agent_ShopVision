export const TOTAL_PRODUCTS = 10165
export const INDEX_TOTAL = 9393

export const CATEGORIES = [
  { key: '鞋', glyph: '鞋', count: 3219, hint: '运动鞋 / 休闲鞋 / 皮鞋' },
  { key: '水杯', glyph: '杯', count: 2016, hint: '保温杯 / 随行杯 / 水壶' },
  { key: '包', glyph: '包', count: 1291, hint: '双肩包 / 单肩包 / 旅行包' },
  { key: '男装', glyph: '男', count: 999, hint: 'T 恤 / 卫衣 / 外套' },
  { key: '运动服', glyph: '运', count: 668, hint: '运动套装 / 健身服' },
  { key: '女装', glyph: '女', count: 357, hint: '连衣裙 / 上衣 / 裤装' },
  { key: '手机壳', glyph: '壳', count: 300, hint: '保护壳 / 硅胶壳' },
  { key: '厨房用品', glyph: '厨', count: 279, hint: '收纳 / 餐具 / 小家电周边' },
  { key: '家居用品', glyph: '居', count: 264, hint: '日用 / 收纳 / 装饰' },
]

// 9 类各自的识别色：柔和底色 + 对比墨色，全部与主色板同灰度
export const CATEGORY_STYLE = {
  鞋: { bg: '#DDEFEF', ink: '#2F6F77' },
  水杯: { bg: '#E3EDF5', ink: '#3D6F9E' },
  包: { bg: '#F7D9C4', ink: '#A96A43' },
  男装: { bg: '#E6EAF2', ink: '#4E5B7C' },
  运动服: { bg: '#DFF3E4', ink: '#2F7D58' },
  女装: { bg: '#F8E3E8', ink: '#B4586F' },
  手机壳: { bg: '#EBE7F4', ink: '#6E5FA3' },
  厨房用品: { bg: '#EEEFDD', ink: '#74753B' },
  家居用品: { bg: '#F0E8DE', ink: '#8F6B4A' },
}

export function categoryStyle(category) {
  return CATEGORY_STYLE[category] || { bg: '#F1F3F5', ink: '#4E5A60' }
}

// Hero 拼贴用的真实商品图（public/items 下已确认存在）
export const HERO_PHOTOS = [
  { src: '/samples/sample-shoe.jpg', category: '鞋', caption: '白色运动鞋' },
  { src: '/items/muge_1104.jpg', category: '水杯', caption: '保温杯' },
  { src: '/samples/sample-bag.jpg', category: '包', caption: '双肩包' },
  { src: '/items/B075DQBBJZ.jpg', category: '女装', caption: '连衣裙' },
  { src: '/items/muge_860.jpg', category: '厨房用品', caption: '厨房好物' },
  { src: '/items/12303593760.jpg', category: '男装', caption: '男士外套' },
]

export const CATEGORY_KEYS = CATEGORIES.map((item) => item.key)

export const CATEGORY_MAP = Object.fromEntries(
  CATEGORIES.map((item) => [item.key, item]),
)

export const SAMPLE_QUERIES = [
  '白色运动鞋',
  '黑色双肩包',
  '黑色保温杯',
  '女士连衣裙',
  '手机壳',
  '厨房收纳盒',
]

export const DEMO_IMAGES = [
  {
    key: 'shoe',
    label: '白色运动鞋',
    src: '/samples/sample-shoe.jpg',
    text: '白色运动鞋',
    hint: '鞋类 · 适合图像分类',
  },
  {
    key: 'bag',
    label: '双肩包',
    src: '/samples/sample-bag.jpg',
    text: '双肩包',
    hint: '包类 · 适合图文匹配',
  },
  {
    key: 'bottle',
    label: '保温杯',
    src: '/samples/sample-bottle.jpg',
    text: '保温杯',
    hint: '水杯类 · 适合文本检索',
  },
]

export const DEMO_PAIRS = [
  {
    key: 'match',
    label: '一致示例',
    description: '白色运动鞋图 + 「白色运动鞋」',
    image: DEMO_IMAGES[0],
    text: '白色运动鞋',
  },
  {
    key: 'mismatch',
    label: '不一致示例',
    description: '白色运动鞋图 + 「双肩包」',
    image: DEMO_IMAGES[0],
    text: '双肩包',
  },
]

export const MODE_META = {
  image: { label: '图像分类', tone: 'teal' },
  text: { label: '文本检索', tone: 'blue' },
  match: { label: '图文匹配', tone: 'warm' },
}
