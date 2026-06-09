<template>
  <div class="health-section">
    <div class="section-header" @click="expanded = !expanded">
      <div class="section-title">
        <HeartPulseIcon :size="14" :stroke-width="1.5" />
        <span>知识健康</span>
        <el-tag v-if="latestScore !== null" size="small" :type="scoreType">{{ latestScore }} 分</el-tag>
      </div>
      <ChevronRightIcon :size="14" :stroke-width="1.5" class="expand-icon" :class="{ rotated: expanded }" />
    </div>

    <div v-show="expanded" class="section-body">
      <div class="section-toolbar">
        <div class="toolbar-left">
          <span v-if="latestReport" class="stat-text">
            上次检查: {{ formatTime(latestReport.completed_at) }}
            <span v-if="latestReport.token_cost"> | Token 消耗: {{ latestReport.token_cost }}</span>
          </span>
        </div>
        <div class="toolbar-right" v-if="canManage">
          <el-button size="small" type="primary" plain @click="handleRunCheck" :loading="checking">
            <SearchCheckIcon :size="13" :stroke-width="1.5" style="margin-right: 4px" />运行检查
          </el-button>
        </div>
      </div>

      <div v-loading="loading">
        <div v-if="!loading && reports.length === 0" class="empty-tip">
          暂无健康检查报告
          <el-button v-if="canManage" link type="primary" @click="handleRunCheck" style="margin-left: 4px">立即检查</el-button>
        </div>

        <!-- Latest report findings -->
        <template v-if="latestReport && latestReport.findings?.length">
          <div class="score-bar">
            <el-progress
              :percentage="latestScore ?? 0"
              :color="scoreColor"
              :stroke-width="10"
              :text-inside="false"
            />
          </div>

          <div class="findings-summary">
            <el-tag v-for="(count, type) in findingCounts" :key="type" size="small" :type="findingTagType(type)">
              {{ findingTypeLabel(type) }}: {{ count }}
            </el-tag>
          </div>

          <div v-for="(finding, idx) in latestReport.findings" :key="idx" class="finding-card" :class="finding.severity">
            <div class="finding-header">
              <el-tag size="small" :type="severityType(finding.severity)">{{ severityLabel(finding.severity) }}</el-tag>
              <el-tag size="small" type="info" effect="plain">{{ findingTypeLabel(finding.type) }}</el-tag>
              <span class="finding-desc">{{ finding.description }}</span>
            </div>
            <div v-if="finding.suggested_action" class="finding-action">
              <span class="action-label">建议:</span> {{ finding.suggested_action }}
            </div>
          </div>
        </template>

        <template v-else-if="latestReport && !latestReport.findings?.length">
          <div class="all-good">
            <CheckCircleIcon :size="32" :stroke-width="1.2" />
            <p>知识库健康状况良好，未发现问题。</p>
          </div>
        </template>

        <!-- History -->
        <div v-if="reports.length > 1" class="history-section">
          <div class="history-title" @click="showHistory = !showHistory">
            <span>历史报告 ({{ reports.length }})</span>
            <ChevronRightIcon :size="12" :stroke-width="1.5" class="expand-icon" :class="{ rotated: showHistory }" />
          </div>
          <div v-show="showHistory" class="history-list">
            <div v-for="report in reports.slice(1)" :key="report.id" class="history-item">
              <span>{{ formatTime(report.created_at) }}</span>
              <el-tag size="small" :type="report.status === 'completed' ? 'success' : 'danger'">
                {{ report.status === 'completed' ? '完成' : '失败' }}
              </el-tag>
              <span v-if="report.summary?.score !== undefined">{{ report.summary.score }} 分</span>
              <span v-if="report.summary?.total_findings">{{ report.summary.total_findings }} 个发现</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { HeartPulse as HeartPulseIcon, ChevronRight as ChevronRightIcon, SearchCheck as SearchCheckIcon, CheckCircle as CheckCircleIcon } from 'lucide-vue-next'
