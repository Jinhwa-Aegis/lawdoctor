import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react'
import { ArrowUp, Square, Sparkles, Undo2, Loader2 } from 'lucide-react'

const MIN_HEIGHT = 52
const MAX_HEIGHT = 220

/**
 * 질문 입력창
 *
 * - 내용에 맞춰 높이 자동 조절 (Enter 전송, Shift+Enter 줄바꿈)
 * - "다듬기": 모호한 질문을 답변하기 좋은 형태로 정리 (되돌리기 가능)
 * - 답변 생성 중에는 전송 버튼이 중단 버튼으로 바뀜
 */
const Composer = forwardRef(function Composer(
  { value, onChange, onSubmit, onStop, onRefine, isLoading, placeholder, disclaimer, size = 'default' },
  ref,
) {
  const textareaRef = useRef(null)
  const [isRefining, setIsRefining] = useState(false)
  const [beforeRefine, setBeforeRefine] = useState(null)
  const [refineError, setRefineError] = useState('')

  useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }))

  // 높이 자동 조절
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = `${MIN_HEIGHT}px`
    el.style.height = `${Math.min(Math.max(el.scrollHeight, MIN_HEIGHT), MAX_HEIGHT)}px`
  }, [value])

  // 사용자가 직접 수정하면 되돌리기 해제
  const handleChange = (e) => {
    setBeforeRefine(null)
    setRefineError('')
    onChange(e.target.value)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (!isLoading) onSubmit()
    }
  }

  const handleRefine = async () => {
    if (!onRefine || !value.trim() || isRefining) return
    setIsRefining(true)
    setRefineError('')
    try {
      const refined = await onRefine(value)
      if (refined && refined !== value) {
        setBeforeRefine(value)
        onChange(refined)
      }
    } catch {
      setRefineError('다듬기에 실패했습니다. 잠시 후 다시 시도해주세요.')
    } finally {
      setIsRefining(false)
      textareaRef.current?.focus()
    }
  }

  const handleUndo = () => {
    if (beforeRefine === null) return
    onChange(beforeRefine)
    setBeforeRefine(null)
    textareaRef.current?.focus()
  }

  const canSend = value.trim().length > 0 && !isRefining
  const large = size === 'large'

  return (
    <div className="w-full">
      <div
        className={`rounded-2xl border bg-white transition-shadow ${
          large ? 'shadow-md border-slate-200' : 'shadow-sm border-slate-200'
        } focus-within:border-primary-400 focus-within:shadow-[0_0_0_4px_rgba(59,130,246,0.12)]`}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          disabled={isRefining}
          className={`block w-full resize-none bg-transparent px-5 pt-4 pb-1 text-[15px] leading-relaxed text-slate-900 placeholder:text-slate-400 focus:outline-none scrollbar-thin ${
            isRefining ? 'opacity-60' : ''
          }`}
          style={{ minHeight: MIN_HEIGHT, maxHeight: MAX_HEIGHT }}
        />

        <div className="flex items-center justify-between gap-2 px-3 pb-3 pt-1">
          <div className="flex items-center gap-1">
            {onRefine && (
              <button
                type="button"
                onClick={handleRefine}
                disabled={!value.trim() || isRefining || isLoading}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-[13px] font-medium text-slate-600 hover:bg-amber-50 hover:text-amber-700 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-slate-600 transition-colors"
                title="모호한 질문을 답변하기 좋은 형태로 정리합니다"
              >
                {isRefining ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 text-amber-500" />}
                {isRefining ? '다듬는 중' : '질문 다듬기'}
              </button>
            )}
            {beforeRefine !== null && (
              <button
                type="button"
                onClick={handleUndo}
                className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg text-[13px] text-slate-500 hover:bg-slate-100"
              >
                <Undo2 className="w-3.5 h-3.5" />
                원래대로
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden sm:inline text-[12px] text-slate-400">Shift+Enter 줄바꿈</span>
            {isLoading ? (
              <button
                type="button"
                onClick={onStop}
                className="inline-flex items-center gap-1.5 h-9 px-4 rounded-xl bg-slate-900 text-white text-[13px] font-semibold hover:bg-slate-700 transition-colors"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                중단
              </button>
            ) : (
              <button
                type="button"
                onClick={onSubmit}
                disabled={!canSend}
                className="inline-flex items-center gap-1.5 h-9 px-4 rounded-xl bg-primary-600 text-white text-[13px] font-semibold hover:bg-primary-700 disabled:bg-slate-200 disabled:text-slate-400 transition-colors"
              >
                질문하기
                <ArrowUp className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {refineError && <p className="mt-2 text-xs text-red-600">{refineError}</p>}
      {beforeRefine !== null && !refineError && (
        <p className="mt-2 text-xs text-amber-700">
          질문을 다듬었습니다. <span className="text-slate-500">[대괄호] 부분을 채우면 더 정확한 답변을 받을 수 있습니다.</span>
        </p>
      )}
      {disclaimer && <p className="mt-2 text-center text-[11px] text-slate-400">{disclaimer}</p>}
    </div>
  )
})

export default Composer
