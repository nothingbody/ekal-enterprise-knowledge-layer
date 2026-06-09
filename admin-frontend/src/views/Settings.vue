<template>
  <div class="settings-page">
    <div class="page-header">
      <div>
        <h2>系统设置</h2>
        <p class="page-subtitle">平台全局配置管理</p>
      </div>
    </div>

    <div class="settings-grid">
      <el-card v-loading="loading" class="settings-card">
        <template #header>
          <div class="card-title-row">
            <div class="card-icon purple"><el-icon :size="18"><Lock /></el-icon></div>
            <div>
              <div class="card-title">注册与访问控制</div>
              <div class="card-desc">管理用户注册与邀请码策略</div>
            </div>
          </div>
        </template>
        <el-form label-position="top">
          <el-form-item>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-label">开放注册</span>
                <span class="setting-hint">{{ form.allow_registration ? '任何人可注册账号' : '仅管理员可创建账号' }}</span>
              </div>
              <el-switch v-model="form.allow_registration" />
            </div>
          </el-form-item>

          <el-form-item>
            <div class="setting-row">
              <div class="setting-info">
                <span class="setting-label">邀请码</span>
                <span class="setting-hint">设置后注册时必须输入正确的邀请码</span>
              </div>
            </div>
            <el-input
              v-model="form.invite_code"
              placeholder="留空则不需要邀请码"
              clearable
              style="margin-top: 8px;"
            />
          </el-form-item>

          <div class="form-actions">
            <el-button type="primary" :loading="saving" @click="saveSettings" round>保存设置</el-button>
          </div>
        </el-form>
      </el-card>

      <el-card class="settings-card">
        <template #header>
          <div class="card-title-row">
            <div class="card-icon blue"><el-icon :size="18"><InfoFilled /></el-icon></div>
            <div>
              <div class="card-title">服务信息</div>
              <div class="card-desc">当前运行环境与配置</div>
            </div>
          </div>
        </template>
        <div class="info-list">
          <div class="info-item">
            <span class="info-label">应用名称</span>
            <span class="info-value">{{ info.app_name || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">CORS 来源</span>
            <code class="info-code">{{ info.cors_origins || '-' }}</code>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../utils/request'

const loading = ref(false)
const saving = ref(false)
const form = reactive({ allow_registration: true, invite_code: '' })
const info = reactive({ app_name: '', cors_origins: '' })

async function loadSettings() {
  loading.value = true
  try {
    const res: any = await request.get('/admin/settings')
    form.allow_registration = res.allow_registration ?? true
    form.invite_code = res.invite_code || ''
    info.app_name = res.app_name || ''
    info.cors_origins = res.cors_origins || ''
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = true
  try {
    await request.put('/admin/settings', {
      allow_registration: form.allow_registration,
      invite_code: form.invite_code,
    })
    ElMessage.success('设置已保存')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<style scoped>
.settings-page { max-width: 800px; }

.page-subtitle { font-size: 14px; color: var(--text-tertiary); margin-top: 4px; }

.settings-grid { display: flex; flex-direction: column; gap: 16px; }

.settings-card :deep(.el-card__header) { padding: 20px 24px !important; }
.settings-card :deep(.el-card__body) { padding: 24px !important; }

.card-title-row { display: flex; align-items: center; gap: 14px; }

.card-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.card-icon.purple { background: var(--brand-primary-light); color: var(--brand-primary); }
.card-icon.blue { background: #DBEAFE; color: #3B82F6; }

.card-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.card-desc { font-size: 13px; color: var(--text-tertiary); margin-top: 2px; }

.setting-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.setting-label { font-size: 14px; font-weight: 600; color: var(--text-primary); display: block; }
.setting-hint { font-size: 12px; color: var(--text-tertiary); display: block; margin-top: 2px; }

.form-actions {
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--border-light);
}

.info-list { display: flex; flex-direction: column; gap: 16px; }

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-light);
}

.info-item:last-child { border-bottom: none; padding-bottom: 0; }

.info-label { font-size: 14px; color: var(--text-secondary); }
.info-value { font-size: 14px; font-weight: 600; color: var(--text-primary); }

.info-code {
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--text-secondary);
  background: #F8FAFC;
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border-light);
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
