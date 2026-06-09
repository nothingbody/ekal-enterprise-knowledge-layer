import request from '../utils/request'

export function listApiKeys() {
  return request.get('/api-keys/')
}

export function createApiKey(name: string) {
  return request.post('/api-keys/', { name })
}

export function updateApiKey(id: number, data: { name?: string; is_active?: boolean }) {
  return request.put(`/api-keys/${id}`, data)
}

export function deleteApiKey(id: number) {
  return request.delete(`/api-keys/${id}`)
}
