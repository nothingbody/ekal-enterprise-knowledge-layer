<template>
  <div class="models-page">
    <div class="page-header">
      <h2>模型管理</h2>
      <div style="display: flex; gap: 8px;">
        <el-button type="success" @click="quickSetupVisible = true">
          <Zap :size="16" :stroke-width="1.5" style="margin-right: 4px" />一键配置
        </el-button>
        <el-button @click="handleDetectOllama" :loading="ollamaDetecting">
          <SearchIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />检测本地 Ollama
        </el-button>
        <el-button type="primary" @click="openDialog()">
          <PlusIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />添加模型
        </el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="LLM 模型" name="llm" />
      <el-tab-pane label="Embedding 模型" name="embedding" />
      <el-tab-pane label="Reranker 模型" name="reranker" />
    </el-tabs>

    <el-input v-model="searchQuery" placeholder="搜索模型名称或提供商..." clearable style="max-width: 320px; margin-bottom: 16px;">
      <template #prefix><SearchIcon :size="14" :stroke-width="1.5" /></template>
    </el-input>

    <el-alert v-if="filteredModels.some(m => m.is_platform)" :closable="false" class="model-hint" type="success" show-icon style="margin-bottom: 12px">
      <template #title>
        <span>🎁 平台已为您预配置了<strong>官方模型</strong>，可直接使用，无需填写 API Key。试用额度用尽后可添加自己的模型。</span>
      </template>
    </el-alert>
    <el-alert :closable="false" class="model-hint" type="info" show-icon>
      <template #title>
        <span v-if="activeTab === 'llm'">LLM 模型用于生成对话回答（如 GPT-4o、Qwen、DeepSeek 等）。<strong>必须配置至少一个才能使用对话功能。</strong></span>
        <span v-else-if="activeTab === 'embedding'">Embedding 模型用于将文本转换为向量以实现语义搜索（如 text-embedding-3-small）。<strong>必须配置至少一个才能创建知识库。</strong></span>
        <span v-else>Reranker 模型用于对检索结果二次排序，提升回答准确率（可选，如 bge-reranker、Cohere Rerank）。</span>
      </template>
    </el-alert>

    <div v-loading="loading">
      <el-table v-if="filteredModels.length" :data="filteredModels" stripe>
        <el-table-column prop="display_name" label="显示名称" min-width="150">
          <template #default="{ row }">
            {{ row.display_name }}
            <el-tag v-if="row.is_platform" type="warning" size="small" effect="light" style="margin-left: 6px">官方</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="提供商" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.provider }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型标识" min-width="180" />
        <el-table-column prop="api_base" label="API 地址" min-width="200" />
        <el-table-column label="默认" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
            <el-button v-else link size="small" type="primary" @click="setDefault(row)">设为默认</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button link size="small" @click="testConnection(row)">测试</el-button>
            <template v-if="!row.is_platform">
              <el-button link size="small" @click="openProviderLinkByModel(row)">获取 API</el-button>
              <el-button link size="small" type="primary" @click="openDialog(row)">编辑</el-button>
              <el-button link size="small" type="danger" @click="removeModel(row.id)">删除</el-button>
            </template>
            <el-tag v-else size="small" type="info">平台提供</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !filteredModels.length">
        <template #description>
          <p>{{ {llm:'暂无 LLM 模型',embedding:'暂无 Embedding 模型',reranker:'暂无 Reranker 模型'}[activeTab] }}</p>
          <p style="font-size: 12px; color: #c0c4cc; margin-top: 4px">首次使用？需同时配置 LLM 和 Embedding 才能使用对话与知识库。<router-link to="/guide" style="color: var(--el-color-primary); margin-left: 4px">查看使用指南</router-link></p>
        </template>
        <el-button type="primary" @click="openDialog()">添加模型</el-button>
        <el-button link type="primary" style="margin-left: 8px" @click="$router.push('/guide')">前往使用指南</el-button>
      </el-empty>
    </div>

    <el-dialog v-model="showDialog" :title="editing ? '编辑模型' : '添加模型'" width="720px" class="modern-dialog" destroy-on-close>
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="110px" label-position="left">
        <el-form-item label="模型类型" prop="model_type">
          <el-radio-group v-model="form.model_type">
            <el-radio-button value="llm">LLM</el-radio-button>
            <el-radio-button value="embedding">Embedding</el-radio-button>
            <el-radio-button value="reranker">Reranker</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <div class="form-section-title">
          <span>快捷预设</span>
          <span class="form-section-subtitle">点击卡片一键填充对应的配置模板</span>
        </div>

        <div class="vendor-selector">
          <div class="vendor-section" v-if="cloudVendorCards.filter(c => c.type === form.model_type).length">
            <div class="vendor-grid">
              <button
                v-for="card in cloudVendorCards.filter(c => c.type === form.model_type)"
                :key="card.key + card.preset"
                type="button"
                class="vendor-card"
                :class="{ active: activePresetKey === card.preset }"
                @click="selectVendorPreset(card.preset)"
              >
                <div class="vendor-card-top">
                  <div class="vendor-logo-wrap">
                    <img :src="getVendorLogo(card.key)" alt="" class="vendor-logo" @error="onLogoError" />
                  </div>
                  <span class="vendor-provider">{{ card.provider }}</span>
                </div>
                <div class="vendor-title">{{ card.title }}</div>
                <div class="vendor-desc">{{ card.desc }}</div>
                <div class="vendor-card-footer">
                  <span class="vendor-model">{{ card.model }}</span>
                  <span class="vendor-action">一键填充</span>
                </div>
              </button>
            </div>
          </div>
        </div>

        <div class="form-section-title mt-4" v-if="localVendorCards.filter(c => c.type === form.model_type).length">
          <span>本地与聚合接口</span>
        </div>
        <div class="vendor-selector" v-if="localVendorCards.filter(c => c.type === form.model_type).length">
          <div class="vendor-section">
            <div class="vendor-grid compact">
              <button
                v-for="card in localVendorCards.filter(c => c.type === form.model_type)"
                :key="card.key + card.preset"
                type="button"
                class="vendor-card compact"
                :class="{ active: activePresetKey === card.preset }"
                @click="selectVendorPreset(card.preset)"
              >
                <div class="vendor-card-top">
                  <div class="vendor-logo-wrap">
                    <img :src="getVendorLogo(card.key)" alt="" class="vendor-logo" @error="onLogoError" />
                  </div>
                  <span class="vendor-provider">{{ card.provider }}</span>
                </div>
                <div class="vendor-title">{{ card.title }}</div>
                <div class="vendor-desc">{{ card.desc }}</div>
              </button>
            </div>
          </div>
        </div>

        <div class="form-section-title mt-4">
          <span>从环境变量/中转配置导入</span>
          <span class="form-section-subtitle">粘贴 Cursor/IDE 等 env 配置 JSON，自动识别并填充 API 地址与 Key</span>
        </div>
        <div class="form-panel env-import-panel">
          <el-input v-model="envConfigInput" type="textarea" :rows="4" placeholder='{"env":{"ANTHROPIC_BASE_URL":"https://api.example.com","ANTHROPIC_AUTH_TOKEN":"api-key-placeholder"}} 或 {"env":{"OPENAI_BASE_URL":"...","OPENAI_API_KEY":"api-key-placeholder"}}' />
          <el-button type="primary" plain @click="parseEnvConfig" class="env-parse-btn">解析并填充</el-button>
        </div>

        <div class="form-section-title mt-4">
          <span>基础配置</span>
          <span class="form-section-subtitle">模型接口连接信息</span>
        </div>

        <div class="form-panel">
          <el-form-item label="提供商" prop="provider">
            <el-select v-model="form.provider" style="width: 100%">
              <el-option label="OpenAI / 兼容接口" value="openai" />
              <el-option label="Anthropic (Claude)" value="anthropic" />
              <el-option label="Ollama 本地模型" value="ollama" />
              <el-option label="自定义" value="custom" />
            </el-select>
          </el-form-item>

          <el-form-item label="接入说明" v-show="form.provider !== 'custom'">
            <div class="provider-hint">
              <template v-if="form.provider === 'openai'">
                <span>大多数国产模型平台提供 OpenAI 兼容接口，通常可直接选择“OpenAI / 兼容接口”接入。</span>
              </template>
              <template v-else-if="form.provider === 'anthropic'">
                <span>Claude 官方模型请选择 Anthropic，地址一般为 <code>https://api.anthropic.com/v1</code>。</span>
              </template>
              <template v-else-if="form.provider === 'ollama'">
                <span>本地模型请确保 Ollama 已启动，地址通常为 <code>http://localhost:11434</code>。</span>
              </template>
            </div>
          </el-form-item>

          <el-form-item label="显示名称" prop="display_name">
            <el-input v-model="form.display_name" placeholder="例如：GPT-4o" />
          </el-form-item>
          <el-form-item label="模型标识" prop="model_name">
            <el-input v-model="form.model_name" placeholder="例如：gpt-4o / qwen2.5:7b" />
          </el-form-item>
          <el-form-item label="API 地址" prop="api_base">
            <el-input v-model="form.api_base" placeholder="例如：https://api.openai.com/v1 或 http://localhost:11434" />
          </el-form-item>
          <el-form-item label="API Key">
            <div class="api-key-wrapper">
              <el-input v-model="form.api_key" type="password" show-password
                :placeholder="editing ? '留空则保持原有 Key 不变' : '请输入 API Key（Ollama 无需填写）'" />
              <el-tooltip content="前往平台获取 API Key" placement="top">
                <el-button @click="openProviderLinkByModel(form)" :icon="ArrowUpRight" circle />
              </el-tooltip>
            </div>
          </el-form-item>
        </div>

        <el-collapse class="advanced-panel mt-4">
          <el-collapse-item title="高级设置 (可选)" name="1">
            <el-form-item label="参数(JSON)">
              <el-input v-model="form.params" type="textarea" :rows="3" placeholder='{"temperature": 0.7, "max_tokens": 2048}' />
            </el-form-item>
            <el-form-item label="设为默认">
              <el-switch v-model="form.is_default" />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleTestConnectionInForm" :loading="testing" class="test-btn">测试连接</el-button>
          <div>
            <el-button @click="showDialog = false">取消</el-button>
            <el-button type="primary" @click="handleSubmit" :loading="submitting">确定保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- Quick Setup Dialog -->
    <el-dialog v-model="quickSetupVisible" title="一键配置模型" width="500px" destroy-on-close>
      <div style="margin-bottom: 16px;">
        <p style="font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 16px;">
          选择一个 AI 提供商，输入 API Key，系统将自动配置 LLM 和 Embedding 模型。
        </p>
        <el-form label-width="100px">
          <el-form-item label="AI 提供商">
            <el-select v-model="quickSetup.preset" placeholder="选择提供商" style="width: 100%">
              <el-option v-for="(p, key) in quickSetupPresets" :key="key" :label="p.label" :value="key">
                <span>{{ p.label }}</span>
                <span style="float: right; font-size: 12px; color: var(--el-text-color-secondary);">
                  {{ p.models.length }} 个模型
                </span>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="API Key">
            <el-input v-model="quickSetup.apiKey" type="password" show-password placeholder="输入 API Key" />
          </el-form-item>
          <el-form-item v-if="selectedPresetNeedsEmbeddingKey" label="Embedding Key">
            <el-input v-model="quickSetup.embeddingApiKey" type="password" show-password placeholder="Embedding 模型的 API Key（如果不同）" />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              该提供商的 Embedding 模型使用不同平台，需要单独提供 API Key
            </div>
          </el-form-item>
        </el-form>

        <div v-if="quickSetup.preset && quickSetupPresets[quickSetup.preset]" style="background: var(--el-fill-color-light); border-radius: 8px; padding: 16px; margin-top: 8px;">
          <div style="font-size: 13px; font-weight: 600; margin-bottom: 8px;">将自动创建：</div>
          <div v-for="m in quickSetupPresets[quickSetup.preset].models" :key="m.name" style="font-size: 13px; color: var(--el-text-color-secondary); padding: 2px 0;">
            · {{ m.display }} <el-tag size="small" effect="plain" style="margin-left: 4px">{{ m.type === 'llm' ? 'LLM' : 'Embedding' }}</el-tag>
          </div>
          <div style="font-size: 13px; color: var(--el-text-color-secondary); padding: 2px 0;">
            · {{ quickSetupPresets[quickSetup.preset].embedding.display }} <el-tag size="small" type="success" effect="plain" style="margin-left: 4px">Embedding</el-tag>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="quickSetupVisible = false">取消</el-button>
        <el-button type="primary" :loading="quickSetupLoading" :disabled="!quickSetup.preset || !quickSetup.apiKey?.trim()" @click="handleQuickSetup">
          一键配置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onActivated } from 'vue'
