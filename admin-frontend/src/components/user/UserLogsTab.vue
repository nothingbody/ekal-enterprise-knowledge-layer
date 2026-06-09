<template>
  <div>
    <el-card class="section-card" shadow="never" v-loading="auditLoading">
      <template #header><span class="section-title">服务器审计日志 ({{ auditTotal }})</span></template>
      <el-table v-if="auditLogs.length" :data="auditLogs" stripe size="small">
        <el-table-column prop="action" label="操作" width="140"><template #default="{ row }"><el-tag size="small" effect="plain" round>{{ actionLabel(row.action) }}</el-tag></template></el-table-column>
        <el-table-column label="资源" width="100"><template #default="{ row }">{{ resourceLabel(row.resource_type) }}</template></el-table-column>
        <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
        <el-table-column label="IP" width="130"><template #default="{ row }"><code style="font-size: 12px; color: var(--text-tertiary);">{{ row.ip_address || '—' }}</code></template></el-table-column>
        <el-table-column label="时间" width="170"><template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}</template></el-table-column>
      </el-table>
      <el-empty v-else description="暂无审计日志" :image-size="60" />
      <div v-if="auditTotal > 20" style="margin-top: 12px; display: flex; justify-content: flex-end;">
        <el-pagination v-model:current-page="auditPage" :page-size="20" :total="auditTotal" layout="total, prev, pager, next" size="small" @current-change="loadAuditLogs" />
      </div>
    </el-card>

    <el-card class="section-card" shadow="never" v-loading="opLogsLoading">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="section-title">客户端操作日志 ({{ opLogsTotal }})</span>
          <el-select v-model="opLogsActionFilter" placeholder="按操作过滤" size="small" clearable style="width: 160px" @change="loadOpLogs">
            <el-option label="全部" value="" /><el-option label="对话" value="chat" /><el-option label="检索" value="search" /><el-option label="登录" value="login" />
          </el-select>
        </div>
      </template>
      <el-table v-if="opLogs.length" :data="opLogs" stripe size="small">
        <el-table-column prop="action" label="操作" width="120"><template #default="{ row }"><el-tag size="small" effect="plain" round>{{ actionLabel(row.action) }}</el-tag></template></el-table-column>
        <el-table-column label="资源" width="100"><template #default="{ row }">{{ resourceLabel(row.resource_type) }}</template></el-table-column>
        <el-table-column prop="detail" label="详情" min-width="180" show-overflow-tooltip />
        <el-table-column label="Token" width="130"><template #default="{ row }"><span v-if="row.total_tokens" style="font-size:12px;font-family:monospace">{{ row.total_tokens.toLocaleString() }}</span><span v-else style="color:var(--text-tertiary)">—</span></template></el-table-column>
        <el-table-column label="延迟" width="80"><template #default="{ row }"><span v-if="row.latency_ms" style="font-size:12px">{{ row.latency_ms }}ms</span><span v-else style="color:var(--text-tertiary)">—</span></template></el-table-column>
        <el-table-column label="时间" width="170"><template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}</template></el-table-column>
      </el-table>
      <el-empty v-else description="暂无客户端操作日志" :image-size="60" />
      <div v-if="opLogsTotal > 20" style="margin-top: 12px; display: flex; justify-content: flex-end;">
        <el-pagination v-model:current-page="opLogsPage" :page-size="20" :total="opLogsTotal" layout="total, prev, pager, next" size="small" @current-change="loadOpLogs" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import request from '../../utils/request'

const props = defineProps<{ userId: number }>()

const auditLogs = ref<any[]>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditLoading = ref(false)

const opLogs = ref<any[]>([])
const opLogsTotal = ref(0)
const opLogsPage = ref(1)
const opLogsLoading = ref(false)
const opLogsActionFilter = ref('')

const actionLabels: Record<string, string> = {
  create: '创建', update: '更新', delete: '删除', login_success: '登录成功',
  login_failed: '登录失败', create_heartbeat: '心跳', update_read: '已读',
  create_members: '添加成员', delete_members: '移除成员',
}
function actionLabel(a: string) { return actionLabels[a] || a }

const resourceLabels: Record<string, string> = {
  users: '用户', devices: '设备', models: '模型', organizations: '组织',
  auth: '认证', workspaces: '工作空间', skills: '技能', notifications: '通知',
  site: '内容', chat: '对话', knowledge_bases: '知识库',
}
function resourceLabel(r: string) { return resourceLabels[r] || r || '—' }

async function loadAuditLogs() {
  auditLoading.value = true
  try {
    const res: any = await request.get(`/users/${props.userId}/audit-logs`, { params: { page: auditPage.value, page_size: 20 } })
    auditLogs.value = res?.items || []; auditTotal.value = res?.total || 0
  } catch {} finally { auditLoading.value = false }
}

async function loadOpLogs() {
  opLogsLoading.value = true
  try {
    const params: Record<string, any> = { page: opLogsPage.value, page_size: 20 }
    if (opLogsActionFilter.value) params.action = opLogsActionFilter.value
    const res: any = await request.get(`/users/${props.userId}/operation-logs`, { params })
    opLogs.value = res?.items || []; opLogsTotal.value = res?.total || 0
  } catch {} finally { opLogsLoading.value = false }
}

defineExpose({ auditTotal, opLogsTotal, loadAuditLogs, loadOpLogs })

onMounted(() => { loadAuditLogs(); loadOpLogs() })
</script>

<style scoped>
.section-card { margin-bottom: 20px; }
.section-title { font-weight: 600; font-size: 15px; }
</style>
