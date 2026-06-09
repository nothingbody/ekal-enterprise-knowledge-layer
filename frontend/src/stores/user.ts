import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMe } from '../api/auth'

interface UserInfo {
  id: number
  username: string
  email: string
  role: string
}

/** 路由与布局用于区分「未登录」与「网络异常但 Token 仍可能有效」 */
export type FetchUserInfoResult =
  | { status: 'ok'; user: UserInfo }
  | { status: 'auth_failed' }
  | { status: 'network' }

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const refreshToken = ref(localStorage.getItem('refreshToken') || '')
  const userInfo = ref<UserInfo | null>(null)

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('token', t)
  }

  function setRefreshToken(t: string) {
    refreshToken.value = t
    localStorage.setItem('refreshToken', t)
  }

  function setUserInfo(info: UserInfo) {
    userInfo.value = info
  }

  function clearToken() {
    token.value = ''
    refreshToken.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
  }

  async function fetchUserInfo(): Promise<FetchUserInfoResult> {
    if (!token.value) {
      return { status: 'auth_failed' }
    }

    const attempt = async (): Promise<FetchUserInfoResult> => {
      try {
        const res: any = await getMe()
        userInfo.value = res
        return { status: 'ok', user: res }
      } catch (e: any) {
        const status = e?.response?.status
        if (status === 401 || status === 403) {
          clearToken()
          return { status: 'auth_failed' }
        }
        return { status: 'network' }
      }
    }

    let r = await attempt()
    if (r.status === 'network') {
      await new Promise((x) => setTimeout(x, 400))
      r = await attempt()
    }
    return r
  }

  return { token, refreshToken, userInfo, setToken, setRefreshToken, setUserInfo, clearToken, fetchUserInfo }
})
