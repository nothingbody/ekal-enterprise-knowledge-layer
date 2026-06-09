<template>
  <el-dialog
    v-model="wizardOpen"
    class="setup-wizard-dialog"
    :show-close="false"
    :close-on-click-modal="false"
    :close-on-press-escape="true"
    fullscreen
    @closed="dismiss"
  >
    <template #header>
      <div class="wizard-header">
        <div>
          <h2>快速开始向导</h2>
          <p>直接在向导中完成模型配置、知识库创建、文档上传和试用对话。</p>
        </div>
        <div class="wizard-header-actions">
          <el-tag type="primary">{{ completed }}/{{ total }} 已完成</el-tag>
          <el-button text @click="dismiss">稍后再说</el-button>
        </div>
      </div>
    </template>

    <div class="wizard-layout">
      <aside class="wizard-sidebar">
        <div
          v-for="(step, index) in wizardSteps"
          :key="step.key"
          class="wizard-step"
          :class="{ active: currentStep === index, done: step.done }"
          @click="currentStep = index"
        >
          <div class="wizard-step-index">{{ index + 1 }}</div>
          <div class="wizard-step-content">
            <div class="wizard-step-title">{{ step.title }}</div>
            <div class="wizard-step-desc">{{ step.desc }}</div>
          </div>
        </div>
      </aside>

      <main class="wizard-main">
        <section v-if="currentStep === 0" class="wizard-panel">
          <h3>配置模型</h3>
          <p class="panel-desc">LLM 与 Embedding 缺一不可。先配置这两种模型，后续步骤会直接复用。</p>

          <div class="wizard-grid">
            <div class="wizard-card">
              <h4>LLM 模型</h4>
              <el-form :model="llmForm" label-width="88px">
                <el-form-item label="提供商">
                  <el-select v-model="llmForm.provider" style="width: 100%">
                    <el-option label="OpenAI" value="openai" />
                    <el-option label="Anthropic" value="anthropic" />
                    <el-option label="Ollama" value="ollama" />
                    <el-option label="自定义" value="custom" />
                  </el-select>
                </el-form-item>
                <el-form-item label="API 地址">
                  <el-input v-model="llmForm.api_base" placeholder="如：https://api.openai.com/v1" />
                </el-form-item>
                <el-form-item label="模型名">
                  <el-input v-model="llmForm.model_name" placeholder="如：gpt-4o-mini" />
                </el-form-item>
                <el-form-item label="显示名">
                  <el-input v-model="llmForm.display_name" placeholder="如：默认对话模型" />
                </el-form-item>
                <el-form-item label="API Key">
                  <el-input v-model="llmForm.api_key" show-password />
                </el-form-item>
              </el-form>
              <div class="panel-actions">
                <el-button @click="testWizardModel('llm')" :loading="testingLlm">测试连接</el-button>
                <el-button type="primary" @click="saveWizardModel('llm')" :loading="savingLlm">保存 LLM</el-button>
              </div>
            </div>

            <div class="wizard-card">
              <h4>Embedding 模型</h4>
              <el-form :model="embeddingForm" label-width="88px">
                <el-form-item label="提供商">
                  <el-select v-model="embeddingForm.provider" style="width: 100%">
                    <el-option label="OpenAI" value="openai" />
                    <el-option label="Ollama" value="ollama" />
                    <el-option label="自定义" value="custom" />
                  </el-select>
                </el-form-item>
                <el-form-item label="API 地址">
                  <el-input v-model="embeddingForm.api_base" placeholder="如：https://api.openai.com/v1" />
                </el-form-item>
                <el-form-item label="模型名">
                  <el-input v-model="embeddingForm.model_name" placeholder="如：text-embedding-3-small" />
                </el-form-item>
                <el-form-item label="显示名">
                  <el-input v-model="embeddingForm.display_name" placeholder="如：默认向量模型" />
                </el-form-item>
                <el-form-item label="API Key">
                  <el-input v-model="embeddingForm.api_key" show-password />
                </el-form-item>
              </el-form>
              <div class="panel-actions">
                <el-button @click="testWizardModel('embedding')" :loading="testingEmbedding">测试连接</el-button>
                <el-button type="primary" @click="saveWizardModel('embedding')" :loading="savingEmbedding">保存 Embedding</el-button>
              </div>
            </div>
          </div>
        </section>

        <section v-else-if="currentStep === 1" class="wizard-panel">
          <h3>创建知识库</h3>
          <p class="panel-desc">创建一个知识库，并选择刚才配置好的 Embedding 模型。</p>

          <div class="wizard-card single-card">
            <el-form :model="kbForm" label-width="88px">
              <el-form-item label="名称">
                <el-input v-model="kbForm.name" placeholder="如：产品文档知识库" />
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="kbForm.description" type="textarea" :rows="3" placeholder="简要描述知识库用途" />
              </el-form-item>
              <el-form-item label="向量模型">
                <el-select v-model="kbForm.embedding_model_id" style="width: 100%" placeholder="选择 Embedding 模型">
                  <el-option
                    v-for="model in embeddingModels"
                    :key="model.id"
                    :label="model.display_name || model.model_name"
                    :value="model.id"
                  />
                </el-select>
              </el-form-item>
            </el-form>
            <div class="panel-actions">
              <el-button type="primary" @click="createWizardKb" :loading="creatingKb">创建知识库</el-button>
            </div>
          </div>
        </section>

        <section v-else-if="currentStep === 2" class="wizard-panel">
          <h3>上传文档</h3>
          <p class="panel-desc">把文档上传到刚创建的知识库中，系统会自动解析、切片并向量化。</p>

          <div class="wizard-card single-card">
            <el-alert
              v-if="!createdKbId"
              type="warning"
              :closable="false"
              title="请先完成“创建知识库”步骤。"
            />
            <template v-else>
              <div class="upload-box">
                <input type="file" @change="onWizardFileChange" />
                <div v-if="selectedFile" class="file-name">已选择：{{ selectedFile.name }}</div>
                <el-progress v-if="uploadProgress > 0" :percentage="uploadProgress" />
              </div>
              <div class="panel-actions">
                <el-button type="primary" @click="uploadWizardFile" :loading="uploadingFile" :disabled="!selectedFile">
                  上传文档
                </el-button>
              </div>
            </template>
          </div>
        </section>

        <section v-else-if="currentStep === 3" class="wizard-panel">
          <h3>试用对话</h3>
          <p class="panel-desc">直接在向导里问一个问题，验证整条知识问答链路是否正常。</p>

          <div class="wizard-card single-card">
            <el-alert
              v-if="!createdKbId || !llmModels.length"
              type="warning"
              :closable="false"
              title="请先完成模型配置和知识库创建。"
            />
            <template v-else>
              <el-input
                v-model="trialQuestion"
                type="textarea"
                :rows="4"
                placeholder="例如：请概括这个知识库中的核心内容"
              />
              <div class="panel-actions">
                <el-button type="primary" @click="runTrialChat" :loading="trialLoading">发送测试问题</el-button>
                <el-button @click="router.push('/chat')">前往完整对话页</el-button>
              </div>
              <div v-if="trialAnswer" class="trial-answer">
                <div class="trial-answer-title">测试回答</div>
                <div class="trial-answer-body">{{ trialAnswer }}</div>
              </div>
            </template>
          </div>
        </section>

        <section v-else class="wizard-panel">
          <h3>完成设置</h3>
          <p class="panel-desc">核心配置已经完成，你现在可以继续完善系统，或者直接开始使用。</p>

          <div class="wizard-card single-card">
            <div class="summary-list">
              <div class="summary-item">LLM 模型：{{ llmModels.length }} 个</div>
              <div class="summary-item">Embedding 模型：{{ embeddingModels.length }} 个</div>
              <div class="summary-item">知识库：{{ knowledgeBases.length }} 个</div>
              <div class="summary-item">已上传文件：{{ uploadedDocCount }} 个</div>
            </div>
            <div class="panel-actions">
              <el-button @click="router.push('/guide')">查看完整指南</el-button>
              <el-button type="primary" @click="finishWizard">开始使用</el-button>
            </div>
          </div>
        </section>

        <div class="wizard-footer">
          <el-button :disabled="currentStep === 0" @click="currentStep -= 1">上一步</el-button>
          <el-button v-if="currentStep < wizardSteps.length - 1" type="primary" @click="currentStep += 1">下一步</el-button>
        </div>
      </main>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getSystemReadiness } from '../api/system'
