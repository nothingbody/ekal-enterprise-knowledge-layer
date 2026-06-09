<template>
  <div class="settings-page">
    <div class="page-header">
      <h2>个人设置</h2>
    </div>

    <el-tabs v-model="activeTab" class="settings-tabs">
      <!-- ═══ 基本设置 ═══ -->
      <el-tab-pane label="基本设置" name="basic">
        <el-row :gutter="20">
          <el-col :xs="24" :md="12">
            <el-card>
              <template #header>个人信息</template>
              <el-form label-width="80px" style="max-width: 400px;">
                <el-form-item label="用户名">
                  <el-input :model-value="userInfo.username" disabled />
                  <div class="field-hint">用户名注册后不可修改</div>
                </el-form-item>
                <el-form-item label="昵称">
                  <el-input v-model="profileForm.nickname" placeholder="设置一个昵称（可选）" maxlength="100" clearable />
                </el-form-item>
                <el-form-item label="角色">
                  <el-tag :type="userInfo.role === 'admin' ? 'danger' : 'info'" size="small">
                    {{ userInfo.role === 'admin' ? '管理员' : '普通用户' }}
                  </el-tag>
                </el-form-item>
                <el-form-item label="邮箱">
                  <el-input v-model="profileForm.email" placeholder="输入新邮箱" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="handleUpdateProfile" :loading="profileSaving">保存</el-button>
                </el-form-item>
              </el-form>
            </el-card>
          </el-col>

          <el-col :xs="24" :md="12">
            <el-card>
              <template #header>修改密码</template>
              <el-form :model="pwdForm" :rules="pwdRules" ref="pwdRef" label-width="80px" style="max-width: 400px;">
                <el-form-item label="原密码" prop="old_password">
                  <el-input v-model="pwdForm.old_password" type="password" show-password />
                </el-form-item>
                <el-form-item label="新密码" prop="new_password">
                  <el-input v-model="pwdForm.new_password" type="password" show-password />
                </el-form-item>
                <el-form-item label="确认密码" prop="confirm_password">
                  <el-input v-model="pwdForm.confirm_password" type="password" show-password />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="handleChangePwd" :loading="pwdLoading">确认修改</el-button>
                </el-form-item>
              </el-form>
            </el-card>
          </el-col>
        </el-row>

        <!-- 2FA -->
        <el-row :gutter="20" style="margin-top: 20px;">
          <el-col :xs="24" :md="12">
            <el-card>
              <template #header>双因素认证 (2FA)</template>
              <div v-if="userInfo.totp_enabled" style="margin-bottom: 16px;">
                <el-tag type="success" effect="light" size="large" round>已启用</el-tag>
                <p style="font-size: 13px; color: var(--el-text-color-secondary); margin-top: 12px;">
                  每次登录需要输入身份验证器 App 中的 6 位动态验证码。
                </p>
                <el-button type="danger" plain @click="handleDisable2FA" :loading="twoFA.disabling" style="margin-top: 12px;">关闭 2FA</el-button>
              </div>
              <div v-else>
                <p style="font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 12px;">
                  启用后每次登录需额外输入动态验证码，大幅提升账号安全性。
                </p>
                <el-button type="primary" @click="handleSetup2FA" :loading="twoFA.setting">启用 2FA</el-button>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <el-row v-if="isDesktop" :gutter="20" style="margin-top: 20px;">
          <el-col :xs="24" :md="12">
            <el-card>
              <template #header>局域网共享</template>
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px;">
                <div>
                  <div style="font-weight: 500;">允许同一网络访问本机知识库</div>
                  <div style="font-size: 13px; color: var(--el-text-color-secondary); margin-top: 6px;">
                    开启后重启客户端生效，其他同网络设备可通过LAN邀请链接访问本机服务。
                  </div>
                </div>
                <el-switch v-model="lanSharing.configured_enabled" :loading="lanSharing.loading" @change="handleLanSharingChange" />
              </div>
              <el-alert
                v-if="lanSharing.requires_restart"
                title="设置已保存，重启客户端后生效"
                type="warning"
                show-icon
                :closable="false"
                style="margin-top: 12px;"
              />
            </el-card>
          </el-col>
        </el-row>

        <!-- 2FA Setup Dialog -->
        <el-dialog v-model="twoFA.showSetup" title="设置双因素认证" width="440px" :close-on-click-modal="false">
          <div v-if="twoFA.uri" style="text-align: center; margin-bottom: 20px;">
            <p style="font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 16px;">
              使用 Google Authenticator、Microsoft Authenticator 或其他身份验证器 App 扫描二维码：
            </p>
            <div style="background: #fff; display: inline-block; padding: 16px; border-radius: 12px; border: 1px solid var(--el-border-color);">
              <img v-if="twoFA.qrDataUrl" :src="twoFA.qrDataUrl" alt="QR Code" style="width: 200px; height: 200px;" />
              <div v-else style="width: 200px; height: 200px; display: flex; align-items: center; justify-content: center; color: #999;">生成中...</div>
            </div>
            <div style="margin-top: 12px;">
              <p style="font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px;">或手动输入密钥：</p>
              <code style="font-size: 14px; letter-spacing: 2px; user-select: all; background: var(--el-fill-color); padding: 6px 12px; border-radius: 6px;">{{ twoFA.secret }}</code>
            </div>
          </div>
          <el-form label-width="80px">
            <el-form-item label="验证码">
              <el-input v-model="twoFA.verifyCode" placeholder="输入 6 位验证码" maxlength="6" style="width: 200px;" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="twoFA.showSetup = false">取消</el-button>
            <el-button type="primary" @click="handleEnable2FA" :loading="twoFA.enabling" :disabled="twoFA.verifyCode.length !== 6">验证并启用</el-button>
          </template>
        </el-dialog>

        <!-- Danger zone -->
        <el-row :gutter="20" style="margin-top: 20px;">
          <el-col :span="24">
            <el-card class="danger-zone-card">
              <template #header><span style="color: var(--el-color-danger);">危险操作</span></template>
              <p style="font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 16px;">
                注销账号后，所有数据将被永久删除，此操作不可恢复。
              </p>
              <el-button type="danger" @click="showDeleteAccount = true">注销账号</el-button>
            </el-card>
          </el-col>
        </el-row>

        <!-- Data backup & restore (admin only) -->
        <el-row v-if="userInfo.role === 'admin'" :gutter="20" style="margin-top: 20px;">
          <el-col :xs="24" :md="12">
            <el-card>
              <template #header>数据备份</template>
              <p style="font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 16px;">
                导出包含数据库、向量库和上传文件的完整备份。
              </p>
              <el-button type="primary" @click="handleBackup" :loading="backupLoading">
                下载备份
              </el-button>
            </el-card>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-card>
              <template #header>数据恢复</template>
              <p style="font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 16px;">
                从备份文件恢复数据。恢复后需要重启应用才能生效。
              </p>
              <el-upload
                :auto-upload="false"
                :show-file-list="false"
                accept=".zip"
                :on-change="handleRestoreFileChange"
              >
                <el-button type="warning" :loading="restoreLoading">选择备份文件恢复</el-button>
              </el-upload>
              <div v-if="restoreResult" style="margin-top: 12px;">
                <el-alert :title="restoreResult.message" type="success" show-icon :closable="false" />
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ═══ AI 记忆 ═══ -->
      <el-tab-pane label="AI 记忆" name="memories">
        <el-card>
          <template #header>
            <div class="card-header-row">
              <span>AI 记忆管理</span>
              <div class="card-header-actions">
                <el-select
                  v-model="memoryCategoryFilter"
                  placeholder="全部分类"
                  clearable
                  size="small"
                  style="width: 120px;"
                  @change="loadMemories(1)"
                >
                  <el-option label="全部" value="" />
                  <el-option label="偏好" value="preference" />
                  <el-option label="事实" value="fact" />
                  <el-option label="经验" value="insight" />
                  <el-option label="通用" value="general" />
                </el-select>
                <el-button size="small" @click="handleCleanupExpired" :loading="cleaningUp">
                  <Clock :size="14" :stroke-width="1.5" style="margin-right: 4px" />清理过期
                </el-button>
                <el-button size="small" @click="showAddMemory = true">
                  <Plus :size="14" :stroke-width="1.5" style="margin-right: 4px" />添加记忆
                </el-button>
                <el-button size="small" type="danger" @click="handleClearMemories" :disabled="!memories.length">
                  <Trash2 :size="14" :stroke-width="1.5" style="margin-right: 4px" />清空全部
                </el-button>
              </div>
            </div>
          </template>
          <p class="section-desc">
            AI 会自动从对话中提取值得记住的信息。你也可以手动添加或删除记忆。这些记忆会在后续对话中被用作上下文参考。
          </p>

          <div v-if="memoriesLoading" v-loading="true" style="min-height: 120px;"></div>
          <div v-else-if="!memories.length" class="empty-state">
            <Brain :size="40" :stroke-width="1" style="color: var(--el-text-color-placeholder); margin-bottom: 8px;" />
            <p>暂无记忆记录</p>
          </div>
          <div v-else class="memory-list">
            <div v-for="mem in memories" :key="mem.id" class="memory-card">
              <div class="memory-card-top">
                <div class="memory-badges">
                  <el-tag size="small" :type="memoryCategoryType(mem.category)">
                    {{ memoryCategoryLabel(mem.category) }}
                  </el-tag>
                  <el-tag
                    size="small"
                    :type="mem.memory_type === 'persistent' ? 'success' : 'warning'"
                    effect="plain"
                  >
                    {{ mem.memory_type === 'persistent' ? '永久' : '临时' }}
                  </el-tag>
                </div>
                <div class="memory-card-actions">
                  <el-button link type="primary" size="small" @click="openEditMemory(mem)">
                    <Pencil :size="13" :stroke-width="1.5" />
                  </el-button>
                  <el-button link type="danger" size="small" @click="handleDeleteMemory(mem.id)">
                    <Trash2 :size="13" :stroke-width="1.5" />
                  </el-button>
                </div>
              </div>
              <div class="memory-card-content">{{ mem.content }}</div>
              <div class="memory-card-footer">
                <span class="memory-stars" :title="`重要性: ${mem.importance ?? 1}`">
                  <Star
                    v-for="s in 5" :key="s"
                    :size="13"
                    :stroke-width="1.5"
                    :class="{ filled: s <= Math.round(mem.importance ?? 1) }"
                  />
                </span>
                <span class="memory-stat">
                  <Eye :size="12" :stroke-width="1.5" />
                  {{ mem.access_count ?? 0 }}
                </span>
                <span v-if="mem.expires_at" class="memory-stat memory-expires">
                  <Clock :size="12" :stroke-width="1.5" />
                  {{ formatDate(mem.expires_at) }}
                </span>
                <span v-if="mem.created_at" class="memory-stat">
                  {{ formatDate(mem.created_at) }}
                </span>
              </div>
            </div>
          </div>
          <div v-if="memoryTotal > memories.length" style="text-align: center; margin-top: 16px;">
            <el-button link size="small" @click="loadMoreMemories">加载更多</el-button>
          </div>
        </el-card>
      </el-tab-pane>

      <!-- ═══ 用户画像 ═══ -->
      <el-tab-pane label="用户画像" name="profile">
        <el-card>
          <template #header>
            <div class="card-header-row">
              <span>用户画像</span>
              <el-button size="small" @click="handleRegenerateProfile" :loading="profileLoading">
                <RefreshCw :size="14" :stroke-width="1.5" style="margin-right: 4px" />重新生成
              </el-button>
            </div>
          </template>

          <div v-if="profileLoading" v-loading="true" style="min-height: 120px;"></div>
          <div v-else-if="!userProfile" class="empty-state">
            <User :size="40" :stroke-width="1" style="color: var(--el-text-color-placeholder); margin-bottom: 8px;" />
            <p>暂无用户画像数据</p>
            <el-button type="primary" size="small" style="margin-top: 12px;" @click="handleRegenerateProfile">
              生成画像
            </el-button>
          </div>
          <div v-else class="profile-content">
            <!-- Summary -->
            <div class="profile-section">
              <h4 class="profile-section-title">
                <FileText :size="15" :stroke-width="1.5" />
                概要
              </h4>
              <p class="profile-summary">{{ userProfile.summary || '暂无概要' }}</p>
            </div>

            <!-- Communication Style -->
            <div v-if="userProfile.communication_style" class="profile-section">
              <h4 class="profile-section-title">
                <MessageSquare :size="15" :stroke-width="1.5" />
                沟通风格
              </h4>
              <p class="profile-summary">{{ userProfile.communication_style }}</p>
            </div>

            <!-- Topics of Interest -->
            <div v-if="userProfile.topics_of_interest?.length" class="profile-section">
              <h4 class="profile-section-title">
                <Lightbulb :size="15" :stroke-width="1.5" />
                兴趣话题
              </h4>
              <div class="profile-tags">
                <el-tag
                  v-for="topic in userProfile.topics_of_interest"
                  :key="topic"
                  size="small"
                  effect="plain"
                  type="primary"
                >
                  {{ topic }}
                </el-tag>
              </div>
            </div>

            <!-- Expertise Areas -->
            <div v-if="userProfile.expertise_areas?.length" class="profile-section">
              <h4 class="profile-section-title">
                <Award :size="15" :stroke-width="1.5" />
                专业领域
              </h4>
              <div class="profile-tags">
                <el-tag
                  v-for="area in userProfile.expertise_areas"
                  :key="area"
                  size="small"
                  effect="plain"
                  type="success"
                >
                  {{ area }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>
      </el-tab-pane>

      <!-- ═══ 用量统计 ═══ -->
      <el-tab-pane label="用量统计" name="usage">
        <div v-loading="usageLoading">
          <div class="usage-stat-row">
            <div class="usage-stat-card">
              <div class="usage-stat-label">总 Token</div>
              <div class="usage-stat-value">{{ usageSummary.total_tokens?.toLocaleString() || 0 }}</div>
            </div>
            <div class="usage-stat-card">
              <div class="usage-stat-label">输入 Token</div>
              <div class="usage-stat-value">{{ usageSummary.total_input_tokens?.toLocaleString() || 0 }}</div>
            </div>
            <div class="usage-stat-card">
              <div class="usage-stat-label">输出 Token</div>
              <div class="usage-stat-value">{{ usageSummary.total_output_tokens?.toLocaleString() || 0 }}</div>
            </div>
            <div class="usage-stat-card">
              <div class="usage-stat-label">对话数</div>
              <div class="usage-stat-value">{{ usageSummary.conversation_count?.toLocaleString() || 0 }}</div>
            </div>
          </div>

          <el-card style="margin-bottom: 16px;">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>Token 趋势（近 30 天）</span>
                <span style="font-size: 12px; color: var(--el-text-color-secondary);">
                  合计 {{ usageTrend.reduce((s: number, d: any) => s + (d.tokens || 0), 0).toLocaleString() }} Token
                </span>
              </div>
            </template>
            <div v-if="usageTrend.length" class="usage-trend-chart">
              <div v-for="(d, i) in usageTrend" :key="d.date" class="usage-trend-bar-col" :style="{ animationDelay: i * 20 + 'ms' }">
                <div class="usage-trend-tooltip">{{ (d.tokens || 0).toLocaleString() }}</div>
                <div class="usage-trend-bar" :style="{ height: usageBarH(d.tokens) + '%' }"></div>
                <div class="usage-trend-label">{{ d.date?.slice?.(5) || '' }}</div>
              </div>
            </div>
            <el-empty v-else description="暂无用量数据" :image-size="60" />
          </el-card>

          <el-card v-if="usageSummary.by_model?.length">
            <template #header>按模型统计</template>
            <el-table :data="usageSummary.by_model" stripe size="small">
              <el-table-column prop="model_name" label="模型" min-width="140" />
              <el-table-column label="输入 Token" width="120">
                <template #default="{ row }">{{ row.input_tokens?.toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="输出 Token" width="120">
                <template #default="{ row }">{{ row.output_tokens?.toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="总 Token" width="120">
                <template #default="{ row }">{{ row.total_tokens?.toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="对话数" width="80">
                <template #default="{ row }">{{ row.conversations }}</template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- ═══ 关于 (桌面版) ═══ -->
      <el-tab-pane v-if="isDesktop" label="关于" name="about">
        <el-card>
          <template #header>版本信息</template>
          <div style="max-width: 400px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
              <span style="font-size: 14px; color: var(--text-secondary);">当前版本</span>
              <el-tag>v{{ desktopVersion || '...' }}</el-tag>
            </div>
            <el-button type="primary" @click="handleCheckForUpdates" :loading="checkingUpdate">
              检查更新
            </el-button>
            <span v-if="updateResult" style="margin-left: 12px; font-size: 13px; color: var(--text-secondary);">
              {{ updateResult }}
            </span>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- Add memory dialog -->
    <el-dialog v-model="showAddMemory" title="添加记忆" width="480px">
      <el-form label-width="60px">
        <el-form-item label="内容">
          <el-input v-model="newMemory.content" type="textarea" :rows="3" placeholder="输入你希望 AI 记住的信息..." maxlength="2000" show-word-limit />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="newMemory.category" style="width: 100%;">
            <el-option label="通用" value="general" />
            <el-option label="偏好" value="preference" />
            <el-option label="事实" value="fact" />
            <el-option label="经验" value="insight" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddMemory = false">取消</el-button>
        <el-button type="primary" @click="handleAddMemory" :loading="addingMemory" :disabled="!newMemory.content.trim()">保存</el-button>
      </template>
    </el-dialog>

    <!-- Edit memory dialog -->
    <el-dialog v-model="showEditMemory" title="编辑记忆" width="480px">
      <el-form label-width="60px">
        <el-form-item label="内容">
          <el-input v-model="editMemoryContent" type="textarea" :rows="3" maxlength="2000" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditMemory = false">取消</el-button>
        <el-button type="primary" @click="handleEditMemory" :loading="editingMemory" :disabled="!editMemoryContent.trim()">保存</el-button>
      </template>
    </el-dialog>

    <!-- Delete account dialog -->
    <el-dialog v-model="showDeleteAccount" title="注销账号" width="420px">
      <el-alert type="error" :closable="false" style="margin-bottom: 16px;">
        <template #title>此操作将永久删除你的账号及所有相关数据，不可恢复。</template>
      </el-alert>
      <el-form label-width="80px">
        <el-form-item label="确认密码">
          <el-input v-model="deleteAccountPwd" type="password" show-password placeholder="请输入当前密码以确认" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDeleteAccount = false">取消</el-button>
        <el-button type="danger" @click="handleDeleteAccount" :loading="deletingAccount" :disabled="!deleteAccountPwd">确认注销</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onActivated, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import {
  Plus, Trash2, Pencil, Star, Eye, Clock, Brain, RefreshCw,
  User, FileText, MessageSquare, Lightbulb, Award,
} from 'lucide-vue-next'
import { getMe, changePassword, deleteAccount } from '../../api/auth'
import {
  listMemories, createMemory, updateMemory, deleteMemory,
  clearAllMemories, getUserProfile, cleanupExpiredMemories,
} from '../../api/memories'
import request from '../../utils/request'
import { API_V1 } from '../../utils/apiBase'
import QRCode from 'qrcode'
import { useUserStore } from '../../stores/user'

const router = useRouter()
const userStore = useUserStore()

// ── Desktop detection ──
const isDesktop = !!(window as any).desktopAPI?.isDesktop
const desktopVersion = ref('')
const checkingUpdate = ref(false)
const updateResult = ref('')

async function loadDesktopVersion() {
  if (!isDesktop) return
  try {
    desktopVersion.value = await (window as any).desktopAPI.getVersion()
  } catch { /* not available */ }
}

async function handleCheckForUpdates() {
  checkingUpdate.value = true
  updateResult.value = ''
  try {
    const res = await (window as any).desktopAPI.checkForUpdates()
    if (res.updateAvailable) {
      updateResult.value = `发现新版本 v${res.version}`
    } else {
      updateResult.value = '已是最新版本'
    }
  } catch {
    updateResult.value = '检查失败，请检查网络连接'
  } finally {
    checkingUpdate.value = false
  }
}

const lanSharing = reactive({
  enabled: false,
  configured_enabled: false,
  requires_restart: false,
  loading: false,
})

async function loadLanSharing() {
  if (!isDesktop) return
  try {
    const res: any = await request.get('/system/lan-sharing', { _silentError: true } as any)
    lanSharing.enabled = !!res.enabled
    lanSharing.configured_enabled = !!res.configured_enabled
    lanSharing.requires_restart = !!res.requires_restart
  } catch { /* ignore */ }
}

async function handleLanSharingChange(value: string | number | boolean) {
  lanSharing.loading = true
  try {
    const res: any = await request.put('/system/lan-sharing', { enabled: !!value })
    lanSharing.enabled = !!res.enabled
    lanSharing.configured_enabled = !!res.configured_enabled
    lanSharing.requires_restart = !!res.requires_restart
    ElMessage.success(lanSharing.requires_restart ? '设置已保存，重启客户端后生效' : '局域网共享设置已更新')
  } catch {
    lanSharing.configured_enabled = lanSharing.enabled
  } finally {
    lanSharing.loading = false
  }
}

// ── Tab state ──
const activeTab = ref('basic')

// ── Usage stats ──
const usageLoading = ref(false)
const usageSummary = ref<any>({})
const usageTrend = ref<any[]>([])
const usageMaxTokens = computed(() => Math.max(...usageTrend.value.map((d: any) => d.tokens || 0), 1))
function usageBarH(v: number) { return usageMaxTokens.value === 0 ? 0 : Math.max((v / usageMaxTokens.value) * 100, v > 0 ? 4 : 0) }

async function loadUsageData() {
  usageLoading.value = true
  try {
    const [summary, trend] = await Promise.all([
      request.get('/chat/usage'),
      request.get('/chat/usage/trend', { params: { days: 30 } }),
    ])
    usageSummary.value = summary || {}
    usageTrend.value = (trend as any)?.trend || []
  } catch { /* interceptor handles */ }
  finally { usageLoading.value = false }
}

// ── User info ──
const userInfo = reactive({ username: '', email: '', role: '', totp_enabled: false })
const profileForm = reactive({ nickname: '', email: '' })
const profileSaving = ref(false)

const pwdRef = ref<FormInstance>()
const pwdLoading = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const validateNewPassword = (_rule: any, value: string, callback: Function) => {
  if (!value) return callback()
  if (value.length < 8) return callback(new Error('密码长度不能少于 8 位'))
  if (!/[A-Za-z]/.test(value)) return callback(new Error('密码必须包含至少一个字母'))
  if (!/\d/.test(value)) return callback(new Error('密码必须包含至少一个数字'))
  if (pwdForm.confirm_password) {
    pwdRef.value?.validateField('confirm_password')
  }
  callback()
}
const validateConfirmPassword = (_rule: any, value: string, callback: Function) => {
  if (!value) return callback(new Error('请再次输入新密码'))
  if (value !== pwdForm.new_password) return callback(new Error('两次输入的密码不一致'))
  callback()
}
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { validator: validateNewPassword, trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' },
  ],
}

