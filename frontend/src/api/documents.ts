import request from '../utils/request'
import type { PaginatedResponse, DocumentItem, DocumentChunkItem, MessageResponse } from '../types/api'

export function uploadDocument(kbId: number, file: File, onProgress?: (percent: number) => void) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post(`/documents/upload/${kbId}`, formData, {
    timeout: 300000,
    onUploadProgress: onProgress
      ? (e: any) => { if (e.total) onProgress(Math.round((e.loaded / e.total) * 100)) }
      : undefined,
  })
}

export function listDocuments(kbId: number, page = 1, pageSize = 20) {
  return request.get<PaginatedResponse<DocumentItem>>(`/documents/${kbId}`, { params: { page, page_size: pageSize } })
}

export function getDocumentChunks(docId: number, page = 1, pageSize = 20) {
  return request.get<PaginatedResponse<DocumentChunkItem>>(`/documents/${docId}/chunks`, { params: { page, page_size: pageSize } })
}

export function previewDocument(docId: number) {
  return request.get<{ content: string; total_chars: number }>(`/documents/${docId}/preview`)
}

export function retryDocument(docId: number) {
  return request.post<MessageResponse>(`/documents/${docId}/retry`)
}

export function deleteDocument(docId: number, permanent = false) {
  return request.delete<MessageResponse>(`/documents/${docId}`, { params: permanent ? { permanent: true } : undefined })
}

export function listTrash(kbId: number) {
  return request.get(`/documents/trash/${kbId}`)
}

export function restoreDocument(docId: number) {
  return request.post<MessageResponse>(`/documents/${docId}/restore`)
}

export function updateChunk(chunkId: number, content: string) {
  return request.put(`/documents/chunks/${chunkId}`, { content })
}

export function createChunk(data: { doc_id: number; kb_id: number; content: string }) {
  return request.post('/documents/chunks', data)
}

export function deleteChunk(chunkId: number) {
  return request.delete(`/documents/chunks/${chunkId}`)
}

export function previewChunks(file: File, strategy = 'fixed', chunkSize?: number, chunkOverlap?: number) {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams()
  params.append('strategy', strategy)
  if (chunkSize) params.append('chunk_size', String(chunkSize))
  if (chunkOverlap) params.append('chunk_overlap', String(chunkOverlap))
  return request.post(`/documents/preview-chunks?${params.toString()}`, form)
}

/** 获取即将过期的文档 */
export function getExpiringDocuments(kbId: number, daysAhead = 7) {
  return request.get<DocumentItem[]>(`/documents/${kbId}/expiring`, { params: { days_ahead: daysAhead } })
}

/** 更新文档标签 */
export function updateDocumentTags(docId: number, tags: string[]) {
  return request.post<MessageResponse>(`/documents/${docId}/tags`, { tags })
}

/** 检查重复文档 */
export function checkDuplicate(kbId: number, contentHash: string) {
  return request.post<{ is_duplicate: boolean }>('/documents/check-duplicate', { kb_id: kbId, content_hash: contentHash })
}

/** 建议知识库 */
export function suggestKnowledgeBase(filename: string, contentPreview: string) {
  return request.post<{ kb_id?: number; kb_name?: string }>('/documents/suggest-kb', { filename, content_preview: contentPreview })
}

/** 设置文档过期时间 */
export function updateDocumentExpiry(docId: number, expiresAt: string | null) {
  return request.put<MessageResponse>(`/documents/${docId}/expiry`, { expires_at: expiresAt })
}
