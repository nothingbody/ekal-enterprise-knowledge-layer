<template>
  <div class="channels-page">
    <div class="page-header">
      <div>
        <h2>渠道管理</h2>
        <p class="page-desc">将 AI 助手接入企业微信、钉钉、飞书、Telegram、Discord、Slack 等平台，通过 Webhook 自动回复消息。</p>
      </div>
      <el-button type="primary" @click="openCreateDialog">
        <Plus :size="16" :stroke-width="1.5" style="margin-right: 4px" />新建渠道
      </el-button>
    </div>

    <div v-if="loading" v-loading="true" style="min-height: 200px;"></div>
    <div v-else-if="!channels.length" class="empty-state">
      <Radio :size="48" :stroke-width="1" style="color: var(--el-text-color-secondary); margin-bottom: 16px;" />
      <p>还没有接入任何渠道</p>
      <p style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; margin-bottom: 12px">将 AI 接入企业微信、钉钉、飞书等，一键创建即可获取 Webhook</p>
      <el-button type="primary" @click="openCreateDialog">创建第一个渠道</el-button>
      <el-button link type="primary" style="margin-left: 8px" @click="$router.push('/guide')">查看使用指南</el-button>
    </div>

    <div v-else class="channel-grid">
      <div v-for="ch in channels" :key="ch.id" class="channel-card" :class="{ inactive: !ch.is_active }">
        <div class="card-header">
          <div class="platform-badge" :class="ch.platform">
            <component :is="platformIcon(ch.platform)" :size="18" :stroke-width="1.5" />
          </div>
          <div class="card-title-area">
            <div class="card-title">{{ ch.name }}</div>
            <el-tag size="small" :type="ch.is_active ? 'success' : 'info'">{{ ch.is_active ? '已启用' : '已停用' }}</el-tag>
          </div>
          <el-dropdown trigger="click" @command="(cmd: string) => handleCommand(cmd, ch)">
            <el-button link><MoreHorizontal :size="16" :stroke-width="1.5" /></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">编辑</el-dropdown-item>
                <el-dropdown-item command="toggle">{{ ch.is_active ? '停用' : '启用' }}</el-dropdown-item>
                <el-dropdown-item command="delete" divided style="color: var(--el-color-danger);">删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="card-body">
          <div class="card-info-row">
            <span class="info-label">平台</span>
            <span class="info-value">{{ platformLabel(ch.platform) }}</span>
          </div>
          <div class="card-info-row">
            <span class="info-label">对话模式</span>
            <span class="info-value">{{ modeLabel(ch.chat_mode) }}</span>
          </div>
          <div class="card-info-row">
            <span class="info-label">知识库</span>
            <span class="info-value">{{ kbName(ch.kb_id) || '未绑定' }}</span>
          </div>
        </div>

        <div class="card-footer">
          <div class="webhook-url">
            <span class="info-label">Webhook URL</span>
            <div class="url-row">
              <code class="webhook-code">{{ webhookUrl(ch.webhook_token) }}</code>
              <el-button link size="small" @click="copyWebhook(ch.webhook_token)">
                <Copy :size="13" :stroke-width="1.5" />
              </el-button>
            </div>
          </div>
          <div class="card-footer-actions">
            <el-button size="small" :loading="testSendingId === ch.id" @click="handleTestSend(ch)">
              <Send :size="13" :stroke-width="1.5" style="margin-right: 4px" />测试发送
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit dialog -->
    <el-dialog v-model="showDialog" :title="editingChannel ? '编辑渠道' : '新建渠道'" width="560px" @close="resetForm">
      <el-form :model="form" label-width="90px">
        <el-form-item label="渠道名称" required>
          <el-input v-model="form.name" placeholder="例如：企微客服机器人" maxlength="100" />
        </el-form-item>
        <el-form-item label="平台" required>
          <el-select v-model="form.platform" :disabled="!!editingChannel" style="width: 100%;" @change="onPlatformChange">
            <el-option label="企业微信" value="wecom" />
            <el-option label="钉钉" value="dingtalk" />
            <el-option label="飞书" value="feishu" />
            <el-option label="Telegram" value="telegram" />
            <el-option label="Discord" value="discord" />
            <el-option label="Slack" value="slack" />
          </el-select>
        </el-form-item>
        <el-form-item label="知识库">
          <el-select v-model="form.kb_id" placeholder="选择知识库" clearable style="width: 100%;">
            <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="LLM 模型">
          <el-select v-model="form.llm_model_id" placeholder="选择模型（默认使用系统默认）" clearable style="width: 100%;">
            <el-option v-for="m in llmModels" :key="m.id" :label="m.display_name || m.model_name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="对话模式">
          <el-select v-model="form.chat_mode" style="width: 100%;">
            <el-option label="自动" value="auto" />
            <el-option label="知识检索" value="rag" />
            <el-option label="数据库查询" value="sql" />
            <el-option label="混合模式" value="hybrid" />
            <el-option label="智能体" value="agent" />
            <el-option label="多Agent" value="multi_agent" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">平台配置</el-divider>

        <!-- WeChat config -->
        <template v-if="form.platform === 'wecom'">
          <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
            <template #title>
              在<strong>企业微信管理后台 → 应用管理 → 机器人</strong>中获取以下配置。<a href="https://developer.work.weixin.qq.com/document/path/91770" target="_blank" style="color: var(--primary);">查看文档</a>
            </template>
          </el-alert>
          <el-form-item label="Token">
            <el-input v-model="form.config.token" placeholder="回调配置中的 Token 值" />
          </el-form-item>
          <el-form-item label="Webhook Key">
            <el-input v-model="form.config.bot_webhook_key" placeholder="机器人 Webhook URL 中 key= 后面的值" />
          </el-form-item>
        </template>

        <!-- DingTalk config -->
        <template v-if="form.platform === 'dingtalk'">
          <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
            <template #title>
              在<strong>钉钉开放平台 → 机器人管理</strong>中获取以下配置。<a href="https://open.dingtalk.com/document/orgapp/custom-robots-send-group-messages" target="_blank" style="color: var(--primary);">查看文档</a>
            </template>
          </el-alert>
          <el-form-item label="App Secret">
            <el-input v-model="form.config.app_secret" placeholder="机器人安全设置中的加签密钥" show-password />
          </el-form-item>
          <el-form-item label="Access Token">
            <el-input v-model="form.config.access_token" placeholder="Webhook URL 中 access_token= 后面的值" />
          </el-form-item>
        </template>

        <!-- Feishu config -->
        <template v-if="form.platform === 'feishu'">
          <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
            <template #title>
              在<strong>飞书开放平台 → 应用详情 → 事件订阅</strong>中获取以下配置。<a href="https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot" target="_blank" style="color: var(--primary);">查看文档</a>
            </template>
          </el-alert>
          <el-form-item label="验证 Token">
            <el-input v-model="form.config.verification_token" placeholder="事件订阅页面的 Verification Token" />
          </el-form-item>
          <el-form-item label="App Secret">
            <el-input v-model="form.config.app_secret" placeholder="应用凭证页面的 App Secret" show-password />
          </el-form-item>
          <el-form-item label="Webhook URL">
            <el-input v-model="form.config.bot_webhook_url" placeholder="自定义机器人的完整 Webhook URL" />
          </el-form-item>
        </template>

        <!-- Telegram config -->
        <template v-if="form.platform === 'telegram'">
          <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
            <template #title>
              通过 <strong>@BotFather</strong> 创建 Telegram Bot 并获取 Token。<a href="https://core.telegram.org/bots/tutorial" target="_blank" style="color: var(--primary);">查看文档</a>
            </template>
          </el-alert>
          <el-form-item label="Bot Token">
            <el-input v-model="form.config.bot_token" placeholder="BotFather 提供的 Bot Token" show-password />
          </el-form-item>
          <el-form-item label="Secret Token">
            <el-input v-model="form.config.secret_token" placeholder="可选：Webhook 验证密钥（setWebhook 时设置）" />
          </el-form-item>
        </template>

        <!-- Discord config -->
        <template v-if="form.platform === 'discord'">
          <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
            <template #title>
              在 <strong>Discord Developer Portal → Applications → Bot</strong> 中获取配置。<a href="https://discord.com/developers/docs/intro" target="_blank" style="color: var(--primary);">查看文档</a>
            </template>
          </el-alert>
          <el-form-item label="Bot Token">
            <el-input v-model="form.config.bot_token" placeholder="Bot 页面的 Token" show-password />
          </el-form-item>
          <el-form-item label="Public Key">
            <el-input v-model="form.config.public_key" placeholder="General Information 页面的 Public Key（用于签名验证）" />
          </el-form-item>
        </template>

        <!-- Slack config -->
        <template v-if="form.platform === 'slack'">
          <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
            <template #title>
              在 <strong>Slack API → Your Apps → Basic Information</strong> 中获取配置。<a href="https://api.slack.com/start" target="_blank" style="color: var(--primary);">查看文档</a>
            </template>
          </el-alert>
          <el-form-item label="Bot Token">
            <el-input v-model="form.config.bot_token" placeholder="xoxb- 开头的 Bot User OAuth Token" show-password />
          </el-form-item>
          <el-form-item label="Signing Secret">
            <el-input v-model="form.config.signing_secret" placeholder="Basic Information 页面的 Signing Secret" show-password />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="handleTestConfig" :loading="testing" style="margin-right: auto;">测试连接</el-button>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">{{ editingChannel ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onActivated, markRaw } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Radio, MoreHorizontal, Copy, Send,
  MessageSquare, MessageCircle, Hash, Bot, Slack, Phone,
} from 'lucide-vue-next'
import { listChannels, createChannel, updateChannel, deleteChannel, toggleChannel, testSendChannel, testChannelConfig } from '../../api/channels'
import { getBackendOrigin } from '../../utils/apiBase'
import { listKnowledgeBases } from '../../api/knowledgeBase'
import { listModels } from '../../api/models'

