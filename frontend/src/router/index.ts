import { createRouter, createWebHistory } from 'vue-router'
import axios from 'axios'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { isTokenExpired } from '../utils/jwt'
import { API_V1 } from '../utils/apiBase'
import { Role, Permission, checkRoleLevel, hasPermission } from '@rag-platform/shared-utils'

NProgress.configure({ showSpinner: false, speed: 300, minimum: 0.2, trickleSpeed: 120 })

const APP_DISPLAY_NAME = '企业多模态知识协作共享服务平台'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/login/index.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../views/layout/index.vue'),
    redirect: '/knowledge',
    children: [
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('../views/knowledge/index.vue'),
        meta: { title: '知识库管理' },
      },
      {
        path: 'knowledge/:id/documents',
        name: 'Documents',
        component: () => import('../views/documents/index.vue'),
        meta: { title: '文档管理', parentTitle: '知识库管理', parentPath: '/knowledge' },
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('../views/chat/index.vue'),
        meta: { title: '智能对话' },
      },
      {
        path: 'retrieval',
        name: 'Retrieval',
        component: () => import('../views/retrieval/index.vue'),
        meta: { title: '检索测试' },
      },
      {
        path: 'guide',
        name: 'Guide',
        component: () => import('../views/guide/index.vue'),
        meta: { title: '使用指南' },
      },
      {
        path: 'models',
        name: 'Models',
        component: () => import('../views/models/index.vue'),
        meta: { title: '模型管理' },
      },
      {
        path: 'databases',
        name: 'Databases',
        component: () => import('../views/databases/index.vue'),
        meta: { title: '数据库管理' },
      },
      {
        path: 'apps',
        name: 'Apps',
        component: () => import('../views/apps/index.vue'),
        meta: { title: '应用发布' },
      },
      {
        path: 'channels',
        name: 'Channels',
        component: () => import('../views/channels/index.vue'),
        meta: { title: '渠道管理' },
      },
      {
        path: 'skills',
        name: 'Skills',
        component: () => import('../views/skills/index.vue'),
        meta: { title: '技能市场' },
      },
      {
        path: 'automations',
        name: 'Automations',
        component: () => import('../views/automations/index.vue'),
        meta: { title: '自动化任务' },
      },
      {
        path: 'agents',
        name: 'Agents',
        component: () => import('../views/agents/index.vue'),
        meta: { title: '多Agent协作' },
      },
      {
        path: 'mcp',
        name: 'McpServers',
        component: () => import('../views/mcp/index.vue'),
        meta: { title: 'MCP 服务器' },
      },
      {
        path: 'diagnostics',
        name: 'Diagnostics',
        component: () => import('../views/diagnostics/index.vue'),
        meta: { title: '系统诊断' },
      },
      {
        path: 'workspaces',
        name: 'Workspaces',
        component: () => import('../views/workspaces/index.vue'),
        meta: { title: '工作空间' },
      },
      {
        path: 'workspaces/:id',
        name: 'WorkspaceDetail',
        component: () => import('../views/workspaces/detail.vue'),
        meta: { title: '工作空间详情', parentTitle: '工作空间', parentPath: '/workspaces' },
      },
      {
        path: 'system',
        name: 'System',
        component: () => import('../views/system/index.vue'),
        meta: { title: '系统管理', minRole: Role.ADMIN },
      },
      {
        path: 'templates',
        name: 'Templates',
        component: () => import('../views/templates/index.vue'),
        meta: { title: '输出模板' },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('../views/settings/index.vue'),
        meta: { title: '个人设置' },
      },
      {
        path: 'settings/api-keys',
        name: 'ApiKeys',
        component: () => import('../views/settings/apiKeys.vue'),
        meta: { title: 'API Key 管理', parentTitle: '个人设置', parentPath: '/settings' },
      },
      {
        path: 'admin/users',
        name: 'AdminUsers',
        component: () => import('../views/admin/users.vue'),
        meta: { title: '用户管理', minRole: Role.ADMIN },
      },
      {
        path: 'admin/users/:userId/detail',
        name: 'AdminUserDetail',
        component: () => import('../views/admin/userDetail.vue'),
        meta: { title: '用户详情', minRole: Role.ADMIN, parentTitle: '用户管理', parentPath: '/admin/users' },
      },
      {
        path: 'admin/analytics',
        name: 'AdminAnalytics',
        component: () => import('../views/admin/analytics.vue'),
        meta: { title: '用户分析', minRole: Role.ADMIN },
      },
    ],
  },
  {
    path: '/invite/:token',
    name: 'Invite',
    component: () => import('../views/invite/index.vue'),
    meta: { public: true, title: '加入工作空间' },
  },
  {
    path: '/share/:token',
    name: 'Share',
    component: () => import('../views/share/index.vue'),
    meta: { public: true, title: '智能问答' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/404/index.vue'),
    meta: { public: true },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition || { top: 0, behavior: 'smooth' }
  },
})

router.beforeEach(async (to, _from, next) => {
  NProgress.start()
  const { useUserStore } = await import('../stores/user')
  const userStore = useUserStore()

  const ensureSession = async () => {
    const token = localStorage.getItem('token')
    const refreshToken = localStorage.getItem('refreshToken')

    if (!token) {
      userStore.clearToken()
      return false
    }

    if (isTokenExpired(token)) {
      if (!refreshToken) {
        userStore.clearToken()
        return false
      }
      try {
        const res: any = await axios.post(`${API_V1}/auth/refresh`, {
          refresh_token: refreshToken,
        }, { timeout: 10000 })
        userStore.setToken(res.data.access_token)
        if (res.data.refresh_token) {
          userStore.setRefreshToken(res.data.refresh_token)
        }
      } catch {
        userStore.clearToken()
        return false
      }
    }

    if (!userStore.userInfo) {
      const r = await userStore.fetchUserInfo()
      if (r.status === 'network') {
        // Token 仍保留；避免短暂网络故障被当成未登录踢到登录页
        return true
      }
      if (r.status === 'auth_failed') {
        return false
      }
    }

    return !!userStore.userInfo
  }

  if (!to.meta.public) {
    const ok = await ensureSession()
    if (!ok) {
      next('/login')
      return
    }
  }

  if (to.path === '/login' && localStorage.getItem('token')) {
    const ok = await ensureSession()
    if (ok) {
      next('/')
      return
    }
  }

  // First-time user: redirect to guide page instead of knowledge list
  if (to.path === '/knowledge' && !localStorage.getItem('has_visited')) {
    localStorage.setItem('has_visited', '1')
    next('/guide')
    return
  }

  // 基于角色层级的路由守卫
  const minRole = to.meta.minRole as Role | undefined
  if (minRole && userStore.userInfo?.role) {
    const userRole = userStore.userInfo.role as Role
    if (!checkRoleLevel(userRole, minRole)) {
      next('/')
      return
    }
  }

  const title = to.meta.title as string | undefined
  document.title = title ? `${title} - ${APP_DISPLAY_NAME}` : APP_DISPLAY_NAME
  next()
})

router.afterEach(() => {
  NProgress.done()
})

export default router
