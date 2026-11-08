import { useEffect, useRef, useState } from 'react'
import { Button, Spin } from 'antd'
import {
  ClearOutlined,
  FileTextOutlined,
  PictureOutlined,
  RobotOutlined,
  SendOutlined,
  ToolOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { sendAgentChat, sendAgentImage } from '../api/client'
import { DetailDrawer } from '../components/result/Results'
import { ItemThumbRow } from '../components/result/ItemThumbRow'
import { isCanceled } from '../utils/errors'
import { EmptyState, SectionLabel } from '../components/common/Ui'

// 只会把输入框填上，不自动发送；不是示例商品，也不是假数据。
const PROMPTS = ['找一双白色运动鞋', '有没有黑色的双肩包', '推荐一款保温水杯']

function describeAgentError(error) {
  const code = String(error?.code ?? '')
  if (code === 'NETWORK') {
    return {
      title: '后端服务未连接',
      message: '前端访问不到 8000 端口的后端接口。请先启动 uvicorn，再重新发送。',
    }
  }
  if (code === '404' || code.startsWith('404')) {
    return {
      title: '对话接口尚未上线',
      message:
        '前端已按 POST /api/v1/agent/chat 发起请求，但后端当前没有注册该路由（HTTP 404）。接口上线前，本页不会生成任何模拟回复。',
    }
  }
  if (code === 'TIMEOUT') {
    return {
      title: '请求超时',
      message: '后端在 30 秒内没有返回。请确认服务状态，或稍后重试。',
    }
  }
  return {
    title: '请求没有完成',
    message: error?.message || '未知错误',
  }
}

function readTraceText(value) {
  if (typeof value === 'string') return value.trim()
  if (Array.isArray(value)) {
    return value
      .map((item) => (typeof item === 'string' ? item.trim() : ''))
      .filter(Boolean)
      .join('\n')
  }
  return ''
}

function readToolCalls(value) {
  if (!Array.isArray(value)) return []
  return value.filter((item) => item && typeof item === 'object')
}

export default function AgentChat() {
  const navigate = useNavigate()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)
  const [activeItem, setActiveItem] = useState(null)
  const [imageFile, setImageFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const fileRef = useRef(null)
  const controllerRef = useRef(null)
  const idRef = useRef(0)
  const streamRef = useRef(null)

  useEffect(() => {
    if (messages.length === 0 && !pending && !error) return
    const node = streamRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages, pending, error])

  useEffect(() => () => controllerRef.current?.abort(), [])

  // 页面任意位置 Ctrl+V 都能贴图（焦点不在输入框也生效），与豆包一致
  useEffect(() => {
    function onWindowPaste(event) {
      const items = Array.from(event.clipboardData?.items || [])
      const imageItem = items.find((item) => String(item.type).startsWith('image/'))
      if (!imageItem) return
      const file = imageItem.getAsFile()
      if (!file) return
      event.preventDefault()
      acceptFile(file)
    }
    window.addEventListener('paste', onWindowPaste)
    return () => window.removeEventListener('paste', onWindowPaste)
  }, [previewUrl])

  function pushMessage(message) {
    idRef.current += 1
    const id = idRef.current
    setMessages((prev) => [...prev, { id, ...message }])
  }

  async function run(text, { echo = true } = {}) {
    const message = String(text || '').trim()
    if (!message || pending) return

    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    if (echo) pushMessage({ role: 'user', text: message })
    setError(null)
    setPending(true)

    try {
      const result = await sendAgentChat({ message }, controller.signal)
      const reply = typeof result?.reply === 'string' ? result.reply.trim() : ''
      if (!reply) {
        setError({
          title: '返回内容不完整',
          message:
            '接口已连通，但返回体里没有可展示的 reply 字段。请与后端确认约定：{ code, result: { reply, thinking?, tool_calls? } }。',
          retryText: message,
        })
        return
      }
      pushMessage({
        role: 'assistant',
        text: reply,
        thinking: readTraceText(result.thinking),
        tools: readToolCalls(result.tool_calls),
        items: Array.isArray(result.items) ? result.items : [],
      })
    } catch (err) {
      if (isCanceled(err)) return
      setError({ ...describeAgentError(err), retryText: message })
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null
        setPending(false)
      }
    }
  }

  function submit() {
    if (pending) return
    if (imageFile) {
      runImage()
      return
    }
    const text = input.trim()
    if (!text) return
    setInput('')
    run(text)
  }

  function pickImage() {
    fileRef.current?.click()
  }

  function acceptFile(file) {
    if (!file) return
    if (!String(file.type).startsWith('image/')) {
      setError({ title: '文件类型不支持', message: '请选择 PNG / JPG / WEBP 图片。' })
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      setError({ title: '图片过大', message: '上限 10 MB，压缩后再试。' })
      return
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setImageFile(file)
    setPreviewUrl(URL.createObjectURL(file))
    setError(null)
  }

  function onPickImage(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    acceptFile(file)
  }

  // 直接 Ctrl+V 粘贴截图：由 window 级 paste 监听统一处理（见上面的 useEffect）

  function handleDrop(event) {
    event.preventDefault()
    const file = event.dataTransfer?.files?.[0]
    if (file) acceptFile(file)
  }

  function clearImage() {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setImageFile(null)
    setPreviewUrl('')
  }

  async function runImage() {
    if (!imageFile || pending) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    const text = input.trim()
    pushMessage({ role: 'user', text: text || '（图片）', imageUrl: previewUrl })
    setInput('')
    setError(null)
    setPending(true)

    try {
      const result = await sendAgentImage({ file: imageFile, message: text }, controller.signal)
      const reply = typeof result?.reply === 'string' ? result.reply.trim() : ''
      if (!reply) {
        setError({
          title: '返回内容不完整',
          message: '接口已连通，但返回体里没有可展示的 reply 字段。',
        })
        return
      }
      pushMessage({
        role: 'assistant',
        text: reply,
        thinking: readTraceText(result.thinking),
        tools: readToolCalls(result.tool_calls),
        items: Array.isArray(result.items) ? result.items : [],
      })
      // 不 revoke：消息里还要用这个预览地址展示用户上传的图
      setImageFile(null)
      setPreviewUrl('')
    } catch (err) {
      if (isCanceled(err)) return
      setError({ ...describeAgentError(err) })
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null
        setPending(false)
      }
    }
  }

  function handleKeyDown(event) {
    if (event.key !== 'Enter' || event.shiftKey) return
    if (event.nativeEvent?.isComposing) return
    event.preventDefault()
    submit()
  }

  function clearSession() {
    controllerRef.current?.abort()
    controllerRef.current = null
    setMessages([])
    setError(null)
    setInput('')
    setPending(false)
  }

  const hasSession = messages.length > 0 || Boolean(error)

  return (
    <div className="sv-ag">
      <header className="sv-page-head">
        <div className="sv-page-head-lines" aria-hidden="true">
          <svg viewBox="0 0 800 200" preserveAspectRatio="none">
            <path
              d="M 0 100 C 200 60, 400 120, 800 80"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.15"
              strokeWidth="1.5"
            />
            <path
              d="M 0 130 C 250 90, 500 150, 800 110"
              fill="none"
              stroke="#5fa8b0"
              strokeOpacity="0.1"
              strokeWidth="1"
            />
            <circle cx="300" cy="95" r="3" fill="#5fa8b0" fillOpacity="0.25" />
            <circle cx="500" cy="120" r="2.5" fill="#5fa8b0" fillOpacity="0.2" />
          </svg>
        </div>
        <div className="sv-page-head-copy">
          <span className="sv-eyebrow">AI SHOPPING GUIDE</span>
          <h1>Describe & Discover</h1>
          <div className="sv-page-head-modes">
            <button type="button" className="sv-page-mode-chip is-current">
              <RobotOutlined />
              <span>Agent</span>
            </button>
            <button
              type="button"
              className="sv-page-mode-chip"
              onClick={() => navigate('/image')}
            >
              <PictureOutlined />
              <span>Image</span>
            </button>
            <button
              type="button"
              className="sv-page-mode-chip"
              onClick={() => navigate('/text')}
            >
              <FileTextOutlined />
              <span>Text</span>
            </button>
          </div>
        </div>
      </header>

      <section>
        <SectionLabel
          index="01"
          title="会话"
          extra={
            <Button
              type="text"
              size="small"
              icon={<ClearOutlined />}
              onClick={clearSession}
              disabled={!hasSession && !input}
            >
              清空会话
            </Button>
          }
        />

        <div className="sv-ag-card">
          <div className="sv-ag-stream" ref={streamRef} role="log" aria-live="polite">
            {messages.length === 0 && !pending && !error && (
              <div className="sv-ag-empty">
                <EmptyState
                  icon={<RobotOutlined />}
                  title="还没有对话"
                  description="发送后会直接请求后端 Agent；接口未上线或服务不可达时，这里只显示真实错误提示。"
                />
                <div className="sv-ag-prompts">
                  <span>可以试试</span>
                  {PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      className="sv-ag-prompt"
                      onClick={() => setInput(prompt)}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => (
              <div
                key={message.id}
                className={`sv-ag-msg ${message.role === 'user' ? 'is-user' : 'is-assistant'}`}
              >
                <span className={`sv-ag-avatar ${message.role === 'user' ? 'is-user' : 'is-assistant'}`}>
                  {message.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                </span>
                <div className="sv-ag-bubble-wrap">
                  <span className="sv-ag-role">{message.role === 'user' ? '你' : '助手'}</span>
                  <div className={`sv-ag-bubble ${message.role === 'user' ? 'is-user' : 'is-assistant'}`}>
                    {message.imageUrl && (
                      <img className="sv-ag-bubble-img" src={message.imageUrl} alt="上传的图片" />
                    )}
                    {message.text}
                  </div>

                  {message.thinking && (
                    <details className="sv-ag-trace">
                      <summary>思考过程</summary>
                      <p>{message.thinking}</p>
                    </details>
                  )}

                  {message.tools?.length > 0 && (
                    <details className="sv-ag-trace">
                      <summary>工具调用（{message.tools.length}）</summary>
                      <div className="sv-ag-tools">
                        {message.tools.map((call, index) => (
                          <div key={`${message.id}-tool-${index}`} className="sv-ag-tool">
                            <span className="sv-ag-tool-name">
                              {String(call.name || call.tool || '未命名工具')}
                            </span>
                            {call.arguments != null && (
                              <code className="sv-ag-tool-args">
                                {JSON.stringify(call.arguments)}
                              </code>
                            )}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  <ItemThumbRow items={message.items} onSelect={setActiveItem} />
                </div>
              </div>
            ))}

            {pending && (
              <div className="sv-ag-msg is-assistant">
                <span className="sv-ag-avatar is-assistant">
                  <RobotOutlined />
                </span>
                <div className="sv-ag-bubble-wrap">
                  <span className="sv-ag-role">助手</span>
                  <div className="sv-ag-bubble is-assistant is-pending">
                    <Spin size="small" />
                    <span>正在等待后端返回…</span>
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="sv-ag-error" role="alert">
                <div className="sv-ag-error-head">
                  <strong>{error.title}</strong>
                </div>
                <p>{error.message}</p>
                {error.retryText && (
                  <Button
                    size="small"
                    onClick={() => run(error.retryText, { echo: false })}
                    disabled={pending}
                  >
                    重新发送
                  </Button>
                )}
              </div>
            )}
          </div>

          <form
            className="sv-ag-composer"
            onSubmit={(event) => {
              event.preventDefault()
              submit()
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            {imageFile && (
              <div className="sv-ag-attach">
                <span className="sv-ag-attach-thumb">
                  <img src={previewUrl} alt="待检索图片" />
                  <button
                    type="button"
                    className="sv-ag-attach-remove"
                    aria-label="移除图片"
                    onClick={clearImage}
                  >
                    ×
                  </button>
                </span>
                <span className="sv-ag-attach-info">
                  已选 1 张图 · 可直接发送，或输入文字一起检索
                </span>
              </div>
            )}
            <textarea
              className="sv-ag-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder={
                imageFile
                  ? '可选：补充一句描述（如「黑色的」「高帮」），会和图片一起检索'
                  : '描述你的购物需求，例如「找一双白色运动鞋」'
              }
              aria-label="输入导购需求"
            />
            <div className="sv-ag-composer-side">
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                hidden
                onChange={onPickImage}
              />
              <Button icon={<PictureOutlined />} onClick={pickImage} disabled={pending}>
                上传图片
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SendOutlined />}
                loading={pending}
                disabled={(!input.trim() && !imageFile) || pending}
              >
                发送
              </Button>
              <span className="sv-ag-hint">Enter 发送 · Shift + Enter 换行</span>
            </div>
          </form>
        </div>
      </section>

      <DetailDrawer
        item={activeItem}
        open={!!activeItem}
        onClose={() => setActiveItem(null)}
      />
    </div>
  )
}
