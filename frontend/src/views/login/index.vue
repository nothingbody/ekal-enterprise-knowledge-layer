<template>
  <div class="login-wrapper">
    <!-- Dynamic Animated Background -->
    <div class="bg-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
    </div>

    <!-- Main Glass Panel -->
    <div class="login-container">
      
      <!-- Left Hero Section -->
      <div class="hero-section">
        <div class="hero-content">
          <div class="brand-logo">
            <img src="/logo.svg" alt="" class="brand-logo-img" />
          </div>
          <h1 class="hero-title">企业多模态知识协作共享服务平台</h1>
          <p class="hero-subtitle">面向企业知识沉淀、协同检索与智能共享的统一入口</p>
          <div class="feature-list">
            <div class="feature-item">
              <div class="feature-icon"><BookOpen :size="18" :stroke-width="1.5" /></div>
              <span>多源异构文档解析与深度入库</span>
            </div>
            <div class="feature-item">
              <div class="feature-icon"><BrainCircuit :size="18" :stroke-width="1.5" /></div>
              <span>向量与稀疏混合双路智能检索</span>
            </div>
            <div class="feature-item">
              <div class="feature-icon"><Database :size="18" :stroke-width="1.5" /></div>
              <span>NL2SQL 结构化数据无缝接入</span>
            </div>
          </div>
        </div>
        <div class="hero-footer">
          <span>&copy; 2026 企业多模态知识协作共享服务平台</span>
          <span class="version-tag">v{{ APP_VERSION }}</span>
        </div>
      </div>

      <!-- Right Form Section -->
      <div class="form-section">
        <transition name="fade-slide" mode="out-in">
          
          <!-- Login Form -->
          <div v-if="activeTab === 'login'" class="form-card" key="login">
            <div class="form-header">
              <h2>欢迎回来</h2>
              <p>登录您的账号以继续</p>
            </div>
            <el-form :model="loginForm" :rules="loginRules" ref="loginRef" @submit.prevent="handleLogin" size="large" class="custom-form">
              <el-form-item prop="username">
                <el-input v-model="loginForm.username" placeholder="请输入用户名" :prefix-icon="User" />
              </el-form-item>
              <el-form-item prop="password">
                <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" :prefix-icon="Lock" show-password @keyup.enter="handleLogin" />
              </el-form-item>
              <div class="forgot-pwd-tip">
                <el-popover trigger="click" :width="280" placement="top">
                  <template #reference>
                    <span class="forgot-link">忘记密码？</span>
                  </template>
                  <div style="line-height: 1.8; font-size: 13px;">
                    <p style="margin: 0 0 8px;"><strong>密码重置方式：</strong></p>
                    <p style="margin: 0;">1. 联系平台管理员，由管理员在后台为您重置密码</p>
                    <p style="margin: 0;">2. 如果您是管理员，请使用其他管理员账号登录后在「用户管理」中重置</p>
                  </div>
                </el-popover>
              </div>
              <el-button type="primary" size="large" class="submit-btn" :loading="loading" native-type="submit">
                <span v-if="!loading">登录</span>
                <span v-else>验证中...</span>
                <ArrowRight v-if="!loading" :size="16" class="btn-icon" />
              </el-button>
            </el-form>
            <div class="form-footer" v-if="regConfig.allow_registration">
              没有账号？ <a @click.prevent="activeTab = 'register'">立即注册</a>
            </div>
            <div class="form-footer" v-else>
              <span class="footer-muted">注册已关闭，请联系管理员分配账号</span>
            </div>
          </div>

          <!-- Register Form -->
          <div v-else class="form-card" key="register">
            <div class="form-header">
              <h2>创建新账号</h2>
              <p>加入企业多模态知识协作共享服务平台，开启智能检索之旅</p>
            </div>
            <el-form :model="registerForm" :rules="registerRules" ref="registerRef" @submit.prevent="handleRegister" size="large" class="custom-form">
              <el-form-item prop="username">
                <el-input v-model="registerForm.username" placeholder="用户名" :prefix-icon="User" />
              </el-form-item>
              <el-form-item prop="email">
                <el-input v-model="registerForm.email" placeholder="邮箱地址" :prefix-icon="Message" />
              </el-form-item>
              <el-form-item prop="password">
                <el-input v-model="registerForm.password" type="password" placeholder="设置密码 (字母+数字，至少8位)" :prefix-icon="Lock" show-password />
              </el-form-item>
              <el-form-item prop="confirmPassword">
                <el-input v-model="registerForm.confirmPassword" type="password" placeholder="确认密码" :prefix-icon="Lock" show-password />
              </el-form-item>
              <el-form-item v-if="regConfig.require_invite_code" prop="invite_code">
                <el-input v-model="registerForm.invite_code" placeholder="邀请码" :prefix-icon="Document" />
              </el-form-item>
              <el-button type="primary" size="large" class="submit-btn" :loading="loading" native-type="submit">
                <span v-if="!loading">创建账号</span>
                <span v-else>注册中...</span>
                <ArrowRight v-if="!loading" :size="16" class="btn-icon" />
              </el-button>
            </el-form>
            <div class="form-footer">
              已有账号？ <a @click.prevent="activeTab = 'login'">返回登录</a>
            </div>
          </div>

        </transition>
      </div>
    </div>

    <!-- Forced password change dialog -->
    <el-dialog v-model="showForceChange" title="安全提示" width="400" :close-on-click-modal="false" :close-on-press-escape="false" :show-close="false" class="modern-dialog">
      <div class="dialog-desc">
        <ShieldAlert :size="20" style="color: var(--el-color-warning); margin-bottom: 12px" />
        <p>您正在使用初始默认密码。<br/>为了保障账户安全，请立即设置一个新密码。</p>
      </div>
      <el-form :model="forceChangeForm" :rules="forceChangeRules" ref="forceChangeRef" label-position="top">
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="forceChangeForm.newPassword" type="password" placeholder="至少 8 位，包含字母和数字" show-password />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input v-model="forceChangeForm.confirmPassword" type="password" placeholder="请再次输入新密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" size="large" style="width: 100%" :loading="forceChangeLoading" @click="handleForceChange">
          确认并进入系统
        </el-button>
      </template>
    </el-dialog>

    <!-- 2FA Verification Dialog -->
    <el-dialog v-model="twoFA.show" title="双因素认证" width="380" :close-on-click-modal="false" class="modern-dialog">
      <div style="text-align: center; margin-bottom: 20px;">
        <p style="font-size: 14px; color: var(--el-text-color-secondary);">
          请输入身份验证器 App 中的 6 位动态验证码
        </p>
      </div>
      <el-form @submit.prevent="handle2FAVerify">
        <el-form-item>
          <el-input v-model="twoFA.code" placeholder="000000" maxlength="6"
            style="font-size: 24px; text-align: center; letter-spacing: 8px;" size="large"
            @keyup.enter="handle2FAVerify" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="twoFA.show = false" size="large" style="width: 48%;">取消</el-button>
        <el-button type="primary" size="large" style="width: 48%;" :loading="twoFA.verifying"
          :disabled="twoFA.code.length !== 6" @click="handle2FAVerify">验证</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, BrainCircuit, Database, ArrowRight, ShieldAlert } from 'lucide-vue-next'