// ── Memory state ──
const memories = ref<any[]>([])
const memoryTotal = ref(0)
const memoriesLoading = ref(false)
const memoryPage = ref(1)
const memoryCategoryFilter = ref('')
const showAddMemory = ref(false)
const addingMemory = ref(false)
const newMemory = reactive({ content: '', category: 'general' })
const showEditMemory = ref(false)
const editingMemory = ref(false)
const editMemoryId = ref<number | null>(null)
const editMemoryContent = ref('')
const cleaningUp = ref(false)

// ── Profile state ──
interface UserProfileData {
  summary?: string
  topics_of_interest?: string[]
  communication_style?: string
  expertise_areas?: string[]
}
const userProfile = ref<UserProfileData | null>(null)
const profileLoading = ref(false)

// ── Account deletion ──
const showDeleteAccount = ref(false)
const deletingAccount = ref(false)
const deleteAccountPwd = ref('')

// ── 2FA ──
const twoFA = reactive({
  setting: false,
  enabling: false,
  disabling: false,
  showSetup: false,
  secret: '',
  uri: '',
  verifyCode: '',
  qrDataUrl: '',
})

async function handleSetup2FA() {
  twoFA.setting = true
  try {
    const res: any = await request.post('/auth/2fa/setup')
    twoFA.secret = res.secret
    twoFA.uri = res.uri
    twoFA.verifyCode = ''
    twoFA.qrDataUrl = ''
    twoFA.showSetup = true
    // Generate QR code locally — never send TOTP secret to third parties
    try {
      twoFA.qrDataUrl = await QRCode.toDataURL(res.uri, { width: 200, margin: 1 })
    } catch { /* QR generation failed, user can still enter secret manually */ }
  } catch { /* interceptor handles */ }
  finally { twoFA.setting = false }
}

