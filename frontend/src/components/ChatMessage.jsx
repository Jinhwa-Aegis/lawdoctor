import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertTriangle, Shield, ChevronDown, ChevronUp, Scale, BookOpen, Briefcase, Sparkles,
  Copy, Check, FileDown, Printer, PencilLine, Library,
} from 'lucide-react';
import FeedbackButton from './FeedbackButton';
import CitationVerificationPanel from './CitationVerificationPanel';
import GenerationProgress from './chat/GenerationProgress';
import PerspectivesPanel from './chat/PerspectivesPanel';

// 복수 분야 질의의 진행 단계
const MULTI_STEPS = [
  { key: 'searching', label: '분야별 법령 검색' },
  { key: 'perspectives', label: '분야별 검토' },
  { key: 'writing', label: '종합 답변 작성' },
  { key: 'verifying', label: '인용 검증' },
];
import { copyAnswer, downloadWord, printAnswer } from '../utils/exportAnswer';

// ---------------------------------------------------------------------------
// 본문 전처리
// ---------------------------------------------------------------------------

/**
 * 본문의 "### 신뢰도" 섹션을 제거한다. 신뢰도는 상단 배지 하나로만 표시한다.
 * (스트리밍 중 제목만 도착한 상태도 처리)
 */
function stripConfidenceSection(content) {
  if (!content) return content;
  return content.replace(/(^|\n)#{2,4}[ \t]*신뢰도[ \t]*(?:\n[\s\S]*?)?(?=\n#{1,4}\s|$)/, '$1').trimEnd();
}

/** "### 결론" 섹션을 분리해 강조 박스로 보여준다. */
function splitConclusion(content) {
  const m = (content || '').match(/(^|\n)#{2,4}[ \t]*결론[ \t]*\n([\s\S]*?)(?=\n#{1,4}\s|$)/);
  if (!m) return { conclusion: '', rest: content || '' };
  const rest = (content.slice(0, m.index) + (m[1] || '') + content.slice(m.index + m[0].length)).trim();
  return { conclusion: m[2].trim(), rest };
}

/** "15" → "제15조", "25의2" → "제25조의2" */
function formatArticleLabel(articleNumber) {
  const [main, branch] = String(articleNumber || '').split('의');
  return branch ? `제${main}조의${branch}` : `제${main}조`;
}

function formatTime(dateStr) {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

// ---------------------------------------------------------------------------
// 마크다운 내 [N] 인용 배지
// ---------------------------------------------------------------------------

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
          className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 mx-0.5 text-[10px] font-semibold text-primary-700 bg-primary-100 rounded-md hover:bg-primary-600 hover:text-white transition-colors align-[2px] leading-none"
          title={`근거 자료 [${num}] 보기`}
        >
          {num}
        </button>
      );
    }
    return part;
  });
}

function transformChildren(children, onCitationClick) {
  return React.Children.map(children, child => {
    if (typeof child === 'string') return processTextWithCitations(child, onCitationClick);
    if (React.isValidElement(child) && child.props?.children) {
      return React.cloneElement(child, {
        ...child.props,
        children: transformChildren(child.props.children, onCitationClick),
      });
    }
    return child;
  });
}

/** 노드 트리에서 순수 텍스트만 추출 */
function nodeText(children) {
  return React.Children.toArray(children)
    .map(c => (typeof c === 'string' ? c : nodeText(c?.props?.children)))
    .join('');
}

const RISK_LEVEL_STYLES = {
  높음: { dot: 'bg-red-500', text: 'text-red-700' },
  긴급: { dot: 'bg-red-500', text: 'text-red-700' },
  중간: { dot: 'bg-amber-400', text: 'text-amber-700' },
  보통: { dot: 'bg-amber-400', text: 'text-amber-700' },
  낮음: { dot: 'bg-emerald-500', text: 'text-emerald-700' },
};

/** 표 셀 값이 위험 수준(높음/중간/낮음) 단독이면 색 점과 함께 표시 */
function RiskLevelCell({ children }) {
  const text = nodeText(children).trim();
  const style = RISK_LEVEL_STYLES[text];
  if (!style) return <>{children}</>;
  return (
    <span className={`inline-flex items-center gap-1.5 font-semibold whitespace-nowrap ${style.text}`}>
      <span className={`w-2 h-2 rounded-full ${style.dot}`} />
      {text}
    </span>
  );
}

function SectionHeading({ children }) {
  return (
    <h3 className="mt-7 mb-3 pt-5 border-t border-slate-100 text-[15px] font-bold text-slate-900 first:mt-0 first:pt-0 first:border-0">
      {children}
    </h3>
  );
}

