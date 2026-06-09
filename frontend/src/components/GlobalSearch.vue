<template>
  <el-dialog
    v-model="visible"
    :show-close="false"
    width="520px"
    top="15vh"
    class="global-search-dialog"
    @close="onClose"
  >
    <div class="search-container">
      <div class="search-input-wrapper">
        <SearchIcon :size="18" :stroke-width="1.5" class="search-icon" />
        <input
          ref="inputRef"
          v-model="keyword"
          class="search-input"
          placeholder="搜索页面..."
          @keydown.down.prevent="moveDown"
          @keydown.up.prevent="moveUp"
          @keydown.enter.prevent="selectCurrent"
          @keydown.esc="visible = false"
        />
        <kbd class="search-kbd">ESC</kbd>
      </div>
      <div v-if="filteredPages.length" class="search-results">
        <div
          v-for="(page, idx) in filteredPages"
          :key="page.path"
          class="search-result-item"
          :class="{ active: activeIndex === idx }"
          @click="navigateTo(page)"
          @mouseenter="activeIndex = idx"
        >
          <component :is="page.icon" :size="16" :stroke-width="1.5" class="result-icon" />
          <div class="result-info">
            <span class="result-name">{{ page.name }}</span>
            <span v-if="page.group" class="result-group">{{ page.group }}</span>
          </div>
          <CornerDownLeft :size="14" :stroke-width="1.5" class="result-enter" />
        </div>
      </div>
      <div v-else-if="keyword" class="search-empty">
        没有匹配的页面
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, type Component as VueComponent } from 'vue'
import { useRouter } from 'vue-router'
import {
  Search as SearchIcon, Database, LibraryBig, BrainCircuit, MessageSquare,
  Search, Globe, Building2, Users, Settings, Radio, UserCog, KeyRound,
  BookOpen, Activity, CornerDownLeft, Puzzle, Zap, Bot, Stethoscope,
} from 'lucide-vue-next'

interface SearchPage {
  name: string
  path: string
  icon: VueComponent
  group: string
  keywords: string[]
}

const pages: SearchPage[] = [
  { name: '使用指南', path: '/guide', icon: BookOpen, group: '', keywords: ['指南', 'guide', '帮助', '教程'] },
  { name: '数据库管理', path: '/databases', icon: Database, group: '数据管理', keywords: ['数据库', 'database', 'db'] },
  { name: '知识库', path: '/knowledge', icon: LibraryBig, group: '数据管理', keywords: ['知识库', 'knowledge', 'kb', '文档'] },
  { name: '模型管理', path: '/models', icon: BrainCircuit, group: '数据管理', keywords: ['模型', 'model', 'llm', 'embedding'] },
  { name: '智能对话', path: '/chat', icon: MessageSquare, group: '智能应用', keywords: ['对话', 'chat', '问答', 'ai'] },
  { name: '检索测试', path: '/retrieval', icon: Search, group: '智能应用', keywords: ['检索', 'retrieval', '搜索', '测试'] },
  { name: '应用发布', path: '/apps', icon: Globe, group: '工作空间', keywords: ['应用', 'app', '发布'] },
  { name: '渠道管理', path: '/channels', icon: Radio, group: '工作空间', keywords: ['渠道', 'channel'] },
  { name: '工作空间', path: '/workspaces', icon: Building2, group: '工作空间', keywords: ['工作空间', 'workspace'] },
  { name: '技能市场', path: '/skills', icon: Puzzle, group: '智能应用', keywords: ['技能', 'skill', '市场', '插件'] },
  { name: '自动化任务', path: '/automations', icon: Zap, group: '智能应用', keywords: ['自动化', 'automation', '定时', '任务'] },
  { name: '多Agent协作', path: '/agents', icon: Bot, group: '智能应用', keywords: ['agent', '多agent', '协作', '智能体'] },
  { name: '系统诊断', path: '/diagnostics', icon: Stethoscope, group: '设置', keywords: ['诊断', 'diagnostics', '检测', '健康'] },
  { name: '用户管理', path: '/admin/users', icon: Users, group: '设置', keywords: ['用户', 'user', '管理'] },
  { name: '用户分析', path: '/admin/analytics', icon: Activity, group: '设置', keywords: ['分析', 'analytics', '统计'] },
  { name: '系统管理', path: '/system', icon: Settings, group: '设置', keywords: ['系统', 'system', '配置'] },
  { name: '个人设置', path: '/settings', icon: UserCog, group: '设置', keywords: ['设置', 'settings', '个人'] },
  { name: 'API Key 管理', path: '/settings/api-keys', icon: KeyRound, group: '设置', keywords: ['api', 'key', '密钥'] },
]

const visible = defineModel<boolean>({ default: false })
const keyword = ref('')
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement>()
const router = useRouter()

const filteredPages = computed(() => {
  if (!keyword.value.trim()) return pages
  const kw = keyword.value.trim().toLowerCase()
  return pages.filter(p =>
    p.name.toLowerCase().includes(kw) ||
    p.group.toLowerCase().includes(kw) ||
    p.keywords.some(k => k.includes(kw))
  )
})

watch(visible, (val) => {
  if (val) {
    keyword.value = ''
    activeIndex.value = 0
    nextTick(() => inputRef.value?.focus())
  }
})

watch(keyword, () => {
  activeIndex.value = 0
})

function moveDown() {
  if (activeIndex.value < filteredPages.value.length - 1) activeIndex.value++
}

function moveUp() {
  if (activeIndex.value > 0) activeIndex.value--
}

function selectCurrent() {
  const page = filteredPages.value[activeIndex.value]
  if (page) navigateTo(page)
}

function navigateTo(page: SearchPage) {
  visible.value = false
  router.push(page.path)
}

function onClose() {
  keyword.value = ''
}
</script>

<style scoped>
.search-container {
  padding: 0;
}

.search-input-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle, #e5e7eb);
}

.search-icon {
  color: var(--text-muted, #9ca3af);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 15px;
  background: transparent;
  color: var(--text-primary, #1f2937);
}

.search-input::placeholder {
  color: var(--text-muted, #9ca3af);
}

.search-kbd {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-muted, #9ca3af);
  border: 1px solid var(--border-subtle, #e5e7eb);
  font-family: inherit;
}

.search-results {
  max-height: 360px;
  overflow-y: auto;
  padding: 8px;
}

.search-result-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.search-result-item:hover,
.search-result-item.active {
  background: var(--hover-bg, #f3f4f6);
}

.result-icon {
  color: var(--text-muted, #9ca3af);
  flex-shrink: 0;
}

.search-result-item.active .result-icon {
  color: var(--primary, #4f46e5);
}

.result-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.result-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #1f2937);
}

.result-group {
  font-size: 12px;
  color: var(--text-muted, #9ca3af);
}

.result-enter {
  color: var(--text-muted, #9ca3af);
  opacity: 0;
  flex-shrink: 0;
}

.search-result-item.active .result-enter {
  opacity: 1;
}

.search-empty {
  text-align: center;
  padding: 32px 16px;
  color: var(--text-muted, #9ca3af);
  font-size: 14px;
}
</style>

<style>
.global-search-dialog .el-dialog__header {
  display: none;
}
.global-search-dialog .el-dialog__body {
  padding: 0;
}
.global-search-dialog .el-dialog {
  border-radius: 12px;
  overflow: hidden;
}
</style>
