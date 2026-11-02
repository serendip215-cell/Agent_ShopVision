import { validateImageFile } from '@/utils/samples'

const bytes = new Uint8Array(4)

describe('validateImageFile', () => {
  it('接受 PNG / JPG / WEBP', () => {
    for (const [name, type] of [
      ['test.png', 'image/png'],
      ['test.jpg', 'image/jpeg'],
      ['test.webp', 'image/webp'],
    ]) {
      expect(validateImageFile(new File([bytes], name, { type }))).toBeNull()
    }
  })

  it('拒绝非图片类型', () => {
    const error = validateImageFile(new File([bytes], 'test.txt', { type: 'text/plain' }))
    expect(error).toMatch(/格式不支持/)
  })

  it('拒绝空文件', () => {
    const error = validateImageFile(new File([], 'empty.jpg', { type: 'image/jpeg' }))
    expect(error).toMatch(/内容为空/)
  })

  it('拒绝超过 10 MB 的文件', () => {
    const file = new File([new ArrayBuffer(10 * 1024 * 1024 + 1)], 'big.jpg', {
      type: 'image/jpeg',
    })
    expect(validateImageFile(file)).toMatch(/10 MB/)
  })

  it('没选文件时给出提示', () => {
    expect(validateImageFile(null)).toMatch(/请先选择/)
  })
})