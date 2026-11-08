import { useState, useEffect, createContext } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import SecurityChatPage from './pages/SecurityChatPage'
import ReviewPage from './pages/ReviewPage'
import AdminPage from './pages/AdminPage'
import { getCurrentUser } from './api/client'

export const UserContext = createContext(null)

function AdminGuard({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-[13px] text-slate-500">권한 확인 중…</p>
      </div>
    )
  }

  if (!user || user.role !== 'executive') {
    // 개발 환경: 권한 체크 우회
    if (import.meta.env.DEV) {
      return <UserContext.Provider value={user}>{children}</UserContext.Provider>
    }
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center p-8">
          <h2 className="text-[17px] font-semibold text-slate-900 mb-1.5">접근 권한이 없습니다</h2>
          <p className="text-[13px] text-slate-500">관리자 화면은 경영진만 이용할 수 있습니다.</p>
        </div>
      </div>
    )
  }

  return <UserContext.Provider value={user}>{children}</UserContext.Provider>
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="security" element={<SecurityChatPage />} />
            <Route path="review" element={<ReviewPage />} />
            <Route path="admin" element={<AdminGuard><AdminPage /></AdminGuard>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
