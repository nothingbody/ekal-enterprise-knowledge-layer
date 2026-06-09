<template>
  <div class="users-page">
    <div class="page-header">
      <h2>用户管理</h2>
      <span class="user-count">共 {{ total }} 位用户</span>
    </div>
    <div style="display: flex; gap: 12px; margin-bottom: 16px;">
      <el-input v-model="searchKeyword" placeholder="搜索用户名或邮箱" clearable style="width: 260px">
        <template #prefix><Search :size="14" :stroke-width="1.5" /></template>
      </el-input>
      <el-select v-model="filterRole" placeholder="全部角色" clearable style="width: 140px">
        <el-option label="管理员" value="admin" />
        <el-option label="普通用户" value="user" />
      </el-select>
    </div>

    <div v-loading="loading">
      <el-table v-if="filteredUsers.length" :data="filteredUsers" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" min-width="130" />
        <el-table-column prop="email" label="邮箱" min-width="200" />
        <el-table-column label="角色" width="130">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '正常' : '已禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后登录 IP" width="140">
          <template #default="{ row }">{{ row.last_login_ip || '—' }}</template>
        </el-table-column>
        <el-table-column label="最后登录" width="170">
          <template #default="{ row }">
            {{ row.last_login_at ? new Date(row.last_login_at).toLocaleString() : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="170">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="$router.push(`/admin/users/${row.id}/detail`)">详情</el-button>
            <el-button size="small" text type="primary" @click="openRoleDialog(row)">角色</el-button>
            <el-button size="small" text :type="row.is_active ? 'warning' : 'success'" @click="toggleActive(row)">
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button size="small" text type="primary" @click="openResetDialog(row)">重置密码</el-button>
            <el-button size="small" text type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !filteredUsers.length" :description="searchKeyword || filterRole ? '没有匹配的用户' : '暂无用户'" />
      <div v-if="total > pageSize" style="margin-top: 16px; display: flex; justify-content: flex-end;">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadUsers"
        />
      </div>
    </div>

    <!-- Role Dialog -->
    <el-dialog v-model="roleDialogVisible" title="修改角色" width="400" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="用户">{{ editingUser?.username }}</el-form-item>
        <el-form-item label="角色">
          <el-select v-model="newRole" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRole">确定</el-button>
      </template>
    </el-dialog>

    <!-- Reset Password Dialog -->
    <el-dialog v-model="resetDialogVisible" title="重置密码" width="400" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="用户">{{ editingUser?.username }}</el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="newPassword" type="password" show-password placeholder="至少 8 位，含字母和数字" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePassword">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from 'lucide-vue-next'
import request from '../../utils/request'

const users = ref<any[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
const loading = ref(false)
const saving = ref(false)

const searchKeyword = ref('')
const filterRole = ref('')

const filteredUsers = computed(() => {
  let list = users.value
  const kw = searchKeyword.value.trim().toLowerCase()
  if (kw) {
    list = list.filter((u: any) =>
      u.username.toLowerCase().includes(kw) || (u.email || '').toLowerCase().includes(kw)
    )
  }
  if (filterRole.value) {
    list = list.filter((u: any) => u.role === filterRole.value)
  }
  return list
})

const roleDialogVisible = ref(false)
const resetDialogVisible = ref(false)
const editingUser = ref<any>(null)
const newRole = ref('')
const newPassword = ref('')

async function loadUsers() {
  loading.value = true
  try {
    const res: any = await request.get('/users/', { params: { page: currentPage.value, page_size: pageSize } })
    users.value = res?.items || res
    total.value = res?.total || users.value.length
  } catch { /* interceptor handles */ }
  finally { loading.value = false }
}

onActivated(loadUsers)

function openRoleDialog(user: any) {
  editingUser.value = user
  newRole.value = user.role
  roleDialogVisible.value = true
}

async function saveRole() {
  saving.value = true
  try {
    await request.put(`/users/${editingUser.value.id}`, { role: newRole.value })
    ElMessage.success('角色已更新')
    roleDialogVisible.value = false
    await loadUsers()
  } catch { /* interceptor handles */ }
  finally { saving.value = false }
}

async function toggleActive(user: any) {
  const action = user.is_active ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(`确定${action}用户「${user.username}」？`, '确认', { type: 'warning' })
    await request.put(`/users/${user.id}`, { is_active: !user.is_active })
    ElMessage.success(`已${action}`)
    await loadUsers()
  } catch { /* cancelled or interceptor handles */ }
}

function openResetDialog(user: any) {
  editingUser.value = user
  newPassword.value = ''
  resetDialogVisible.value = true
}

async function savePassword() {
  if (newPassword.value.length < 8) {
    ElMessage.warning('密码长度不能少于 8 位')
    return
  }
  if (!/[A-Za-z]/.test(newPassword.value)) {
    ElMessage.warning('密码必须包含至少一个字母')
    return
  }
  if (!/\d/.test(newPassword.value)) {
    ElMessage.warning('密码必须包含至少一个数字')
    return
  }
  saving.value = true
  try {
    await request.post(`/users/${editingUser.value.id}/reset-password`, { new_password: newPassword.value })
    ElMessage.success('密码已重置')
    resetDialogVisible.value = false
  } catch { /* interceptor handles */ }
  finally { saving.value = false }
}

async function handleDelete(user: any) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${user.username}」？该用户的知识库、文档、对话记录和 API Key 将一并删除，此操作不可恢复。`, '确认删除', { type: 'error' })
    await request.delete(`/users/${user.id}`)
    ElMessage.success('用户已删除')
    await loadUsers()
  } catch { /* cancelled or interceptor handles */ }
}
</script>

<style scoped>
.users-page {
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

.user-count {
  font-size: 13px;
  color: var(--text-muted);
}
</style>
