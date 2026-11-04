// 只保留类别本身与展示文案；条数、总量一律来自 /health，不在前端写快照。
export const CATEGORIES = [
  { key: '鞋', glyph: '鞋', hint: '运动鞋 / 休闲鞋 / 皮鞋' },
  { key: '水杯', glyph: '杯', hint: '保温杯 / 随行杯 / 水壶' },
  { key: '包', glyph: '包', hint: '双肩包 / 单肩包 / 旅行包' },
  { key: '男装', glyph: '男', hint: 'T 恤 / 卫衣 / 外套' },
  { key: '运动服', glyph: '运', hint: '运动套装 / 健身服' },
  { key: '女装', glyph: '女', hint: '连衣裙 / 上衣 / 裤装' },
  { key: '手机壳', glyph: '壳', hint: '保护壳 / 硅胶壳' },
  { key: '厨房用品', glyph: '厨', hint: '收纳 / 餐具 / 小家电周边' },
  { key: '家居用品', glyph: '居', hint: '日用 / 收纳 / 装饰' },
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

// 分类入口卡的代表图：Apple 风格干净白底产品图，风格统一
export const CATEGORY_PHOTOS = {
  鞋: '/samples/cat-shoe.png', // 白色运动鞋
  水杯: '/samples/cat-bottle.png', // 黑色保温杯
  包: '/samples/cat-bag.png', // 白色双肩包
  男装: '/samples/cat-shirt.png', // 浅灰男士T恤
  运动服: '/samples/cat-sportswear.png', // 浅灰运动套装
  女装: '/samples/cat-dress.png', // 米色连衣裙
  手机壳: '/samples/cat-phonecase.png', // 透明手机壳
  厨房用品: '/samples/cat-pan.png', // 灰色平底锅
  家居用品: '/samples/cat-vase.png', // 陶瓷花瓶绿植
}

export const CATEGORY_KEYS = CATEGORIES.map((item) => item.key)

export const CATEGORY_MAP = Object.fromEntries(
  CATEGORIES.map((item) => [item.key, item]),
)

// 每个类别的代表描述词：从「工作台类别卡」跳转文本检索时带上，
// 否则只有 category 没有 q，语义检索页会停在空态。每句都实测过模型判类与类目一致。
export const CATEGORY_QUERY = {
  鞋: '白色运动鞋',
  水杯: '黑色保温杯',
  包: '黑色双肩包',
  男装: '男士短袖T恤',
  运动服: '运动套装',
  女装: '女士连衣裙',
  手机壳: '手机壳',
  厨房用品: '不粘锅',
  家居用品: '木质衣架',
}

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
