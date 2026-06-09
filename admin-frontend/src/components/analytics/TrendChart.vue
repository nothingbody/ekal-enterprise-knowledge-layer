<template>
  <div class="trend-chart">
    <div class="chart-header">
      <h3 class="chart-title">{{ title }}</h3>
      <el-radio-group v-model="selectedMetric" size="small" @change="onMetricChange">
        <el-radio-button value="conversations">对话数</el-radio-button>
        <el-radio-button value="messages">消息数</el-radio-button>
        <el-radio-button value="users">活跃用户</el-radio-button>
      </el-radio-group>
    </div>
    <div ref="chartRef" class="chart-container" v-loading="loading"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { TrendPoint } from '../../api/analytics'

const props = withDefaults(defineProps<{
  title?: string
  data: TrendPoint[]
  loading?: boolean
}>(), {
  title: '趋势分析',
  loading: false,
})

const emit = defineEmits<{
  (e: 'metric-change', metric: string): void
}>()

const chartRef = ref<HTMLElement>()
const selectedMetric = ref('conversations')
let chart: echarts.ECharts | null = null

const metricLabels: Record<string, string> = {
  conversations: '对话数',
  messages: '消息数',
  users: '活跃用户',
}

function initChart() {
  if (!chartRef.value) return
  
  chart = echarts.init(chartRef.value)
  updateChart()
  
  window.addEventListener('resize', handleResize)
}

function updateChart() {
  if (!chart) return
  
  const dates = props.data.map(d => d.date)
  const values = props.data.map(d => d.value)
  
  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const point = params[0]
        return `${point.axisValue}<br/>${metricLabels[selectedMetric.value]}: <strong>${point.value}</strong>`
      },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '10%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#E4E7ED' } },
      axisLabel: { color: '#909399', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#E4E7ED', type: 'dashed' } },
      axisLabel: { color: '#909399', fontSize: 11 },
    },
    series: [
      {
        name: metricLabels[selectedMetric.value],
        type: 'line',
        data: values,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        showSymbol: false,
        lineStyle: { width: 2, color: '#409EFF' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
            { offset: 1, color: 'rgba(64, 158, 255, 0.05)' },
          ]),
        },
        itemStyle: { color: '#409EFF' },
      },
    ],
  }
  
  chart.setOption(option)
}

function handleResize() {
  chart?.resize()
}

function onMetricChange(metric: string) {
  emit('metric-change', metric)
}

watch(() => props.data, () => {
  updateChart()
}, { deep: true })

onMounted(() => {
  initChart()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
})
</script>

<style scoped>
.trend-chart {
  background: var(--el-bg-color);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  padding: 20px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.chart-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin: 0;
}

.chart-container {
  height: 300px;
}
</style>
