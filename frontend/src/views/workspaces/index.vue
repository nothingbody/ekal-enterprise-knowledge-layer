<template>
  <div class="workspaces-page">
    <div class="page-header">
      <h2>工作空间</h2>
      <el-button type="primary" @click="openCreate">
        <PlusIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />创建空间
      </el-button>
    </div>

    <div v-loading="loading">
      <el-row :gutter="16" v-if="workspaces.length">
        <el-col :xs="24" :sm="12" :md="8" v-for="ws in workspaces" :key="ws.id">
          <el-card shadow="hover" class="ws-card" @click="$router.push(`/workspaces/${ws.id}`)">
            <template #header>
              <div class="ws-header">
                <span class="ws-name">{{ ws.name }}</span>
                <el-dropdown trigger="click" @click.stop>
                  <MoreHorizontalIcon :size="16" :stroke-width="1.5" class="more-icon" @click.stop />
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-if="ws.role === 'owner'" @click="openEditWs(ws)">编辑</el-dropdown-item>
                      <el-dropdown-item v-if="ws.role === 'owner' || ws.role === 'admin'" @click="openMembers(ws)">管理成员</el-dropdown-item>
                      <el-dropdown-item v-if="ws.role === 'owner'" @click="removeWs(ws.id)" class="danger-item">删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
            <p class="ws-desc">{{ ws.description || '暂无描述' }}</p>
            <div class="ws-meta">
              <span class="ws-meta-item"><UsersIcon :size="14" :stroke-width="1.5" /> {{ ws.member_count ?? 0 }} 位成员</span>
              <span class="ws-meta-item"><DatabaseIcon :size="14" :stroke-width="1.5" /> {{ ws.kb_count ?? 0 }} 个知识库</span>
              <el-tag :type="ws.role === 'owner' ? 'danger' : ws.role === 'admin' ? 'warning' : 'info'" size="small" class="ws-role-tag">{{ roleLabel(ws.role) }}</el-tag>
            </div>
          </el-card>
        </el-col>
      </el-row>
      <el-empty v-if="!loading && !workspaces.length" description="暂无工作空间，点击上方按钮创建" />
    </div>

    <!-- Edit Workspace Dialog -->
    <el-dialog v-model="showEdit" title="编辑工作空间" width="420px" :close-on-click-modal="false">
      <el-form ref="editFormRef" :model="editForm" :rules="wsFormRules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="editForm.name" placeholder="工作空间名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="editForm.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" @click="saveEditWs" :loading="editSaving">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showCreate" title="创建工作空间" width="420px">
      <el-form ref="createFormRef" :model="createForm" :rules="wsFormRules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="工作空间名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="createForm.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="handleCreate" :loading="creating">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showMembers" :title="`成员管理 - ${currentWs?.name || ''}`" width="560px">
      <div class="add-member-row">
        <el-input v-model="memberUsername" placeholder="输入用户名" style="flex: 1" />
        <el-select v-model="memberRole" style="width: 120px">
          <el-option label="管理员" value="admin" />
          <el-option label="成员" value="member" />
          <el-option label="只读" value="viewer" />
        </el-select>
        <el-button type="primary" @click="handleAddMember" :loading="addingMember">添加</el-button>
      </div>

      <el-table :data="members" stripe style="margin-top: 12px">
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'owner' ? 'danger' : row.role === 'admin' ? 'warning' : 'info'" size="small">
              {{ roleMap[row.role] || row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-select
              v-if="row.role !== 'owner' && canManageMembers"
              :model-value="row.role"
              size="small"
              style="width: 80px; margin-right: 4px;"
              @change="(val: string) => handleRoleChange(row, val)"
            >
              <el-option label="管理员" value="admin" />
              <el-option label="成员" value="member" />
              <el-option label="只读" value="viewer" />
            </el-select>
            <el-button v-if="row.role !== 'owner' && canManageMembers" link type="danger" size="small" @click="handleRemoveMember(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onActivated, computed } from 'vue'
import { Plus as PlusIcon, MoreHorizontal as MoreHorizontalIcon, Users as UsersIcon, Database as DatabaseIcon } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { listWorkspaces, createWorkspace, listMembers, addMember, deleteWorkspace, updateWorkspace, updateMemberRole, removeMember } from '../../api/workspaces'
import { roleMap, roleLabel } from '../../utils/format'
import { useWorkspaceStore } from '../../stores/workspace'

const workspaceStore = useWorkspaceStore()
const workspaces = ref<any[]>([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)

const createFormRef = ref<FormInstance>()
const createForm = reactive({ name: '', description: '' })

const showEdit = ref(false)
const editSaving = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({ name: '', description: '' })
const editingWsId = ref<number | null>(null)

const wsFormRules = {
  name: [
    { required: true, message: '请输入工作空间名称', trigger: 'blur' },
    { min: 1, max: 100, message: '名称长度不能超过 100 个字符', trigger: 'blur' },
  ],
  description: [
    { max: 500, message: '描述长度不能超过 500 个字符', trigger: 'blur' },
  ],
}

const showMembers = ref(false)
const currentWs = ref<any>(null)
const members = ref<any[]>([])
const memberUsername = ref('')
const memberRole = ref('member')
const addingMember = ref(false)

const canManageMembers = computed(() => currentWs.value?.role === 'owner' || currentWs.value?.role === 'admin')


async function loadWorkspaces() {
  loading.value = true
  try {
    const res: any = await listWorkspaces()
    workspaces.value = res
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.name = ''
  createForm.description = ''
  showCreate.value = true
}

async function handleCreate() {
  try { await createFormRef.value?.validate() } catch { return }
  creating.value = true
  try {
    await createWorkspace(createForm)
    ElMessage.success('创建成功')
    showCreate.value = false
    await loadWorkspaces()
  } finally {
    creating.value = false
  }
}

async function removeWs(id: number) {
  const ws = workspaces.value.find((w: any) => w.id === id)
  const name = ws?.name ? `「${ws.name}」` : '该工作空间'
  try {
    await ElMessageBox.confirm(`删除${name}将移除所有成员，确定？`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteWorkspace(id)
    ElMessage.success('删除成功')
    await loadWorkspaces()
  } catch { /* interceptor handles */ }
}

async function openMembers(ws: any) {
  currentWs.value = ws
  showMembers.value = true
  try {
    const res: any = await listMembers(ws.id)
    members.value = res
  } catch {
    ElMessage.error('加载成员列表失败')
  }
}

async function handleAddMember() {
  if (!memberUsername.value.trim()) {
    ElMessage.warning('请输入用户名')
    return
  }
  addingMember.value = true
  try {
    await addMember(currentWs.value.id, { username: memberUsername.value, role: memberRole.value })
    ElMessage.success('添加成功')
    memberUsername.value = ''
    const res: any = await listMembers(currentWs.value.id)
    members.value = res
  } finally {
    addingMember.value = false
  }
}

async function handleRoleChange(member: any, newRole: string) {
  try {
    await updateMemberRole(currentWs.value.id, member.id, newRole)
    member.role = newRole
    ElMessage.success('角色已更新')
  } catch { /* interceptor handles */ }
}

async function handleRemoveMember(member: any) {
  try {
    await ElMessageBox.confirm(`确定移除成员「${member.username}」？`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await removeMember(currentWs.value.id, member.id)
    ElMessage.success('已移除')
    const res: any = await listMembers(currentWs.value.id)
    members.value = res
  } catch { /* interceptor handles */ }
}

function openEditWs(ws: any) {
  editingWsId.value = ws.id
  editForm.name = ws.name
  editForm.description = ws.description || ''
  showEdit.value = true
}

async function saveEditWs() {
  try { await editFormRef.value?.validate() } catch { return }
  editSaving.value = true
  try {
    await updateWorkspace(editingWsId.value!, { name: editForm.name.trim(), description: editForm.description })
    ElMessage.success('已更新')
    showEdit.value = false
    await loadWorkspaces()
  } catch { /* interceptor handles */ }
  finally { editSaving.value = false }
}

onActivated(() => {
  workspaceStore.setCurrent(null)
  loadWorkspaces()
})
</script>

<style scoped>
.workspaces-page {
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

.ws-card {
  margin-bottom: 16px;
  border-radius: var(--radius-lg) !important;
  transition: all var(--duration-base) var(--ease-out);
  cursor: pointer;
}

.ws-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg) !important;
}

.ws-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ws-name {
  font-weight: 700;
  color: var(--text-primary);
}

.more-icon {
  cursor: pointer;
  color: var(--gray-400);
  transition: color var(--duration-fast) var(--ease-out);
}

.more-icon:hover {
  color: var(--text-secondary);
}

.ws-desc {
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.ws-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.ws-meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.ws-role-tag {
  margin-left: auto;
}

.add-member-row {
  display: flex;
  gap: 8px;
}

.danger-item {
  color: var(--danger) !important;
}
</style>