function buildMarkdownComponents(onCitationClick) {
  const wrap = (Tag, className) => {
    const Comp = ({ children, node, ...props }) => (
      <Tag className={className} {...props}>
        {transformChildren(children, onCitationClick)}
      </Tag>
    );
    Comp.displayName = `MD_${Tag}`;
    return Comp;
  };

  return {
    p: wrap('p', 'mb-3 text-[15px] leading-7 text-slate-700'),
    li: wrap('li', 'mb-1.5 pl-1 text-[15px] leading-7 text-slate-700 marker:text-slate-400'),
    ul: ({ children, node, ...props }) => <ul className="list-disc ml-5 mb-3" {...props}>{children}</ul>,
    ol: ({ children, node, ...props }) => <ol className="list-decimal ml-5 mb-3 marker:font-semibold marker:text-primary-600" {...props}>{children}</ol>,
    strong: wrap('strong', 'font-semibold text-slate-900'),
    em: wrap('em', 'italic text-slate-500'),
    a: ({ children, node, ...props }) => (
      <a className="text-primary-600 underline underline-offset-2 hover:text-primary-800" target="_blank" rel="noopener noreferrer" {...props}>{children}</a>
    ),
    hr: () => <hr className="my-5 border-slate-200" />,
    code: ({ className, children, node, ...props }) => {
      const isInline = !className;
      return isInline ? (
        <code className="px-1.5 py-0.5 bg-slate-100 text-slate-800 rounded text-[13px]" {...props}>{children}</code>
      ) : (
        <pre className="p-3 bg-slate-900 text-slate-100 rounded-lg text-[13px] mb-3 overflow-x-auto">
          <code className={className} {...props}>{children}</code>
        </pre>
      );
    },
    blockquote: wrap('blockquote', 'border-l-4 border-primary-200 bg-primary-50/40 pl-4 py-1 my-3 text-slate-600'),
    h1: SectionHeading,
    h2: SectionHeading,
    h3: SectionHeading,
    h4: wrap('h4', 'mt-4 mb-2 text-[14px] font-semibold text-slate-800'),
    table: ({ children, node, ...props }) => (
      <div className="my-4 overflow-x-auto rounded-xl border border-slate-200">
        <table className="min-w-full text-[13.5px]" {...props}>{children}</table>
      </div>
    ),
    thead: ({ children, node, ...props }) => <thead className="bg-slate-800 text-white" {...props}>{children}</thead>,
    tbody: ({ children, node, ...props }) => <tbody className="divide-y divide-slate-100 [&>tr:nth-child(even)]:bg-slate-50/70" {...props}>{children}</tbody>,
    th: ({ children, node, ...props }) => (
      <th className="px-4 py-2.5 text-left text-[12.5px] font-semibold whitespace-nowrap" {...props}>{children}</th>
    ),
    td: ({ children, node, ...props }) => (
      <td className="px-4 py-2.5 align-top text-slate-700 leading-6" {...props}>
        <RiskLevelCell>{transformChildren(children, onCitationClick)}</RiskLevelCell>
      </td>
    ),
  };
}

// ---------------------------------------------------------------------------
// 근거 자료 (RAG 검색 결과)
// ---------------------------------------------------------------------------

const SOURCE_TYPE_CONFIG = {
  law: { icon: Scale, label: '법령', color: 'text-primary-700' },
  precedent: { icon: BookOpen, label: '판례', color: 'text-violet-700' },
  consultation: { icon: Briefcase, label: '자문', color: 'text-emerald-700' },
  security_guide: { icon: Shield, label: '보안', color: 'text-orange-700' },
  security_incident: { icon: Shield, label: '사례', color: 'text-orange-700' },
};

function describeSource(item) {
  if (item.source_type === 'precedent') {
    return {
      title: item.case_name || item.source || '관련 판례',
      subtitle: [item.court, item.case_number, item.decision_date].filter(Boolean).join(' · '),
    };
  }
  if (item.source_type === 'law') {
    let subtitle = item.article_number ? formatArticleLabel(item.article_number) : '';
    if (item.article_title) subtitle += ` ${item.article_title}`;
    return { title: item.law_name || item.source || '관련 법령', subtitle };
  }
  if (item.guide_name) return { title: item.guide_name, subtitle: item.section || '' };
  return { title: item.source || '자문 이력', subtitle: '' };
}

