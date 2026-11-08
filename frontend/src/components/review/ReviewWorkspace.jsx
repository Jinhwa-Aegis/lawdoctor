import { useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, ArrowLeft, ChevronDown, ChevronUp, FileDown, Printer, MapPinOff, FileText,
} from 'lucide-react'
import ContractViewer from './ContractViewer'
import CitationVerificationPanel from '../CitationVerificationPanel'
import RiskReport, {
  RISK_CONFIGS, IMPORTANCE_LABELS, RiskBadge, RiskScore, CopyButton, ClauseDiff, ChecklistSection,
} from '../RiskReport'
import { downloadWord, printAnswer } from '../../utils/exportAnswer'

const LEVEL_RANK = { high: 3, medium: 2, low: 1 }

const REVIEW_DISCLAIMER =
  '본 분석 결과는 AI 기반 자동 검토로 참고용 정보입니다. 계약 체결 전에는 반드시 법무 담당자 또는 외부 변호사의 검토를 받으시기 바랍니다.'

/** 위험 점수 높은 순 (점수 없으면 위험도 순) */
function sortRisks(items) {
  return [...items].sort((a, b) => {
    const sa = a.risk_score ?? (LEVEL_RANK[a.risk_level] ?? 2) * 30
    const sb = b.risk_score ?? (LEVEL_RANK[b.risk_level] ?? 2) * 30
    return sb - sa
  })
}

function SummaryStat({ label, value, tone = 'slate' }) {
  const tones = {
    red: 'text-red-600',
    amber: 'text-amber-600',
    slate: 'text-slate-900',
  }
  return (
    <div className="flex-1 min-w-0 rounded-xl bg-slate-50 px-3 py-2.5">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className={`text-[18px] font-bold leading-tight mt-0.5 ${tones[tone]}`}>{value}</p>
    </div>
  )
}

