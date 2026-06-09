<template>
  <div class="workspaces-page">
    <div class="page-header">
      <div>
        <h2>工作空间管理</h2>
        <p class="page-subtitle">管理所有工作空间及其成员</p>
      </div>
    </div>

    <el-card class="table-card" shadow="never" v-loading="loading">
      <div class="table-toolbar">
        <el-input v-model="search" placeholder="搜索工作空间..." clearable size="small" style="width: 240px" @clear="() => { page = 1; loadData() }" @keyup.enter="() => { page = 1; loadData() }" />
        <el-button size="small" @click="loadData"><el-icon><Refresh /></el-icon>刷新</el-button>
      </div>

      <el-table :data="items" stripe size="default" empty-text="暂无工作空间">
        <el-table-column prop="name" label="名称" min-width="180">
          <template #default="{ row }">
            <div style="font-weight: 600">{{ row.name }}</div>
            <div v-if="row.description" style="font-size: 12px; color: var(--el-text-color-secondary)">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="所有者" width="120">
          <template #default="{ row }">{{ row.owner_username || row.owner_id }}</template>
        </el-table-column>
        <el-table-column label="成员数" width="80" align="center">
          <template #default="{ row }">{{ row.member_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="组织" width="80" align="center">
          <template #default="{ row }">{{ row.org_id || '—' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click.stop="showMembers(row)">成员</el-button>
            <el-button link size="small" type="danger" @click.stop="deleteWs(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > 20" style="margin-top: 12px; display: flex; justify-content: flex-end;">
        <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" size="small" @current-change="loadData" />
      </div>
    </el-card>

    <el-dialog v-model="memberDialogVisible" :title="`${selectedWs?.name} — 成员`" width="500px">
      <el-table :data="members" size="small" v-loading="membersLoading">
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="email" label="邮箱" min-width="160" />
        <el-table-column prop="role" label="角色" width="80">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" round>{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link size="small" type="danger" @click="removeMember(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../utils/request'

const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const search = ref('')

const memberDialogVisible = ref(false)
const selectedWs = ref<any>(null)
const members = ref<any[]>([])
const membersLoading = ref(false)

async function loadData() {
  loading.value = true
  try {
    const params: Record<string, any> = { page: page.value, page_size: 20 }
    if (search.value) params.search = search.value
    const res: any = await request.get('/workspaces', { params })
    items.value = res?.items || []
    total.value = res?.total || 0
  } catch { /* */ }
  finally { loading.value = false }
}

async function showMembers(ws: any) {
  selectedWs.value = ws
  memberDialogVisible.value = true
  membersLoading.value = true
  try {
    members.value = (await request.get(`/workspaces/${ws.id}/members`)) as any[] || []
  } catch { members.value = [] }
  finally { membersLoading.value = false }
}

async function removeMember(member: any) {
  if (!selectedWs.value) return
  try { await ElMessageBox.confirm(`移除成员「${member.username}」？`, '确认', { type: 'warning' }) } catch { return }
  try {
    await request.delete(`/workspaces/${selectedWs.value.id}/members/${member.user_id}`)
    ElMessage.success('已移除')
    showMembers(selectedWs.value)
  } catch { /* */ }
}

async function deleteWs(ws: any) {
  try { await ElMessageBox.confirm(`确定删除工作空间「${ws.name}」？`, '确认', { type: 'warning' }) } catch { return }
  try {
    await request.delete(`/workspaces/${ws.id}`)
    ElMessage.success('已删除')
    await loadData()
  } catch { /* */ }
}

onMounted(loadData)
</script>

<style scoped>
.workspaces-page { max-width: 1200px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-header h2 { margin: 0 0 4px; }
.page-subtitle { font-size: 13px; color: var(--el-text-color-secondary); margin: 0; }
.table-card { margin-bottom: 20px; }
.table-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