async function handleEnable2FA() {
  twoFA.enabling = true
  try {
    await request.post('/auth/2fa/enable', { code: twoFA.verifyCode })
    ElMessage.success('双因素认证已启用')
    twoFA.showSetup = false
    userInfo.totp_enabled = true
  } catch { /* interceptor handles */ }
  finally { twoFA.enabling = false }
}

async function handleDisable2FA() {
  let password: string
  try {
    const res = await ElMessageBox.prompt('请输入当前密码以关闭双因素认证', '关闭 2FA', {
      inputType: 'password',
      confirmButtonText: '确认关闭',
      cancelButtonText: '取消',
      inputPlaceholder: '当前密码',
    })
    password = res.value
  } catch { return }
  twoFA.disabling = true
  try {
    await request.post('/auth/2fa/disable', { password })
    ElMessage.success('双因素认证已关闭')
    userInfo.totp_enabled = false
  } catch { /* interceptor handles */ }
  finally { twoFA.disabling = false }
}

// ── Backup & Restore ──
const backupLoading = ref(false)
const restoreLoading = ref(false)
const restoreResult = ref<{ message: string } | null>(null)

// ── Lifecycle ──
onActivated(async () => {
  try {
    const res: any = await getMe()
    userInfo.username = res.username
    userInfo.email = res.email
    userInfo.role = res.role
    userInfo.totp_enabled = res.totp_enabled || false
    profileForm.email = res.email
    profileForm.nickname = res.nickname || ''
  } catch {
    ElMessage.error('加载用户信息失败，部分功能可能不可用')
  }
  loadMemories()
  loadProfile()
  loadDesktopVersion()
  loadLanSharing()
})