import { listModels, createModel, testModel } from '../api/models'
import { listKnowledgeBases, createKnowledgeBase } from '../api/knowledgeBase'
import { uploadDocument } from '../api/documents'
import { streamChat } from '../api/chat'

const router = useRouter()
const route = useRoute()

const DISMISS_KEY = 'setup_wizard_dismissed'
const DISMISS_TTL = 4 * 3600 * 1000

const visible = ref(false)
const dismissed = ref(false)
const wizardOpen = ref(false)
const currentStep = ref(0)
const readiness = ref<any>(null)

const models = ref<any[]>([])
const knowledgeBases = ref<any[]>([])
const uploadedDocCount = ref(0)
const createdKbId = ref<number | null>(null)
const selectedFile = ref<File | null>(null)
const uploadProgress = ref(0)
const trialQuestion = ref('请简要介绍这个知识库的核心内容')
const trialAnswer = ref('')

const testingLlm = ref(false)
const savingLlm = ref(false)
const testingEmbedding = ref(false)
const savingEmbedding = ref(false)
const creatingKb = ref(false)
const uploadingFile = ref(false)
const trialLoading = ref(false)

const llmForm = ref({
  provider: 'openai',
  api_base: 'https://api.openai.com/v1',
  api_key: '',
  model_name: 'gpt-4o-mini',
  display_name: '默认对话模型',
})

