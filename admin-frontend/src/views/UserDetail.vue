<template>
  <div class="user-detail-page">
    <div class="page-header">
      <div style="display: flex; align-items: center; gap: 12px;">
        <button class="back-btn" @click="$router.push('/users')">
          <el-icon :size="16"><ArrowLeft /></el-icon>
        </button>
        <div>
          <h2>用户详情</h2>
          <p class="page-subtitle" v-if="userInfo">{{ userInfo.username }} · {{ roleLabel(userInfo.role) }}</p>
        </div>
      </div>
      <div v-if="userInfo" style="display: flex; gap: 8px; align-items: center;">
        <el-button size="small" type="primary" @click="onAddCredit">充值算力</el-button>
        <el-button size="small" @click="onEditQuota">编辑配额</el-button>
        <el-button size="small" type="warning" @click="resetPassword">重置密码</el-button>
      </div>
    </div>

    <!-- Profile Card -->
    <div v-if="userInfo" class="profile-banner">
      <div class="profile-avatar">{{ userInfo.username?.[0]?.toUpperCase() }}</div>
      <div class="profile-info">
        <div class="profile-name">{{ userInfo.username }}</div>
        <div class="profile-email">{{ userInfo.email }}</div>
      </div>
      <div class="profile-stats">
        <div class="profile-stat">
          <span class="profile-stat-value">
            <el-tag :type="quotaPlanTag" size="small" effect="dark" round>{{ quotaPlanLabel }}</el-tag>
          </span>
          <span class="profile-stat-label">方案</span>
        </div>
        <div class="profile-stat">
          <span class="profile-stat-value">{{ modelsTabRef?.models?.length ?? 0 }}</span>
          <span class="profile-stat-label">模型</span>
        </div>
        <div class="profile-stat">
          <span class="profile-stat-value">{{ devices.length }}</span>
          <span class="profile-stat-label">设备</span>
        </div>
        <div class="profile-stat">
          <span class="profile-stat-value">{{ usageData.length ? usageData.reduce((s, d) => s + d.tokens, 0).toLocaleString() : '—' }}</span>
          <span class="profile-stat-label">月 Token</span>
        </div>
        <div class="profile-stat">
          <span class="profile-stat-value">{{ userInfo.last_login_at ? new Date(userInfo.last_login_at).toLocaleDateString() : '—' }}</span>
          <span class="profile-stat-label">最后登录</span>
        </div>
      </div>
    </div>

    <!-- Tab Navigation -->
    <el-tabs v-model="activeTab" class="detail-tabs">
      <!-- Overview Tab -->
      <el-tab-pane label="概览" name="overview">
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; margin-bottom: 20px;" v-if="userInfo">
          <div class="quota-stat-card">
            <div class="quota-stat-label">当前方案</div>
            <div class="quota-stat-value"><el-tag :type="quotaPlanTag" size="small">{{ quotaPlanLabel }}</el-tag></div>
          </div>
          <div class="quota-stat-card">
            <div class="quota-stat-label">试用额度</div>
            <div class="quota-stat-value">{{ userInfo.trial_used ?? 0 }} / {{ userInfo.trial_total ?? 50 }}</div>
          </div>
          <div class="quota-stat-card">
            <div class="quota-stat-label">算力额度</div>
            <div class="quota-stat-value">{{ (userInfo.token_credit ?? 0).toLocaleString() }}</div>
          </div>
          <div class="quota-stat-card">
            <div class="quota-stat-label">已用算力</div>
            <div class="quota-stat-value">{{ (userInfo.token_used ?? 0).toLocaleString() }}</div>
          </div>
          <div v-if="tokenSummary.chat_count" class="quota-stat-card">
            <div class="quota-stat-label">对话数</div>
            <div class="quota-stat-value">{{ tokenSummary.chat_count }}</div>
          </div>
          <div v-if="tokenSummary.avg_latency_ms" class="quota-stat-card">
            <div class="quota-stat-label">平均延迟</div>
            <div class="quota-stat-value">{{ tokenSummary.avg_latency_ms }}ms</div>
          </div>
        </div>

        <el-card v-if="userInfo?.org_id" class="section-card" shadow="never">
          <template #header><span class="section-title">所属组织</span></template>
          <div style="display: flex; align-items: center; gap: 12px;">
            <el-tag type="primary" effect="light" size="large" round>组织 #{{ userInfo.org_id }}</el-tag>
            <el-button size="small" type="primary" link @click="$router.push(`/organizations/${userInfo.org_id}/detail`)">查看组织详情 &rarr;</el-button>
          </div>
        </el-card>

        <el-card class="section-card" shadow="never" v-loading="usageLoading">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span class="section-title">用量趋势</span>
              <span class="chart-period">近 30 天</span>
            </div>
          </template>
          <div v-if="usageData.length" class="usage-chart-area">
            <div class="usage-bar-chart">
              <div v-for="(item, idx) in usageData" :key="item.date" class="usage-bar-col" :style="{ animationDelay: idx * 20 + 'ms' }">
                <div class="usage-bar-tooltip">{{ (item.tokens || 0).toLocaleString() }}</div>
                <div class="usage-bar" :style="{ height: barH(item.tokens) + '%' }"></div>
                <div class="usage-bar-label">{{ item.date?.slice?.(5) || '' }}</div>
              </div>
            </div>
          </div>
          <el-empty v-else description="暂无用量数据" :image-size="60" />
        </el-card>

        <el-card v-if="usageDetail.by_model?.length" class="section-card" shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span class="section-title">模型用量明细</span>
              <span v-if="usageDetail.synced_at" style="font-size: 12px; color: var(--text-tertiary);">同步于 {{ new Date(usageDetail.synced_at).toLocaleString() }}</span>
            </div>
          </template>
          <el-table :data="usageDetail.by_model" stripe size="small">
            <el-table-column prop="model_name" label="模型" min-width="140" />
            <el-table-column label="输入 Token" width="120"><template #default="{ row }">{{ (row.input_tokens || 0).toLocaleString() }}</template></el-table-column>
            <el-table-column label="输出 Token" width="120"><template #default="{ row }">{{ (row.output_tokens || 0).toLocaleString() }}</template></el-table-column>
            <el-table-column label="对话数" width="80"><template #default="{ row }">{{ row.conversations || 0 }}</template></el-table-column>
          </el-table>
        </el-card>

        <el-card v-if="userInfo" class="section-card" shadow="never">
          <template #header><span class="section-title">详细信息</span></template>
          <el-descriptions :column="3" border>
            <el-descriptions-item label="ID">{{ userInfo.id }}</el-descriptions-item>
            <el-descriptions-item label="用户名">{{ userInfo.username }}</el-descriptions-item>
            <el-descriptions-item label="邮箱">{{ userInfo.email }}</el-descriptions-item>
            <el-descriptions-item label="角色"><el-tag :type="roleTag(userInfo.role)" size="small" effect="light" round>{{ roleLabel(userInfo.role) }}</el-tag></el-descriptions-item>
            <el-descriptions-item label="状态"><el-tag :type="userInfo.is_active ? 'success' : 'danger'" size="small" effect="light" round>{{ userInfo.is_active ? '正常' : '已禁用' }}</el-tag></el-descriptions-item>
            <el-descriptions-item label="组织 ID">{{ userInfo.org_id ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="最后登录 IP"><code v-if="userInfo.last_login_ip" style="color: var(--text-secondary);">{{ userInfo.last_login_ip }}</code><span v-else>—</span></el-descriptions-item>
            <el-descriptions-item label="最后登录">{{ userInfo.last_login_at ? new Date(userInfo.last_login_at).toLocaleString() : '—' }}</el-descriptions-item>
            <el-descriptions-item label="注册时间">{{ userInfo.created_at ? new Date(userInfo.created_at).toLocaleString() : '—' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-tab-pane>

      <!-- Models Tab -->
      <el-tab-pane :label="`模型 (${modelsTabRef?.models?.length ?? 0})`" name="models">
        <UserModelsTab ref="modelsTabRef" :userId="userId" :userInfo="userInfo" @reload-user="loadUserInfo" />
      </el-tab-pane>

      <!-- Devices Tab -->
      <el-tab-pane :label="`设备 (${devices.length})`" name="devices">
        <el-table v-if="devices.length" :data="devices" stripe size="small" v-loading="devicesLoading">
          <el-table-column prop="device_name" label="设备名称" min-width="140"><template #default="{ row }">{{ row.device_name || row.device_id }}</template></el-table-column>
          <el-table-column prop="os_info" label="系统信息" min-width="150" show-overflow-tooltip />
          <el-table-column prop="mac_address" label="MAC 地址" width="150"><template #default="{ row }"><code v-if="row.mac_address" style="font-size:12px;color:var(--text-tertiary)">{{ row.mac_address }}</code><span v-else>—</span></template></el-table-column>
          <el-table-column prop="app_version" label="版本" width="100" />
          <el-table-column label="状态" width="80"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="plain" round>{{ row.is_active ? '在线' : '离线' }}</el-tag></template></el-table-column>
          <el-table-column label="最后心跳" width="170"><template #default="{ row }">{{ row.last_heartbeat ? new Date(row.last_heartbeat).toLocaleString() : '—' }}</template></el-table-column>
        </el-table>
        <el-empty v-else description="暂无关联设备" :image-size="60" />
      </el-tab-pane>

      <!-- Logs Tab -->
      <el-tab-pane :label="`日志 (${(logsTabRef?.auditTotal ?? 0) + (logsTabRef?.opLogsTotal ?? 0)})`" name="logs">
        <UserLogsTab ref="logsTabRef" :userId="userId" />
      </el-tab-pane>
    </el-tabs>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../utils/request'
import UserModelsTab from '../components/user/UserModelsTab.vue'
import UserLogsTab from '../components/user/UserLogsTab.vue'

const route = useRoute()
const userId = Number(route.params.userId)

const activeTab = ref('overview')
const userInfo = ref<any>(null)
const modelsTabRef = ref<InstanceType<typeof UserModelsTab>>()
const logsTabRef = ref<InstanceType<typeof UserLogsTab>>()

const quotaPlanLabel = computed(() => {
  const m: Record<string, string> = { trial: '试用', basic: '基础', pro: '专业', enterprise: '企业' }
  return m[userInfo.value?.plan] || userInfo.value?.plan || '未知'
})
const quotaPlanTag = computed(() => {
  const m: Record<string, string> = { trial: 'info', basic: '', pro: 'warning', enterprise: 'success' }
  return (m[userInfo.value?.plan] || 'info') as any
})

function onAddCredit() { if (modelsTabRef.value) modelsTabRef.value.showAddCreditDialog = true }
function onEditQuota() { if (modelsTabRef.value) modelsTabRef.value.openQuotaEdit() }

const usageData = ref<any[]>([])
const usageLoading = ref(false)
const usageDetail = ref<any>({})
const tokenSummary = ref<any>({})
const devices = ref<any[]>([])
const devicesLoading = ref(false)

const maxTokens = computed(() => Math.max(...usageData.value.map(d => d.tokens || 0), 1))
function barH(v: number) { return maxTokens.value === 0 ? 0 : Math.max((v / maxTokens.value) * 100, v > 0 ? 4 : 0) }

function roleLabel(r: string) {
  return { super_admin: '超级管理员', admin: '管理员', org_admin: '组织管理员', user: '普通用户' }[r] || r
}
function roleTag(r: string) {
  return { super_admin: 'danger', admin: 'warning', org_admin: '', user: 'info' }[r] as any || 'info'
}

async function loadUserInfo() {
  try {
    userInfo.value = await request.get(`/users/${userId}`)
    if (!userInfo.value) {
      ElMessage.error('用户不存在')
    }
  } catch (e: any) {
    if (e?.response?.status === 404) {
      ElMessage.error('用户不存在')
    }
  }
}

async function loadUsage() {
  usageLoading.value = true
  try {
    usageData.value = (await request.get(`/users/${userId}/usage`, { params: { days: 30 } })) as any[] || []
    try { usageDetail.value = await request.get(`/users/${userId}/usage-detail`) } catch { usageDetail.value = {} }
  } catch { /* */ }
  finally { usageLoading.value = false }
}

async function loadDevices() {
  devicesLoading.value = true
  try {
    const res: any = await request.get(`/users/${userId}/devices`)
    devices.value = Array.isArray(res) ? res : (res?.items || [])
  }
  catch { /* */ }
  finally { devicesLoading.value = false }
}

async function resetPassword() {
  try {
    await ElMessageBox.confirm(
      `确定重置用户「${userInfo.value?.username}」的密码？将生成一个新的随机密码。`,
      '重置密码',
      { type: 'warning', confirmButtonText: '重置', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    const res: any = await request.post(`/users/${userId}/reset-password`)
    const rawPwd = res.temp_password || res.new_password || res.password || '查看日志'
    const escaped = rawPwd.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
    ElMessageBox.alert(
      `新密码：<code style="font-size:16px;background:#f0f0f0;padding:4px 12px;border-radius:6px;user-select:all">${escaped}</code>`,
      '密码已重置',
      { dangerouslyUseHTMLString: true, confirmButtonText: '知道了' },
    )
  } catch { /* interceptor handles */ }
}

async function loadTokenSummary() {
  try { tokenSummary.value = await request.get(`/users/${userId}/token-summary`) as any || {} }
  catch { /* endpoint may not exist */ }
}

onMounted(() => { loadUserInfo(); loadUsage(); loadDevices(); loadTokenSummary() })
</script>

<style scoped>
.user-detail-page { max-width: 1200px; }

.page-subtitle { font-size: 14px; color: var(--text-tertiary); margin-top: 2px; }

.back-btn {
  width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-color); border-radius: 8px; background: transparent;
  cursor: pointer; color: var(--text-secondary); transition: all 0.2s;
}
.back-btn:hover { background: var(--bg-page); color: var(--text-primary); border-color: #CBD5E1; }

.profile-banner {
  display: flex; align-items: center; gap: 20px;
  background: var(--brand-gradient-dark);
  border-radius: var(--radius-lg); padding: 28px 32px; margin-bottom: 20px;
  position: relative; overflow: hidden;
}
.profile-banner::before {
  content: ''; position: absolute; top: -40px; right: -40px; width: 160px; height: 160px;
  background: radial-gradient(circle, rgba(43,90,237,0.2) 0%, transparent 70%); border-radius: 50%;
}

.profile-avatar {
  width: 64px; height: 64px; border-radius: 16px;
  background: var(--brand-gradient); color: #FFF; display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 700; flex-shrink: 0; box-shadow: 0 4px 12px rgba(43,90,237,0.3);
}

.profile-info { flex: 1; min-width: 0; }
.profile-name { font-size: 20px; font-weight: 700; color: #FFF; margin-bottom: 4px; }
.profile-email { font-size: 14px; color: rgba(255,255,255,0.55); }

.profile-stats { display: flex; gap: 32px; }
.profile-stat { display: flex; flex-direction: column; align-items: center; }
.profile-stat-value { font-size: 18px; font-weight: 700; color: #FFF; letter-spacing: -0.02em; }
.profile-stat-label { font-size: 11px; color: rgba(255,255,255,0.45); margin-top: 2px; }

.detail-tabs { margin-bottom: 20px; }
.detail-tabs :deep(.el-tabs__header) { margin-bottom: 20px; }
.section-card { margin-bottom: 20px; }
.section-title { font-weight: 600; font-size: 15px; }
.chart-period { font-size: 12px; color: var(--text-tertiary); }

.quota-stat-card {
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  padding: 14px 16px;
}
.quota-stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.quota-stat-value { font-size: 18px; font-weight: 600; color: var(--el-text-color-primary); }

.usage-chart-area { height: 200px; display: flex; align-items: flex-end; }
.usage-bar-chart {
  display: flex; align-items: flex-end; gap: 3px; width: 100%; height: 100%; padding-bottom: 24px;
}
.usage-bar-col {
  flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%;
  justify-content: flex-end; position: relative; animation: barFadeIn 0.4s ease-out both;
}
@keyframes barFadeIn { from { opacity: 0; transform: scaleY(0.5); } to { opacity: 1; transform: scaleY(1); } }

.usage-bar-tooltip {
  font-size: 10px; color: var(--text-tertiary); margin-bottom: 4px; opacity: 0; transition: opacity 0.2s;
}
.usage-bar-col:hover .usage-bar-tooltip { opacity: 1; }
.usage-bar {
  width: 100%; max-width: 16px; border-radius: 4px 4px 0 0; min-height: 2px;
  background: linear-gradient(180deg, #2B5AED 0%, #5B8DEF 100%);
  transition: height 0.6s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer;
}
.usage-bar:hover { opacity: 0.85; }
.usage-bar-label { font-size: 9px; color: var(--text-tertiary); margin-top: 6px; white-space: nowrap; }
</style>
