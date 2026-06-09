<template>
  <div class="ranking-list">
    <div class="list-header">
      <h3 class="list-title">{{ title }}</h3>
      <el-tag v-if="warning" type="warning" size="small">{{ warning }}</el-tag>
    </div>
    <div class="list-content" v-loading="loading">
      <div v-if="!items.length" class="empty-state">
        <el-empty description="暂无数据" :image-size="60" />
      </div>
      <div v-else class="ranking-items">
        <div
          v-for="(item, index) in items"
          :key="item.id || index"
          class="ranking-item"
          @click="$emit('item-click', item)"
        >
          <div class="rank-badge" :class="getRankClass(index)">
            {{ index + 1 }}
          </div>
          <div class="item-content">
            <div class="item-name" :title="item.name">{{ item.name }}</div>
            <div v-if="item.subtitle" class="item-subtitle">{{ item.subtitle }}</div>
          </div>
          <div class="item-value">
            <span class="value">{{ formatValue(item.value) }}</span>
            <span v-if="valueSuffix" class="suffix">{{ valueSuffix }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface RankingItem {
  id?: number
  name: string
  value: number
  subtitle?: string
}

const props = withDefaults(defineProps<{
  title: string
  items: RankingItem[]
  loading?: boolean
  warning?: string
  valueSuffix?: string
}>(), {
  loading: false,
})

defineEmits<{
  (e: 'item-click', item: RankingItem): void
}>()

function getRankClass(index: number): string {
  if (index === 0) return 'rank-1'
  if (index === 1) return 'rank-2'
  if (index === 2) return 'rank-3'
  return ''
}

function formatValue(value: number): string {
  if (value >= 10000) {
    return `${(value / 1000).toFixed(1)}k`
  }
  return value.toLocaleString()
}
</script>

<style scoped>
.ranking-list {
  background: var(--el-bg-color);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  padding: 20px;
  height: 100%;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.list-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin: 0;
}

.list-content {
  min-height: 200px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}

.ranking-items {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ranking-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.ranking-item:hover {
  background: var(--el-fill-color-light);
}

.rank-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
}

.rank-badge.rank-1 {
  background: linear-gradient(135deg, #FFD700, #FFA500);
  color: white;
}

.rank-badge.rank-2 {
  background: linear-gradient(135deg, #C0C0C0, #A0A0A0);
  color: white;
}

.rank-badge.rank-3 {
  background: linear-gradient(135deg, #CD7F32, #B87333);
  color: white;
}

.item-content {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 14px;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-subtitle {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.item-value {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.item-value .value {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.item-value .suffix {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