const embeddingForm = ref({
  provider: 'openai',
  api_base: 'https://api.openai.com/v1',
  api_key: '',
  model_name: 'text-embedding-3-small',
  display_name: '默认向量模型',
})

const kbForm = ref({
  name: '我的第一个知识库',
  description: '',
  embedding_model_id: null as number | null,
})

const llmModels = computed(() => models.value.filter((m: any) => m.model_type === 'llm'))
const embeddingModels = computed(() => models.value.filter((m: any) => m.model_type === 'embedding'))

const wizardSteps = computed(() => [
  {
    key: 'models',
    title: '模型配置',
    desc: '配置 LLM 与 Embedding',
    done: llmModels.value.length > 0 && embeddingModels.value.length > 0,
  },
  {
    key: 'kb',
    title: '创建知识库',
    desc: '建立知识库并绑定向量模型',
    done: knowledgeBases.value.length > 0,
  },
  {
    key: 'upload',
    title: '上传文档',
    desc: '导入文档并自动入库',
    done: uploadedDocCount.value > 0,
  },
  {
    key: 'trial',
    title: '试用对话',
    desc: '验证问答链路可用',
    done: !!trialAnswer.value,
  },
  {
    key: 'finish',
    title: '完成配置',
    desc: '查看总结并开始使用',
    done: llmModels.value.length > 0 && embeddingModels.value.length > 0 && knowledgeBases.value.length > 0,
  },
])

const completed = computed(() => wizardSteps.value.filter(step => step.done).length)
const total = computed(() => wizardSteps.value.length)

function syncDismissedState() {
  const raw = localStorage.getItem(DISMISS_KEY)
  const ts = Number(raw)
  if (!raw || !Number.isFinite(ts)) {
    localStorage.removeItem(DISMISS_KEY)
    dismissed.value = false
    return
  }
  if (Date.now() - ts < DISMISS_TTL) {
    dismissed.value = true
    return
  }
  localStorage.removeItem(DISMISS_KEY)
  dismissed.value = false
}

