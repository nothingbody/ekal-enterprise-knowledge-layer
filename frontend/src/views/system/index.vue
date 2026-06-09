<template>
  <div class="system-page">
    <div class="page-header">
      <h2>系统管理</h2>
      <el-button @click="loadData" :loading="loading">
        <RefreshCwIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />刷新
      </el-button>
    </div>

    <!-- System Health -->
    <el-card class="health-card" style="margin-bottom: 16px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>系统健康状态</span>
          <el-button link size="small" @click="loadHealth" :loading="healthLoading">
            <RefreshCwIcon :size="13" :stroke-width="1.5" style="margin-right: 2px" />刷新
          </el-button>
        </div>
      </template>
      <div v-loading="healthLoading" class="health-grid">
        <div v-for="(item, key) in healthItems" :key="key" class="health-item">
          <div class="health-dot" :class="item.status"></div>
          <div class="health-info">
            <div class="health-name">{{ item.label }}</div>
            <div class="health-detail">{{ item.detail }}</div>
          </div>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16" class="stats-row" v-loading="loading">
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="知识库数量" :value="stats.knowledge_base_count">
            <template #prefix><el-icon color="#409eff"><FolderOpened /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="文档数量" :value="stats.document_count">
            <template #prefix><el-icon color="#67c23a"><Document /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="数据库源" :value="stats.database_source_count || 0">
            <template #prefix><el-icon color="#e6a23c"><Coin /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="对话数量" :value="stats.conversation_count">
            <template #prefix><el-icon color="#e6a23c"><ChatDotRound /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="stats-row" style="margin-top: 16px;" v-loading="loading">
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="消息数量" :value="stats.message_count">
            <template #prefix><el-icon color="#f56c6c"><ChatLineSquare /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="stats-row" style="margin-top: 16px;" v-loading="loading">
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="Token 总用量" :value="stats.total_tokens">
            <template #prefix><el-icon color="#909399"><Coin /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="点赞数" :value="stats.like_count">
            <template #prefix><el-icon color="#67c23a"><Top /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="点踩数" :value="stats.dislike_count">
            <template #prefix><el-icon color="#f56c6c"><Bottom /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="好评率" :value="feedbackRate" suffix="%">
            <template #prefix><el-icon color="#e6a23c"><Star /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 20px;">
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>近 7 天消息量</template>
          <div class="chart-container">
            <div class="bar-chart">
              <div v-for="item in trend" :key="item.date" class="bar-col">
                <div class="bar-value">{{ item.messages }}</div>
                <div class="bar" :style="{ height: barHeight(item.messages, maxMessages) + '%' }"></div>
                <div class="bar-label">{{ item.date.slice(5) }}</div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>近 7 天 Token 用量</template>
          <div class="chart-container">
            <div class="bar-chart">
              <div v-for="item in trend" :key="item.date" class="bar-col">
                <div class="bar-value">{{ formatNum(item.tokens) }}</div>
                <div class="bar bar-tokens" :style="{ height: barHeight(item.tokens, maxTokens) + '%' }"></div>
                <div class="bar-label">{{ item.date.slice(5) }}</div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top: 20px">
      <template #header>系统配置</template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="默认切片大小">{{ config.default_chunk_size }} 字符</el-descriptions-item>
        <el-descriptions-item label="默认切片重叠">{{ config.default_chunk_overlap }} 字符</el-descriptions-item>
        <el-descriptions-item label="默认检索 Top-K">{{ config.default_top_k }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card style="margin-top: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>操作日志</span>
          <div style="display: flex; gap: 8px; align-items: center;">
            <el-select v-model="logActionFilter" placeholder="操作类型" clearable size="small" style="width: 140px" @change="onLogFilterChange">
              <el-option v-for="a in logFilterOptions.actions" :key="a" :label="a" :value="a" />
            </el-select>
            <el-select v-model="logResourceFilter" placeholder="资源类型" clearable size="small" style="width: 140px" @change="onLogFilterChange">
              <el-option v-for="r in logFilterOptions.resource_types" :key="r" :label="r" :value="r" />
            </el-select>
            <el-button v-if="isAdmin" size="small" type="danger" plain @click="handleCleanupLogs">
              <Trash2Icon :size="13" :stroke-width="1.5" style="margin-right: 4px" />清理旧日志
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="logs" stripe v-loading="logsLoading" size="small">
        <el-table-column prop="action" label="操作" width="120">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" size="small" effect="plain">{{ actionLabel(row.action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" label="资源类型" width="100">
          <template #default="{ row }">
            <span class="log-resource-type">{{ resourceLabel(row.resource_type) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="resource_id" label="资源ID" width="80" />
        <el-table-column label="详情" min-width="260">
          <template #default="{ row }">
            <div class="log-detail-cell" @click="showLogDetail(row)">
              <template v-if="parsedRowDetail(row)">
                <div class="log-detail-summary">
                  <el-tag v-if="parsedRowDetail(row)?.mode" size="small" :type="modeTagType(parsedRowDetail(row)?.mode ?? '')" style="margin-right: 6px;">{{ modeLabel(parsedRowDetail(row)?.mode ?? '') }}</el-tag>
                  <span v-if="parsedRowDetail(row)?.retrieval_count != null" class="log-kv">召回 <b>{{ parsedRowDetail(row)?.retrieval_count }}</b> 条</span>
                  <span v-if="parsedRowDetail(row)?.top_score != null" class="log-kv">最高分 <b>{{ ((parsedRowDetail(row)?.top_score ?? 0) * 100).toFixed(1) }}%</b></span>
                  <span v-if="parsedRowDetail(row)?.agent_count != null" class="log-kv">{{ parsedRowDetail(row)?.agent_count }} 个 Agent</span>
                  <span v-if="parsedRowDetail(row)?.sources?.length" class="log-kv log-sources">来源: {{ (parsedRowDetail(row)?.sources ?? []).join(', ') }}</span>
                </div>
              </template>
              <span v-else class="log-detail-text">{{ row.detail || '-' }}</span>
              <el-icon v-if="row.detail" class="log-detail-expand"><View /></el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="total_tokens" label="Token" width="90">
          <template #default="{ row }">
            <span v-if="row.total_tokens" class="log-token">{{ formatNum(row.total_tokens) }}</span>
            <span v-else class="log-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="延迟" width="90">
          <template #default="{ row }">
            <span v-if="row.latency_ms" :class="['log-latency', row.latency_ms > 10000 ? 'slow' : '']">{{ row.latency_ms >= 1000 ? (row.latency_ms / 1000).toFixed(1) + 's' : row.latency_ms.toFixed(0) + 'ms' }}</span>
            <span v-else class="log-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
      </el-table>

      <!-- Log Detail Dialog -->
      <el-dialog v-model="logDetailVisible" title="操作日志详情" width="560px" destroy-on-close>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="操作">
            <el-tag :type="actionTagType(logDetailRow.action)" size="small" effect="plain">{{ actionLabel(logDetailRow.action) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="资源类型">{{ resourceLabel(logDetailRow.resource_type) }}</el-descriptions-item>
          <el-descriptions-item label="资源ID">{{ logDetailRow.resource_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="Token">{{ logDetailRow.total_tokens || '-' }}</el-descriptions-item>
          <el-descriptions-item label="延迟">{{ logDetailRow.latency_ms ? (logDetailRow.latency_ms >= 1000 ? (logDetailRow.latency_ms / 1000).toFixed(1) + 's' : logDetailRow.latency_ms.toFixed(0) + 'ms') : '-' }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ logDetailRow.created_at ? new Date(logDetailRow.created_at).toLocaleString() : '-' }}</el-descriptions-item>
        </el-descriptions>
        <div class="log-detail-block" v-if="logDetailRow.detail">
          <div class="log-detail-block-title">详情内容</div>
          <template v-if="parseDetail(logDetailRow.detail)">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item v-for="(val, key) in parseDetail(logDetailRow.detail)" :key="key" :label="detailKeyLabel(String(key))">
                <template v-if="Array.isArray(val)">
                  <el-tag v-for="(item, i) in val" :key="i" size="small" effect="plain" style="margin: 2px 4px 2px 0;">{{ item }}</el-tag>
                </template>
                <template v-else-if="typeof val === 'number'">
                  {{ key === 'top_score' || key === 'avg_score' ? (val * 100).toFixed(1) + '%' : val }}
                </template>
                <template v-else>{{ val ?? '-' }}</template>
              </el-descriptions-item>
            </el-descriptions>
          </template>
          <pre v-else class="log-detail-raw">{{ logDetailRow.detail }}</pre>
        </div>
      </el-dialog>
      <el-pagination
        v-if="logsTotal > logsPageSize"
        style="margin-top: 12px; justify-content: flex-end;"
        layout="total, prev, pager, next"
        :total="logsTotal"
        :page-size="logsPageSize"
        v-model:current-page="logsPage"
        @current-change="loadLogs"
      />
    </el-card>

    <!-- Server Logs (desktop mode) -->
    <el-card style="margin-top: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>服务器日志</span>
          <div style="display: flex; gap: 8px; align-items: center;">
            <el-input-number v-model="serverLogLines" :min="50" :max="5000" :step="100" size="small" style="width: 140px" />
            <el-button size="small" @click="loadServerLogs" :loading="serverLogLoading">
              <RefreshCwIcon :size="13" :stroke-width="1.5" style="margin-right: 4px" />加载
            </el-button>
          </div>
        </div>
      </template>
      <div v-if="serverLogFile" style="font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 8px;">
        日志文件：{{ serverLogFile }} ({{ serverLogContent.length }} 行)
      </div>
      <div v-if="serverLogError" style="color: var(--el-color-danger); font-size: 13px; margin-bottom: 8px;">
        {{ serverLogError }}
      </div>
      <div class="server-log-container" ref="serverLogContainer">
        <pre class="server-log-content">{{ serverLogContent.join('\n') || '点击"加载"查看服务器日志' }}</pre>
      </div>
    </el-card>

  </div>
</template>

<script setup lang="ts">
import { reactive, onActivated, ref, computed, nextTick } from 'vue'
import { RefreshCw as RefreshCwIcon, Trash2 as Trash2Icon } from 'lucide-vue-next'
import { View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getSystemStats, getSystemConfig, getOperationLogs, getUsageTrend, getLogFilters, cleanupLogs } from '../../api/system'
import request from '../../utils/request'
import { useUserStore } from '../../stores/user'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.userInfo?.role === 'admin')
const loading = ref(false)

// Health status
interface HealthItem { label: string; status: string; detail: string }
const healthLoading = ref(false)
const healthItems = ref<HealthItem[]>([])

async function loadHealth() {
  healthLoading.value = true
  try {
    const res: any = await request.get('/health')
    const items: HealthItem[] = []
    const labelMap: Record<string, string> = {
      database: '数据库',
      redis: 'Redis 缓存',
      chromadb: '向量数据库 (ChromaDB)',
    }
    for (const key of ['database', 'redis', 'chromadb']) {
      const val = res[key] || 'unknown'
      let status = 'ok'
      if (val === 'ok' || val === 'embedded') {
        status = 'ok'
      } else if (val.startsWith('unavailable')) {
        status = 'warn'
      } else {
        status = 'error'
      }
      items.push({ label: labelMap[key] || key, status, detail: val })
    }
    healthItems.value = items
  } catch {
    healthItems.value = [{ label: '健康检查', status: 'error', detail: '无法连接后端服务' }]
  } finally {
    healthLoading.value = false
  }
}

const logs = ref<any[]>([])
const logsLoading = ref(false)
const logsTotal = ref(0)
const logsPage = ref(1)
const logsPageSize = 20
const logActionFilter = ref('')
const logResourceFilter = ref('')
const logFilterOptions = reactive({ actions: [] as string[], resource_types: [] as string[] })

const stats = reactive({
  knowledge_base_count: 0,
  document_count: 0,
  database_source_count: 0,
  conversation_count: 0,
  message_count: 0,
  total_tokens: 0,
  like_count: 0,
  dislike_count: 0,
})

const feedbackRate = computed(() => {
  const total = stats.like_count + stats.dislike_count
  if (total === 0) return 0
  return Math.round((stats.like_count / total) * 100)
})

const config = reactive({
  default_chunk_size: 0,
  default_chunk_overlap: 0,
  default_top_k: 0,
})

const trend = ref<any[]>([])
const maxMessages = computed(() => Math.max(...trend.value.map((t: any) => t.messages), 1))
const maxTokens = computed(() => Math.max(...trend.value.map((t: any) => t.tokens), 1))

function barHeight(value: number, max: number) {
  if (max === 0) return 0
  return Math.max((value / max) * 100, value > 0 ? 4 : 0)
}

function formatNum(n: number) {
  if (n >= 10000) return (n / 1000).toFixed(1) + 'k'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return n
}

async function loadData() {
  loading.value = true
  try {
    const [sRes, cRes, tRes] = await Promise.allSettled([getSystemStats(), getSystemConfig(), getUsageTrend(7)])
    if (sRes.status === 'fulfilled') Object.assign(stats, sRes.value)
    if (cRes.status === 'fulfilled') Object.assign(config, cRes.value)
    if (tRes.status === 'fulfilled') trend.value = tRes.value as any
  } finally {
    loading.value = false
  }
  await loadLogs()
  try {
    const f: any = await getLogFilters()
    Object.assign(logFilterOptions, f)
  } catch {}
}

function onLogFilterChange() {
  logsPage.value = 1
  loadLogs()
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const res: any = await getOperationLogs(
      logsPage.value, logsPageSize,
      logActionFilter.value || undefined,
      logResourceFilter.value || undefined
    )
    logs.value = res.items || []
    logsTotal.value = res.total || 0
  } finally {
    logsLoading.value = false
  }
}

async function handleCleanupLogs() {
  try {
    const { value } = await ElMessageBox.prompt(
      '将删除指定天数之前的操作日志，此操作不可恢复。',
      '清理旧日志',
      {
        inputValue: '90',
        inputPattern: /^[1-9]\d*$/,
        inputErrorMessage: '请输入正整数（天数）',
        confirmButtonText: '清理',
        cancelButtonText: '取消',
        type: 'warning',
        inputPlaceholder: '保留天数（默认90天）',
      }
    )
    const days = parseInt(value, 10) || 90
    const res: any = await cleanupLogs(days)
    ElMessage.success(`已清理 ${res.deleted} 条日志（保留近 ${days} 天）`)
    await loadLogs()
  } catch { /* cancelled */ }
}

// ── Server Logs ──
const serverLogLines = ref(200)
const serverLogLoading = ref(false)
const serverLogContent = ref<string[]>([])
const serverLogFile = ref('')
const serverLogError = ref('')
const serverLogContainer = ref<HTMLElement>()

async function loadServerLogs() {
  serverLogLoading.value = true
  serverLogError.value = ''
  try {
    const res: any = await request.get('/system/server-logs', { params: { lines: serverLogLines.value } })
    const data = res.data || res
    serverLogContent.value = data.lines || []
    serverLogFile.value = data.file || ''
    if (data.message && !data.lines?.length) {
      serverLogError.value = data.message
    }
    await nextTick()
    if (serverLogContainer.value) {
      serverLogContainer.value.scrollTop = serverLogContainer.value.scrollHeight
    }
  } catch (e: any) {
    serverLogError.value = e.response?.data?.detail || '加载日志失败'
  } finally {
    serverLogLoading.value = false
  }
}

// ── Log detail helpers ──
const logDetailVisible = ref(false)
const logDetailRow = ref<any>({})

function showLogDetail(row: any) {
  logDetailRow.value = row
  logDetailVisible.value = true
}

function parseDetail(detail: string | null): Record<string, any> | null {
  if (!detail) return null
  try {
    const obj = JSON.parse(detail)
    return typeof obj === 'object' && !Array.isArray(obj) ? obj : null
  } catch {
    return null
  }
}

function parsedRowDetail(row: { detail?: string | null }): Record<string, any> | null {
  return parseDetail(row?.detail ?? null)
}

const actionMap: Record<string, string> = {
  chat: '对话',
  public_chat: '公开对话',
  create_kb: '创建知识库',
  delete_kb: '删除知识库',
  upload_doc: '上传文档',
  delete_doc: '删除文档',
  login: '登录',
  register: '注册',
}

function actionLabel(action: string) {
  return actionMap[action] || action
}

function actionTagType(action: string) {
  if (action === 'chat' || action === 'public_chat') return 'primary' as const
  if (action.startsWith('create') || action === 'register') return 'success' as const
  if (action.startsWith('delete')) return 'danger' as const
  return 'info' as const
}

const resourceMap: Record<string, string> = {
  conversation: '对话',
  knowledge_base: '知识库',
  document: '文档',
  published_app: '应用',
  user: '用户',
}

function resourceLabel(type: string) {
  return resourceMap[type] || type || '-'
}

function modeLabel(mode: string) {
  const m: Record<string, string> = { rag: '知识检索', sql: '数据库查询', hybrid: '混合模式', agent: '智能体', multi_agent: '多Agent' }
  return m[mode] || mode
}

function modeTagType(mode: string) {
  const m: Record<string, string> = { rag: 'info', sql: 'warning', hybrid: 'success', agent: 'danger', multi_agent: '' }
  return (m[mode] || '') as any
}

const detailKeyMap: Record<string, string> = {
  mode: '对话模式',
  retrieval_count: '召回数量',
  top_score: '最高分',
  avg_score: '平均分',
  sources: '来源文档',
  agent_count: 'Agent 数量',
  reference_count: '引用数量',
  published_app_id: '应用ID',
  visitor_id: '访客ID',
  conversation_id: '对话ID',
}

function detailKeyLabel(key: string) {
  return detailKeyMap[key] || key
}

onActivated(() => {
  loadData()
  loadHealth()
})
</script>

<style scoped>
.system-page {
  max-width: 1200px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.stats-row .stat-card {
  text-align: center;
  border-radius: var(--radius-lg) !important;
  padding: 8px 0;
  transition: all var(--duration-base) var(--ease-out);
}

.stats-row .stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg) !important;
}

.stats-row {
  margin-bottom: 0;
}

:deep(.el-card__header) {
  font-weight: 700;
  font-size: 15px;
  color: var(--text-primary);
  padding: 16px 20px;
}

:deep(.el-descriptions__label) {
  font-weight: 600;
  color: var(--text-secondary);
}

.chart-container {
  height: 200px;
  display: flex;
  align-items: flex-end;
}

.bar-chart {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  width: 100%;
  height: 100%;
  padding-bottom: 24px;
  position: relative;
}

.bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
}

.bar-value {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
  font-weight: 600;
}

.bar {
  width: 100%;
  max-width: 40px;
  background: linear-gradient(180deg, var(--primary) 0%, var(--primary-light) 100%);
  border-radius: 4px 4px 0 0;
  min-height: 2px;
  transition: height 0.6s var(--ease-out);
}

.bar-tokens {
  background: linear-gradient(180deg, var(--accent) 0%, var(--accent-light) 100%);
}

.bar-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 6px;
  white-space: nowrap;
}

/* Health status */
.health-grid {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.health-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 180px;
}

.health-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.health-dot.ok {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.4);
}

