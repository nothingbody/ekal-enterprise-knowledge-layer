import request from '../utils/request'
import { getValidToken } from '../utils/request'
import { API_V1 } from '../utils/apiBase'
import type { KnowledgeBaseItem, MessageResponse } from '../types/api'

export function listKnowledgeBases() {
  return request.get<KnowledgeBaseItem[]>('/knowledge-bases/')
}

export function getKnowledgeBase(id: number) {
  return request.get<KnowledgeBaseItem>(`/knowledge-bases/${id}`)
}

export function createKnowledgeBase(data: {
  name: string;
  description?: string;
  workspace_id?: number | null;
  embedding_model_id?: number | null;
  chunk_strategy?: string;
  chunk_size?: number;
  chunk_overlap?: number;
  search_mode?: string;
  welcome_message?: string;
  suggested_questions?: string;
  prompt_template?: string;
}) {
  return request.post('/knowledge-bases/', data)
}

export function updateKnowledgeBase(id: number, data: any) {
  return request.put(`/knowledge-bases/${id}`, data)
}

export function deleteKnowledgeBase(id: number) {
  return request.delete(`/knowledge-bases/${id}`)
}

export async function exportKnowledgeBase(id: number) {
  const token = await getValidToken()
  const resp = await fetch(`${API_V1}/kb-transfer/${id}/export`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok) throw new Error('导出失败')
  const blob = await resp.blob()
  const disposition = resp.headers.get('content-disposition') || ''
  const match = disposition.match(/filename=(.+)/)
  const filename = match?.[1] ?? `kb_${id}.zip`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function listTrashedKnowledgeBases() {
  return request.get('/knowledge-bases/trash')
}

export function restoreKnowledgeBase(id: number) {
  return request.post(`/knowledge-bases/${id}/restore`)
}

export function permanentDeleteKnowledgeBase(id: number) {
  return request.delete(`/knowledge-bases/${id}`, { params: { permanent: true } })
}

export function reindexKnowledgeBase(id: number) {
  return request.post(`/knowledge-bases/${id}/reindex`)
}

export function importKnowledgeBase(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/kb-transfer/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}
