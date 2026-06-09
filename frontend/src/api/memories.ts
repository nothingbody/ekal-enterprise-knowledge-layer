import request from '../utils/request'

export function listMemories(params?: { category?: string; page?: number; page_size?: number }) {
  return request.get('/memories/', { params })
}

export function createMemory(data: { content: string; category?: string }) {
  return request.post('/memories/', data)
}

export function updateMemory(id: number, data: { content: string }) {
  return request.put(`/memories/${id}`, data)
}

export function deleteMemory(id: number) {
  return request.delete(`/memories/${id}`)
}

export function clearAllMemories() {
  return request.delete('/memories/')
}

export function getUserProfile(regenerate = false) {
  return request.get('/memories/profile', { params: { regenerate } })
}

export function cleanupExpiredMemories() {
  return request.post('/memories/cleanup')
}
