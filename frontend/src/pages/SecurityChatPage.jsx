import { Shield } from 'lucide-react'
import { sendSecurityMessageStream, getSecuritySessions, getSecuritySessionMessages } from '../api/client'
import ChatMessage from '../components/ChatMessage'
import ChatPageTemplate from './ChatPageTemplate'

const SECURITY_DOMAIN_CONFIG = {
  escalationTitle: '보안 전문가 상담 권장',
  escalationDescription: '이 질문은 보안 전문가의 상담이 필요합니다. 정보보안 담당자 또는 외부 보안 전문가와 상담하시기 바랍니다.',
  referencesTitle: '참고 보안 기준',
  referencesField: 'security_references',
  renderReference: (ref, index) => (
    <li key={index} className="text-sm">
      <span className="font-medium text-blue-600">
        {ref.guide_name || ref.standard || ref.source || '보안 가이드'}
      </span>
      {ref.section && <span className="text-gray-600"> — {ref.section}</span>}
    </li>
  ),
  disclaimer: '⚠️ 본 답변은 AI가 생성한 참고 정보이며, 조직의 보안 정책을 대체하는 공식 보안 자문이 아닙니다. 중요한 보안 결정이 필요한 경우 정보보안 담당자 또는 외부 보안 전문가와 상담하시기 바랍니다.',
}

function SecurityMessage({ message }) {
  return <ChatMessage message={message} domainConfig={SECURITY_DOMAIN_CONFIG} />
}

function SecurityEmptyState({ setInputText, inputRef }) {
  return (
    <div className="text-center max-w-md">
      <div className="w-16 h-16 bg-primary-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
        <Shield className="h-8 w-8 text-primary-600" />
      </div>
      <h2 className="text-xl font-semibold text-gray-800 mb-2">정보보안 Q&A</h2>
      <p className="text-sm text-gray-500 mb-6">
        네트워크·시스템·애플리케이션·클라우드 보안,<br />
        ISMS-P/컴플라이언스 관련 질문을 자유롭게 입력해주세요.
      </p>
      <div className="grid grid-cols-2 gap-2 text-xs">
        {[
          'ISMS-P 인증 심사 준비 항목은?',
          'OWASP Top 10 대응 방안은?',
          'AWS S3 버킷 보안 설정 방법은?',
          '랜섬웨어 대응 절차는?',
        ].map((q, i) => (
          <button
            key={i}
            onClick={() => { setInputText(q); inputRef.current?.focus() }}
            className="p-2 bg-gray-50 border rounded-lg text-gray-600 hover:bg-gray-100 hover:border-primary-300 transition-all text-left"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function SecurityChatPage() {
  return (
    <ChatPageTemplate
      sendStreamFn={sendSecurityMessageStream}
      getSessionsFn={getSecuritySessions}
      getSessionMessagesFn={getSecuritySessionMessages}
      MessageComponent={SecurityMessage}
      sidebarIcon={Shield}
      newChatLabel="새 보안 상담"
      emptySessionText={'보안 상담 이력이 없습니다.\n새 상담을 시작해보세요.'}
      sessionCategoryField="security_category"
      placeholder="정보보안 관련 질문을 입력하세요..."
      emptyState={SecurityEmptyState}
      buildAiMessage={(metadata) => ({
        security_references: metadata?.security_references || [],
      })}
      buildStreamingMessage={(meta) => ({
        security_references: meta?.security_references,
      })}
    />
  )
}