watch(activeTab, (tab) => {
  if (tab === 'usage' && !usageSummary.value.total_tokens) loadUsageData()
})

// ── Helpers ──
function formatDate(d: string) {
  return new Date(d).toLocaleDateString()
}

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

// ── Email ──
async function handleUpdateProfile() {
  const email = profileForm.email.trim()
  if (!email) {
    ElMessage.warning('请输入邮箱')
    return
  }
  if (!emailPattern.test(email)) {
    ElMessage.warning('请输入有效的邮箱地址')
    return
  }
  profileSaving.value = true
  try {
    const payload: Record<string, any> = { email }
    if (profileForm.nickname !== undefined) payload.nickname = profileForm.nickname
    const res: any = await request.put('/auth/profile', payload)
    userInfo.email = res.email
    userStore.setUserInfo(res)
    ElMessage.success('个人信息已更新')
  } catch { /* interceptor handles */ }
  finally { profileSaving.value = false }
}

// ── Password ──
async function handleChangePwd() {
  try {
    await pwdRef.value?.validate()
  } catch { return }
  pwdLoading.value = true
  try {
    await changePassword({ old_password: pwdForm.old_password, new_password: pwdForm.new_password })
    ElMessage.success('密码修改成功')
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
  } catch { /* interceptor handles */ }
  finally { pwdLoading.value = false }
}

