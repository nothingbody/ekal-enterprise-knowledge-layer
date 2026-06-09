<template>
  <div>
    <div class="page-header">
      <div>
        <h2>审计日志</h2>
        <p class="page-subtitle">系统操作记录追踪</p>
      </div>
      <el-button size="small" @click="exportCSV" :disabled="!logs.length">
        <el-icon><Download /></el-icon>导出 CSV
      </el-button>
    </div>

    <el-card class="table-card">
      <div class="table-toolbar">
        <div class="toolbar-left">
          <el-input v-model="searchQuery" placeholder="搜索用户名、详情..." clearable style="width: 200px"
            @keydown.enter="() => { page = 1; loadLogs() }" @clear="() => { page = 1; loadLogs() }">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="actionFilter" placeholder="操作类型" clearable style="width: 140px" @change="() => { page = 1; loadLogs() }">
            <el-option label="登录成功" value="login_success" />
            <el-option label="登录失败" value="login_failed" />
            <el-option label="创建" value="create" />
            <el-option label="更新" value="update" />
            <el-option label="删除" value="delete" />
            <el-option label="更新设置" value="update_settings" />
            <el-option label="重置密码" value="reset_password" />
          </el-select>
          <el-select v-model="resourceFilter" placeholder="资源类型" clearable style="width: 130px" @change="() => { page = 1; loadLogs() }">
            <el-option label="认证" value="auth" />
            <el-option label="用户" value="users" />
            <el-option label="组织" value="organizations" />
            <el-option label="设备" value="devices" />
            <el-option label="模型" value="models" />
            <el-option label="技能" value="skills" />
            <el-option label="通知" value="notifications" />
            <el-option label="内容" value="site" />
          </el-select>
          <el-date-picker v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始日期"
            end-placeholder="结束日期" style="width: 260px" value-format="YYYY-MM-DD" @change="() => { page = 1; loadLogs() }" clearable />
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
          <el-tag v-if="total > 0" type="info" effect="plain" round>共 {{ total }} 条</el-tag>
          <el-button @click="loadLogs" :loading="loading" round>
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </div>
      </div>

      <el-table :data="logs" v-loading="loading" style="width: 100%" empty-text="暂无审计记录" :row-class-name="rowClassName">
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column label="操作人" width="130">
          <template #default="{ row }">
            <el-button v-if="row.user_id" link type="primary" size="small" @click="$router.push(`/users/${row.user_id}/detail`)">{{ row.username || '-' }}</el-button>
            <span v-else class="text-primary-bold">{{ row.username || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-tag :type="actionTag(row.action)" size="small" effect="light" round>{{ actionLabel(row.action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="资源" width="150">
          <template #default="{ row }">
            <div class="resource-cell">
              <span class="resource-type">{{ resourceTypeLabel(row.resource_type) }}</span>
              <code v-if="row.resource_id" class="resource-id">#{{ row.resource_id }}</code>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="240">
          <template #default="{ row }">
            <el-tooltip v-if="row.detail && row.detail.length > 50" :content="row.detail" placement="top" :show-after="500">
              <span class="detail-text">{{ row.detail }}</span>
            </el-tooltip>
            <span v-else class="detail-text">{{ row.detail || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="IP" width="130">
          <template #default="{ row }">
            <code class="ip-text">{{ row.ip_address || '-' }}</code>
          </template>
        </el-table-column>
        <el-table-column label="状态码" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.status_code" :type="row.status_code >= 400 ? 'danger' : row.status_code >= 300 ? 'warning' : 'success'" size="small" effect="plain" round>{{ row.status_code }}</el-tag>
            <span v-else class="text-secondary">-</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            <el-tooltip :content="row.created_at ? new Date(row.created_at).toLocaleString() : ''" placement="top">
              <span class="text-secondary">{{ formatRelativeTime(row.created_at) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > pageSize" class="table-pagination">
        <el-pagination
          layout="total, sizes, prev, pager, next"
          :total="total" :page-size="pageSize" :page-sizes="[20, 50, 100]"
          v-model:current-page="page" @current-change="loadLogs" @size-change="onPageSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import request from '../utils/request'

const logs = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
let pageSize = 20
const total = ref(0)
const actionFilter = ref('')
const resourceFilter = ref('')
const searchQuery = ref('')
const dateRange = ref<[string, string] | null>(null)

const resourceTypeLabels: Record<string, string> = {
  users: '用户', devices: '设备', models: '模型', organizations: '组织',
  auth: '认证', workspaces: '工作空间', skills: '技能',
  notifications: '通知', site: '内容', settings: '设置', releases: '版本',
}
function resourceTypeLabel(t: string) { return resourceTypeLabels[t] || t || '-' }

const actionLabels: Record<string, string> = {
  create: '创建', update: '更新', delete: '删除',
  login_success: '登录成功', login_failed: '登录失败',
  create_heartbeat: '心跳', update_read: '已读',
  create_members: '添加成员', delete_members: '移除成员',
  update_settings: '更新设置', delete_org: '删除组织',
  admin_create_model: '创建模型', admin_update_model: '更新模型', admin_delete_model: '删除模型',
  reset_password: '重置密码', update_user: '更新用户', delete_user: '删除用户',
  update_role: '修改角色', deactivate_device: '停用设备',
  create_notification: '发送通知', delete_notification: '删除通知',
  approve_skill: '通过技能', reject_skill: '拒绝技能',
  create_org: '创建组织', update_org: '更新组织',
  create_release: '发布版本', delete_release: '删除版本',
}
function actionLabel(a: string) { return actionLabels[a] || a }

function actionTag(a: string) {
  if (a === 'login_success') return 'success'
  if (a === 'login_failed') return 'danger'
  if (a?.startsWith('create')) return 'success'
  if (a?.startsWith('delete')) return 'danger'
  if (a?.startsWith('update') || a?.startsWith('reset') || a?.startsWith('approve')) return 'warning'
  return 'info'
}

function rowClassName({ row }: { row: any }) {
  if (row.action === 'login_failed') return 'row-danger'
  if (row.status_code && row.status_code >= 400) return 'row-warn'
  return ''
}

function formatRelativeTime(dateStr: string) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} 天前`
  return d.toLocaleDateString()
}

function onPageSizeChange(size: number) {
  pageSize = size
  page.value = 1
  loadLogs()
}

async function loadLogs() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: page.value,
      page_size: pageSize,
      action: actionFilter.value || undefined,
      search: searchQuery.value || undefined,
      resource_type: resourceFilter.value || undefined,
    }
    if (dateRange.value?.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    const res: any = await request.get('/admin/audit-logs', { params })
    logs.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

function exportCSV() {
  if (!logs.value.length) return
  const header = 'ID,时间,操作人,操作,资源类型,资源ID,详情,IP,状态码\n'
  const rows = logs.value.map(l =>
    `${l.id},"${l.created_at || ''}","${l.username || ''}","${actionLabel(l.action)}","${resourceTypeLabel(l.resource_type)}","${l.resource_id || ''}","${(l.detail || '').replace(/"/g, '""')}","${l.ip_address || ''}",${l.status_code || ''}`
  ).join('\n')
  const blob = new Blob(['\ufeff' + header + rows], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `audit_logs_${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(loadLogs)
</script>

<style scoped>
.page-subtitle { font-size: 14px; color: var(--text-tertiary); margin-top: 4px; }
.table-card :deep(.el-card__body) { padding: 0 !important; }

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-light);
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-left { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }

.text-primary-bold { font-weight: 600; color: var(--text-primary); }
.text-secondary { color: var(--text-secondary); font-size: 13px; }

.resource-cell { display: flex; align-items: center; gap: 6px; }

.resource-type { font-size: 13px; color: var(--text-secondary); }

.resource-id {
  font-size: 11px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--text-tertiary);
  background: #F8FAFC;
  padding: 1px 5px;
  border-radius: 3px;
}

.ip-text {
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--text-tertiary);
}

.detail-text {
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 320px;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.row-danger) { background-color: #FFF5F5 !important; }
:deep(.row-warn) { background-color: #FFFBEB !important; }

.table-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid var(--border-light);
}
</style>
