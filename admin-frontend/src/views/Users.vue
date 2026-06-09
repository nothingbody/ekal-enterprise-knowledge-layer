<template>
  <div class="users-page">
    <div class="page-header">
      <div>
        <h2>用户管理</h2>
        <p class="page-subtitle">管理平台所有注册用户</p>
      </div>
    </div>

    <el-card class="table-card">
      <div class="table-toolbar">
        <div class="toolbar-left">
          <el-input
            v-model="search"
            placeholder="搜索用户名或邮箱..."
            clearable
            style="width: 260px"
            @keydown.enter="loadUsers(true)"
            @clear="loadUsers(true)"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="roleFilter" placeholder="角色筛选" clearable style="width: 150px" @change="loadUsers(true)">
            <el-option label="超级管理员" value="super_admin" />
            <el-option label="管理员" value="admin" />
            <el-option label="组织管理员" value="org_admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
          <el-select v-model="orgFilter" placeholder="组织筛选" clearable style="width: 160px" @change="loadUsers(true)">
            <el-option label="全部组织" value="" />
            <el-option v-for="o in orgs" :key="o.id" :label="o.name" :value="o.id" />
          </el-select>
        </div>
        <el-button @click="loadUsers" :loading="loading" round>
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>

      <div v-if="selectedUsers.length" class="batch-bar">
        <span>已选 {{ selectedUsers.length }} 个用户</span>
        <el-button size="small" @click="batchToggleActive(true)" :loading="batchLoading">批量启用</el-button>
        <el-button size="small" @click="batchToggleActive(false)" :loading="batchLoading">批量禁用</el-button>
        <el-button size="small" @click="selectedUsers = []">取消选择</el-button>
      </div>

      <el-table :data="users" v-loading="loading" style="width: 100%" :empty-text="search || roleFilter || orgFilter ? '未找到匹配用户' : '暂无用户数据'" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="id" label="ID" width="60" align="center" />
        <el-table-column label="用户" min-width="200">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-cell-avatar">{{ row.username?.[0]?.toUpperCase() }}</div>
              <div>
                <div class="user-cell-name">{{ row.username }}</div>
                <div class="user-cell-email">{{ row.email }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="130" align="center">
          <template #default="{ row }">
            <el-tag :type="roleTag(row.role)" size="small" effect="light" round>{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="方案" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="({ trial: 'info', basic: '', pro: 'warning', enterprise: 'success' } as Record<string, string>)[row.plan] || 'info'" size="small" effect="light" round>
              {{ ({ trial: '试用', basic: '基础', pro: '专业', enterprise: '企业' } as Record<string, string>)[row.plan] || row.plan || '试用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="组织" width="90" align="center">
          <template #default="{ row }">
            <el-button v-if="row.org_id" link type="primary" size="small" @click.stop="$router.push(`/organizations/${row.org_id}/detail`)">{{ row.org_id }}</el-button>
            <span v-else style="color:var(--text-tertiary)">—</span>
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
        <el-table-column label="设备数" width="80" prop="device_count" align="center" />
        <el-table-column label="最后登录" width="170">
          <template #default="{ row }">
            <span class="text-secondary">{{ row.last_login_at ? new Date(row.last_login_at).toLocaleString() : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="170">
          <template #default="{ row }">
            <span class="text-secondary">{{ new Date(row.created_at).toLocaleString() }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right" align="center">
          <template #default="{ row }">
            <div class="action-group">
              <el-button link size="small" type="primary" @click="$router.push(`/users/${row.id}/detail`)">详情</el-button>
              <el-divider direction="vertical" />
              <el-button link size="small" :loading="actionLoading === row.id" @click="toggleActive(row)">
                {{ row.is_active ? '禁用' : '启用' }}
              </el-button>
              <el-divider direction="vertical" />
              <el-button link size="small" @click="changeRole(row)">改角色</el-button>
              <el-divider direction="vertical" />
              <el-button link size="small" @click="changePwd(row)">修改密码</el-button>
              <el-divider direction="vertical" />
              <el-button link size="small" type="danger" :loading="actionLoading === row.id" @click="deleteUser(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > pageSize" class="table-pagination">
        <el-pagination
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          v-model:current-page="page"
          @current-change="loadUsers"
        />
      </div>
    </el-card>

    <!-- 修改角色对话框 -->
    <el-dialog v-model="roleDialogVisible" title="修改角色" width="420px" destroy-on-close>
      <div v-if="roleEditingUser" style="margin-bottom: 16px;">
        <span style="color: var(--text-secondary);">用户：</span>
        <strong>{{ roleEditingUser.username }}</strong>
      </div>
      <el-select v-model="roleNewValue" style="width: 100%" size="large">
        <el-option value="super_admin">
          <div class="role-option">
            <el-tag type="danger" size="small" effect="dark" round>超级管理员</el-tag>
            <span class="role-option-desc">拥有所有权限，可管理系统设置</span>
          </div>
        </el-option>
        <el-option value="admin">
          <div class="role-option">
            <el-tag type="warning" size="small" effect="dark" round>管理员</el-tag>
            <span class="role-option-desc">管理用户、组织、设备、内容</span>
          </div>
        </el-option>
        <el-option value="org_admin">
          <div class="role-option">
            <el-tag size="small" effect="dark" round>组织管理员</el-tag>
            <span class="role-option-desc">管理所属组织的成员和数据</span>
          </div>
        </el-option>
        <el-option value="user">
          <div class="role-option">
            <el-tag type="info" size="small" effect="dark" round>普通用户</el-tag>
            <span class="role-option-desc">仅可使用基础功能</span>
          </div>
        </el-option>
      </el-select>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="roleSubmitting" :disabled="roleNewValue === roleEditingUser?.role" @click="submitRoleChange">确认修改</el-button>
      </template>
    </el-dialog>

    <!-- 修改密码对话框 -->
    <el-dialog v-model="pwdDialogVisible" title="修改密码" width="420px" destroy-on-close>
      <div v-if="pwdEditingUser" style="margin-bottom: 16px;">
        <span style="color: var(--text-secondary);">用户：</span>
        <strong>{{ pwdEditingUser.username }}</strong>
      </div>
      <el-form :model="pwdForm" :rules="pwdRules" ref="pwdFormRef" label-position="top">
        <el-form-item label="新密码" prop="password">
          <el-input v-model="pwdForm.password" type="password" show-password placeholder="至少8位，含字母和数字" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="pwdForm.confirmPassword" type="password" show-password placeholder="再次输入新密码" @keydown.enter="submitPwdChange" />
        </el-form-item>
      </el-form>
      <div class="pwd-strength" v-if="pwdForm.password">
        <span class="pwd-strength-label">密码强度：</span>
        <div class="pwd-strength-bar">
          <div class="pwd-strength-fill" :class="pwdStrengthClass" :style="{ width: pwdStrengthPercent + '%' }"></div>
        </div>
        <span class="pwd-strength-text" :class="pwdStrengthClass">{{ pwdStrengthText }}</span>
      </div>
      <template #footer>
        <el-button @click="pwdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdSubmitting" @click="submitPwdChange">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../utils/request'

const users = ref<any[]>([])
const loading = ref(false)
const search = ref('')
const roleFilter = ref('')
const orgFilter = ref<number | ''>('')
const orgs = ref<any[]>([])
const page = ref(1)
const pageSize = 20
const total = ref(0)

function roleLabel(r: string) {
  return { super_admin: '超级管理员', admin: '管理员', org_admin: '组织管理员', user: '普通用户' }[r] || r
}
function roleTag(r: string) {
  return { super_admin: 'danger', admin: 'warning', org_admin: '', user: 'info' }[r] as any || 'info'
}

async function loadUsers(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const res: any = await request.get('/users/', {
      params: {
        page: page.value,
        page_size: pageSize,
        search: search.value || undefined,
        role: roleFilter.value || undefined,
        org_id: orgFilter.value || undefined,
      },
    })
    users.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

const actionLoading = ref<number | null>(null)
const selectedUsers = ref<any[]>([])
const batchLoading = ref(false)

function handleSelectionChange(rows: any[]) {
  selectedUsers.value = rows
}

async function batchToggleActive(active: boolean) {
  const action = active ? '启用' : '禁用'
  try {
    await ElMessageBox.confirm(`确定批量${action} ${selectedUsers.value.length} 个用户？`, '确认', { type: 'warning' })
  } catch { return }
  batchLoading.value = true
  try {
    await Promise.all(
      selectedUsers.value
        .filter(u => u.is_active !== active)
        .map(u => request.put(`/users/${u.id}`, { is_active: active }))
    )
    ElMessage.success(`已批量${action}`)
    selectedUsers.value = []
    loadUsers()
  } catch { /* interceptor handles */ }
  finally { batchLoading.value = false }
}

async function toggleActive(row: any) {
  const action = row.is_active ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(`确定${action}用户「${row.username}」？`, '确认', { type: 'warning' })
  } catch { return }
  actionLoading.value = row.id
  try {
    await request.put(`/users/${row.id}`, { is_active: !row.is_active })
    ElMessage.success(`已${action}`)
    loadUsers()
  } finally { actionLoading.value = null }
}

const roleDialogVisible = ref(false)
const roleEditingUser = ref<any>(null)
const roleNewValue = ref('')
const roleSubmitting = ref(false)

function changeRole(row: any) {
  roleEditingUser.value = row
  roleNewValue.value = row.role
  roleDialogVisible.value = true
}

async function submitRoleChange() {
  if (!roleEditingUser.value || roleNewValue.value === roleEditingUser.value.role) return
  roleSubmitting.value = true
  try {
    await request.put(`/users/${roleEditingUser.value.id}`, { role: roleNewValue.value })
    ElMessage.success('角色已更新')
    roleDialogVisible.value = false
    loadUsers()
  } catch { /* interceptor handles */ }
  finally { roleSubmitting.value = false }
}

const pwdDialogVisible = ref(false)
const pwdEditingUser = ref<any>(null)
const pwdForm = ref({ password: '', confirmPassword: '' })
const pwdSubmitting = ref(false)
const pwdFormRef = ref<any>()

const pwdRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码长度至少8位', trigger: 'blur' },
    { pattern: /[A-Za-z]/, message: '密码须包含字母', trigger: 'blur' },
    { pattern: /\d/, message: '密码须包含数字', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string, callback: (err?: Error) => void) => {
        if (value !== pwdForm.value.password) callback(new Error('两次密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

function computePwdStrength(pwd: string): number {
  let score = 0
  if (pwd.length >= 8) score++
  if (pwd.length >= 12) score++
  if (/[A-Z]/.test(pwd) && /[a-z]/.test(pwd)) score++
  if (/\d/.test(pwd)) score++
  if (/[^A-Za-z0-9]/.test(pwd)) score++
  return score
}

const pwdStrengthPercent = computed(() => Math.min(computePwdStrength(pwdForm.value.password) * 20, 100))
const pwdStrengthClass = computed(() => {
  const s = computePwdStrength(pwdForm.value.password)
  if (s <= 1) return 'weak'
  if (s <= 3) return 'medium'
  return 'strong'
})
const pwdStrengthText = computed(() => {
  const s = computePwdStrength(pwdForm.value.password)
  if (s <= 1) return '弱'
  if (s <= 3) return '中'
  return '强'
})

function changePwd(row: any) {
  pwdEditingUser.value = row
  pwdForm.value = { password: '', confirmPassword: '' }
  pwdDialogVisible.value = true
}

async function submitPwdChange() {
  try { await pwdFormRef.value?.validate() } catch { return }
  pwdSubmitting.value = true
  try {
    await request.put(`/users/${pwdEditingUser.value.id}`, { password: pwdForm.value.password })
    ElMessage.success('密码修改成功')
    pwdDialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '密码修改失败')
  } finally { pwdSubmitting.value = false }
}

async function deleteUser(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${row.username}」？`, '确认', { type: 'error' })
  } catch { return }
  actionLoading.value = row.id
  try {
    await request.delete(`/users/${row.id}`)
    ElMessage.success('用户已删除')
    loadUsers()
  } finally { actionLoading.value = null }
}

async function loadOrgs() {
  try {
    const pageSize = 100
    let currentPage = 1
    const allOrgs: any[] = []

    while (true) {
      const res: any = await request.get('/organizations/', {
        params: { page: currentPage, page_size: pageSize },
      })
      const items = res.items || []
      allOrgs.push(...items)

      if (items.length < pageSize || allOrgs.length >= (res.total || 0)) break
      currentPage += 1
    }

    orgs.value = allOrgs
  } catch { /* */ }
}

onMounted(() => {
  loadOrgs()
  loadUsers()
})
</script>

<style scoped>
.page-subtitle {
  font-size: 14px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.table-card :deep(.el-card__body) { padding: 0 !important; }

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
}

.toolbar-left { display: flex; gap: 12px; align-items: center; }

.user-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-cell-avatar {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--brand-primary-light);
  color: var(--brand-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.user-cell-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
}

.user-cell-email {
  font-size: 12px;
  color: var(--text-tertiary);
}

.status-dot-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.status-dot.online { background: var(--color-success); box-shadow: 0 0 0 3px rgba(0, 181, 120, 0.15); }
.status-dot.offline { background: var(--color-danger); box-shadow: 0 0 0 3px rgba(227, 77, 89, 0.1); }

.text-secondary { color: var(--text-secondary); font-size: 13px; }

.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  background: var(--brand-primary-light, #E8EFFD);
  border-bottom: 1px solid var(--border-light);
  font-size: 13px;
  font-weight: 500;
  color: var(--brand-primary, #2B5AED);
}

.action-group { display: flex; align-items: center; justify-content: center; }
.action-group .el-divider { margin: 0 4px; }

.table-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid var(--border-light);
}

.role-option { display: flex; align-items: center; gap: 10px; padding: 2px 0; }
.role-option-desc { font-size: 12px; color: var(--text-tertiary); }

.pwd-strength { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.pwd-strength-label { font-size: 12px; color: var(--text-tertiary); flex-shrink: 0; }
.pwd-strength-bar { flex: 1; height: 4px; background: #F1F5F9; border-radius: 2px; overflow: hidden; }
.pwd-strength-fill { height: 100%; border-radius: 2px; transition: width 0.3s, background 0.3s; }
.pwd-strength-fill.weak { background: #EF4444; }
.pwd-strength-fill.medium { background: #F59E0B; }
.pwd-strength-fill.strong { background: #10B981; }
.pwd-strength-text { font-size: 12px; font-weight: 600; min-width: 20px; }
.pwd-strength-text.weak { color: #EF4444; }
.pwd-strength-text.medium { color: #F59E0B; }
.pwd-strength-text.strong { color: #10B981; }
</style>
