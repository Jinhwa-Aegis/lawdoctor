import { MessageSquare } from 'lucide-react'
import { sendMessageStream, getSessions, getSessionMessages, deleteSession } from '../api/client'
import ChatMessage from '../components/ChatMessage'
import ChatPageTemplate from './ChatPageTemplate'

function LegalEmptyState({ setInputText, inputRef }) {
  return (
    <div className="text-center max-w-md">
      <div className="w-16 h-16 bg-primary-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
        <MessageSquare className="h-8 w-8 text-primary-600" />
      </div>
      <h2 className="text-xl font-semibold text-gray-800 mb-2">법률 Q&A</h2>
      <p className="text-sm text-gray-500 mb-6">
        개인정보보호, 계약 검토, 공동주택관리법 등<br />
        법률 관련 질문을 자유롭게 입력해주세요.
      </p>
      <div className="grid grid-cols-2 gap-2 text-xs">
        {[
          '개인정보 제3자 제공 시 동의 요건은?',
          'NDA 계약서에 필수 포함 조항은?',
          '장기수선충당금 사용 기준은?',
          '개인정보 처리위탁 계약 시 주의사항은?',
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

function LegalMessage({ message }) {
  return <ChatMessage message={message} />
}

export default function ChatPage() {
  return (
    <ChatPageTemplate
      sendStreamFn={sendMessageStream}
      getSessionsFn={getSessions}
      getSessionMessagesFn={getSessionMessages}
      deleteSessionFn={deleteSession}
      MessageComponent={LegalMessage}
      sidebarIcon={MessageSquare}
      newChatLabel="새 대화"
      emptySessionText={'대화 이력이 없습니다.\n새 대화를 시작해보세요.'}
      sessionCategoryField="category"
      placeholder="법률 관련 질문을 입력하세요..."
      emptyState={LegalEmptyState}
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
