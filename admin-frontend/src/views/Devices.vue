<template>
  <div>
    <div class="page-header">
      <div>
        <h2>设备管理</h2>
        <p class="page-subtitle">监控所有已注册的客户端设备</p>
      </div>
      <el-button @click="loadDevices" :loading="loading" round>
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <el-card class="table-card">
      <div class="table-toolbar">
        <div class="toolbar-left">
          <el-checkbox v-model="onlineOnly" label="仅显示在线" @change="loadDevices" />
          <el-input v-model="searchText" placeholder="搜索设备..." clearable style="width: 180px" @keydown.enter="loadDevices" @clear="loadDevices">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-tag v-if="total > 0" type="info" effect="plain" round>共 {{ total }} 台设备</el-tag>
        </div>
      </div>

      <el-table :data="devices" v-loading="loading" style="width: 100%" empty-text="暂无设备数据">
        <el-table-column label="设备ID" min-width="180">
          <template #default="{ row }">
            <code class="device-id">{{ row.device_id }}</code>
          </template>
        </el-table-column>
        <el-table-column label="用户" width="120">
          <template #default="{ row }">
            <el-button v-if="row.user_id" link type="primary" @click="$router.push(`/users/${row.user_id}/detail`)">{{ row.username || '-' }}</el-button>
            <span v-else class="text-primary-bold">{{ row.username || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="device_name" label="设备名" min-width="140" />
        <el-table-column label="系统" min-width="140">
          <template #default="{ row }">
            <span class="text-secondary">{{ row.os_info || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="MAC 地址" width="150">
          <template #default="{ row }"><code v-if="row.mac_address" style="font-size:12px;color:var(--text-tertiary)">{{ row.mac_address }}</code><span v-else>—</span></template>
        </el-table-column>
        <el-table-column label="版本" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.app_version" size="small" effect="plain" round>{{ row.app_version }}</el-tag>
            <span v-else class="text-secondary">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <div class="status-badge" :class="row.is_online ? 'online' : 'offline'">
              <span class="status-badge-dot"></span>
              {{ row.is_online ? '在线' : '离线' }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="最后心跳" width="170">
          <template #default="{ row }">
            <span class="text-secondary">{{ row.last_heartbeat ? new Date(row.last_heartbeat).toLocaleString() : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link size="small" type="danger" @click="deactivateDevice(row)">停用</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > pageSize" class="table-pagination">
        <el-pagination
          layout="total, prev, pager, next"
          :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="loadDevices"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../utils/request'

const devices = ref<any[]>([])
const loading = ref(false)
const onlineOnly = ref(false)
const searchText = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)

async function loadDevices() {
  loading.value = true
  try {
    const res: any = await request.get('/devices/', {
      params: { page: page.value, page_size: pageSize, online_only: onlineOnly.value || undefined, search: searchText.value.trim() || undefined },
    })
    devices.value = res.items || []
    total.value = res.total || 0
  } finally { loading.value = false }
}

async function deactivateDevice(row: any) {
  try {
    await ElMessageBox.confirm(`确定停用设备「${row.device_name || row.device_id}」？`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await request.put(`/devices/${row.id}/deactivate`)
    ElMessage.success('设备已停用')
    loadDevices()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

onMounted(loadDevices)
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
}

.toolbar-left { display: flex; gap: 12px; align-items: center; }

.device-id {
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--text-secondary);
  background: #F8FAFC;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-light);
}

.text-primary-bold { font-weight: 600; color: var(--text-primary); }
.text-secondary { color: var(--text-secondary); font-size: 13px; }

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.status-badge.online {
  background: #D1FAE5;
  color: #065F46;
}

.status-badge.offline {
  background: #F1F5F9;
  color: #64748B;
}

.status-badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-badge.online .status-badge-dot { background: #10B981; }
.status-badge.offline .status-badge-dot { background: #94A3B8; }

.table-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid var(--border-light);
}
</style>
