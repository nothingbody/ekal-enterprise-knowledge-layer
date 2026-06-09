import request from '../utils/request'
import { API_V1 } from '../utils/apiBase'
import { forceLogout, getValidToken } from '../utils/request'

export function listRemoteSharedKbs() {
  return request.get('/relay/shared-kbs', { _silentError: true } as any)
}

export async function* streamRemoteChat(
  data: {
    remote_kb_id: number
    conversation_id?: number
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
  const response = await fetch(`${API_V1}/relay/chat/completions`, {
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
    let detail = '远程知识库请求失败'
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
      if (!line.trim()) continue
      try {
        yield JSON.parse(line)
      } catch {
        // skip malformed lines
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
