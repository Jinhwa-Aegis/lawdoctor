import { Outlet, NavLink } from 'react-router-dom'
import { MessageSquare, Shield, FileSearch, Settings } from 'lucide-react'

export default function Layout() {
  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        {/* Logo/Title */}
        <div className="p-6 border-b border-gray-200">
          <h1 className="text-2xl font-bold text-primary-600">법무주치의</h1>
          <p className="text-sm text-gray-500 mt-1">AI 법률 자문 서비스</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          <NavLink
            to="/chat"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                isActive
                  ? 'bg-primary-50 text-primary-700 font-medium'
                  : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            <MessageSquare className="w-5 h-5" />
            <span>법률 Q&A</span>
          </NavLink>

          <NavLink
            to="/security"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                isActive
                  ? 'bg-primary-50 text-primary-700 font-medium'
                  : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            <Shield className="w-5 h-5" />
            <span>정보보안 Q&A</span>
          </NavLink>

          <NavLink
            to="/review"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                isActive
                  ? 'bg-primary-50 text-primary-700 font-medium'
                  : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            <FileSearch className="w-5 h-5" />
            <span>계약서 리뷰</span>
          </NavLink>

          <NavLink
            to="/admin"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                isActive
                  ? 'bg-primary-50 text-primary-700 font-medium'
                  : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            <Settings className="w-5 h-5" />
            <span>관리자</span>
          </NavLink>
        </nav>

        {/* Disclaimer */}
        <div className="p-4 border-t border-gray-200">
          <p className="text-xs text-gray-500 leading-relaxed">
            본 서비스는 참고용 법률·보안 정보를 제공하며, 정식 전문가 자문을 대체하지 않습니다.
            중요한 결정이 필요한 경우 반드시 전문가와 상담하시기 바랍니다.
          </p>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
