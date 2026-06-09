<template>
  <div class="invite-page">
    <div class="invite-card" v-loading="loading">
      <!-- Error state -->
      <template v-if="error">
        <div class="invite-icon error"><XCircle :size="48" :stroke-width="1.5" /></div>
        <h2>邀请链接无效</h2>
        <p class="invite-desc">{{ error }}</p>
        <el-button type="primary" @click="$router.push('/login')">前往登录</el-button>
      </template>

      <!-- Invitation info -->
      <template v-else-if="inviteInfo && !accepted">
        <div class="invite-icon"><Building2 :size="48" :stroke-width="1.5" /></div>
        <h2>你被邀请加入</h2>
        <h1>{{ inviteInfo.workspace_name }}</h1>
        <p v-if="inviteInfo.workspace_description" class="invite-desc">{{ inviteInfo.workspace_description }}</p>
        <div class="invite-role">
          <span>加入角色：</span>
          <el-tag :type="inviteInfo.role === 'admin' ? 'warning' : 'info'" size="small">
            {{ roleMap[inviteInfo.role] || inviteInfo.role }}
          </el-tag>
        </div>

        <template v-if="isLoggedIn">
          <el-button type="primary" size="large" @click="handleAccept" :loading="accepting" style="margin-top: 24px; width: 200px">
            接受邀请，加入空间
          </el-button>
        </template>
        <template v-else>
          <div class="login-hint">
            <p>请先登录或注册账号，然后自动加入工作空间</p>
            <div style="display: flex; gap: 12px; margin-top: 16px">
              <el-button type="primary" size="large" @click="goLogin">登录</el-button>
              <el-button size="large" @click="goRegister">注册新账号</el-button>
            </div>
          </div>
        </template>
      </template>

      <!-- Accepted state -->
      <template v-if="accepted">
        <div class="invite-icon success"><CheckCircle :size="48" :stroke-width="1.5" /></div>
        <h2>加入成功！</h2>
        <p class="invite-desc">你已成功加入「{{ acceptResult.workspace_name }}」</p>
        <el-button type="primary" size="large" @click="goAfterAccept" style="margin-top: 16px">
          {{ acceptResult.remote ? '前往聊天' : '进入工作空间' }}
        </el-button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Building2, XCircle, CheckCircle } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { getInvitationInfo, acceptInvitation } from '../../api/workspaces'
import { roleMap } from '../../utils/format'

const route = useRoute()
const router = useRouter()
const token = computed(() => route.params.token as string)

const loading = ref(true)
const error = ref('')
const inviteInfo = ref<any>(null)
const accepting = ref(false)
const accepted = ref(false)
const acceptResult = ref<any>({})

const isLoggedIn = computed(() => !!localStorage.getItem('token'))


async function loadInviteInfo() {
  loading.value = true
  try {
    inviteInfo.value = await getInvitationInfo(token.value)
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    error.value = detail || '邀请链接无效或已过期'
  } finally {
    loading.value = false
  }
}

async function handleAccept() {
  accepting.value = true
  try {
    const res: any = await acceptInvitation(token.value)
    acceptResult.value = res
    accepted.value = true
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    if (detail) ElMessage.error(detail)
  } finally {
    accepting.value = false
  }
}

function goLogin() {
  // Store invite token so we can redirect back after login
  sessionStorage.setItem('pendingInvite', token.value)
  router.push('/login')
}

function goRegister() {
  sessionStorage.setItem('pendingInvite', token.value)
  router.push('/login?register=1')
}

function goAfterAccept() {
  if (acceptResult.value?.remote) {
    router.push('/chat')
    return
  }
  router.push(`/workspaces/${acceptResult.value.workspace_id}`)
}

onMounted(async () => {
  await loadInviteInfo()
  // Auto-accept if logged in and came back from login redirect
  const pending = sessionStorage.getItem('pendingInvite')
  if (pending === token.value && isLoggedIn.value && inviteInfo.value) {
    sessionStorage.removeItem('pendingInvite')
    await handleAccept()
  }
})
</script>

<style scoped>
.invite-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary, #f5f7fa);
  padding: 24px;
}

.invite-card {
  background: var(--card-bg, #fff);
  border: 1px solid var(--border-color, #e4e7ed);
  border-radius: 16px;
  padding: 48px;
  max-width: 480px;
  width: 100%;
  text-align: center;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
}

.invite-icon {
  width: 80px;
  height: 80px;
  border-radius: 20px;
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 24px;
}

.invite-icon.error {
  background: linear-gradient(135deg, #ef4444, #f97316);
}

.invite-icon.success {
  background: linear-gradient(135deg, #10b981, #34d399);
}

.invite-card h2 {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-secondary, #909399);
  margin: 0 0 8px;
}

.invite-card h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary, #303133);
  margin: 0 0 12px;
}

.invite-desc {
  color: var(--text-muted, #c0c4cc);
  font-size: 14px;
  margin: 0 0 16px;
  line-height: 1.5;
}

.invite-role {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 14px;
}

.login-hint {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--border-color, #e4e7ed);
}

.login-hint p {
  color: var(--text-secondary);
  font-size: 14px;
  margin: 0;
}
</style>
