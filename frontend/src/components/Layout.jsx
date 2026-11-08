import { Outlet, NavLink } from 'react-router-dom'
import { MessageSquare, Shield, FileSearch, Settings, Scale } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/chat', icon: MessageSquare, label: '법률 Q&A' },
  { to: '/security', icon: Shield, label: '보안 Q&A' },
  { to: '/review', icon: FileSearch, label: '계약서 리뷰' },
  { to: '/admin', icon: Settings, label: '관리자' },
]

/**
 * 앱 셸 — 좁은 아이콘 레일 + 본문
 * 대화 기록 패널은 각 채팅 화면이 자체적으로 접고 펼친다.
 */
export default function Layout() {
  return (
    <div className="flex h-screen bg-slate-50">
      <aside className="w-[76px] flex-shrink-0 bg-white border-r border-slate-200 flex flex-col items-center py-4">
        {/* 로고 */}
        <NavLink to="/chat" className="mb-6 flex flex-col items-center gap-1" title="법무주치의">
          <span className="w-10 h-10 rounded-xl bg-primary-600 text-white flex items-center justify-center shadow-sm">
            <Scale className="w-5 h-5" />
          </span>
          <span className="text-[10px] font-bold tracking-tight text-slate-800">법무주치의</span>
        </NavLink>

        <nav className="flex-1 flex flex-col items-center gap-1 w-full px-2">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `w-full flex flex-col items-center gap-1 py-2.5 rounded-xl transition-colors ${
                  isActive
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
                }`
              }
            >
              <Icon className="w-5 h-5" />
              <span className="text-[11px] font-medium leading-none">{label}</span>
            </NavLink>
          ))}
        </nav>

        <p className="text-[10px] text-slate-400 text-center leading-tight px-1">
          사내 전용
          <br />
          참고용 정보
        </p>
      </aside>

      <main className="flex-1 min-w-0 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