import { Plus as PlusIcon, ArrowUpRight, Search as SearchIcon, Zap } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { listModels, createModel, updateModel, deleteModel, testModel, testSavedModel, detectOllama, getQuickSetupPresets, quickSetupModels } from '../../api/models'

const modelList = ref<any[]>([])
const activeTab = ref('llm')
const showDialog = ref(false)
const submitting = ref(false)
const loading = ref(false)
const testing = ref(false)
const editing = ref<any>(null)
const ollamaDetecting = ref(false)
const formRef = ref<FormInstance>()
const activePresetKey = ref('')

const quickSetupVisible = ref(false)
const quickSetupLoading = ref(false)
const quickSetupPresets = ref<Record<string, any>>({})
const quickSetup = reactive({ preset: '', apiKey: '', embeddingApiKey: '' })
const selectedPresetNeedsEmbeddingKey = computed(() => {
  const p = quickSetupPresets.value[quickSetup.preset]
  return p?.needs_separate_embedding_key
})
const envConfigInput = ref('')
const searchQuery = ref('')

const filteredModels = computed(() => {
  let list = modelList.value.filter((m) => m.model_type === activeTab.value)
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter((m) =>
      (m.display_name || '').toLowerCase().includes(q) ||
      (m.model_name || '').toLowerCase().includes(q) ||
      (m.provider || '').toLowerCase().includes(q) ||
      (m.api_base || '').toLowerCase().includes(q)
    )
  }
  return list
})

