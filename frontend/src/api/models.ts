import request from '../utils/request'
import type { ModelConfigItem, MessageResponse } from '../types/api'

export function listModels(modelType?: string) {
  return request.get<ModelConfigItem[]>('/models/', { params: { model_type: modelType } })
}

export function createModel(data: any) {
  return request.post<ModelConfigItem>('/models/', data)
}

export function updateModel(id: number, data: any) {
  return request.put<ModelConfigItem>(`/models/${id}`, data)
}

export function deleteModel(id: number, force = false) {
  return request.delete<MessageResponse>(`/models/${id}`, { params: force ? { force: true } : undefined })
}

export function testModel(data: any) {
  return request.post('/models/test', data)
}

export function testSavedModel(modelId: number) {
  return request.post(`/models/${modelId}/test`)
}

export function getQuickSetupPresets() {
  return request.get('/models/quick-setup/presets')
}

export function quickSetupModels(data: { preset: string; api_key: string; embedding_api_key?: string }) {
  return request.post('/models/quick-setup', data)
}

export function detectOllama() {
  return request.get('/models/detect-ollama')
}
