<template>
  <div>
    <div class="page-header">
      <div>
        <h2>组织管理</h2>
        <p class="page-subtitle">管理企业组织与成员</p>
      </div>
      <el-button type="primary" round @click="openCreate"><el-icon><Plus /></el-icon>新建组织</el-button>
    </div>

    <el-card class="table-card">
      <el-table :data="orgs" v-loading="loading" style="width: 100%" empty-text="暂无组织数据">
        <el-table-column prop="id" label="ID" width="60" align="center" />
        <el-table-column label="组织" min-width="200">
          <template #default="{ row }">
            <div class="org-cell">
              <div class="org-avatar">{{ row.name?.[0] }}</div>
              <div>
                <div class="org-name"><router-link :to="`/organizations/${row.id}/detail`" style="color: inherit; text-decoration: none;">{{ row.name }}</router-link></div>
                <div class="org-desc">{{ row.description || '暂无描述' }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="成员" width="140" align="center">
          <template #default="{ row }">
            <div class="member-bar-cell">
              <div class="member-bar-track">
                <div class="member-bar-fill" :style="{ width: (row.max_members ? Math.min(row.member_count / row.max_members * 100, 100) : 0) + '%' }"></div>
              </div>
              <span class="member-count-text">{{ row.member_count }} / {{ row.max_members }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <div class="status-dot-cell">
              <span class="status-dot" :class="row.is_active ? 'online' : 'offline'"></span>
              <span>{{ row.is_active ? '正常' : '禁用' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }"><span class="text-secondary">{{ new Date(row.created_at).toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link size="small" @click="viewMembers(row)">成员</el-button>
            <el-divider direction="vertical" />
            <el-button link size="small" @click="editOrg(row)">编辑</el-button>
            <el-divider direction="vertical" />
            <el-button link size="small" type="danger" @click="deleteOrg(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > pageSize" class="table-pagination">
        <el-pagination
          layout="total, prev, pager, next"
          :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="loadOrgs"
        />
      </div>
    </el-card>

    <el-dialog v-model="formVisible" :title="editingOrg ? '编辑组织' : '新建组织'" width="480px" destroy-on-close>
      <el-form :model="form" label-width="80px" label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="请输入组织名称" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="3" placeholder="组织描述（选填）" /></el-form-item>
        <el-form-item label="成员上限"><el-input-number v-model="form.max_members" :min="1" :max="9999" style="width: 100%;" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false" round>取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitOrg" round>{{ editingOrg ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="membersVisible" :title="'成员 — ' + (currentOrg?.name || '')" size="520px">
      <el-table :data="members" size="small" style="width: 100%">
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="role" label="角色" width="90">
          <template #default="{ row }"><el-tag size="small" round effect="light">{{ row.role }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button link size="small" type="danger" @click="removeMember(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-member-bar">
        <el-select
          v-model="selectedUserForAdd"
          filterable
          remote
          reserve-keyword
          placeholder="搜索用户名或邮箱"
          :remote-method="searchUsersForAdd"
          :loading="userSearchLoading"
          clearable
          style="width: 260px"
          value-key="id"
        >
          <el-option
            v-for="u in userSearchResults"
            :key="u.id"
            :label="`${u.username} (${u.email})`"
            :value="u"
          />
        </el-select>
        <el-button type="primary" size="small" round :disabled="!selectedUserForAdd" @click="addMember">添加成员</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../utils/request'

const orgs = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)

const formVisible = ref(false)
const editingOrg = ref<any>(null)
const submitting = ref(false)
const form = ref({ name: '', description: '', max_members: 50 })

const membersVisible = ref(false)
const currentOrg = ref<any>(null)
const members = ref<any[]>([])
const selectedUserForAdd = ref<any>(null)
const userSearchResults = ref<any[]>([])
const userSearchLoading = ref(false)
let userSearchTimer: ReturnType<typeof setTimeout> | null = null

async function searchUsersForAdd(query: string) {
  if (!query || query.trim().length < 1) {
    userSearchResults.value = []
    return
  }
  if (userSearchTimer) clearTimeout(userSearchTimer)
  userSearchTimer = setTimeout(async () => {
    userSearchLoading.value = true
    try {
      const res: any = await request.get('/users/', {
        params: { search: query.trim(), page_size: 20 },
      })
      const list = res.items || []
      const memberIds = new Set(members.value.map((m: any) => m.user_id))
      userSearchResults.value = list.filter((u: any) => !memberIds.has(u.id))
    } catch { userSearchResults.value = [] }
    finally { userSearchLoading.value = false }
  }, 300)
}

async function loadOrgs() {
  loading.value = true
  try {
    const res: any = await request.get('/organizations/', { params: { page: page.value, page_size: pageSize } })
    orgs.value = res.items || []
    total.value = res.total || 0
  } finally { loading.value = false }
}

function openCreate() {
  editingOrg.value = null
  form.value = { name: '', description: '', max_members: 50 }
  formVisible.value = true
}

function editOrg(row: any) {
  editingOrg.value = row
  form.value = { name: row.name, description: row.description || '', max_members: row.max_members }
  formVisible.value = true
}

async function submitOrg() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入组织名称')
    return
  }
  submitting.value = true
  try {
    if (editingOrg.value) {
      await request.put(`/organizations/${editingOrg.value.id}`, form.value)
      ElMessage.success('已更新')
    } else {
      await request.post('/organizations/', form.value)
      ElMessage.success('已创建')
    }
    formVisible.value = false
    loadOrgs()
  } finally { submitting.value = false }
}

async function deleteOrg(row: any) {
  try { await ElMessageBox.confirm(`确定删除「${row.name}」？`, '确认', { type: 'error' }) } catch { return }
  try {
    await request.delete(`/organizations/${row.id}`)
    ElMessage.success('已删除')
    loadOrgs()
  } catch { /* interceptor handles */ }
}

async function viewMembers(row: any) {
  currentOrg.value = row
  membersVisible.value = true
  const res: any = await request.get(`/organizations/${row.id}/members`)
  members.value = res || []
}

async function addMember() {
  const user = selectedUserForAdd.value
  if (!user?.id || !currentOrg.value) return
  try {
    await request.post(`/organizations/${currentOrg.value.id}/members`, { user_id: user.id, role: 'member' })
    ElMessage.success('已添加')
    selectedUserForAdd.value = null
    userSearchResults.value = []
    viewMembers(currentOrg.value)
    loadOrgs()
  } catch { /* interceptor handles */ }
}

async function removeMember(row: any) {
  try { await ElMessageBox.confirm(`确定移除「${row.username}」？`, '确认') } catch { return }
  try {
    await request.delete(`/organizations/${currentOrg.value.id}/members/${row.user_id}`)
    ElMessage.success('已移除')
    viewMembers(currentOrg.value)
    loadOrgs()
  } catch { /* interceptor handles */ }
}

onMounted(loadOrgs)
</script>

<style scoped>
.page-subtitle { font-size: 14px; color: var(--text-tertiary); margin-top: 4px; }
.table-card :deep(.el-card__body) { padding: 0 !important; }

.org-cell { display: flex; align-items: center; gap: 12px; }

.org-avatar {
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: linear-gradient(135deg, #FEF3C7, #FDE68A);
  color: #D97706;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
  flex-shrink: 0;
}

.org-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.org-desc { font-size: 12px; color: var(--text-tertiary); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.member-bar-cell { display: flex; flex-direction: column; align-items: center; gap: 4px; }

.member-bar-track {
  width: 80px;
  height: 4px;
  background: #F1F5F9;
  border-radius: 2px;
  overflow: hidden;
}

.member-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #2B5AED, #5B8DEF);
  border-radius: 2px;
  transition: width 0.3s;
}

.member-count-text { font-size: 12px; color: var(--text-tertiary); }

.status-dot-cell { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; }
.status-dot.online { background: #10B981; box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15); }
.status-dot.offline { background: #EF4444; box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1); }

.text-secondary { color: var(--text-secondary); font-size: 13px; }
.table-pagination { display: flex; justify-content: flex-end; padding: 16px 20px; border-top: 1px solid var(--border-light); }

.add-member-bar {
  margin-top: 20px;
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
