import React, { useState } from 'react';
import {
  AlertTriangle, Shield, FileText, CheckCircle, ClipboardCheck, XCircle, MinusCircle, ArrowRight, Copy, Check,
} from 'lucide-react';
import CitationVerificationPanel from './CitationVerificationPanel';

// ---------------------------------------------------------------------------
// 공통 표시 설정
// ---------------------------------------------------------------------------

const RISK_CONFIGS = {
  high: { label: '높음', color: 'bg-red-100 text-red-800 border-red-200', bar: 'bg-red-500', icon: AlertTriangle, iconColor: 'text-red-600' },
  medium: { label: '보통', color: 'bg-yellow-100 text-yellow-800 border-yellow-200', bar: 'bg-yellow-500', icon: AlertTriangle, iconColor: 'text-yellow-600' },
  low: { label: '낮음', color: 'bg-green-100 text-green-800 border-green-200', bar: 'bg-green-500', icon: CheckCircle, iconColor: 'text-green-600' },
};

const CHECK_STATUS = {
  ok: { label: '충족', icon: CheckCircle, color: 'text-green-700 bg-green-50 border-green-200' },
  risk: { label: '리스크', icon: AlertTriangle, color: 'text-yellow-800 bg-yellow-50 border-yellow-200' },
  missing: { label: '누락', icon: XCircle, color: 'text-red-700 bg-red-50 border-red-200' },
  na: { label: '해당 없음', icon: MinusCircle, color: 'text-gray-600 bg-gray-50 border-gray-200' },
};

const IMPORTANCE_LABELS = { high: '높음', medium: '보통', low: '낮음' };

function RiskBadge({ level }) {
  const cfg = RISK_CONFIGS[level] || RISK_CONFIGS.medium;
  return (
    <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium border ${cfg.color}`}>
      <Shield size={14} />
      {cfg.label}
    </span>
  );
}

/** 위험 점수(0~100) 막대 */
function RiskScore({ score, level }) {
  if (score === null || score === undefined) return null;
  const value = Math.max(0, Math.min(100, Number(score)));
  const cfg = RISK_CONFIGS[level] || RISK_CONFIGS.medium;
  return (
    <div className="flex items-center gap-2 mb-3" title="80 이상: 체결 전 반드시 수정 · 50~79: 수정 협상 권장">
      <span className="text-xs text-gray-500 w-14 flex-shrink-0">위험 점수</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${cfg.bar}`} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs font-semibold text-gray-800 w-8 text-right">{value}</span>
    </div>
  );
}

/** 수정안 복사 버튼 */
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 클립보드 권한이 없는 환경 — 무시
    }
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center gap-1 text-xs text-blue-700 hover:text-blue-900"
      title="수정안 복사"
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {copied ? '복사됨' : '복사'}
    </button>
  );
}

