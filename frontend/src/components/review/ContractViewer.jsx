import { useEffect, useMemo, useRef } from 'react'
import { FileText } from 'lucide-react'

const LEVEL_RANK = { high: 3, medium: 2, low: 1 }

const HIGHLIGHT_STYLES = {
  high: 'bg-red-100/80 decoration-red-400',
  medium: 'bg-amber-100/80 decoration-amber-400',
  low: 'bg-emerald-50 decoration-emerald-400',
}

/**
 * 위험 조항 위치(span)로 원문을 구간으로 나눈다.
 * 겹치는 구간은 가장 높은 위험 수준의 항목에 속한 것으로 본다.
 *
 * @returns {Array<{text: string, risk: {index, level} | null, isStart: boolean}>}
 */
export function buildSegments(text, risks) {
  const located = risks
    .map((r, index) => ({ index, level: r.risk_level || r.severity, start: r.span_start, end: r.span_end }))
    .filter((r) => Number.isInteger(r.start) && Number.isInteger(r.end) && r.end > r.start && r.start < text.length)

  if (!located.length) return [{ text, risk: null, isStart: false }]

  const bounds = new Set([0, text.length])
  located.forEach((r) => { bounds.add(r.start); bounds.add(Math.min(r.end, text.length)) })
  const points = [...bounds].sort((a, b) => a - b)

  const segments = []
  const started = new Set()
  for (let i = 0; i < points.length - 1; i++) {
    const [s, e] = [points[i], points[i + 1]]
    if (s === e) continue
    const covering = located.filter((r) => r.start <= s && r.end >= e)
    const top = covering.sort((a, b) => (LEVEL_RANK[b.level] || 0) - (LEVEL_RANK[a.level] || 0))[0] || null
    const isStart = Boolean(top && !started.has(top.index))
    if (top) started.add(top.index)
    segments.push({ text: text.slice(s, e), risk: top ? { index: top.index, level: top.level } : null, isStart })
  }
  return segments
}

/**
 * 계약서 원문 뷰어 — 위험 조항을 원문 위에 강조하고, 클릭하면 해당 리스크를 선택한다.
 */
export default function ContractViewer({ text, risks, selectedIndex, onSelect }) {
  const containerRef = useRef(null)
  const segments = useMemo(() => buildSegments(text || '', risks || []), [text, risks])
  const locatedCount = (risks || []).filter((r) => Number.isInteger(r.span_start)).length

  // 오른쪽에서 리스크를 고르면 원문의 해당 위치로 스크롤
  useEffect(() => {
    if (selectedIndex == null) return
    const el = containerRef.current?.querySelector(`[data-risk-start="${selectedIndex}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [selectedIndex])

  if (!text) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-slate-400">
        계약서 원문을 표시할 수 없습니다.
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-6 h-11 border-b border-slate-200 bg-white/70 text-[12px] text-slate-500 flex-shrink-0">
        <span className="inline-flex items-center gap-1.5 font-medium text-slate-700">
          <FileText className="w-3.5 h-3.5" />
          계약서 원문
        </span>
        <span className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-red-200" />높음</span>
          <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-amber-200" />보통</span>
          <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-100" />낮음</span>
          <span className="text-slate-400">· 원문 위치 확인 {locatedCount}/{(risks || []).length}건</span>
        </span>
      </div>

      <div ref={containerRef} className="flex-1 overflow-y-auto scrollbar-thin px-6 py-6">
        <article className="max-w-[720px] mx-auto bg-white rounded-xl border border-slate-200 shadow-sm px-10 py-10 text-[14.5px] leading-8 text-slate-800 whitespace-pre-wrap break-words">
          {segments.map((seg, i) => {
            if (!seg.risk) return <span key={i}>{seg.text}</span>
            const selected = seg.risk.index === selectedIndex
            return (
              <mark
                key={i}
                data-risk-start={seg.isStart ? seg.risk.index : undefined}
                onClick={() => onSelect(seg.risk.index)}
                className={`cursor-pointer rounded-[3px] px-0.5 underline decoration-2 underline-offset-4 text-inherit transition-shadow ${
                  HIGHLIGHT_STYLES[seg.risk.level] || HIGHLIGHT_STYLES.medium
                } ${selected ? 'ring-2 ring-primary-400 ring-offset-1' : 'hover:ring-1 hover:ring-slate-300'}`}
              >
                {seg.isStart && (
                  <sup className="mr-0.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded bg-slate-800 text-white text-[10px] font-semibold not-italic no-underline align-[3px]">
                    {seg.risk.index + 1}
                  </sup>
                )}
                {seg.text}
              </mark>
            )
          })}
        </article>
      </div>
    </div>
  )
}
