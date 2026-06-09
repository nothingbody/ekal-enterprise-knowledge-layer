<template>
  <div>
    <div class="page-header">
      <div>
        <h2>服务器日志</h2>
        <p class="page-subtitle">实时查看应用运行日志</p>
      </div>
      <div class="header-actions">
        <el-select v-model="levelFilter" placeholder="全部级别" clearable style="width: 120px" @change="loadLogs">
          <el-option label="DEBUG" value="DEBUG" />
          <el-option label="INFO" value="INFO" />
          <el-option label="WARNING" value="WARNING" />
          <el-option label="ERROR" value="ERROR" />
        </el-select>
        <el-input v-model="searchText" placeholder="搜索日志..." clearable style="width: 180px"
          @keydown.enter="applySearch" @clear="applySearch">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="logLimit" style="width: 100px" @change="loadLogs">
          <el-option :value="100" label="100 条" />
          <el-option :value="200" label="200 条" />
          <el-option :value="500" label="500 条" />
        </el-select>
        <el-button @click="loadLogs" :loading="loading" round>
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
        <el-switch v-model="autoRefresh" active-text="自动" @change="toggleAutoRefresh" />
        <el-button v-if="autoRefresh" size="small" circle @click="scrollToBottom">
          <el-icon><Bottom /></el-icon>
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <!-- Stats bar -->
      <div class="stats-bar" v-if="logs.length">
        <span class="stats-item">共 <strong>{{ filteredLogs.length }}</strong> 条</span>
        <span class="stats-item" v-if="errorCount > 0">
          <span class="stats-dot error"></span> ERROR: <strong>{{ errorCount }}</strong>
        </span>
        <span class="stats-item" v-if="warnCount > 0">
          <span class="stats-dot warn"></span> WARNING: <strong>{{ warnCount }}</strong>
        </span>
      </div>

      <div v-loading="loading" ref="logContainerRef" class="log-container">
        <div v-if="filteredLogs.length === 0 && !loading" class="log-empty">
          <el-empty :image-size="80" :description="searchText ? '无匹配日志' : '暂无日志记录'">
            <el-button v-if="searchText" size="small" @click="searchText = ''; applySearch()">清除搜索</el-button>
          </el-empty>
        </div>
        <div
          v-for="(log, idx) in filteredLogs" :key="idx"
          class="log-entry"
          :class="['level-' + log.level?.toLowerCase(), { expanded: expandedRows.has(idx) }]"
          @click="toggleExpand(idx, log)"
        >
          <div class="log-main">
            <span class="log-time">{{ formatTime(log.ts) }}</span>
            <span class="log-level" :class="'badge-' + log.level?.toLowerCase()">{{ log.level }}</span>
            <span class="log-logger">{{ shortenLogger(log.logger) }}</span>
            <span class="log-msg" :class="{ 'has-exception': log.exception }">{{ log.msg }}</span>
          </div>
          <transition name="expand">
            <div v-if="expandedRows.has(idx)" class="log-detail">
              <div class="log-detail-row"><span class="log-detail-label">完整时间</span>{{ log.ts }}</div>
              <div class="log-detail-row"><span class="log-detail-label">Logger</span>{{ log.logger }}</div>
              <div class="log-detail-row"><span class="log-detail-label">消息</span><pre class="log-detail-msg">{{ log.msg }}</pre></div>
              <div v-if="log.exception" class="log-detail-row">
                <span class="log-detail-label">异常</span>
                <pre class="log-exception">{{ log.exception }}</pre>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import request from '../utils/request'

const logs = ref<any[]>([])
const loading = ref(false)
const levelFilter = ref('')
const searchText = ref('')
const logLimit = ref(200)
const autoRefresh = ref(false)
const expandedRows = ref<Set<number>>(new Set())
const logContainerRef = ref<HTMLElement>()
let refreshTimer: ReturnType<typeof setInterval> | null = null

const filteredLogs = computed(() => {
  if (!searchText.value) return logs.value
  const q = searchText.value.toLowerCase()
  return logs.value.filter(l =>
    l.msg?.toLowerCase().includes(q) ||
    l.logger?.toLowerCase().includes(q) ||
    l.exception?.toLowerCase().includes(q)
  )
})

const errorCount = computed(() => logs.value.filter(l => l.level === 'ERROR').length)
const warnCount = computed(() => logs.value.filter(l => l.level === 'WARNING').length)

function formatTime(ts: string) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return ts }
}

