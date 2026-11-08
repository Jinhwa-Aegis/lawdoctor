import { useMemo, useState } from 'react'
import { Plus, Search, UserRound } from 'lucide-react'
import { createUser, updateUser } from '../../api/client'
import { Button, Card, EmptyState, Field, Notice, inputClass } from './AdminUI'

const ROLE_OPTIONS = [
  { value: 'staff', label: '직원' },
  { value: 'executive', label: '경영진' },
]

const EMPTY_USER = { username: '', display_name: '', role: 'staff' }

function AddUserForm({ onCreated, onCancel }) {
  const [form, setForm] = useState(EMPTY_USER)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!form.username.trim() || !form.display_name.trim()) {
      setError('사용자명과 표시 이름을 모두 입력해주세요.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const user = await createUser({ ...form, username: form.username.trim(), display_name: form.display_name.trim() })
      onCreated(user)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-primary-100 bg-primary-50/40 p-4 mb-4">
      <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_140px_auto] gap-3 items-end">
        <Field label="표시 이름">
          <input autoFocus className={inputClass} value={form.display_name} placeholder="홍길동"
            onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
        </Field>
        <Field label="사용자명">
          <input className={inputClass} value={form.username} placeholder="hong.gildong"
            onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </Field>
        <Field label="역할">
          <select className={inputClass} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onCancel}>취소</Button>
          <Button type="submit" loading={saving}>추가</Button>
        </div>
      </div>
      <p className="mt-2 text-[11.5px] text-slate-500">경영진은 관리자 화면과 소송·분쟁 분야에 접근할 수 있습니다.</p>
      {error && <div className="mt-3"><Notice tone="error">{error}</Notice></div>}
    </form>
  )
}

function ActiveToggle({ active, disabled, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      disabled={disabled}
      onClick={() => onChange(!active)}
      className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
        active ? 'bg-primary-600' : 'bg-slate-300'
      }`}
    >
      <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${active ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
    </button>
  )
}

export default function UsersTab({ users, currentUserId, onUsersChanged }) {
  const [adding, setAdding] = useState(false)
  const [query, setQuery] = useState('')
  const [savingId, setSavingId] = useState(null)
  const [notice, setNotice] = useState(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return users
    return users.filter((u) => u.display_name.toLowerCase().includes(q) || u.username.toLowerCase().includes(q))
  }, [users, query])

  const patch = async (user, data, message) => {
    setSavingId(user.id)
    setNotice(null)
    try {
      await updateUser(user.id, data)
      setNotice({ tone: 'success', text: message })
      onUsersChanged()
    } catch (err) {
      setNotice({ tone: 'error', text: err.message })
    } finally {
      setSavingId(null)
    }
  }

  const activeCount = users.filter((u) => u.is_active).length

  return (
    <Card
      title="사용자"
      description={`전체 ${users.length}명 · 활성 ${activeCount}명`}
      icon={UserRound}
      action={!adding && <Button icon={Plus} onClick={() => setAdding(true)}>사용자 추가</Button>}
    >
      {adding && (
        <AddUserForm
          onCancel={() => setAdding(false)}
          onCreated={(u) => {
            setAdding(false)
            setNotice({ tone: 'success', text: `${u.display_name} 님을 추가했습니다.` })
            onUsersChanged()
          }}
        />
      )}

      {notice && (
        <div className="mb-4">
          <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>
        </div>
      )}

      <div className="relative mb-3 max-w-xs">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input className={`${inputClass} pl-9`} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="이름 또는 사용자명 검색" />
      </div>

      {filtered.length === 0 ? (
        <EmptyState icon={UserRound} title={users.length ? '검색 결과가 없습니다' : '등록된 사용자가 없습니다'} />
      ) : (
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-y border-slate-100 bg-slate-50 text-left text-[12px] text-slate-500">
                <th className="px-5 py-2 font-medium">이름</th>
                <th className="px-3 py-2 font-medium">역할</th>
                <th className="px-3 py-2 font-medium">사용</th>
                <th className="px-5 py-2 font-medium text-right">등록일</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((u) => {
                const isSelf = u.id === currentUserId
                return (
                  <tr key={u.id} className={u.is_active ? '' : 'text-slate-400'}>
                    <td className="px-5 py-2.5">
                      <div className="flex items-center gap-2.5">
                        <span className="w-8 h-8 rounded-full bg-slate-100 text-slate-600 text-[12px] font-semibold flex items-center justify-center">
                          {u.display_name.slice(0, 1)}
                        </span>
                        <div className="min-w-0">
                          <p className={`font-medium ${u.is_active ? 'text-slate-900' : 'text-slate-400'}`}>
                            {u.display_name}
                            {isSelf && <span className="ml-1.5 text-[11px] font-normal text-primary-600">나</span>}
                          </p>
                          <p className="text-[12px] text-slate-400">{u.username}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <select
                        aria-label={`${u.display_name} 역할`}
                        className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[12.5px] disabled:bg-slate-50"
                        value={u.role}
                        disabled={isSelf || savingId === u.id}
                        title={isSelf ? '본인 역할은 바꿀 수 없습니다' : undefined}
                        onChange={(e) => patch(u, { role: e.target.value }, `${u.display_name} 님의 역할을 바꿨습니다.`)}
                      >
                        {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-2.5">
                      <ActiveToggle
                        active={u.is_active}
                        disabled={isSelf || savingId === u.id}
                        onChange={(active) => patch(u, { is_active: active }, `${u.display_name} 님을 ${active ? '활성화' : '비활성화'}했습니다.`)}
                      />
                    </td>
                    <td className="px-5 py-2.5 text-right text-slate-500 tabular-nums">
                      {new Date(u.created_at).toLocaleDateString('ko-KR')}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