const loading = ref(false)
const testSendingId = ref<number | null>(null)
const channels = ref<any[]>([])
const knowledgeBases = ref<any[]>([])
const llmModels = ref<any[]>([])

const showDialog = ref(false)
const saving = ref(false)
const testing = ref(false)
const editingChannel = ref<any>(null)
const form = reactive({
  name: '',
  platform: 'wecom',
  kb_id: null as number | null,
  llm_model_id: null as number | null,
  chat_mode: 'auto',
  config: {} as Record<string, any>,
})

function platformLabel(p: string) {
  const m: Record<string, string> = { wecom: '企业微信', dingtalk: '钉钉', feishu: '飞书', telegram: 'Telegram', discord: 'Discord', slack: 'Slack' }
  return m[p] || p
}

const _PLATFORM_ICONS: Record<string, any> = {
  wecom: MessageCircle,      // 企业微信
  dingtalk: Phone,           // 钉钉
  feishu: MessageSquare,     // 飞书
  telegram: Bot,             // Telegram
  slack: Slack,              // Slack (if available)
  discord: Hash,             // Discord
}

function platformIcon(p: string) {
  return markRaw(_PLATFORM_ICONS[p] || MessageSquare)
}

function modeLabel(mode: string) {
  const m: Record<string, string> = { auto: '自动', rag: '知识检索', sql: '数据库查询', hybrid: '混合模式', agent: '智能体', multi_agent: '多Agent' }
  return m[mode] || mode
}

