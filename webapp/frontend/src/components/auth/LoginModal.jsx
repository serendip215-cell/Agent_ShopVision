import { useState } from 'react'
import { Button, Input, Modal } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useAuth } from '../../context/AuthContext'

export default function LoginModal() {
  const { loginOpen, closeLogin, login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  function submit() {
    const result = login(username.trim(), password)
    if (!result.ok) {
      setError(result.message)
      return
    }
    setUsername('')
    setPassword('')
    setError('')
  }

  function cancel() {
    setError('')
    closeLogin()
  }

  return (
    <Modal
      open={loginOpen}
      onCancel={cancel}
      footer={null}
      width={380}
      centered
      className="sv-login-modal"
      title={null}
    >
      <div className="sv-login">
        <div className="sv-login-badge">
          <LockOutlined />
        </div>
        <h2>管理员登录</h2>
        <p>运行记录与系统状态属于管理功能，登录后才可见。游客可直接使用三台检索仪器。</p>
        <div className="sv-login-form">
          <Input
            size="large"
            prefix={<UserOutlined />}
            placeholder="账号"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            onPressEnter={submit}
            autoFocus
          />
          <Input.Password
            size="large"
            prefix={<LockOutlined />}
            placeholder="密码"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            onPressEnter={submit}
          />
          {error && <div className="sv-inline-error">{error}</div>}
          <Button type="primary" size="large" block onClick={submit}>
            登录
          </Button>
          <span className="sv-login-hint">演示账号写死在前端：admin / admin888</span>
        </div>
      </div>
    </Modal>
  )
}
