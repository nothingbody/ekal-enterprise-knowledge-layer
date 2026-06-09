import request from '../utils/request'

export function listApps() {
  return request.get('/apps/')
}

export function createApp(data: any) {
  return request.post('/apps/', data)
}

export function updateApp(appId: number, data: any) {
  return request.put(`/apps/${appId}`, data)
}

export function generateApiKey(appId: number) {
  return request.post(`/apps/${appId}/generate-api-key`)
}

export function deleteApp(appId: number) {
  return request.delete(`/apps/${appId}`)
}

export function getPublicAppInfo(shareToken: string) {
  return request.get(`/apps/public/${shareToken}/info`)
}