/** 解析 env 配置 JSON，自动识别并填充 api_base、api_key、provider 等 */
function parseEnvConfig() {
  const raw = envConfigInput.value?.trim()
  if (!raw) {
    ElMessage.warning('请先粘贴 env 配置 JSON')
    return
  }
  let data: any
  try {
    data = JSON.parse(raw)
  } catch {
    ElMessage.error('JSON 格式无效，请检查粘贴内容')
    return
  }
  const env = data?.env ?? data
  if (!env || typeof env !== 'object') {
    ElMessage.warning('未找到 env 对象，请确认格式为 {"env": {...}} 或直接 {...}')
    return
  }
  const e = env as Record<string, string>

  // Anthropic / Claude 中转
  const anthropicBase = e.ANTHROPIC_BASE_URL || e.ANTHROPIC_API_URL || ''
  const anthropicKey = e.ANTHROPIC_AUTH_TOKEN || e.ANTHROPIC_API_KEY || e.CLAUDE_API_KEY || ''
  if (anthropicBase || anthropicKey) {
    form.model_type = 'llm'
    form.provider = 'anthropic'
    if (anthropicBase) form.api_base = anthropicBase.replace(/\/+$/, '')
    if (anthropicKey) form.api_key = anthropicKey
    if (!form.display_name) form.display_name = 'Claude (中转)'
    if (!form.model_name) form.model_name = 'claude-sonnet-4-20250514'
    activePresetKey.value = ''
    ElMessage.success('已解析 Anthropic 中转配置')
    return
  }

  // OpenAI 兼容 / 通用中转
  const openaiBase = e.OPENAI_BASE_URL || e.OPENAI_API_BASE || e.API_BASE_URL || ''
  const openaiKey = e.OPENAI_API_KEY || e.API_KEY || ''
  if (openaiBase || openaiKey) {
    form.model_type = 'llm'
    form.provider = 'openai'
    if (openaiBase) form.api_base = openaiBase.replace(/\/+$/, '')
    if (openaiKey) form.api_key = openaiKey
    if (!form.display_name) form.display_name = 'OpenAI 兼容 (中转)'
    if (!form.model_name) form.model_name = 'gpt-4o'
    activePresetKey.value = ''
    ElMessage.success('已解析 OpenAI 兼容配置')
    return
  }

  ElMessage.warning('未识别到 ANTHROPIC_* 或 OPENAI_* 等已知环境变量')
}

