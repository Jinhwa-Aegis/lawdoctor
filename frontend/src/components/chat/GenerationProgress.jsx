import { Check, Loader2 } from 'lucide-react'

/**
 * 답변 생성 진행 단계 표시
 *
 * stage: 'searching' (질문 분석·법령 검색) → 'writing' (답변 작성) → 'verifying' (인용 법령 검증)
 */
const DEFAULT_STEPS = [
  { key: 'searching', label: '법령·자문 이력 검색' },
  { key: 'writing', label: '답변 작성' },
  { key: 'verifying', label: '인용 법령 검증' },
]

export default function GenerationProgress({ stage, steps = DEFAULT_STEPS }) {
  if (!stage) return null
  const currentIdx = steps.findIndex((s) => s.key === stage)

  return (
    <ol className="flex items-center gap-1.5 text-[12px]" aria-label="답변 생성 진행 상태">
      {steps.map((step, idx) => {
        const done = idx < currentIdx
        const active = idx === currentIdx
        return (
          <li key={step.key} className="flex items-center gap-1.5">
            {idx > 0 && <span className={`w-4 h-px ${done || active ? 'bg-primary-300' : 'bg-slate-200'}`} />}
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${
                active
                  ? 'bg-primary-50 text-primary-700 font-medium'
                  : done
                    ? 'text-slate-500'
                    : 'text-slate-300'
              }`}
            >
              {done ? (
                <Check className="w-3 h-3" />
              ) : active ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
              )}
              {step.label}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
