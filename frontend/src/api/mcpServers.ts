import request from '../utils/request'

export interface McpServerForm {
  name: string
  transport_type: 'stdio' | 'http' | 'sse'
  command?: string
  args?: string
  env?: string
  url?: string
  headers?: string
  tool_filter?: string
  workspace_id?: number
}

export function listMcpServers(params?: { page?: number; page_size?: number; workspace_id?: number }) {
  return request.get('/mcp-servers/', { params })
}

export function getMcpServer(serverId: number) {
  return request.get(`/mcp-servers/${serverId}`)
}

export function createMcpServer(data: McpServerForm) {
  return request.post('/mcp-servers', data)
}

export function updateMcpServer(serverId: number, data: Partial<McpServerForm>) {
  return request.put(`/mcp-servers/${serverId}`, data)
}

export function deleteMcpServer(serverId: number) {
  return request.delete(`/mcp-servers/${serverId}`)
}

export function toggleMcpServer(serverId: number) {
  return request.post(`/mcp-servers/${serverId}/toggle`)
}

export function listMcpServerTools(serverId: number) {
  return request.get(`/mcp-servers/${serverId}/tools`)
}

export function testMcpServer(serverId: number) {
  return request.post(`/mcp-servers/${serverId}/test`)
}
