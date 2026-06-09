<template>
  <div class="db-sources-section">
    <div class="section-header" @click="expanded = !expanded">
      <div class="section-title">
        <DatabaseIcon :size="14" :stroke-width="1.5" />
        <span>数据库数据源</span>
        <el-tag size="small" type="info" v-if="sources.length">{{ sources.length }}</el-tag>
      </div>
      <ChevronRightIcon :size="14" :stroke-width="1.5" class="expand-icon" :class="{ rotated: expanded }" />
    </div>

    <div v-show="expanded" class="section-body">
      <div class="source-actions" v-if="canManage">
        <el-button type="primary" size="small" @click="openCreate">
          <PlusIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />添加数据库源
        </el-button>
      </div>

      <div v-loading="loading">
        <div v-if="!loading && sources.length === 0" class="empty-tip">
          暂无数据库数据源
          <el-button v-if="canManage" link type="primary" @click="openCreate" style="margin-left: 4px">点击添加</el-button>
          <el-button link type="primary" @click="$router.push('/databases')" style="margin-left: 4px">前往数据库管理</el-button>
        </div>
        <div v-for="src in sources" :key="src.id" class="source-card">
          <div class="source-card-header">
            <div class="source-info">
              <DatabaseIcon :size="16" :stroke-width="1.5" class="db-icon" />
              <span class="source-name">{{ src.name }}</span>
              <el-tag size="small">{{ dbTypeLabel(src.db_type) }}</el-tag>
              <el-tag size="small" :type="statusTagType(src.status)">{{ statusLabel(src.status) }}</el-tag>
            </div>
            <div class="source-card-actions" v-if="canManage">
              <el-button link size="small" type="primary" @click="handleTestSaved(src)">测试连接</el-button>
              <el-button link size="small" type="primary" @click="handleBrowseTables(src)">浏览表</el-button>
              <el-button link size="small" type="success" @click="handleSync(src)" :loading="src._syncing">同步</el-button>
              <el-button link size="small" type="primary" @click="openEdit(src)">编辑</el-button>
              <el-button link size="small" type="danger" @click="handleDelete(src)">删除</el-button>
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

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="showFormDialog" :title="editingSource ? '编辑数据库源' : '添加数据库源'" width="580px" :close-on-click-modal="false" destroy-on-close>
      <el-form :model="form" label-width="100px" ref="formRef">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="数据源名称" maxlength="200" />
        </el-form-item>
        <el-form-item label="数据库类型" required>
          <el-select v-model="form.db_type" style="width: 100%" @change="onDbTypeChange">
            <el-option label="PostgreSQL" value="postgresql" />
            <el-option label="MySQL" value="mysql" />
            <el-option label="Trino" value="trino" />
          </el-select>
        </el-form-item>

        <el-form-item label="主机" required>
            <el-input v-model="form.host" placeholder="localhost" />
          </el-form-item>
          <el-form-item label="端口">
            <el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" />
          </el-form-item>
          <el-form-item label="数据库名" required>
            <el-input v-model="form.database_name" placeholder="数据库名称" />
          </el-form-item>
          <el-form-item label="Schema">
            <el-input v-model="form.schema_name" placeholder="可选，如 public" />
          </el-form-item>
          <el-form-item label="用户名" required>
            <el-input v-model="form.username" placeholder="数据库用户名" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="form.password" type="password" show-password :placeholder="editingSource?.has_password ? '留空则不修改' : '数据库密码'" />
          </el-form-item>

        <el-form-item label="同步表">
          <div style="width: 100%">
            <div style="display: flex; gap: 8px; margin-bottom: 8px;">
              <el-input v-model="tableInput" placeholder="输入表名后回车添加" @keyup.enter="addTable" style="flex: 1" />
              <el-button size="small" @click="addTable">添加</el-button>
              <el-button size="small" type="primary" @click="fetchAndPickTables" :loading="browseLoading">从数据库选择</el-button>
            </div>
            <div v-if="form.table_names?.length" class="selected-tables">
              <el-tag v-for="t in form.table_names" :key="t" closable size="small" @close="removeTable(t)" style="margin: 2px">{{ t }}</el-tag>
            </div>
            <div v-else class="table-hint">未指定则同步所有表</div>
          </div>
        </el-form-item>
        <el-form-item label="行数上限">
          <el-input-number v-model="form.row_limit" :min="1" :max="5000" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleTestForm" :loading="testLoading">测试连接</el-button>
        <el-button @click="showFormDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitLoading">{{ editingSource ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <!-- 表浏览对话框 -->
    <el-dialog v-model="showTablesDialog" title="数据库表结构" width="650px" destroy-on-close>
      <div v-loading="browseLoading">
        <div v-if="!browseLoading && browseTables.length === 0" style="text-align: center; color: #909399; padding: 20px;">未发现表或视图</div>
        <el-collapse v-if="browseTables.length" accordion>
          <el-collapse-item v-for="tbl in browseTables" :key="tbl.name" :name="tbl.name">
            <template #title>
              <span style="font-weight: 600;">{{ tbl.name }}</span>
              <el-tag size="small" type="info" style="margin-left: 8px">{{ tbl.kind }}</el-tag>
              <el-tag size="small" style="margin-left: 4px">{{ tbl.columns.length }} 列</el-tag>
            </template>
            <el-table :data="tbl.columns" size="small" stripe>
              <el-table-column prop="name" label="字段名" />
              <el-table-column prop="type" label="类型" />
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-dialog>

    <!-- 从数据库选择表和字段对话框 -->
    <el-dialog v-model="showPickTablesDialog" title="选择要同步的表和字段" width="600px" destroy-on-close>
      <div v-loading="browseLoading">
        <div style="margin-bottom: 8px; color: #909399; font-size: 12px;">勾选表后可展开选择具体字段，不选字段则同步所有列</div>
        <div v-for="tbl in browseTables" :key="tbl.name" class="pick-table-item">
          <el-checkbox :model-value="pickedTables.includes(tbl.name)" @change="(v: boolean) => togglePickTable(tbl.name, v)">
            <span style="font-weight: 600;">{{ tbl.name }}</span>
            <el-tag size="small" type="info" style="margin-left: 4px">{{ tbl.kind }}</el-tag>
            <el-tag size="small" style="margin-left: 4px">{{ tbl.columns.length }} 列</el-tag>
          </el-checkbox>
          <div v-if="pickedTables.includes(tbl.name)" class="pick-columns">
            <el-checkbox
              :model-value="!(pickedColumns[tbl.name]?.length) || pickedColumns[tbl.name]?.length === tbl.columns.length"
              :indeterminate="(pickedColumns[tbl.name]?.length ?? 0) > 0 && (pickedColumns[tbl.name]?.length ?? 0) < tbl.columns.length"
              @change="(v: boolean) => toggleAllColumns(tbl, v)"
              style="margin-right: 12px;"
            >全选</el-checkbox>
            <el-checkbox-group :model-value="pickedColumns[tbl.name] || []" @update:model-value="(v: string[]) => pickedColumns[tbl.name] = v">
              <el-checkbox v-for="col in tbl.columns" :key="col.name" :value="col.name" style="margin-right: 8px;">
                {{ col.name }} <span style="color: #909399; font-size: 11px;">{{ col.type }}</span>
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </div>
        <div v-if="!browseLoading && browseTables.length === 0" style="text-align: center; color: #909399; padding: 20px;">未发现表或视图</div>
      </div>
      <template #footer>
        <el-button @click="showPickTablesDialog = false">取消</el-button>
        <el-button type="primary" @click="applyPickedTables">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import {
  Database as DatabaseIcon, ChevronRight as ChevronRightIcon,
  Plus as PlusIcon, TriangleAlert as TriangleAlertIcon,
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listDatabaseSources,
  createDatabaseSource,
  updateDatabaseSource,
  deleteDatabaseSource,
  testDatabaseConnection,
  testSavedDatabaseConnection,
  listDatabaseTables,
  syncDatabaseSource,
  type DatabaseSourceItem,
  type DatabaseSourceForm,
  type DatabaseTableInfo,
} from '../../api/databaseSources'

const props = defineProps<{
  kbId: number
  canManage: boolean
}>()

const expanded = ref(true)
const loading = ref(false)
const sources = ref<(DatabaseSourceItem & { _syncing?: boolean })[]>([])

const showFormDialog = ref(false)
const editingSource = ref<DatabaseSourceItem | null>(null)
const submitLoading = ref(false)
const testLoading = ref(false)

const defaultForm = (): DatabaseSourceForm => ({
  kb_id: props.kbId,
  name: '',
  db_type: 'postgresql',
  host: '',
  port: 5432,
  database_name: '',
  schema_name: '',
  username: '',
  password: '',
  table_names: [],
  column_filter: {},
  row_limit: 200,
})

const form = ref<DatabaseSourceForm>(defaultForm())
const tableInput = ref('')

const showTablesDialog = ref(false)
const showPickTablesDialog = ref(false)
const browseLoading = ref(false)
const browseTables = ref<DatabaseTableInfo[]>([])
const pickedTables = ref<string[]>([])
const pickedColumns = ref<Record<string, string[]>>({})

let pollTimer: ReturnType<typeof setInterval> | null = null

function dbTypeLabel(t: string) {
  const m: Record<string, string> = { postgresql: 'PostgreSQL', mysql: 'MySQL', trino: 'Trino' }
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

async function loadSources() {
  loading.value = true
  try {
    const res = await listDatabaseSources(props.kbId)
    sources.value = (res as any) || []
    if (sources.value.length > 0 || props.canManage) {
      expanded.value = true
    }
    const hasSyncing = sources.value.some(s => s.status === 'syncing')
    if (hasSyncing && !pollTimer) {
      pollTimer = setInterval(loadSources, 5000)
    } else if (!hasSyncing && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingSource.value = null
  form.value = defaultForm()
  showFormDialog.value = true
}

function openEdit(src: DatabaseSourceItem) {
  editingSource.value = src
  form.value = {
    kb_id: src.kb_id,
    name: src.name,
    db_type: src.db_type as any,
    host: src.host || '',
    port: src.port || (src.db_type === 'mysql' ? 3306 : src.db_type === 'trino' ? 8080 : 5432),
    database_name: src.database_name || '',
    schema_name: src.schema_name || '',
    username: src.username || '',
    password: '',
    table_names: [...(src.table_names || [])],
    column_filter: src.column_filter ? { ...src.column_filter } : {},
    row_limit: src.row_limit || 200,
  }
  showFormDialog.value = true
}

function onDbTypeChange(val: string) {
  if (val === 'postgresql') form.value.port = 5432
  else if (val === 'mysql') form.value.port = 3306
  else if (val === 'trino') form.value.port = 8080
  else form.value.port = undefined
}

function addTable() {
  const t = tableInput.value.trim()
  if (!t) return
  if (!form.value.table_names) form.value.table_names = []
  if (!form.value.table_names.includes(t)) {
    form.value.table_names.push(t)
  }
  tableInput.value = ''
}

function removeTable(t: string) {
  form.value.table_names = form.value.table_names?.filter(x => x !== t)
}

function buildTestPayload() {
  return {
    db_type: form.value.db_type,
    host: form.value.host,
    port: form.value.port,
    database_name: form.value.database_name,
    schema_name: form.value.schema_name,
    username: form.value.username,
    password: form.value.password,
    row_limit: form.value.row_limit,
  }
}

async function handleTestForm() {
  testLoading.value = true
  try {
    await testDatabaseConnection(buildTestPayload())
    ElMessage.success('连接成功')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e.message || '连接失败')
  } finally {
    testLoading.value = false
  }
}

async function handleSubmit() {
  if (!form.value.name.trim()) { ElMessage.warning('请输入数据源名称'); return }
  submitLoading.value = true
  try {
    const payload = { ...form.value }
    if (!payload.table_names?.length) delete payload.table_names
    if (!payload.column_filter || Object.keys(payload.column_filter).length === 0) delete payload.column_filter
    if (!payload.password) delete payload.password
    if (editingSource.value) {
      const { kb_id, ...rest } = payload
      await updateDatabaseSource(editingSource.value.id, rest)
      ElMessage.success('更新成功')
    } else {
      await createDatabaseSource(payload)
      ElMessage.success('创建成功')
    }
    showFormDialog.value = false
    await loadSources()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e.message || '操作失败')
  } finally {
    submitLoading.value = false
  }
}

async function handleTestSaved(src: DatabaseSourceItem) {
  try {
    await testSavedDatabaseConnection(src.id)
    ElMessage.success('连接成功')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e.message || '连接失败')
  }
}

async function handleBrowseTables(src: DatabaseSourceItem) {
  browseLoading.value = true
  browseTables.value = []
  showTablesDialog.value = true
  try {
    browseTables.value = (await listDatabaseTables(src.id)) as any
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e.message || '获取表结构失败')
  } finally {
    browseLoading.value = false
  }
}

async function fetchAndPickTables() {
  if (!editingSource.value && !form.value.host) {
    ElMessage.warning('请先填写连接信息')
    return
  }
  browseLoading.value = true
  browseTables.value = []

  if (editingSource.value) {
    try {
      browseTables.value = (await listDatabaseTables(editingSource.value.id)) as any
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e.message || '获取表失败')
      browseLoading.value = false
      return
    }
  } else {
    try {
      await testDatabaseConnection(buildTestPayload())
    } catch (e: any) {
      ElMessage.error('请先确保连接成功: ' + (e?.response?.data?.detail || e.message || ''))
      browseLoading.value = false
      return
    }
    ElMessage.info('新建数据源需要先保存后才能浏览表结构，请先手动输入表名或保存后再选择')
    browseLoading.value = false
    return
  }

  browseLoading.value = false
  pickedTables.value = [...(form.value.table_names || [])]
  // Initialize pickedColumns from existing column_filter
  pickedColumns.value = {}
  if (form.value.column_filter) {
    for (const [tbl, cols] of Object.entries(form.value.column_filter)) {
      if (cols && cols.length) pickedColumns.value[tbl] = [...cols]
    }
  }
  showPickTablesDialog.value = true
}