const form = reactive({
  model_type: 'llm',
  provider: 'openai',
  display_name: '',
  model_name: '',
  api_base: '',
  api_key: '',
  params: '',
  is_default: false,
})

const validateJson = (_rule: any, value: string, callback: Function) => {
  if (!value) return callback()
  try {
    JSON.parse(value)
    callback()
  } catch {
    callback(new Error('请输入有效的 JSON'))
  }
}

const formRules = {
  model_type: [{ required: true, message: '请选择模型类型', trigger: 'change' }],
  provider: [{ required: true, message: '请选择提供商', trigger: 'change' }],
  display_name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  model_name: [{ required: true, message: '请输入模型标识', trigger: 'blur' }],
  api_base: [{ required: true, message: '请输入 API 地址', trigger: 'blur' }],
  params: [{ validator: validateJson, trigger: 'blur' }],
}

const cloudVendorCards = [
  // LLM
  { key: 'openai', preset: 'openai-gpt4o', type: 'llm', provider: 'OpenAI', title: 'GPT-4o', model: 'gpt-4o', desc: '国际通用旗舰模型，适合高质量通用对话。' },
  { key: 'claude', preset: 'claude-sonnet', type: 'llm', provider: 'Anthropic', title: 'Claude Sonnet', model: 'claude-sonnet-4', desc: '长文本与写作体验优秀，适合复杂推理。' },
  { key: 'deepseek', preset: 'deepseek', type: 'llm', provider: 'DeepSeek', title: 'DeepSeek-V3', model: 'deepseek-chat', desc: '高性价比国产大模型，适合企业问答场景。' },
  { key: 'qwen', preset: 'qwen-max', type: 'llm', provider: '阿里云百炼', title: '通义千问 Max', model: 'qwen-max', desc: 'OpenAI 兼容接入稳定，适合中文综合任务。' },
  { key: 'zhipu', preset: 'glm-4-plus', type: 'llm', provider: '智谱 AI', title: 'GLM-4-Plus', model: 'glm-4-plus', desc: '国产通用能力强，适合聊天与工具调用。' },
  { key: 'kimi', preset: 'kimi-k2', type: 'llm', provider: 'Moonshot', title: 'Kimi K2', model: 'kimi-k2', desc: '长上下文表现突出，适合知识问答与总结。' },
  { key: 'doubao', preset: 'doubao-pro', type: 'llm', provider: '火山方舟', title: '豆包 Pro', model: 'doubao-pro-32k', desc: '生态成熟，适合国内企业集成与部署。' },
  { key: 'qianfan', preset: 'ernie-speed', type: 'llm', provider: '百度千帆', title: '文心 Speed', model: 'ERNIE-Speed-128K', desc: '适合中文问答与业务知识助手场景。' },

  // Embedding
  { key: 'openai', preset: 'openai-embed', type: 'embedding', provider: 'OpenAI', title: 'text-embed-3', model: 'text-embedding-3-small', desc: '业界标杆的文本向量化模型。' },
  { key: 'qwen', preset: 'qwen-embed', type: 'embedding', provider: '阿里云百炼', title: '千问 Embedding', model: 'text-embedding-v3', desc: '支持多语言，中文检索效果优秀。' },
  { key: 'zhipu', preset: 'zhipu-embed', type: 'embedding', provider: '智谱 AI', title: 'Embedding-3', model: 'embedding-3', desc: '适合国内知识库构建，性价比高。' },
  { key: 'doubao', preset: 'doubao-embed', type: 'embedding', provider: '火山方舟', title: '豆包 Embedding', model: 'doubao-embedding', desc: '高精度向量大模型。' },
  
  // Reranker
  { key: 'zhipu', preset: 'zhipu-reranker', type: 'reranker', provider: '智谱 AI', title: 'GLM Reranker', model: 'glm-reranker', desc: '针对中文优化的业务重排序能力。' },
]

