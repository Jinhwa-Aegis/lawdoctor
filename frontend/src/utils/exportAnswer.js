/**
 * 답변 내보내기 — 복사, Word(.doc), 인쇄/PDF
 *
 * 렌더링된 답변 HTML을 그대로 사용하므로 표·목록 서식이 유지된다.
 * 모든 내보내기 결과에 면책 문구를 포함한다 (CLAUDE.md 법률 도메인 규칙).
 */

const EXPORT_STYLES = `
  body { font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; font-size: 11pt; line-height: 1.7; color: #1e293b; margin: 24px; }
  h1 { font-size: 16pt; margin: 0 0 4px; }
  .meta { color: #64748b; font-size: 9pt; margin-bottom: 16px; }
  .question { background: #f1f5f9; padding: 10px 14px; border-radius: 6px; margin-bottom: 16px; }
  h3 { font-size: 12pt; margin: 18px 0 6px; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0; }
  th, td { border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; vertical-align: top; }
  th { background: #e2e8f0; }
  .disclaimer { margin-top: 24px; padding: 10px 14px; border: 1px solid #fcd34d; background: #fffbeb; font-size: 9pt; color: #92400e; }
  button { display: none; }
`

function escapeHtml(text) {
  return String(text || '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ))
}

function buildDocument({ title, question, answerHtml, disclaimer }) {
  const now = new Date().toLocaleString('ko-KR')
  return `<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>
<style>${EXPORT_STYLES}</style></head>
<body>
  <h1>${escapeHtml(title)}</h1>
  <div class="meta">법무주치의 · ${escapeHtml(now)}</div>
  ${question ? `<div class="question"><strong>질문</strong><br>${escapeHtml(question)}</div>` : ''}
  ${answerHtml}
  <div class="disclaimer">⚠️ ${escapeHtml(disclaimer)}</div>
</body></html>`
}

function safeFileName(name) {
  return (name || '법률답변').replace(/[\\/:*?"<>|]/g, '').slice(0, 40)
}

export async function copyAnswer(markdown) {
  await navigator.clipboard.writeText(markdown)
}

export function downloadWord({ title, question, answerHtml, disclaimer }) {
  const html = buildDocument({ title, question, answerHtml, disclaimer })
  const blob = new Blob(['﻿', html], { type: 'application/msword' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${safeFileName(title)}.doc`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** 새 창에서 인쇄 대화상자를 연다 (PDF로 저장 가능) */
export function printAnswer({ title, question, answerHtml, disclaimer }) {
  const win = window.open('', '_blank', 'width=900,height=1000')
  if (!win) return false
  win.document.open()
  win.document.write(buildDocument({ title, question, answerHtml, disclaimer }))
  win.document.close()
  win.focus()
  // 글꼴·레이아웃 적용 후 인쇄
  setTimeout(() => win.print(), 300)
  return true
}
