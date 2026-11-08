import { useEffect, useState } from 'react'
import {
  AlertTriangle, BarChart3, FileWarning, MessageSquare, MessagesSquare, ThumbsDown, ThumbsUp, Users,
} from 'lucide-react'
import { getFeedbackStats, getRecentFeedback } from '../../api/client'
import { Card, EmptyState, Notice, Spinner } from './AdminUI'

export const FEEDBACK_REASON_LABELS = {
  inaccurate: '부정확',
  insufficient_evidence: '근거 부족',
  irrelevant: '관련 없는 답변',
  helpful: '도움됨',
  other: '기타',
}

const CONFIDENCE_LABELS = { high: '신뢰도 높음', medium: '신뢰도 보통', low: '신뢰도 낮음' }

function Kpi({ icon: Icon, label, value, sub, tone = 'default' }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3.5">
      <p className="flex items-center gap-1.5 text-[12px] text-slate-500">
        <Icon className="w-3.5 h-3.5" />
        {label}
      </p>
      <p className={`mt-1 text-[24px] font-bold leading-tight tabular-nums ${tone === 'warn' && value > 0 ? 'text-amber-600' : 'text-slate-900'}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-[11.5px] text-slate-400">{sub}</p>}
    </div>
  )
}

/** 일별 질문 수 막대 그래프 (단일 계열 — 범례 없이 제목으로 설명) */
function DailyQuestionsChart({ data }) {
  const [hover, setHover] = useState(null)
  const max = Math.max(1, ...data.map((d) => d.count))
  const total = data.reduce((s, d) => s + d.count, 0)
  const fmt = (iso) => {
    const [, m, d] = iso.split('-')
    return `${Number(m)}/${Number(d)}`
  }

  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <p className="text-[12.5px] text-slate-500">
          최근 {data.length}일 질문 <span className="font-semibold text-slate-900 tabular-nums">{total}</span>건
        </p>
        <p className="text-[12px] text-slate-500 tabular-nums h-4">
          {hover != null && `${fmt(data[hover].date)} · ${data[hover].count}건`}
        </p>
      </div>
      <div className="relative h-36 pl-7">
        {/* 최댓값 보조선(점선)과 기준선 — 눈금 숫자는 왼쪽 여백에 */}
        <span className="absolute left-0 -top-1.5 text-[10.5px] text-slate-400 tabular-nums">{max}</span>
        <span className="absolute left-0 -bottom-1.5 text-[10.5px] text-slate-400">0</span>
        <div className="absolute left-7 right-0 top-0 border-t border-dashed border-slate-200" />
        <div className="absolute left-7 right-0 bottom-0 border-t border-slate-200" />
        <div className="absolute left-7 right-0 inset-y-0 flex items-end gap-[2px]">
          {data.map((d, i) => (
            <div
              key={d.date}
              className="flex-1 h-full flex items-end cursor-default"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              title={`${fmt(d.date)} 질문 ${d.count}건`}
            >
              <div
                className={`w-full rounded-t-[4px] transition-colors ${hover === i ? 'bg-primary-700' : 'bg-primary-500'}`}
                style={{ height: d.count ? `${Math.max(3, (d.count / max) * 100)}%` : 0 }}
              />
            </div>
          ))}
        </div>
      </div>
      <div className="mt-1.5 ml-7 flex justify-between text-[10.5px] text-slate-400 tabular-nums">
        <span>{fmt(data[0].date)}</span>
        <span>{fmt(data[data.length - 1].date)}</span>
      </div>
    </div>
  )
}

function FeedbackSummary({ stats }) {
  if (!stats || stats.total === 0) {
    return <EmptyState icon={ThumbsUp} title="아직 피드백이 없습니다">답변 아래의 도움됨·아쉬움 버튼으로 쌓입니다.</EmptyState>
  }
  const posPct = Math.round((stats.positive / stats.total) * 100)
  const maxReason = Math.max(1, ...stats.top_negative_reasons.map((r) => r.count))
  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-baseline justify-between">
          <p className="text-[24px] font-bold text-slate-900 tabular-nums">{stats.positive_ratio}%</p>
          <p className="text-[12px] text-slate-500 tabular-nums">총 {stats.total}건</p>
        </div>
        <p className="text-[12px] text-slate-500">긍정 비율</p>
        <div className="mt-2 flex h-2 gap-[2px] overflow-hidden rounded-full">
          {stats.positive > 0 && <div className="bg-emerald-500" style={{ width: `${posPct}%` }} />}
          {stats.negative > 0 && <div className="bg-red-400" style={{ width: `${100 - posPct}%` }} />}
        </div>
        <div className="mt-1.5 flex justify-between text-[11.5px] text-slate-600">
          <span className="inline-flex items-center gap-1"><ThumbsUp className="w-3 h-3 text-emerald-600" />도움됨 {stats.positive}</span>
          <span className="inline-flex items-center gap-1"><ThumbsDown className="w-3 h-3 text-red-500" />아쉬움 {stats.negative}</span>
        </div>
      </div>
      {stats.top_negative_reasons.length > 0 && (
        <div>
          <p className="text-[12px] font-medium text-slate-700 mb-2">아쉬움 사유</p>
          <ul className="space-y-1.5">
            {stats.top_negative_reasons.map((r) => (
              <li key={r.reason} className="grid grid-cols-[88px_1fr_28px] items-center gap-2 text-[12px]">
                <span className="text-slate-600 truncate">{FEEDBACK_REASON_LABELS[r.reason] || r.reason}</span>
                <span className="h-1.5 rounded-full bg-slate-100">
                  <span className="block h-full rounded-full bg-slate-400" style={{ width: `${(r.count / maxReason) * 100}%` }} />
                </span>
                <span className="text-right text-slate-700 tabular-nums">{r.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function RecentNegativeFeedback({ items }) {
  if (items.length === 0) {
    return <EmptyState icon={MessagesSquare} title="아쉬움 피드백이 없습니다">사용자가 아쉬움을 남긴 답변이 여기에 모입니다.</EmptyState>
  }
  return (
    <ul className="divide-y divide-slate-100">
      {items.map((it) => (
        <li key={it.id} className="py-3.5 first:pt-0 last:pb-0">
          <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
            <span className="rounded-md bg-red-50 px-1.5 py-0.5 font-medium text-red-700">
              {FEEDBACK_REASON_LABELS[it.reason] || '사유 없음'}
            </span>
            {it.confidence && (
              <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-slate-600">{CONFIDENCE_LABELS[it.confidence]}</span>
            )}
            {it.citation_issues > 0 && (
              <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-1.5 py-0.5 text-amber-700">
                <FileWarning className="w-3 h-3" />
                인용 문제 {it.citation_issues}건
              </span>
            )}
            <span className="ml-auto text-slate-400">
              {it.user_name} · {new Date(it.created_at).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
          <p className="mt-2 text-[13px] font-medium text-slate-900 line-clamp-2">Q. {it.question || '(질문을 찾지 못했습니다)'}</p>
          <p className="mt-1 text-[12.5px] text-slate-500 line-clamp-2">{it.answer_excerpt}</p>
          {it.comment && (
            <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-[12.5px] text-slate-700">“{it.comment}”</p>
          )}
        </li>
      ))}
    </ul>
  )
}

export default function OverviewTab({ dashboard }) {
  const [feedbackStats, setFeedbackStats] = useState(null)
  const [recent, setRecent] = useState(null)
  const [error, setError] = useState(null)
  const days = dashboard?.daily_questions?.length || 14

  useEffect(() => {
    Promise.all([getFeedbackStats(days), getRecentFeedback('negative', 10)])
      .then(([s, r]) => {
        setFeedbackStats(s)
        setRecent(r)
      })
      .catch((e) => setError(e.message))
  }, [days])

  if (!dashboard) return <Spinner />

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Kpi icon={Users} label="사용자" value={dashboard.total_users} />
        <Kpi icon={MessageSquare} label="누적 대화" value={dashboard.total_sessions} sub={`메시지 ${dashboard.total_messages}건`} />
        <Kpi icon={ThumbsUp} label="누적 긍정 비율" value={`${dashboard.positive_feedback_ratio}%`} sub={`피드백 ${dashboard.total_feedbacks}건`} />
        <Kpi
          icon={FileWarning}
          label="인용 문제 답변"
          value={dashboard.citation_issue_answers}
          sub={`최근 ${days}일 답변 ${dashboard.recent_answers}건 중`}
          tone="warn"
        />
        <Kpi
          icon={AlertTriangle}
          label="신뢰도 낮은 답변"
          value={dashboard.low_confidence_answers}
          sub={`최근 ${days}일`}
          tone="warn"
        />
      </div>

      {error && <Notice tone="error" title="피드백 정보를 불러오지 못했습니다">{error}</Notice>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card title="사용량" icon={BarChart3} className="lg:col-span-2">
          {dashboard.daily_questions?.length ? (
            <DailyQuestionsChart data={dashboard.daily_questions} />
          ) : (
            <EmptyState icon={BarChart3} title="집계할 질문이 없습니다" />
          )}
        </Card>
        <Card title="답변 만족도" description={`최근 ${days}일`} icon={ThumbsUp}>
          {feedbackStats ? <FeedbackSummary stats={feedbackStats} /> : <Spinner />}
        </Card>
      </div>

      <Card
        title="점검이 필요한 답변"
        description="사용자가 아쉬움을 남긴 최근 답변입니다. 질문 유형이 반복되면 자료 보강을 검토하세요."
        icon={ThumbsDown}
      >
        {recent ? <RecentNegativeFeedback items={recent} /> : <Spinner />}
      </Card>
    </div>
  )
}
