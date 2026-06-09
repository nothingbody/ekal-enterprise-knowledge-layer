<template>
  <div class="analytics">
    <div class="page-header">
      <div>
        <h2>用量分析</h2>
        <p class="page-subtitle">Token 消耗与对话数据统计</p>
      </div>
      <el-button @click="loadData" :loading="loading" round>
        <el-icon><Refresh /></el-icon>刷新数据
      </el-button>
    </div>

    <div class="summary-grid">
      <div class="summary-card purple">
        <div class="summary-icon"><el-icon :size="22"><Coin /></el-icon></div>
        <div class="summary-info">
          <span class="summary-label">总 Token 消耗</span>
          <span class="summary-value">{{ formatNum(summary.total_tokens || 0) }}</span>
        </div>
      </div>
      <div class="summary-card blue">
        <div class="summary-icon"><el-icon :size="22"><Coin /></el-icon></div>
        <div class="summary-info">
          <span class="summary-label">今日 Token</span>
          <span class="summary-value">{{ formatNum(summary.today_tokens || 0) }}</span>
        </div>
      </div>
      <div class="summary-card teal">
        <div class="summary-icon"><el-icon :size="22"><ChatDotRound /></el-icon></div>
        <div class="summary-info">
          <span class="summary-label">总对话数</span>
          <span class="summary-value">{{ formatNum(summary.total_conversations || 0) }}</span>
        </div>
      </div>
    </div>

    <el-card class="chart-card">
      <template #header>
        <div class="chart-header">
          <div>
            <span class="chart-title">Token 消耗趋势</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <el-select v-model="days" size="small" style="width: 120px" @change="loadTrend">
              <el-option :value="7" label="近 7 天" />
              <el-option :value="30" label="近 30 天" />
              <el-option :value="90" label="近 90 天" />
              <el-option :value="0" label="自定义" />
            </el-select>
            <el-date-picker
              v-if="days === 0"
              v-model="customRange"
              type="daterange"
              size="small"
              range-separator="~"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              @change="loadTrend"
              style="width: 260px"
            />
          </div>
        </div>
      </template>
      <div class="chart-area">
        <div class="bar-chart">
          <div v-for="(item, idx) in trend" :key="item.date" class="bar-col" :style="{ animationDelay: idx * 15 + 'ms' }">
            <div class="bar-tooltip">{{ formatK(item.tokens) }}</div>
            <div class="bar bar-purple" :style="{ height: barH(item.tokens, maxTokens) + '%' }"></div>
            <div class="bar-label">{{ item.date.slice(5) }}</div>
          </div>
        </div>
      </div>
    </el-card>

    <el-card class="chart-card" style="margin-top: 16px;">
      <template #header>
        <div class="chart-header">
          <span class="chart-title">对话量趋势</span>
        </div>
      </template>
      <div class="chart-area">
        <div class="bar-chart">
          <div v-for="(item, idx) in trend" :key="item.date" class="bar-col" :style="{ animationDelay: idx * 15 + 'ms' }">
            <div class="bar-tooltip">{{ item.conversations }}</div>
            <div class="bar bar-teal" :style="{ height: barH(item.conversations, maxConv) + '%' }"></div>
            <div class="bar-label">{{ item.date.slice(5) }}</div>
          </div>
        </div>
      </div>
    </el-card>

    <el-card class="chart-card" style="margin-top: 16px;" v-loading="userAnalyticsLoading">
      <template #header>
        <div class="chart-header">
          <span class="chart-title">用户活跃度排行</span>
        </div>
      </template>
      <el-table v-if="userAnalytics.length" :data="userAnalytics" stripe size="small">
        <el-table-column label="#" width="50">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column label="消息数" width="100">
          <template #default="{ row }">{{ (row.msg_count || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="Token 消耗" width="120">
          <template #default="{ row }">{{ formatK(row.total_tokens || 0) }}</template>
        </el-table-column>
        <el-table-column label="对话数" width="80">
          <template #default="{ row }">{{ row.conv_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="最后活跃" width="170">
          <template #default="{ row }">{{ row.last_active ? new Date(row.last_active).toLocaleString() : '—' }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无用户活跃数据" :image-size="60" />
    </el-card>

    <div style="text-align: right; margin-top: 20px;">
      <el-button size="small" @click="exportCSV">
        <el-icon><Download /></el-icon>导出用量 CSV
      </el-button>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import request from '../utils/request'