function SourceItem({ item, number, isHighlighted }) {
  const [expanded, setExpanded] = useState(false);
  const ref = useRef(null);
  const typeCfg = SOURCE_TYPE_CONFIG[item.source_type] || SOURCE_TYPE_CONFIG.law;
  const Icon = typeCfg.icon;
  const hasExcerpt = Boolean(item.excerpt);
  const { title, subtitle } = describeSource(item);

  useEffect(() => {
    if (isHighlighted) {
      setExpanded(true);
      ref.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [isHighlighted]);

  return (
    <li
      ref={ref}
      className={`rounded-lg border transition-all ${
        isHighlighted ? 'border-primary-300 bg-primary-50/60 ring-2 ring-primary-100' : 'border-slate-200 bg-white'
      }`}
    >
      <button
        type="button"
        className="w-full text-left px-3 py-2 flex items-center gap-2.5"
        onClick={() => hasExcerpt && setExpanded(!expanded)}
      >
        {number != null && (
          <span className="flex-shrink-0 min-w-[20px] h-5 px-1 rounded-md bg-slate-100 text-slate-600 text-[11px] font-semibold flex items-center justify-center">
            {number}
          </span>
        )}
        <Icon size={14} className={`${typeCfg.color} flex-shrink-0`} />
        <span className={`text-[13px] font-medium ${typeCfg.color} truncate`}>{title}</span>
        {subtitle && <span className="text-[12px] text-slate-500 truncate">{subtitle}</span>}
        <span className="ml-auto flex items-center gap-2 flex-shrink-0">
          <span className="text-[10px] text-slate-400">{typeCfg.label}</span>
          {hasExcerpt && (expanded ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />)}
        </span>
      </button>
      {expanded && hasExcerpt && (
        <p className="mx-3 mb-2.5 text-[12.5px] text-slate-600 leading-relaxed bg-slate-50 rounded-md p-2.5 whitespace-pre-line">
          {item.excerpt}
        </p>
      )}
    </li>
  );
}

function SourcesSection({ items, useCitationNumbers, highlighted, open, onToggle, title }) {
  if (!items.length) return null;
  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={onToggle}
        className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-slate-500 hover:text-slate-800"
      >
        <Library size={14} />
        {title} {items.length}건
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5">
          {items.map((item, idx) => (
            <SourceItem
              key={useCitationNumbers ? item.citation_id : idx}
              item={item}
              number={useCitationNumbers ? item.citation_id : null}
              isHighlighted={useCitationNumbers && highlighted === item.citation_id}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 신뢰도 배지 · 후속 질문 · 액션 바
// ---------------------------------------------------------------------------

const CONFIDENCE_CONFIGS = {
  high: { label: '높음', color: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  medium: { label: '보통', color: 'bg-amber-50 text-amber-700 ring-amber-200' },
  low: { label: '낮음', color: 'bg-red-50 text-red-700 ring-red-200' },
};

function ConfidenceBadge({ level, notes }) {
  const cfg = CONFIDENCE_CONFIGS[level];
  if (!cfg) return null;
  return (
    <span className="relative group/conf inline-flex">
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11.5px] font-medium ring-1 ring-inset ${cfg.color}`}>
        <Shield size={11} />
        신뢰도 {cfg.label}
      </span>
      {notes.length > 0 && (
        <span className="pointer-events-none absolute right-0 top-full mt-1.5 z-20 w-72 rounded-lg bg-slate-900 px-3 py-2 text-[12px] leading-relaxed text-slate-100 opacity-0 shadow-lg transition-opacity group-hover/conf:opacity-100">
          {notes.map((n) => <span key={n} className="block">{n}</span>)}
        </span>
      )}
    </span>
  );
}

function FollowupChips({ questions, onSelect }) {
  if (!questions?.length) return null;
  return (
    <div className="mt-5">
      <p className="flex items-center gap-1 text-[12px] font-medium text-slate-500 mb-2">
        <Sparkles size={12} className="text-amber-500" />
        이어서 물어볼까요
      </p>
      <div className="flex flex-col items-start gap-1.5">
        {questions.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onSelect?.(q)}
            className="text-left px-3.5 py-2 text-[13px] text-slate-700 bg-white border border-slate-200 rounded-xl hover:border-primary-300 hover:text-primary-700 hover:bg-primary-50/50 transition-colors"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function ActionButton({ icon: Icon, label, onClick, active }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1 h-7 px-2 rounded-md text-[12px] transition-colors ${
        active ? 'text-emerald-600' : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
      }`}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}

function AnswerActions({ message, question, bodyRef, disclaimer, exportTitle }) {
  const [copied, setCopied] = useState(false);

  const exportPayload = () => ({
    title: exportTitle || question?.slice(0, 30) || '법률 답변',
    question,
    answerHtml: bodyRef.current?.innerHTML || '',
    disclaimer,
  });

  const handleCopy = async () => {
    try {
      await copyAnswer(`${stripConfidenceSection(message.content)}\n\n---\n${disclaimer}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 클립보드 권한 없음 — 무시
    }
  };

  const canFeedback = message.id && message.id !== 'streaming' && typeof message.id === 'number';

  return (
    <div className="mt-3 flex items-center gap-0.5 flex-wrap">
      <ActionButton icon={copied ? Check : Copy} label={copied ? '복사됨' : '복사'} onClick={handleCopy} active={copied} />
      <ActionButton icon={FileDown} label="Word" onClick={() => downloadWord(exportPayload())} />
      <ActionButton icon={Printer} label="인쇄·PDF" onClick={() => printAnswer(exportPayload())} />
      {canFeedback && (
        <>
          <span className="mx-1.5 w-px h-4 bg-slate-200" />
          <FeedbackButton messageId={message.id} compact />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatMessage
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG = {
  assistantName: '법무주치의',
  escalationTitle: '외부 전문가 자문 권장',
  escalationDescription: '고위험 법률 사안이 포함되어 있습니다. AI 답변은 참고용이며, 결정 전에 반드시 외부 변호사 등 전문가 자문을 받으시기 바랍니다.',
  referencesTitle: '근거 자료',
  referencesField: 'legal_references',
  disclaimer: '본 답변은 AI가 생성한 참고 정보이며, 법적 효력이 있는 공식 법률 자문이 아닙니다. 중요한 법률적 판단이 필요한 경우 외부 전문가 자문을 받으시기 바랍니다.',
};

function UserMessage({ message, onEditQuestion }) {
  return (
    <div className="group flex flex-col items-end">
      <div className="max-w-[85%] bg-primary-600 text-white rounded-2xl rounded-br-md px-4 py-2.5 shadow-sm">
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{message.content}</p>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11.5px] text-slate-400">
        {onEditQuestion && (
          <button
            type="button"
            onClick={() => onEditQuestion(message.content)}
            className="inline-flex items-center gap-1 opacity-0 group-hover:opacity-100 hover:text-slate-700 transition-opacity"
          >
            <PencilLine size={12} />
            고쳐서 다시 묻기
          </button>
        )}
        <span>{formatTime(message.created_at)}</span>
      </div>
    </div>
  );
}

const ChatMessage = ({
  message,
  domainConfig,
  question,
  isLast = false,
  isStreaming = false,
  stage = null,
  isPostProcessing = false,
  onFollowup,
  onEditQuestion,
  categoryLabels = {},
}) => {
  const config = { ...DEFAULT_CONFIG, ...domainConfig };
  const [highlightedCitation, setHighlightedCitation] = useState(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const bodyRef = useRef(null);

  const handleCitationClick = useCallback((num) => {
    setSourcesOpen(true);
    setHighlightedCitation(num);
    setTimeout(() => setHighlightedCitation(null), 3000);
  }, []);

  // 스트리밍 중 매 청크마다 컴포넌트 맵을 새로 만들지 않도록 고정
  const mdComponents = useMemo(() => buildMarkdownComponents(handleCitationClick), [handleCitationClick]);

  const { conclusion, rest } = useMemo(
    () => splitConclusion(stripConfidenceSection(message.content)),
    [message.content],
  );

  if (message.role === 'user') {
    return <UserMessage message={message} onEditQuestion={onEditQuestion} />;
  }

  const answerMeta = message.answer_meta || {};
  const finalConfidence = isStreaming && !answerMeta.confidence ? null : (answerMeta.confidence || message.confidence);
  const confidenceNotes = [
    answerMeta.confidence_reason,
    ...(answerMeta.confidence_adjustments || []).map(a => `하향 조정: ${a}`),
  ].filter(Boolean);

  // 저장된 대화는 answer_meta.citations에 인용 번호 목록이 있다
  const citations = message.citations?.length ? message.citations : (answerMeta.citations || []);
  const legacyRefs = message[config.referencesField] || [];
  const useCitations = citations.length > 0;
  const sources = useCitations ? citations : legacyRefs;
  const perspectives = answerMeta.perspectives || [];
  const perspectiveLabels = perspectives.length
    ? perspectives.map((p) => p.label)
    : (message.perspective_domains || []);
  const isMulti = perspectiveLabels.length > 1;
  const categoryLabel = isMulti
    ? perspectiveLabels.join(' + ')
    : (message.category ? (categoryLabels[message.category] || null) : null);
  const hasContent = Boolean(message.content);
  const showMeta = !isStreaming || (!isPostProcessing && answerMeta.followups);

  return (
    <div className="flex gap-3">
      {/* 아바타 */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-600 text-white flex items-center justify-center shadow-sm">
        <Scale size={15} />
      </div>

      <div className="flex-1 min-w-0">
        {/* 헤더 */}
        <div className="flex items-center gap-2 h-8 mb-1.5 whitespace-nowrap">
          <span className="text-[13px] font-semibold text-slate-900">{config.assistantName}</span>
          {categoryLabel && (
            <span className="text-[11px] font-medium text-primary-700 bg-primary-50 rounded px-1.5 py-0.5 truncate">{categoryLabel}</span>
          )}
          <span className="text-[11.5px] text-slate-400">{formatTime(message.created_at)}</span>
          {!isStreaming && (
            <span className="ml-auto">
              <ConfidenceBadge level={finalConfidence} notes={confidenceNotes} />
            </span>
          )}
        </div>

        {/* 생성 진행 단계 (헤더 아래 별도 줄) */}
        {isStreaming && (
          <div className="mb-2.5 whitespace-nowrap overflow-x-auto scrollbar-thin">
            <GenerationProgress stage={stage} steps={isMulti ? MULTI_STEPS : undefined} />
          </div>
        )}

        {/* 고위험 안내 */}
        {message.is_escalated && (
          <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-xl flex items-start gap-2.5">
            <AlertTriangle size={18} className="text-red-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-[13px] font-semibold text-red-900">{config.escalationTitle}</p>
              <p className="text-[12.5px] text-red-700 mt-0.5 leading-relaxed">{config.escalationDescription}</p>
            </div>
          </div>
        )}

        {/* 분야별 검토 의견 (복수 분야 질의) */}
        {isMulti && (
          <PerspectivesPanel
            opinions={perspectives}
            pendingLabels={isStreaming && !perspectives.length ? perspectiveLabels : []}
          />
        )}

        {/* 답변 카드 */}
        <div className="rounded-2xl rounded-tl-md bg-white border border-slate-200 shadow-sm px-6 py-5">
          {!hasContent && isStreaming ? (
            <div className="space-y-2.5 py-1" aria-label="답변 준비 중">
              <div className="h-3.5 w-3/4 rounded bg-slate-100 animate-pulse" />
              <div className="h-3.5 w-full rounded bg-slate-100 animate-pulse" />
              <div className="h-3.5 w-5/6 rounded bg-slate-100 animate-pulse" />
            </div>
          ) : (
            <div ref={bodyRef}>
              {conclusion && (
                <div className="mb-5 rounded-xl bg-primary-50/70 border border-primary-100 px-4 py-3.5">
                  <p className="text-[11.5px] font-bold tracking-wide text-primary-700 mb-1">결론</p>
                  <div className="[&_p]:mb-0 [&_p]:text-[15.5px] [&_p]:leading-7 [&_p]:font-medium [&_p]:text-slate-900">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{conclusion}</ReactMarkdown>
                  </div>
                </div>
              )}
              <div className={isStreaming && !isPostProcessing ? 'streaming-caret' : ''}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{rest}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* 인용 법령 검증 */}
          {showMeta && <CitationVerificationPanel items={answerMeta.verified_citations} />}

          {/* 근거 자료 (검색 결과) */}
          {!isStreaming && (
            <SourcesSection
              items={sources}
              useCitationNumbers={useCitations}
              highlighted={highlightedCitation}
              open={sourcesOpen}
              onToggle={() => setSourcesOpen(!sourcesOpen)}
              title={config.referencesTitle}
            />
          )}

          {/* 면책 문구 (모든 답변 필수) */}
          {hasContent && (
            <p className="mt-5 flex items-start gap-1.5 rounded-lg bg-amber-50/70 border border-amber-100 px-3 py-2 text-[11.5px] leading-relaxed text-amber-800">
              <AlertTriangle size={13} className="flex-shrink-0 mt-[1px]" />
              {config.disclaimer}
            </p>
          )}
        </div>

        {/* 액션 바 */}
        {!isStreaming && hasContent && !message.aborted && (
          <AnswerActions
            message={message}
            question={question}
            bodyRef={bodyRef}
            disclaimer={config.disclaimer}
          />
        )}

        {/* 후속 질문 (마지막 답변에만) */}
        {isLast && <FollowupChips questions={answerMeta.followups} onSelect={onFollowup} />}
      </div>
    </div>
  );
};

export default React.memo(ChatMessage);
