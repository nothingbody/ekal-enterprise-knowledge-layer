import request from '../utils/request'
import type { LoginResponse, UserInfo, MessageResponse } from '../types/api'

export function login(data: { username: string; password: string }) {
  return request.post<LoginResponse>('/auth/login', data)
}

export function register(data: { username: string; email: string; password: string; invite_code?: string }) {
  return request.post<LoginResponse>('/auth/register', data)
}

export function getMe() {
  return request.get<UserInfo>('/auth/me')
}

export function changePassword(data: { old_password: string; new_password: string }) {
  return request.post<MessageResponse>('/auth/change-password', data)
}

export function deleteAccount(data: { password: string }) {
  return request.delete('/auth/account', { data })
}
