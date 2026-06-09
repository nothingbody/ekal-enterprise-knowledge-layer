<template>
  <div v-if="mobileOpen" class="mobile-sidebar-mask" @click="$emit('close-mobile')"></div>
  <div class="chat-sidebar" :class="{ 'mobile-open': mobileOpen }">
    <div class="sidebar-top-actions">
      <el-button type="primary" class="new-chat-btn" @click="$emit('start-new-chat')">
        <PlusIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />新建对话
      </el-button>
      <el-button
        v-if="conversations.length > 0"
        size="small"
        :type="batchMode ? 'info' : 'default'"
        @click="$emit('toggle-batch-mode')"
        class="batch-toggle-btn"
      >
        {{ batchMode ? '取消' : '管理' }}
      </el-button>
    </div>
    <div v-if="batchMode" class="batch-bar">
      <el-checkbox
        :model-value="allSelected"
        :indeterminate="batchSelected.size > 0 && batchSelected.size < conversations.length"
        @change="onToggleSelectAll"
      >全选</el-checkbox>
      <el-button size="small" type="danger" :disabled="batchSelected.size === 0" @click="$emit('batch-delete')">
        <Trash2 :size="13" :stroke-width="1.5" style="margin-right: 2px" />删除 ({{ batchSelected.size }})
      </el-button>
    </div>
    <el-input
      :model-value="searchText"
      @update:model-value="onSearchInput"
      placeholder="搜索对话内容..."
      clearable
      size="small"
      style="margin: 0 8px 8px; width: calc(100% - 16px);"
    >
      <template #prefix>
        <SearchIcon :size="14" :stroke-width="1.5" />
      </template>
    </el-input>
    <div class="conv-list">
      <div v-if="searchLoading" class="conv-empty">搜索中...</div>
      <div v-else-if="!conversations.length" class="conv-empty">{{ isSearchMode ? '无匹配对话' : '暂无对话记录' }}</div>
      <div
        v-for="conv in conversations"
        :key="conv.id"
        class="conv-item"
        :class="{ active: currentConvId === conv.id }"
        @click="batchMode ? $emit('toggle-batch-item', conv.id) : $emit('select-conversation', conv.id)"
      >
        <el-checkbox
          v-if="batchMode"
          :model-value="batchSelected.has(conv.id)"
          @click.stop
          @change="$emit('toggle-batch-item', conv.id)"
        />
        <MessageCircle v-else :size="14" :stroke-width="1.5" />
        <div class="conv-info" @dblclick.stop="$emit('rename-conversation', conv)">
          <span class="conv-title">{{ conv.title || '新对话' }}</span>
          <div v-if="conv._snippets?.length" class="conv-snippets">
            <div v-for="(s, si) in conv._snippets.slice(0, 2)" :key="si" class="conv-snippet">
              <span class="snippet-role">{{ s.role === 'user' ? 'Q' : 'A' }}</span>
              <span class="snippet-text">{{ s.snippet }}</span>
            </div>
          </div>
          <span v-else class="conv-time">{{ relativeTime(conv.created_at || '') }}</span>
        </div>
        <Pin :size="13" :stroke-width="1.5" class="conv-action" :class="{ 'pinned': conv.is_pinned }" @click.stop="$emit('pin-conversation', conv.id)" :title="conv.is_pinned ? '取消置顶' : '置顶'" />
        <Pencil :size="13" :stroke-width="1.5" class="conv-action" @click.stop="$emit('rename-conversation', conv)" />
        <Trash2 :size="13" :stroke-width="1.5" class="conv-delete" @click.stop="$emit('remove-conversation', conv.id)" />
      </div>
      <div v-if="hasMore && !isSearchMode" class="conv-load-more">
        <el-button link size="small" @click="$emit('load-more')" :loading="loadingMore">加载更多对话</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Plus as PlusIcon, Search as SearchIcon, MessageCircle, Pencil, Trash2, Pin } from 'lucide-vue-next'
