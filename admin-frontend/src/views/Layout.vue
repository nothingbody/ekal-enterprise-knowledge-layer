<template>
  <el-container class="app-layout">
    <el-aside :width="collapsed ? '68px' : '240px'" class="app-sidebar">
      <div class="sidebar-header">
        <div class="sidebar-logo" :class="{ compact: collapsed }">
          <div class="logo-mark">
            <svg width="22" height="22" viewBox="0 0 48 46" fill="none">
              <path d="M25.946 44.938c-.664.845-2.021.375-2.021-.698V33.937a2.26 2.26 0 0 0-2.262-2.262H10.287c-.92 0-1.456-1.04-.92-1.788l7.48-10.471c1.07-1.497 0-3.578-1.842-3.578H1.237c-.92 0-1.456-1.04-.92-1.788L10.013.474c.214-.297.556-.474.92-.474h28.894c.92 0 1.456 1.04.92 1.788l-7.48 10.471c-1.07 1.498 0 3.579 1.842 3.579h11.377c.943 0 1.473 1.088.89 1.83L25.947 44.94z" fill="rgba(255,255,255,0.95)"/>
            </svg>
          </div>
          <transition name="fade-text">
            <span v-if="!collapsed" class="logo-text">知枢管理后台</span>
          </transition>
        </div>
      </div>

      <div class="sidebar-nav">
        <div class="nav-group">
          <div v-if="!collapsed" class="nav-group-label">概览</div>
          <router-link to="/dashboard" class="nav-item" :class="{ active: $route.path === '/dashboard' }">
            <el-icon><DataAnalysis /></el-icon>
            <span v-if="!collapsed">仪表板</span>
          </router-link>
        </div>

        <div class="nav-group" v-if="hasRole(Role.ADMIN)">
          <div v-if="!collapsed" class="nav-group-label">管理</div>
          <router-link to="/users" class="nav-item" :class="{ active: $route.path.startsWith('/users') }">
            <el-icon><User /></el-icon>
            <span v-if="!collapsed">用户管理</span>
          </router-link>
          <router-link to="/organizations" class="nav-item" :class="{ active: $route.path.startsWith('/organizations') }">
            <el-icon><OfficeBuilding /></el-icon>
            <span v-if="!collapsed">组织管理</span>
          </router-link>
          <router-link to="/devices" class="nav-item" :class="{ active: $route.path === '/devices' }">
            <el-icon><Monitor /></el-icon>
            <span v-if="!collapsed">设备管理</span>
          </router-link>
          <router-link to="/platform-models" class="nav-item" :class="{ active: $route.path === '/platform-models' }">
            <el-icon><Cpu /></el-icon>
            <span v-if="!collapsed">平台模型</span>
          </router-link>
          <router-link to="/workspaces" class="nav-item" :class="{ active: $route.path.startsWith('/workspaces') }">
            <el-icon><Briefcase /></el-icon>
            <span v-if="!collapsed">工作空间</span>
          </router-link>
          <router-link to="/knowledge-bases" class="nav-item" :class="{ active: $route.path.startsWith('/knowledge-bases') }">
            <el-icon><Collection /></el-icon>
            <span v-if="!collapsed">知识库总览</span>
          </router-link>
        </div>

        <div class="nav-group">
          <div v-if="!collapsed" class="nav-group-label">运营</div>
          <router-link to="/skills" class="nav-item" :class="{ active: $route.path === '/skills' }">
            <el-icon><MagicStick /></el-icon>
            <span v-if="!collapsed">技能市场</span>
          </router-link>
          <router-link to="/analytics" class="nav-item" :class="{ active: $route.path === '/analytics' }">
            <el-icon><TrendCharts /></el-icon>
            <span v-if="!collapsed">用量分析</span>
          </router-link>
          <router-link v-if="hasRole(Role.ADMIN)" to="/notifications" class="nav-item" :class="{ active: $route.path === '/notifications' }">
            <el-icon><Bell /></el-icon>
            <span v-if="!collapsed">通知管理</span>
          </router-link>
          <router-link v-if="hasRole(Role.SUPER_ADMIN)" to="/releases" class="nav-item" :class="{ active: $route.path === '/releases' }">
            <el-icon><Download /></el-icon>
            <span v-if="!collapsed">版本管理</span>
          </router-link>
          <router-link v-if="hasRole(Role.ADMIN)" to="/site-content" class="nav-item" :class="{ active: $route.path === '/site-content' }">
            <el-icon><Reading /></el-icon>
            <span v-if="!collapsed">官网内容</span>
          </router-link>
        </div>

        <div class="nav-group" v-if="hasRole(Role.ADMIN)">
          <div v-if="!collapsed" class="nav-group-label">系统</div>
          <router-link v-if="hasRole(Role.SUPER_ADMIN)" to="/settings" class="nav-item" :class="{ active: $route.path === '/settings' }">
            <el-icon><Setting /></el-icon>
            <span v-if="!collapsed">系统设置</span>
          </router-link>
          <router-link to="/audit-logs" class="nav-item" :class="{ active: $route.path === '/audit-logs' }">
            <el-icon><Document /></el-icon>
            <span v-if="!collapsed">审计日志</span>
          </router-link>
          <router-link v-if="hasRole(Role.SUPER_ADMIN)" to="/server-logs" class="nav-item" :class="{ active: $route.path === '/server-logs' }">
            <el-icon><Tickets /></el-icon>
            <span v-if="!collapsed">服务器日志</span>
          </router-link>
        </div>
      </div>
    </el-aside>

    <el-container class="app-main-container">
      <el-header class="app-header">
        <div class="header-left">
          <button class="collapse-btn" @click="collapsed = !collapsed">
            <el-icon :size="18"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
          </button>
          <div class="breadcrumb-area">
            <span class="breadcrumb-home">管理后台</span>
            <span class="breadcrumb-sep">/</span>
            <span class="breadcrumb-current">{{ currentTitle }}</span>
          </div>
        </div>

        <div class="header-right">
          <el-popover placement="bottom-end" :width="380" trigger="click" @show="loadMyNotifications">
            <template #reference>
              <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99" class="notif-badge">
                <button class="notif-btn">
                  <el-icon :size="18"><Bell /></el-icon>
                </button>
              </el-badge>
            </template>
            <div class="notif-popover">
              <div class="notif-popover-header">
                <span class="notif-popover-title">通知</span>
                <el-button link size="small" @click="markAllRead" :disabled="unreadCount === 0">全部已读</el-button>
              </div>
              <div v-if="myNotifications.length === 0" class="notif-empty">暂无通知</div>
              <div v-else class="notif-list">
                <div
                  v-for="n in myNotifications"
                  :key="n.id"
                  class="notif-item"
                  :class="{ unread: !n.is_read }"
                  @click="markRead(n)"
                >
                  <div class="notif-item-dot" v-if="!n.is_read"></div>
                  <div class="notif-item-body">
                    <div class="notif-item-title">{{ n.title }}</div>
                    <div class="notif-item-content">{{ n.content }}</div>
                    <div class="notif-item-meta">
                      <el-tag :type="n.type === 'system' ? 'primary' : n.type === 'team' ? 'success' : 'warning'" size="small" effect="plain" round>
                        {{ notificationTypeLabel(n.type) }}
                      </el-tag>
                      <span>{{ n.created_at ? timeAgo(n.created_at) : '' }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </el-popover>

          <el-dropdown @command="handleCommand" trigger="click">
            <div class="user-block">
              <div class="user-avatar">{{ userStore.userInfo?.username?.[0]?.toUpperCase() }}</div>
              <div v-if="!collapsed" class="user-info">
                <span class="user-name">{{ userStore.userInfo?.username }}</span>
                <span class="user-role">{{ userRoleLabel(userStore.userInfo?.role) }}</span>
              </div>
              <el-icon class="dropdown-arrow"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="app-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '../stores/user'
import { ElMessageBox } from 'element-plus'
import request from '../utils/request'
import { Role, checkRoleLevel } from '@rag-platform/shared-utils'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const collapsed = ref(false)

function hasRole(minRole: Role): boolean {
  const role = userStore.userInfo?.role
  if (!role) return false
  return checkRoleLevel(role as Role, minRole)
}

const titleMap: Record<string, string> = {
  '/dashboard': '仪表板',
  '/users': '用户管理',
  '/organizations': '组织管理',
  '/devices': '设备管理',
  '/platform-models': '平台模型',
  '/workspaces': '工作空间',
  '/knowledge-bases': '知识库总览',
  '/skills': '技能市场',
  '/analytics': '用量分析',
  '/settings': '系统设置',
  '/audit-logs': '审计日志',
  '/server-logs': '服务器日志',
  '/notifications': '通知管理',
  '/releases': '版本管理',
  '/site-content': '官网内容',
}

const unreadCount = ref(0)
const myNotifications = ref<any[]>([])
const notificationTypeMap: Record<string, string> = {
  system: '系统',
  team: '团队',
  personal: '个人',
}
const userRoleMap: Record<string, string> = {
  super_admin: '超级管理员',
  admin: '管理员',
  org_admin: '组织管理员',
}

function timeAgo(dateStr: string) {
  const d = new Date(dateStr)
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} 天前`
  return d.toLocaleDateString()
}

function notificationTypeLabel(type: unknown) {
  const key = typeof type === 'string' ? type : ''
  return notificationTypeMap[key] || key
}

function userRoleLabel(role: unknown) {
  const key = typeof role === 'string' ? role : ''
  return userRoleMap[key] || '用户'
}

async function loadUnreadCount() {
  try {
    const res: any = await request.get('/notifications/unread-count')
    unreadCount.value = res.count || 0
  } catch { /* ignore */ }
}

async function loadMyNotifications() {
  try {
    const res: any = await request.get('/notifications/mine', { params: { page_size: 10 } })
    myNotifications.value = res.items || []
  } catch { /* ignore */ }
}

async function markRead(n: any) {
  if (n.is_read) return
  try {
    await request.put(`/notifications/${n.id}/read`)
    n.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch { /* ignore */ }
}

async function markAllRead() {
  try {
    await request.post('/notifications/read-all')
    myNotifications.value.forEach((n: any) => { n.is_read = true })
    unreadCount.value = 0
  } catch { /* ignore */ }
}

const currentTitle = computed(() => {
  if (route.path.match(/^\/users\/\d+\/detail$/)) return '用户详情'
  if (route.path.match(/^\/organizations\/\d+\/detail$/)) return '组织详情'
  return titleMap[route.path] || (route.meta?.title as string) || '管理后台'
})

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  try {
    await userStore.fetchMe()
    loadUnreadCount()
    pollTimer = setInterval(loadUnreadCount, 60000)
  } catch {
    router.push('/login')
  }
})

onUnmounted(() => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
})

async function handleCommand(cmd: string) {
  if (cmd === 'logout') {
    try {
      await ElMessageBox.confirm('确定退出登录？', '退出确认', { type: 'warning', confirmButtonText: '退出', cancelButtonText: '取消' })
    } catch { return }
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    await userStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.app-layout { height: 100vh; overflow: hidden; }

.app-sidebar {
  background: var(--bg-sidebar);
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: none;
}

.sidebar-header { padding: 0 16px; }

.sidebar-logo {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 0 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.sidebar-logo.compact { justify-content: center; padding: 0; }

.logo-mark {
  width: 32px;
  height: 32px;
  background: rgba(255,255,255,0.1);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.logo-text {
  font-size: 15px;
  font-weight: 600;
  color: #FFFFFF;
  white-space: nowrap;
  letter-spacing: 0.01em;
}

.fade-text-enter-active,
.fade-text-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}
.fade-text-enter-from,
.fade-text-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}

.sidebar-nav {
  flex: 1;
  padding: 14px 10px;
  overflow-y: auto;
}

.nav-group { margin-bottom: 6px; }

.nav-group-label {
  font-size: 10px;
  font-weight: 600;
  color: rgba(148, 163, 184, 0.45);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 14px 14px 6px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 9px 14px;
  border-radius: 7px;
  color: rgba(160, 174, 192, 0.9);
  text-decoration: none;
  font-size: 13.5px;
  font-weight: 400;
  transition: all 0.2s;
  margin-bottom: 1px;
  cursor: pointer;
  position: relative;
}

.nav-item:hover {
  color: #FFFFFF;
  background: rgba(255, 255, 255, 0.06);
}

.nav-item.active {
  color: #FFFFFF;
  background: rgba(0, 102, 255, 0.15);
  font-weight: 500;
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--brand-primary);
}

.nav-item .el-icon { font-size: 17px; }

.app-main-container {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-page);
}

.app-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #FFFFFF;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.collapse-btn {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: transparent;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.2s;
}

.collapse-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-dark);
}

.breadcrumb-area {
  display: flex;
  align-items: center;
  gap: 6px;
}

.breadcrumb-home {
  font-size: 13px;
  color: var(--text-tertiary);
  cursor: default;
}

.breadcrumb-sep {
  font-size: 13px;
  color: var(--text-quaternary);
}

.breadcrumb-current {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-right { display: flex; align-items: center; gap: 4px; }

.user-block {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.user-block:hover { background: var(--bg-hover); }

.user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--brand-gradient);
  color: #FFFFFF;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.user-info {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.user-role {
  font-size: 11px;
  color: var(--text-tertiary);
}

.dropdown-arrow {
  color: var(--text-quaternary);
  font-size: 12px;
  margin-left: 2px;
}

.app-content {
  padding: 24px;
  overflow-y: auto;
  background: var(--bg-page);
}

.notif-badge { margin-right: 8px; }

.notif-btn {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: transparent;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.2s;
}

.notif-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-dark);
}

.notif-popover-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-light);
  margin-bottom: 8px;
}

.notif-popover-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.notif-empty {
  text-align: center;
  padding: 32px 0;
  color: var(--text-tertiary);
  font-size: 14px;
}

.notif-list {
  max-height: 360px;
  overflow-y: auto;
}

.notif-item {
  display: flex;
  gap: 10px;
  padding: 10px 6px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.notif-item:hover { background: #F9FAFB; }

.notif-item.unread { background: var(--brand-primary-bg); }
.notif-item.unread:hover { background: var(--brand-primary-light); }

.notif-item-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--brand-primary);
  margin-top: 6px;
  flex-shrink: 0;
}

.notif-item-body { flex: 1; min-width: 0; }

.notif-item-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.notif-item-content {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}

.notif-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-tertiary);
}
</style>
