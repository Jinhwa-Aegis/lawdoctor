import React, { useState, useCallback, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { AlertTriangle, Shield, FileText, ChevronDown, ChevronUp, Scale, BookOpen, Briefcase } from 'lucide-react';
import FeedbackButton from './FeedbackButton';

// ---------------------------------------------------------------------------
// 마크다운 내 [N] 인용 배지 처리
// ---------------------------------------------------------------------------

/**
 * 텍스트 노드에서 [N] 패턴을 찾아 인라인 인용 배지로 변환한다.
 */
function processTextWithCitations(text, onCitationClick) {
  if (typeof text !== 'string') return text;
  const parts = text.split(/(\[\d+\])/g);
  if (parts.length === 1) return text;

  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const num = parseInt(match[1]);
      return (
        <button
          key={`cite-${i}`}
          type="button"
          onClick={(e) => { e.stopPropagation(); onCitationClick(num); }}
          className="inline-flex items-center justify-center w-5 h-5 mx-0.5 text-[10px] font-bold text-white bg-blue-500 rounded-full hover:bg-blue-600 transition-colors cursor-pointer align-super leading-none"
          title={`참고자료 [${num}] 보기`}
        >
          {num}
        </button>
      );
    }
    return part;
  });
}

/**
 * children(React 노드 트리)을 순회하며 텍스트 내 [N]을 인용 배지로 변환한다.
 */
function transformChildren(children, onCitationClick) {
  return React.Children.map(children, child => {
    if (typeof child === 'string') {
      return processTextWithCitations(child, onCitationClick);
    }
    if (React.isValidElement(child) && child.props?.children) {
      return React.cloneElement(child, {
        ...child.props,
        children: transformChildren(child.props.children, onCitationClick),
      });
    }
    return child;
  });
}

/**
 * [N] 인용 배지가 포함된 마크다운 컴포넌트를 생성한다.
 */
function buildMarkdownComponents(onCitationClick) {
  const wrap = (Tag, className) => {
    const Comp = ({ children, ...props }) => (
      <Tag className={className} {...props}>
        {transformChildren(children, onCitationClick)}
      </Tag>
    );
    Comp.displayName = `MD_${Tag}`;
    return Comp;
  };

  return {
    p: wrap('p', 'mb-2 leading-relaxed'),
    li: wrap('li', 'mb-1'),
    ul: ({ children, ...props }) => <ul className="list-disc ml-4 mb-2" {...props}>{children}</ul>,
    ol: ({ children, ...props }) => <ol className="list-decimal ml-4 mb-2" {...props}>{children}</ol>,
    strong: wrap('strong', 'font-bold text-gray-900'),
    em: wrap('em', 'italic text-gray-700'),
    code: ({ className, children, ...props }) => {
      const isInline = !className;
      return isInline ? (
        <code className="px-1 py-0.5 bg-gray-100 rounded text-sm" {...props}>{children}</code>
      ) : (
        <pre className="p-2 bg-gray-100 rounded text-sm mb-2 overflow-x-auto">
          <code className={className} {...props}>{children}</code>
        </pre>
      );
    },
    blockquote: wrap('blockquote', 'border-l-4 border-gray-300 pl-3 italic text-gray-600 mb-2'),
  };
}

// ---------------------------------------------------------------------------
// 상수
// ---------------------------------------------------------------------------

const CONFIDENCE_CONFIGS = {
  high: { label: '높음', color: 'bg-green-100 text-green-800' },
  medium: { label: '보통', color: 'bg-yellow-100 text-yellow-800' },
  low: { label: '낮음', color: 'bg-red-100 text-red-800' },
};

