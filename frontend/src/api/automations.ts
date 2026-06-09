import request from '../utils/request'

export interface AutomationTask {
  id: number
  name: string
  description?: string
  task_type: 'scheduled' | 'webhook' | 'event'
  cron_expression?: string
  interval_minutes?: number
  event_trigger?: string
  config: Record<string, any>
  is_active: boolean
  last_run_at?: string
  last_status?: string
  run_count: number
  webhook_token?: string
  created_at: string
  updated_at: string
}

export interface AutomationLog {
  id: number
  task_id: number
  status: string
  created_at: string
  duration_ms?: number
  output?: string
  error_message?: string
  triggered_by?: string
}

export function listAutomations(params?: { page?: number; page_size?: number }) {
  return request.get('/automations/', { params })
}

export function getAutomation(id: number) {
  return request.get(`/automations/${id}`)
}

export function createAutomation(data: {
  name: string
  description?: string
  task_type: string
  cron_expression?: string
  interval_minutes?: number
  event_trigger?: string
  config: Record<string, any>
  is_active?: boolean
}) {
  return request.post('/automations/', data)
}

export function updateAutomation(id: number, data: Record<string, any>) {
  return request.put(`/automations/${id}`, data)
}

export function deleteAutomation(id: number) {
  return request.delete(`/automations/${id}`)
}

export function runAutomation(id: number) {
  return request.post(`/automations/${id}/run`)
}

export function getAutomationLogs(id: number, params?: { page?: number; page_size?: number }) {
  return request.get(`/automations/${id}/logs`, { params })
}