const localVendorCards = [
  // LLM
  { key: 'minimax', preset: 'minimax-text', type: 'llm', provider: 'MiniMax', title: 'MiniMax Text', desc: '适合 OpenAI 兼容方式快速接入。' },
  { key: 'hunyuan', preset: 'hunyuan-lite', type: 'llm', provider: '腾讯混元', title: '混元 Lite', desc: '适合腾讯云生态与国产模型方案。' },
  { key: 'siliconflow', preset: 'siliconflow-deepseek', type: 'llm', provider: '硅基流动', title: '硅基 DeepSeek', desc: '聚合多种开源模型，接入门槛低。' },
  { key: 'ollama', preset: 'ollama-qwen', type: 'llm', provider: 'Ollama', title: '本地 Qwen', desc: '适合离线、本地部署和隐私场景。' },
  
  // Embedding
  { key: 'siliconflow', preset: 'bge-m3-embed', type: 'embedding', provider: '硅基流动', title: 'BGE-M3', desc: '开源多语言 Embedding 标杆。' },
  { key: 'ollama', preset: 'ollama-embed', type: 'embedding', provider: 'Ollama', title: '本地 Embedding', desc: '适合本地向量化与离线知识库。' },
  { key: 'custom', preset: 'custom-embed', type: 'embedding', provider: '自定义', title: '私有 Embedding', desc: '接入本地自建的向量服务。' },

  // Reranker
  { key: 'siliconflow', preset: 'bge-reranker', type: 'reranker', provider: '硅基流动', title: 'BGE Reranker', desc: '强大的开源重排序模型。' },
  { key: 'siliconflow', preset: 'jina-reranker', type: 'reranker', provider: '硅基流动', title: 'Jina Reranker', desc: '支持长上下文的多语言重排序。' },
  { key: 'custom', preset: 'custom-reranker', type: 'reranker', provider: '自定义', title: '私有 Reranker', desc: '接入本地自建的重排序服务。' },
]

const _defaultIcon = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%2394a3b8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>'

function getVendorLogo(key: string) {
  const favicons: Record<string, string> = {
    openai: 'https://cdn.openai.com/favicon.ico',
    claude: 'https://www.anthropic.com/favicon.ico',
    deepseek: 'https://platform.deepseek.com/favicon.ico',
    qwen: 'https://img.alicdn.com/imgextra/i1/O1CN01AKUdEM1Qv7gYkfEfI_!!6000000002038-2-tps-512-512.png',
    zhipu: 'https://open.bigmodel.cn/favicon.ico',
    kimi: 'https://platform.moonshot.cn/favicon.ico',
    doubao: 'https://lf-flow-web-cdn.doubao.com/obj/flow-doubao/doubao/logo-icon-white-bg.png',
    qianfan: 'https://console.bce.baidu.com/static/favicon.ico',
    minimax: 'https://platform.minimaxi.com/favicon.ico',
    hunyuan: 'https://cloud.tencent.com/favicon.ico',
    siliconflow: 'https://cloud.siliconflow.cn/favicon.ico',
    ollama: 'https://ollama.com/public/ollama.png',
  }
  return favicons[key] || _defaultIcon
}

function onLogoError(e: Event) {
  const img = e.target as HTMLImageElement
  if (img) img.src = _defaultIcon
}

