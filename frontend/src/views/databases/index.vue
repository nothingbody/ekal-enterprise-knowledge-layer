<template>
  <div class="databases-page">
    <div class="page-header">
      <div>
        <h2>数据库管理</h2>
        <p class="page-desc">连接数据库，构建知识库的数据基础</p>
      </div>
      <el-button type="primary" @click="openCreateDialog">
        <PlusIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />连接新数据库
      </el-button>
    </div>

    <!-- ═══ 本地发现的数据库 ═══ -->
    <div class="section-block" v-loading="scanning">
      <div class="section-title">
        <span><MonitorIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" /> 本地数据库</span>
        <el-button link type="primary" size="small" @click="runScan" :loading="scanning">
          <RefreshCwIcon :size="13" :stroke-width="1.5" style="margin-right: 2px" />重新扫描
        </el-button>
      </div>
      <div v-if="!scanning && discoveredDbs.length === 0" class="scan-empty">
        未发现本地数据库服务，请确认 MySQL 或 PostgreSQL 已启动。
        <span v-if="!sources.length">或<el-button link type="primary" @click="openCreateDialog">点击连接新数据库</el-button>手动配置。首次使用？<el-button link type="primary" @click="$router.push('/guide')">查看使用指南</el-button></span>
      </div>
      <div v-else class="discovered-grid">
        <div v-for="(db, idx) in discoveredDbs" :key="idx" class="discovered-card" :class="{ used: isDbAlreadyConnected(db) }">
          <div class="discovered-header">
            <el-icon class="db-icon" :size="18"><Coin /></el-icon>
            <span class="discovered-name">{{ db.database_name }}</span>
            <el-tag size="small">{{ dbTypeLabel(db.db_type) }}</el-tag>
          </div>
          <div class="discovered-meta">
            <span>{{ db.host }}:{{ db.port }} · {{ db.username }}</span>
            <span>{{ db.table_count }} 张表</span>
          </div>
          <div class="discovered-actions">
            <template v-if="isDbAlreadyConnected(db)">
              <el-tag size="small" type="success">已连接</el-tag>
            </template>
            <template v-else>
              <el-button size="small" type="primary" @click="quickCreateFromDiscovered(db)">
                <FolderPlusIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />创建知识库
              </el-button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 已连接的数据库源 ═══ -->
    <div class="section-block" v-loading="loading" v-if="sources.length > 0">
      <div class="section-title">
        <span><PlugIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" /> 已连接的数据库</span>
      </div>
      <div class="source-list">
        <div v-for="src in sources" :key="src.id" class="source-card">
          <div class="source-card-header">
            <div class="source-info">
              <el-icon class="db-icon" :size="20"><Coin /></el-icon>
              <span class="source-name">{{ src.name }}</span>
              <el-tag size="small">{{ dbTypeLabel(src.db_type) }}</el-tag>
              <el-tag size="small" :type="statusTagType(src.status)">{{ statusLabel(src.status) }}</el-tag>
              <span v-if="src.status === 'syncing' && syncProgress[src.id]" class="sync-progress-text">{{ syncProgress[src.id] }}</span>
            </div>
            <div class="source-card-actions">
              <el-button link size="small" type="primary" @click="handleTest(src)">测试连接</el-button>
              <el-button link size="small" type="primary" @click="handleBrowseTables(src)">浏览表</el-button>
              <el-button link size="small" type="success" @click="handleSync(src)" :loading="src._syncing">同步数据</el-button>
              <el-button link size="small" type="primary" @click="handleSyncRuns(src)">同步历史</el-button>
              <el-button link size="small" type="primary" @click="goToKb(src.kb_id)">查看知识库</el-button>
            </div>
          </div>
          <div class="source-card-meta">
            <span>{{ src.host }}:{{ src.port }} / {{ src.database_name }}</span>
            <span v-if="src.table_names?.length" class="meta-tables">表: {{ src.table_names.join(', ') }}</span>
            <span v-if="src.last_synced_at" class="meta-sync">上次同步: {{ new Date(src.last_synced_at).toLocaleString() }}</span>
          </div>
          <div v-if="src.status === 'failed' && src.last_error" class="source-error">
            <TriangleAlertIcon :size="13" :stroke-width="1.5" style="margin-right: 4px" /> {{ src.last_error }}
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 同步历史对话框 ═══ -->
    <el-dialog v-model="showSyncRunsDialog" title="同步历史" width="720px" destroy-on-close>
      <div v-loading="syncRunsLoading">
        <el-table v-if="syncRuns.length" :data="syncRuns" size="small" stripe>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">
              {{ row.started_at ? new Date(row.started_at).toLocaleString() : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="syncRunTagType(row.status)" size="small">{{ syncRunLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="table_count" label="表数" width="65" />
          <el-table-column prop="row_count" label="行数" width="65" />
          <el-table-column prop="chunk_count" label="切片" width="65" />
          <el-table-column label="耗时" width="80">
            <template #default="{ row }">
              {{ row.duration_seconds != null ? row.duration_seconds + 's' : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="详情" min-width="160">
            <template #default="{ row }">
              <span v-if="row.error_message" class="source-error-inline">{{ row.error_message }}</span>
              <el-button v-if="row.tables_detail" link size="small" type="primary" @click="showRunDetail(row)">查看表详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!syncRunsLoading" description="暂无同步记录" />
      </div>
    </el-dialog>

    <!-- 单次同步表详情 -->
    <el-dialog v-model="showRunDetailDialog" title="表同步详情" width="600px" destroy-on-close>
      <el-table v-if="runDetailTables.length" :data="runDetailTables" size="small" stripe>
        <el-table-column prop="table" label="表名" min-width="120" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ok' ? 'success' : 'danger'" size="small">{{ row.status === 'ok' ? '成功' : '失败' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rows" label="行数" width="65" />
        <el-table-column prop="chunks" label="切片" width="65" />
        <el-table-column label="耗时" width="80">
          <template #default="{ row }">{{ row.seconds != null ? row.seconds + 's' : '-' }}</template>
        </el-table-column>
        <el-table-column prop="error" label="错误" min-width="150" />
      </el-table>
    </el-dialog>

    <!-- 连接数据库 + 创建知识库 对话框 -->
    <el-dialog v-model="showCreateDialog" title="连接数据库" width="640px" :close-on-click-modal="false" destroy-on-close>
      <el-steps :active="createStep" finish-status="success" simple style="margin-bottom: 20px;">
        <el-step title="服务器连接" />
        <el-step title="选择数据库和表" />
        <el-step title="创建知识库" />
      </el-steps>

      <!-- Step 0: 服务器连接（只需 host/port/用户名/密码） -->
      <div v-show="createStep === 0">
        <el-form :model="form" label-width="100px">
          <el-form-item label="数据库类型" required>
            <el-select v-model="form.db_type" style="width: 100%" @change="onDbTypeChange">
              <el-option label="PostgreSQL" value="postgresql" />
              <el-option label="MySQL" value="mysql" />
            </el-select>
          </el-form-item>
          <el-form-item label="主机" required>
            <el-input v-model="form.host" placeholder="localhost" />
          </el-form-item>
          <el-form-item label="端口" required>
            <el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" />
          </el-form-item>
          <el-form-item label="用户名" required>
            <el-input v-model="form.username" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="form.password" type="password" show-password />
          </el-form-item>
        </el-form>
        <div style="text-align: right; margin-top: 12px;">
          <el-button type="primary" @click="connectServer" :loading="connectLoading" :disabled="!canConnect">
            连接服务器
          </el-button>
        </div>
      </div>

      <!-- Step 1: 选择数据库 → 选择表 -->
      <div v-show="createStep === 1">
        <div v-loading="connectLoading || tablesLoading">
          <!-- 选择数据库 -->
          <div style="margin-bottom: 12px;">
            <span style="font-weight: 600; margin-right: 8px;">选择数据库：</span>
            <el-select v-model="form.database_name" placeholder="选择数据库" style="width: 300px;" @change="onDatabaseSelected">
              <el-option v-for="db in serverDatabases" :key="db.database_name" :label="`${db.database_name}（${db.table_count} 张表）`" :value="db.database_name" />
            </el-select>
          </div>
          <!-- 选择表 -->
          <div v-if="form.database_name">
            <p style="margin-bottom: 8px; color: var(--text-secondary, #909399);">选择要同步的表（不选则同步全部）：</p>
            <el-checkbox-group v-model="selectedTables" v-if="availableTables.length">
              <el-checkbox v-for="t in availableTables" :key="t.name" :value="t.name" style="display: block; margin: 6px 0;">
                {{ t.name }} <el-tag size="small" type="info">{{ t.kind }}</el-tag>
                <span style="color: #909399; font-size: 12px; margin-left: 8px;">{{ t.columns.length }} 列</span>
              </el-checkbox>
            </el-checkbox-group>
            <el-empty v-else-if="!tablesLoading" description="未找到表" />
          </div>
        </div>
        <div style="text-align: right; margin-top: 12px;">
          <el-button @click="createStep = 0">上一步</el-button>
          <el-button type="primary" @click="createStep = 2" :disabled="!form.database_name">下一步：创建知识库</el-button>
        </div>
      </div>

      <!-- Step 2: 知识库信息 -->
      <div v-show="createStep === 2">
        <el-form :model="kbForm" label-width="100px">
          <el-form-item label="知识库名称" required>
            <el-input v-model="kbForm.name" placeholder="为知识库命名" maxlength="200" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="kbForm.description" type="textarea" :rows="3" placeholder="知识库描述（可选）" />
          </el-form-item>
          <el-form-item label="Embedding 模型" required>
            <el-select v-model="kbForm.embedding_model_id" placeholder="选择 Embedding 模型" style="width: 100%">
              <el-option v-for="m in embeddingModels" :key="m.id" :label="m.display_name" :value="m.id" />
            </el-select>
            <div v-if="!embeddingModels.length" style="margin-top: 4px; color: var(--warning, #e6a23c); font-size: 12px;">
              尚未配置 Embedding 模型，
              <el-button link type="primary" size="small" @click="router.push('/models')">前往添加</el-button>
            </div>
          </el-form-item>
          <el-form-item label="每表行数上限">
            <el-input-number v-model="form.row_limit" :min="1" :max="5000" :step="100" style="width: 100%" />
          </el-form-item>
        </el-form>
        <div style="text-align: right; margin-top: 12px;">
          <el-button @click="createStep = 1">上一步</el-button>
          <el-button type="primary" @click="handleCreateKbWithDb" :loading="createLoading" :disabled="!canCreateKbWithDb">创建知识库</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 浏览表对话框 -->
    <el-dialog v-model="showTablesDialog" title="数据库表结构" width="650px" destroy-on-close>
      <div v-loading="browseLoading">
        <el-collapse v-if="browseTables.length">
          <el-collapse-item v-for="t in browseTables" :key="t.name" :title="`${t.name} (${t.kind})`">
            <el-table :data="t.columns" size="small" stripe>
              <el-table-column prop="name" label="列名" />
              <el-table-column prop="type" label="类型" />
            </el-table>
          </el-collapse-item>
        </el-collapse>
        <el-empty v-else-if="!browseLoading" description="无表信息" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, onDeactivated } from 'vue'
import { useRouter } from 'vue-router'
import {
  Plus as PlusIcon, Monitor as MonitorIcon, RefreshCw as RefreshCwIcon,
  FolderPlus as FolderPlusIcon, Plug as PlugIcon, TriangleAlert as TriangleAlertIcon,
} from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import request from '../../utils/request'
import {
  listAllDatabaseSources,
  scanLocalDatabases,
  testDatabaseConnection,
  testSavedDatabaseConnection,
  listDatabaseTables,
  listServerDatabases,
  syncDatabaseSource,
  listSyncRuns,
  type DatabaseSourceItem,
  type DatabaseTableInfo,
  type DiscoveredDatabase,
  type ServerDatabase,
  type SyncRunItem,
} from '../../api/databaseSources'
import { listModels } from '../../api/models'

const router = useRouter()
const loading = ref(false)
const sources = ref<(DatabaseSourceItem & { _syncing?: boolean })[]>([])
const scanning = ref(false)
const discoveredDbs = ref<DiscoveredDatabase[]>([])
const embeddingModels = ref<any[]>([])

let pollTimer: ReturnType<typeof setInterval> | null = null
const syncProgress = ref<Record<number, string>>({})

function dbTypeLabel(t: string) {
  const m: Record<string, string> = { postgresql: 'PostgreSQL', mysql: 'MySQL' }
  return m[t] || t
}
function statusTagType(s: string) {
  const m: Record<string, string> = { completed: 'success', syncing: 'warning', failed: 'danger', pending: 'info' }
  return m[s] || 'info'
}
function statusLabel(s: string) {
  const m: Record<string, string> = { completed: '已同步', syncing: '同步中', failed: '失败', pending: '待同步' }
  return m[s] || s
}

async function runScan() {
  scanning.value = true
  try {
    const res: any = await scanLocalDatabases()
    discoveredDbs.value = res?.databases || []
  } catch {
    discoveredDbs.value = []
    ElMessage.error('扫描本地数据库失败，请确认数据库服务已启动')
  } finally {
    scanning.value = false
  }
}

function isDbAlreadyConnected(db: DiscoveredDatabase): boolean {
  return sources.value.some(s => {
    if (s.db_type !== db.db_type) return false
    return s.host === db.host && s.port === db.port && s.database_name === db.database_name
  })
}

async function quickCreateFromDiscovered(db: DiscoveredDatabase) {
  form.value = {
    db_type: db.db_type as 'postgresql' | 'mysql',
    host: db.host || 'localhost',
    port: db.port || 3306,
    database_name: db.database_name || '',
    schema_name: '',
    username: db.username || '',
    password: '',
    row_limit: 200,
  }
  await loadEmbeddingModels()
  kbForm.value = {
    name: db.database_name,
    description: `基于 ${dbTypeLabel(db.db_type)} 数据库 ${db.database_name} 构建的知识库`,
    embedding_model_id: getDefaultEmbeddingModelId(),
  }
  serverDatabases.value = [{ database_name: db.database_name, table_count: db.table_count }]
  availableTables.value = []
  selectedTables.value = []
  showCreateDialog.value = true
  createStep.value = 1
  await onDatabaseSelected()
}

async function loadSources() {
  if (!pollTimer) loading.value = true
  try {
    const res = await listAllDatabaseSources()
    sources.value = (res as any) || []
    const syncingSources = sources.value.filter(s => s.status === 'syncing')
    if (syncingSources.length && !pollTimer) {
      pollTimer = setInterval(loadSources, 3000)
    } else if (!syncingSources.length && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
      syncProgress.value = {}
    }
    // Fetch progress for syncing sources
    for (const src of syncingSources) {
      try {
        const runs = await listSyncRuns(src.id, 1)
        const latest = (runs as any)?.[0]
        if (latest && latest.status === 'running' && latest.error_message) {
          syncProgress.value[src.id] = latest.error_message
        }
      } catch {}
    }
  } finally {
    loading.value = false
  }
}

async function handleTest(src: DatabaseSourceItem) {
  try {
    const res: any = await testSavedDatabaseConnection(src.id)
    ElMessage.success(res.message || '连接成功')
  } catch (e: any) {
    ElMessage.error(extractError(e))
  }
}

const showTablesDialog = ref(false)
const browseLoading = ref(false)
const browseTables = ref<DatabaseTableInfo[]>([])

async function handleBrowseTables(src: DatabaseSourceItem) {
  showTablesDialog.value = true
  browseLoading.value = true
  browseTables.value = []
  try {
    const res = await listDatabaseTables(src.id)
    browseTables.value = (res as any) || []
  } catch (e: any) {
    ElMessage.error(extractError(e))
  } finally {
    browseLoading.value = false
  }
}

async function handleSync(src: DatabaseSourceItem & { _syncing?: boolean }) {
  try {
    src._syncing = true
    await syncDatabaseSource(src.id)
    ElMessage.success('同步任务已启动')
    src.status = 'syncing'
    if (!pollTimer) {
      pollTimer = setInterval(loadSources, 5000)
    }
  } catch (e: any) {
    ElMessage.error(extractError(e))
  } finally {
    src._syncing = false
  }
}

function goToKb(kbId: number) {
  router.push(`/knowledge/${kbId}/documents`)
}

// ── 同步历史 ──
const showSyncRunsDialog = ref(false)
const syncRunsLoading = ref(false)
const syncRuns = ref<SyncRunItem[]>([])
const showRunDetailDialog = ref(false)
const runDetailTables = ref<any[]>([])

function syncRunTagType(s: string) {
  const m: Record<string, string> = { completed: 'success', partial: 'warning', failed: 'danger', running: 'info' }
  return m[s] || 'info'
}
function syncRunLabel(s: string) {
  const m: Record<string, string> = { completed: '成功', partial: '部分成功', failed: '失败', running: '运行中' }
  return m[s] || s
}

async function handleSyncRuns(src: DatabaseSourceItem) {
  showSyncRunsDialog.value = true
  syncRunsLoading.value = true
  syncRuns.value = []
  try {
    const res = await listSyncRuns(src.id)
    syncRuns.value = (res as any) || []
  } catch (e: any) {
    ElMessage.error(extractError(e))
  } finally {
    syncRunsLoading.value = false
  }
}

function showRunDetail(run: SyncRunItem) {
  try {
    runDetailTables.value = JSON.parse(run.tables_detail || '[]')
  } catch {
    runDetailTables.value = []
  }
  showRunDetailDialog.value = true
}

// ── 创建数据库 + 知识库 ──
const showCreateDialog = ref(false)
const createStep = ref(0)
const connectLoading = ref(false)
const tablesLoading = ref(false)
const createLoading = ref(false)
const serverDatabases = ref<ServerDatabase[]>([])
const availableTables = ref<DatabaseTableInfo[]>([])
const selectedTables = ref<string[]>([])

const defaultForm = () => ({
  db_type: 'postgresql' as 'postgresql' | 'mysql',
  host: 'localhost',
  port: 5432,
  database_name: '',
  schema_name: '',
  username: '',
  password: '',
  row_limit: 200,
})
const form = ref(defaultForm())

const kbForm = ref({ name: '', description: '', embedding_model_id: null as number | null })

const canConnect = computed(() => !!form.value.host && !!form.value.username)

function getDefaultEmbeddingModelId() {
  if (!embeddingModels.value.length) return null
  const defaultModel = embeddingModels.value.find((m: any) => m.is_default)
  return defaultModel?.id || embeddingModels.value[0].id
}

async function loadEmbeddingModels() {
  try {
    const res: any = await listModels('embedding')
    embeddingModels.value = res || []
  } catch {
    embeddingModels.value = []
  }
  if (!embeddingModels.value.some((m: any) => m.id === kbForm.value.embedding_model_id)) {
    kbForm.value.embedding_model_id = getDefaultEmbeddingModelId()
  }
}

function onDbTypeChange() {
  if (form.value.db_type === 'postgresql') form.value.port = 5432
  else if (form.value.db_type === 'mysql') form.value.port = 3306
}

const canCreateKbWithDb = computed(() => !!kbForm.value.name.trim() && !!kbForm.value.embedding_model_id)

async function openCreateDialog() {
  await loadEmbeddingModels()
  form.value = defaultForm()
  kbForm.value = { name: '', description: '', embedding_model_id: getDefaultEmbeddingModelId() }
  createStep.value = 0
  serverDatabases.value = []
  availableTables.value = []
  selectedTables.value = []
  showCreateDialog.value = true
}

function extractError(e: any): string {
  const d = e?.response?.data?.detail
  if (Array.isArray(d)) return d.map((x: any) => x.msg || x).join('; ')
  if (typeof d === 'string') return d
  return '操作失败'
}

function cleanFormData(f: typeof form.value) {
  const base: Record<string, any> = { db_type: f.db_type, row_limit: f.row_limit }
  base.host = f.host || undefined
  if (f.port) base.port = f.port
  base.database_name = f.database_name || undefined
  base.username = f.username || undefined
  if (f.password) base.password = f.password
  if (f.schema_name) base.schema_name = f.schema_name
  return base
}

async function connectServer() {
  connectLoading.value = true
  serverDatabases.value = []
  form.value.database_name = ''
  availableTables.value = []
  selectedTables.value = []
  try {
    const res: any = await listServerDatabases({
      db_type: form.value.db_type as 'postgresql' | 'mysql',
      host: form.value.host,
      port: form.value.port,
      username: form.value.username,
      password: form.value.password || undefined,
    })
    serverDatabases.value = res.databases || []
    if (!serverDatabases.value.length) {
      ElMessage.warning('服务器上没有发现用户数据库')
      return
    }
    ElMessage.success(res.message || `发现 ${serverDatabases.value.length} 个数据库`)
    createStep.value = 1
  } catch (e: any) {
    ElMessage.error(extractError(e))
  } finally {
    connectLoading.value = false
  }
}

async function onDatabaseSelected() {
  if (!form.value.database_name) return
  tablesLoading.value = true
  availableTables.value = []
  selectedTables.value = []
  kbForm.value.name = form.value.database_name
  kbForm.value.description = `基于 ${dbTypeLabel(form.value.db_type)} 数据库 ${form.value.database_name} 构建的知识库`
  try {
    const res: any = await testDatabaseConnection(cleanFormData(form.value) as any)
    availableTables.value = res.tables || []
  } catch {
    // Tables will just be empty
  } finally {
    tablesLoading.value = false
  }
}

async function handleCreateKbWithDb() {
  if (!kbForm.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  if (!kbForm.value.embedding_model_id) {
    ElMessage.warning('请选择 Embedding 模型')
    return
  }
  createLoading.value = true
  try {
    const payload: any = {
      ...cleanFormData(form.value),
      kb_name: kbForm.value.name,
      kb_description: kbForm.value.description,
      embedding_model_id: kbForm.value.embedding_model_id,
      source_name: kbForm.value.name,
      table_names: selectedTables.value.length ? selectedTables.value : undefined,
    }
    const res: any = await request.post('/database-sources/create-with-kb', payload, { _silentError: true } as any)
    ElMessage.success(res.message || '知识库已创建，数据库同步已启动')
    showCreateDialog.value = false
    await loadSources()
    router.push(`/knowledge/${res.kb_id}/documents`)
  } catch (e: any) {
    ElMessage.error(extractError(e))
  } finally {
    createLoading.value = false
  }
}

onActivated(() => {
  loadSources()
  runScan()
})

onDeactivated(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<style scoped>
.databases-page {
  max-width: 1200px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}
.page-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}
.page-desc {
  margin: 4px 0 0;
  color: var(--text-secondary, #909399);
  font-size: 13px;
}

.section-block {
  margin-bottom: 24px;
}
.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}
.section-title .el-icon {
  margin-right: 4px;
  vertical-align: -2px;
}
.scan-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-secondary, #909399);
  font-size: 13px;
  background: var(--bg-card, #fff);
  border: 1px dashed var(--border-color, #e4e7ed);
  border-radius: 8px;
}

.discovered-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.discovered-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e4e7ed);
  border-radius: 8px;
  padding: 14px;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.discovered-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border-color: var(--el-color-primary-light-5, #a0cfff);
}
.discovered-card.used {
  opacity: 0.7;
}
.discovered-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.discovered-name {
  font-weight: 600;
  font-size: 14px;
}
.discovered-meta {
  font-size: 12px;
  color: var(--text-secondary, #909399);
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}
.discovered-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.source-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e4e7ed);
  border-radius: 8px;
  padding: 16px;
  transition: box-shadow 0.2s;
}
.source-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.source-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.source-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sync-progress-text {
  font-size: 12px;
  color: var(--el-color-warning);
  font-weight: 500;
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.db-icon {
  color: var(--el-color-warning);
}
.source-name {
  font-weight: 600;
  font-size: 15px;
}
.source-card-actions {
  display: flex;
  gap: 4px;
}

.source-card-meta {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary, #909399);
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}
.meta-tables {
  color: var(--el-color-primary);
}
.meta-sync {
  color: var(--text-tertiary, #c0c4cc);
}

.source-error {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--el-color-danger-light-9, #fef0f0);
  color: var(--el-color-danger, #f56c6c);
  border-radius: 4px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.source-error-inline {
  color: var(--el-color-danger, #f56c6c);
  font-size: 12px;
  margin-right: 6px;
}
</style>