function kbName(kbId: number | null) {
  if (!kbId) return ''
  const kb = knowledgeBases.value.find((k: any) => k.id === kbId)
  return kb?.name || `#${kbId}`
}

function webhookUrl(token: string) {
  const base = getBackendOrigin()
  return `${base}/api/v1/webhook/${token}`
}

async function copyWebhook(token: string) {
  try {
    await navigator.clipboard.writeText(webhookUrl(token))
    ElMessage.success('已复制 Webhook URL')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

async function handleTestSend(ch: any) {
  testSendingId.value = ch.id
  try {
    await testSendChannel(ch.id)
    ElMessage.success('测试消息已发送')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '发送失败')
  } finally {
    testSendingId.value = null
  }
}

async function loadData() {
  loading.value = true
  try {
    const [chRes, kbRes, modelRes] = await Promise.allSettled([
      listChannels(),
      listKnowledgeBases(),
      listModels('llm'),
    ])
    if (chRes.status === 'fulfilled') channels.value = (chRes.value as any)?.items || chRes.value || []
    if (kbRes.status === 'fulfilled') knowledgeBases.value = (kbRes.value as any) || []
    if (modelRes.status === 'fulfilled') llmModels.value = (modelRes.value as any) || []
  } catch { /* interceptor handles */ }
  finally { loading.value = false }
}

function openCreateDialog() {
  editingChannel.value = null
  form.name = ''
  form.platform = 'wecom'
  form.kb_id = null
  form.llm_model_id = null
  form.chat_mode = 'auto'
  form.config = {}
  showDialog.value = true
}

function resetForm() {
  editingChannel.value = null
}

// Reset platform-specific config when platform changes during create
function onPlatformChange() {
  if (!editingChannel.value) {
    form.config = {}
  }
}

function handleCommand(cmd: string, ch: any) {
  if (cmd === 'edit') {
    editingChannel.value = ch
    form.name = ch.name
    form.platform = ch.platform
    form.kb_id = ch.kb_id
    form.llm_model_id = ch.llm_model_id
    form.chat_mode = ch.chat_mode || 'auto'
    form.config = { ...(ch.config || {}) }
    showDialog.value = true
  } else if (cmd === 'toggle') {
    handleToggle(ch)
  } else if (cmd === 'delete') {
    handleDelete(ch)
  }
}

async function handleTestConfig() {
  testing.value = true
  try {
    const res: any = await testChannelConfig({ platform: form.platform, config: form.config })
    if (res.valid) {
      ElMessage.success(res.message || '配置格式正确')
    } else {
      ElMessage.warning(res.message || '配置校验失败')
    }
  } catch { ElMessage.error('测试请求失败') }
  finally { testing.value = false }
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入渠道名称')
    return
  }
  saving.value = true
  try {
    if (editingChannel.value) {
      await updateChannel(editingChannel.value.id, {
        name: form.name,
        kb_id: form.kb_id,
        llm_model_id: form.llm_model_id,
        chat_mode: form.chat_mode,
        config: form.config,
      })
      ElMessage.success('渠道已更新')
    } else {
      await createChannel({
        name: form.name,
        platform: form.platform,
        kb_id: form.kb_id || undefined,
        llm_model_id: form.llm_model_id || undefined,
        chat_mode: form.chat_mode,
        config: form.config,
      })
      ElMessage.success('渠道已创建')
    }
    showDialog.value = false
    await loadData()
  } catch { /* interceptor handles */ }
  finally { saving.value = false }
}

