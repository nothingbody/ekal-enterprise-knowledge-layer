<template>
  <div class="layout-root">
    <LayoutSidebar
      :mobile-menu-open="mobileMenuOpen"
      :sidebar-collapsed="sidebarCollapsed"
      :active-menu="activeMenu"
      :advanced-nav-open="advancedNavOpen"
      :is-admin="userStore.userInfo?.role === 'admin'"
      :quota-info="quotaInfo"
      :quota-percent="quotaPercent"
      :app-version="APP_VERSION"
      @close-mobile="mobileMenuOpen = false"
      @toggle-advanced-nav="advancedNavOpen = !advancedNavOpen"
      @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
    />

    <!-- ═══ Main ═══ -->
    <div class="layout-body">
      <!-- Readiness warning banner -->
      <ReadinessBanner />

      <!-- Trial banner -->
      <div v-if="quotaInfo && quotaInfo.plan === 'trial'" class="trial-banner">
        <div class="trial-banner-content">
          <span class="trial-banner-icon">🎁</span>
          <span>您正在使用<strong>免费试用版</strong>，共 {{ quotaInfo.trial_total }} 次对话额度，已使用 {{ quotaInfo.trial_used }} 次，剩余 <strong>{{ quotaInfo.trial_remaining }}</strong> 次</span>
          <el-tag v-if="quotaInfo.trial_remaining <= 10" type="danger" size="small" effect="dark" style="margin-left: 8px">即将用尽</el-tag>
        </div>
        <el-button size="small" type="warning" round @click="$router.push('/settings')">升级方案</el-button>
      </div>
 
      <!-- Topbar — clean, minimal -->
      <LayoutTopbar
        :workspace-link="workspaceLink"
        :workspace-name="workspaceName"
        :parent-breadcrumb="parentBreadcrumb"
        :current-title="currentTitle"
        :is-dark="isDark"
        :username="userStore.userInfo?.username"
        :email="userStore.userInfo?.email"
        @toggle-mobile-menu="mobileMenuOpen = !mobileMenuOpen"
        @open-search="searchVisible = true"
        @toggle-theme="toggleTheme"
        @command="handleCommand"
      />
 
      <!-- Content -->
      <main class="content-scroll">
        <SetupWizard />
        <router-view v-slot="{ Component, route }">
          <transition name="view" mode="out-in">
            <keep-alive :max="8">
              <component :is="Component" :key="route.fullPath" />
            </keep-alive>
          </transition>
        </router-view>
      </main>
    </div>

    <GlobalSearch v-model="searchVisible" />
    <div v-if="userStore.userInfo?.email" class="watermark-layer" :style="watermarkStyle"></div>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { ElMessageBox } from 'element-plus'
  import { useStorage } from '@vueuse/core'
  import {
    Layers, Database, LibraryBig, BrainCircuit, MessageSquare,
    Search as SearchIcon, Globe, Building2, Users, Settings, Radio,
    UserCog, KeyRound, PanelLeftClose, PanelLeftOpen,
    BookOpen, Activity, Puzzle, Zap,
    Bot, Stethoscope, Cable, FileText,
  } from 'lucide-vue-next'
  import { APP_VERSION } from '../../version'
  import { useUserStore } from '../../stores/user'
  import { useWorkspaceStore } from '../../stores/workspace'
  import request from '../../utils/request'
  import ReadinessBanner from '../../components/ReadinessBanner.vue'
  import SetupWizard from '../../components/SetupWizard.vue'
  import GlobalSearch from '../../components/GlobalSearch.vue'
  import LayoutTopbar from '../../components/layout/LayoutTopbar.vue'
  import LayoutSidebar from '../../components/layout/LayoutSidebar.vue'

  const quotaInfo = ref<any>(null)
  const quotaPercent = computed(() => {
    if (!quotaInfo.value) return 100
    if (quotaInfo.value.plan === 'trial') {
      const total = quotaInfo.value.trial_total || 1
      return Math.round((quotaInfo.value.trial_remaining / total) * 100)
    }
    const total = quotaInfo.value.token_credit || 1
    return Math.round((quotaInfo.value.token_remaining / total) * 100)
  })

  function formatCredit(n: number) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
    return String(n)
  }

  async function loadQuota() {
    try {
      quotaInfo.value = await request.get('/quota/me', { _silentError: true } as any)
    } catch (e: any) {
      console.warn('[Layout] 加载用量配额失败:', e?.message || e)
    }
  }

  const route = useRoute()
  const router = useRouter()
  const userStore = useUserStore()
  const workspaceStore = useWorkspaceStore()
  const sidebarCollapsed = useStorage('sidebarCollapsed', false)

  const watermarkStyle = computed(() => {
    const email = userStore.userInfo?.email || ''
    if (!email) return {}
    const canvas = document.createElement('canvas')
    canvas.width = 300
    canvas.height = 200
    const ctx = canvas.getContext('2d')
    if (!ctx) return {}
    ctx.clearRect(0, 0, 300, 200)
    ctx.font = '14px -apple-system, sans-serif'
    ctx.fillStyle = 'rgba(0, 0, 0, 0.04)'
    ctx.textAlign = 'center'
    ctx.translate(150, 100)
    ctx.rotate(-25 * Math.PI / 180)
    ctx.fillText(email, 0, 0)
    return { backgroundImage: `url(${canvas.toDataURL()})` }
  })
  const advancedNavOpen = useStorage('advancedNavOpen', false)
  const mobileMenuOpen = ref(false)
  const isDark = useStorage('theme', 'light')

  function toggleTheme() {
    isDark.value = isDark.value === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', isDark.value)
  }

  const activeMenu = computed(() => {
    if (route.path.startsWith('/knowledge')) return '/knowledge'
    if (route.path.startsWith('/workspaces')) return '/workspaces'
    if (route.path.startsWith('/admin/analytics')) return '/admin/analytics'
    if (route.path.startsWith('/admin')) return '/admin/users'
    return route.path
  })

  const currentTitle = computed(() => (route.meta.title as string) || '')
  const parentBreadcrumb = computed(() => {
    const meta = route.meta
    if (meta.parentTitle && meta.parentPath) {
      return { title: meta.parentTitle as string, path: meta.parentPath as string }
    }
    return null
  })
  const workspaceName = computed(() => workspaceStore.currentWorkspace?.name || '')
  const workspaceLink = computed(() => workspaceStore.currentWorkspace ? `/workspaces/${workspaceStore.currentWorkspace.id}` : '')
  const searchVisible = ref(false)

  function handleGlobalKeydown(e: KeyboardEvent) {
    const mod = e.ctrlKey || e.metaKey
    if (mod && e.key.toLowerCase() === 'k') {
      e.preventDefault()
      searchVisible.value = true
    }
    if (mod && e.key.toLowerCase() === 'n') {
      e.preventDefault()
      router.push('/chat')
    }
  }

  onMounted(() => {
    if (!userStore.userInfo) {
      userStore.fetchUserInfo()
    }
    document.documentElement.setAttribute('data-theme', isDark.value)
    window.addEventListener('keydown', handleGlobalKeydown)
    loadQuota()
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleGlobalKeydown)
  })

  watch(() => route.path, () => {
    mobileMenuOpen.value = false
  })

  function handleCommand(cmd: string) {
    if (cmd === 'logout') {
      ElMessageBox.confirm('确定退出登录？', '确认', { type: 'info' }).then(async () => {
        try { await request.post('/auth/logout', { refresh_token: userStore.refreshToken || undefined }) } catch {}
        userStore.clearToken()
        router.push('/login')
      }).catch(() => {})
    } else if (cmd === 'system') {
      router.push('/system')
    }
  }
