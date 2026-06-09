import request from '../utils/request'
import { getValidToken, forceLogout } from '../utils/request'
import { API_V1 } from '../utils/apiBase'
import type {
  PaginatedResponse, ConversationItem, ChatMessageItem,
  RetrievalResultItem, ConversationSearchResult,
  StreamEvent, MessageResponse, BatchDeleteResponse,
} from '../types/api'

export function listConversations(page = 1, pageSize = 50) {
  return request.get<PaginatedResponse<ConversationItem>>('/chat/conversations', { params: { page, page_size: pageSize } })
}

export function searchConversations(q: string, page = 1, pageSize = 20) {
  return request.get<PaginatedResponse<ConversationSearchResult>>('/chat/conversations/search', { params: { q, page, page_size: pageSize } })
}

export function getConversationMessages(conversationId: number) {
  return request.get<ChatMessageItem[]>(`/chat/conversations/${conversationId}/messages`)
}

export function deleteConversation(conversationId: number) {
  return request.delete<MessageResponse>(`/chat/conversations/${conversationId}`)
}

export function batchDeleteConversations(ids: number[]) {
  return request.post<BatchDeleteResponse>('/chat/conversations/batch-delete', { ids })
}

export function renameConversation(conversationId: number, title: string) {
  return request.put<MessageResponse>(`/chat/conversations/${conversationId}`, { title })
}

export function searchKnowledge(data: { kb_id: number; query: string; top_k?: number; score_threshold?: number }) {
  return request.post<RetrievalResultItem[]>('/chat/search', data)
}

export function searchMultiKb(data: { kb_ids: number[]; query: string; top_k?: number; score_threshold?: number }) {
  return request.post<RetrievalResultItem[]>('/chat/search/multi-kb', data)
}

export function messageFeedback(messageId: number, feedback: string | null, feedbackReason?: string) {
  return request.post<MessageResponse>(`/chat/messages/${messageId}/feedback`, { feedback, feedback_reason: feedbackReason || null })
}

export function regenerateMessage(messageId: number) {
  return request.post(`/chat/messages/${messageId}/regenerate`)
}

export function editMessage(messageId: number, content: string) {
  return request.put(`/chat/messages/${messageId}/edit`, { content })
}

export function togglePinConversation(conversationId: number) {
  return request.patch<{ is_pinned: boolean }>(`/chat/conversations/${conversationId}/pin`)
}

export function recallMessage(messageId: number) {
  return request.post<{ content: string }>(`/chat/messages/${messageId}/recall`)
}

export async function exportConversation(conversationId: number) {
  const token = await getValidToken()
  const resp = await fetch(`${API_V1}/chat/conversations/${conversationId}/export`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok) throw new Error('导出失败')
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `conversation_${conversationId}.md`
  a.click()
  URL.revokeObjectURL(url)
}

export async function* streamChat(
  data: {
    conversation_id?: number
    kb_id: number
    llm_model_id: number
    question: string
    top_k?: number
    score_threshold?: number
    enable_rewrite?: boolean
    chat_mode?: string
    context_strategy?: string
    prompt_template_id?: number
  },
  signal?: AbortSignal
) {
  const token = await getValidToken()
  const response = await fetch(`${API_V1}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
    signal,
  })

  if (!response.ok) {
    const text = await response.text()
    let detail = '请求失败'
    try {
      detail = JSON.parse(text).detail || text
    } catch {
      detail = text
    }
    if (response.status === 401) {
      forceLogout('登录已过期，请重新登录')
    }
    throw new Error(detail)
  }

  if (!response.body) return

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.trim()) {
        try {
          yield JSON.parse(line)
        } catch {
          // skip malformed lines
        }
      }
    }
  }

  if (buffer.trim()) {
    try {
      yield JSON.parse(buffer)
    } catch {
      // skip
    }
  }
}

export function analyzeFile(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/chat/analyze-file', formData)
}

export function summarizeFile(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/chat/summarize-file', formData)
}

export async function processFile(file: File, instruction: string) {
  const formData = new FormData()
  formData.append('file', file)
  const token = await getValidToken()
  const resp = await fetch(`${API_V1}/chat/process-file?instruction=${encodeURIComponent(instruction)}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err.detail || '文件处理失败')
  }
  const blob = await resp.blob()
  const disposition = resp.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="?(.+?)"?$/i)
  const filename = match?.[1] || 'processed_file'
  return { blob, filename }
}
