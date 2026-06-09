import request from '../utils/request'

export function getSystemReadiness() {
  return request.get('/system/readiness')
}

export function getSystemStats() {
  return request.get('/system/stats')
}

export function getSystemConfig() {
  return request.get('/system/config')
}

export function getOperationLogs(page = 1, pageSize = 20, action?: string, resourceType?: string) {
  return request.get('/system/logs', { params: { page, page_size: pageSize, action, resource_type: resourceType } })
}

export function getLogFilters() {
  return request.get('/system/logs/filters')
}

export function getUsageTrend(days = 7) {
  return request.get('/system/usage-trend', { params: { days } })
}

export function cleanupLogs(retentionDays = 90) {
  return request.delete('/system/logs/cleanup', { params: { retention_days: retentionDays } })
}
