import request from '../utils/request'

export function listChannels(params?: { page?: number; page_size?: number }) {
  return request.get('/channels/', { params })
}

export function getChannel(id: number) {
  return request.get(`/channels/${id}`)
}

export function createChannel(data: {
  name: string
  platform: string
  kb_id?: number
  llm_model_id?: number
  chat_mode?: string
  config?: Record<string, any>
}) {
  return request.post('/channels/', data)
}

export function updateChannel(id: number, data: Record<string, any>) {
  return request.put(`/channels/${id}`, data)
}

export function deleteChannel(id: number) {
  return request.delete(`/channels/${id}`)
}

export function toggleChannel(id: number) {
  return request.post(`/channels/${id}/toggle`)
}

export function testSendChannel(id: number) {
  return request.post<{ message: string }>(`/channels/${id}/test-send`)
}

export function testChannelConfig(data: { platform: string; config: Record<string, any> }) {
  return request.post('/channels/test', data)
}