// ── Memory helpers ──
function memoryCategoryLabel(cat: string) {
  const m: Record<string, string> = { general: '通用', preference: '偏好', fact: '事实', insight: '经验' }
  return m[cat] || cat
}

function memoryCategoryType(cat: string) {
  const m: Record<string, string> = { general: 'info', preference: 'success', fact: 'warning', insight: '' }
  return m[cat] || 'info'
}

// ── Memory CRUD ──
async function loadMemories(page = 1) {
  memoriesLoading.value = true
  try {
    const params: any = { page, page_size: 50 }
    if (memoryCategoryFilter.value) {
      params.category = memoryCategoryFilter.value
    }
    const res: any = await listMemories(params)
    if (page === 1) {
      memories.value = res.items || []
    } else {
      memories.value = [...memories.value, ...(res.items || [])]
    }
    memoryTotal.value = res.total || 0
    memoryPage.value = page
  } catch { /* interceptor handles */ }
  finally { memoriesLoading.value = false }
}

async function loadMoreMemories() {
  await loadMemories(memoryPage.value + 1)
}

async function handleAddMemory() {
  if (!newMemory.content.trim()) return
  addingMemory.value = true
  try {
    await createMemory({ content: newMemory.content.trim(), category: newMemory.category })
    ElMessage.success('记忆已添加')
    showAddMemory.value = false
    newMemory.content = ''
    newMemory.category = 'general'
    await loadMemories()
  } catch { /* interceptor handles */ }
  finally { addingMemory.value = false }
}

