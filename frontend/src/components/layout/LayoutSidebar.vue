<template>
  <div v-if="mobileMenuOpen" class="mobile-overlay" @click="$emit('close-mobile')"></div>
  <aside class="sidebar" :class="{ collapsed: sidebarCollapsed, 'mobile-open': mobileMenuOpen }">
    <div class="sidebar-brand" @click="navigateHome">
      <div class="brand-mark">
        <img src="/logo.svg" alt="" class="brand-mark-img" />
      </div>
      <transition name="fade">
        <span v-show="!sidebarCollapsed" class="brand-text">企业多模态知识协作共享服务平台</span>
      </transition>
    </div>

    <nav class="sidebar-nav">
      <div class="nav-section">
        <el-tooltip content="使用指南" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/guide" class="nav-link guide-link" :class="{ active: activeMenu === '/guide' }">
            <BookOpen :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">使用指南</span>
          </router-link>
        </el-tooltip>
      </div>

      <div class="nav-section">
        <div v-show="!sidebarCollapsed" class="nav-label">核心功能</div>
        <el-tooltip content="智能对话" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/chat" class="nav-link" :class="{ active: activeMenu === '/chat' }">
            <MessageSquare :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">智能对话</span>
          </router-link>
        </el-tooltip>
        <el-tooltip content="知识库" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/knowledge" class="nav-link" :class="{ active: activeMenu === '/knowledge' }">
            <LibraryBig :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">知识库</span>
          </router-link>
        </el-tooltip>
        <el-tooltip content="模型管理" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/models" class="nav-link" :class="{ active: activeMenu === '/models' }">
            <BrainCircuit :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">模型管理</span>
          </router-link>
        </el-tooltip>
      </div>

      <div class="nav-section">
        <div v-show="!sidebarCollapsed" class="nav-label">数据管理</div>
        <el-tooltip content="数据库管理" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/databases" class="nav-link" :class="{ active: activeMenu === '/databases' }">
            <Database :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">数据库管理</span>
          </router-link>
        </el-tooltip>
        <el-tooltip content="检索测试" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/retrieval" class="nav-link" :class="{ active: activeMenu === '/retrieval' }">
            <SearchIcon :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">检索测试</span>
          </router-link>
        </el-tooltip>
      </div>

      <div class="nav-section">
        <div v-show="!sidebarCollapsed" class="nav-label">扩展功能</div>
        <el-tooltip content="技能市场" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/skills" class="nav-link" :class="{ active: activeMenu === '/skills' }">
            <Puzzle :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">技能市场</span>
          </router-link>
        </el-tooltip>
        <el-tooltip content="输出模板" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/templates" class="nav-link" :class="{ active: activeMenu === '/templates' }">
            <FileText :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">输出模板</span>
          </router-link>
        </el-tooltip>
        <el-tooltip content="应用发布" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/apps" class="nav-link" :class="{ active: activeMenu === '/apps' }">
            <Globe :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">应用发布</span>
          </router-link>
        </el-tooltip>
        <el-tooltip content="渠道管理" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/channels" class="nav-link" :class="{ active: activeMenu === '/channels' }">
            <Radio :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">渠道管理</span>
          </router-link>
        </el-tooltip>
      </div>

      <div class="nav-section">
        <div v-show="!sidebarCollapsed" class="nav-label nav-label-toggle" @click="$emit('toggle-advanced-nav')">
          高级功能
          <span class="nav-label-arrow" :class="{ open: advancedNavOpen }">›</span>
        </div>
        <template v-if="advancedNavOpen || sidebarCollapsed">
          <el-tooltip content="自动化" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
            <router-link to="/automations" class="nav-link" :class="{ active: activeMenu === '/automations' }">
              <Zap :size="18" :stroke-width="1.5" />
              <span v-show="!sidebarCollapsed" class="nav-link-text">自动化</span>
            </router-link>
          </el-tooltip>
          <el-tooltip content="工作空间" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
            <router-link to="/workspaces" class="nav-link" :class="{ active: activeMenu === '/workspaces' }">
              <Building2 :size="18" :stroke-width="1.5" />
              <span v-show="!sidebarCollapsed" class="nav-link-text">工作空间</span>
            </router-link>
          </el-tooltip>
          <el-tooltip content="多Agent协作" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
            <router-link to="/agents" class="nav-link" :class="{ active: activeMenu === '/agents' }">
              <Bot :size="18" :stroke-width="1.5" />
              <span v-show="!sidebarCollapsed" class="nav-link-text">多Agent</span>
            </router-link>
          </el-tooltip>
          <el-tooltip content="MCP 服务器" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
            <router-link to="/mcp" class="nav-link" :class="{ active: activeMenu === '/mcp' }">
              <Cable :size="18" :stroke-width="1.5" />
              <span v-show="!sidebarCollapsed" class="nav-link-text">MCP 服务器</span>
            </router-link>
          </el-tooltip>
        </template>
      </div>

      <div class="nav-section">
        <div v-show="!sidebarCollapsed" class="nav-label">设置</div>
        <el-tooltip v-if="isAdmin" content="用户管理" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/admin/users" class="nav-link" :class="{ active: activeMenu === '/admin/users' }">
            <Users :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">用户管理</span>
          </router-link>
        </el-tooltip>
        <el-tooltip v-if="isAdmin" content="用户分析" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/admin/analytics" class="nav-link" :class="{ active: activeMenu === '/admin/analytics' }">
            <Activity :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">用户分析</span>
          </router-link>
        </el-tooltip>
        <el-tooltip v-if="isAdmin" content="系统管理" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/system" class="nav-link" :class="{ active: activeMenu === '/system' }">
            <Settings :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">系统管理</span>
          </router-link>
        </el-tooltip>
        <el-tooltip content="系统诊断" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/diagnostics" class="nav-link" :class="{ active: activeMenu === '/diagnostics' }">
            <Stethoscope :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">系统诊断</span>
          </router-link>
        </el-tooltip>
        <el-tooltip content="个人设置" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/settings" class="nav-link" :class="{ active: activeMenu === '/settings' }">
            <UserCog :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">个人设置</span>
          </router-link>
        </el-tooltip>
        <el-tooltip content="API Key" placement="right" :disabled="!sidebarCollapsed" :show-after="300">
          <router-link to="/settings/api-keys" class="nav-link" :class="{ active: activeMenu === '/settings/api-keys' }">
            <KeyRound :size="18" :stroke-width="1.5" />
            <span v-show="!sidebarCollapsed" class="nav-link-text">API Key</span>
          </router-link>
        </el-tooltip>
      </div>
    </nav>

    <div class="sidebar-bottom">
      <div v-if="!sidebarCollapsed && quotaInfo" class="sidebar-quota" @click="openSettings">
        <div class="quota-label">{{ quotaLabel }}</div>
        <el-progress
          :percentage="quotaPercent"
          :stroke-width="4"
          :show-text="false"
          :color="quotaPercent < 20 ? '#f56c6c' : '#409eff'"
          style="width: 100%"
        />
      </div>
      <div v-show="!sidebarCollapsed" class="sidebar-version">v{{ appVersion }}</div>
      <div class="sidebar-collapse-btn" @click="$emit('toggle-sidebar')">
        <PanelLeftClose v-if="!sidebarCollapsed" :size="18" :stroke-width="1.5" />
        <PanelLeftOpen v-else :size="18" :stroke-width="1.5" />
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  Database, LibraryBig, BrainCircuit, MessageSquare,
  Search as SearchIcon, Globe, Building2, Users, Settings, Radio,
  UserCog, KeyRound, PanelLeftClose, PanelLeftOpen,
  BookOpen, Activity, Puzzle, Zap,
  Bot, Stethoscope, Cable, FileText,
} from 'lucide-vue-next'

