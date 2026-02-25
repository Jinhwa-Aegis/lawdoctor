import { useState, useEffect, useRef } from 'react'
import { Plus, Send, Loader } from 'lucide-react'

let _msgIdCounter = 0
function nextMsgId() {
  return `msg-${Date.now()}-${++_msgIdCounter}`
}

/**
 * 채팅 페이지 공통 템플릿
 *
 * @param {Object} props
 * @param {Function} props.sendStreamFn - 스트리밍 메시지 전송 함수
 * @param {Function} props.getSessionsFn - 세션 목록 조회 함수
 * @param {Function} props.getSessionMessagesFn - 세션 메시지 조회 함수
 * @param {React.ComponentType} props.MessageComponent - 메시지 렌더링 컴포넌트
 * @param {React.ComponentType} props.sidebarIcon - 사이드바 세션 아이콘
 * @param {string} props.newChatLabel - 새 대화 버튼 라벨
 * @param {string} props.emptySessionText - 세션 없을 때 텍스트
 * @param {string} props.sessionCategoryField - 세션 카테고리 필드명
 * @param {string} props.placeholder - 입력 필드 placeholder
 * @param {React.ReactNode} props.emptyState - 빈 상태 UI
 * @param {Function} props.buildAiMessage - AI 메시지 빌더 (metadata → message fields)
 * @param {Function} props.buildStreamingMessage - 스트리밍 메시지 빌더
 */
export default function ChatPageTemplate({
  sendStreamFn,
  getSessionsFn,
  getSessionMessagesFn,
  MessageComponent,
  sidebarIcon: SidebarIcon,
  newChatLabel = '새 대화',
  emptySessionText = '대화 이력이 없습니다.\n새 대화를 시작해보세요.',
  sessionCategoryField = 'category',
  placeholder = '질문을 입력하세요...',
  emptyState,
  buildAiMessage,
  buildStreamingMessage,
}) {
  const [sessions, setSessions] = useState([])
  const [currentSessionId, setCurrentSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingMeta, setStreamingMeta] = useState(null)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    loadSessions()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  const loadSessions = async () => {
    try {
      const data = await getSessionsFn()
      setSessions(data)
    } catch (err) {
      console.error('세션 목록 로드 실패:', err)
    }
  }

  const loadSessionMessages = async (sessionId) => {
    try {
      const data = await getSessionMessagesFn(sessionId)
      setMessages(data)
      setCurrentSessionId(sessionId)
    } catch (err) {
      console.error('메시지 로드 실패:', err)
    }
  }

  const handleNewChat = () => {
    setCurrentSessionId(null)
    setMessages([])
    setStreamingContent('')
    setStreamingMeta(null)
    inputRef.current?.focus()
  }

  const handleSend = async () => {
    const text = inputText.trim()
    if (!text || isLoading) return

    const userMessage = {
      id: nextMsgId(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMessage])
    setInputText('')
    setIsLoading(true)
    setStreamingContent('')
    setStreamingMeta(null)

    try {
      let fullContent = ''
      let metadata = null

      await sendStreamFn(
        text,
        currentSessionId,
        (chunk) => {
          fullContent += chunk.content
          setStreamingContent(fullContent)
        },
        (meta) => {
          metadata = meta
          setStreamingMeta(meta)
        },
        (data) => {
          const aiMessage = {
            id: nextMsgId(),
            role: 'assistant',
            content: fullContent,
            confidence: metadata?.confidence || 'medium',
            is_escalated: metadata?.classification?.requires_escalation || false,
            created_at: new Date().toISOString(),
            ...buildAiMessage(metadata),
          }
          setMessages(prev => [...prev, aiMessage])
          setStreamingContent('')
          setStreamingMeta(null)
          setIsLoading(false)

          if (data?.session_id) {
            setCurrentSessionId(data.session_id)
            loadSessions()
          }
        }
      )
    } catch (err) {
      console.error('메시지 전송 실패:', err)
      setIsLoading(false)
      setStreamingContent('')
      const errorMessage = {
        id: nextMsgId(),
        role: 'assistant',
        content: '죄송합니다, 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
        confidence: 'low',
        is_escalated: false,
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, errorMessage])
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="h-full flex">
      {/* 세션 사이드바 */}
      <div className="w-64 bg-gray-50 border-r flex flex-col">
        <div className="p-3">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center gap-2 px-3 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm"
          >
            <Plus className="h-4 w-4" />
            {newChatLabel}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2">
          {sessions.map(session => (
            <button
              key={session.id}
              onClick={() => loadSessionMessages(session.id)}
              className={`w-full text-left px-3 py-2 rounded-lg mb-1 text-sm transition-colors ${
                currentSessionId === session.id
                  ? 'bg-primary-100 text-primary-800'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              <div className="flex items-center gap-2">
                <SidebarIcon className="h-3.5 w-3.5 flex-shrink-0" />
                <span className="truncate">{session.title}</span>
              </div>
              {session[sessionCategoryField] && (
                <span className="text-xs text-gray-500 ml-6">{session[sessionCategoryField]}</span>
              )}
            </button>
          ))}
          {sessions.length === 0 && (
            <p className="text-xs text-gray-400 text-center mt-4 px-2 whitespace-pre-line">
              {emptySessionText}
            </p>
          )}
        </div>
      </div>

      {/* 채팅 영역 */}
      <div className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && !streamingContent && emptyState && (
            <div className="h-full flex items-center justify-center">
              {emptyState({ setInputText, inputRef })}
            </div>
          )}

          {messages.map(msg => (
            <MessageComponent key={msg.id} message={msg} />
          ))}

          {streamingContent && (
            <MessageComponent
              message={{
                id: 'streaming',
                role: 'assistant',
                content: streamingContent,
                confidence: streamingMeta?.confidence,
                is_escalated: streamingMeta?.classification?.requires_escalation,
                created_at: new Date().toISOString(),
                ...buildStreamingMessage(streamingMeta),
              }}
            />
          )}

          {isLoading && !streamingContent && (
            <div className="flex items-center gap-2 text-gray-400 text-sm">
              <Loader className="h-4 w-4 animate-spin" />
              답변을 생성하고 있습니다...
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* 입력 영역 */}
        <div className="border-t p-4 bg-white">
          <div className="flex gap-2 max-w-4xl mx-auto">
            <textarea
              ref={inputRef}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              rows={1}
              className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              style={{ minHeight: '44px', maxHeight: '120px' }}
              onInput={(e) => {
                e.target.style.height = '44px'
                e.target.style.height = e.target.scrollHeight + 'px'
              }}
            />
            <button
              onClick={handleSend}
              disabled={!inputText.trim() || isLoading}
              className="px-4 py-3 bg-primary-600 text-white rounded-xl hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
