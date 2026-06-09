import { createRouter, createWebHistory } from 'vue-router'
import axios from 'axios'
import { ADMIN_API_BASE } from '../config/adminApi'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { isTokenExpired, getRoleFromToken } from '../utils/jwt'
import { Role, checkRoleLevel } from '@rag-platform/shared-utils'

NProgress.configure({ showSpinner: false, speed: 300, minimum: 0.2 })

const routes = [
  {
    path: '/login',
    component: () => import('../views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '仪表板', minRole: Role.ORG_ADMIN } },
      { path: 'users', component: () => import('../views/Users.vue'), meta: { title: '用户管理', minRole: Role.ADMIN } },
      { path: 'users/:userId/detail', component: () => import('../views/UserDetail.vue'), meta: { title: '用户详情', minRole: Role.ADMIN } },
      { path: 'organizations', component: () => import('../views/Organizations.vue'), meta: { title: '组织管理', minRole: Role.ADMIN } },
      { path: 'organizations/:orgId/detail', component: () => import('../views/OrganizationDetail.vue'), meta: { title: '组织详情', minRole: Role.ADMIN } },
      { path: 'devices', component: () => import('../views/Devices.vue'), meta: { title: '设备管理', minRole: Role.ADMIN } },
      { path: 'platform-models', component: () => import('../views/PlatformModels.vue'), meta: { title: '平台模型', minRole: Role.ADMIN } },
      { path: 'workspaces', component: () => import('../views/Workspaces.vue'), meta: { title: '工作空间', minRole: Role.ORG_ADMIN } },
      { path: 'knowledge-bases', component: () => import('../views/KnowledgeBases.vue'), meta: { title: '知识库总览', minRole: Role.ORG_ADMIN } },
      { path: 'skills', component: () => import('../views/Skills.vue'), meta: { title: '技能市场', minRole: Role.ORG_ADMIN } },
      { path: 'analytics', component: () => import('../views/Analytics.vue'), meta: { title: '用量分析', minRole: Role.ORG_ADMIN } },
      { path: 'settings', component: () => import('../views/Settings.vue'), meta: { title: '系统设置', minRole: Role.SUPER_ADMIN } },
      { path: 'audit-logs', component: () => import('../views/AuditLogs.vue'), meta: { title: '审计日志', minRole: Role.ADMIN } },
      { path: 'server-logs', component: () => import('../views/ServerLogs.vue'), meta: { title: '服务器日志', minRole: Role.SUPER_ADMIN } },
      { path: 'notifications', component: () => import('../views/Notifications.vue'), meta: { title: '通知管理', minRole: Role.ADMIN } },
      { path: 'releases', component: () => import('../views/Releases.vue'), meta: { title: '版本管理', minRole: Role.SUPER_ADMIN } },
      { path: 'site-content', component: () => import('../views/SiteContent.vue'), meta: { title: '官网内容', minRole: Role.ADMIN } },
    ],
  },
  {
    path: '/share/:pathMatch(.*)*',
    redirect: '/',
    meta: { public: true },
  },
  {
    path: '/invite/:pathMatch(.*)*',
    redirect: '/login',
    meta: { public: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/NotFound.vue'),
    meta: { public: true, title: '页面未找到' },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

let _sessionVerified = false

export function resetSessionVerified() {
  _sessionVerified = false
}

async function _tryRefresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem('admin_refresh_token')
  if (!refreshToken) return false
  try {
    const res: any = await axios.post(`${ADMIN_API_BASE}/auth/refresh`, { refresh_token: refreshToken })
    localStorage.setItem('admin_token', res.data.access_token)
    localStorage.setItem('admin_refresh_token', res.data.refresh_token)
    _sessionVerified = true
    return true
  } catch {
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_refresh_token')
    _sessionVerified = false
    return false
  }
}

async function ensureSession(): Promise<boolean> {
  const token = localStorage.getItem('admin_token')
  if (!token) return false

  if (isTokenExpired(token)) {
    return _tryRefresh()
  }

  if (!_sessionVerified) {
    try {
      await axios.get(`${ADMIN_API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 5000,
      })
      _sessionVerified = true
    } catch (err: any) {
      if (err?.response?.status === 401) {
        return _tryRefresh()
      }
      // 非 401 错误（网络/服务端故障）：安全优先，不信任客户端状态
      // 避免攻击者通过网络劫持绕过认证
      console.warn('[auth] Session verification failed (network/server error), denying access')
      return false
    }
  }
  return true
}

router.beforeEach(async (to, _from, next) => {
  NProgress.start()

  if (!to.meta.public) {
    const ok = await ensureSession()
    if (!ok) {
      next('/login')
      return
    }
  }

  if (to.path === '/login' && localStorage.getItem('admin_token')) {
    const ok = await ensureSession()
    if (ok) {
      next('/dashboard')
      return
    }
  }

  // 基于角色层级的路由守卫
  // 注意：JWT payload 可能不含 role 字段，此时跳过客户端角色检查（由后端 API 鉴权兜底）
  const minRole = to.meta.minRole as Role | undefined
  if (minRole) {
    const token = localStorage.getItem('admin_token')
    const userRole = token ? getRoleFromToken(token) : null
    if (userRole && !checkRoleLevel(userRole as Role, minRole)) {
      if (to.path === '/dashboard') {
        next('/login')
      } else {
        next('/dashboard')
      }
      return
    }
  }

  const title = to.meta.title as string | undefined
  document.title = title ? `${title} - 知枢管理后台` : '知枢管理后台'
  next()
})

router.afterEach(() => {
  NProgress.done()
})

export default router
