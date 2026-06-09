<template>
  <div class="dashboard">
    <div class="page-header">
      <div>
        <h2>仪表板</h2>
        <p class="page-subtitle">平台运行状态总览</p>
      </div>
      <el-button @click="loadData" :loading="loading" round>
        <el-icon><Refresh /></el-icon>刷新数据
      </el-button>
    </div>

    <div class="stat-grid">
      <div v-for="item in statCards" :key="item.label" class="stat-card" :class="[item.theme, { clickable: item.link }]" @click="item.link && $router.push(item.link)">
        <div class="stat-card-inner">
          <div class="stat-info">
            <span class="stat-label">{{ item.label }}</span>
            <span class="stat-value">{{ formatNum(item.value) }}</span>
          </div>
          <div class="stat-icon-wrap">
            <el-icon :size="22"><component :is="item.icon" /></el-icon>
          </div>
        </div>
        <div v-if="item.sub" class="stat-sub">{{ item.sub }}</div>
      </div>
    </div>

    <div class="chart-grid">
      <el-card class="chart-card span-2">
        <template #header>
          <div class="chart-header">
            <div>
              <span class="chart-title">Token 消耗趋势</span>
              <span class="chart-period">近 30 天</span>
            </div>
            <span class="chart-total">总计 {{ formatNum(totalTokens) }}</span>
          </div>
        </template>
        <v-chart :option="tokenChartOpt" :autoresize="true" class="echart" />
      </el-card>

      <el-card class="chart-card">
        <template #header>
          <div class="chart-header">
            <div>
              <span class="chart-title">对话量趋势</span>
              <span class="chart-period">近 30 天</span>
            </div>
            <span class="chart-total">总计 {{ formatNum(totalConv) }}</span>
          </div>
        </template>
        <v-chart :option="convChartOpt" :autoresize="true" class="echart" />
      </el-card>

      <el-card class="chart-card">
        <template #header>
          <div class="chart-header">
            <span class="chart-title">用户构成</span>
          </div>
        </template>
        <v-chart :option="userPieOpt" :autoresize="true" class="echart" />
      </el-card>

      <el-card class="chart-card">
        <template #header>
          <div class="chart-header">
            <span class="chart-title">模型用量分布</span>
          </div>
        </template>
        <v-chart v-if="modelPieData.length" :option="modelPieOpt" :autoresize="true" class="echart" />
        <el-empty v-else description="暂无模型用量数据" :image-size="40" />
      </el-card>

      <el-card class="chart-card">
        <template #header>
          <div class="chart-header">
            <span class="chart-title">平台数据统计</span>
          </div>
        </template>
        <div v-if="sysStats.total_conversations" class="kb-stats-grid">
          <div class="kb-stat"><span class="kb-stat-value">{{ formatNum(sysStats.total_conversations || 0) }}</span><span class="kb-stat-label">总对话数</span></div>
          <div class="kb-stat"><span class="kb-stat-value">{{ formatNum(sysStats.total_messages || 0) }}</span><span class="kb-stat-label">总消息数</span></div>
          <div class="kb-stat"><span class="kb-stat-value">{{ formatNum(sysStats.total_tokens || 0) }}</span><span class="kb-stat-label">总 Token</span></div>
        </div>
        <el-empty v-else description="暂无数据" :image-size="40" />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart, { THEME_KEY } from 'vue-echarts'
import request from '../utils/request'

use([CanvasRenderer, LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent])
provide(THEME_KEY, 'light')

const loading = ref(false)
const stats = ref<any>({})
const trend = ref<any[]>([])
const modelPieData = ref<any[]>([])
const sysStats = ref<any>({})

