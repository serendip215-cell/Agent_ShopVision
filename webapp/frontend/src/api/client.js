import axios from 'axios'

const HTTP_FALLBACK = {
  400: '参数错误，请检查输入后重试',
  404: '资源不存在',
  500: '服务器内部错误，请稍后重试',
}

export class AppError extends Error {
  constructor(code, message, status = null) {
    super(message)
    this.name = 'AppError'
    this.code = code
    this.status = status
  }
}

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

client.interceptors.response.use(
  (response) => {
    const body = response.data
    if (!body || typeof body.code !== 'number') {
      throw new AppError(
        'INVALID_RESPONSE',
        '后端返回格式异常，请确认服务版本是否匹配',
        response.status,
      )
    }
    if (body.code !== 0) {
      throw new AppError(body.code, body.msg || '请求失败', response.status)
    }
    return body.result
  },
  (error) => {
    if (axios.isCancel(error) || error.code === 'ERR_CANCELED') {
      throw error
    }

    if (error.response) {
      const body = error.response.data
      if (body && typeof body.code === 'number') {
        throw new AppError(
          body.code,
          body.msg || HTTP_FALLBACK[String(body.code).slice(0, 3)] || '请求失败',
          error.response.status,
        )
      }
      throw new AppError(
        String(error.response.status),
        HTTP_FALLBACK[error.response.status] || `请求失败（HTTP ${error.response.status}）`,
        error.response.status,
      )
    }

    if (error.code === 'ECONNABORTED') {
      throw new AppError('TIMEOUT', '请求超时，图片可能过大或模型繁忙，请重试')
    }

    throw new AppError(
      'NETWORK',
      '连不上后端服务，请确认 uvicorn 已在 8000 端口启动',
    )
  },
)

export function getHealth(signal) {
  return client.get('/health', { signal })
}

export function classifyImage(file, signal) {
  const form = new FormData()
  form.append('file', file)
  return client.post('/image', form, { signal })
}

export function searchText({ query, topK = 5, category }, signal) {
  const payload = { query, top_k: topK }
  if (category) payload.category = category
  return client.post('/text', payload, { signal })
}

export function matchImageText({ file, text, topK = 5 }, signal) {
  const form = new FormData()
  form.append('file', file)
  form.append('text', text)
  form.append('top_k', String(topK))
  return client.post('/match', form, { signal })
}
