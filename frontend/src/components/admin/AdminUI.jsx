import { AlertCircle, CheckCircle2, Loader2, X } from 'lucide-react'

/**
 * 관리자 화면 공통 요소 — 채팅·계약서 화면과 같은 slate/primary 톤
 */

export function Card({ title, description, icon: Icon, action, children, className = '', bodyClassName = 'p-5' }) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-slate-100">
          <div className="min-w-0">
            <h3 className="flex items-center gap-2 text-[15px] font-semibold text-slate-900">
              {Icon && <Icon className="w-4 h-4 text-slate-500" />}
              {title}
            </h3>
            {description && <p className="mt-0.5 text-[12.5px] text-slate-500">{description}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  )
}

export function Button({ variant = 'primary', loading = false, icon: Icon, children, className = '', ...props }) {
  const variants = {
    primary: 'bg-primary-600 text-white hover:bg-primary-700 disabled:bg-primary-300',
    secondary: 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400',
    danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300',
    ghost: 'text-slate-600 hover:bg-slate-100 disabled:text-slate-300',
  }
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || loading}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium transition-colors disabled:cursor-not-allowed ${variants[variant]} ${className}`}
    >
      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : Icon && <Icon className="w-4 h-4" />}
      {children}
    </button>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="block text-[12.5px] font-medium text-slate-700 mb-1">{label}</span>
      {children}
      {hint && <span className="block mt-1 text-[11.5px] text-slate-400">{hint}</span>}
    </label>
  )
}

export const inputClass =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-primary-400 focus:ring-2 focus:ring-primary-100 disabled:bg-slate-50 disabled:text-slate-400'

/** 인라인 결과 알림 (alert 대신) */
export function Notice({ tone = 'success', title, children, onClose }) {
  const tones = {
    success: { box: 'border-emerald-200 bg-emerald-50 text-emerald-800', Icon: CheckCircle2, icon: 'text-emerald-600' },
    error: { box: 'border-red-200 bg-red-50 text-red-800', Icon: AlertCircle, icon: 'text-red-600' },
  }
  const t = tones[tone]
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`flex items-start gap-2.5 rounded-xl border px-3.5 py-3 ${t.box}`}>
      <t.Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${t.icon}`} />
      <div className="flex-1 min-w-0 text-[13px]">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={title ? 'mt-1 text-[12.5px] opacity-90' : ''}>{children}</div>}
      </div>
      {onClose && (
        <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" aria-label="알림 닫기">
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}

/** 세그먼트 선택 (채팅 화면 분야 선택과 같은 모양) */
export function Segmented({ options, value, onChange }) {
  return (
    <div className="inline-flex rounded-lg bg-slate-100 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
            value === o.value ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          {o.icon && <o.icon className="w-3.5 h-3.5" />}
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Spinner({ label = '불러오는 중…' }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-[13px] text-slate-500">
      <Loader2 className="w-4 h-4 animate-spin" />
      {label}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      {Icon && (
        <span className="w-10 h-10 rounded-xl bg-slate-100 text-slate-400 flex items-center justify-center mb-3">
          <Icon className="w-5 h-5" />
        </span>
      )}
      <p className="text-[13.5px] font-medium text-slate-700">{title}</p>
      {children && <p className="mt-1 text-[12.5px] text-slate-500">{children}</p>}
    </div>
  )
}