function openEditMemory(mem: any) {
  editMemoryId.value = mem.id
  editMemoryContent.value = mem.content
  showEditMemory.value = true
}

async function handleEditMemory() {
  if (!editMemoryContent.value.trim() || !editMemoryId.value) return
  editingMemory.value = true
  try {
    await updateMemory(editMemoryId.value, { content: editMemoryContent.value.trim() })
    ElMessage.success('记忆已更新')
    showEditMemory.value = false
    await loadMemories()
  } catch { /* interceptor handles */ }
  finally { editingMemory.value = false }
}

async function handleDeleteMemory(id: number) {
  try {
    await deleteMemory(id)
    memories.value = memories.value.filter((m: any) => m.id !== id)
    memoryTotal.value = Math.max(0, memoryTotal.value - 1)
    ElMessage.success('已删除')
  } catch { /* interceptor handles */ }
}

async function handleClearMemories() {
  try {
    await ElMessageBox.confirm('确定清空所有记忆？此操作不可恢复。', '清空记忆', { type: 'warning' })
  } catch { return }
  try {
    const res: any = await clearAllMemories()
    memories.value = []
    memoryTotal.value = 0
    ElMessage.success(`已清空 ${res.deleted || 0} 条记忆`)
  } catch { /* interceptor handles */ }
}