function RiskCard({ risk, index, selected, onSelect }) {
  const level = risk.risk_level || risk.severity
  const cfg = RISK_CONFIGS[level] || RISK_CONFIGS.medium
  const located = Number.isInteger(risk.span_start)
  const suggestion = risk.recommendation || risk.suggestion
  const ref = useRef(null)

  return (
    <li
      ref={ref}
      className={`rounded-xl border bg-white transition-all ${
        selected ? 'border-primary-300 shadow-md ring-1 ring-primary-200' : 'border-slate-200 hover:border-slate-300'
      }`}
    >
      <button type="button" onClick={() => onSelect(selected ? null : index)} className="w-full text-left px-4 py-3">
        <div className="flex items-start gap-2.5">
          <span className="flex-shrink-0 mt-0.5 min-w-[20px] h-5 px-1 rounded bg-slate-800 text-white text-[11px] font-semibold flex items-center justify-center">
            {index + 1}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[14px] font-semibold text-slate-900 truncate">{risk.clause}</p>
              <span className="flex items-center gap-1.5 flex-shrink-0">
                {risk.risk_score != null && (
                  <span className={`text-[12px] font-bold ${cfg.iconColor}`}>{risk.risk_score}</span>
                )}
                <span className={`inline-block px-1.5 py-0.5 rounded text-[11px] font-medium border ${cfg.color}`}>{cfg.label}</span>
              </span>
            </div>
            <p className={`text-[12.5px] text-slate-600 mt-1 ${selected ? '' : 'line-clamp-2'}`}>{risk.description}</p>
            {!located && (
              <p className="mt-1 inline-flex items-center gap-1 text-[11px] text-slate-400">
                <MapPinOff className="w-3 h-3" />
                원문에서 위치를 찾지 못했습니다
              </p>
            )}
          </div>
          {selected ? <ChevronUp className="w-4 h-4 text-slate-400 mt-0.5" /> : <ChevronDown className="w-4 h-4 text-slate-400 mt-0.5" />}
        </div>
      </button>

      {selected && (
        <div className="px-4 pb-4 pl-[46px]">
          <RiskScore score={risk.risk_score} level={level} />
          {(risk.original_text || risk.revised_text) && (
            <ClauseDiff original={risk.original_text} revised={risk.revised_text} stacked />
          )}
          {risk.legal_basis && (
            <p className="mb-2 text-[12px] text-slate-500">
              <span className="font-medium text-slate-700">근거 법령</span> · {risk.legal_basis}
            </p>
          )}
          {suggestion && (
            <div className="p-3 bg-primary-50/60 rounded-lg border border-primary-100">
              <p className="text-[11.5px] font-semibold text-primary-800 mb-0.5">협상 포인트</p>
              <p className="text-[13px] text-slate-700">{suggestion}</p>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

function MissingList({ items }) {
  if (!items?.length) return <p className="text-sm text-slate-400 py-6 text-center">추가를 권장하는 조항이 없습니다.</p>
  return (
    <ul className="space-y-2.5">
      {items.map((clause, i) => (
        <li key={i} className="rounded-xl border border-orange-200 bg-orange-50/60 p-4">
          <div className="flex items-center justify-between gap-2 mb-1">
            <p className="text-[14px] font-semibold text-slate-900">{clause.name || clause.clause_name}</p>
            {clause.importance && (
              <span className="text-[11px] text-slate-500">중요도 {IMPORTANCE_LABELS[clause.importance] || clause.importance}</span>
            )}
          </div>
          <p className="text-[12.5px] text-slate-600">{clause.description}</p>
          {clause.suggested_text && (
            <div className="mt-3 p-3 bg-white rounded-lg border border-orange-100">
              <div className="flex items-center justify-between mb-1">
                <p className="text-[11.5px] font-medium text-slate-600">추가 조문안</p>
                <CopyButton text={clause.suggested_text} />
              </div>
              <p className="text-[13px] text-slate-800 whitespace-pre-wrap">{clause.suggested_text}</p>
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}

/**
 * 계약서 리뷰 결과 작업 화면 — 왼쪽 원문(위험 조항 강조) + 오른쪽 분석 패널
 */
export default function ReviewWorkspace({ result, onReset }) {
  const risks = useMemo(() => sortRisks(result.risk_items || result.risks || []), [result])
  const [selected, setSelected] = useState(null)
  const [tab, setTab] = useState('risks')
  const reportRef = useRef(null)

  const counts = risks.reduce((acc, r) => {
    const lv = r.risk_level || r.severity
    acc[lv] = (acc[lv] || 0) + 1
    return acc
  }, {})
  const checklist = result.checklist_results || []
  const missingChecks = checklist.filter((c) => c.status === 'missing').length
  const maxScore = risks.reduce((m, r) => Math.max(m, r.risk_score ?? 0), 0)

  const handleSelect = (idx) => {
    setSelected(idx)
    if (idx != null) setTab('risks')
  }

  const exportPayload = () => ({
    title: `계약서 검토 - ${result.file_name || result.contract_type || '계약서'}`,
    question: '',
    answerHtml: reportRef.current?.innerHTML || '',
    disclaimer: REVIEW_DISCLAIMER,
  })

  const tabs = [
    { key: 'risks', label: '리스크', count: risks.length },
    { key: 'checklist', label: '점검표', count: checklist.length },
    { key: 'missing', label: '추가 권장 조항', count: (result.missing_clauses || []).length },
    { key: 'opinion', label: '종합 의견' },
  ]

  return (
    <div className="h-full flex flex-col">
      {/* 상단 바 */}
      <header className="h-14 flex-shrink-0 flex items-center justify-between gap-4 px-4 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg text-[13px] text-slate-500 hover:bg-slate-100 hover:text-slate-800"
          >
            <ArrowLeft className="w-4 h-4" />
            새 계약서
          </button>
          <span className="w-px h-5 bg-slate-200" />
          <FileText className="w-4 h-4 text-slate-400 flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-[14px] font-semibold text-slate-900 truncate">{result.file_name || '계약서'}</p>
            <p className="text-[11.5px] text-slate-500 truncate">
              {result.contract_type}
              {result.our_position && <> · 당사 지위 <strong className="text-slate-700">{result.our_position}</strong></>}
              {result.checklist_label && <> · 점검표 {result.checklist_label}{result.checklist_auto_detected ? '(자동 감지)' : ''}</>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <RiskBadge level={result.overall_risk_level || result.overall_risk} />
          <span className="w-px h-5 bg-slate-200 mx-1" />
          <button
            type="button"
            onClick={() => downloadWord(exportPayload())}
            className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg text-[12.5px] text-slate-600 hover:bg-slate-100"
          >
            <FileDown className="w-4 h-4" />
            Word
          </button>
          <button
            type="button"
            onClick={() => printAnswer(exportPayload())}
            className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg text-[12.5px] text-slate-600 hover:bg-slate-100"
          >
            <Printer className="w-4 h-4" />
            인쇄·PDF
          </button>
        </div>
      </header>

      <div className="flex-1 min-h-0 grid grid-cols-[minmax(0,1.15fr)_minmax(400px,0.85fr)]">
        {/* 왼쪽: 원문 */}
        <div className="min-h-0 bg-slate-100/70 border-r border-slate-200">
          <ContractViewer
            text={result.contract_text}
            risks={risks}
            selectedIndex={selected}
            onSelect={handleSelect}
          />
        </div>

        {/* 오른쪽: 분석 */}
        <div className="min-h-0 flex flex-col bg-white">
          <div className="px-5 pt-4 pb-3 border-b border-slate-100 flex-shrink-0">
            {result.summary && <p className="text-[13.5px] leading-relaxed text-slate-700 mb-3">{result.summary}</p>}
            <div className="flex gap-2">
              <SummaryStat label="높음 리스크" value={`${counts.high || 0}건`} tone={counts.high ? 'red' : 'slate'} />
              <SummaryStat label="보통·낮음" value={`${(counts.medium || 0) + (counts.low || 0)}건`} />
              <SummaryStat label="점검표 누락 판정" value={`${missingChecks}건`} tone={missingChecks ? 'amber' : 'slate'} />
              <SummaryStat label="최고 위험 점수" value={maxScore || '-'} tone={maxScore >= 80 ? 'red' : 'slate'} />
            </div>
          </div>

          <nav className="flex gap-1 px-4 border-b border-slate-200 flex-shrink-0">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={`relative h-10 px-3 text-[13px] font-medium transition-colors ${
                  tab === t.key ? 'text-primary-700' : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {t.label}
                {t.count != null && <span className="ml-1 text-[11px] text-slate-400">{t.count}</span>}
                {tab === t.key && <span className="absolute left-2 right-2 -bottom-px h-0.5 rounded bg-primary-600" />}
              </button>
            ))}
          </nav>

          <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin px-4 py-4">
            {tab === 'risks' && (
              risks.length ? (
                <ul className="space-y-2.5">
                  {risks.map((risk, idx) => (
                    <RiskCard key={idx} risk={risk} index={idx} selected={selected === idx} onSelect={handleSelect} />
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-400 py-6 text-center">발견된 리스크가 없습니다.</p>
              )
            )}
            {tab === 'checklist' && (
              <div className="-mx-6 -my-6 [&_h3]:text-[15px]">
                <ChecklistSection result={result} />
              </div>
            )}
            {tab === 'missing' && <MissingList items={result.missing_clauses} />}
            {tab === 'opinion' && (
              <div>
                <p className="text-[14px] leading-7 text-slate-700 whitespace-pre-wrap">
                  {result.overall_opinion || result.recommendation || '종합 의견이 없습니다.'}
                </p>
                <CitationVerificationPanel items={result.verified_citations} />
              </div>
            )}
          </div>

          <p className="flex-shrink-0 flex items-start gap-1.5 mx-4 mb-3 mt-1 rounded-lg bg-amber-50/70 border border-amber-100 px-3 py-2 text-[11px] leading-relaxed text-amber-800">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-[1px]" />
            {REVIEW_DISCLAIMER}
          </p>
        </div>
      </div>

      {/* 내보내기용 전체 보고서 (화면에는 보이지 않음) */}
      <div ref={reportRef} className="hidden" aria-hidden="true">
        <RiskReport result={result} />
      </div>
    </div>
  )
}

