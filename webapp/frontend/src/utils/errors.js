const ERROR_COPY = {
  40000: {
    title: '参数不符合要求',
    hint: '请检查查询词长度与返回条数后重试。',
  },
  40001: {
    title: '图片格式无法识别',
    hint: '请上传 PNG、JPG 或 WEBP 格式的商品图，建议先确认文件能正常打开。',
  },
  40002: {
    title: '没有收到图片',
    hint: '请重新选择一张商品图再提交。',
  },
  40003: {
    title: '模型与索引不同源',
    hint: '查询向量维度和索引不一致，通常是后端编码器配置问题，请到系统状态页检查。',
  },
  40004: {
    title: '图片超过大小上限',
    hint: '当前上限为 10 MB，请压缩图片或降低分辨率后重试。',
  },
  40400: {
    title: '接口路径不存在',
    hint: '请确认后端版本与前端接口约定一致。',
  },
  40401: {
    title: '类别不存在',
    hint: '该类别不在索引注册表中，已为你重置为「全部类别」。',
  },
  40402: {
    title: '索引文件缺失',
    hint: '后端缺少注册表、条目表或向量文件，请到系统状态页查看索引目录。',
  },
  50000: {
    title: '服务器内部错误',
    hint: '请稍后重试；如果持续失败，请到系统状态页检查后服务状态。',
  },
  50001: {
    title: '模型或依赖不可用',
    hint: '后端可能仍在占位模式，或 ONNX / cn_clip 依赖未安装。',
  },
  TIMEOUT: {
    title: '请求超时',
    hint: '图片可能过大或模型繁忙，请压缩图片后重试。',
  },
  TASK_TIMEOUT: {
    title: '异步任务超时',
    hint: '请确认后端已启动 Celery worker：celery -A app.celery_app worker --pool=solo。',
  },
  NETWORK: {
    title: '无法连接后端',
    hint: '请确认后端已启动：uvicorn app.main:app --reload --port 8000。',
  },
  INVALID_RESPONSE: {
    title: '后端响应格式异常',
    hint: '请确认前后端版本一致，返回体应为 { code, result, msg }。',
  },
}

export function describeError(error) {
  if (!error) return null

  const code = error.code
  const key = typeof code === 'number' ? code : String(code || '')

  if (ERROR_COPY[key]) {
    return { code, ...ERROR_COPY[key], message: error.message }
  }

  const prefix = String(key).slice(0, 3)
  if (prefix === '400') {
    return {
      code,
      title: '请求参数有问题',
      hint: '请检查输入后重试。',
      message: error.message,
    }
  }
  if (prefix === '404') {
    return {
      code,
      title: '目标资源不存在',
      hint: '请确认接口路径与类别设置。',
      message: error.message,
    }
  }
  if (prefix === '500') {
    return {
      code,
      title: '服务暂时不可用',
      hint: '请稍后重试，或到系统状态页检查后端。',
      message: error.message,
    }
  }

  return {
    code: code ?? 'UNKNOWN',
    title: '请求没有完成',
    hint: '请稍后重试。',
    message: error.message || '未知错误',
  }
}

export function isCanceled(error) {
  return (
    error?.__CANCEL__ === true ||
    error?.code === 'ERR_CANCELED' ||
    error?.name === 'CanceledError' ||
    error?.name === 'AbortError'
  )
}