async function handleCleanupExpired() {
  cleaningUp.value = true
  try {
    const res: any = await cleanupExpiredMemories()
    ElMessage.success(`已清理 ${res.deleted || res.cleaned || 0} 条过期记忆`)
    await loadMemories()
  } catch { /* interceptor handles */ }
  finally { cleaningUp.value = false }
}

// ── Profile ──
async function loadProfile() {
  profileLoading.value = true
  try {
    const res: any = await getUserProfile(false)
    userProfile.value = res && res.summary ? res : null
  } catch {
    userProfile.value = null
  } finally {
    profileLoading.value = false
  }
}

async function handleRegenerateProfile() {
  profileLoading.value = true
  try {
    const res: any = await getUserProfile(true)
    userProfile.value = res && res.summary ? res : null
    ElMessage.success('用户画像已更新')
  } catch { /* interceptor handles */ }
  finally { profileLoading.value = false }
}

// ── Delete account ──
async function handleDeleteAccount() {
  if (!deleteAccountPwd.value) return
  deletingAccount.value = true
  try {
    await deleteAccount({ password: deleteAccountPwd.value })
    ElMessage.success('账号已注销')
    userStore.clearToken()
    router.push('/login')
  } catch { /* interceptor handles */ }
  finally { deletingAccount.value = false }
}

