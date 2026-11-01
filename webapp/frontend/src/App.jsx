import { Button, Result } from 'antd'
import { Route, Routes, useNavigate } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import RequireAdmin from './components/auth/RequireAdmin'
import { AppProvider } from './context/AppContext'
import { AuthProvider } from './context/AuthContext'
import { WorkflowProvider } from './context/WorkflowContext'
import History from './pages/History'
import ImageLab from './pages/ImageLab'
import MatchLab from './pages/MatchLab'
import Overview from './pages/Overview'
import Status from './pages/Status'
import TextSearch from './pages/TextSearch'

function NotFound() {
  const navigate = useNavigate()
  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="这个地址没有对应的页面，请从顶部导航返回工作台。"
      extra={
        <Button type="primary" onClick={() => navigate('/')}>
          回到工作台
        </Button>
      }
    />
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppProvider>
        <WorkflowProvider>
          <AppShell>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/image" element={<ImageLab />} />
              <Route path="/text" element={<TextSearch />} />
              <Route path="/match" element={<MatchLab />} />
              <Route
                path="/history"
                element={(
                  <RequireAdmin
                    title="运行记录是管理员功能"
                    description="这里汇总了本机所有的检索轨迹，只对管理员开放。"
                  >
                    <History />
                  </RequireAdmin>
                )}
              />
              <Route
                path="/status"
                element={(
                  <RequireAdmin
                    title="系统状态是管理员功能"
                    description="模型、索引与接口细节只对管理员开放。"
                  >
                    <Status />
                  </RequireAdmin>
                )}
              />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </AppShell>
        </WorkflowProvider>
      </AppProvider>
    </AuthProvider>
  )
}