.health-dot.warn {
  background: #f59e0b;
  box-shadow: 0 0 6px rgba(245, 158, 11, 0.4);
}

.health-dot.error {
  background: #ef4444;
  box-shadow: 0 0 6px rgba(239, 68, 68, 0.4);
}

.health-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.health-detail {
  font-size: 11px;
  color: var(--text-muted);
}

/* ── Log Detail Styles ── */
.log-detail-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  border-radius: 4px;
  padding: 2px 4px;
  margin: -2px -4px;
  transition: background 0.15s;
}

.log-detail-cell:hover {
  background: var(--gray-50);
}

.log-detail-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.log-kv {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.log-kv b {
  color: var(--text-primary);
  font-weight: 600;
}

.log-sources {
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
  display: inline-block;
  vertical-align: middle;
}

.log-detail-text {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.log-detail-expand {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 14px;
  opacity: 0;
  transition: opacity 0.15s;
}

.log-detail-cell:hover .log-detail-expand {
  opacity: 1;
}

.log-resource-type {
  font-size: 12px;
  color: var(--text-secondary);
}

.log-token {
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.log-latency {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.log-latency.slow {
  color: var(--warning-color, #e6a23c);
  font-weight: 500;
}

.log-muted {
  color: var(--text-muted);
  font-size: 12px;
}

.log-detail-block {
  margin-top: 16px;
}

.log-detail-block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.log-detail-raw {
  background: var(--gray-50);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px 16px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  font-family: var(--font-mono, monospace);
  max-height: 300px;
  overflow-y: auto;
}

.server-log-container {
  max-height: 500px;
  overflow-y: auto;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
}

.server-log-content {
  font-family: 'JetBrains Mono', 'SF Mono', 'Cascadia Code', monospace;
  font-size: 12px;
  line-height: 1.6;
  padding: 16px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-text-color-regular);
}
</style>
