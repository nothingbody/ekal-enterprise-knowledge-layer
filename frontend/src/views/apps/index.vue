<template>
  <div class="apps-page">
    <div class="page-header">
      <h2>应用发布</h2>
      <el-button type="primary" @click="openCreate">
        <PlusIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />创建应用
      </el-button>
    </div>

    <div v-loading="loading">
      <el-table v-if="apps.length" :data="apps" stripe style="width: 100%; overflow-x: auto;">
        <el-table-column prop="name" label="应用名称" min-width="150" />
        <el-table-column label="知识库" width="150">
          <template #default="{ row }">{{ getKbName(row.kb_id) }}</template>
        </el-table-column>
        <el-table-column label="权限" width="90">
          <template #default="{ row }">
            <el-tag :type="row.can_manage ? 'success' : 'info'" size="small">{{ row.can_manage ? '可管理' : '只读' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分享链接" min-width="200">
          <template #default="{ row }">
            <el-button link size="small" @click="copyLink(row.share_token)">
              <LinkIcon :size="13" :stroke-width="1.5" style="margin-right: 2px" />复制链接
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="API Key" min-width="200">
          <template #default="{ row }">
            <el-tag v-if="row.has_api_key" type="success" size="small">已生成</el-tag>
            <el-button v-if="row.can_manage" link size="small" type="primary" @click="genKey(row.id, row.has_api_key)">{{ row.has_api_key ? '重新生成' : '生成' }}</el-button>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button v-if="row.can_manage" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.can_manage" link size="small" @click="toggleActive(row)">{{ row.is_active ? '停用' : '启用' }}</el-button>
            <el-button link type="primary" size="small" @click="copyEmbed(row.share_token)">嵌入代码</el-button>
            <el-button v-if="row.can_manage" link type="danger" size="small" @click="removeApp(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !apps.length" description="暂无应用，点击上方按钮创建" />
    </div>

    <el-dialog v-model="showCreate" :title="editingAppId ? '编辑应用' : '创建应用'" width="520px">
      <el-form :model="form" :rules="formRules" ref="appFormRef" label-width="100px">
        <el-form-item label="应用名称" prop="name">
          <el-input v-model="form.name" placeholder="为你的应用起个名字" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="知识库" prop="kb_id">
          <el-select v-model="form.kb_id" placeholder="选择知识库" style="width: 100%">
            <el-option v-for="kb in writableKbList" :key="kb.id" :label="kb.name" :value="kb.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="LLM 模型" prop="llm_model_id">
          <el-select v-model="form.llm_model_id" placeholder="选择 LLM 模型" style="width: 100%">
            <el-option v-for="m in llmModels" :key="m.id" :label="m.display_name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="开场白">
          <el-input v-model="form.welcome_message" type="textarea" :rows="2" placeholder="用户打开应用时看到的欢迎消息" />
        </el-form-item>
        <el-form-item label="推荐问题">
          <div style="width: 100%">
            <el-tag v-for="(q, i) in suggestedTags" :key="i" closable @close="suggestedTags.splice(i, 1)" style="margin: 0 4px 4px 0">{{ q }}</el-tag>
            <el-input v-if="showTagInput" ref="tagInputRef" v-model="tagInputValue" size="small" style="width: 200px" @keydown.enter.prevent="addTag" @blur="addTag" placeholder="输入后回车添加" />
            <el-button v-else size="small" @click="showTagInput = true; nextTick(() => tagInputRef?.focus())">+ 添加问题</el-button>
          </div>
        </el-form-item>
        <el-form-item label="对话模式">
          <el-select v-model="form.default_chat_mode" style="width: 100%;">
            <el-option label="自动" value="auto" />
            <el-option label="知识检索" value="rag" />
            <el-option label="数据库查询" value="sql" />
            <el-option label="混合模式" value="hybrid" />
            <el-option label="智能体" value="agent" />
          </el-select>
        </el-form-item>
        <el-form-item label="每日限额">
          <el-input-number v-model="form.daily_limit" :min="0" :max="100000" :step="10" style="width: 100%;" />
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">公开访问每日最大对话次数，0 表示不限制</div>
        </el-form-item>
        <el-form-item label="应用 Prompt">
          <el-input v-model="form.prompt_template" type="textarea" :rows="4" placeholder="可选：覆盖知识库默认 Prompt，需包含 {context} 占位符" />
        </el-form-item>
        <el-divider content-position="left">品牌定制（可选）</el-divider>
        <el-form-item label="品牌色">
          <el-color-picker v-model="form.brand_color" show-alpha />
          <span style="margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary)">公开页面的主题色</span>
        </el-form-item>
        <el-form-item label="Logo URL">
          <el-input v-model="form.logo_url" placeholder="https://example.com/logo.png" />
        </el-form-item>
        <el-form-item label="自定义 CSS">
          <el-input v-model="form.custom_css" type="textarea" :rows="3" placeholder="可选：注入自定义样式到公开页面" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="handleCreate" :loading="creating">{{ editingAppId ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onActivated, nextTick, computed } from 'vue'
import { Plus as PlusIcon, Link as LinkIcon } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { listApps, createApp, updateApp, generateApiKey, deleteApp } from '../../api/publishedApps'
import { listKnowledgeBases } from '../../api/knowledgeBase'
import { listModels } from '../../api/models'
import { getShareBaseUrl } from '../../utils/apiBase'

const apps = ref<any[]>([])
const kbList = ref<any[]>([])
const llmModels = ref<any[]>([])
const writableKbList = computed(() => kbList.value.filter((kb: any) => kb.can_write))
const loading = ref(false)
const showCreate = ref(false)
const appFormRef = ref<FormInstance>()

const formRules = {
  name: [{ required: true, message: '请输入应用名称', trigger: 'blur' }],
  kb_id: [{ required: true, message: '请选择知识库', trigger: 'change' }],
  llm_model_id: [{ required: true, message: '请选择 LLM 模型', trigger: 'change' }],
}
const creating = ref(false)
const editingAppId = ref<number | null>(null)

const form = reactive({
  name: '', description: '', kb_id: null as number | null,
  llm_model_id: null as number | null,
  welcome_message: '',
  prompt_template: '',
  brand_color: '',
  logo_url: '',
  custom_css: '',
  default_chat_mode: 'auto',
  daily_limit: 100,
})
const suggestedTags = ref<string[]>([])
const showTagInput = ref(false)
const tagInputValue = ref('')
const tagInputRef = ref<any>(null)

function addTag() {
  const v = tagInputValue.value.trim()
  if (v && !suggestedTags.value.includes(v)) {
    suggestedTags.value.push(v)
  }
  tagInputValue.value = ''
  showTagInput.value = false
}

function getKbName(kbId: number) {
  const kb = kbList.value.find((k: any) => k.id === kbId)
  return kb ? kb.name : `ID: ${kbId}`
}

async function loadData() {
  loading.value = true
  try {
    const [aRes, kRes, mRes] = await Promise.allSettled([listApps(), listKnowledgeBases(), listModels('llm')])
    if (aRes.status === 'fulfilled') apps.value = aRes.value as any
    if (kRes.status === 'fulfilled') kbList.value = kRes.value as any
    if (mRes.status === 'fulfilled') llmModels.value = mRes.value as any
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingAppId.value = null
  form.name = ''
  form.description = ''
  form.kb_id = null
  form.welcome_message = ''
  form.prompt_template = ''
  form.brand_color = ''
  form.logo_url = ''
  form.custom_css = ''
  form.default_chat_mode = 'auto'
  form.daily_limit = 100
  suggestedTags.value = []
  // 自动选择默认或唯一的 LLM 模型
  if (llmModels.value.length === 1) {
    form.llm_model_id = llmModels.value[0].id
  } else {
    const defaultModel = llmModels.value.find((m: any) => m.is_default)
    form.llm_model_id = defaultModel?.id || null
  }
  showCreate.value = true
}

function openEdit(app: any) {
  editingAppId.value = app.id
  form.name = app.name || ''
  form.description = app.description || ''
  form.kb_id = app.kb_id
  form.llm_model_id = app.llm_model_id
  form.welcome_message = app.welcome_message || ''
  form.prompt_template = app.prompt_template || ''
  form.default_chat_mode = app.default_chat_mode || 'auto'
  form.daily_limit = app.daily_limit ?? 100
  form.brand_color = app.brand_color || ''
  form.logo_url = app.logo_url || ''
  form.custom_css = app.custom_css || ''
  try {
    suggestedTags.value = app.suggested_questions ? JSON.parse(app.suggested_questions) : []
  } catch {
    suggestedTags.value = []
  }
  showCreate.value = true
}

async function handleCreate() {
  try {
    await appFormRef.value?.validate()
  } catch { return }
  creating.value = true
  try {
    const payload = {
      ...form,
      suggested_questions: suggestedTags.value.length ? JSON.stringify(suggestedTags.value) : '',
    }
    if (editingAppId.value) {
      await updateApp(editingAppId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await createApp(payload)
      ElMessage.success('创建成功')
    }
    showCreate.value = false
    await loadData()
  } finally {
    creating.value = false
  }
}

async function genKey(appId: number, hasExisting: boolean) {
  if (hasExisting) {
    try {
      await ElMessageBox.confirm('重新生成将使当前 API Key 立即失效，确定继续？', '确认', { type: 'warning' })
    } catch { return }
  }
  try {
    const res: any = await generateApiKey(appId)
    await copyToClipboard(res.api_key)
    ElMessage.success('API Key 已生成并复制: ' + res.api_key.substring(0, 16) + '...')
    await loadData()
  } catch { /* interceptor handles */ }
}

async function toggleActive(app: any) {
  try {
    await updateApp(app.id, { is_active: !app.is_active })
    ElMessage.success(app.is_active ? '已停用' : '已启用')
    await loadData()
  } catch { }
}

async function removeApp(id: number) {
  const app = apps.value.find((a: any) => a.id === id)
  const name = app?.name ? `「${app.name}」` : '该应用'
  try {
    await ElMessageBox.confirm(`确定删除${name}？分享链接将失效。`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteApp(id)
    ElMessage.success('删除成功')
    await loadData()
  } catch { /* interceptor handles */ }
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    ElMessageBox.alert(text, '请手动复制以下内容', {
      confirmButtonText: '关闭',
      customClass: 'copy-fallback-dialog',
      inputType: 'textarea',
    })
  }
}

async function copyLink(token: string) {
  const base = getShareBaseUrl()
  const url = `${base}/share/${token}`
  try {
    await navigator.clipboard.writeText(url)
    if (base.includes('127.0.0.1') || base.includes('localhost')) {
      ElMessage.warning('分享链接已复制（当前为本机地址，请在服务器管理端配置 CENTRAL_SERVER_URL 后生成外部可访问链接）')
    } else {
      ElMessage.success('分享链接已复制')
    }
  } catch {
    ElMessageBox.alert(url, '请手动复制分享链接', { confirmButtonText: '关闭' })
  }
}

async function copyEmbed(token: string) {
  const embedUrl = `${getShareBaseUrl()}/share/${token}`
  const code = `<iframe src="${embedUrl}" width="400" height="600" frameborder="0"></iframe>`
  try {
    await navigator.clipboard.writeText(code)
    ElMessage.success('嵌入代码已复制')
  } catch {
    ElMessageBox.alert(code, '请手动复制嵌入代码', { confirmButtonText: '关闭' })
  }
}

onActivated(loadData)
</script>

<style scoped>
.apps-page {
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

.api-key {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .apps-page {
    padding: 0 8px;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .apps-page :deep(.el-table) {
    font-size: 12px;
  }

  .apps-page :deep(.el-table .el-button) {
    padding: 4px 8px;
    font-size: 12px;
  }
}
</style>
