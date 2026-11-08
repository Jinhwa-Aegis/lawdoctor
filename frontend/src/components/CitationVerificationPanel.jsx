import { useState } from 'react';
import { CheckCircle2, XCircle, HelpCircle, AlertTriangle, ExternalLink, ShieldCheck } from 'lucide-react';

// ---------------------------------------------------------------------------
// 인용 검증 상태별 표시 설정
// ---------------------------------------------------------------------------

const STATUS_CONFIG = {
  verified: {
    label: '검증됨',
    icon: CheckCircle2,
    chip: 'bg-green-50 text-green-800 border-green-200',
    iconColor: 'text-green-600',
  },
  repealed: {
    label: '삭제된 조문',
    icon: XCircle,
    chip: 'bg-red-50 text-red-800 border-red-200',
    iconColor: 'text-red-600',
  },
  not_found: {
    label: '조문 없음',
    icon: XCircle,
    chip: 'bg-red-50 text-red-800 border-red-200',
    iconColor: 'text-red-600',
  },
  unknown_law: {
    label: '법령 확인 불가',
    icon: HelpCircle,
    chip: 'bg-amber-50 text-amber-800 border-amber-200',
    iconColor: 'text-amber-600',
  },
  unverified: {
    label: '미검증',
    icon: HelpCircle,
    chip: 'bg-gray-50 text-gray-700 border-gray-200',
    iconColor: 'text-gray-500',
  },
};

// 사용자가 반드시 원문을 다시 확인해야 하는 상태
const PROBLEM_STATUSES = new Set(['repealed', 'not_found']);

/** "15의2" → "제15조의2" */
function formatArticle(article) {
  const [main, branch] = String(article || '').split('의');
  return branch ? `제${main}조의${branch}` : `제${main}조`;
}

/** 긴 정식 법령명은 칩에서 줄여 표시 */
function shortLawName(name) {
  return name && name.length > 14 ? `${name.slice(0, 13)}…` : name;
}

function VerificationChip({ item, selected, onClick }) {
  const cfg = STATUS_CONFIG[item.status] || STATUS_CONFIG.unverified;
  const Icon = cfg.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${item.law_name} ${formatArticle(item.article)} — ${cfg.label}`}
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-full border text-xs transition-shadow ${cfg.chip} ${
        selected ? 'ring-2 ring-offset-1 ring-primary-300' : 'hover:shadow-sm'
      }`}
    >
      <Icon size={12} className={cfg.iconColor} />
      <span className="font-medium">{shortLawName(item.law_name)} {formatArticle(item.article)}</span>
      <span className="opacity-70">· {cfg.label}</span>
    </button>
  );
}

function VerificationDetail({ item }) {
  const cfg = STATUS_CONFIG[item.status] || STATUS_CONFIG.unverified;
  const descriptions = {
    verified: '현행 법령에서 해당 조문을 확인했습니다.',
    repealed: '이 조문은 현재 삭제된 상태입니다. 답변에서 이 조문에 근거한 부분은 신뢰하지 마십시오.',
    not_found: '현행 법령에 해당 조문 번호가 없습니다. AI가 잘못 인용했을 가능성이 높습니다.',
    unknown_law: '국가법령정보센터에서 이 법령명을 찾지 못했습니다. 법령명이 부정확하거나 약칭일 수 있습니다.',
    unverified: '일시적인 오류로 확인하지 못했습니다. 원문을 직접 확인하십시오.',
  };

  return (
    <div className="mt-2 p-3 rounded-lg border border-gray-200 bg-gray-50 text-xs">
      <div className="flex items-center justify-between gap-2 mb-1">
        <p className="font-medium text-gray-900">
          {item.law_name} {formatArticle(item.article)}
          {item.article_title && <span className="text-gray-500 font-normal"> ({item.article_title})</span>}
        </p>
        {item.law_url && (
          <a
            href={item.law_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-primary-600 hover:underline flex-shrink-0"
          >
            원문 보기 <ExternalLink size={11} />
          </a>
        )}
      </div>
      <p className={`mb-2 ${cfg.iconColor}`}>{descriptions[item.status] || descriptions.unverified}</p>
      {item.excerpt && (
        <p className="text-gray-600 leading-relaxed whitespace-pre-line bg-white rounded p-2 border border-gray-100">
          {item.excerpt}
        </p>
      )}
    </div>
  );
}

/**
 * AI 답변에 인용된 법령 조문의 실존 검증 결과 패널
 *
 * @param {Array} items - 백엔드 answer_meta.verified_citations
 */
export default function CitationVerificationPanel({ items }) {
  const [selectedIdx, setSelectedIdx] = useState(null);
  if (!items?.length) return null;

  const problemCount = items.filter(i => PROBLEM_STATUSES.has(i.status)).length;
  const verifiedCount = items.filter(i => i.status === 'verified').length;
  const selected = selectedIdx !== null ? items[selectedIdx] : null;

  return (
    <div className="mt-4 pt-4 border-t border-gray-200">
      {problemCount > 0 && (
        <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
          <AlertTriangle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-red-800">
            답변에 <strong>현행 법령에서 확인되지 않는 조문 {problemCount}건</strong>이 포함되어 있습니다.
            빨간색으로 표시된 인용은 신뢰하지 말고, 원문을 확인하거나 법무 담당자에게 문의하십시오.
          </p>
        </div>
      )}

      <div className="flex items-center gap-2 mb-2">
        <ShieldCheck size={16} className="text-gray-600" />
        <p className="text-sm font-medium text-gray-900">인용 법령 검증</p>
        <span className="text-xs text-gray-400">
          {verifiedCount}/{items.length}건 확인 · 국가법령정보센터 현행 법령 기준
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {items.map((item, idx) => (
          <VerificationChip
            key={`${item.law_name}-${item.article}`}
            item={item}
            selected={selectedIdx === idx}
            onClick={() => setSelectedIdx(selectedIdx === idx ? null : idx)}
          />
        ))}
      </div>

      {selected && <VerificationDetail item={selected} />}
    </div>
  );
}
