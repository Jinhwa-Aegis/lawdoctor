import { useState, useEffect, useRef, useCallback } from 'react'
import { PanelLeftOpen, Plus } from 'lucide-react'
import Composer from '../components/chat/Composer'
import HistoryPanel from '../components/chat/HistoryPanel'

let _msgIdCounter = 0
function nextMsgId() {
  return `msg-${Date.now()}-${++_msgIdCounter}`
}

const HISTORY_OPEN_KEY = 'lawdoctor.historyOpen'

function readHistoryOpen() {
  try {
    return localStorage.getItem(HISTORY_OPEN_KEY) !== 'false'
  } catch {
    return true
  }
}

/**
 * 채팅 페이지 공통 템플릿 (법률 Q&A / 보안 Q&A)
 *
 * @param {Object} props
 * @param {Function} props.sendStreamFn - (text, sessionId, onChunk, onMeta, onDone, onEvent, {category, signal})
 * @param {Function} props.getSessionsFn
 * @param {Function} props.getSessionMessagesFn
 * @param {Function} props.deleteSessionFn
 * @param {Function} [props.refineFn] - 질문 다듬기 (없으면 버튼 숨김)
 * @param {React.ComponentType} props.MessageComponent
 * @param {{icon: React.ComponentType, title: string, subtitle: string}} props.hero - 첫 화면 문구
 * @param {Array<{text: string, tag?: string}>} props.examples - 예시 질문
 * @param {Array<{value: string, label: string}>} [props.domainOptions] - 분야 직접 선택 (첫 값은 자동)
 * @param {string} props.disclaimer - 입력창 아래 한 줄 면책 문구
 */
