const BASE_URL = '/api'

function getUserId() {
  let userId = localStorage.getItem('userId')
  if (!userId) {
    userId = '1'
    localStorage.setItem('userId', userId)
  }
  return userId
}

function getHeaders() {
  return {
    'Content-Type': 'application/json',
    'X-User-ID': getUserId(),
  }
}

export async function getCurrentUser() {
  const response = await fetch(`${BASE_URL}/auth/me`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '사용자 정보를 불러올 수 없습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function sendMessage(message, sessionId = null) {
  const response = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ message, session_id: sessionId }),
  })

  if (!response.ok) {
    let message = '메시지 전송에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

async function parseSSEStream(response, onChunk, onMetadata, onDone) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()

      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.trim() || !line.startsWith('data: ')) continue

        const data = line.slice(6)
        if (data === '[DONE]') continue

        try {
          const parsed = JSON.parse(data)

          if (parsed.type === 'text' && onChunk) {
            onChunk(parsed)
          } else if (parsed.type === 'metadata' && onMetadata) {
            onMetadata(parsed)
          } else if (parsed.type === 'done' && onDone) {
            onDone(parsed)
          }
        } catch (e) {
          console.error('Failed to parse SSE data:', e)
        }
      }
    }

    // 스트림 종료 후 잔여 버퍼 처리
    if (buffer.trim()) {
      const line = buffer.trim()
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data !== '[DONE]') {
          try {
            const parsed = JSON.parse(data)
            if (parsed.type === 'text' && onChunk) onChunk(parsed)
            else if (parsed.type === 'metadata' && onMetadata) onMetadata(parsed)
            else if (parsed.type === 'done' && onDone) onDone(parsed)
          } catch (e) {
            console.error('SSE 잔여 데이터 파싱 실패:', e)
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function sendMessageStream(message, sessionId, onChunk, onMetadata, onDone) {
  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ message, session_id: sessionId }),
  })

  if (!response.ok) {
    let errorMessage = '메시지 전송에 실패했습니다'
    try {
      const body = await response.json()
      errorMessage = body.detail || body.message || errorMessage
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(errorMessage)
  }

  await parseSSEStream(response, onChunk, onMetadata, onDone)
}

export async function getSessions() {
  const response = await fetch(`${BASE_URL}/chat/sessions`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '세션 목록을 불러올 수 없습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function getSessionMessages(sessionId) {
  const response = await fetch(`${BASE_URL}/chat/sessions/${sessionId}/messages`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '메시지 이력을 불러올 수 없습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function uploadContract(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${BASE_URL}/review`, {
    method: 'POST',
    headers: {
      'X-User-ID': getUserId(),
    },
    body: formData,
  })

  if (!response.ok) {
    let message = '계약서 업로드에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function sendFeedback(messageId, feedbackType, reason = null, comment = null) {
  const response = await fetch(`${BASE_URL}/feedback`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      message_id: messageId,
      feedback_type: feedbackType,
      reason,
      comment,
    }),
  })

  if (!response.ok) {
    let message = '피드백 전송에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function getFeedbackStats(days = 7) {
  const response = await fetch(`${BASE_URL}/feedback/stats?days=${days}`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '피드백 통계를 불러올 수 없습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function getUsers() {
  const response = await fetch(`${BASE_URL}/admin/users`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '사용자 목록을 불러올 수 없습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function createUser(data) {
  const response = await fetch(`${BASE_URL}/admin/users`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    let message = '사용자 생성에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function getDashboard() {
  const response = await fetch(`${BASE_URL}/admin/dashboard`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '대시보드 데이터를 불러올 수 없습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

// === 정보보안 Q&A API ===

export async function sendSecurityMessageStream(message, sessionId, onChunk, onMetadata, onDone) {
  const response = await fetch(`${BASE_URL}/security/stream`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ message, session_id: sessionId }),
  })

  if (!response.ok) {
    let errorMessage = '보안 메시지 전송에 실패했습니다'
    try {
      const body = await response.json()
      errorMessage = body.detail || body.message || errorMessage
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(errorMessage)
  }

  await parseSSEStream(response, onChunk, onMetadata, onDone)
}

export async function getSecuritySessions() {
  const response = await fetch(`${BASE_URL}/security/sessions`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '보안 세션 목록을 불러올 수 없습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function getSecuritySessionMessages(sessionId) {
  const response = await fetch(`${BASE_URL}/security/sessions/${sessionId}/messages`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '보안 메시지 이력을 불러올 수 없습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

// === 관리자 PDF 업로드 API ===

export async function uploadLegalPdf(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${BASE_URL}/admin/upload/legal`, {
    method: 'POST',
    headers: {
      'X-User-ID': getUserId(),
    },
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '법률 PDF 업로드에 실패했습니다.')
  }

  return response.json()
}

export async function uploadSecurityPdf(file, metadata = {}) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('collection', metadata.collection || 'security_guides')
  formData.append('guide_name', metadata.guide_name || '')
  formData.append('standard', metadata.standard || '')
  formData.append('section', metadata.section || '')

  const response = await fetch(`${BASE_URL}/admin/upload/security`, {
    method: 'POST',
    headers: {
      'X-User-ID': getUserId(),
    },
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '보안 PDF 업로드에 실패했습니다.')
  }

  return response.json()
}

export async function ingestLaws(lawNames = null) {
  const response = await fetch(`${BASE_URL}/admin/ingest/laws`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ law_names: lawNames }),
  })

  if (!response.ok) {
    let message = '법령 적재에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function ingestPrecedents(keywords = null, maxPerKeyword = 10) {
  const response = await fetch(`${BASE_URL}/admin/ingest/precedents`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ keywords, max_per_keyword: maxPerKeyword }),
  })

  if (!response.ok) {
    let message = '판례 적재에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function getVectorStats() {
  const response = await fetch(`${BASE_URL}/admin/vectors/stats`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '벡터 DB 통계 조회에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

// === 문서 관리 API ===

export async function getDocuments(params = {}) {
  const query = new URLSearchParams()
  if (params.document_type) query.set('document_type', params.document_type)
  if (params.search) query.set('search', params.search)
  if (params.collection) query.set('collection', params.collection)

  const qs = query.toString()
  const response = await fetch(`${BASE_URL}/admin/documents${qs ? `?${qs}` : ''}`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '문서 목록을 불러올 수 없습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function updateDocument(id, data) {
  const response = await fetch(`${BASE_URL}/admin/documents/${id}`, {
    method: 'PATCH',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    let message = '문서 수정에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function deleteDocument(id) {
  const response = await fetch(`${BASE_URL}/admin/documents/${id}`, {
    method: 'DELETE',
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '문서 삭제에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}

export async function getSecurityMetadata() {
  const response = await fetch(`${BASE_URL}/admin/security/metadata`, {
    headers: { 'X-User-ID': getUserId() },
  })

  if (!response.ok) {
    let message = '보안 메타데이터 조회에 실패했습니다'
    try {
      const body = await response.json()
      message = body.detail || body.message || message
    } catch {
      // 서버가 비JSON 응답 반환
    }
    throw new Error(message)
  }

  return response.json()
}
