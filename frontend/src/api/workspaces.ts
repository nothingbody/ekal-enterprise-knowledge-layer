import request from '../utils/request'

export function listWorkspaces() {
  return request.get('/workspaces/')
}

export function createWorkspace(data: { name: string; description?: string }) {
  return request.post('/workspaces/', data)
}

export function listMembers(wsId: number) {
  return request.get(`/workspaces/${wsId}/members`)
}

export function addMember(wsId: number, data: { username: string; role?: string }) {
  return request.post(`/workspaces/${wsId}/members`, data)
}

export function updateWorkspace(wsId: number, data: { name?: string; description?: string }) {
  return request.put(`/workspaces/${wsId}`, data)
}

export function updateMemberRole(wsId: number, memberId: number, role: string) {
  return request.put(`/workspaces/${wsId}/members/${memberId}`, { role })
}

export function removeMember(wsId: number, memberId: number) {
  return request.delete(`/workspaces/${wsId}/members/${memberId}`)
}

export function leaveWorkspace(wsId: number) {
  return request.post(`/workspaces/${wsId}/leave`)
}

export function deleteWorkspace(wsId: number) {
  return request.delete(`/workspaces/${wsId}`)
}

export function getWorkspace(wsId: number) {
  return request.get(`/workspaces/${wsId}`)
}

export function listWorkspaceKbs(wsId: number) {
  return request.get(`/workspaces/${wsId}/knowledge-bases`)
}

export function listWorkspaceModels(wsId: number, modelType?: string) {
  return request.get(`/workspaces/${wsId}/models`, { params: { model_type: modelType } })
}

export function shareModelToWorkspace(wsId: number, modelConfigId: number) {
  return request.post(`/workspaces/${wsId}/models`, { model_config_id: modelConfigId })
}

export function unshareModelFromWorkspace(wsId: number, linkId: number) {
  return request.delete(`/workspaces/${wsId}/models/${linkId}`)
}

export function createInvitation(wsId: number, data: { role?: string; expires_hours?: number; max_uses?: number | null }) {
  return request.post(`/workspaces/${wsId}/invitations`, data)
}

export function listInvitations(wsId: number) {
  return request.get(`/workspaces/${wsId}/invitations`)
}

export function revokeInvitation(wsId: number, invitationId: number) {
  return request.delete(`/workspaces/${wsId}/invitations/${invitationId}`)
}

export function getInvitationInfo(token: string) {
  return request.get(`/invitations/${token}/info`)
}

export function acceptInvitation(token: string) {
  return request.post(`/invitations/${token}/accept`)
}