interface QuotaInfo {
  plan?: string
  trial_remaining?: number
  trial_total?: number
  token_remaining?: number
}

const props = defineProps<{
  mobileMenuOpen: boolean
  sidebarCollapsed: boolean
  activeMenu: string
  advancedNavOpen: boolean
  isAdmin: boolean
  quotaInfo: QuotaInfo | null
  quotaPercent: number
  appVersion: string
}>()

defineEmits<{
  (e: 'close-mobile'): void
  (e: 'toggle-advanced-nav'): void
  (e: 'toggle-sidebar'): void
}>()

const router = useRouter()

const quotaLabel = computed(() => {
  if (!props.quotaInfo) return ''
  if (props.quotaInfo.plan === 'trial') {
    return `试用额度：${props.quotaInfo.trial_remaining}/${props.quotaInfo.trial_total}`
  }
  return `算力：${formatCredit(props.quotaInfo.token_remaining || 0)}`
})

function formatCredit(n: number) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

function navigateHome() {
  router.push('/')
}

function openSettings() {
  router.push('/settings')
}
</script>

<style scoped>
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
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  box-shadow: 0 6px 14px rgba(13, 143, 215, 0.24);
}

.brand-mark-img {
  width: 100%;
  height: 100%;
  display: block;
}

.brand-text {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: 0;
  white-space: normal;
}

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

.sidebar-bottom {
  padding: 12px;
  border-top: 1px solid var(--sidebar-divider);
  flex-shrink: 0;
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

.fade-enter-active,
.fade-leave-active {
  transition: opacity 150ms;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

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

  .mobile-overlay {
    position: fixed;
    inset: 0;
    z-index: 999;
    background: rgba(15, 23, 42, 0.6);
    backdrop-filter: blur(2px);
  }
}
</style>
