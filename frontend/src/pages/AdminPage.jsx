import { useCallback, useContext, useEffect, useState } from 'react'
import { LayoutDashboard, Scale, Shield, Users } from 'lucide-react'
import { getDashboard, getUsers } from '../api/client'
import { UserContext } from '../App'
import { Notice } from '../components/admin/AdminUI'
import OverviewTab from '../components/admin/OverviewTab'
import UsersTab from '../components/admin/UsersTab'
import KnowledgeTab from '../components/admin/KnowledgeTab'

const TABS = [
  { id: 'overview', label: '현황', icon: LayoutDashboard, description: '사용량과 답변 품질을 확인합니다.' },
  { id: 'users', label: '사용자', icon: Users, description: '사용자를 추가하고 역할과 사용 여부를 관리합니다.' },
  { id: 'legal', label: '법률 자료', icon: Scale, description: '법령·판례·자문 문서를 관리합니다. 법률 Q&A와 계약서 리뷰의 근거가 됩니다.' },
  { id: 'security', label: '보안 자료', icon: Shield, description: '보안 가이드와 사고 사례를 관리합니다. 보안 Q&A의 근거가 됩니다.' },
]

const TAB_STORAGE_KEY = 'admin.activeTab'

function readStoredTab() {
  try {
    const saved = localStorage.getItem(TAB_STORAGE_KEY)
    return TABS.some((t) => t.id === saved) ? saved : 'overview'
  } catch {
    return 'overview'
  }
}

export default function AdminPage() {
  const currentUser = useContext(UserContext)
  const [activeTab, setActiveTab] = useState(readStoredTab)
  const [dashboard, setDashboard] = useState(null)
  const [users, setUsers] = useState([])
  const [error, setError] = useState(null)

  const loadDashboard = useCallback(() => {
    getDashboard().then(setDashboard).catch((e) => setError(e.message))
  }, [])
  const loadUsers = useCallback(() => {
    getUsers().then(setUsers).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    loadDashboard()
    loadUsers()
  }, [loadDashboard, loadUsers])

  const selectTab = (id) => {
    setActiveTab(id)
    try {
      localStorage.setItem(TAB_STORAGE_KEY, id)
    } catch {
      // 저장소를 쓸 수 없는 환경 — 무시
    }
  }

  const tab = TABS.find((t) => t.id === activeTab)

  return (
    <div className="min-h-full bg-slate-50">
      {/* 상단 바 */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="max-w-6xl mx-auto px-6 pt-5">
          <h1 className="text-[20px] font-bold text-slate-900">관리자</h1>
          <p className="mt-0.5 text-[13px] text-slate-500">{tab.description}</p>
          <nav className="mt-4 flex gap-1 -mb-px" role="tablist">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={activeTab === id}
                onClick={() => selectTab(id)}
                className={`inline-flex items-center gap-1.5 border-b-2 px-3 pb-2.5 pt-1 text-[13.5px] font-medium transition-colors ${
                  activeTab === id
                    ? 'border-primary-600 text-slate-900'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
                {id === 'users' && users.length > 0 && (
                  <span className="ml-0.5 rounded-full bg-slate-100 px-1.5 text-[11px] text-slate-500 tabular-nums">{users.length}</span>
                )}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-6">
        {error && (
          <div className="mb-5">
            <Notice tone="error" title="관리자 정보를 불러오지 못했습니다" onClose={() => setError(null)}>{error}</Notice>
          </div>
        )}
        {activeTab === 'overview' && <OverviewTab dashboard={dashboard} />}
        {activeTab === 'users' && (
          <UsersTab
            users={users}
            currentUserId={currentUser?.id}
            onUsersChanged={() => {
              loadUsers()
              loadDashboard()
            }}
          />
        )}
        {activeTab === 'legal' && <KnowledgeTab domain="legal" />}
        {activeTab === 'security' && <KnowledgeTab domain="security" />}
      </div>
    </div>
  )
}
