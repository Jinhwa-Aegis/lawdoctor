import { Shield } from 'lucide-react'
import {
  sendSecurityMessageStream,
  getSecuritySessions,
  getSecuritySessionMessages,
  deleteSecuritySession,
  refineQuestion,
} from '../api/client'
import ChatMessage from '../components/ChatMessage'
import ChatPageTemplate from './ChatPageTemplate'

const SECURITY_DOMAIN_CONFIG = {
  assistantName: '보안 어시스턴트',
  escalationTitle: '보안 담당자 확인 권장',
  escalationDescription: '보안 사고 또는 고위험 사안이 포함되어 있습니다. 조치 전에 정보보안 담당자 또는 외부 보안 전문가와 상의하시기 바랍니다.',
  referencesTitle: '참고 보안 기준',
  referencesField: 'security_references',
  disclaimer: '본 답변은 AI가 생성한 참고 정보이며, 조직의 보안 정책을 대체하는 공식 보안 자문이 아닙니다. 중요한 보안 결정이 필요한 경우 정보보안 담당자 또는 외부 보안 전문가와 상담하시기 바랍니다.',
}

const SECURITY_CATEGORY_LABELS = {
  network: '네트워크 보안',
  system: '시스템 보안',
  application: '애플리케이션 보안',
  cloud: '클라우드 보안',
  compliance: '컴플라이언스',
  data_protection: '데이터 보호',
  incident: '보안 사고 대응',
  audit: '보안 감사',
}

const EXAMPLES = [
  { tag: '컴플라이언스', text: 'ISMS-P 인증 심사를 처음 준비합니다. 우선 갖춰야 할 관리체계 항목이 무엇인가요?' },
  { tag: '보안 사고 대응', text: '직원 PC가 랜섬웨어에 감염된 것 같습니다. 첫 1시간 안에 해야 할 조치를 순서대로 알려주세요.' },
  { tag: '클라우드 보안', text: '입주민 데이터를 저장하는 AWS S3 버킷의 접근 권한을 어떻게 점검해야 하나요?' },
  { tag: '애플리케이션 보안', text: '관리비 조회 웹에서 OWASP Top 10 중 가장 먼저 점검할 취약점은 무엇인가요?' },
]

function SecurityMessage(props) {
  return <ChatMessage {...props} domainConfig={SECURITY_DOMAIN_CONFIG} />
}

export default function SecurityChatPage() {
  return (
    <ChatPageTemplate
      sendStreamFn={sendSecurityMessageStream}
      getSessionsFn={getSecuritySessions}
      getSessionMessagesFn={getSecuritySessionMessages}
      deleteSessionFn={deleteSecuritySession}
      refineFn={refineQuestion}
      MessageComponent={SecurityMessage}
      newChatLabel="새 보안 상담"
      emptySessionText={'보안 상담 이력이 없습니다.\n새 상담을 시작해보세요.'}
      sessionCategoryField="security_category"
      categoryLabels={SECURITY_CATEGORY_LABELS}
      placeholder="상황을 구체적으로 적을수록 정확합니다. 예) 어떤 시스템에서, 무슨 일이, 언제 발생했는지"
      hero={{
        icon: Shield,
        title: '정보보안 Q&A',
        subtitle: '네트워크·시스템·클라우드 보안부터 ISMS-P, 사고 대응까지 보안 기준을 근거로 답합니다.',
      }}
      examples={EXAMPLES}
      disclaimer="AI 답변은 참고용이며 조직의 보안 정책을 대체하지 않습니다. 실제 조치 전 정보보안 담당자와 확인하세요."
      buildAiMessage={(metadata) => ({
        security_references: metadata?.security_references || [],
        citations: metadata?.citations || [],
      })}
      buildStreamingMessage={(meta) => ({
        security_references: meta?.security_references,
        citations: meta?.citations,
      })}
    />
  )
}
