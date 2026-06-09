<template>
  <div>
    <!-- Add Credit Dialog -->
    <el-dialog v-model="showAddCreditDialog" title="充值算力" width="400px">
      <el-form label-width="80px">
        <el-form-item label="充值量">
          <el-input-number v-model="addCreditAmount" :min="1000" :step="10000" style="width: 100%" />
        </el-form-item>
        <div style="font-size: 12px; color: var(--el-text-color-secondary);">
          充值后用户方案将自动从"试用"升级为"基础"
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showAddCreditDialog = false">取消</el-button>
        <el-button type="primary" :loading="creditLoading" @click="handleAddCredit">确认充值</el-button>
      </template>
    </el-dialog>

    <!-- Edit Quota Dialog -->
    <el-dialog v-model="showQuotaEditDialog" title="编辑配额" width="450px">
      <el-form label-width="100px">
        <el-form-item label="方案">
          <el-select v-model="quotaEditForm.plan" style="width: 100%">
            <el-option label="试用" value="trial" />
            <el-option label="基础" value="basic" />
            <el-option label="专业" value="pro" />
            <el-option label="企业" value="enterprise" />
          </el-select>
        </el-form-item>
        <el-form-item label="试用总额">
          <el-input-number v-model="quotaEditForm.trial_total" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="试用已用">
          <el-input-number v-model="quotaEditForm.trial_used" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="算力额度">
          <el-input-number v-model="quotaEditForm.token_credit" :min="0" :step="10000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="已用算力">
          <el-input-number v-model="quotaEditForm.token_used" :min="0" :step="10000" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showQuotaEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="quotaEditLoading" @click="handleSaveQuota">保存</el-button>
      </template>
    </el-dialog>

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
            <el-button size="small" type="primary" round @click="openModelDialog()">
              <el-icon><Plus /></el-icon>添加
            </el-button>
          </div>
        </div>
      </template>

      <div v-if="models.length" class="model-grid">
        <div v-for="m in models" :key="m.id" class="model-card" :class="'theme-' + m.model_type">
          <div class="model-card-top">
            <div class="model-type-badge">{{ m.model_type.toUpperCase() }}</div>
            <div class="model-actions">
              <el-button size="small" text @click="openModelDialog(m)"><el-icon><Edit /></el-icon></el-button>
              <el-button size="small" text type="danger" @click="deleteModel(m)"><el-icon><Delete /></el-icon></el-button>
            </div>
          </div>
          <div class="model-card-name">{{ m.display_name }}</div>
          <div class="model-card-meta">
            <span>{{ m.provider }}</span>
            <span>{{ m.model_name }}</span>
          </div>
          <div class="model-card-bottom">
            <el-tag v-if="m.api_key_set" size="small" type="success" effect="plain" round>Key 已配置</el-tag>
            <el-tag v-else size="small" type="info" effect="plain" round>未配置 Key</el-tag>
            <el-tag v-if="m.is_default" size="small" type="warning" effect="plain" round>默认</el-tag>
            <el-tag v-if="m.is_shared" size="small" type="primary" effect="plain" round>共享</el-tag>
          </div>
        </div>
      </div>
      <el-empty v-else description="暂无模型配置" :image-size="60">
        <el-button size="small" type="primary" round @click="openModelDialog()">
          <el-icon><Plus /></el-icon>添加模型
        </el-button>
      </el-empty>
    </el-card>

    <!-- Model Dialog -->
    <el-dialog v-model="modelDialogVisible" :title="editingModel ? '编辑模型配置' : '添加模型配置'" width="560px" :close-on-click-modal="false">
      <el-form :model="modelForm" label-width="100px">
        <div v-if="!editingModel" class="env-import-section">
          <div class="env-import-title">从环境变量导入</div>
          <el-input v-model="envConfigInput" type="textarea" :rows="3"
            placeholder='粘贴 JSON，如：{"env":{"ANTHROPIC_BASE_URL":"https://...","ANTHROPIC_AUTH_TOKEN":"api-key-placeholder"}}' />
          <el-button size="small" type="primary" plain @click="parseEnvConfig" style="margin-top: 8px;">解析并填充</el-button>
        </div>
        <el-form-item label="模型类型" v-if="!editingModel">
          <el-radio-group v-model="modelForm.model_type">
            <el-radio-button value="llm">LLM</el-radio-button>
            <el-radio-button value="embedding">Embedding</el-radio-button>
            <el-radio-button value="reranker">Reranker</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="提供商">
          <el-select v-model="modelForm.provider" style="width: 100%">
            <el-option label="OpenAI / 兼容接口" value="openai" />
            <el-option label="Anthropic (Claude)" value="anthropic" />
            <el-option label="Ollama 本地模型" value="ollama" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="modelForm.display_name" placeholder="例如：GPT-4o" />
        </el-form-item>
        <el-form-item label="模型标识">
          <el-input v-model="modelForm.model_name" placeholder="例如：gpt-4o" />
        </el-form-item>
        <el-form-item label="API 地址">
          <el-input v-model="modelForm.api_base" placeholder="例如：https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="modelForm.api_key" type="password" show-password
            :placeholder="editingModel ? '留空保持不变；输入 CLEAR 清除' : 'API Key'" />
          <div v-if="editingModel" class="form-hint">
            留空 = 保持原有 Key 不变 · 输入 <code>CLEAR</code> = 清除已有 Key
          </div>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="modelForm.is_default" />
        </el-form-item>
        <el-form-item label="共享给组织">
          <el-switch v-model="modelForm.is_shared" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialogVisible = false" round>取消</el-button>
        <el-button type="primary" @click="saveModel" :loading="modelSaving" round>保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../utils/request'