function formatTime(dateStr) {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

// ---------------------------------------------------------------------------
// 참조 항목 컴포넌트
// ---------------------------------------------------------------------------

const SOURCE_TYPE_CONFIG = {
  law: { icon: Scale, label: '법령', color: 'text-blue-600', bg: 'bg-blue-50', ring: 'ring-blue-300' },
  precedent: { icon: BookOpen, label: '판례', color: 'text-purple-600', bg: 'bg-purple-50', ring: 'ring-purple-300' },
  consultation: { icon: Briefcase, label: '자문', color: 'text-emerald-600', bg: 'bg-emerald-50', ring: 'ring-emerald-300' },
  security_guide: { icon: Shield, label: '보안', color: 'text-orange-600', bg: 'bg-orange-50', ring: 'ring-orange-300' },
  security_incident: { icon: Shield, label: '사례', color: 'text-orange-600', bg: 'bg-orange-50', ring: 'ring-orange-300' },
};

function CitationItem({ citation, isHighlighted, onToggle }) {
  const [expanded, setExpanded] = useState(false);
  const ref = useRef(null);
  const typeCfg = SOURCE_TYPE_CONFIG[citation.source_type] || SOURCE_TYPE_CONFIG.law;
  const Icon = typeCfg.icon;
  const hasExcerpt = citation.excerpt && citation.excerpt.length > 0;

  // 하이라이트 시 자동 펼침 및 스크롤
  useEffect(() => {
    if (isHighlighted) {
      setExpanded(true);
      ref.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [isHighlighted]);

  let title = '';
  let subtitle = '';

  if (citation.source_type === 'precedent') {
    title = citation.case_name || citation.source || '관련 판례';
    const parts = [];
    if (citation.court) parts.push(citation.court);
    if (citation.case_number) parts.push(citation.case_number);
    if (citation.decision_date) parts.push(citation.decision_date);
    subtitle = parts.join(' | ');
  } else if (citation.source_type === 'law') {
    title = citation.law_name || citation.source || '관련 법령';
    if (citation.article_number) {
      subtitle = `제${citation.article_number}조`;
      if (citation.article_title) subtitle += ` (${citation.article_title})`;
    }
  } else if (citation.guide_name) {
    title = citation.guide_name || citation.source || '보안 가이드';
    if (citation.section) subtitle = citation.section;
  } else {
    title = citation.source || '자문 이력';
  }

  return (
    <li
      ref={ref}
      className={`rounded-lg border overflow-hidden transition-all duration-300 ${
        isHighlighted
          ? `${typeCfg.bg} border-current ring-2 ${typeCfg.ring}`
          : `${typeCfg.bg} border-gray-100`
      }`}
    >
      <button
        type="button"
        className="w-full text-left px-3 py-2 flex items-start gap-2 hover:bg-white/40 transition-colors"
        onClick={() => { hasExcerpt && setExpanded(!expanded); onToggle?.(); }}
      >
        {/* 인용 번호 */}
        <span className="inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold text-white bg-blue-500 rounded-full flex-shrink-0 mt-0.5">
          {citation.citation_id}
        </span>
        <Icon size={14} className={`${typeCfg.color} mt-0.5 flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-sm font-medium ${typeCfg.color}`}>{title}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${typeCfg.bg} ${typeCfg.color} border border-current/10 font-medium`}>
              {typeCfg.label}
            </span>
          </div>
          {subtitle && (
            <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
          )}
        </div>
        {hasExcerpt && (
          <span className="text-gray-400 flex-shrink-0 mt-0.5">
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </span>
        )}
      </button>
      {expanded && hasExcerpt && (
        <div className="px-3 pb-2 pt-0 ml-7">
          <p className="text-xs text-gray-600 leading-relaxed bg-white/60 rounded p-2 border border-gray-100">
            {citation.excerpt}
          </p>
        </div>
      )}
    </li>
  );
}

// 기존 ReferenceItem (citations가 없을 때 폴백)
function ReferenceItem({ ref_ }) {
  const [expanded, setExpanded] = useState(false);
  const typeCfg = SOURCE_TYPE_CONFIG[ref_.source_type] || SOURCE_TYPE_CONFIG.law;
  const Icon = typeCfg.icon;
  const hasExcerpt = ref_.excerpt && ref_.excerpt.length > 0;

  let title = '';
  let subtitle = '';
  if (ref_.source_type === 'precedent') {
    title = ref_.case_name || ref_.source || '관련 판례';
    const parts = [];
    if (ref_.court) parts.push(ref_.court);
    if (ref_.case_number) parts.push(ref_.case_number);
    if (ref_.decision_date) parts.push(ref_.decision_date);
    subtitle = parts.join(' | ');
  } else if (ref_.source_type === 'law') {
    title = ref_.law_name || ref_.source || '관련 법령';
    if (ref_.article_number) {
      subtitle = `제${ref_.article_number}조`;
      if (ref_.article_title) subtitle += ` (${ref_.article_title})`;
    }
  } else {
    title = ref_.source || '자문 이력';
  }

  return (
    <li className={`rounded-lg border border-gray-100 ${typeCfg.bg} overflow-hidden`}>
      <button
        type="button"
        className="w-full text-left px-3 py-2 flex items-start gap-2 hover:bg-white/40 transition-colors"
        onClick={() => hasExcerpt && setExpanded(!expanded)}
        disabled={!hasExcerpt}
      >
        <Icon size={14} className={`${typeCfg.color} mt-0.5 flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-sm font-medium ${typeCfg.color}`}>{title}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${typeCfg.bg} ${typeCfg.color} border border-current/10 font-medium`}>
              {typeCfg.label}
            </span>
          </div>
          {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
        </div>
        {hasExcerpt && (
          <span className="text-gray-400 flex-shrink-0 mt-0.5">
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </span>
        )}
      </button>
      {expanded && hasExcerpt && (
        <div className="px-3 pb-2 pt-0">
          <p className="text-xs text-gray-600 leading-relaxed bg-white/60 rounded p-2 border border-gray-100">
            {ref_.excerpt}
          </p>
        </div>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// ChatMessage 메인 컴포넌트
// ---------------------------------------------------------------------------

const ChatMessage = ({ message, domainConfig }) => {
  const isUser = message.role === 'user';
  const [highlightedCitation, setHighlightedCitation] = useState(null);

  const config = {
    escalationTitle: '전문가 상담 권장',
    escalationDescription: '이 질문은 전문 변호사의 상담이 필요합니다. 정확한 법률 자문을 위해 전문가와 상담하시기 바랍니다.',
    referencesTitle: '근거 법령',
    referencesField: 'legal_references',
    renderReference: (ref, index) => (
      <ReferenceItem key={index} ref_={ref} />
    ),
    disclaimer: '본 답변은 AI가 생성한 참고 정보이며, 법적 효력이 있는 공식 법률 자문이 아닙니다. 중요한 법률적 판단이 필요한 경우 외부 전문가 자문을 받으시기 바랍니다.',
    ...domainConfig,
  };

  // 인용 배지 클릭 핸들러
  const handleCitationClick = useCallback((num) => {
    setHighlightedCitation(num);
    // 2초 후 하이라이트 해제
    setTimeout(() => setHighlightedCitation(null), 3000);
  }, []);

  // citations 기반 마크다운 컴포넌트
  const mdComponents = buildMarkdownComponents(handleCitationClick);

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-3xl">
          <div className="bg-blue-600 text-white rounded-lg px-4 py-3 shadow-sm">
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
          <p className="text-xs text-gray-500 mt-1 text-right">
            {formatTime(message.created_at)}
          </p>
        </div>
      </div>
    );
  }

  // citations가 있으면 통합 인용 목록 사용, 없으면 기존 references 폴백
  const citations = message.citations || [];
  const legacyRefs = message[config.referencesField] || [];
  const useCitations = citations.length > 0;
  const confidenceCfg = CONFIDENCE_CONFIGS[message.confidence] || CONFIDENCE_CONFIGS.medium;

  return (
    <div className="flex justify-start">
      <div className="max-w-3xl w-full">
        <div className="bg-white rounded-lg px-4 py-3 shadow-sm border border-gray-200">
          {/* 에스컬레이션 배너 */}
          {message.is_escalated && (
            <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
              <AlertTriangle size={20} className="text-red-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium text-red-900">{config.escalationTitle}</p>
                <p className="text-xs text-red-700 mt-1">{config.escalationDescription}</p>
              </div>
            </div>
          )}

          {/* 신뢰도 배지 */}
          {message.confidence && (
            <div className="mb-2">
              <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${confidenceCfg.color}`}>
                <Shield size={12} />
                신뢰도: {confidenceCfg.label}
              </span>
            </div>
          )}

          {/* 메시지 내용 (인라인 인용 배지 포함) */}
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown components={useCitations ? mdComponents : mdComponents}>
              {message.content}
            </ReactMarkdown>
          </div>

          {/* 인용 출처 (통합 citations) */}
          {useCitations && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              <div className="flex items-center gap-2 mb-2">
                <FileText size={16} className="text-gray-600" />
                <p className="text-sm font-medium text-gray-900">{config.referencesTitle}</p>
                <span className="text-xs text-gray-400">({citations.length})</span>
              </div>
              <ul className="space-y-1.5">
                {citations.map((c) => (
                  <CitationItem
                    key={c.citation_id}
                    citation={c}
                    isHighlighted={highlightedCitation === c.citation_id}
                    onToggle={() => setHighlightedCitation(null)}
                  />
                ))}
              </ul>
            </div>
          )}

          {/* 기존 references 폴백 */}
          {!useCitations && legacyRefs.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              <div className="flex items-center gap-2 mb-2">
                <FileText size={16} className="text-gray-600" />
                <p className="text-sm font-medium text-gray-900">{config.referencesTitle}</p>
              </div>
              <ul className="space-y-1.5">
                {legacyRefs.map((ref, index) => config.renderReference(ref, index))}
              </ul>
            </div>
          )}

          {/* 면책 문구 */}
          <div className="mt-4 pt-4 border-t border-gray-200">
            <p className="text-xs text-gray-500">{config.disclaimer}</p>
          </div>

          {/* 피드백 버튼 */}
          {message.id && message.id !== 'streaming' && (
            <div className="mt-3">
              <FeedbackButton messageId={message.id} />
            </div>
          )}
        </div>

        <p className="text-xs text-gray-500 mt-1">
          {formatTime(message.created_at)}
        </p>
      </div>
    </div>
  );
};

export default React.memo(ChatMessage);

