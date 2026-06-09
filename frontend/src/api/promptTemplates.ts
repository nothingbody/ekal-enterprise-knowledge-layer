import request from '../utils/request'

export interface PromptTemplate {
  id: number
  user_id: number | null
  name: string
  description: string | null
  content: string
  category: string
  is_builtin: boolean
  created_at: string | null
  updated_at: string | null
}

export interface TemplateVariable {
  name: string
  label: string
  example: string
}

export function listTemplates(): Promise<PromptTemplate[]> {
  return request.get('/prompt-templates/') as any
}

export function getTemplate(id: number): Promise<PromptTemplate> {
  return request.get(`/prompt-templates/${id}`) as any
}

export function createTemplate(data: {
  name: string
  description?: string
  content: string
  category?: string
}): Promise<PromptTemplate> {
  return request.post('/prompt-templates/', data) as any
}

export function updateTemplate(id: number, data: {
  name?: string
  description?: string
  content?: string
  category?: string
}): Promise<PromptTemplate> {
  return request.put(`/prompt-templates/${id}`, data) as any
}

export function deleteTemplate(id: number) {
  return request.delete(`/prompt-templates/${id}`)
}

export function getVariables(): Promise<TemplateVariable[]> {
  return request.get('/prompt-templates/variables') as any
}