function dismiss() {
  dismissed.value = true
  wizardOpen.value = false
  localStorage.setItem(DISMISS_KEY, String(Date.now()))
}

async function loadReadiness() {
  try {
    const [readinessRes, modelsRes, kbRes] = await Promise.all([
      getSystemReadiness(),
      listModels(),
      listKnowledgeBases(),
    ])
    readiness.value = readinessRes
    models.value = modelsRes.data || modelsRes
    knowledgeBases.value = kbRes.data || kbRes
    if (!createdKbId.value && knowledgeBases.value.length) {
      createdKbId.value = knowledgeBases.value[0].id
    }
    if (!kbForm.value.embedding_model_id && embeddingModels.value.length) {
      kbForm.value.embedding_model_id = embeddingModels.value[0].id
    }
    visible.value = true

    const isDesktop = (readinessRes as any)?.desktop_mode
    const modelsReady = llmModels.value.length > 0 && embeddingModels.value.length > 0

    if (isDesktop && modelsReady) {
      dismissed.value = true
      localStorage.setItem('has_visited', '1')
      return
    }

    // Check if user explicitly requested the wizard from guide page
    const forceWizard = localStorage.getItem('force_setup_wizard')
    if (forceWizard) {
      localStorage.removeItem('force_setup_wizard')
      wizardOpen.value = true
    } else if (!dismissed.value && !(readinessRes as any)?.ready) {
      wizardOpen.value = true
    }
  } catch {
    visible.value = true
  }
}

async function testWizardModel(kind: 'llm' | 'embedding') {
  const form = kind === 'llm' ? llmForm.value : embeddingForm.value
  const loadingRef = kind === 'llm' ? testingLlm : testingEmbedding
  loadingRef.value = true
  try {
    await testModel({
      model_type: kind,
      provider: form.provider,
      api_base: form.api_base,
      api_key: form.api_key,
      model_name: form.model_name,
    })
    ElMessage.success('模型测试成功')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '模型测试失败')
  } finally {
    loadingRef.value = false
  }
}

async function saveWizardModel(kind: 'llm' | 'embedding') {
  const form = kind === 'llm' ? llmForm.value : embeddingForm.value
  const loadingRef = kind === 'llm' ? savingLlm : savingEmbedding
  if (!form.api_base || !form.model_name || !form.display_name) {
    ElMessage.warning('请填写完整的模型信息')
    return
  }
  loadingRef.value = true
  try {
    await createModel({
      model_type: kind,
      provider: form.provider,
      api_base: form.api_base,
      api_key: form.api_key || undefined,
      model_name: form.model_name,
      display_name: form.display_name,
      is_default: true,
    })
    await loadReadiness()
    ElMessage.success(`${kind === 'llm' ? 'LLM' : 'Embedding'} 模型已保存`)
    if (kind === 'embedding' && embeddingModels.value.length) {
      kbForm.value.embedding_model_id = embeddingModels.value[0].id
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '模型保存失败')
  } finally {
    loadingRef.value = false
  }
}

async function createWizardKb() {
  if (!kbForm.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  if (!kbForm.value.embedding_model_id) {
    ElMessage.warning('请选择 Embedding 模型')
    return
  }
  creatingKb.value = true
  try {
    const res: any = await createKnowledgeBase({
      name: kbForm.value.name.trim(),
      description: kbForm.value.description,
      embedding_model_id: kbForm.value.embedding_model_id,
    })
    createdKbId.value = res.data?.id || res.id
    await loadReadiness()
    currentStep.value = 2
    ElMessage.success('知识库已创建')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '知识库创建失败')
  } finally {
    creatingKb.value = false
  }
}

function onWizardFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] || null
  uploadProgress.value = 0
}