function togglePickTable(name: string, checked: boolean) {
  if (checked) {
    if (!pickedTables.value.includes(name)) pickedTables.value.push(name)
  } else {
    pickedTables.value = pickedTables.value.filter(t => t !== name)
    delete pickedColumns.value[name]
  }
}

function toggleAllColumns(tbl: DatabaseTableInfo, selectAll: boolean) {
  if (selectAll) {
    pickedColumns.value[tbl.name] = tbl.columns.map(c => c.name)
  } else {
    pickedColumns.value[tbl.name] = []
  }
}

function applyPickedTables() {
  form.value.table_names = [...pickedTables.value]
  // Build column_filter: only include tables with partial column selection
  const cf: Record<string, string[]> = {}
  for (const tbl of pickedTables.value) {
    const cols = pickedColumns.value[tbl]
    const tblInfo = browseTables.value.find(t => t.name === tbl)
    if (cols && cols.length > 0 && tblInfo && cols.length < tblInfo.columns.length) {
      cf[tbl] = [...cols]
    }
  }
  form.value.column_filter = Object.keys(cf).length > 0 ? cf : undefined
  showPickTablesDialog.value = false
}

async function handleSync(src: DatabaseSourceItem & { _syncing?: boolean }) {
  src._syncing = true
  try {
    await syncDatabaseSource(src.id)
    ElMessage.success('同步任务已启动')
    src.status = 'syncing'
    if (!pollTimer) {
      pollTimer = setInterval(loadSources, 5000)
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e.message || '同步失败')
  } finally {
    src._syncing = false
  }
}