import { relativeTime } from '../../utils/format'

interface ConversationItem {
  id: number
  title?: string
  is_pinned?: boolean
  created_at?: string
  _snippets?: Array<{ role: string; snippet: string }>
}

const props = defineProps<{
  mobileOpen: boolean
  conversations: ConversationItem[]
  currentConvId: number | null
  batchMode: boolean
  batchSelected: Set<number>
  searchText: string
  searchLoading: boolean
  isSearchMode: boolean
  hasMore: boolean
  loadingMore: boolean
}>()

const emit = defineEmits<{
  (e: 'close-mobile'): void
  (e: 'start-new-chat'): void
  (e: 'toggle-batch-mode'): void
  (e: 'toggle-select-all', checked: boolean): void
  (e: 'batch-delete'): void
  (e: 'update:searchText', value: string): void
  (e: 'select-conversation', id: number): void
  (e: 'toggle-batch-item', id: number): void
  (e: 'rename-conversation', conv: ConversationItem): void
  (e: 'remove-conversation', id: number): void
  (e: 'pin-conversation', id: number): void
  (e: 'load-more'): void
}>()

const allSelected = computed(() => props.conversations.length > 0 && props.batchSelected.size === props.conversations.length)

function onSearchInput(value: string | number) {
  emit('update:searchText', String(value ?? ''))
}

function onToggleSelectAll(value: string | number | boolean) {
  emit('toggle-select-all', Boolean(value))
}
</script>

<style scoped>
.chat-sidebar {
  width: 260px;
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  padding: 12px;
  background: var(--gray-25);
}

.sidebar-top-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}

.sidebar-top-actions .new-chat-btn {
  flex: 1;
}

.batch-toggle-btn {
  flex-shrink: 0;
}

.batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px 8px;
  gap: 8px;
}

.new-chat-btn {
  width: 100%;
  height: 36px;
  font-weight: 500;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
}

.conv-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  padding: 40px 0;
}

.conv-snippets {
  margin-top: 3px;
}

.conv-snippet {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
  margin-bottom: 2px;
}

.snippet-role {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 500;
  background: var(--gray-100);
  color: var(--text-tertiary);
  padding: 0 4px;
  border-radius: 3px;
  margin-top: 1px;
}

.snippet-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}

.conv-load-more {
  text-align: center;
  padding: 8px 0;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  margin-bottom: 2px;
  font-size: 13px;
  color: var(--text-secondary);
  transition: all var(--duration-fast) var(--ease-out);
}

.conv-item:hover {
  background: var(--gray-100);
  color: var(--text-primary);
}

.conv-item.active {
  background: var(--primary-lighter);
  color: var(--primary);
  font-weight: 500;
  box-shadow: inset 3px 0 0 var(--primary);
}

.conv-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-time {
  font-size: 10px;
  color: var(--text-muted);
}

.conv-action {
  opacity: 0;
  color: var(--text-muted);
  cursor: pointer;
  transition: opacity var(--duration-fast);
  flex-shrink: 0;
}

.conv-item:hover .conv-action {
  opacity: 0.6;
}

.conv-action:hover {
  color: var(--primary);
  opacity: 1 !important;
}

.conv-delete {
  opacity: 0;
  color: var(--danger);
  transition: opacity var(--duration-fast);
  flex-shrink: 0;
}

.conv-item:hover .conv-delete {
  opacity: 0.7;
}

.conv-item:hover .conv-delete:hover {
  opacity: 1;
}

.mobile-sidebar-mask {
  display: none;
}

@media (max-width: 768px) {
  .chat-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 200;
    width: 280px;
    transform: translateX(-100%);
    transition: transform 0.25s var(--ease-out);
    box-shadow: none;
  }

  .chat-sidebar.mobile-open {
    transform: translateX(0);
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.15);
  }

  .mobile-sidebar-mask {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 199;
    background: rgba(0, 0, 0, 0.3);
  }
}
</style>