import { User, Lock, Message, Document } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { APP_VERSION } from '../../version'
import { login, register } from '../../api/auth'
import { useUserStore } from '../../stores/user'
import request from '../../utils/request'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeTab = ref(route.query.register === '1' ? 'register' : 'login')
const loading = ref(false)
const loginRef = ref<FormInstance>()
const registerRef = ref<FormInstance>()
const regConfig = reactive({ allow_registration: false, require_invite_code: false, loaded: false })

onMounted(async () => {
  try {
    const res: any = await request.get('/auth/register-config')
    regConfig.allow_registration = res.allow_registration ?? false
    regConfig.require_invite_code = res.require_invite_code ?? false
    regConfig.loaded = true
  } catch {
    regConfig.allow_registration = false
    regConfig.loaded = true
  }
})

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', email: '', password: '', confirmPassword: '', invite_code: '' })

const validatePasswordStrength = (_rule: any, value: string, callback: Function) => {
  if (!value) return callback()
  if (value.length < 8) return callback(new Error('密码长度不能少于 8 位'))
  if (!/[A-Za-z]/.test(value)) return callback(new Error('密码必须包含至少一个字母'))
  if (!/\d/.test(value)) return callback(new Error('密码必须包含至少一个数字'))
  callback()
}
const validateConfirm = (_rule: any, value: string, callback: Function) => {
  if (value !== registerForm.password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const loginRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
const registerRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 50, message: '长度 2 到 50 个字符', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email' as const, message: '请输入正确的邮箱格式', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { validator: validatePasswordStrength, trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

const showForceChange = ref(false)
const forceChangeLoading = ref(false)
const forceChangeRef = ref<FormInstance>()
const forceChangeForm = reactive({ newPassword: '', confirmPassword: '' })
const forceOldPassword = ref('')
const validateForceConfirm = (_rule: any, value: string, callback: Function) => {
  if (value !== forceChangeForm.newPassword) callback(new Error('两次输入的密码不一致'))
  else callback()
}
const forceChangeRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { validator: validatePasswordStrength, trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateForceConfirm, trigger: 'blur' },
  ],
}