const props = defineProps<{ userId: number; userInfo: any }>()
const emit = defineEmits<{ (e: 'reload-user'): void }>()

const showAddCreditDialog = ref(false)
const addCreditAmount = ref(100000)
const creditLoading = ref(false)

watch(showAddCreditDialog, (val) => {
  if (val) addCreditAmount.value = 100000
})

const showQuotaEditDialog = ref(false)
const quotaEditLoading = ref(false)
const quotaEditForm = ref({ plan: 'trial', trial_total: 50, trial_used: 0, token_credit: 0, token_used: 0 })

const models = ref<any[]>([])
const modelsLoading = ref(false)
const modelTypeFilter = ref('')
const modelDialogVisible = ref(false)
const modelSaving = ref(false)
const editingModel = ref<any>(null)
const envConfigInput = ref('')
const modelForm = ref({
  model_type: 'llm', provider: 'openai', display_name: '', model_name: '',
  api_base: '', api_key: '', is_default: false, is_shared: false,
})

async function handleAddCredit() {
  creditLoading.value = true
  try {
    await request.post(`/admin/users/${props.userId}/add-credit?amount=${addCreditAmount.value}`)
    ElMessage.success('充值成功')
    showAddCreditDialog.value = false
    emit('reload-user')
  } catch {} finally { creditLoading.value = false }
}

function openQuotaEdit() {
  const u = props.userInfo
  if (!u) return
  quotaEditForm.value = {
    plan: u.plan || 'trial', trial_total: u.trial_total ?? 50,
    trial_used: u.trial_used ?? 0, token_credit: u.token_credit ?? 0, token_used: u.token_used ?? 0,
  }
  showQuotaEditDialog.value = true
}

async function handleSaveQuota() {
  quotaEditLoading.value = true
  try {
    await request.put(`/admin/users/${props.userId}/quota`, quotaEditForm.value)
    ElMessage.success('配额已更新')
    showQuotaEditDialog.value = false
    emit('reload-user')
  } catch {} finally { quotaEditLoading.value = false }
}

async function loadModels() {
  modelsLoading.value = true
  try {
    const params: Record<string, string> = {}
    if (modelTypeFilter.value) params.model_type = modelTypeFilter.value
    const res: any = await request.get(`/users/${props.userId}/models`, { params })
    models.value = res?.items || []
  } catch {} finally { modelsLoading.value = false }
}

function openModelDialog(model?: any) {
  envConfigInput.value = ''
  if (model) {
    editingModel.value = model
    modelForm.value = { model_type: model.model_type, provider: model.provider, display_name: model.display_name, model_name: model.model_name, api_base: model.api_base, api_key: '', is_default: model.is_default, is_shared: model.is_shared || false }
  } else {
    editingModel.value = null
    modelForm.value = { model_type: modelTypeFilter.value || 'llm', provider: 'openai', display_name: '', model_name: '', api_base: '', api_key: '', is_default: false, is_shared: false }
  }
  modelDialogVisible.value = true
}