const loading = ref(false)
const userAnalyticsLoading = ref(false)
const userAnalytics = ref<any[]>([])
const summary = ref<any>({})
const trend = ref<any[]>([])
const days = ref(30)
const customRange = ref<[Date, Date] | null>(null)


const maxTokens = computed(() => Math.max(...trend.value.map(t => t.tokens || 0), 1))
const maxConv = computed(() => Math.max(...trend.value.map(t => t.conversations || 0), 1))

function barH(v: number, max: number) { return max === 0 ? 0 : Math.max((v / max) * 100, v > 0 ? 4 : 0) }
function formatK(n: number) { return n >= 10000 ? (n / 10000).toFixed(1) + 'w' : n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n) }
function formatNum(n: number) { return n?.toLocaleString?.() ?? n }

async function loadTrend() {
  const params: Record<string, any> = { days: days.value }
  if (days.value === 0 && customRange.value) {
    params.start_date = customRange.value[0].toISOString().split('T')[0]
    params.end_date = customRange.value[1].toISOString().split('T')[0]
  }
  const res: any = await request.get('/stats/trend', { params })
  trend.value = res || []
}


async function loadData() {
  loading.value = true
  try {
    const [s, t] = await Promise.allSettled([
      request.get('/stats/summary'),
      request.get('/stats/trend', { params: { days: days.value } }),
    ])
    if (s.status === 'fulfilled') summary.value = s.value
    if (t.status === 'fulfilled') trend.value = t.value as any
  } finally { loading.value = false }
}

async function loadUserAnalytics() {
  userAnalyticsLoading.value = true
  try {
    const res: any = await request.get('/users/analytics', { params: { page: 1, page_size: 20 } })
    userAnalytics.value = res?.items || []
  } catch { /* ignore — endpoint may not exist on older servers */ }
  finally { userAnalyticsLoading.value = false }
}

function exportCSV() {
  if (!trend.value.length) return
  const header = 'Date,Tokens,Conversations\n'
  const rows = trend.value.map(t => `${t.date},${t.tokens || 0},${t.conversations || 0}`).join('\n')
  const blob = new Blob(['\ufeff' + header + rows], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `usage_${days.value}d_${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  loadData()
  loadUserAnalytics()
})
</script>

<style scoped>
.analytics { max-width: 1400px; }

.page-subtitle { font-size: 14px; color: var(--text-tertiary); margin-top: 4px; }

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.summary-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px;
  background: #FFFFFF;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
  transition: all 0.25s;
}

.summary-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.summary-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.summary-card.purple .summary-icon { background: var(--brand-primary-light); color: var(--brand-primary); }
.summary-card.blue .summary-icon { background: #DBEAFE; color: #3B82F6; }
.summary-card.teal .summary-icon { background: #D1FAE5; color: #10B981; }

.summary-label { font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 4px; }
.summary-value { font-size: 28px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; }

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.chart-area { height: 240px; display: flex; align-items: flex-end; }

.bar-chart {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  width: 100%;
  height: 100%;
  padding-bottom: 28px;
}

.bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
  position: relative;
  animation: barFadeIn 0.4s ease-out both;
}

@keyframes barFadeIn {
  from { opacity: 0; transform: scaleY(0.5); }
  to { opacity: 1; transform: scaleY(1); }
}

.bar-tooltip {
  font-size: 10px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.bar-col:hover .bar-tooltip { opacity: 1; }

.bar {
  width: 100%;
  max-width: 20px;
  border-radius: 4px 4px 0 0;
  min-height: 2px;
  transition: height 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
}

.bar:hover { opacity: 0.85; }

.bar-purple { background: linear-gradient(180deg, #2B5AED 0%, #5B8DEF 100%); }
.bar-teal { background: linear-gradient(180deg, #10B981 0%, #6EE7B7 100%); }
.bar-label { font-size: 9px; color: var(--text-tertiary); margin-top: 6px; white-space: nowrap; }

@media (max-width: 768px) {
  .summary-grid { grid-template-columns: 1fr; }
}

</style>
