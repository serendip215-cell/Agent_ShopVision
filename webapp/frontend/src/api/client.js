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

// ---- 数据入库（未启用管理鉴权，仅本机演示） ----

export function suggestAdminItem(file, signal) {
  const form = new FormData()
  form.append('file', file)
  return client.post('/admin/items', form, { signal })
}

export function ingestAdminItem({ file, category, createCategory = false, metadata = {} }, signal) {
  const form = new FormData()
  form.append('file', file)
  form.append('category', category)
  form.append('confirm', 'true')
  if (createCategory) form.append('create_category', 'true')
  Object.entries(metadata).forEach(([key, value]) => {
    const text = String(value ?? '').trim()
    if (text) form.append(key, text)
  })
  return client.post('/admin/items', form, { signal })
}

export function createAdminCategory(name, signal) {
  return client.post('/admin/categories', { name }, { signal })
}

// ---- 异步任务（Celery + Redis）：提交拿 task_id，再轮询结果 ----

export function enqueueImageTask(file, signal) {
  const form = new FormData()
  form.append('file', file)
  return client.post('/tasks/image', form, { signal })
}

export function enqueueBatchTask(files, signal) {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  return client.post('/tasks/batch', form, { signal })
}

export function fetchTask(taskId, signal) {
  return client.get(`/tasks/${taskId}`, { signal })
}

const TASK_POLL_MS = 800

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    const onAbort = () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

/**
 * 轮询任务直到 SUCCESS，返回结果；FAILURE 抛 AppError。
 * @param {string} taskId
 * @param {{ signal?: AbortSignal, timeoutMs?: number, onProgress?: (p: {done: number, total: number}) => void }} options
 */
export async function waitForTask(taskId, { signal, timeoutMs = 120000, onProgress } = {}) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const payload = await fetchTask(taskId, signal)
    if (payload.status === 'SUCCESS') return payload.result
    if (payload.status === 'FAILURE') {
      throw new AppError(
        payload.error?.code ?? 'TASK_FAILED',
        payload.error?.msg || '异步任务失败，请重试',
      )
    }
    if (payload.progress && onProgress) onProgress(payload.progress)
    if (Date.now() > deadline) {
      throw new AppError(
        'TASK_TIMEOUT',
        '任务长时间未完成，请确认 Celery worker 已启动（celery -A app.celery_app worker --pool=solo）',
      )
    }
    await sleep(TASK_POLL_MS, signal)
  }
}
