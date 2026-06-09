<template>
  <div class="login-page">
    <div class="login-left">
      <div class="brand-content">
        <div class="brand-logo">
          <div class="logo-mark">
            <svg width="36" height="36" viewBox="0 0 48 46" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M25.946 44.938c-.664.845-2.021.375-2.021-.698V33.937a2.26 2.26 0 0 0-2.262-2.262H10.287c-.92 0-1.456-1.04-.92-1.788l7.48-10.471c1.07-1.497 0-3.578-1.842-3.578H1.237c-.92 0-1.456-1.04-.92-1.788L10.013.474c.214-.297.556-.474.92-.474h28.894c.92 0 1.456 1.04.92 1.788l-7.48 10.471c-1.07 1.498 0 3.579 1.842 3.579h11.377c.943 0 1.473 1.088.89 1.83L25.947 44.94z" fill="rgba(255,255,255,0.95)"/>
            </svg>
          </div>
          <span class="brand-name">知枢</span>
        </div>
        <h1 class="brand-title">知枢管理后台</h1>
        <p class="brand-desc">企业级 RAG 解决方案，赋能知识管理与智能检索</p>
        <div class="feature-list">
          <div class="feature-item">
            <div class="feature-dot"></div>
            <span>统一设备管理与监控</span>
          </div>
          <div class="feature-item">
            <div class="feature-dot"></div>
            <span>智能技能市场与分发</span>
          </div>
          <div class="feature-item">
            <div class="feature-dot"></div>
            <span>多维度数据分析洞察</span>
          </div>
        </div>
      </div>
      <div class="brand-footer">
        <span>&copy; {{ new Date().getFullYear() }} 知枢平台 · 版权所有</span>
      </div>
    </div>

    <div class="login-right">
      <div class="login-form-wrapper">
        <div class="login-form-header">
          <h2>欢迎回来</h2>
          <p>请输入您的管理员账号登录控制台</p>
        </div>

        <el-form :model="form" :rules="formRules" ref="formRef" @submit.prevent="handleLogin" class="login-form">
          <div class="form-field">
            <label class="form-label">用户名</label>
            <el-form-item prop="username">
              <el-input
                v-model="form.username"
                placeholder="请输入用户名"
                size="large"
                :prefix-icon="User"
                clearable
              />
            </el-form-item>
          </div>
          <div class="form-field">
            <label class="form-label">密码</label>
            <el-form-item prop="password">
              <el-input
                v-model="form.password"
                type="password"
                placeholder="请输入密码"
                size="large"
                :prefix-icon="Lock"
                show-password
                @keydown.enter="handleLogin"
              />
            </el-form-item>
          </div>
          <el-form-item>
            <el-button
              type="primary"
              size="large"
              class="login-btn"
              :loading="loading"
              @click="handleLogin"
            >
              {{ loading ? '登录中...' : '登 录' }}
            </el-button>
          </el-form-item>
        </el-form>

        <div class="login-footer-tip">
          <el-icon><InfoFilled /></el-icon>
          <span>仅限管理员账号登录</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { User, Lock, InfoFilled } from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })

const formRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 50, message: '用户名长度 2-50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
}

async function handleLogin() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const res = await userStore.login(form.username, form.password)
    if (!['super_admin', 'admin', 'org_admin'].includes(res.user.role)) {
      userStore.logout()
      ElMessage.error('仅管理员可登录后台')
      return
    }
    router.push('/dashboard')
  } catch {
    /* interceptor handles */
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  background: #FFFFFF;
}

.login-left {
  flex: 0 0 45%;
  background: linear-gradient(160deg, #0A1628 0%, #0F2847 35%, #1A4AD8 70%, #5B8DEF 100%);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 48px;
  position: relative;
  overflow: hidden;
}

.login-left::before {
  content: '';
  position: absolute;
  top: -20%;
  right: -15%;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(255,255,255,0.06) 0%, transparent 70%);
  border-radius: 50%;
}

.login-left::after {
  content: '';
  position: absolute;
  bottom: -10%;
  left: -10%;
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(255,255,255,0.04) 0%, transparent 70%);
  border-radius: 50%;
}

.brand-content { position: relative; z-index: 1; margin-top: 20%; }

.brand-logo {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 40px;
}

.logo-mark {
  width: 52px;
  height: 52px;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-name {
  font-size: 22px;
  font-weight: 700;
  color: #FFFFFF;
  letter-spacing: 0.04em;
}

.brand-title {
  font-size: 36px;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.3;
  margin-bottom: 16px;
  letter-spacing: -0.02em;
}

.brand-desc {
  font-size: 16px;
  color: rgba(255, 255, 255, 0.7);
  line-height: 1.6;
  margin-bottom: 48px;
}

.feature-list { display: flex; flex-direction: column; gap: 18px; }

.feature-item {
  display: flex;
  align-items: center;
  gap: 14px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 15px;
  font-weight: 500;
}

.feature-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.5);
  flex-shrink: 0;
}

.brand-footer {
  position: relative;
  z-index: 1;
  color: rgba(255, 255, 255, 0.4);
  font-size: 13px;
}

.login-right {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  background: #FAFBFC;
}

.login-form-wrapper {
  width: 100%;
  max-width: 400px;
}

.login-form-header {
  margin-bottom: 40px;
}

.login-form-header h2 {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
  letter-spacing: -0.02em;
}

.login-form-header p {
  font-size: 15px;
  color: var(--text-secondary);
}

.login-form { display: flex; flex-direction: column; gap: 4px; }

.form-field { margin-bottom: 20px; }

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.login-form :deep(.el-input__wrapper) {
  padding: 4px 16px;
  border-radius: 10px !important;
  box-shadow: 0 0 0 1px #E2E8F0 inset !important;
  background: #FFFFFF;
  transition: all 0.2s;
}

.login-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #CBD5E1 inset !important;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1.5px var(--brand-primary) inset, 0 0 0 4px rgba(124, 58, 237, 0.1) !important;
}

.login-form :deep(.el-input__inner) { font-size: 15px; }

.login-form :deep(.el-input__prefix .el-icon) {
  color: var(--text-tertiary);
  font-size: 18px;
}

.login-btn {
  width: 100%;
  height: 48px !important;
  font-size: 16px !important;
  font-weight: 600 !important;
  border-radius: 10px !important;
  background: var(--brand-primary) !important;
  border-color: var(--brand-primary) !important;
  margin-top: 12px;
  letter-spacing: 0.08em;
  transition: all 0.25s;
}

.login-btn:hover {
  background: var(--brand-primary-hover) !important;
  border-color: var(--brand-primary-hover) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(124, 58, 237, 0.35);
}

.login-btn:active { transform: translateY(0); }

.login-footer-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 24px;
  padding: 12px 16px;
  background: var(--brand-primary-bg);
  border-radius: 10px;
  font-size: 13px;
  color: var(--brand-primary);
}

@media (max-width: 768px) {
  .login-left { display: none; }
  .login-right { padding: 24px; }
}
</style>
