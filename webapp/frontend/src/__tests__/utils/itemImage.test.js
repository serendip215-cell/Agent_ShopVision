import { resolveItemImage } from '@/utils/itemImage'

describe('resolveItemImage', () => {
  it('优先用后端给的 local_image_path 走 /item-images', () => {
    expect(
      resolveItemImage({
        item_id: 'muge_430640',
        local_image_path: 'data/processed_data_cleaning/鞋/images/muge_430640__430640.jpg',
      }),
    ).toBe('/item-images/鞋/images/muge_430640__430640.jpg')
  })

  it('兼容 Windows 反斜杠路径', () => {
    expect(
      resolveItemImage({
        local_image_path: 'data\\processed_data_cleaning\\包\\images\\a.jpg',
      }),
    ).toBe('/item-images/包/images/a.jpg')
  })

  it('兼容带前导斜杠的绝对路径', () => {
    expect(
      resolveItemImage({
        local_image_path: '/data/processed_data_cleaning/鞋/images/a.jpg',
      }),
    ).toBe('/item-images/鞋/images/a.jpg')
  })

  it('只剥离开头的数据集前缀，不碰路径中间的同名片段', () => {
    expect(
      resolveItemImage({
        local_image_path: 'data/processed_data_cleaning/鞋/images/a__data/processed_data_cleaning.jpg',
      }),
    ).toBe('/item-images/鞋/images/a__data/processed_data_cleaning.jpg')
  })

  it('缺 local_image_path 时退回 public/items 演示图', () => {
    expect(resolveItemImage({ item_id: 'muge_860' })).toBe('/items/muge_860.jpg')
  })

  it('两者都没有时返回空串', () => {
    expect(resolveItemImage(null)).toBe('')
    expect(resolveItemImage({})).toBe('')
  })
})