async function handleToggle(ch: any) {
  try {
    await toggleChannel(ch.id)
    ElMessage.success(ch.is_active ? '已停用' : '已启用')
    await loadData()
  } catch { /* interceptor handles */ }
}

async function handleDelete(ch: any) {
  try {
    await ElMessageBox.confirm(`确定删除渠道「${ch.name}」？`, '删除渠道', { type: 'warning' })
  } catch { return }
  try {
    await deleteChannel(ch.id)
    ElMessage.success('已删除')
    await loadData()
  } catch { /* interceptor handles */ }
}

onActivated(loadData)
</script>

<style scoped>
.channels-page {
  max-width: 1200px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  margin-bottom: 4px;
}

.page-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.empty-state {
  text-align: center;
  padding: 60px 0;
  color: var(--el-text-color-secondary);
}

.empty-state p {
  margin-bottom: 16px;
  font-size: 14px;
}

.channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}

.channel-card {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  overflow: hidden;
  transition: box-shadow 0.2s;
}

.channel-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.channel-card.inactive {
  opacity: 0.65;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 16px 12px;
}

.platform-badge {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: white;
}

.platform-badge.wecom {
  background: linear-gradient(135deg, #07c160, #06ad56);
}

.platform-badge.dingtalk {
  background: linear-gradient(135deg, #3296fa, #1677ff);
}

.platform-badge.feishu {
  background: linear-gradient(135deg, #3370ff, #2b5fd9);
}

.platform-badge.telegram {
  background: linear-gradient(135deg, #2AABEE, #229ED9);
}

.card-title-area {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-body {
  padding: 0 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.card-info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}

.info-label {
  color: var(--el-text-color-secondary);
}

.info-value {
  color: var(--text-primary);
  font-weight: 500;
}

.card-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-color);
  background: var(--gray-25);
}

.card-footer-actions {
  margin-top: 10px;
}

.webhook-url {
  font-size: 12px;
}

.url-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.webhook-code {
  flex: 1;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  background: var(--gray-50);
  padding: 4px 8px;
  border-radius: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.el-divider__text) {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .channel-grid {
    grid-template-columns: 1fr;
  }
}
</style>
