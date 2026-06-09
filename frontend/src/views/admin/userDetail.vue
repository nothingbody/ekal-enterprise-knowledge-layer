<template>
  <div class="user-detail-page">
    <div class="page-header">
      <div style="display: flex; align-items: center; gap: 8px;">
        <el-button text @click="$router.push('/admin/users')">
          <ArrowLeft :size="16" />
        </el-button>
        <h2>用户详情 — {{ userInfo?.username || '加载中...' }}</h2>
      </div>
      <div v-if="userInfo" style="display: flex; gap: 8px; align-items: center;">
        <el-tag :type="userInfo.role === 'admin' ? 'danger' : 'info'" size="small">
          {{ userInfo.role === 'admin' ? '管理员' : '普通用户' }}
        </el-tag>
        <el-tag :type="userInfo.is_active ? 'success' : 'warning'" size="small">
          {{ userInfo.is_active ? '正常' : '已禁用' }}
        </el-tag>
      </div>
    </div>

    <!-- Basic Info -->
    <el-card v-if="userInfo" class="section-card" shadow="never">
      <template #header><span class="section-title">基本信息</span></template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="ID">{{ userInfo.id }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ userInfo.username }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ userInfo.email }}</el-descriptions-item>
        <el-descriptions-item label="最后登录 IP">{{ userInfo.last_login_ip || '未记录' }}</el-descriptions-item>
        <el-descriptions-item label="最后登录时间">
          {{ userInfo.last_login_at ? new Date(userInfo.last_login_at).toLocaleString() : '未记录' }}
        </el-descriptions-item>
        <el-descriptions-item label="注册时间">
          {{ new Date(userInfo.created_at).toLocaleString() }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- User Profile -->
    <el-card class="section-card" shadow="never" v-loading="profileLoading">
      <template #header><span class="section-title">用户画像</span></template>
      <div v-if="profile && profile.profile_summary">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="画像摘要" :span="2">
            <div style="white-space: pre-wrap;">{{ profile.profile_summary }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="兴趣主题">{{ profile.topics_of_interest || '—' }}</el-descriptions-item>
          <el-descriptions-item label="沟通风格">{{ profile.communication_style || '—' }}</el-descriptions-item>
          <el-descriptions-item label="专业领域">{{ profile.expertise_areas || '—' }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ profile.updated_at ? new Date(profile.updated_at).toLocaleString() : '—' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <el-empty v-else description="暂无画像数据" :image-size="60" />
    </el-card>

    <!-- User Memories -->
    <el-card class="section-card" shadow="never" v-loading="memoriesLoading">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="section-title">用户记忆 ({{ memoriesTotal }})</span>
        </div>
      </template>
      <el-table v-if="memories.length" :data="memories" stripe size="small">
        <el-table-column prop="content" label="内容" min-width="300" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="160" show-overflow-tooltip />
        <el-table-column prop="importance" label="重要度" width="80" />
        <el-table-column prop="memory_type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.memory_type === 'persistent' ? 'success' : 'warning'">
              {{ row.memory_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无记忆数据" :image-size="60" />
      <div v-if="memoriesTotal > memoriesPageSize" style="margin-top: 12px; display: flex; justify-content: flex-end;">
        <el-pagination
          v-model:current-page="memoriesPage"
          :page-size="memoriesPageSize"
          :total="memoriesTotal"
          layout="total, prev, pager, next"
          small
          @current-change="loadMemories"
        />
      </div>
    </el-card>

    <!-- Model Configs -->
    <el-card class="section-card" shadow="never" v-loading="modelsLoading">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="section-title">模型配置 ({{ models.length }})</span>
          <div style="display: flex; gap: 8px; align-items: center;">
            <el-radio-group v-model="modelTypeFilter" size="small" @change="loadModels">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button value="llm">LLM</el-radio-button>
              <el-radio-button value="embedding">Embedding</el-radio-button>
              <el-radio-button value="reranker">Reranker</el-radio-button>
            </el-radio-group>
            <el-button size="small" type="primary" @click="openModelCreateDialog">添加模型</el-button>
          </div>
        </div>
      </template>
      <el-table v-if="models.length" :data="models" stripe size="small">
        <el-table-column prop="display_name" label="显示名称" min-width="140" />
        <el-table-column prop="model_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.model_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="提供商" width="100" />
        <el-table-column prop="model_name" label="模型标识" min-width="140" show-overflow-tooltip />
        <el-table-column prop="api_base" label="API 地址" min-width="180" show-overflow-tooltip />
        <el-table-column label="API Key" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.api_key_set" size="small" type="success">已配置</el-tag>
            <el-tag v-else size="small" type="info">未配置</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="默认" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openModelEditDialog(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="deleteModel(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无模型配置" :image-size="60">
        <el-button size="small" type="primary" @click="openModelCreateDialog">添加模型</el-button>
      </el-empty>
    </el-card>

    <!-- Model Edit/Create Dialog -->
    <el-dialog v-model="modelEditVisible" :title="editingModel ? '编辑模型配置' : '添加模型配置'" width="560px" :close-on-click-modal="false">
      <el-form :model="modelEditForm" label-width="100px">
        <!-- Env JSON import -->
        <div v-if="!editingModel" class="env-import-section">
          <div class="env-import-title">从环境变量导入</div>
          <el-input v-model="envConfigInput" type="textarea" :rows="3"
            placeholder='粘贴 JSON，如：{"env":{"ANTHROPIC_BASE_URL":"https://...","ANTHROPIC_AUTH_TOKEN":"api-key-placeholder"}}' />
          <el-button size="small" type="primary" plain @click="parseEnvConfig" style="margin-top: 8px;">解析并填充</el-button>
        </div>
        <el-form-item label="模型类型" v-if="!editingModel">
          <el-radio-group v-model="modelEditForm.model_type">
            <el-radio-button value="llm">LLM</el-radio-button>
            <el-radio-button value="embedding">Embedding</el-radio-button>
            <el-radio-button value="reranker">Reranker</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="提供商">
          <el-select v-model="modelEditForm.provider" style="width: 100%">
            <el-option label="OpenAI / 兼容接口" value="openai" />
            <el-option label="Anthropic (Claude)" value="anthropic" />
            <el-option label="Ollama 本地模型" value="ollama" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="modelEditForm.display_name" placeholder="例如：GPT-4o" />
        </el-form-item>
        <el-form-item label="模型标识">
          <el-input v-model="modelEditForm.model_name" placeholder="例如：gpt-4o" />
        </el-form-item>
        <el-form-item label="API 地址">
          <el-input v-model="modelEditForm.api_base" placeholder="例如：https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="modelEditForm.api_key" type="password" show-password
            :placeholder="editingModel ? '留空保持不变；输入新 Key 覆盖；输入 CLEAR 清除' : 'API Key'" />
          <div v-if="editingModel" style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            留空 = 保持原有 Key 不变 | 输入 <code>CLEAR</code> = 清除已有 Key
          </div>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="modelEditForm.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveModelEdit" :loading="modelSaving">保存</el-button>
      </template>
    </el-dialog>

    <!-- Token Consumption Summary -->
    <el-card class="section-card" shadow="never" v-loading="tokenSummaryLoading">
      <template #header><span class="section-title">Token 消耗统计</span></template>
      <div v-if="tokenSummary" class="token-stats-grid">
        <div class="token-stat-item">
          <div class="token-stat-value">{{ formatNumber(tokenSummary.total_tokens) }}</div>
          <div class="token-stat-label">总 Token</div>
        </div>
        <div class="token-stat-item">
          <div class="token-stat-value">{{ formatNumber(tokenSummary.prompt_tokens) }}</div>
          <div class="token-stat-label">输入 Token</div>
        </div>
        <div class="token-stat-item">
          <div class="token-stat-value">{{ formatNumber(tokenSummary.completion_tokens) }}</div>
          <div class="token-stat-label">输出 Token</div>
        </div>
        <div class="token-stat-item">
          <div class="token-stat-value">{{ tokenSummary.chat_count }}</div>
          <div class="token-stat-label">对话次数</div>
        </div>
        <div class="token-stat-item">
          <div class="token-stat-value">{{ tokenSummary.avg_latency_ms ? (tokenSummary.avg_latency_ms + 'ms') : '—' }}</div>
          <div class="token-stat-label">平均延迟</div>
        </div>
      </div>
      <el-empty v-else description="暂无消耗数据" :image-size="60" />
    </el-card>

    <!-- Usage Detail (per-model) -->
    <el-card class="section-card" shadow="never" v-loading="usageDetailLoading">
      <template #header><span class="section-title">按模型用量明细</span></template>
      <el-table v-if="usageDetail.length" :data="usageDetail" stripe size="small">
        <el-table-column prop="model_name" label="模型" min-width="160" />
        <el-table-column prop="conversations" label="对话数" width="100" />
        <el-table-column prop="input_tokens" label="输入 Token" width="120">
          <template #default="{ row }">{{ formatNumber(row.input_tokens) }}</template>
        </el-table-column>
        <el-table-column prop="output_tokens" label="输出 Token" width="120">
          <template #default="{ row }">{{ formatNumber(row.output_tokens) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无模型用量数据" :image-size="60" />
    </el-card>

    <!-- Operation Logs -->
    <el-card class="section-card" shadow="never" v-loading="opLogsLoading">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="section-title">操作日志 ({{ opLogsTotal }})</span>
          <el-select v-model="opLogActionFilter" placeholder="全部操作" clearable size="small" style="width: 160px;" @change="loadOpLogs">
            <el-option label="全部" value="" />
            <el-option label="对话 (chat)" value="chat" />
            <el-option label="公开对话" value="public_chat" />
            <el-option label="创建知识库" value="create_kb" />
            <el-option label="删除知识库" value="delete_kb" />
            <el-option label="创建模型" value="create_model" />
            <el-option label="更新模型" value="update_model" />
            <el-option label="删除模型" value="delete_model" />
          </el-select>
        </div>
      </template>
      <el-table v-if="opLogs.length" :data="opLogs" stripe size="small">
        <el-table-column prop="action" label="操作" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="row.action === 'chat' ? 'success' : row.action.includes('delete') ? 'danger' : 'info'">
              {{ row.action }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" label="资源类型" width="120" />
        <el-table-column prop="detail" label="详情" min-width="220" show-overflow-tooltip />
        <el-table-column label="Token" width="100">
          <template #default="{ row }">
            <span v-if="row.total_tokens">{{ formatNumber(row.total_tokens) }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="延迟" width="80">
          <template #default="{ row }">
            <span v-if="row.latency_ms">{{ Math.round(row.latency_ms) }}ms</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无操作日志" :image-size="60" />
      <div v-if="opLogsTotal > opLogsPageSize" style="margin-top: 12px; display: flex; justify-content: flex-end;">
        <el-pagination
          v-model:current-page="opLogsPage"
          :page-size="opLogsPageSize"
          :total="opLogsTotal"
          layout="total, prev, pager, next"
          small
          @current-change="loadOpLogs"
        />
      </div>
    </el-card>

    <!-- Agent Configs -->
    <el-card class="section-card" shadow="never" v-loading="agentsLoading">
      <template #header>
        <span class="section-title">Agent 配置 ({{ agents.length }})</span>
      </template>
      <div v-if="agents.length" class="agents-grid">
        <el-card v-for="agent in agents" :key="agent.id" class="agent-card" shadow="hover">
          <div class="agent-name">
            {{ agent.name }}
            <el-tag v-if="agent.is_active" size="small" type="success">启用</el-tag>
            <el-tag v-else size="small" type="info">停用</el-tag>
          </div>
          <div v-if="agent.description" class="agent-desc">{{ agent.description }}</div>
          <div v-if="agent.system_prompt" class="agent-prompt">
            <div class="prompt-label">System Prompt:</div>
            <div class="prompt-content">{{ agent.system_prompt }}</div>
          </div>
          <div class="agent-meta">
            <span>知识库: {{ agent.kb_ids || '无' }}</span>
            <span>创建: {{ new Date(agent.created_at).toLocaleDateString() }}</span>
          </div>
        </el-card>
      </div>
      <el-empty v-else description="暂无 Agent 配置" :image-size="60" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../utils/request'

const route = useRoute()
const userId = Number(route.params.userId)

const userInfo = ref<any>(null)
const profile = ref<any>(null)
const profileLoading = ref(false)
const memories = ref<any[]>([])
const memoriesTotal = ref(0)
const memoriesPage = ref(1)
const memoriesPageSize = 20
const memoriesLoading = ref(false)
const agents = ref<any[]>([])
const agentsLoading = ref(false)

const tokenSummary = ref<any>(null)
const tokenSummaryLoading = ref(false)
const usageDetail = ref<any[]>([])
const usageDetailLoading = ref(false)
const opLogs = ref<any[]>([])
const opLogsTotal = ref(0)
const opLogsPage = ref(1)
const opLogsPageSize = 20
const opLogsLoading = ref(false)
const opLogActionFilter = ref('')

const models = ref<any[]>([])
const modelsLoading = ref(false)
const modelTypeFilter = ref('')
const modelEditVisible = ref(false)
const modelSaving = ref(false)
const editingModel = ref<any>(null)
const modelEditForm = ref({
  model_type: 'llm',
  provider: 'openai',
  display_name: '',
  model_name: '',
  api_base: '',
  api_key: '',
  is_default: false,
})
const envConfigInput = ref('')

function parseEnvConfig() {
  const raw = envConfigInput.value?.trim()
  if (!raw) { ElMessage.warning('请先粘贴 env 配置 JSON'); return }
  let data: any
  try { data = JSON.parse(raw) } catch { ElMessage.error('JSON 格式无效'); return }
  const env = data?.env ?? data
  if (!env || typeof env !== 'object') { ElMessage.warning('未找到 env 对象'); return }
  const e = env as Record<string, string>

  const anthropicBase = e.ANTHROPIC_BASE_URL || e.ANTHROPIC_API_URL || ''
  const anthropicKey = e.ANTHROPIC_AUTH_TOKEN || e.ANTHROPIC_API_KEY || e.CLAUDE_API_KEY || ''
  if (anthropicBase || anthropicKey) {
    modelEditForm.value.model_type = 'llm'
    modelEditForm.value.provider = 'anthropic'
    if (anthropicBase) modelEditForm.value.api_base = anthropicBase.replace(/\/+$/, '')
    if (anthropicKey) modelEditForm.value.api_key = anthropicKey
    if (!modelEditForm.value.display_name) modelEditForm.value.display_name = 'Claude (中转)'
    if (!modelEditForm.value.model_name) modelEditForm.value.model_name = 'claude-sonnet-4-20250514'
    ElMessage.success('已解析 Anthropic 中转配置')
    return
  }

  const openaiBase = e.OPENAI_BASE_URL || e.OPENAI_API_BASE || e.API_BASE_URL || ''
  const openaiKey = e.OPENAI_API_KEY || e.API_KEY || ''
  if (openaiBase || openaiKey) {
    modelEditForm.value.model_type = 'llm'
    modelEditForm.value.provider = 'openai'
    if (openaiBase) modelEditForm.value.api_base = openaiBase.replace(/\/+$/, '')
    if (openaiKey) modelEditForm.value.api_key = openaiKey
    if (!modelEditForm.value.display_name) modelEditForm.value.display_name = 'OpenAI 兼容 (中转)'
    if (!modelEditForm.value.model_name) modelEditForm.value.model_name = 'gpt-4o'
    ElMessage.success('已解析 OpenAI 兼容配置')
    return
  }

  ElMessage.warning('未识别到 ANTHROPIC_* 或 OPENAI_* 等已知环境变量')
}

async function loadUserInfo() {
  try {
    userInfo.value = await request.get(`/users/${userId}/detail`)
  } catch { /* interceptor handles */ }
}

async function loadProfile() {
  profileLoading.value = true
  try {
    profile.value = await request.get(`/users/${userId}/profile`)
  } catch { /* interceptor handles */ }
  finally { profileLoading.value = false }
}

async function loadMemories() {
  memoriesLoading.value = true
  try {
    const res: any = await request.get(`/users/${userId}/memories`, {
      params: { page: memoriesPage.value, page_size: memoriesPageSize }
    })
    memories.value = res?.items || []
    memoriesTotal.value = res?.total || 0
  } catch { /* interceptor handles */ }
  finally { memoriesLoading.value = false }
}

function formatNumber(n: number): string {
  if (!n) return '0'
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

async function loadTokenSummary() {
  tokenSummaryLoading.value = true
  try {
    tokenSummary.value = await request.get(`/users/${userId}/token-summary`)
  } catch { /* interceptor handles */ }
  finally { tokenSummaryLoading.value = false }
}

async function loadUsageDetail() {
  usageDetailLoading.value = true
  try {
    const res: any = await request.get(`/users/${userId}/usage-detail`)
    usageDetail.value = res?.by_model || []
  } catch { /* interceptor handles */ }
  finally { usageDetailLoading.value = false }
}

async function loadOpLogs() {
  opLogsLoading.value = true
  try {
    const params: Record<string, any> = { page: opLogsPage.value, page_size: opLogsPageSize }
    if (opLogActionFilter.value) params.action = opLogActionFilter.value
    const res: any = await request.get(`/users/${userId}/operation-logs`, { params })
    opLogs.value = res?.items || []
    opLogsTotal.value = res?.total || 0
  } catch { /* interceptor handles */ }
  finally { opLogsLoading.value = false }
}

async function loadAgents() {
  agentsLoading.value = true
  try {
    const res: any = await request.get(`/users/${userId}/agents`)
    agents.value = res?.items || []
  } catch { /* interceptor handles */ }
  finally { agentsLoading.value = false }
}

async function loadModels() {
  modelsLoading.value = true
  try {
    const params: Record<string, string> = {}
    if (modelTypeFilter.value) params.model_type = modelTypeFilter.value
    const res: any = await request.get(`/users/${userId}/models`, { params })
    models.value = res?.items || []
  } catch { /* interceptor handles */ }
  finally { modelsLoading.value = false }
}

function openModelEditDialog(model: any) {
  editingModel.value = model
  modelEditForm.value = {
    model_type: model.model_type,
    provider: model.provider,
    display_name: model.display_name,
    model_name: model.model_name,
    api_base: model.api_base,
    api_key: '',
    is_default: model.is_default,
  }
  modelEditVisible.value = true
}

function openModelCreateDialog() {
  editingModel.value = null
  modelEditForm.value = {
    model_type: modelTypeFilter.value || 'llm',
    provider: 'openai',
    display_name: '',
    model_name: '',
    api_base: '',
    api_key: '',
    is_default: false,
  }
  modelEditVisible.value = true
}

async function saveModelEdit() {
  modelSaving.value = true
  try {
    if (editingModel.value) {
      const payload: Record<string, any> = {
        provider: modelEditForm.value.provider,
        display_name: modelEditForm.value.display_name,
        model_name: modelEditForm.value.model_name,
        api_base: modelEditForm.value.api_base,
        is_default: modelEditForm.value.is_default,
      }
      const keyInput = modelEditForm.value.api_key
      if (keyInput === 'CLEAR') {
        payload.api_key = ''
      } else if (keyInput) {
        payload.api_key = keyInput
      }
      await request.put(`/users/${userId}/models/${editingModel.value.id}`, payload)
      ElMessage.success('模型配置已更新')
    } else {
      const payload: Record<string, any> = {
        model_type: modelEditForm.value.model_type,
        provider: modelEditForm.value.provider,
        display_name: modelEditForm.value.display_name,
        model_name: modelEditForm.value.model_name,
        api_base: modelEditForm.value.api_base,
        is_default: modelEditForm.value.is_default,
      }
      if (modelEditForm.value.api_key) {
        payload.api_key = modelEditForm.value.api_key
      }
      await request.post(`/users/${userId}/models`, payload)
      ElMessage.success('模型配置已添加')
    }
    modelEditVisible.value = false
    await loadModels()
  } catch { /* interceptor handles */ }
  finally { modelSaving.value = false }
}

async function deleteModel(model: any) {
  try {
    await ElMessageBox.confirm(
      `确定删除模型「${model.display_name}」？`,
      '确认删除',
      { type: 'warning' }
    )
  } catch { return }
  try {
    await request.delete(`/users/${userId}/models/${model.id}`)
    ElMessage.success('模型配置已删除')
    await loadModels()
  } catch (err: any) {
    if (err?.response?.status === 409) {
      try {
        await ElMessageBox.confirm(
          `${err.response.data?.detail || '模型正在被使用'}\n\n强制删除后关联的资源将无法正常工作。确定继续？`,
          '模型正在使用中',
          { type: 'error', confirmButtonText: '强制删除', cancelButtonText: '取消' }
        )
        await request.delete(`/users/${userId}/models/${model.id}`, { params: { force: true } })
        ElMessage.success('模型配置已删除')
        await loadModels()
      } catch { /* cancelled or error */ }
    }
  }
}

onMounted(() => {
  loadUserInfo()
  loadProfile()
  loadMemories()
  loadModels()
  loadAgents()
  loadTokenSummary()
  loadUsageDetail()
  loadOpLogs()
})
</script>

<style scoped>
.user-detail-page {
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

.section-card {
  margin-bottom: 16px;
}

.section-title {
  font-weight: 600;
  font-size: 15px;
}

.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 12px;
}

.agent-card {
  border: 1px solid var(--el-border-color-lighter);
}

.agent-name {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.agent-prompt {
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 8px;
  max-height: 150px;
  overflow-y: auto;
}

.prompt-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.prompt-content {
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}

.agent-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
}

.token-stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}

.token-stat-item {
  padding: 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  text-align: center;
}

.token-stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
}

.token-stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.text-muted {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.env-import-section {
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 20px;
}

.env-import-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
}
</style>
