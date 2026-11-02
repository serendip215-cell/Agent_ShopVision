import { isCanceled } from '@/utils/errors'

describe('isCanceled', () => {
  it('识别 AbortController 的中止', () => {
    expect(isCanceled(new DOMException('Aborted', 'AbortError'))).toBe(true)
  })

  it('识别 axios 的取消标记', () => {
    expect(isCanceled({ __CANCEL__: true })).toBe(true)
    expect(isCanceled({ code: 'ERR_CANCELED' })).toBe(true)
    expect(isCanceled({ name: 'CanceledError' })).toBe(true)
  })

  it('普通错误不算取消', () => {
    expect(isCanceled(new Error('boom'))).toBe(false)
    expect(isCanceled(null)).toBe(false)
    expect(isCanceled(undefined)).toBe(false)
  })
})