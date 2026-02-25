import React from 'react';
import ReactMarkdown from 'react-markdown';
import { AlertTriangle, Shield, FileText } from 'lucide-react';
import FeedbackButton from './FeedbackButton';

const MARKDOWN_COMPONENTS = {
  p: ({ children, ...props }) => <p className="mb-2 leading-relaxed" {...props}>{children}</p>,
  ul: ({ children, ...props }) => <ul className="list-disc ml-4 mb-2" {...props}>{children}</ul>,
  ol: ({ children, ...props }) => <ol className="list-decimal ml-4 mb-2" {...props}>{children}</ol>,
  li: ({ children, ...props }) => <li className="mb-1" {...props}>{children}</li>,
  strong: ({ children, ...props }) => <strong className="font-bold text-gray-900" {...props}>{children}</strong>,
  em: ({ children, ...props }) => <em className="italic text-gray-700" {...props}>{children}</em>,
  code: ({ className, children, ...props }) => {
    const isInline = !className
    return isInline ? (
      <code className="px-1 py-0.5 bg-gray-100 rounded text-sm" {...props}>{children}</code>
    ) : (
      <pre className="p-2 bg-gray-100 rounded text-sm mb-2 overflow-x-auto">
        <code className={className} {...props}>{children}</code>
      </pre>
    )
  },
  blockquote: ({ children, ...props }) => (
    <blockquote className="border-l-4 border-gray-300 pl-3 italic text-gray-600 mb-2" {...props}>{children}</blockquote>
  )
};

const CONFIDENCE_CONFIGS = {
  high: { label: '높음', color: 'bg-green-100 text-green-800' },
  medium: { label: '보통', color: 'bg-yellow-100 text-yellow-800' },
  low: { label: '낮음', color: 'bg-red-100 text-red-800' }
};

function formatTime(dateStr) {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return '';
  }
}

/**
 * 범용 채팅 메시지 컴포넌트
 *
 * @param {Object} props
 * @param {Object} props.message - 메시지 객체
 * @param {Object} [props.domainConfig] - 도메인별 설정
 * @param {string} [props.domainConfig.escalationTitle] - 에스컬레이션 제목
 * @param {string} [props.domainConfig.escalationDescription] - 에스컬레이션 설명
 * @param {string} [props.domainConfig.referencesTitle] - 참조 섹션 제목
 * @param {string} [props.domainConfig.referencesField] - 참조 데이터 필드명
 * @param {Function} [props.domainConfig.renderReference] - 참조 항목 렌더링 함수
 * @param {string} [props.domainConfig.disclaimer] - 면책 문구
 */
const ChatMessage = ({ message, domainConfig }) => {
  const isUser = message.role === 'user';

  const config = {
    escalationTitle: '전문가 상담 권장',
    escalationDescription: '이 질문은 전문 변호사의 상담이 필요합니다. 정확한 법률 자문을 위해 전문가와 상담하시기 바랍니다.',
    referencesTitle: '근거 법령',
    referencesField: 'legal_references',
    renderReference: (ref, index) => (
      <li key={index} className="text-sm">
        <span className="font-medium text-blue-600">
          {ref.law_name || ref.source || '관련 법령'}
        </span>
        {ref.article && <span className="text-gray-600"> - {ref.article}</span>}
        {ref.source_type && (
          <span className="text-xs text-gray-400 ml-2">({ref.source_type})</span>
        )}
      </li>
    ),
    disclaimer: '⚠️ 본 답변은 AI가 생성한 참고 정보이며, 법적 효력이 있는 공식 법률 자문이 아닙니다. 중요한 법률적 판단이 필요한 경우 외부 전문가 자문을 받으시기 바랍니다.',
    ...domainConfig,
  };

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

  const references = message[config.referencesField] || [];
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

          {/* 메시지 내용 */}
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown components={MARKDOWN_COMPONENTS}>
              {message.content}
            </ReactMarkdown>
          </div>

          {/* 참조 정보 */}
          {references.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              <div className="flex items-center gap-2 mb-2">
                <FileText size={16} className="text-gray-600" />
                <p className="text-sm font-medium text-gray-900">{config.referencesTitle}</p>
              </div>
              <ul className="space-y-2">
                {references.map((ref, index) => config.renderReference(ref, index))}
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
