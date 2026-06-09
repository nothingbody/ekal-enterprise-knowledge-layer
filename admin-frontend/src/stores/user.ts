import { defineStore } from 'pinia'
import { ref } from 'vue'
import { resetSessionVerified } from '../router'
import request from '../utils/request'

export const useUserStore = defineStore('user', () => {
  const userInfo = ref<any>(null)
  const token = ref(localStorage.getItem('admin_token') || '')

  async function login(username: string, password: string) {
    const res: any = await request.post('/auth/login', { username, password })
    token.value = res.access_token
    userInfo.value = res.user
    localStorage.setItem('admin_token', res.access_token)
    localStorage.setItem('admin_refresh_token', res.refresh_token)
    return res
  }

  async function fetchMe() {
    const res: any = await request.get('/auth/me')
    userInfo.value = res
    return res
  }

  async function logout() {
    try {
      await request.post('/auth/logout')
    } catch { /* ignore */ }
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_refresh_token')
    resetSessionVerified()
  }

  return { userInfo, token, login, fetchMe, logout }
})