function fillPreset(preset: string) {
  const presets: Record<string, any> = {
    'openai-gpt4o': { model_type: 'llm', provider: 'openai', display_name: 'GPT-4o', model_name: 'gpt-4o', api_base: 'https://api.openai.com/v1', params: '{"temperature": 0.7}' },
    'openai-embed': { model_type: 'embedding', provider: 'openai', display_name: 'text-embedding-3-small', model_name: 'text-embedding-3-small', api_base: 'https://api.openai.com/v1', params: '' },
    'claude-sonnet': { model_type: 'llm', provider: 'anthropic', display_name: 'Claude Sonnet 4', model_name: 'claude-sonnet-4-20250514', api_base: 'https://api.anthropic.com/v1', params: '{"temperature": 0.7}' },
    'deepseek': { model_type: 'llm', provider: 'openai', display_name: 'DeepSeek-V3', model_name: 'deepseek-chat', api_base: 'https://api.deepseek.com', params: '{"temperature": 0.7}' },
    'qwen-max': { model_type: 'llm', provider: 'openai', display_name: '通义千问 Max', model_name: 'qwen-max', api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', params: '{"temperature": 0.7}' },
    'glm-4-plus': { model_type: 'llm', provider: 'openai', display_name: 'GLM-4-Plus', model_name: 'glm-4-plus', api_base: 'https://open.bigmodel.cn/api/paas/v4', params: '{"temperature": 0.7}' },
    'kimi-k2': { model_type: 'llm', provider: 'openai', display_name: 'Kimi K2', model_name: 'kimi-k2-0711-preview', api_base: 'https://api.moonshot.cn/v1', params: '{"temperature": 0.7}' },
    'doubao-pro': { model_type: 'llm', provider: 'openai', display_name: '豆包 Pro', model_name: 'doubao-pro-32k', api_base: 'https://ark.cn-beijing.volces.com/api/v3', params: '{"temperature": 0.7}' },
    'ernie-speed': { model_type: 'llm', provider: 'openai', display_name: '文心 Speed', model_name: 'ERNIE-Speed-128K', api_base: 'https://qianfan.baidubce.com/v2', params: '{"temperature": 0.7}' },
    'minimax-text': { model_type: 'llm', provider: 'openai', display_name: 'MiniMax Text-01', model_name: 'MiniMax-Text-01', api_base: 'https://api.minimax.chat/v1', params: '{"temperature": 0.7}' },
    'hunyuan-lite': { model_type: 'llm', provider: 'openai', display_name: '腾讯混元 Lite', model_name: 'hunyuan-lite', api_base: 'https://api.hunyuan.cloud.tencent.com/v1', params: '{"temperature": 0.7}' },
    'siliconflow-deepseek': { model_type: 'llm', provider: 'openai', display_name: '硅基流动 DeepSeek', model_name: 'deepseek-ai/DeepSeek-V3', api_base: 'https://api.siliconflow.cn/v1', params: '{"temperature": 0.7}' },
    'ollama-qwen': { model_type: 'llm', provider: 'ollama', display_name: 'Qwen2.5 (本地)', model_name: 'qwen2.5:7b', api_base: 'http://localhost:11434', params: '{"temperature": 0.7}' },
    'ollama-embed': { model_type: 'embedding', provider: 'ollama', display_name: 'nomic-embed (本地)', model_name: 'nomic-embed-text', api_base: 'http://localhost:11434', params: '' },
    'qwen-embed': { model_type: 'embedding', provider: 'openai', display_name: '通义千问 Embedding', model_name: 'text-embedding-v3', api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', params: '' },
    'zhipu-embed': { model_type: 'embedding', provider: 'openai', display_name: '智谱 Embedding-3', model_name: 'embedding-3', api_base: 'https://open.bigmodel.cn/api/paas/v4', params: '' },
    'doubao-embed': { model_type: 'embedding', provider: 'openai', display_name: '豆包 Embedding', model_name: 'doubao-embedding', api_base: 'https://ark.cn-beijing.volces.com/api/v3', params: '' },
    'bge-m3-embed': { model_type: 'embedding', provider: 'openai', display_name: 'BGE-M3 (硅基流动)', model_name: 'BAAI/bge-m3', api_base: 'https://api.siliconflow.cn/v1', params: '' },
    'custom-embed': { model_type: 'embedding', provider: 'custom', display_name: '私有 Embedding', model_name: '', api_base: '', params: '' },
    'zhipu-reranker': { model_type: 'reranker', provider: 'openai', display_name: '智谱 GLM Reranker', model_name: 'glm-reranker', api_base: 'https://open.bigmodel.cn/api/paas/v4', params: '' },
    'bge-reranker': { model_type: 'reranker', provider: 'openai', display_name: 'BGE Reranker (硅基流动)', model_name: 'BAAI/bge-reranker-v2-m3', api_base: 'https://api.siliconflow.cn/v1', params: '' },
    'jina-reranker': { model_type: 'reranker', provider: 'openai', display_name: 'Jina Reranker (硅基流动)', model_name: 'jinaai/jina-reranker-v2-base-multilingual', api_base: 'https://api.siliconflow.cn/v1', params: '' },
    'custom-reranker': { model_type: 'reranker', provider: 'custom', display_name: '私有 Reranker', model_name: '', api_base: '', params: '' },
  }
  const p = presets[preset]
  if (p) {
    Object.assign(form, p)
    activePresetKey.value = preset
  }
}

function selectVendorPreset(preset: string) {
  fillPreset(preset)
}

function openProviderLink(key: string) {
  const links: Record<string, string> = {
    openai: 'https://platform.openai.com/api-keys',
    anthropic: 'https://console.anthropic.com/settings/keys',
    deepseek: 'https://platform.deepseek.com/api_keys',
    qwen: 'https://bailian.console.aliyun.com/',
    zhipu: 'https://open.bigmodel.cn/usercenter/proj-mgmt/apikeys',
    kimi: 'https://platform.moonshot.cn/console/api-keys',
    doubao: 'https://console.volcengine.com/ark',
    qianfan: 'https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application',
    minimax: 'https://platform.minimaxi.com/user-center/basic-information/interface-key',
    hunyuan: 'https://console.cloud.tencent.com/hunyuan/api-key',
    siliconflow: 'https://cloud.siliconflow.cn/account/ak',
    ollama: 'https://ollama.com/download',
  }
  const url = links[key]
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}

function openProviderLinkByModel(model: any) {
  const base = String(model.api_base || '')
  const display = String(model.display_name || '').toLowerCase()
  const modelName = String(model.model_name || '').toLowerCase()
  if (base.includes('deepseek') || display.includes('deepseek') || modelName.includes('deepseek')) return openProviderLink('deepseek')
  if (base.includes('dashscope') || display.includes('千问') || modelName.includes('qwen')) return openProviderLink('qwen')
  if (base.includes('bigmodel') || display.includes('glm') || modelName.includes('glm')) return openProviderLink('zhipu')
  if (base.includes('moonshot') || display.includes('kimi') || modelName.includes('kimi')) return openProviderLink('kimi')
  if (base.includes('volces') || display.includes('豆包') || modelName.includes('doubao')) return openProviderLink('doubao')
  if (base.includes('qianfan') || display.includes('文心') || modelName.includes('ernie')) return openProviderLink('qianfan')
  if (base.includes('minimax') || display.includes('minimax')) return openProviderLink('minimax')
  if (base.includes('hunyuan') || display.includes('混元')) return openProviderLink('hunyuan')
  if (base.includes('siliconflow') || display.includes('硅基')) return openProviderLink('siliconflow')
  if (String(model.provider) === 'anthropic') return openProviderLink('anthropic')
  if (String(model.provider) === 'ollama') return openProviderLink('ollama')
  return openProviderLink('openai')
}

function resetForm() {
  form.model_type = activeTab.value
  form.provider = 'openai'
  form.display_name = ''
  form.model_name = ''
  form.api_base = ''
  form.api_key = ''
  form.params = ''
  form.is_default = false
  activePresetKey.value = ''
  envConfigInput.value = ''
}

function openDialog(model?: any) {
  envConfigInput.value = ''
  if (model) {
    editing.value = model
    Object.assign(form, {
      model_type: model.model_type,
      provider: model.provider,
      display_name: model.display_name,
      model_name: model.model_name,
      api_base: model.api_base,
      api_key: model.api_key || '',
      params: model.params || '',
      is_default: model.is_default,
    })
  } else {
    editing.value = null
    resetForm()
  }
  showDialog.value = true
}

async function handleDetectOllama() {
  ollamaDetecting.value = true
  try {
    const res: any = await detectOllama()
    if (!res.detected || !res.models?.length) {
      ElMessage.info('未检测到本地 Ollama 服务。请确认 Ollama 正在运行（默认端口 11434）')
      return
    }
    const models = res.models as Array<{ name: string; size_gb: number; model_type: string; api_base: string; provider: string }>
    const names = models.map((m: any) => `• ${m.name} (${m.size_gb}GB, ${m.model_type})`).join('\n')
    await ElMessageBox.confirm(
      `检测到 ${models.length} 个本地模型：\n${names}\n\n是否一键添加到模型列表？`,
      '发现 Ollama 模型',
      { confirmButtonText: '全部添加', cancelButtonText: '取消', type: 'success' }
    )
    let added = 0
    for (const m of models) {
      const existing = modelList.value.find((e: any) => e.model_name === m.name && e.api_base === m.api_base)
      if (existing) continue
      try {
        await createModel({
          model_type: m.model_type,
          provider: m.provider,
          display_name: `Ollama ${m.name}`,
          model_name: m.name,
          api_base: m.api_base,
          api_key: 'ollama',
        })
        added++
      } catch { /* skip duplicates */ }
    }
    await loadModels()
    ElMessage.success(`已添加 ${added} 个模型`)
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString() !== 'cancel') {
      ElMessage.error('检测失败: ' + (e?.message || e))
    }
  } finally {
    ollamaDetecting.value = false
  }
}

async function loadModels() {
  loading.value = true
  try {
    const res: any = await listModels()
    modelList.value = res
  } finally {
    loading.value = false
  }
}

async function handleSubmit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    if (editing.value) {
      await updateModel(editing.value.id, form)
      ElMessage.success('更新成功')
    } else {
      await createModel(form)
      ElMessage.success('添加成功')
    }
    showDialog.value = false
    await loadModels()
  } finally {
    submitting.value = false
  }
}