function shortenLogger(name: string) {
  if (!name) return ''
  // "uvicorn.access" -> "uvicorn.access", "app.api.admin" -> "api.admin"
  if (name.startsWith('app.')) return name.slice(4)
  return name
}

function toggleExpand(idx: number, log: any) {
  if (expandedRows.value.has(idx)) {
    expandedRows.value.delete(idx)
  } else {
    // Only expand if there's extra info worth showing
    if (log.exception || log.msg?.length > 100) {
      expandedRows.value.add(idx)
    }
  }
}

function applySearch() {
  expandedRows.value.clear()
}

function scrollToBottom() {
  nextTick(() => {
    if (logContainerRef.value) {
      logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
    }
  })
}

async function loadLogs() {
  loading.value = true
  try {
    const params: Record<string, any> = { limit: logLimit.value }
    if (levelFilter.value) params.level = levelFilter.value
    const res: any = await request.get('/admin/server-logs', { params })
    logs.value = (res?.items || []).reverse()
    if (autoRefresh.value) scrollToBottom()
  } catch { /* interceptor */ }
  finally { loading.value = false }
}

function toggleAutoRefresh(val: boolean) {
  if (val) {
    refreshTimer = setInterval(loadLogs, 5000)
  } else if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(loadLogs)
onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer) })
</script>

<style scoped>
.page-subtitle { font-size: 14px; color: var(--text-tertiary); margin-top: 4px; }

.header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.stats-bar {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-light, #F2F3F5);
  background: #FAFBFC;
  font-size: 12px;
  color: var(--text-secondary);
}

.stats-item { display: flex; align-items: center; gap: 4px; }
.stats-item strong { color: var(--text-primary); font-variant-numeric: tabular-nums; }
.stats-dot { width: 6px; height: 6px; border-radius: 50%; }
.stats-dot.error { background: #DC2626; }
.stats-dot.warn { background: #D97706; }

.log-container {
  max-height: calc(100vh - 260px);
  min-height: 400px;
  overflow-y: auto;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.log-empty { padding: 60px 0; }

.log-entry {
  border-bottom: 1px solid var(--border-light, #F2F3F5);
  cursor: default;
  transition: background 0.15s;
}

.log-entry:hover { background: #F9FAFB; }
.log-entry.level-error { background: #FFF5F5; }
.log-entry.level-error:hover { background: #FEF2F2; }
.log-entry.level-warning { background: #FFFBEB; }
.log-entry.level-warning:hover { background: #FEF9C3; }

.log-main {
  display: flex;
  gap: 8px;
  padding: 6px 12px;
  align-items: baseline;
}

.log-time { color: var(--text-tertiary, #86909C); min-width: 70px; flex-shrink: 0; }

.log-level {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  min-width: 52px;
  text-align: center;
  flex-shrink: 0;
}

.badge-info { background: #E8EFFD; color: #2B5AED; }
.badge-warning { background: #FEF3C7; color: #D97706; }
.badge-error { background: #FEE2E2; color: #DC2626; }
.badge-debug { background: #F2F3F5; color: #86909C; }

.log-logger {
  color: var(--text-tertiary, #86909C);
  min-width: 90px;
  max-width: 140px;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-msg {
  color: var(--text-primary, #1D2129);
  flex: 1;
  word-break: break-word;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-msg.has-exception { color: #DC2626; font-weight: 500; }

/* Expanded detail */
.log-detail {
  padding: 8px 12px 12px 92px;
  background: #F8FAFC;
  border-top: 1px dashed var(--border-light);
  font-size: 11px;
}

.log-detail-row { display: flex; gap: 8px; margin-bottom: 6px; }
.log-detail-label {
  font-weight: 600; color: var(--text-tertiary);
  min-width: 56px; flex-shrink: 0;
}

.log-detail-msg {
  margin: 0; white-space: pre-wrap; word-break: break-word;
  color: var(--text-primary); font-size: 11px;
}

.log-exception {
  width: 100%;
  background: #FEF2F2;
  color: #991B1B;
  padding: 10px 14px;
  border-radius: 6px;
  margin: 4px 0;
  font-size: 11px;
  overflow-x: auto;
  white-space: pre-wrap;
  line-height: 1.5;
}

.expand-enter-active,
.expand-leave-active { transition: all 0.2s ease; overflow: hidden; }
.expand-enter-from,
.expand-leave-to { opacity: 0; max-height: 0; padding-top: 0; padding-bottom: 0; }
</style>