// ── Backup ──
async function handleBackup() {
  backupLoading.value = true
  try {
    const { getValidToken } = await import('../../utils/request')
    const token = await getValidToken()
    const res = await fetch(`${API_V1}/system/backup`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error('备份失败')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const disposition = res.headers.get('content-disposition') || ''
    const match = disposition.match(/filename\*?=(?:UTF-8'')?(.+)/i)
    a.download = match?.[1] ? decodeURIComponent(match[1]) : 'backup.zip'
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('备份文件已开始下载')
  } catch {
    ElMessage.error('备份失败，请稍后重试')
  } finally {
    backupLoading.value = false
  }
}

async function handleRestoreFileChange(uploadFile: any) {
  const file = uploadFile.raw || uploadFile
  if (!file) return
  try {
    await ElMessageBox.confirm(
      '恢复将覆盖当前所有数据（数据库、向量库、上传文件），且需要重启应用。\n\n建议先下载当前备份作为保险。确定继续？',
      '确认恢复',
      { type: 'warning', confirmButtonText: '确认恢复', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  restoreLoading.value = true
  restoreResult.value = null
  try {
    const { getValidToken } = await import('../../utils/request')
    const token = await getValidToken()
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`${API_V1}/system/restore`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || '恢复失败')
    }
    const data = await res.json()
    restoreResult.value = data
    ElMessage.success('恢复成功，请重启应用')
  } catch (e: any) {
    ElMessage.error(e.message || '恢复失败，请检查备份文件')
  } finally {
    restoreLoading.value = false
  }
}
</script>

<style scoped>
.settings-page {
  max-width: 1200px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.settings-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 20px;
  }
  :deep(.el-tabs__item) {
    font-size: 14px;
  }
}

:deep(.el-card) {
  border-radius: var(--radius-lg) !important;
}

:deep(.el-card__header) {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
  padding: 18px 24px;
}

:deep(.el-card__body) {
  padding: 24px !important;
}

.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  margin-top: 4px;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.card-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.section-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

/* ── Memory Cards ── */
.memory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.memory-card {
  padding: 14px 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  background: var(--gray-25);
  transition: background 0.15s, box-shadow 0.15s;
}

.memory-card:hover {
  background: var(--gray-50);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.memory-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.memory-badges {
  display: flex;
  gap: 6px;
}

.memory-card-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
}

.memory-card:hover .memory-card-actions {
  opacity: 1;
}

.memory-card-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  margin-bottom: 10px;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-card-footer {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 11px;
  color: var(--text-muted);
}

.memory-stars {
  display: inline-flex;
  gap: 2px;
  color: var(--el-text-color-placeholder);
}

.memory-stars .filled {
  color: var(--el-color-warning);
  fill: var(--el-color-warning);
}

.memory-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.memory-expires {
  color: var(--el-color-warning);
}

/* ── Profile ── */
.profile-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.profile-section {
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-color);
}

.profile-section:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.profile-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.profile-summary {
  font-size: 13px;
  line-height: 1.8;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.profile-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.danger-zone-card {
  border-color: var(--el-color-danger-light-5) !important;
}

:deep(.danger-zone-card .el-card__header) {
  background: var(--el-color-danger-light-9);
}

.usage-stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}

.usage-stat-card {
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: var(--radius, 8px);
  padding: 18px 20px;
  text-align: center;
}

.usage-stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.usage-stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.usage-trend-chart {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  width: 100%;
  height: 180px;
  padding-bottom: 24px;
}

.usage-trend-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
  position: relative;
  animation: usageBarIn 0.4s ease-out both;
}

@keyframes usageBarIn {
  from { opacity: 0; transform: scaleY(0.5); }
  to { opacity: 1; transform: scaleY(1); }
}

.usage-trend-tooltip {
  font-size: 10px;
  color: var(--text-secondary);
  margin-bottom: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.usage-trend-bar-col:hover .usage-trend-tooltip { opacity: 1; }

.usage-trend-bar {
  width: 100%;
  max-width: 14px;
  border-radius: 3px 3px 0 0;
  min-height: 2px;
  background: linear-gradient(180deg, var(--el-color-primary) 0%, var(--el-color-primary-light-5) 100%);
  transition: height 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
}

.usage-trend-bar:hover { opacity: 0.85; }

.usage-trend-label {
  font-size: 9px;
  color: var(--text-secondary);
  margin-top: 6px;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .usage-stat-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
