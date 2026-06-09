<template>
  <div>
    <div class="page-header">
      <div>
        <h2>通知管理</h2>
        <p class="page-subtitle">管理系统通知与团队消息</p>
      </div>
      <el-button type="primary" @click="showSendDialog = true" round>
        <el-icon><Plus /></el-icon>发送通知
      </el-button>
    </div>

    <el-card class="table-card">
      <div class="table-toolbar">
        <div class="toolbar-left">
          <el-select v-model="typeFilter" placeholder="通知类型" clearable style="width: 140px" @change="() => { page = 1; loadNotifications() }">
            <el-option label="系统广播" value="system" />
            <el-option label="团队通知" value="team" />
            <el-option label="个人通知" value="personal" />
          </el-select>
          <el-tag v-if="total > 0" type="info" effect="plain" round>共 {{ total }} 条</el-tag>
        </div>
        <el-button @click="loadNotifications" :loading="loading" round>
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>

      <el-table :data="notifications" v-loading="loading" style="width: 100%" empty-text="暂无通知">
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column label="类型" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.type)" size="small" effect="light" round>{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="priorityTag(row.priority)" size="small" effect="plain" round>{{ priorityLabel(row.priority) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="180">
          <template #default="{ row }">
            <span class="notif-title">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="内容" min-width="200">
          <template #default="{ row }">
            <span class="notif-content">{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发送人" width="110">
          <template #default="{ row }">
            <span class="text-primary-bold">{{ row.sender_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已读" width="80" align="center">
          <template #default="{ row }">
            <span class="read-count">{{ row.read_count ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发送时间" width="170">
          <template #default="{ row }">
            <span class="text-secondary">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" type="danger" :loading="deleting === row.id" @click="deleteNotif(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > pageSize" class="table-pagination">
        <el-pagination
          layout="total, prev, pager, next"
          :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="loadNotifications"
        />
      </div>
    </el-card>

    <el-dialog v-model="showSendDialog" title="发送通知" width="560px" :close-on-click-modal="false">
      <el-form :model="sendForm" label-position="top">
        <el-form-item label="通知类型">
          <el-radio-group v-model="sendForm.type">
            <el-radio-button value="system">系统广播</el-radio-button>
            <el-radio-button value="team">团队通知</el-radio-button>
            <el-radio-button value="personal">个人通知</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="优先级">
          <el-select v-model="sendForm.priority" style="width: 100%">
            <el-option label="低" value="low" />
            <el-option label="普通" value="normal" />
            <el-option label="高" value="high" />
            <el-option label="紧急" value="urgent" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="sendForm.type === 'team'" label="组织 ID">
          <el-input-number v-model="sendForm.org_id" :min="1" style="width: 100%" />
        </el-form-item>

        <el-form-item v-if="sendForm.type === 'personal'" label="目标用户 ID">
          <el-input-number v-model="sendForm.target_user_id" :min="1" style="width: 100%" />
        </el-form-item>

        <el-form-item label="标题">
          <el-input v-model="sendForm.title" placeholder="通知标题" maxlength="200" show-word-limit />
        </el-form-item>

        <el-form-item label="内容">
          <el-input v-model="sendForm.content" type="textarea" :rows="4" placeholder="通知内容" maxlength="2000" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSendDialog = false" round>取消</el-button>
        <el-button type="primary" :loading="sending" @click="handleSend" round>发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../utils/request'

const notifications = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const typeFilter = ref('')
const showSendDialog = ref(false)
const sending = ref(false)
const deleting = ref<number | null>(null)

const sendForm = reactive({
  type: 'system',
  priority: 'normal',
  title: '',
  content: '',
  org_id: null as number | null,
  target_user_id: null as number | null,
})

function typeLabel(t: string) {
  return { system: '系统广播', team: '团队', personal: '个人' }[t] || t
}

function typeTag(t: string) {
  return { system: 'primary', team: 'success', personal: 'warning' }[t] || 'info'
}

function priorityLabel(p: string) {
  return { low: '低', normal: '普通', high: '高', urgent: '紧急' }[p] || p
}

function priorityTag(p: string) {
  return { low: 'info', normal: '', high: 'warning', urgent: 'danger' }[p] || 'info'
}

async function loadNotifications() {
  loading.value = true
  try {
    const res: any = await request.get('/notifications/admin/list', {
      params: { page: page.value, page_size: pageSize, type: typeFilter.value || undefined },
    })
    notifications.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

async function handleSend() {
  if (!sendForm.title || !sendForm.content) {
    ElMessage.warning('请填写标题和内容')
    return
  }
  if (sendForm.type === 'team' && !sendForm.org_id) {
    ElMessage.warning('团队通知需要指定组织 ID')
    return
  }
  if (sendForm.type === 'personal' && !sendForm.target_user_id) {
    ElMessage.warning('个人通知需要指定目标用户 ID')
    return
  }
  sending.value = true
  try {
    await request.post('/notifications/send', {
      type: sendForm.type,
      priority: sendForm.priority,
      title: sendForm.title,
      content: sendForm.content,
      org_id: sendForm.type === 'team' ? sendForm.org_id : undefined,
      target_user_id: sendForm.type === 'personal' ? sendForm.target_user_id : undefined,
    })
    ElMessage.success('通知已发送')
    showSendDialog.value = false
    sendForm.type = 'system'
    sendForm.priority = 'normal'
    sendForm.title = ''
    sendForm.content = ''
    sendForm.org_id = null
    sendForm.target_user_id = null
    loadNotifications()
  } finally {
    sending.value = false
  }
}

async function deleteNotif(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除通知「${row.title}」？`, '确认', { type: 'warning' })
  } catch { return }
  deleting.value = row.id
  try {
    await request.delete(`/notifications/admin/${row.id}`)
    ElMessage.success('已删除')
    loadNotifications()
  } finally {
    deleting.value = null
  }
}

onMounted(loadNotifications)
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
.text-primary-bold { font-weight: 600; color: var(--text-primary); }
.text-secondary { color: var(--text-secondary); font-size: 13px; }

.notif-title {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 13px;
}

.notif-content {
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 240px;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.read-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.table-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid var(--border-light);
}
</style>