const statCards = computed(() => [
  { label: '总用户', value: stats.value.total_users || 0, icon: 'User', theme: 'theme-blue', link: '/users' },
  { label: '今日活跃', value: stats.value.active_users_today || 0, icon: 'UserFilled', theme: 'theme-teal', link: '/users' },
  { label: '组织数', value: stats.value.total_organizations || 0, icon: 'OfficeBuilding', theme: 'theme-amber', link: '/organizations' },
  { label: '在线设备', value: stats.value.online_devices || 0, icon: 'Monitor', theme: 'theme-teal', sub: `共 ${stats.value.total_devices || 0} 台设备`, link: '/devices' },
  { label: '上架技能', value: stats.value.total_skills || 0, icon: 'MagicStick', theme: 'theme-blue', link: '/skills' },
  { label: '待审核', value: stats.value.pending_skills || 0, icon: 'Bell', theme: 'theme-red', link: '/skills' },
  { label: '今日 Token', value: stats.value.total_tokens_today || 0, icon: 'Coin', theme: 'theme-amber', link: '/analytics' },
  { label: '累计 Token', value: stats.value.total_tokens_total || 0, icon: 'ChatDotRound', theme: 'theme-slate', link: '/analytics' },
])

const totalTokens = computed(() => trend.value.reduce((s, t) => s + (t.tokens || 0), 0))
const totalConv = computed(() => trend.value.reduce((s, t) => s + (t.conversations || 0), 0))

const dates = computed(() => trend.value.map(t => t.date?.slice(5) || ''))
const tokenData = computed(() => trend.value.map(t => t.tokens || 0))
const convData = computed(() => trend.value.map(t => t.conversations || 0))

const commonGrid = { left: 48, right: 20, top: 20, bottom: 28 }
const commonTooltip = { trigger: 'axis' as const, backgroundColor: '#fff', borderColor: '#E5E7EB', textStyle: { fontSize: 12, color: '#4B5563' } }

const tokenChartOpt = computed(() => ({
  grid: { ...commonGrid, right: 24 },
  tooltip: commonTooltip,
  xAxis: { type: 'category', data: dates.value, axisTick: { show: false }, axisLine: { lineStyle: { color: '#E5E7EB' } }, axisLabel: { fontSize: 10, color: '#9CA3AF' } },
  yAxis: { type: 'value', splitLine: { lineStyle: { color: '#F3F4F6', type: 'dashed' } }, axisLabel: { fontSize: 10, color: '#9CA3AF', formatter: (v: number) => v >= 10000 ? (v / 10000).toFixed(0) + 'w' : v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v } },
  series: [{
    type: 'line',
    data: tokenData.value,
    smooth: true,
    symbol: 'circle',
    symbolSize: 4,
    showSymbol: false,
    lineStyle: { width: 2.5, color: '#0066FF' },
    itemStyle: { color: '#0066FF' },
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(0,102,255,0.15)' }, { offset: 1, color: 'rgba(0,102,255,0.01)' }] } },
  }],
}))

const convChartOpt = computed(() => ({
  grid: commonGrid,
  tooltip: commonTooltip,
  xAxis: { type: 'category', data: dates.value, axisTick: { show: false }, axisLine: { lineStyle: { color: '#E5E7EB' } }, axisLabel: { fontSize: 10, color: '#9CA3AF' } },
  yAxis: { type: 'value', splitLine: { lineStyle: { color: '#F3F4F6', type: 'dashed' } }, axisLabel: { fontSize: 10, color: '#9CA3AF' } },
  series: [{
    type: 'bar',
    data: convData.value,
    barWidth: '60%',
    itemStyle: { color: '#00B578', borderRadius: [3, 3, 0, 0] },
  }],
}))

const userPieOpt = computed(() => {
  const active = stats.value.active_users_today || 0
  const total = stats.value.total_users || 0
  const inactive = Math.max(total - active, 0)
  return {
    tooltip: { trigger: 'item' as const, backgroundColor: '#fff', borderColor: '#E5E7EB', textStyle: { fontSize: 12, color: '#4B5563' } },
    legend: { bottom: 0, textStyle: { fontSize: 12, color: '#9CA3AF' } },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: [
        { value: active, name: '今日活跃', itemStyle: { color: '#0066FF' } },
        { value: inactive, name: '未活跃', itemStyle: { color: '#E5E7EB' } },
      ],
    }],
  }
})

const COLORS = ['#0066FF', '#00B578', '#FF8800', '#E5484D', '#8B5CF6', '#06B6D4', '#F59E0B', '#EC4899']