async function uploadWizardFile() {
  if (!createdKbId.value || !selectedFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  uploadingFile.value = true
  try {
    await uploadDocument(createdKbId.value, selectedFile.value, percent => {
      uploadProgress.value = percent
    })
    uploadedDocCount.value += 1
    currentStep.value = 3
    ElMessage.success('文档上传成功，后台将继续处理')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '文档上传失败')
  } finally {
    uploadingFile.value = false
  }
}

async function runTrialChat() {
  if (!createdKbId.value) {
    ElMessage.warning('请先创建知识库')
    return
  }
  if (!trialQuestion.value.trim()) {
    ElMessage.warning('请输入测试问题')
    return
  }
  const llmId = llmModels.value[0]?.id
  if (!llmId) {
    ElMessage.warning('请先配置 LLM 模型')
    return
  }
  trialLoading.value = true
  trialAnswer.value = ''
  try {
    const gen = streamChat({
      kb_id: createdKbId.value,
      llm_model_id: llmId,
      question: trialQuestion.value.trim(),
      chat_mode: 'rag',
    })
    for await (const chunk of gen) {
      if (chunk.type === 'content') {
        trialAnswer.value += chunk.data || ''
      } else if (chunk.type === 'error') {
        throw new Error(chunk.data || '试用对话失败')
      }
    }
    ElMessage.success('试用对话成功')
    currentStep.value = 4
  } catch (error: any) {
    ElMessage.error(error?.message || '试用对话失败')
  } finally {
    trialLoading.value = false
  }
}

function finishWizard() {
  wizardOpen.value = false
  localStorage.setItem('has_visited', '1')
  router.push('/chat')
}

onMounted(async () => {
  syncDismissedState()
  if (!dismissed.value) {
    await loadReadiness()
  }
})

watch(() => route.path, async () => {
  if (!dismissed.value) {
    await loadReadiness()
  }
})

defineExpose({ loadReadiness, dismissed })
</script>

<style scoped>
:deep(.setup-wizard-dialog .el-dialog__header) {
  margin-right: 0;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

:deep(.setup-wizard-dialog .el-dialog__body) {
  padding: 0;
  height: calc(100vh - 100px);
}

.wizard-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.wizard-header h2 {
  margin: 0 0 6px;
  font-size: 22px;
}

.wizard-header p {
  margin: 0;
  color: var(--el-text-color-secondary);
}

.wizard-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.wizard-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  height: 100%;
}

.wizard-sidebar {
  border-right: 1px solid var(--el-border-color-lighter);
  padding: 20px;
  overflow: auto;
  background: var(--el-fill-color-extra-light);
}

.wizard-step {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-radius: 10px;
  cursor: pointer;
  margin-bottom: 10px;
  border: 1px solid transparent;
}

.wizard-step.active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
}

.wizard-step.done {
  opacity: 0.75;
}

.wizard-step-index {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color);
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.wizard-step.active .wizard-step-index {
  background: var(--el-color-primary);
  color: #fff;
}

.wizard-step-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.wizard-step-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.wizard-main {
  padding: 24px 28px;
  overflow: auto;
}

.wizard-panel h3 {
  margin: 0 0 8px;
  font-size: 20px;
}

.panel-desc {
  margin: 0 0 20px;
  color: var(--el-text-color-secondary);
}

.wizard-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.wizard-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 18px;
  background: var(--el-bg-color);
}

.wizard-card h4 {
  margin: 0 0 16px;
  font-size: 16px;
}

.single-card {
  max-width: 760px;
}

.panel-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.upload-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.file-name {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.trial-answer {
  margin-top: 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 14px;
  background: var(--el-fill-color-extra-light);
}

.trial-answer-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.trial-answer-body {
  white-space: pre-wrap;
  line-height: 1.7;
}

.summary-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.summary-item {
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.wizard-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 24px;
}

@media (max-width: 980px) {
  .wizard-layout {
    grid-template-columns: 1fr;
  }

  .wizard-sidebar {
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  .wizard-grid {
    grid-template-columns: 1fr;
  }
}
</style>
