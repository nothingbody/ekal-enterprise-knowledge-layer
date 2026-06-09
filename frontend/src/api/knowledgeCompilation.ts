import request from '../utils/request'

// --- Compilation Config ---

export function getCompilationConfig(kbId: number) {
  return request.get(`/knowledge-compilation/${kbId}/compilation-config`)
}

export function updateCompilationConfig(kbId: number, data: {
  enabled: boolean
  auto_compile_on_ingest?: boolean
  compilation_model_id?: number | null
  max_tokens_per_article?: number
  max_chunks_per_group?: number
  health_check_enabled?: boolean
  health_check_interval_hours?: number
  incremental_synthesis?: boolean
  synthesis_similarity_threshold?: number
}) {
  return request.put(`/knowledge-compilation/${kbId}/compilation-config`, data)
}

// --- Compiled Articles ---

export function listArticles(kbId: number, params?: { status?: string; skip?: number; limit?: number }) {
  return request.get(`/knowledge-compilation/${kbId}/articles`, { params })
}

export function getArticle(articleId: number) {
  return request.get(`/knowledge-compilation/articles/${articleId}`)
}

export function updateArticle(articleId: number, data: {
  title?: string
  content?: string
  summary?: string
  tags?: string[]
}) {
  return request.put(`/knowledge-compilation/articles/${articleId}`, data)
}

export function deleteArticle(articleId: number) {
  return request.delete(`/knowledge-compilation/articles/${articleId}`)
}

// --- Compilation Triggers ---

export function triggerCompileKb(kbId: number) {
  return request.post(`/knowledge-compilation/${kbId}/compile`)
}

export function triggerCompileDocument(kbId: number, docId: number) {
  return request.post(`/knowledge-compilation/${kbId}/compile/${docId}`)
}

// --- Health Check ---

export function listHealthReports(kbId: number, params?: { skip?: number; limit?: number }) {
  return request.get(`/knowledge-compilation/${kbId}/health-reports`, { params })
}

export function getHealthReport(reportId: number) {
  return request.get(`/knowledge-compilation/health-reports/${reportId}`)
}

export function triggerHealthCheck(kbId: number) {
  return request.post(`/knowledge-compilation/${kbId}/health-check`)
}

// --- Cross References ---

export function listCrossRefs(kbId: number) {
  return request.get(`/knowledge-compilation/${kbId}/cross-refs`)
}

// --- Compilation Status ---

export function getCompilationStatus(kbId: number) {
  return request.get(`/knowledge-compilation/${kbId}/compilation-status`)
}
