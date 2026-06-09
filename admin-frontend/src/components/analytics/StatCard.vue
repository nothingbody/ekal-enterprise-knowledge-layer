<template>
  <div class="stat-card" :class="[`stat-${type}`]">
    <div class="stat-icon">
      <component :is="iconComponent" :size="24" :stroke-width="1.5" />
    </div>
    <div class="stat-content">
      <div class="stat-label">{{ label }}</div>
      <div class="stat-value">
        <span class="value">{{ formattedValue }}</span>
        <span v-if="suffix" class="suffix">{{ suffix }}</span>
      </div>
      <div v-if="change !== undefined" class="stat-change" :class="changeClass">
        <TrendingUp v-if="change > 0" :size="14" :stroke-width="1.5" />
        <TrendingDown v-else-if="change < 0" :size="14" :stroke-width="1.5" />
        <Minus v-else :size="14" :stroke-width="1.5" />
        <span>{{ changeText }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  MessageSquare,
  Users,
  FileText,
  ThumbsUp,
  TrendingUp,
  TrendingDown,
  Minus,
  Activity,
} from 'lucide-vue-next'

const props = withDefaults(defineProps<{
  label: string
  value: number
  change?: number
  type?: 'conversations' | 'messages' | 'users' | 'satisfaction' | 'default'
  suffix?: string
  format?: 'number' | 'percent'
}>(), {
  type: 'default',
  format: 'number',
})

const iconMap = {
  conversations: MessageSquare,
  messages: FileText,
  users: Users,
  satisfaction: ThumbsUp,
  default: Activity,
}

const iconComponent = computed(() => iconMap[props.type] || Activity)

const formattedValue = computed(() => {
  if (props.format === 'percent') {
    return `${(props.value * 100).toFixed(1)}%`
  }
  if (props.value >= 10000) {
    return `${(props.value / 1000).toFixed(1)}k`
  }
  return props.value.toLocaleString()
})

const changeClass = computed(() => {
  if (props.change === undefined) return ''
  if (props.change > 0) return 'positive'
  if (props.change < 0) return 'negative'
  return 'neutral'
})

const changeText = computed(() => {
  if (props.change === undefined) return ''
  const absChange = Math.abs(props.change * 100)
  if (props.change > 0) return `+${absChange.toFixed(1)}%`
  if (props.change < 0) return `-${absChange.toFixed(1)}%`
  return '0%'
})
</script>

<style scoped>
.stat-card {
  display: flex;
  gap: 16px;
  padding: 20px;
  background: var(--el-bg-color);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  transition: box-shadow 0.2s;
}

.stat-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}

.stat-conversations .stat-icon {
  background: rgba(64, 158, 255, 0.1);
  color: var(--el-color-primary);
}

.stat-messages .stat-icon {
  background: rgba(103, 194, 58, 0.1);
  color: var(--el-color-success);
}

.stat-users .stat-icon {
  background: rgba(230, 162, 60, 0.1);
  color: var(--el-color-warning);
}

.stat-satisfaction .stat-icon {
  background: rgba(245, 108, 108, 0.1);
  color: var(--el-color-danger);
}

.stat-content {
  flex: 1;
  min-width: 0;
}

.stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.stat-value {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.stat-value .value {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.stat-value .suffix {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.stat-change {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  margin-top: 4px;
}

.stat-change.positive {
  color: var(--el-color-success);
}

.stat-change.negative {
  color: var(--el-color-danger);
}

.stat-change.neutral {
  color: var(--el-text-color-secondary);
}
</style>