const modelPieOpt = computed(() => ({
  tooltip: { trigger: 'item' as const, backgroundColor: '#fff', borderColor: '#E5E7EB', textStyle: { fontSize: 12, color: '#4B5563' } },
  legend: { bottom: 0, textStyle: { fontSize: 11, color: '#9CA3AF' } },
  series: [{
    type: 'pie',
    radius: ['40%', '65%'],
    center: ['50%', '42%'],
    avoidLabelOverlap: true,
    label: { show: false },
    emphasis: { label: { show: true, fontSize: 13, fontWeight: 'bold' } },
    data: modelPieData.value.map((m, i) => ({
      value: m.tokens_used_today || 0,
      name: m.display_name,
      itemStyle: { color: COLORS[i % COLORS.length] },
    })),
  }],
}))

function formatNum(n: number) { return n?.toLocaleString?.() ?? n }

async function loadData() {
  loading.value = true
  try {
    const [s, t, sys, mdl] = await Promise.allSettled([
      request.get('/admin/dashboard'),
      request.get('/stats/trend', { params: { days: 30 } }),
      request.get('/system/admin-stats', { _silentError: true } as any),
      request.get('/models', { params: { page_size: 50 }, _silentError: true } as any),
    ])
    if (s.status === 'fulfilled') stats.value = s.value
    if (t.status === 'fulfilled') trend.value = t.value as any
    if (sys.status === 'fulfilled') {
      sysStats.value = sys.value as any
      const sysData = sys.value as any
      if (sysData.total_conversations) stats.value.total_conversations = sysData.total_conversations
      if (sysData.total_messages) stats.value.total_messages = sysData.total_messages
    }
    if (mdl.status === 'fulfilled') {
      const items = (mdl.value as any)?.items || []
      modelPieData.value = items.filter((m: any) => m.tokens_used_today > 0)
    }
  } finally {
    loading.value = false
  }
}

let _autoRefresh: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  loadData()
  _autoRefresh = setInterval(loadData, 60000) // Auto-refresh every 60 seconds
})
onUnmounted(() => {
  if (_autoRefresh) clearInterval(_autoRefresh)
})
</script>

<style scoped>
.dashboard { max-width: 1400px; }

.page-subtitle {
  font-size: 14px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 20px;
}

.stat-card {
  background: #FFFFFF;
  border-radius: 10px;
  padding: 18px 20px;
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
  transition: all 0.25s;
  position: relative;
  overflow: hidden;
}

.stat-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  border-radius: 10px 10px 0 0;
}

.stat-card.theme-blue::before { background: linear-gradient(90deg, #0066FF, #338AFF); }
.stat-card.theme-teal::before { background: linear-gradient(90deg, #00B578, #5EDCA5); }
.stat-card.theme-amber::before { background: linear-gradient(90deg, #FF8800, #FFB24D); }
.stat-card.theme-red::before { background: linear-gradient(90deg, #E5484D, #F08B8B); }
.stat-card.theme-slate::before { background: linear-gradient(90deg, #4B5563, #9CA3AF); }

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
.stat-card.clickable { cursor: pointer; }

.stat-card-inner {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.stat-info { display: flex; flex-direction: column; }

.stat-label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
  margin-bottom: 6px;
}

.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.stat-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.theme-blue .stat-icon-wrap { background: var(--brand-primary-bg); color: var(--brand-primary); }
.theme-teal .stat-icon-wrap { background: var(--color-success-light); color: var(--color-success); }
.theme-amber .stat-icon-wrap { background: var(--color-warning-light); color: var(--color-warning); }
.theme-red .stat-icon-wrap { background: var(--color-danger-light); color: var(--color-danger); }
.theme-slate .stat-icon-wrap { background: #F3F4F6; color: #4B5563; }

.stat-sub {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.chart-card.span-2 { grid-column: span 2; }

.chart-card :deep(.el-card__header) {
  padding: 14px 20px !important;
}

.chart-card :deep(.el-card__body) {
  padding: 12px 16px !important;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.chart-period {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-left: 8px;
}

.chart-total {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.echart { width: 100%; height: 260px; }

.kb-stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 20px 0; }
.kb-stat { text-align: center; }
.kb-stat-value { display: block; font-size: 24px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; }
.kb-stat-label { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; }

@media (max-width: 1200px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .chart-grid { grid-template-columns: 1fr; }
  .chart-card.span-2 { grid-column: span 1; }
}
</style>