</script>

<style scoped>
/* ══════════════════════════════════════════
  Layout — Modern SaaS / Enterprise Style
  ══════════════════════════════════════════ */
.layout-root {
  display: flex;
  height: 100vh;
  overflow: hidden;
  position: relative;
}

.watermark-layer {
  position: fixed;
  inset: 0;
  z-index: 9999;
  pointer-events: none;
  background-repeat: repeat;
}

/* ── Sidebar — Clean Minimal ── */
.sidebar {
  width: var(--sidebar-width);
  background: var(--sidebar-bg);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
  transition: width var(--duration-slow) var(--ease-in-out);
  z-index: 100;
  border-right: 1px solid var(--sidebar-divider);
  will-change: width;
}

.sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

/* ── Brand ── */
.sidebar-brand {
  height: var(--header-height);
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 12px;
  cursor: pointer;
  flex-shrink: 0;
  border-bottom: 1px solid transparent;
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 2px 4px rgba(22, 93, 255, 0.2);
}

.brand-text {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  white-space: nowrap;
}

/* ── Nav ── */
.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 12px 0;
}

.nav-section {
  margin-bottom: 16px;
}

.nav-label {
  padding: 0 8px 8px;
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
}

.nav-label-toggle {
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
  transition: color var(--duration-fast);
}
.nav-label-toggle:hover {
  color: var(--text-secondary);
}
.nav-label-arrow {
  font-size: 13px;
  transition: transform var(--duration-fast);
  transform: rotate(0deg);
}
.nav-label-arrow.open {
  transform: rotate(90deg);
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  height: 34px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  white-space: nowrap;
  margin-bottom: 2px;
  position: relative;
  transition: all var(--duration-fast) var(--ease-out);
}

