import { Button, Result } from 'antd'
import { Route, Routes, useNavigate } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import { AppProvider } from './context/AppContext'
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
      subTitle="这个地址没有对应的页面，请从左侧导航返回工作台。"
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
    <AppProvider>
      <WorkflowProvider>
        <AppShell>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/image" element={<ImageLab />} />
            <Route path="/text" element={<TextSearch />} />
            <Route path="/match" element={<MatchLab />} />
            <Route path="/history" element={<History />} />
            <Route path="/status" element={<Status />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AppShell>
      </WorkflowProvider>
    </AppProvider>
  )
}