async function removeModel(id: number) {
  const model = modelList.value.find((m: any) => m.id === id)
  const name = model?.display_name ? `「${model.display_name}」` : '该模型配置'
  try {
    await ElMessageBox.confirm(`确定删除${name}？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteModel(id)
    ElMessage.success('删除成功')
    await loadModels()
  } catch (err: any) {
    if (err?.response?.status === 409) {
      const detail = err.response.data?.detail || '模型正在被使用'
      try {
        await ElMessageBox.confirm(
          `${detail}\n\n强制删除后，使用该模型的知识库或应用将无法正常工作。确定继续？`,
          '模型正在使用中',
          { type: 'error', confirmButtonText: '强制删除', cancelButtonText: '取消' }
        )
        await deleteModel(id, true)
        ElMessage.success('删除成功')
        await loadModels()
      } catch { /* cancelled */ }
    }
  }
}

async function setDefault(model: any) {
  try {
    await updateModel(model.id, { is_default: true })
    ElMessage.success(`已将「${model.display_name}」设为默认${activeTab.value === 'llm' ? ' LLM' : activeTab.value === 'embedding' ? ' Embedding' : ' Reranker'}模型`)
    await loadModels()
  } catch {
    ElMessage.error('设置默认模型失败')
  }
}

async function testConnection(model: any) {
  const msg = ElMessage({ message: '正在测试连接...', type: 'info', duration: 30000 })
  try {
    const res: any = model.id
      ? await testSavedModel(model.id)
      : await testModel({
          model_type: model.model_type,
          provider: model.provider,
          api_base: model.api_base,
          api_key: model.api_key || undefined,
          model_name: model.model_name,
        })
    msg.close()
    if (res.success) {
      const latencyInfo = res.latency_ms != null ? ` (延迟: ${res.latency_ms}ms)` : ''
      ElMessage.success(`✓ ${res.message}${latencyInfo}`)
    } else {
      const detail = res.detail ? `\n${res.detail}` : ''
      ElMessage.error({ message: `✗ ${res.message}${detail}`, duration: 8000 })
    }
  } catch {
    msg.close()
    ElMessage.error('测试失败，请检查网络或模型配置')
  }
}

async function handleTestConnectionInForm() {
  const msg = ElMessage({ message: '正在测试连接...', type: 'info', duration: 30000 })
  testing.value = true
  try {
    const res: any = await testModel({
      model_type: form.model_type,
      provider: form.provider,
      api_base: form.api_base,
      api_key: form.api_key || undefined,
      model_name: form.model_name,
    })
    msg.close()
    if (res.success) {
      const latencyInfo = res.latency_ms != null ? ` (延迟: ${res.latency_ms}ms)` : ''
      ElMessage.success(`✓ ${res.message}${latencyInfo}`)
    } else {
      const detail = res.detail ? `\n${res.detail}` : ''
      ElMessage.error({ message: `✗ ${res.message}${detail}`, duration: 8000 })
    }
  } catch {
    msg.close()
    ElMessage.error('测试失败，请检查网络或模型配置')
  } finally {
    testing.value = false
  }
}

async function loadQuickSetupPresets() {
  try {
    const res: any = await getQuickSetupPresets()
    quickSetupPresets.value = res.data || res
  } catch { /* ignore */ }
}

async function handleQuickSetup() {
  if (!quickSetup.preset) {
    ElMessage.warning('请选择 AI 提供商')
    return
  }
  if (!quickSetup.apiKey?.trim()) {
    ElMessage.warning('请输入 API Key')
    return
  }
  quickSetupLoading.value = true
  try {
    const res: any = await quickSetupModels({
      preset: quickSetup.preset,
      api_key: quickSetup.apiKey,
      embedding_api_key: quickSetup.embeddingApiKey || undefined,
    })
    const data = res.data || res
    ElMessage.success(data.message || '配置成功')
    quickSetupVisible.value = false
    quickSetup.preset = ''
    quickSetup.apiKey = ''
    quickSetup.embeddingApiKey = ''
    await loadModels()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '配置失败')
  } finally {
    quickSetupLoading.value = false
  }
}

onActivated(() => {
  loadModels()
  loadQuickSetupPresets()
})
</script>

<style scoped>
/* ══════════════════════════════════════════
   Models — Google Cloud Style
   ══════════════════════════════════════════ */
.models-page {
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

.model-hint {
  margin-bottom: 20px;
  border-radius: var(--radius) !important;
}

.form-section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px 0;
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.form-section-subtitle {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
}

.mt-4 {
  margin-top: 32px;
}

.form-panel {
  background: var(--bg-color);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 20px 24px 4px 24px;
}

.env-import-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.env-import-panel .env-parse-btn {
  align-self: flex-start;
}

.api-key-wrapper {
  display: flex;
  gap: 10px;
  width: 100%;
}

.advanced-panel :deep(.el-collapse-item__header) {
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border-bottom: none;
}

.advanced-panel :deep(.el-collapse-item__wrap) {
  background: transparent;
  border-bottom: none;
}

.advanced-panel {
  border: none;
  background: var(--gray-25);
  border-radius: 12px;
  padding: 0 20px;
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.vendor-selector {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.vendor-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.vendor-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
}

.vendor-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.vendor-grid.compact {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.vendor-card {
  appearance: none;
  border: 1px solid var(--border-color);
  background: linear-gradient(180deg, #ffffff 0%, #fafcff 100%);
  border-radius: 14px;
  padding: 12px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 126px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.vendor-card.compact {
  min-height: 112px;
}

.vendor-card:hover {
  border-color: var(--primary);
  box-shadow: 0 8px 24px rgba(22, 93, 255, 0.12);
  transform: translateY(-2px);
}

.vendor-card.active {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.12);
  background: linear-gradient(180deg, rgba(22, 93, 255, 0.05) 0%, rgba(22, 93, 255, 0.01) 100%);
}

.vendor-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.vendor-logo-wrap {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--gray-25);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid var(--border-color-lighter);
  overflow: hidden;
  padding: 4px;
}

.vendor-logo {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.vendor-provider {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

.vendor-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.vendor-desc {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  flex: 1;
}

.vendor-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.vendor-model {
  font-size: 11px;
  color: var(--text-muted);
  max-width: 70%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vendor-action {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
}

.provider-links {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: center;
}

.provider-hint {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary);
  background: var(--gray-25);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
}

.provider-hint code {
  color: var(--primary);
  background: rgba(22, 93, 255, 0.08);
  padding: 2px 6px;
  border-radius: 6px;
}

.modern-dialog :deep(.el-dialog__header) {
  margin-right: 0;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}

.modern-dialog :deep(.el-dialog__title) {
  font-weight: 600;
  font-size: 16px;
}

.modern-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.modern-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
  background: var(--gray-25);
  border-bottom-left-radius: var(--radius-lg);
  border-bottom-right-radius: var(--radius-lg);
}

.modern-dialog :deep(.el-dialog) {
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.15);
}

@media (max-width: 1100px) {
  .vendor-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .vendor-grid.compact {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

:deep(.el-tabs__item) {
  font-size: 14px;
  font-weight: 500;
}

:deep(.el-table) {
  border-radius: var(--radius);
  overflow: hidden;
}

:deep(.el-empty) {
  padding: 60px 0;
}
</style>
