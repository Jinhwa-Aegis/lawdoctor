import { Scale } from 'lucide-react'
import {
  sendMessageStream,
  getSessions,
  getSessionMessages,
  deleteSession,
  refineQuestion,
} from '../api/client'
import ChatMessage from '../components/ChatMessage'
import ChatPageTemplate from './ChatPageTemplate'

const LEGAL_CATEGORY_LABELS = {
  privacy: '개인정보보호',
  contract: '계약',
  housing: '공동주택관리',
  litigation: '소송·분쟁',
}

// 분야 직접 선택 — 첫 값은 자동 판단 (소송·분쟁은 경영진 전용이라 제외)
const DOMAIN_OPTIONS = [
  { value: 'auto', label: '자동', description: '질문 내용으로 분야를 자동 판단합니다' },
  { value: 'privacy', label: '개인정보', description: '개인정보 보호법·정보통신망법' },
  { value: 'contract', label: '계약', description: '민법·상법 등 계약 일반' },
  { value: 'housing', label: '공동주택', description: '공동주택관리법·주택법' },
]

// 이지스엔터프라이즈 실무에서 자주 나오는 상황형 질문
const EXAMPLES = [
  { tag: '개인정보', text: '아파트 관리사무소가 CCTV 영상을 입주민에게 보여줘도 되나요? 관리업무는 우리 회사가 위탁받아 하고 있습니다.' },
  { tag: '개인정보', text: '입주민 정보를 처리하는 솔루션을 외부 업체에 개발 위탁할 때 위탁계약서에 꼭 들어가야 할 내용은?' },
  { tag: '계약', text: '협력사가 보낸 NDA에 위반 시 위약벌 5억 원 조항이 있습니다. 그대로 서명해도 괜찮을까요?' },
  { tag: '계약', text: 'SI 용역계약에서 검수 기한을 넘기면 자동으로 검수된 것으로 보는 조항을 넣을 수 있나요?' },
  { tag: '공동주택', text: '장기수선충당금을 승강기 교체가 아닌 단순 수리에 써도 되는지, 입주자대표회의 의결이 필요한가요?' },
  { tag: '공동주택', text: '관리비 부과 내역을 입주민 앱에 공개할 때 법적으로 공개해야 하는 항목은 무엇인가요?' },
]

function LegalMessage(props) {
  return <ChatMessage {...props} />
}

export default function ChatPage() {
  return (
    <ChatPageTemplate
      sendStreamFn={sendMessageStream}
      getSessionsFn={getSessions}
      getSessionMessagesFn={getSessionMessages}
      deleteSessionFn={deleteSession}
      refineFn={refineQuestion}
      MessageComponent={LegalMessage}
      newChatLabel="새 대화"
      emptySessionText={'대화 이력이 없습니다.\n새 대화를 시작해보세요.'}
      sessionCategoryField="category"
      categoryLabels={LEGAL_CATEGORY_LABELS}
      placeholder="상황을 구체적으로 적을수록 정확합니다. 예) 누가, 어떤 계약/업무에서, 무엇을 하려는지"
      hero={{
        icon: Scale,
        title: '법률 Q&A',
        subtitle: '개인정보보호·계약·공동주택관리 질문에 근거 법령을 확인해 답합니다.',
      }}
      examples={EXAMPLES}
      domainOptions={DOMAIN_OPTIONS}
      disclaimer="AI 답변은 법적 효력이 있는 자문이 아닙니다. 계약 체결·분쟁 등 중요한 결정 전에는 외부 전문가와 상담하세요."
      buildAiMessage={(metadata) => ({
        legal_references: metadata?.legal_references || [],
        citations: metadata?.citations || [],
      })}
      buildStreamingMessage={(meta) => ({
        legal_references: meta?.legal_references,
        citations: meta?.citations,
      })}
    />
  )
}
