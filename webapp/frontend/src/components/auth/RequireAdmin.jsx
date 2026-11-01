import { Button } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { useAuth } from '../../context/AuthContext'

export default function RequireAdmin({ children, title = '这是管理员功能', description }) {
  const { isAdmin, openLogin } = useAuth()

  if (isAdmin) return children

  return (
    <div className="sv-locked sv-reveal">
      <div className="sv-locked-icon">
        <LockOutlined />
      </div>
      <h2>{title}</h2>
      <p>{description || '运行记录与系统状态只对管理员开放。登录后即可查看，游客请使用检索功能。'}</p>
      <Button type="primary" size="large" onClick={openLogin}>
        登录管理员账号
      </Button>
    </div>
  )
}