export default function ChatPageTemplate({
  sendStreamFn,
  getSessionsFn,
  getSessionMessagesFn,
  deleteSessionFn,
  refineFn,
  MessageComponent,
  newChatLabel = '새 대화',
  emptySessionText = '대화 이력이 없습니다.\n새 대화를 시작해보세요.',
  sessionCategoryField = 'category',
  categoryLabels = {},
  placeholder = '질문을 입력하세요...',
  hero,
  examples = [],
  domainOptions = null,
  disclaimer,
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
  // 답변 생성 단계: searching → writing → verifying
  const [stage, setStage] = useState(null)
  const [isPostProcessing, setIsPostProcessing] = useState(false)
  const [streamingAnswerMeta, setStreamingAnswerMeta] = useState(null)
  // 분야 간 의견 대조: 검토 대상 분야 이름, 분야별 검토 결과
  const [perspectiveDomains, setPerspectiveDomains] = useState([])
  const [streamingPerspectives, setStreamingPerspectives] = useState(null)
  const [historyOpen, setHistoryOpen] = useState(readHistoryOpen)
  const [domain, setDomain] = useState(domainOptions?.[0]?.value ?? null)

  const scrollRef = useRef(null)
  const composerRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    loadSessions()
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_OPEN_KEY, String(historyOpen))
    } catch {
      // 저장 불가 환경 — 무시
    }
  }, [historyOpen])

  // 새 내용이 생기면 맨 아래로 (사용자가 위로 올려 읽는 중이면 유지)
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160
    if (nearBottom || !isLoading) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, streamingContent, stage, isLoading])

  const loadSessions = async () => {
    try {
      setSessions(await getSessionsFn())
    } catch (err) {
      console.error('세션 목록 로드 실패:', err)
    }
  }

  const loadSessionMessages = async (sessionId) => {
    if (isLoading) return
    try {
      setMessages(await getSessionMessagesFn(sessionId))
      setCurrentSessionId(sessionId)
    } catch (err) {
      console.error('메시지 로드 실패:', err)
    }
  }

  const resetStreaming = () => {
    setStreamingContent('')
    setStreamingMeta(null)
    setStreamingAnswerMeta(null)
    setIsPostProcessing(false)
    setStage(null)
    setPerspectiveDomains([])
    setStreamingPerspectives(null)
  }

  const handleNewChat = () => {
    if (isLoading) return
    setCurrentSessionId(null)
    setMessages([])
    resetStreaming()
    composerRef.current?.focus()
  }

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation()
    if (!confirm('이 대화를 삭제하시겠습니까?')) return
    try {
      await deleteSessionFn(sessionId)
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null)
        setMessages([])
      }
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
    } catch (err) {
      console.error('세션 삭제 실패:', err)
      alert('삭제에 실패했습니다.')
    }
  }

  const handleStop = () => abortRef.current?.abort()

  // overrideText: 후속 질문 칩·다시 묻기에서 입력창을 거치지 않고 바로 전송
  const handleSend = async (overrideText) => {
    const text = (typeof overrideText === 'string' ? overrideText : inputText).trim()
    if (!text || isLoading) return

    setMessages((prev) => [...prev, {
      id: nextMsgId(), role: 'user', content: text, created_at: new Date().toISOString(),
    }])
    if (typeof overrideText !== 'string') setInputText('')
    setIsLoading(true)
    resetStreaming()
    setStage('searching')

    const controller = new AbortController()
    abortRef.current = controller

    let fullContent = ''
    let metadata = null
    let answerMeta = null
    let perspectives = null
    let doneReceived = false

    const finishWith = (extra) => {
      setMessages((prev) => [...prev, {
        id: nextMsgId(),
        role: 'assistant',
        content: fullContent,
        confidence: answerMeta?.confidence || metadata?.confidence || 'medium',
        is_escalated: metadata?.classification?.requires_escalation || false,
        answer_meta: answerMeta,
        category: metadata?.classification?.category,
        perspective_domains: metadata?.perspective_domains || [],
        created_at: new Date().toISOString(),
        ...buildAiMessage(metadata),
        ...extra,
      }])
    }

    try {
      await sendStreamFn(
        text,
        currentSessionId,
        (chunk) => {
          fullContent += chunk.content
          setStreamingContent(fullContent)
          setStage('writing')
        },
        (meta) => {
          metadata = meta
          setStreamingMeta(meta)
          if (meta?.perspective_domains?.length) {
            setPerspectiveDomains(meta.perspective_domains)
            setStage('perspectives')
          } else {
            setStage('writing')
          }
        },
        (data) => {
          doneReceived = true
          // 서버 메시지 ID를 사용해야 피드백이 해당 답변에 저장된다
          finishWith({ id: data?.message_id ?? nextMsgId() })
          if (data?.session_id) {
            setCurrentSessionId(data.session_id)
            loadSessions()
          }
        },
        (event) => {
          if (event.type === 'status' && event.stage === 'post_processing') {
            setIsPostProcessing(true)
            setStage('verifying')
          } else if (event.type === 'status' && event.stage === 'perspectives') {
            setStage('perspectives')
          } else if (event.type === 'perspectives') {
            perspectives = event.items || []
            setStreamingPerspectives(perspectives)
          } else if (event.type === 'answer_meta') {
            answerMeta = {
              perspectives: event.perspectives || perspectives || undefined,
              verified_citations: event.verified_citations || [],
              followups: event.followups || [],
              confidence: event.confidence,
              confidence_reason: event.confidence_reason,
              confidence_adjustments: event.confidence_adjustments || [],
            }
            setStreamingAnswerMeta(answerMeta)
            setIsPostProcessing(false)
          }
        },
        { category: domain && domain !== 'auto' ? domain : null, signal: controller.signal },
      )

      // 서버가 done 없이 스트림을 끊은 경우 (서버 오류·네트워크 단절)
      if (!doneReceived) {
        finishWith({
          content: fullContent
            ? `${fullContent}\n\n---\n_⚠️ 응답이 중간에 끊겨 저장되지 않았습니다. 다시 질문해주세요._`
            : '죄송합니다, 응답이 중간에 끊겼습니다. 잠시 후 다시 시도해주세요.',
          confidence: 'low',
        })
      }
    } catch (err) {
      if (err?.name === 'AbortError') {
        finishWith({
          content: fullContent
            ? `${fullContent}\n\n---\n_답변 생성을 중단했습니다. 중단된 답변은 기록에 저장되지 않습니다._`
            : '_답변 생성을 중단했습니다._',
          answer_meta: null,
          aborted: true,
        })
      } else {
        console.error('메시지 전송 실패:', err)
        setMessages((prev) => [...prev, {
          id: nextMsgId(),
          role: 'assistant',
          content: err?.message && !err.message.startsWith('Failed')
            ? `죄송합니다. ${err.message}`
            : '죄송합니다, 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
          confidence: 'low',
          is_escalated: false,
          created_at: new Date().toISOString(),
        }])
      }
    } finally {
      abortRef.current = null
      resetStreaming()
      setIsLoading(false)
    }
  }

  // 후속 질문·다시 묻기 — 참조를 고정해 메시지 컴포넌트(React.memo) 재렌더링을 막는다
  const handleSendRef = useRef(handleSend)
  handleSendRef.current = handleSend
  const handleFollowup = useCallback((question) => handleSendRef.current(question), [])

  const handleEditQuestion = useCallback((text) => {
    setInputText(text)
    composerRef.current?.focus()
  }, [])

  const handlePickExample = (text) => {
    setInputText(text)
    composerRef.current?.focus()
  }

  const currentTitle = sessions.find((s) => s.id === currentSessionId)?.title
  const isEmpty = messages.length === 0 && !isLoading
  const HeroIcon = hero?.icon

  // 각 답변에 대응하는 직전 질문 (내보내기·다시 묻기용)
  const questionFor = (idx) => {
    for (let i = idx - 1; i >= 0; i--) if (messages[i].role === 'user') return messages[i].content
    return ''
  }
  const lastAssistantIdx = messages.map((m) => m.role).lastIndexOf('assistant')

  const composer = (
    <Composer
      ref={composerRef}
      value={inputText}
      onChange={setInputText}
      onSubmit={() => handleSend()}
      onStop={handleStop}
      onRefine={refineFn}
      isLoading={isLoading}
      placeholder={placeholder}
      disclaimer={disclaimer}
      size={isEmpty ? 'large' : 'default'}
    />
  )

  return (
    <div className="h-full flex">
      {historyOpen && (
        <HistoryPanel
          sessions={sessions}
          currentSessionId={currentSessionId}
          onSelect={loadSessionMessages}
          onDelete={handleDeleteSession}
          onNewChat={handleNewChat}
          onClose={() => setHistoryOpen(false)}
          newChatLabel={newChatLabel}
          emptyText={emptySessionText}
          categoryField={sessionCategoryField}
          categoryLabels={categoryLabels}
        />
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        {/* 상단 바 */}
        <header className="h-14 flex-shrink-0 flex items-center justify-between gap-4 px-4 border-b border-slate-200 bg-white/80 backdrop-blur">
          <div className="flex items-center gap-2 min-w-0">
            {!historyOpen && (
              <>
                <button
                  type="button"
                  onClick={() => setHistoryOpen(true)}
                  className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                  title="대화 기록 열기"
                >
                  <PanelLeftOpen className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                  title={newChatLabel}
                >
                  <Plus className="w-4 h-4" />
                </button>
              </>
            )}
            <h1 className="text-[14px] font-semibold text-slate-800 truncate">
              {currentTitle || (messages.length ? '새 대화' : hero?.title)}
            </h1>
          </div>

          {domainOptions && (
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className="text-[12px] text-slate-400 hidden md:inline">분야</span>
              <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1">
                {domainOptions.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setDomain(opt.value)}
                    disabled={isLoading}
                    className={`h-7 px-3 rounded-lg text-[12px] font-medium transition-colors ${
                      domain === opt.value
                        ? 'bg-white text-primary-700 shadow-sm'
                        : 'text-slate-500 hover:text-slate-800'
                    }`}
                    title={opt.description}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </header>

        {isEmpty ? (
          /* 첫 화면 */
          <div className="flex-1 overflow-y-auto scrollbar-thin">
            <div className="max-w-3xl mx-auto px-6 pt-[12vh] pb-12">
              <div className="text-center mb-8">
                {HeroIcon && (
                  <span className="inline-flex w-12 h-12 rounded-2xl bg-primary-50 text-primary-600 items-center justify-center mb-4">
                    <HeroIcon className="w-6 h-6" />
                  </span>
                )}
                <h2 className="text-[26px] font-bold tracking-tight text-slate-900">무엇을 도와드릴까요?</h2>
                {hero?.subtitle && <p className="mt-2 text-[15px] text-slate-500">{hero.subtitle}</p>}
              </div>

              {composer}

              {examples.length > 0 && (
                <div className="mt-8">
                  <p className="text-[12px] font-medium text-slate-400 mb-3">이런 질문을 많이 합니다</p>
                  <div className="grid sm:grid-cols-2 gap-2.5">
                    {examples.map((ex) => (
                      <button
                        key={ex.text}
                        type="button"
                        onClick={() => handlePickExample(ex.text)}
                        className="group text-left p-3.5 rounded-xl border border-slate-200 bg-white hover:border-primary-300 hover:shadow-sm transition-all"
                      >
                        {ex.tag && (
                          <span className="inline-block mb-1.5 text-[11px] font-medium text-primary-600 bg-primary-50 rounded px-1.5 py-0.5">
                            {ex.tag}
                          </span>
                        )}
                        <p className="text-[13.5px] leading-snug text-slate-700 group-hover:text-slate-900">{ex.text}</p>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <>
            {/* 대화 */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
              <div className="max-w-3xl mx-auto px-6 py-8 space-y-8">
                {messages.map((msg, idx) => (
                  <MessageComponent
                    key={msg.id}
                    message={msg}
                    question={msg.role === 'assistant' ? questionFor(idx) : undefined}
                    isLast={idx === lastAssistantIdx && !isLoading}
                    onFollowup={handleFollowup}
                    onEditQuestion={handleEditQuestion}
                    categoryLabels={categoryLabels}
                  />
                ))}

                {isLoading && (
                  <MessageComponent
                    message={{
                      id: 'streaming',
                      role: 'assistant',
                      content: streamingContent,
                      confidence: streamingMeta?.confidence,
                      is_escalated: streamingMeta?.classification?.requires_escalation,
                      answer_meta: {
                        ...(streamingAnswerMeta || {}),
                        perspectives: streamingAnswerMeta?.perspectives || streamingPerspectives || undefined,
                      },
                      perspective_domains: perspectiveDomains,
                      category: streamingMeta?.classification?.category,
                      created_at: new Date().toISOString(),
                      ...buildStreamingMessage(streamingMeta),
                    }}
                    isStreaming
                    stage={stage}
                    isPostProcessing={isPostProcessing}
                    categoryLabels={categoryLabels}
                  />
                )}
              </div>
            </div>

            {/* 입력 */}
            <div className="flex-shrink-0 bg-gradient-to-t from-slate-50 via-slate-50 to-slate-50/0 pt-2 pb-4 px-6">
              <div className="max-w-3xl mx-auto">{composer}</div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