async function handleForceChange() {
  try { await forceChangeRef.value?.validate() } catch { return }
  forceChangeLoading.value = true
  try {
    await request.post('/auth/change-password', {
      old_password: forceOldPassword.value,
      new_password: forceChangeForm.newPassword,
    })
    ElMessage.success('密码修改成功')
    showForceChange.value = false
    router.push('/')
  } catch {
    // error shown by interceptor
  } finally {
    forceChangeLoading.value = false
  }
}

const twoFA = reactive({ show: false, tempToken: '', code: '', verifying: false })

async function handleLogin() {
  try {
    await loginRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const res: any = await login(loginForm)
    if (res.requires_2fa && res.temp_token) {
      twoFA.tempToken = res.temp_token
      twoFA.code = ''
      twoFA.show = true
      loading.value = false
      return
    }
    _completeLogin(res)
  } catch {
    // error message already shown by axios interceptor
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  try {
    await registerRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await register({
      username: registerForm.username,
      email: registerForm.email,
      password: registerForm.password,
      invite_code: registerForm.invite_code || undefined,
    })
    ElMessage.success('注册成功，请登录')
    activeTab.value = 'login'
    loginForm.username = registerForm.username
  } catch {
    // error message already shown by axios interceptor
  } finally {
    loading.value = false
  }
}

function _completeLogin(res: any) {
  userStore.setToken(res.access_token)
  if (res.refresh_token) userStore.setRefreshToken(res.refresh_token)
  userStore.setUserInfo(res.user)
  if (res.user?.must_change_password) {
    forceOldPassword.value = loginForm.password
    showForceChange.value = true
    ElMessage.warning('请先修改默认密码')
  } else {
    ElMessage.success('登录成功')
    const pendingInvite = sessionStorage.getItem('pendingInvite')
    if (pendingInvite) {
      router.push(`/invite/${pendingInvite}`)
    } else {
      router.push('/')
    }
  }
}

async function handle2FAVerify() {
  if (twoFA.code.length !== 6) return
  twoFA.verifying = true
  try {
    const res: any = await request.post('/auth/2fa/verify', {
      temp_token: twoFA.tempToken,
      code: twoFA.code,
    })
    twoFA.show = false
    _completeLogin(res)
  } catch { /* interceptor handles */ }
  finally { twoFA.verifying = false }
}
</script>

<style scoped>
/* ══════════════════════════════════════════
   Modern Glassmorphism Login Style
   ══════════════════════════════════════════ */

.login-wrapper {
  position: relative;
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f3f4f6;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

/* ── Dynamic Background Shapes ── */
.bg-shapes {
  position: absolute;
  inset: 0;
  overflow: hidden;
  z-index: 0;
  pointer-events: none;
}

.shape {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.6;
  animation: float 20s infinite alternate ease-in-out;
}

.shape-1 {
  width: 500px;
  height: 500px;
  background: #3b82f6; /* Blue */
  top: -100px;
  left: -100px;
  animation-delay: 0s;
}

.shape-2 {
  width: 600px;
  height: 600px;
  background: #8b5cf6; /* Light Blue/Purple */
  bottom: -200px;
  right: -100px;
  animation-delay: -5s;
}

.shape-3 {
  width: 400px;
  height: 400px;
  background: #10b981; /* Teal/Green */
  top: 40%;
  left: 40%;
  animation-delay: -10s;
  opacity: 0.4;
}

@keyframes float {
  0% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -50px) scale(1.1); }
  66% { transform: translate(-30px, 30px) scale(0.9); }
  100% { transform: translate(0, 0) scale(1); }
}

/* ── Main Container ── */
.login-container {
  display: flex;
  width: 1000px;
  height: 600px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border-radius: 24px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255,255,255,0.5);
  overflow: hidden;
  z-index: 1;
  border: 1px solid rgba(255, 255, 255, 0.4);
  animation: slideUpFade 0.8s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes slideUpFade {
  0% { opacity: 0; transform: translateY(40px); }
  100% { opacity: 1; transform: translateY(0); }
}

/* ── Left Hero Section ── */
.hero-section {
  flex: 1.2;
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  color: #fff;
  padding: 60px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  position: relative;
}