async function handleDelete(src: DatabaseSourceItem) {
  try {
    await ElMessageBox.confirm(`确定删除数据库源「${src.name}」？相关同步文档将被清除。`, '确认删除', { type: 'warning' })
  } catch { return }
  try {
    await deleteDatabaseSource(src.id)
    ElMessage.success('删除成功')
    await loadSources()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e.message || '删除失败')
  }
}

onMounted(() => {
  loadSources()
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<style scoped>
.db-sources-section {
  margin-bottom: 20px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  background: var(--bg-secondary, #fafafa);
  user-select: none;
  transition: background var(--duration-fast, 0.15s);
}

.section-header:hover {
  background: var(--bg-hover, #f0f0f0);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.expand-icon {
  transition: transform var(--duration-fast, 0.15s);
}

.expand-icon.rotated {
  transform: rotate(90deg);
}

.section-body {
  padding: 16px;
}

.source-actions {
  margin-bottom: 12px;
}

.empty-tip {
  text-align: center;
  color: #909399;
  padding: 20px 0;
  font-size: 13px;
}

.source-card {
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 12px 16px;
  margin-bottom: 10px;
  transition: border-color var(--duration-fast, 0.15s);
}

.source-card:hover {
  border-color: var(--primary-lighter, #409eff);
}

.source-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.source-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.db-icon {
  color: var(--primary, #409eff);
}

.source-name {
  font-weight: 600;
  font-size: 14px;
}

.source-card-actions {
  display: flex;
  gap: 4px;
}

.source-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12px;
  color: var(--text-muted, #909399);
}

.meta-tables {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-error {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--bg-danger, #fef0f0);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-danger, #f56c6c);
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.selected-tables {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.table-hint {
  font-size: 12px;
  color: #909399;
}

.pick-table-item {
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}

.pick-table-item:last-child {
  border-bottom: none;
}

.pick-columns {
  margin: 6px 0 4px 24px;
  padding: 8px 12px;
  background: var(--bg-secondary, #fafafa);
  border-radius: 4px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
</style>
