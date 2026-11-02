import { AppError } from '@/api/client'

describe('AppError', () => {
  it('携带业务码、文案与 HTTP 状态', () => {
    const error = new AppError(40004, '文件过大', 400)
    expect(error.code).toBe(40004)
    expect(error.status).toBe(400)
    expect(error.message).toBe('文件过大')
    expect(error.name).toBe('AppError')
  })

  it('支持字符串错误码（TIMEOUT / NETWORK）', () => {
    expect(new AppError('TIMEOUT', '请求超时').code).toBe('TIMEOUT')
    expect(new AppError('NETWORK', '连不上后端服务').message).toContain('后端')
  })
})