.hero-section::after {
  content: '';
  position: absolute;
  inset: 0;
  background: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCI+PGNpcmNsZSBjeD0iMiIgY3k9IjIiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=') repeat;
  opacity: 0.5;
  pointer-events: none;
}

.hero-content {
  position: relative;
  z-index: 2;
}

.brand-logo {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 32px;
  overflow: hidden;
  box-shadow: 0 12px 24px rgba(13, 143, 215, 0.32);
}

.brand-logo-img {
  width: 100%;
  height: 100%;
  display: block;
}

.hero-title {
  font-size: 28px;
  font-weight: 800;
  line-height: 1.25;
  letter-spacing: 0;
  margin: 0 0 12px 0;
  background: linear-gradient(to right, #ffffff, #cbd5e1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-subtitle {
  font-size: 16px;
  color: #94a3b8;
  margin-bottom: 48px;
  line-height: 1.6;
}

.feature-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 15px;
  color: #e2e8f0;
  font-weight: 500;
  transition: transform 0.3s ease;
}

.feature-item:hover {
  transform: translateX(8px);
}

.feature-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #60a5fa;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.hero-footer {
  position: relative;
  z-index: 2;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #64748b;
}

.version-tag {
  background: rgba(255, 255, 255, 0.1);
  padding: 4px 10px;
  border-radius: 12px;
  font-family: monospace;
}

/* ── Right Form Section ── */
.form-section {
  flex: 1;
  padding: 60px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  position: relative;
}

.form-card {
  width: 100%;
  max-width: 340px;
  margin: 0 auto;
}

.form-header {
  margin-bottom: 36px;
}

.form-header h2 {
  font-size: 26px;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 8px 0;
  letter-spacing: -0.5px;
}

.form-header p {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

/* ── Custom Form Styles ── */
.custom-form :deep(.el-input__wrapper) {
  background-color: rgba(255, 255, 255, 0.6) !important;
  border: 1px solid #e2e8f0;
  box-shadow: none !important;
  border-radius: 10px;
  height: 48px;
  transition: all 0.2s ease;
}

.custom-form :deep(.el-input__wrapper:hover),
.custom-form :deep(.el-input__wrapper.is-focus) {
  background-color: #fff !important;
  border-color: #3b82f6;
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1) !important;
}

.custom-form :deep(.el-input__prefix-inner) {
  color: #94a3b8;
}

.custom-form :deep(.el-form-item) {
  margin-bottom: 24px;
}

.submit-btn {
  width: 100%;
  height: 48px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  margin-top: 8px;
  background: #3b82f6;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.3s ease;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.submit-btn:hover {
  background: #2563eb;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.4);
}

.submit-btn:active {
  transform: translateY(0);
}

.btn-icon {
  transition: transform 0.3s ease;
}

.submit-btn:hover .btn-icon {
  transform: translateX(4px);
}

.form-footer {
  margin-top: 32px;
  text-align: center;
  font-size: 14px;
  color: #64748b;
}

.form-footer a {
  color: #3b82f6;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: color 0.2s;
}

.form-footer a:hover {
  color: #1d4ed8;
  text-decoration: underline;
}

.forgot-pwd-tip {
  margin-top: -8px;
  margin-bottom: 8px;
  font-size: 13px;
}
.forgot-link {
  color: #94a3b8;
  cursor: help;
}
.forgot-link:hover {
  color: #64748b;
}

.footer-muted {
  color: #94a3b8;
}

/* ── Vue Transitions ── */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateX(15px);
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateX(-15px);
}

/* ── Modern Dialog ── */
.modern-dialog :deep(.el-dialog) {
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
}

.modern-dialog :deep(.el-dialog__header) {
  padding: 24px 24px 0;
  margin: 0;
  border-bottom: none;
}

.modern-dialog :deep(.el-dialog__title) {
  font-weight: 700;
  font-size: 18px;
}

.modern-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
}

.dialog-desc {
  background: #fffbeb;
  border: 1px solid #fef3c7;
  padding: 16px;
  border-radius: 12px;
  margin-bottom: 24px;
  text-align: center;
}

.dialog-desc p {
  margin: 0;
  font-size: 14px;
  color: #92400e;
  line-height: 1.5;
}

/* ── Responsive ── */
@media (max-width: 900px) {
  .login-container {
    width: 90%;
    height: auto;
    min-height: 500px;
    flex-direction: column;
  }
  
  .hero-section {
    display: none;
  }
  
  .form-section {
    padding: 40px 24px;
  }
}
</style>
