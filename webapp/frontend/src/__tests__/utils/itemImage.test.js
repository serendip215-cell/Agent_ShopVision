import { resolveItemImage } from '@/utils/itemImage'

describe('resolveItemImage', () => {
  it('有原始图时优先走 /item-originals，而不是清洗图', () => {
    expect(
      resolveItemImage({
        item_id: '12452469352',
        local_image_path: 'data/processed_data_cleaning/包/images/12452469352.jpg',
        original_image_path: 'data/raw_data/Suning_data/images/12452469352.jpg',
      }),
    ).toBe('/item-originals/Suning_data/images/12452469352.jpg')
  })

  it('原始图路径前缀不认识时退回 local_image_path', () => {
    expect(
      resolveItemImage({
        local_image_path: 'data/processed_data_cleaning/鞋/images/a.jpg',
        original_image_path: 'C:/elsewhere/a.jpg',
      }),
    ).toBe('/item-images/鞋/images/a.jpg')
  })

  it('兼容原始图的 Windows 反斜杠路径', () => {
    expect(
      resolveItemImage({
        original_image_path: 'data\\raw_data\\MUGE_data\\images\\916.jpg',
      }),
    ).toBe('/item-originals/MUGE_data/images/916.jpg')
  })

  it('没有原始图时用后端给的 local_image_path 走 /item-images', () => {
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

  it('上传原图走 /item-uploads，不混进 cleaning 目录', () => {
    expect(
      resolveItemImage({
        item_id: 'upload_82ab83715acc',
        local_image_path: 'data/uploaded_data/鞋/images/upload_82ab83715acc.jpg',
      }),
    ).toBe('/item-uploads/鞋/images/upload_82ab83715acc.jpg')
  })

  it('旧上传数据仍兼容 processed_data_cleaning 路径', () => {
    expect(
      resolveItemImage({
        item_id: 'upload_old',
        local_image_path: 'data/processed_data_cleaning/鞋/images/upload_old.jpg',
      }),
    ).toBe('/item-images/鞋/images/upload_old.jpg')
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