import { listHealthReports, triggerHealthCheck } from '../../api/knowledgeCompilation'

const props = defineProps<{
  kbId: number
  canManage: boolean
}>()

const expanded = ref(false)
const loading = ref(false)
const checking = ref(false)
const showHistory = ref(false)
const reports = ref<any[]>([])

const latestReport = computed(() => reports.value[0] || null)
const latestScore = computed(() => latestReport.value?.summary?.score ?? null)
const scoreType = computed(() => {
  const s = latestScore.value
  if (s === null) return 'info'
  if (s >= 80) return 'success'
  if (s >= 50) return 'warning'
  return 'danger'
})
const scoreColor = computed(() => {
  const s = latestScore.value ?? 0
  if (s >= 80) return '#67c23a'
  if (s >= 50) return '#e6a23c'
  return '#f56c6c'
})

const findingCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const f of latestReport.value?.findings || []) {
    counts[f.type] = (counts[f.type] || 0) + 1
  }
  return counts
})

function findingTypeLabel(t: string) {
  const map: Record<string, string> = { contradiction: '矛盾', outdated: '过时', gap: '缺口', redundancy: '冗余', quality: '质量' }
  return map[t] || t
}
function findingTagType(t: string) {
  const map: Record<string, string> = { contradiction: 'danger', outdated: 'warning', gap: 'info', redundancy: '', quality: 'info' }
  return map[t] || 'info'
}
function severityType(s: string) {
  const map: Record<string, string> = { high: 'danger', medium: 'warning', low: 'info' }
  return map[s] || 'info'
}
function severityLabel(s: string) {
  const map: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return map[s] || s
}
function formatTime(t: string | null) {
  if (!t) return '-'
  return new Date(t).toLocaleString()
}

async function handleRunCheck() {
  await ElMessageBox.confirm('运行健康检查将消耗一定 Token，确定继续？', '健康检查', { type: 'info' })
  checking.value = true
  try {
    await triggerHealthCheck(props.kbId)
    ElMessage.success('健康检查任务已提交，请稍后刷新查看')
  } catch { ElMessage.error('提交失败') } finally { checking.value = false }
}

async function loadData() {
  loading.value = true
  try {
    const res = await listHealthReports(props.kbId, { limit: 10 })
    reports.value = res.data || []
  } catch { /* ignore */ } finally { loading.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.health-section { margin-bottom: 20px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; cursor: pointer; border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px; background: var(--el-fill-color-blank);
  transition: background 0.2s;
}
.section-header:hover { background: var(--el-fill-color-light); }
.section-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 500; }
.expand-icon { transition: transform 0.2s; }
.expand-icon.rotated { transform: rotate(90deg); }
.section-body { padding: 12px 0; }
.section-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.stat-text { font-size: 12px; color: var(--el-text-color-secondary); }
.empty-tip { text-align: center; color: var(--el-text-color-secondary); padding: 24px 0; font-size: 13px; }

.score-bar { margin-bottom: 16px; }
.findings-summary { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }

.finding-card {
  border: 1px solid var(--el-border-color-lighter); border-radius: 6px;
  padding: 10px 14px; margin-bottom: 8px;
}
.finding-card.high { border-left: 3px solid var(--el-color-danger); }
.finding-card.medium { border-left: 3px solid var(--el-color-warning); }
.finding-card.low { border-left: 3px solid var(--el-color-info); }
.finding-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.finding-desc { font-size: 13px; }
.finding-action { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.action-label { font-weight: 500; }

.all-good { text-align: center; padding: 32px 0; color: var(--el-color-success); }
.all-good p { margin-top: 8px; font-size: 14px; }

.history-section { margin-top: 16px; }
.history-title {
  display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;
  color: var(--el-text-color-secondary);
}
.history-list { margin-top: 8px; }
.history-item {
  display: flex; align-items: center; gap: 12px;
  padding: 6px 0; font-size: 12px; color: var(--el-text-color-secondary);
  border-bottom: 1px dashed var(--el-border-color-extra-light);
}
</style>