.nav-link:hover {
  background: var(--sidebar-hover);
  color: var(--text-primary);
}

.nav-link.active {
  background: var(--sidebar-active-bg);
  color: var(--primary);
  font-weight: 600;
}
.nav-link.active::before {
  content: '';
  position: absolute;
  left: -12px;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--primary);
}

/* ── Sidebar bottom ── */
.sidebar-bottom {
  padding: 12px;
  border-top: 1px solid var(--sidebar-divider);
  flex-shrink: 0;
}
.trial-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 20px;
  background: linear-gradient(90deg, #fff7ed 0%, #fffbeb 100%);
  border-bottom: 1px solid #fed7aa;
  font-size: 13px;
  color: #92400e;
}

.trial-banner-content {
  display: flex;
  align-items: center;
  gap: 6px;
}

.trial-banner-icon {
  font-size: 16px;
}

.sidebar-quota {
  padding: 8px 12px;
  margin: 0 8px 6px;
  background: var(--gray-50, #f9f9f9);
  border-radius: 6px;
  cursor: pointer;
  transition: background var(--duration-fast, 0.15s);
}

.sidebar-quota:hover {
  background: var(--bg-hover, #f0f0f0);
}

.quota-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
  font-weight: 500;
}

.sidebar-version {
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
  padding: 0 0 8px;
  user-select: none;
  font-weight: 500;
}

.sidebar-collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 32px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-fast);
  border: 1px solid transparent;
}

.sidebar-collapse-btn:hover {
  background: var(--sidebar-hover);
  border-color: var(--border-color);
  color: var(--text-primary);
}

/* ── Collapsed State ── */
.guide-link {
  color: var(--primary) !important;
}

.collapsed .nav-link {
  justify-content: center;
  padding: 0;
  border-radius: var(--radius-sm);
  width: 36px;
  height: 36px;
  margin: 2px auto;
}
.collapsed .sidebar-brand {
  justify-content: center;
  padding: 0;
}
.collapsed .sidebar-nav {
  padding: 12px 8px 0;
}
.collapsed .nav-label {
  display: none;
}
.collapsed .nav-link.active::before {
  left: -8px;
}

