import { useState } from 'react'
import { ChevronDown, ChevronUp, GitCompareArrows, AlertTriangle, Scale } from 'lucide-react'

const RISK_STYLES = {
  high: { bar: 'bg-red-500', badge: 'bg-red-50 text-red-700 ring-red-200', label: '위험 높음' },
  medium: { bar: 'bg-amber-400', badge: 'bg-amber-50 text-amber-700 ring-amber-200', label: '위험 보통' },
  low: { bar: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 ring-emerald-200', label: '위험 낮음' },
}

/** 카드 안에서는 [1] 같은 참고자료 번호를 숨긴다 (본 답변에서 확인) */
function stripRefs(text) {
  return (text || '').replace(/\s*\[\d+\]/g, '')
}

function OpinionCard({ opinion }) {
  const [open, setOpen] = useState(false)
  const risk = RISK_STYLES[opinion.risk] || RISK_STYLES.medium
  const hasDetail = opinion.key_points?.length || opinion.cautions?.length || opinion.citations?.length

  return (
    <div className="relative rounded-xl border border-slate-200 bg-white overflow-hidden">
      <span className={`absolute inset-y-0 left-0 w-1 ${risk.bar}`} />
      <div className="pl-4 pr-3.5 py-3">
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <span className="text-[12px] font-semibold text-slate-500">{opinion.label} 관점</span>
          <span className={`inline-flex px-1.5 py-0.5 rounded text-[10.5px] font-medium ring-1 ring-inset ${risk.badge}`}>
            {risk.label}
          </span>
        </div>
        <p className="text-[15px] font-bold text-slate-900 leading-snug">{opinion.verdict}</p>
        <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{stripRefs(opinion.conclusion)}</p>

        {hasDetail ? (
          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="mt-2 inline-flex items-center gap-0.5 text-[12px] font-medium text-slate-500 hover:text-slate-800"
          >
            {open ? '근거 접기' : '근거 보기'}
            {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        ) : null}

        {open && (
          <div className="mt-2 space-y-2">
            {opinion.key_points?.length > 0 && (
              <ul className="space-y-1">
                {opinion.key_points.map((p) => (
                  <li key={p} className="flex gap-1.5 text-[12.5px] leading-relaxed text-slate-700">
                    <span className="mt-[7px] w-1 h-1 rounded-full bg-slate-400 flex-shrink-0" />
                    {stripRefs(p)}
                  </li>
                ))}
              </ul>
            )}
            {opinion.cautions?.length > 0 && (
              <ul className="space-y-1">
                {opinion.cautions.map((c) => (
                  <li key={c} className="flex gap-1.5 text-[12.5px] leading-relaxed text-amber-800">
                    <AlertTriangle className="w-3.5 h-3.5 mt-[3px] flex-shrink-0" />
                    {stripRefs(c)}
                  </li>
                ))}
              </ul>
            )}
            {opinion.citations?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {opinion.citations.map((c) => (
                  <span key={c} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-100 text-[11px] text-slate-600">
                    <Scale className="w-3 h-3" />
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function PendingCard({ label }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-[12px] font-semibold text-slate-500 mb-2">{label} 관점</p>
      <div className="space-y-2">
        <div className="h-4 w-1/3 rounded bg-slate-100 animate-pulse" />
        <div className="h-3 w-full rounded bg-slate-100 animate-pulse" />
        <div className="h-3 w-4/5 rounded bg-slate-100 animate-pulse" />
      </div>
    </div>
  )
}

/**
 * 분야별 검토 의견 카드
 *
 * @param {Array} opinions - answer_meta.perspectives
 * @param {string[]} pendingLabels - 검토 중인 분야 이름 (의견 도착 전 자리 표시)
 */
export default function PerspectivesPanel({ opinions, pendingLabels = [] }) {
  const items = opinions || []
  if (!items.length && !pendingLabels.length) return null
  const count = items.length || pendingLabels.length
  const cols = count >= 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2'

  return (
    <section className="mb-3">
      <p className="flex items-center gap-1.5 mb-2 text-[12.5px] font-medium text-slate-500">
        <GitCompareArrows className="w-3.5 h-3.5 text-primary-600" />
        분야별 검토
        <span className="text-slate-400">
          · {count}개 분야의 의견을 따로 검토한 뒤 대조했습니다
        </span>
      </p>
      <div className={`grid gap-2 ${cols}`}>
        {items.length
          ? items.map((o) => <OpinionCard key={o.domain} opinion={o} />)
          : pendingLabels.map((label) => <PendingCard key={label} label={label} />)}
      </div>
    </section>
  )
}
