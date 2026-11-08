import { useMemo, useState } from 'react'
import { Plus, Search, Trash2, PanelLeftClose } from 'lucide-react'

/** 대화를 최근 수정일 기준으로 묶는다 */
function groupSessions(sessions) {
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const today = startOfDay(new Date())
  const DAY = 24 * 60 * 60 * 1000
  const groups = [
    { label: '오늘', items: [] },
    { label: '어제', items: [] },
    { label: '지난 7일', items: [] },
    { label: '이전', items: [] },
  ]
  for (const s of sessions) {
    const t = startOfDay(new Date(s.updated_at || s.created_at))
    const diff = today - t
    if (diff <= 0) groups[0].items.push(s)
    else if (diff <= DAY) groups[1].items.push(s)
    else if (diff <= 7 * DAY) groups[2].items.push(s)
    else groups[3].items.push(s)
  }
  return groups.filter((g) => g.items.length > 0)
}

/**
 * 대화 기록 패널 — 날짜별 묶음, 제목 검색, 삭제
 */
export default function HistoryPanel({
  sessions,
  currentSessionId,
  onSelect,
  onDelete,
  onNewChat,
  onClose,
  newChatLabel,
  emptyText,
  categoryField,
  categoryLabels = {},
}) {
  const [query, setQuery] = useState('')

  const groups = useMemo(() => {
    const q = query.trim()
    const filtered = q ? sessions.filter((s) => (s.title || '').includes(q)) : sessions
    return groupSessions(filtered)
  }, [sessions, query])

  return (
    <div className="w-[264px] flex-shrink-0 border-r border-slate-200 bg-white flex flex-col">
      <div className="flex items-center justify-between px-4 h-14">
        <span className="text-[13px] font-semibold text-slate-800">대화 기록</span>
        <button
          type="button"
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          title="기록 닫기"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      <div className="px-3 space-y-2">
        <button
          type="button"
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-1.5 h-9 rounded-xl bg-primary-600 text-white text-[13px] font-semibold hover:bg-primary-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          {newChatLabel}
        </button>
        <label className="flex items-center gap-2 h-9 px-3 rounded-xl bg-slate-100 text-slate-500 focus-within:bg-white focus-within:ring-1 focus-within:ring-primary-300">
          <Search className="w-3.5 h-3.5 flex-shrink-0" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="제목 검색"
            className="w-full bg-transparent text-[13px] text-slate-800 placeholder:text-slate-400 focus:outline-none"
          />
        </label>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 py-3">
        {groups.length === 0 && (
          <p className="text-xs text-slate-400 text-center mt-6 px-4 whitespace-pre-line">
            {query ? '검색 결과가 없습니다.' : emptyText}
          </p>
        )}
        {groups.map((group) => (
          <div key={group.label} className="mb-3">
            <p className="px-2 mb-1 text-[11px] font-medium text-slate-400">{group.label}</p>
            {group.items.map((session) => {
              const active = currentSessionId === session.id
              const category = session[categoryField]
              return (
                <div
                  key={session.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(session.id)}
                  onKeyDown={(e) => e.key === 'Enter' && onSelect(session.id)}
                  className={`group flex items-start gap-2 px-2.5 py-2 rounded-lg cursor-pointer transition-colors ${
                    active ? 'bg-primary-50' : 'hover:bg-slate-100'
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <p className={`text-[13px] truncate ${active ? 'text-primary-800 font-medium' : 'text-slate-700'}`}>
                      {session.title}
                    </p>
                    {category && (
                      <p className="text-[11px] text-slate-400 mt-0.5">{categoryLabels[category] || category}</p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={(e) => onDelete(e, session.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-red-500 hover:bg-white transition-opacity"
                    title="대화 삭제"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
