import axios, { type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router, { resetSessionVerified } from '../router'
import { ADMIN_API_BASE } from '../config/adminApi'

const request = axios.create({
  baseURL: ADMIN_API_BASE,
  timeout: 30000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let isRefreshing = false
type PendingItem = { resolve: (value: unknown) => void; reject: (reason?: unknown) => void; config: InternalAxiosRequestConfig }
let pendingQueue: PendingItem[] = []

async function tryRefreshToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem('admin_refresh_token')
  if (!refreshToken) return null
  try {
    const { data } = await axios.post(`${ADMIN_API_BASE}/auth/refresh`, { refresh_token: refreshToken })
    localStorage.setItem('admin_token', data.access_token)
    localStorage.setItem('admin_refresh_token', data.refresh_token)
    return data.access_token
  } catch {
    return null
  }
}

function formatErrorDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d: unknown) => {
      if (d && typeof d === 'object') {
        const obj = d as Record<string, unknown>
        if (typeof obj.msg === 'string') return obj.msg
        if (typeof obj.message === 'string') return obj.message
      }
      return String(d)
    }).join('；')
  }
  if (detail && typeof detail === 'object' && 'detail' in detail) return String((detail as { detail: unknown }).detail)
  return '请求失败'
}

request.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const status = error.response?.status
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retried?: boolean; _silentError?: boolean }

    const url = originalRequest?.url || ''
    const isAuthRequest = url.includes('/auth/login') || url.includes('/auth/refresh')

    if (status === 401 && isAuthRequest) {
      const rawDetail = error.response?.data?.detail
      ElMessage.error(formatErrorDetail(rawDetail) || '认证失败')
      return Promise.reject(error)
    }

    if (status === 401 && !originalRequest._retried) {
      originalRequest._retried = true

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingQueue.push({ resolve, reject, config: originalRequest })
        })
      }

      isRefreshing = true
      const newToken = await tryRefreshToken()
      isRefreshing = false

      if (newToken) {
        pendingQueue.forEach(({ resolve, config }) => {
          config.headers = config.headers || {}
          config.headers.Authorization = `Bearer ${newToken}`
          resolve(request(config))
        })
        pendingQueue = []
        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return request(originalRequest)
      }

      pendingQueue.forEach(({ reject }) => reject(error))
      pendingQueue = []
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_refresh_token')
      resetSessionVerified()
      router.push('/login')
      ElMessage.error('登录已过期')
      return Promise.reject(error)
    }

    const rawDetail = error.response?.data?.detail
    const msg = formatErrorDetail(rawDetail) || '请求失败'
    if (!originalRequest?._silentError) {
      if (status === 403) {
        ElMessage.error('权限不足')
      } else if (status !== 401) {
        ElMessage.error(msg)
      }
    }
    return Promise.reject(error)
  }
)

export default request