/** 원문 vs 수정안 나란히 보기 */
/** stacked: 좁은 패널에서 원문·수정안을 위아래로 배치 */
function ClauseDiff({ original, revised, stacked = false }) {
  if (!original && !revised) return null;
  return (
    <div className={`grid gap-2 items-stretch mb-3 ${stacked ? 'grid-cols-1 [&>div:nth-child(2)]:hidden' : 'md:grid-cols-[1fr_auto_1fr]'}`}>
      <div className="p-3 bg-red-50/60 rounded border border-red-100">
        <p className="text-xs font-medium text-red-800 mb-1">계약서 원문</p>
        <p className="text-sm text-gray-800 whitespace-pre-wrap">{original || '—'}</p>
      </div>
      <div className="hidden md:flex items-center text-gray-400">
        <ArrowRight size={16} />
      </div>
      <div className="p-3 bg-green-50/60 rounded border border-green-100">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs font-medium text-green-800">수정 조문안</p>
          {revised && <CopyButton text={revised} />}
        </div>
        <p className="text-sm text-gray-800 whitespace-pre-wrap">{revised || '—'}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 필수 점검표
// ---------------------------------------------------------------------------

function ChecklistSection({ result }) {
  const items = result.checklist_results || [];
  if (!items.length) return null;

  const counts = items.reduce((acc, it) => ({ ...acc, [it.status]: (acc[it.status] || 0) + 1 }), {});

  return (
    <div className="p-6 border-b border-gray-200">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
        <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
          <ClipboardCheck size={20} className="text-blue-600" />
          필수 점검표
          <span className="text-sm font-normal text-gray-500">
            {result.checklist_label}
            {result.checklist_auto_detected ? ' (자동 감지)' : ''}
          </span>
        </h3>
        <div className="flex gap-1.5 text-xs">
          {['missing', 'risk', 'ok', 'na'].map((st) => counts[st] ? (
            <span key={st} className={`px-2 py-0.5 rounded-full border ${CHECK_STATUS[st].color}`}>
              {CHECK_STATUS[st].label} {counts[st]}
            </span>
          ) : null)}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b border-gray-200">
              <th className="py-2 pr-3 font-medium w-24">판정</th>
              <th className="py-2 pr-3 font-medium">점검 항목</th>
              <th className="py-2 pr-3 font-medium">판단 근거</th>
              <th className="py-2 font-medium w-24">관련 조항</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => {
              const cfg = CHECK_STATUS[it.status] || CHECK_STATUS.na;
              const Icon = cfg.icon;
              return (
                <tr key={it.item_id} className="border-b border-gray-100 align-top">
                  <td className="py-2 pr-3">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs ${cfg.color}`}>
                      <Icon size={12} />
                      {cfg.label}
                    </span>
                  </td>
                  <td className="py-2 pr-3">
                    <p className="font-medium text-gray-900">{it.name || it.item_id}</p>
                    {it.legal_basis && <p className="text-xs text-gray-400 mt-0.5">{it.legal_basis}</p>}
                  </td>
                  <td className="py-2 pr-3 text-gray-700">
                    {it.comment}
                    {it.auto_adjusted && (
                      <span
                        className="ml-1 text-[11px] text-yellow-700"
                        title="AI가 '충족'으로 판정했으나 판단 근거에 불리한 내용이 있어 '리스크'로 보정했습니다."
                      >
                        (자동 보정)
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-gray-600">{it.clause_ref || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RiskReport 메인
// ---------------------------------------------------------------------------

const RiskReport = ({ result }) => {
  if (!result) return null;

  // 위험 점수 높은 순 정렬 (점수 없으면 위험도 순)
  const levelRank = { high: 3, medium: 2, low: 1 };
  const risks = [...(result.risks || result.risk_items || [])].sort((a, b) => {
    const sa = a.risk_score ?? (levelRank[a.severity || a.risk_level] ?? 2) * 30;
    const sb = b.risk_score ?? (levelRank[b.severity || b.risk_level] ?? 2) * 30;
    return sb - sa;
  });

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      {/* 헤더 */}
      <div className="p-6 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">계약서 분석 결과</h2>
            <p className="text-sm text-gray-600 mt-1">
              {result.contract_type || '일반 계약서'}
              {result.our_position && (
                <span className="ml-2 text-gray-500">· 당사 지위: <strong className="text-gray-800">{result.our_position}</strong></span>
              )}
            </p>
          </div>
          <RiskBadge level={result.overall_risk_level || result.overall_risk} />
        </div>
      </div>

      {/* 요약 */}
      {result.summary && (
        <div className="p-6 border-b border-gray-200 bg-blue-50">
          <h3 className="text-lg font-semibold text-gray-900 mb-2">요약</h3>
          <p className="text-gray-700 whitespace-pre-wrap">{result.summary}</p>
        </div>
      )}

      {/* 필수 점검표 */}
      <ChecklistSection result={result} />

      {/* 리스크 항목 */}
      {risks.length > 0 && (
        <div className="p-6 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <AlertTriangle size={20} className="text-red-600" />
            발견된 리스크 ({risks.length}건)
          </h3>
          <div className="space-y-4">
            {risks.map((risk, index) => {
              const level = risk.severity || risk.risk_level;
              const cfg = RISK_CONFIGS[level] || RISK_CONFIGS.medium;
              const Icon = cfg.icon;
              const hasDiff = risk.original_text || risk.revised_text;
              const suggestion = risk.recommendation || risk.suggestion;
              return (
                <div key={index} className="p-4 border border-gray-200 rounded-lg hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-3">
                    <Icon size={20} className={cfg.iconColor} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <h4 className="font-semibold text-gray-900">{risk.clause}</h4>
                        <RiskBadge level={level} />
                      </div>

                      <RiskScore score={risk.risk_score} level={level} />

                      <p className="text-sm text-gray-700 mb-3">{risk.description}</p>

                      {hasDiff && <ClauseDiff original={risk.original_text} revised={risk.revised_text} />}

                      {risk.legal_basis && risk.legal_basis.length > 0 && (
                        <div className="mb-3 p-3 bg-gray-50 rounded">
                          <p className="text-xs font-medium text-gray-700 mb-1">근거 법령</p>
                          {Array.isArray(risk.legal_basis) ? (
                            <ul className="space-y-1">
                              {risk.legal_basis.map((basis, idx) => (
                                <li key={idx} className="text-xs text-gray-600">{basis}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-xs text-gray-600">{risk.legal_basis}</p>
                          )}
                        </div>
                      )}

                      {suggestion && (
                        <div className="p-3 bg-blue-50 rounded border border-blue-200">
                          <p className="text-xs font-medium text-blue-900 mb-1">
                            {hasDiff ? '협상 포인트' : '수정 제안'}
                          </p>
                          <p className="text-sm text-blue-800">{suggestion}</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 누락 조항 */}
      {result.missing_clauses && result.missing_clauses.length > 0 && (
        <div className="p-6 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FileText size={20} className="text-orange-600" />
            누락된 조항 ({result.missing_clauses.length}건)
          </h3>
          <div className="space-y-3">
            {result.missing_clauses.map((clause, index) => (
              <div key={index} className="p-4 border border-orange-200 bg-orange-50 rounded-lg">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <h4 className="font-semibold text-gray-900">{clause.name || clause.clause_name}</h4>
                  {clause.importance && (
                    <span className="text-xs text-gray-600">중요도: {IMPORTANCE_LABELS[clause.importance] || clause.importance}</span>
                  )}
                </div>
                <p className="text-sm text-gray-700">{clause.description}</p>
                {clause.suggested_text && (
                  <div className="mt-3 p-3 bg-white rounded border border-orange-100">
                    <div className="flex items-center justify-between mb-1">
                      <p className="text-xs font-medium text-gray-700">추가 조문 예시</p>
                      <CopyButton text={clause.suggested_text} />
                    </div>
                    <p className="text-sm text-gray-800 whitespace-pre-wrap">{clause.suggested_text}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 근거 법령 인용 검증 */}
      {result.verified_citations?.length > 0 && (
        <div className="px-6 pb-6 border-b border-gray-200">
          <CitationVerificationPanel items={result.verified_citations} />
        </div>
      )}

      {/* 종합 의견 */}
      {(result.overall_opinion || result.recommendation) && (
        <div className="p-6 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">종합 의견</h3>
          <p className="text-gray-700 whitespace-pre-wrap">{result.overall_opinion || result.recommendation}</p>
        </div>
      )}

      {/* 면책 문구 */}
      <div className="p-6 bg-gray-50">
        <div className="flex items-start gap-3">
          <AlertTriangle size={20} className="text-gray-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-gray-900 mb-2">법률 자문 면책</p>
            <p className="text-xs text-gray-600 leading-relaxed">
              본 분석 결과는 AI 기반 자동 검토 시스템에 의한 것으로, 참고용 정보 제공을 목적으로 합니다.
              실제 계약서 체결 전에는 반드시 전문 변호사의 법률 자문을 받으시기 바랍니다.
              본 분석 결과를 신뢰하여 발생한 손해에 대해 당사는 책임을 지지 않습니다.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RiskReport;

// 계약서 리뷰 작업 화면(ReviewWorkspace)에서 재사용
export { RISK_CONFIGS, CHECK_STATUS, IMPORTANCE_LABELS, RiskBadge, RiskScore, CopyButton, ClauseDiff, ChecklistSection };
