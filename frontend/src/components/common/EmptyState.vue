<template>
  <div class="empty-state" :class="[`empty-${type}`, { compact }]">
    <div class="empty-icon">
      <component :is="iconComponent" :size="compact ? 32 : 48" :stroke-width="1.5" />
    </div>
    <h3 v-if="title" class="empty-title">{{ title }}</h3>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <div v-if="$slots.default || action" class="empty-actions">
      <slot>
        <el-button v-if="action" type="primary" @click="handleAction">
          {{ action.text }}
        </el-button>
      </slot>
    </div>
    <div v-if="tips?.length" class="empty-tips">
      <div v-for="(tip, i) in tips" :key="i" class="tip-item">
        <Lightbulb :size="14" :stroke-width="1.5" />
        <span>{{ tip }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  FolderOpen,
  FileText,
  MessageSquare,
  Settings,
  Search,
  Database,
  Bot,
  Lightbulb,
  Inbox,
} from 'lucide-vue-next'

export interface EmptyAction {
  text: string
  route?: string
  handler?: () => void
}

const props = withDefaults(defineProps<{
  type?: 'default' | 'knowledge' | 'document' | 'chat' | 'model' | 'search' | 'database'
  title?: string
  description?: string
  action?: EmptyAction | null
  tips?: string[]
  compact?: boolean
}>(), {
  type: 'default',
  compact: false,
})

const router = useRouter()

const iconMap = {
  default: Inbox,
  knowledge: FolderOpen,
  document: FileText,
  chat: MessageSquare,
  model: Bot,
  search: Search,
  database: Database,
}

const iconComponent = computed(() => iconMap[props.type] || Inbox)

function handleAction() {
  if (props.action?.handler) {
    props.action.handler()
  } else if (props.action?.route) {
    router.push(props.action.route)
  }
}
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.empty-state.compact {
  padding: 24px 16px;
}

.empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  margin-bottom: 16px;
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 50%;
  color: var(--el-text-color-secondary, #909399);
}

.compact .empty-icon {
  width: 56px;
  height: 56px;
  margin-bottom: 12px;
}

.empty-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 500;
  color: var(--el-text-color-primary, #303133);
}

.compact .empty-title {
  font-size: 14px;
}

.empty-desc {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--el-text-color-secondary, #909399);
  max-width: 320px;
}

.compact .empty-desc {
  font-size: 13px;
  margin-bottom: 12px;
}

.empty-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.empty-tips {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.tip-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular, #606266);
}

.tip-item svg {
  color: var(--el-color-warning, #e6a23c);
}

/* 不同类型的主题色 */
.empty-knowledge .empty-icon {
  background: rgba(64, 158, 255, 0.1);
  color: var(--el-color-primary, #409eff);
}

.empty-document .empty-icon {
  background: rgba(103, 194, 58, 0.1);
  color: var(--el-color-success, #67c23a);
}

.empty-chat .empty-icon {
  background: rgba(144, 147, 153, 0.1);
  color: var(--el-text-color-secondary, #909399);
}

.empty-model .empty-icon {
  background: rgba(230, 162, 60, 0.1);
  color: var(--el-color-warning, #e6a23c);
}

.empty-search .empty-icon {
  background: rgba(144, 147, 153, 0.1);
  color: var(--el-text-color-secondary, #909399);
}

.empty-database .empty-icon {
  background: rgba(245, 108, 108, 0.1);
  color: var(--el-color-danger, #f56c6c);
}
</style>
