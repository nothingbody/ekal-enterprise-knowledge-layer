import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { isTokenExpired } from './jwt'
import { API_V1 } from './apiBase'

const request = axios.create({
  baseURL: API_V1,
  timeout: 60000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let isRefreshing = false
let pendingQueue: Array<{ resolve: Function; reject: Function; config: AxiosRequestConfig }> = []

export function forceLogout(msg: string) {
  localStorage.removeItem('token')
  localStorage.removeItem('refreshToken')
  ElMessage.error(msg)
  router.push('/login')
}

request.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const status = error.response?.status
    if (!error.response && !status) {
      ElMessage.error('无法连接到后端服务，请检查服务是否正在运行')
      return Promise.reject(error)
    }
    const responseData = error.response?.data
    const rawDetail = responseData?.detail
    const formatDetail = (d: unknown): string => {
      if (typeof d === 'string') return d
      if (Array.isArray(d)) {
        return d.map((x: unknown) => {
          if (x && typeof x === 'object') {
            const obj = x as Record<string, unknown>
            if (typeof obj.msg === 'string') return obj.msg
            if (typeof obj.message === 'string') return obj.message
          }
          return String(x)
        }).join('；')
      }
      if (d && typeof d === 'object' && 'detail' in d) return String((d as { detail: unknown }).detail)
      return ''
    }
    let msg = formatDetail(rawDetail)
    if (!msg) {
      if (typeof responseData === 'string' && responseData.includes('301'))
        msg = '服务器重定向错误，请检查服务器地址配置是否使用了 HTTPS'
      else if (typeof responseData === 'string' && responseData.includes('502'))
        msg = '后端服务网关错误 (502)'
      else if (typeof responseData === 'string' && responseData.includes('nginx'))
        msg = '请求被反向代理拦截，请检查服务器配置'
      else if (status)
        msg = `请求失败 (${status})`
      else
        msg = '请求失败'
    }
    const originalConfig = error.config

    if (status === 401) {
      const url = originalConfig?.url || ''
      const isAuthRequest = url.includes('/auth/login') || url.includes('/auth/refresh')

      if (isAuthRequest) {
        ElMessage.error(msg)
        return Promise.reject(error)
      }

      const refreshToken = localStorage.getItem('refreshToken')
      if (!refreshToken) {
        forceLogout('登录已过期，请重新登录')
        return Promise.reject(error)
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingQueue.push({ resolve, reject, config: originalConfig })
        })
      }

      isRefreshing = true
      try {
        const res = await axios.post(`${API_V1}/auth/refresh`, { refresh_token: refreshToken })
        const { access_token, refresh_token: newRefresh } = res.data
        localStorage.setItem('token', access_token)
        localStorage.setItem('refreshToken', newRefresh)

        // Retry queued requests
        pendingQueue.forEach(({ resolve, config }) => {
          config.headers!.Authorization = `Bearer ${access_token}`
          resolve(request(config))
        })
        pendingQueue = []

        // Retry original request
        originalConfig.headers.Authorization = `Bearer ${access_token}`
        return request(originalConfig)
      } catch {
        pendingQueue.forEach(({ reject }) => reject(error))
        pendingQueue = []
        forceLogout('登录已过期，请重新登录')
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    } else if (!originalConfig?._silentError) {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

/**
 * Get a valid access token, refreshing if expired.
 * Use this before raw `fetch` calls that bypass axios interceptors.
 *
 * Uses a shared promise so concurrent callers trigger only one refresh.
 */
let _tokenRefreshPromise: Promise<string> | null = null

export async function getValidToken(): Promise<string> {
  const token = localStorage.getItem('token')
  if (!token) throw new Error('未登录')

  if (!isTokenExpired(token)) {
    return token
  }

  // Token expired — if another caller is already refreshing, wait for it
  if (_tokenRefreshPromise) {
    return _tokenRefreshPromise
  }

  const refreshToken = localStorage.getItem('refreshToken')
  if (!refreshToken) {
    forceLogout('登录已过期，请重新登录')
    throw new Error('登录已过期')
  }

  _tokenRefreshPromise = axios.post(`${API_V1}/auth/refresh`, { refresh_token: refreshToken })
    .then(res => {
      const { access_token, refresh_token: newRefresh } = res.data
      localStorage.setItem('token', access_token)
      localStorage.setItem('refreshToken', newRefresh)
      return access_token
    })
    .catch(() => {
      forceLogout('登录已过期，请重新登录')
      throw new Error('登录已过期')
    })
    .finally(() => {
      _tokenRefreshPromise = null
    })

  return _tokenRefreshPromise
}

export default request