/* ── Fade transition ── */
.fade-enter-active, .fade-leave-active {
  transition: opacity 150ms;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* ══════════════════════════════════════════
   Topbar — Clean & Sharp
   ══════════════════════════════════════════ */
.layout-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.topbar {
  height: var(--header-height);
  background: var(--header-bg);
  backdrop-filter: var(--header-blur);
  -webkit-backdrop-filter: var(--header-blur);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 50;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.topbar-workspace-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--primary);
  background: var(--primary-lighter, rgba(var(--primary-rgb, 59 130 246), 0.1));
  border: 1px solid var(--primary-light, rgba(var(--primary-rgb, 59 130 246), 0.3));
  border-radius: var(--radius-sm);
  text-decoration: none;
  font-weight: 500;
  transition: opacity var(--duration-fast);
}
.topbar-workspace-badge:hover {
  opacity: 0.9;
}

.topbar-breadcrumb {
  font-size: 13px;
}
.topbar-breadcrumb :deep(.el-breadcrumb__inner) {
  font-weight: 500;
  color: var(--text-secondary);
}
.topbar-breadcrumb :deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) {
  font-weight: 600;
  color: var(--text-primary);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  background: var(--gray-50);
  border: 1px solid var(--border-color);
  cursor: pointer;
  color: var(--text-muted);
  font-size: 13px;
  transition: all var(--duration-fast) var(--ease-out);
}
.search-trigger:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.search-trigger-text {
  white-space: nowrap;
}
.search-trigger-kbd {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  font-family: var(--font-mono);
  margin-left: 8px;
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .search-trigger-text,
  .search-trigger-kbd {
    display: none;
  }
  .search-trigger {
    padding: 6px;
    background: transparent;
    border-color: transparent;
  }
}

.mobile-menu-btn, .theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--duration-fast);
  border: 1px solid transparent;
}
.mobile-menu-btn { display: none; }
@media (max-width: 768px) { .mobile-menu-btn { display: flex; } }

.mobile-menu-btn:hover, .theme-toggle:hover {
  background: var(--gray-50);
  border-color: var(--border-color);
  color: var(--text-primary);
}

/* ── Topbar avatar ── */
.topbar-avatar {
  cursor: pointer;
  padding: 2px;
  border-radius: var(--radius-full);
  transition: transform var(--duration-fast);
}
.topbar-avatar:hover {
  transform: scale(1.05);
}

.avatar-circle {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  border: 2px solid var(--card-bg);
  box-shadow: var(--shadow-sm);
}

.dropdown-user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: var(--text-muted);
}
.dropdown-user-info strong {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
}

/* ══════════════════════════════════════════
   Content Area
   ══════════════════════════════════════════ */
.content-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
  background: var(--content-bg);
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
}

/* ── Page Transitions ── */
.view-enter-active {
  transition: opacity var(--duration-base) var(--ease-out),
              transform var(--duration-base) var(--ease-out);
}
.view-leave-active {
  transition: opacity 120ms var(--ease-out);
}
.view-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.view-leave-to {
  opacity: 0;
}

/* ── Dark mode topbar ── */
[data-theme="dark"] .topbar {
  background: rgba(28, 28, 30, 0.85);
}

/* ══════════════════════════════════════════
   Mobile Responsive
   ══════════════════════════════════════════ */
@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    z-index: 1000;
    transform: translateX(-100%);
    transition: transform var(--duration-base) var(--ease-out);
    box-shadow: var(--shadow-xl);
  }
  .sidebar.mobile-open {
    transform: translateX(0);
  }
  .layout-body {
    margin-left: 0 !important;
  }
  .content-scroll {
    padding: 16px;
  }
  .topbar {
    padding: 0 16px !important;
  }
  .mobile-overlay {
    position: fixed;
    inset: 0;
    z-index: 999;
    background: rgba(15, 23, 42, 0.6);
    backdrop-filter: blur(2px);
  }
}
</style>
