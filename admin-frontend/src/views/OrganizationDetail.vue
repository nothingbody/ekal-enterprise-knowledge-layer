<template>
  <div class="org-detail-page">
    <div class="page-header">
      <div style="display: flex; align-items: center; gap: 12px;">
        <button class="back-btn" @click="$router.push('/organizations')">
          <el-icon :size="16"><ArrowLeft /></el-icon>
        </button>
        <div>
          <h2>组织详情</h2>
          <p class="page-subtitle" v-if="orgInfo">{{ orgInfo.name }}</p>
        </div>
      </div>
    </div>

    <div v-if="orgInfo" class="org-banner">
      <div class="org-avatar">{{ orgInfo.name?.[0]?.toUpperCase() }}</div>
      <div class="org-info">
        <div class="org-name">{{ orgInfo.name }}</div>
        <div class="org-desc">{{ orgInfo.description || '暂无描述' }}</div>
      </div>
      <div class="org-stats">
        <div class="org-stat">
          <span class="org-stat-value">{{ members.length }}</span>
          <span class="org-stat-label">成员</span>
        </div>
        <div class="org-stat">
          <span class="org-stat-value">{{ totalTokens.toLocaleString() }}</span>
          <span class="org-stat-label">总 Token</span>
        </div>
        <div class="org-stat">
          <span class="org-stat-value">{{ orgInfo.created_at ? new Date(orgInfo.created_at).toLocaleDateString() : '—' }}</span>
          <span class="org-stat-label">创建时间</span>
        </div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="detail-tabs">
      <el-tab-pane :label="`成员 (${members.length})`" name="members">
        <el-table :data="members" stripe size="default" v-loading="membersLoading" empty-text="暂无成员">
          <el-table-column label="用户名" min-width="140">
            <template #default="{ row }">
              <el-button link type="primary" @click="$router.push(`/users/${row.id || row.user_id}/detail`)">{{ row.username }}</el-button>
            </template>
          </el-table-column>
          <el-table-column prop="email" label="邮箱" min-width="200" />
          <el-table-column label="角色" width="140">
            <template #default="{ row }">
              <el-select
                :model-value="row.role"
                size="small"
                style="width: 110px"
                @change="(val: string) => changeMemberRole(row, val)"
              >
                <el-option label="所有者" value="owner" />
                <el-option label="管理员" value="admin" />
                <el-option label="成员" value="member" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="方案" width="90">
            <template #default="{ row }">
              <el-tag :type="({ trial: 'info', basic: '', pro: 'warning', enterprise: 'success' } as Record<string, string>)[row.plan] || 'info'" size="small" effect="light" round>
                {{ ({ trial: '试用', basic: '基础', pro: '专业', enterprise: '企业' } as Record<string, string>)[row.plan] || row.plan || '试用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Token 消耗" width="130">
            <template #default="{ row }">{{ (row.token_used || 0).toLocaleString() }}</template>
          </el-table-column>
          <el-table-column label="最后登录" width="170">
            <template #default="{ row }">{{ row.last_login_at ? new Date(row.last_login_at).toLocaleString() : '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button link size="small" type="danger" @click="removeMember(row)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div style="margin-top: 16px;">
          <el-button size="small" type="primary" round @click="showAddMemberDialog = true">
            <el-icon><Plus /></el-icon>添加成员
          </el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Token 统计" name="stats">
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px;">
          <div class="stat-card">
            <div class="stat-label">总成员数</div>
            <div class="stat-value">{{ members.length }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">总 Token 消耗</div>
            <div class="stat-value">{{ totalTokens.toLocaleString() }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">总算力额度</div>
            <div class="stat-value">{{ totalCredit.toLocaleString() }}</div>
          </div>
        </div>

        <el-card shadow="never">
          <template #header><span style="font-weight: 600;">成员 Token 消耗排行</span></template>
          <el-table :data="membersByUsage" stripe size="small" empty-text="暂无数据">
            <el-table-column label="#" width="50"><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
            <el-table-column label="用户名" min-width="120">
              <template #default="{ row }">
                <el-button link type="primary" @click="$router.push(`/users/${row.id || row.user_id}/detail`)">{{ row.username }}</el-button>
              </template>
            </el-table-column>
            <el-table-column label="已用 Token" width="130"><template #default="{ row }">{{ (row.token_used || 0).toLocaleString() }}</template></el-table-column>
            <el-table-column label="额度" width="130"><template #default="{ row }">{{ (row.token_credit || 0).toLocaleString() }}</template></el-table-column>
            <el-table-column label="使用率" width="120">
              <template #default="{ row }">
                <el-progress :percentage="row.token_credit ? Math.round((row.token_used || 0) / row.token_credit * 100) : 0" :stroke-width="6" :show-text="true" />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showAddMemberDialog" title="添加成员" width="440px">
      <el-form label-width="80px">
        <el-form-item label="搜索用户">
          <el-select
            v-model="selectedUserForAdd"
            filterable
            remote
            reserve-keyword
            placeholder="搜索用户名或邮箱"
            :remote-method="searchUsersForAdd"
            :loading="userSearchLoading"
            clearable
            style="width: 100%"
            value-key="id"
          >
            <el-option
              v-for="u in userSearchResults"
              :key="u.id"
              :label="`${u.username} (${u.email})`"
              :value="u"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddMemberDialog = false">取消</el-button>
        <el-button type="primary" :loading="addMemberLoading" :disabled="!selectedUserForAdd" @click="addMember">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../utils/request'

const route = useRoute()
const orgId = Number(route.params.orgId)
const activeTab = ref('members')

const orgInfo = ref<any>(null)
const members = ref<any[]>([])
const membersLoading = ref(false)
const showAddMemberDialog = ref(false)
const addMemberLoading = ref(false)
const selectedUserForAdd = ref<any>(null)
const userSearchResults = ref<any[]>([])
const userSearchLoading = ref(false)
let userSearchTimer: ReturnType<typeof setTimeout> | null = null

const totalTokens = computed(() => members.value.reduce((s, m) => s + (m.token_used || 0), 0))
const totalCredit = computed(() => members.value.reduce((s, m) => s + (m.token_credit || 0), 0))
const membersByUsage = computed(() => [...members.value].sort((a, b) => (b.token_used || 0) - (a.token_used || 0)))

async function loadOrgInfo() {
  try {
    orgInfo.value = await request.get(`/organizations/${orgId}`) as any
  } catch {
    // Fallback: fetch from list if direct endpoint unavailable
    try {
      const orgs: any = await request.get('/organizations', { params: { page_size: 100 } })
      orgInfo.value = (orgs?.items || []).find((o: any) => o.id === orgId) || null
    } catch { /* */ }
  }
  if (!orgInfo.value) {
    ElMessage.error('组织不存在')
  }
}

async function loadMembers() {
  membersLoading.value = true
  try { members.value = (await request.get(`/organizations/${orgId}/members`)) as any[] || [] }
  catch { members.value = [] }
  finally { membersLoading.value = false }
}

function searchUsersForAdd(query: string) {
  if (!query || query.trim().length < 1) { userSearchResults.value = []; return }
  if (userSearchTimer) clearTimeout(userSearchTimer)
  userSearchTimer = setTimeout(async () => {
    userSearchLoading.value = true
    try {
      const res: any = await request.get('/users/', { params: { search: query.trim(), page_size: 20 } })
      const list = res.items || []
      const memberIds = new Set(members.value.map((m: any) => m.user_id))
      userSearchResults.value = list.filter((u: any) => !memberIds.has(u.id))
    } catch { userSearchResults.value = [] }
    finally { userSearchLoading.value = false }
  }, 300)
}

async function addMember() {
  const user = selectedUserForAdd.value
  if (!user?.id) { ElMessage.warning('请选择用户'); return }
  addMemberLoading.value = true
  try {
    await request.post(`/organizations/${orgId}/members`, { user_id: user.id, role: 'member' })
    ElMessage.success('已添加')
    showAddMemberDialog.value = false
    selectedUserForAdd.value = null
    userSearchResults.value = []
    await loadMembers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '添加失败')
  }
  finally { addMemberLoading.value = false }
}

async function changeMemberRole(member: any, newRole: string) {
  if (member.role === newRole) return
  try {
    await request.put(`/organizations/${orgId}/members/${member.user_id}/role`, null, { params: { role: newRole } })
    ElMessage.success('角色已更新')
    await loadMembers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '角色更新失败')
  }
}

async function removeMember(member: any) {
  try { await ElMessageBox.confirm(`移除成员「${member.username}」？`, '确认', { type: 'warning' }) } catch { return }
  try {
    await request.delete(`/organizations/${orgId}/members/${member.id || member.user_id}`)
    ElMessage.success('已移除')
    await loadMembers()
  } catch { /* */ }
}

onMounted(() => { loadOrgInfo(); loadMembers() })
</script>

<style scoped>
.org-detail-page { max-width: 1200px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-header h2 { margin: 0 0 4px; }
.page-subtitle { font-size: 14px; color: var(--text-tertiary); margin-top: 2px; }

.back-btn {
  width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-color); border-radius: 8px; background: transparent;
  cursor: pointer; color: var(--text-secondary); transition: all 0.2s;
}
.back-btn:hover { background: var(--bg-page); color: var(--text-primary); border-color: #CBD5E1; }

.org-banner {
  display: flex; align-items: center; gap: 20px;
  background: var(--brand-gradient-dark);
  border-radius: var(--radius-lg); padding: 28px 32px; margin-bottom: 20px;
  position: relative; overflow: hidden;
}
.org-avatar {
  width: 64px; height: 64px; border-radius: 16px;
  background: var(--brand-gradient); color: #FFF; display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 700; flex-shrink: 0;
}
.org-info { flex: 1; min-width: 0; }
.org-name { font-size: 20px; font-weight: 700; color: #FFF; margin-bottom: 4px; }
.org-desc { font-size: 14px; color: rgba(255,255,255,0.55); }
.org-stats { display: flex; gap: 32px; }
.org-stat { display: flex; flex-direction: column; align-items: center; }
.org-stat-value { font-size: 18px; font-weight: 700; color: #FFF; }
.org-stat-label { font-size: 11px; color: rgba(255,255,255,0.45); margin-top: 2px; }

.detail-tabs { margin-bottom: 20px; }

.stat-card {
  background: #FFF; border: 1px solid var(--border-color, #E5E7EB);
  border-radius: 10px; padding: 18px 20px; text-align: center;
}
.stat-value { font-size: 28px; font-weight: 700; color: var(--text-primary, #1e293b); letter-spacing: -0.02em; }
.stat-label { font-size: 12px; color: var(--text-tertiary, #94a3b8); margin-bottom: 6px; }
</style>
