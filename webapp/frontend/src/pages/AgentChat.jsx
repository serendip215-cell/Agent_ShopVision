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
import { sendAgentChat } from '../api/client'
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
  const controllerRef = useRef(null)
  const idRef = useRef(0)
  const streamRef = useRef(null)

  useEffect(() => {
    if (messages.length === 0 && !pending && !error) return
    const node = streamRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages, pending, error])

  useEffect(() => () => controllerRef.current?.abort(), [])

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
    const text = input.trim()
    if (!text || pending) return
    setInput('')
    run(text)
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
                    {message.text}
                  </div>

                  {message.thinking && (
                    <details className="sv-ag-trace">
                      <summary>思考过程</summary>
                      <p>{message.thinking}</p>
                    </details>
                  )}

                  {message.tools?.length > 0 && (
                    <div className="sv-ag-tools">
                      <div className="sv-ag-tools-head">
                        <ToolOutlined />
                        工具调用
                      </div>
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
                  )}
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
          >
            <textarea
              className="sv-ag-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="描述你的购物需求，例如「找一双白色运动鞋」"
              aria-label="输入导购需求"
            />
            <div className="sv-ag-composer-side">
              <Button
                type="primary"
                htmlType="submit"
                icon={<SendOutlined />}
                loading={pending}
                disabled={!input.trim() || pending}
              >
                发送
              </Button>
              <span className="sv-ag-hint">Enter 发送 · Shift + Enter 换行</span>
            </div>
          </form>
        </div>
      </section>
    </div>
  )
}
