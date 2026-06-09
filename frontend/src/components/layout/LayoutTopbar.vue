<template>
  <header class="topbar">
    <div class="topbar-left">
      <div class="mobile-menu-btn" @click="$emit('toggle-mobile-menu')">
        <Menu :size="20" :stroke-width="1.5" />
      </div>
      <router-link v-if="workspaceName && workspaceLink" :to="workspaceLink" class="topbar-workspace-badge">
        <Building2 :size="14" :stroke-width="1.5" />
        <span>当前：{{ workspaceName }}</span>
      </router-link>
      <el-breadcrumb separator="/" class="topbar-breadcrumb">
        <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
        <el-breadcrumb-item v-if="parentBreadcrumb" :to="{ path: parentBreadcrumb.path }">
          {{ parentBreadcrumb.title }}
        </el-breadcrumb-item>
        <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
      </el-breadcrumb>
    </div>
    <div class="topbar-right">
      <div class="search-trigger" @click="$emit('open-search')" title="搜索页面 (Ctrl+K)">
        <SearchIcon :size="18" :stroke-width="1.5" />
        <span class="search-trigger-text">搜索</span>
        <kbd class="search-trigger-kbd">⌘K</kbd>
      </div>
      <div class="theme-toggle" @click="$emit('toggle-theme')" :title="isDark === 'dark' ? '切换到浅色模式' : '切换到深色模式'">
        <Moon v-if="isDark !== 'dark'" :size="18" :stroke-width="1.5" />
        <Sun v-else :size="18" :stroke-width="1.5" />
      </div>
      <el-dropdown trigger="click" @command="onCommand">
        <div class="topbar-avatar">
          <div class="avatar-circle">
            {{ (username || 'U').charAt(0).toUpperCase() }}
          </div>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <div class="dropdown-user-info">
                <strong>{{ username }}</strong>
                <span>{{ email }}</span>
              </div>
            </el-dropdown-item>
            <el-dropdown-item command="system" divided>
              <Settings :size="14" :stroke-width="1.5" style="margin-right: 6px" />系统设置
            </el-dropdown-item>
            <el-dropdown-item command="logout">
              <LogOut :size="14" :stroke-width="1.5" style="margin-right: 6px" />退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Building2, LogOut, Menu, Moon, Search as SearchIcon, Settings, Sun } from 'lucide-vue-next'

interface BreadcrumbItem {
  title: string
  path: string
}

defineProps<{
  workspaceLink?: string
  workspaceName?: string
  parentBreadcrumb?: BreadcrumbItem | null
  currentTitle: string
  isDark: string
  username?: string
  email?: string
}>()

const emit = defineEmits<{
  (e: 'toggle-mobile-menu'): void
  (e: 'open-search'): void
  (e: 'toggle-theme'): void
  (e: 'command', value: string): void
}>()

function onCommand(command: string | number | object) {
  if (typeof command === 'string') {
    emit('command', command)
  }
}
</script>

<style scoped>
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

.mobile-menu-btn,
.theme-toggle {
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

.mobile-menu-btn {
  display: none;
}

.mobile-menu-btn:hover,
.theme-toggle:hover {
  background: var(--gray-50);
  border-color: var(--border-color);
  color: var(--text-primary);
}

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

[data-theme="dark"] .topbar {
  background: rgba(28, 28, 30, 0.85);
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

  .mobile-menu-btn {
    display: flex;
  }

  .topbar {
    padding: 0 16px;
  }
}
</style>