function parseEnvConfig() {
  const raw = envConfigInput.value?.trim()
  if (!raw) { ElMessage.warning('请先粘贴 env 配置 JSON'); return }
  let data: any
  try { data = JSON.parse(raw) } catch { ElMessage.error('JSON 格式无效'); return }
  const env = data?.env ?? data
  if (!env || typeof env !== 'object') { ElMessage.warning('未找到 env 对象'); return }
  const e = env as Record<string, string>
  const ab = e.ANTHROPIC_BASE_URL || e.ANTHROPIC_API_URL || ''
  const ak = e.ANTHROPIC_AUTH_TOKEN || e.ANTHROPIC_API_KEY || e.CLAUDE_API_KEY || ''
  if (ab || ak) {
    modelForm.value.model_type = 'llm'; modelForm.value.provider = 'anthropic'
    if (ab) modelForm.value.api_base = ab.replace(/\/+$/, '')
    if (ak) modelForm.value.api_key = ak
    if (!modelForm.value.display_name) modelForm.value.display_name = 'Claude (中转)'
    if (!modelForm.value.model_name) modelForm.value.model_name = 'claude-sonnet-4-20250514'
    ElMessage.success('已解析 Anthropic 中转配置'); return
  }
  const ob = e.OPENAI_BASE_URL || e.OPENAI_API_BASE || e.API_BASE_URL || ''
  const ok = e.OPENAI_API_KEY || e.API_KEY || ''
  if (ob || ok) {
    modelForm.value.model_type = 'llm'; modelForm.value.provider = 'openai'
    if (ob) modelForm.value.api_base = ob.replace(/\/+$/, '')
    if (ok) modelForm.value.api_key = ok
    if (!modelForm.value.display_name) modelForm.value.display_name = 'OpenAI 兼容 (中转)'
    if (!modelForm.value.model_name) modelForm.value.model_name = 'gpt-4o'
    ElMessage.success('已解析 OpenAI 兼容配置'); return
  }
  ElMessage.warning('未识别到已知环境变量')
}

async function saveModel() {
  modelSaving.value = true
  try {
    if (editingModel.value) {
      const payload: Record<string, any> = { provider: modelForm.value.provider, display_name: modelForm.value.display_name, model_name: modelForm.value.model_name, api_base: modelForm.value.api_base, is_default: modelForm.value.is_default, is_shared: modelForm.value.is_shared }
      const ki = modelForm.value.api_key
      if (ki === 'CLEAR') payload.api_key = ''; else if (ki) payload.api_key = ki
      await request.put(`/users/${props.userId}/models/${editingModel.value.id}`, payload)
      ElMessage.success('已更新')
    } else {
      const payload: Record<string, any> = { model_type: modelForm.value.model_type, provider: modelForm.value.provider, display_name: modelForm.value.display_name, model_name: modelForm.value.model_name, api_base: modelForm.value.api_base, is_default: modelForm.value.is_default, is_shared: modelForm.value.is_shared }
      if (modelForm.value.api_key) payload.api_key = modelForm.value.api_key
      await request.post(`/users/${props.userId}/models`, payload)
      ElMessage.success('已添加')
    }
    modelDialogVisible.value = false; await loadModels()
  } catch {} finally { modelSaving.value = false }
}

async function deleteModel(model: any) {
  try { await ElMessageBox.confirm(`确定删除「${model.display_name}」？`, '确认', { type: 'warning' }) } catch { return }
  try { await request.delete(`/users/${props.userId}/models/${model.id}`); ElMessage.success('已删除'); await loadModels() } catch {}
}

defineExpose({ models, loadModels, showAddCreditDialog, openQuotaEdit })

onMounted(() => { loadModels() })
</script>

<style scoped>
.section-card { margin-bottom: 20px; }
.section-title { font-weight: 600; font-size: 15px; }

.model-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px;
}
.model-card {
  border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: 16px 18px;
  background: #FFF; transition: all 0.25s; position: relative; overflow: hidden;
}
.model-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
}
.model-card.theme-llm::before { background: linear-gradient(90deg, #2B5AED, #5B8DEF); }
.model-card.theme-embedding::before { background: linear-gradient(90deg, #0052D9, #4D8AF0); }
.model-card.theme-reranker::before { background: linear-gradient(90deg, #00B578, #5EDCA5); }
.model-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.model-card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.model-type-badge {
  font-size: 10px; font-weight: 700; letter-spacing: 0.06em;
  padding: 2px 8px; border-radius: 4px; background: #F1F5F9; color: var(--text-secondary);
}
.model-actions { display: flex; gap: 0; }
.model-card-name { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.model-card-meta { font-size: 12px; color: var(--text-tertiary); display: flex; gap: 12px; margin-bottom: 12px; }
.model-card-bottom { display: flex; gap: 6px; flex-wrap: wrap; }

.env-import-section {
  background: var(--bg-page); border: 1px solid var(--border-color); border-radius: var(--radius-md);
  padding: 14px 16px; margin-bottom: 20px;
}
.env-import-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; }
.form-hint { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; }
.form-hint code {
  background: rgba(43,90,237,0.08); color: var(--brand-primary);
  padding: 1px 6px; border-radius: 4px; font-size: 11px;
}
</style>
