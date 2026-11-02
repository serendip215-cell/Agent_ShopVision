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
  鞋: { bg: '#EEEDFD', ink: '#4338CA' },
  水杯: { bg: '#E0F2FE', ink: '#0369A1' },
  包: { bg: '#FBF0DF', ink: '#B45309' },
  男装: { bg: '#EEF2F6', ink: '#475569' },
  运动服: { bg: '#E4F6EC', ink: '#15803D' },
  女装: { bg: '#FCE7F3', ink: '#BE185D' },
  手机壳: { bg: '#F3E8FF', ink: '#7E22CE' },
  厨房用品: { bg: '#FFEDD5', ink: '#C2410C' },
  家居用品: { bg: '#CCFBF1', ink: '#0F766E' },
}

export function categoryStyle(category) {
  return CATEGORY_STYLE[category] || { bg: '#F1F1F4', ink: '#4B4B53' }
}

// 分类入口卡的真实商品背景图。每张都经过双重核验：
// 1) 图内容人工看过与类别相符；2) 文件名 ID 在 items.csv 中确属该类别。
// 此前版本仅凭看图印象挑选，出现过水杯卡配高跟鞋等 4 处错位。
export const CATEGORY_PHOTOS = {
  鞋: '/samples/sample-shoe.jpg', // 白色运动鞋
  水杯: '/items/muge_860.jpg', // 维尼熊马克杯（水杯类索引内）
  包: '/samples/sample-bag.jpg', // 米白双肩包
  男装: '/items/12449731693.jpg', // 深蓝男士衬衫
  运动服: '/items/12440833831.jpg', // 白绿印花运动套装
  女装: '/items/12445240159.jpg', // 粉色蝴蝶印花连衣裙
  手机壳: '/items/B07R7WML4R.jpg', // 粉色小猫手机壳
  厨房用品: '/items/B08CGSSCB8.jpg', // 不粘平底煎锅
  家居用品: '/items/B07DWNWGNJ.jpg', // 木质衣架
}

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
  {
    key: 'dress',
    label: '碎花连衣裙',
    src: '/items/12445240159.jpg',
    text: '碎花连衣裙',
    hint: '女装类 · 适合图像分类',
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
