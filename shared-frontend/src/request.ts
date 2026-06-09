/**
 * HTTP 请求工具抽象。
 *
 * 提供可配置的 axios 实例创建和通用拦截器逻辑。
 */
import type { AxiosInstance, AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios'

/**
 * 请求配置选项
 */
export interface RequestOptions {
  /** API 基础路径 */
  baseURL: string
  /** 请求超时时间（毫秒） */
  timeout?: number
  /** 获取 access token */
  getToken: () => string | null
  /** 获取 refresh token */
  getRefreshToken: () => string | null
  /** 保存新的 tokens */
  setTokens: (accessToken: string, refreshToken: string) => void
  /** 清除 tokens（登出时） */
  clearTokens: () => void
  /** 刷新 token 的 API 路径（相对于 baseURL） */
  refreshEndpoint?: string
  /** 显示错误消息 */
  showError?: (message: string) => void
  /** 跳转到登录页 */
  redirectToLogin?: () => void
  /** 登出时的额外操作 */
  onLogout?: () => void
}

/**
 * 格式化错误详情为可读字符串
 */
export function formatErrorDetail(detail: unknown): string {
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
  if (detail && typeof detail === 'object' && 'detail' in detail) {
    return String((detail as { detail: unknown }).detail)
  }
  return ''
}

/**
 * 创建带有 token 管理的 axios 请求拦截器
 */
export function createRequestInterceptor(
  options: Pick<RequestOptions, 'getToken'>
) {
  return (config: InternalAxiosRequestConfig) => {
    const token = options.getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  }
}

/**
 * Pending request queue item
 */
interface PendingItem {
  resolve: (value: unknown) => void
  reject: (reason?: unknown) => void
  config: InternalAxiosRequestConfig
}

/**
 * 创建带有自动刷新 token 的 axios 响应拦截器工厂
 */
export function createResponseInterceptorFactory(
  instance: AxiosInstance,
  options: RequestOptions
) {
  let isRefreshing = false
  let pendingQueue: PendingItem[] = []

  const refreshEndpoint = options.refreshEndpoint ?? '/auth/refresh'

  async function tryRefreshToken(): Promise<string | null> {
    const refreshToken = options.getRefreshToken()
    if (!refreshToken) return null
    try {
      const { default: axios } = await import('axios')
      const { data } = await axios.post(
        `${options.baseURL}${refreshEndpoint}`,
        { refresh_token: refreshToken }
      )
      options.setTokens(data.access_token, data.refresh_token)
      return data.access_token
    } catch {
      return null
    }
  }

  function forceLogout(msg: string) {
    options.clearTokens()
    options.onLogout?.()
    options.showError?.(msg)
    options.redirectToLogin?.()
  }

  return {
    onFulfilled: (response: { data: unknown }) => response.data,
    onRejected: async (error: {
      response?: { status?: number; data?: { detail?: unknown } }
      config?: InternalAxiosRequestConfig & { _retried?: boolean; _silentError?: boolean }
    }) => {
      const status = error.response?.status
      const originalRequest = error.config

      if (!originalRequest) {
        return Promise.reject(error)
      }

      const url = originalRequest.url || ''
      const isAuthRequest = url.includes('/auth/login') || url.includes('/auth/refresh')

      // Handle auth request failures
      if (status === 401 && isAuthRequest) {
        const rawDetail = error.response?.data?.detail
        const msg = formatErrorDetail(rawDetail) || '认证失败'
        options.showError?.(msg)
        return Promise.reject(error)
      }

      // Handle 401 with token refresh
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
            resolve(instance(config))
          })
          pendingQueue = []
          originalRequest.headers = originalRequest.headers || {}
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return instance(originalRequest)
        }

        pendingQueue.forEach(({ reject }) => reject(error))
        pendingQueue = []
        forceLogout('登录已过期，请重新登录')
        return Promise.reject(error)
      }

      // Handle other errors
      const rawDetail = error.response?.data?.detail
      const msg = formatErrorDetail(rawDetail) || '请求失败'
      if (!originalRequest._silentError && status !== 401) {
        if (status === 403) {
          options.showError?.('权限不足')
        } else {
          options.showError?.(msg)
        }
      }
      return Promise.reject(error)
    }
  }
}

/**
 * Token 存储键名配置
 */
export interface TokenStorageKeys {
  accessToken: string
  refreshToken: string
}

/**
 * 创建基于 localStorage 的 token 存储
 */
export function createLocalStorageTokens(keys: TokenStorageKeys) {
  return {
    getToken: () => localStorage.getItem(keys.accessToken),
    getRefreshToken: () => localStorage.getItem(keys.refreshToken),
    setTokens: (accessToken: string, refreshToken: string) => {
      localStorage.setItem(keys.accessToken, accessToken)
      localStorage.setItem(keys.refreshToken, refreshToken)
    },
    clearTokens: () => {
      localStorage.removeItem(keys.accessToken)
      localStorage.removeItem(keys.refreshToken)
    }
  }
}
