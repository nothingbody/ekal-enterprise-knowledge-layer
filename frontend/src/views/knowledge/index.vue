<template>
  <div class="knowledge-page">
    <div class="page-header">
      <h2>知识库管理</h2>
      <div style="display: flex; gap: 8px; align-items: center;">
        <el-input v-model="searchQuery" placeholder="搜索知识库..." clearable style="width: 200px" size="default" />
        <el-upload :show-file-list="false" :before-upload="handleImport" accept=".zip" :action="''">
          <el-button><UploadIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />导入知识库</el-button>
        </el-upload>
        <el-button type="primary" @click="openCreateDialog">
          <PlusIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />新建知识库
        </el-button>
      </div>
    </div>

    <!-- Model configuration warning -->
    <el-alert v-if="!loading && !hasEmbeddingModel" type="warning" show-icon :closable="false" style="margin-bottom: 16px;">
      <template #title>
        <span v-if="!hasEmbeddingModel && !hasLlmModel">
          <strong>首次使用？</strong>请先配置 AI 模型，否则知识库和对话功能无法正常工作。
          <el-button type="primary" size="small" style="margin-left: 8px;" @click="$router.push('/models')">前往配置模型</el-button>
          <el-button size="small" style="margin-left: 4px;" @click="$router.push('/guide')">查看使用指南</el-button>
        </span>
        <span v-else>
          尚未配置 Embedding 模型，文档上传后将无法向量化。
          <el-button type="primary" size="small" style="margin-left: 8px;" @click="$router.push('/models')">前往配置</el-button>
        </span>
      </template>
    </el-alert>

    <div>
      <!-- Skeleton loading -->
      <el-row v-if="loading" :gutter="16">
        <el-col :xs="24" :sm="12" :md="8" v-for="i in 6" :key="'sk'+i">
          <div class="kb-skeleton-card">
            <div class="skeleton skeleton-title"></div>
            <div class="skeleton skeleton-text"></div>
            <div class="skeleton skeleton-text medium"></div>
            <div style="display:flex;gap:8px;margin-top:12px">
              <div class="skeleton" style="width:70px;height:24px;border-radius:4px"></div>
              <div class="skeleton" style="width:50px;height:24px;border-radius:4px"></div>
            </div>
          </div>
        </el-col>
      </el-row>
      <el-row :gutter="16" v-else-if="filteredKbList.length">
        <el-col :xs="24" :sm="12" :md="8" v-for="(kb, idx) in paginatedKbList" :key="kb.id">
          <el-card class="kb-card" shadow="hover" :style="{ '--card-accent': cardAccentColor(idx) }" @click="$router.push(`/knowledge/${kb.id}/documents`)">
            <template #header>
              <div class="kb-card-header">
                <span class="kb-name">{{ kb.name }}</span>
                <el-dropdown trigger="click" @click.stop>
                  <MoreHorizontal :size="16" :stroke-width="1.5" class="more-icon" @click.stop />
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-if="kb.can_manage" @click="editKb(kb)"><PencilIcon :size="13" :stroke-width="1.5" style="margin-right: 6px" />编辑</el-dropdown-item>
                      <el-dropdown-item @click="handleExport(kb.id)"><DownloadIcon :size="13" :stroke-width="1.5" style="margin-right: 6px" />导出</el-dropdown-item>
                      <el-dropdown-item v-if="kb.can_manage" @click="handleReindex(kb.id)"><RefreshCwIcon :size="13" :stroke-width="1.5" style="margin-right: 6px" />重建索引</el-dropdown-item>
                      <el-dropdown-item v-if="kb.can_manage" @click="removeKb(kb.id)" class="danger"><Trash2Icon :size="13" :stroke-width="1.5" style="margin-right: 6px" />删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
            <p class="kb-desc">{{ kb.description || '暂无描述' }}</p>
            <div class="kb-meta-tags">
              <el-tag size="small" :type="kb.workspace_id ? 'primary' : 'info'">{{ kb.workspace_id ? `工作空间：${kb.workspace_name}` : '个人知识库' }}</el-tag>
              <el-tag v-if="kb.access_role" size="small" type="success">{{ roleLabel(kb.access_role) }}</el-tag>
            </div>
            <div class="kb-stats">
              <span><FileTextIcon :size="13" :stroke-width="1.5" /> {{ kb.doc_count }} 文档</span>
              <span><LayersIcon :size="13" :stroke-width="1.5" /> {{ kb.chunk_count }} 片段</span>
              <span v-if="kb.processing_count > 0" class="kb-processing"><span class="pulse-dot"></span>{{ kb.processing_count }} 处理中</span>
              <span v-if="!kb.embedding_model_id" class="kb-no-model"><TriangleAlertIcon :size="13" :stroke-width="1.5" /> 未配置模型</span>
              <span v-if="kb.updated_at" class="kb-update-time"><ClockIcon :size="13" :stroke-width="1.5" /> {{ relativeTime(kb.updated_at) }}</span>
            </div>
            <div class="kb-actions">
              <el-button size="small" @click.stop="$router.push(`/knowledge/${kb.id}/documents`)">{{ kb.can_write ? '管理文档' : '查看文档' }}</el-button>
              <el-button size="small" type="primary" @click.stop="$router.push({ path: '/chat', query: { kb_id: kb.id } })">开始对话</el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-pagination
        v-if="filteredKbList.length > kbPageSize"
        class="kb-pagination"
        layout="total, prev, pager, next"
        :total="filteredKbList.length"
        :page-size="kbPageSize"
        v-model:current-page="kbPage"
        style="margin-top: 16px; justify-content: flex-end;"
      />

      <el-empty v-if="!loading && kbList.length === 0">
        <template #description>
          <p>还没有知识库，点击下方按钮创建</p>
          <p style="font-size: 12px; color: #c0c4cc; margin-top: 4px">若未配置模型，需先配置 LLM 和 Embedding 才能创建知识库</p>
        </template>
        <div style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;">
          <el-button type="primary" @click="$router.push('/models')">
            <BrainCircuit :size="14" :stroke-width="1.5" style="margin-right: 4px" />前往配置模型
          </el-button>
          <el-button @click="$router.push('/databases')">
            <DatabaseIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />从数据库创建
          </el-button>
          <el-button @click="openCreateDialog">手动创建</el-button>
          <el-button link type="primary" @click="$router.push('/guide')">查看使用指南</el-button>
        </div>
      </el-empty>
      <el-empty v-else-if="!loading && kbList.length > 0 && filteredKbList.length === 0" description="没有匹配的搜索结果" />
    </div>

    <el-collapse v-if="trashedList.length" style="margin-top: 24px;">
      <el-collapse-item>
        <template #title>
          <Trash2Icon :size="14" :stroke-width="1.5" style="margin-right: 4px" />回收站（{{ trashedList.length }}）
        </template>
        <el-table :data="trashedList" size="small" stripe>
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="doc_count" label="文档数" width="80" />
          <el-table-column label="删除时间" width="180">
            <template #default="{ row }">{{ new Date(row.deleted_at).toLocaleString() }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="handleRestore(row.id)">恢复</el-button>
              <el-button link type="danger" size="small" @click="handlePermanentDelete(row.id)">永久删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <el-dialog v-model="showDialog" :title="editingKb ? '编辑知识库' : '新建知识库'" width="480px">
      <el-form :model="form" :rules="formRules" ref="kbFormRef" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入知识库名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入描述" />
        </el-form-item>
        <el-form-item label="工作空间">
          <el-select v-model="form.workspace_id" clearable placeholder="不选择则为个人知识库" style="width: 100%">
            <el-option v-for="ws in writableWorkspaces" :key="ws.id" :label="`${ws.name}（${roleLabel(ws.role)}）`" :value="ws.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <template #label>
            <span>Embedding 模型
              <el-tooltip content="用于将文本转换为向量，实现语义搜索。如未配置，请先到模型管理中添加。" placement="top">
                <el-icon class="help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <el-select v-model="form.embedding_model_id" placeholder="选择 Embedding 模型" clearable style="width: 100%">
            <el-option v-for="m in embeddingModels" :key="m.id" :label="m.display_name" :value="m.id" />
          </el-select>
          <div v-if="!embeddingModels.length" class="field-hint warning">
            <TriangleAlertIcon :size="13" :stroke-width="1.5" style="margin-right: 4px" />
            尚未配置 Embedding 模型，<el-button link type="primary" size="small" @click="$router.push('/models')">前往添加</el-button>
          </div>
        </el-form-item>
        <el-collapse v-model="showAdvanced" class="advanced-collapse">
          <el-collapse-item title="高级设置（可选）" name="advanced">
            <el-form-item>
              <template #label>
                <span>切片策略
                  <el-tooltip content="决定文档如何被拆分为小段。固定长度适合大多数场景，递归切分更智能。" placement="top">
                    <el-icon class="help-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select v-model="form.chunk_strategy" style="width: 100%">
                <el-option label="固定长度（推荐）" value="fixed" />
                <el-option label="按段落切分" value="paragraph" />
                <el-option label="递归智能切分" value="recursive" />
                <el-option label="按标题/章节切分" value="heading" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <template #label>
                <span>切片大小
                  <el-tooltip content="每个文本片段的最大字符数，通常 300-800 较合适。" placement="top">
                    <el-icon class="help-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input-number v-model="form.chunk_size" :min="100" :max="5000" :step="100" style="width: 100%" />
            </el-form-item>
            <el-form-item>
              <template #label>
                <span>切片重叠
                  <el-tooltip content="相邻片段间重叠的字符数，避免关键信息在分割处丢失。" placement="top">
                    <el-icon class="help-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-input-number v-model="form.chunk_overlap" :min="0" :max="500" :step="10" style="width: 100%" />
            </el-form-item>
            <el-form-item>
              <template #label>
                <span>检索模式
                  <el-tooltip content="混合检索结合语义理解和关键词匹配，效果最佳。" placement="top">
                    <el-icon class="help-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select v-model="form.search_mode" style="width: 100%">
                <el-option label="混合检索（推荐）" value="hybrid" />
                <el-option label="语义向量检索" value="vector" />
                <el-option label="关键词检索" value="keyword" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.search_mode === 'hybrid'">
              <template #label>
                <span>向量权重
                  <el-tooltip content="控制混合检索中语义向量搜索的权重（0=纯关键词, 1=纯向量, 0.7为推荐值）" placement="top">
                    <el-icon style="cursor: help"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-slider v-model="form.vector_weight" :min="0" :max="1" :step="0.1" :format-tooltip="(v: number) => `向量 ${(v*100).toFixed(0)}% / 关键词 ${((1-v)*100).toFixed(0)}%`" style="padding: 0 10px" />
            </el-form-item>
            <el-form-item label="开场白">
              <el-input v-model="form.welcome_message" type="textarea" :rows="2" placeholder="用户进入对话时看到的欢迎消息" />
            </el-form-item>
            <el-form-item label="推荐问题">
              <div class="tag-input-wrapper">
                <el-tag v-for="(q, i) in parsedQuestions" :key="i" closable @close="removeQuestion(Number(i))" class="question-tag">{{ q }}</el-tag>
                <el-input v-model="newQuestion" size="small" placeholder="输入推荐问题后按回车" @keydown.enter.prevent="addQuestion" style="width: 200px" />
              </div>
            </el-form-item>
            <el-form-item>
              <template #label>
                <span>Prompt 模板
                  <el-tooltip content="自定义 AI 的系统提示词。使用 {context} 代表检索到的参考资料。留空则使用默认模板。" placement="top">
                    <el-icon class="help-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <el-select
                v-model="form.prompt_template_id"
                placeholder="选择预设模板（可选）"
                clearable
                style="width: 100%; margin-bottom: 8px"
                @change="onTemplateSelect"
              >
                <el-option
                  v-for="tpl in templateOptions"
                  :key="tpl.id"
                  :label="tpl.name + (tpl.is_builtin ? ' (内置)' : '')"
                  :value="tpl.id"
                />
              </el-select>
              <el-input v-model="form.prompt_template" type="textarea" :rows="4" placeholder="留空使用默认模板。变量: {context} {question} {date} {kb_name} {history} {sql_context}" />
            </el-form-item>
          </el-collapse-item>

          <el-collapse-item name="compilation">
            <template #title>
              <BrainCircuit :size="14" :stroke-width="1.5" style="margin-right: 6px" />
              知识编译（Karpathy LLM Wiki）
            </template>
            <el-form-item label="启用知识编译">
              <el-switch v-model="compilationConfig.enabled" />
              <span style="margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary)">
                文档入库后自动编译为结构化知识文章
              </span>
            </el-form-item>
            <template v-if="compilationConfig.enabled">
              <el-form-item label="自动编译">
                <el-switch v-model="compilationConfig.auto_compile_on_ingest" />
                <span style="margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary)">
                  新文档上传后自动触发编译
                </span>
              </el-form-item>
              <el-form-item label="增量综合">
                <el-switch v-model="compilationConfig.incremental_synthesis" />
                <span style="margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary)">
                  新文档自动更新已有相关文章
                </span>
              </el-form-item>
              <el-form-item label="每组 Chunk 数">
                <el-input-number v-model="compilationConfig.max_chunks_per_group" :min="3" :max="30" />
              </el-form-item>
              <el-form-item label="健康检查">
                <el-switch v-model="compilationConfig.health_check_enabled" />
                <span style="margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary)">
                  定期检测矛盾、过时、冗余
                </span>
              </el-form-item>
              <el-form-item v-if="compilationConfig.health_check_enabled" label="检查间隔(小时)">
                <el-input-number v-model="compilationConfig.health_check_interval_hours" :min="1" :max="720" />
              </el-form-item>
            </template>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onActivated } from 'vue'
import {
  Plus as PlusIcon, Upload as UploadIcon, MoreHorizontal,
  Pencil as PencilIcon, Download as DownloadIcon, RefreshCw as RefreshCwIcon,
  Trash2 as Trash2Icon, FileText as FileTextIcon, Layers as LayersIcon,
  Clock as ClockIcon, Database as DatabaseIcon, TriangleAlert as TriangleAlertIcon,
  BrainCircuit,
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listKnowledgeBases, createKnowledgeBase, updateKnowledgeBase, deleteKnowledgeBase, importKnowledgeBase, exportKnowledgeBase, reindexKnowledgeBase, listTrashedKnowledgeBases, restoreKnowledgeBase, permanentDeleteKnowledgeBase } from '../../api/knowledgeBase'
import { getCompilationConfig, updateCompilationConfig } from '../../api/knowledgeCompilation'
import { listTemplates } from '../../api/promptTemplates'
import type { PromptTemplate } from '../../api/promptTemplates'
import { listModels } from '../../api/models'
import { relativeTime, roleLabel } from '../../utils/format'
import { listWorkspaces } from '../../api/workspaces'

const kbList = ref<any[]>([])
const workspaceList = ref<any[]>([])
const KB_ACCENT_COLORS = ['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1']
function cardAccentColor(index: number) { return KB_ACCENT_COLORS[index % KB_ACCENT_COLORS.length] }
const searchQuery = ref('')
const kbPage = ref(1)
const kbPageSize = 12
const filteredKbList = computed(() => {
  if (!searchQuery.value.trim()) return kbList.value
  const q = searchQuery.value.toLowerCase()
  return kbList.value.filter((kb: any) =>
    kb.name.toLowerCase().includes(q) || (kb.description || '').toLowerCase().includes(q)
  )
})
const paginatedKbList = computed(() => {
  const start = (kbPage.value - 1) * kbPageSize
  return filteredKbList.value.slice(start, start + kbPageSize)
})

const trashedList = ref<any[]>([])
const embeddingModels = ref<any[]>([])
const llmModels = ref<any[]>([])
const hasEmbeddingModel = computed(() => embeddingModels.value.length > 0)
const hasLlmModel = computed(() => llmModels.value.length > 0)
const writableWorkspaces = computed(() => workspaceList.value.filter((ws: any) => ['owner', 'admin', 'member'].includes(ws.role)))
const showDialog = ref(false)
const submitting = ref(false)
const loading = ref(false)
const editingKb = ref<any>(null)

const showAdvanced = ref<string[]>([])
const newQuestion = ref('')
const kbFormRef = ref<any>(null)
const formRules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
}

const parsedQuestions = computed(() => {
  if (!form.suggested_questions) return []
  try {
    return JSON.parse(form.suggested_questions)
  } catch {
    return []
  }
})

function addQuestion() {
  if (!newQuestion.value.trim()) return
  const current = parsedQuestions.value
  current.push(newQuestion.value.trim())
  form.suggested_questions = JSON.stringify(current)
  newQuestion.value = ''
}

function removeQuestion(index: number) {
  const current = parsedQuestions.value
  current.splice(index, 1)
  form.suggested_questions = current.length ? JSON.stringify(current) : ''
}

const form = reactive({
  name: '', description: '', workspace_id: null as number | null, embedding_model_id: null as number | null,
  chunk_strategy: 'fixed', chunk_size: 500, chunk_overlap: 50,
  search_mode: 'hybrid', vector_weight: 0.7, welcome_message: '', suggested_questions: '',
  prompt_template: '',
  prompt_template_id: null as number | null,
})

const compilationConfig = reactive({
  enabled: false,
  auto_compile_on_ingest: true,
  compilation_model_id: null as number | null,
  max_tokens_per_article: 4000,
  max_chunks_per_group: 12,
  health_check_enabled: false,
  health_check_interval_hours: 168,
  incremental_synthesis: true,
  synthesis_similarity_threshold: 0.65,
})

function resetCompilationConfig() {
  compilationConfig.enabled = false
  compilationConfig.auto_compile_on_ingest = true
  compilationConfig.compilation_model_id = null
  compilationConfig.max_tokens_per_article = 4000
  compilationConfig.max_chunks_per_group = 12
  compilationConfig.health_check_enabled = false
  compilationConfig.health_check_interval_hours = 168
  compilationConfig.incremental_synthesis = true
  compilationConfig.synthesis_similarity_threshold = 0.65
}

const templateOptions = ref<PromptTemplate[]>([])

async function loadTemplateOptions() {
  try { templateOptions.value = await listTemplates() } catch {}
}

function onTemplateSelect(id: number | null) {
  if (!id) return
  const tpl = templateOptions.value.find(t => t.id === id)
  if (tpl) form.prompt_template = tpl.content
}

function resetForm() {
  form.name = ''
  form.description = ''
  form.workspace_id = null
  form.embedding_model_id = null
  form.chunk_strategy = 'fixed'
  form.chunk_size = 500
  form.chunk_overlap = 50
  form.search_mode = 'hybrid'
  form.vector_weight = 0.7
  form.welcome_message = ''
  form.suggested_questions = ''
  form.prompt_template = ''
  form.prompt_template_id = null
  editingKb.value = null
  resetCompilationConfig()
}

function openCreateDialog() {
  resetForm()
  // 自动选择默认或唯一的 Embedding 模型
  if (embeddingModels.value.length === 1) {
    form.embedding_model_id = embeddingModels.value[0].id
  } else {
    const defaultModel = embeddingModels.value.find((m: any) => m.is_default)
    if (defaultModel) form.embedding_model_id = defaultModel.id
  }
  // Auto-expand advanced settings when no embedding model is available
  if (!embeddingModels.value.length) {
    showAdvanced.value = ['advanced']
  }
  showDialog.value = true
}


async function loadData() {
  loading.value = true
  try {
    const [kbsRes, embedRes, llmsRes, wsRes] = await Promise.allSettled([
      listKnowledgeBases(),
      listModels('embedding'),
      listModels('llm'),
      listWorkspaces(),
    ])
    if (kbsRes.status === 'fulfilled') kbList.value = kbsRes.value as any
    if (embedRes.status === 'fulfilled') embeddingModels.value = embedRes.value as any
    if (llmsRes.status === 'fulfilled') llmModels.value = llmsRes.value as any
    if (wsRes.status === 'fulfilled') workspaceList.value = wsRes.value as any
    try { trashedList.value = (await listTrashedKnowledgeBases()) as any } catch { trashedList.value = [] }
  } catch {
    // handled by interceptor
  } finally {
    loading.value = false
  }
}

function editKb(kb: any) {
  editingKb.value = kb
  form.name = kb.name
  form.description = kb.description || ''
  form.workspace_id = kb.workspace_id ?? null
  form.embedding_model_id = kb.embedding_model_id
  form.chunk_strategy = kb.chunk_strategy || 'fixed'
  form.chunk_size = kb.chunk_size || 500
  form.chunk_overlap = kb.chunk_overlap || 50
  form.search_mode = kb.search_mode || 'hybrid'
  form.vector_weight = kb.vector_weight ?? 0.7
  form.welcome_message = kb.welcome_message || ''
  form.suggested_questions = kb.suggested_questions || ''
  form.prompt_template = kb.prompt_template || ''
  form.prompt_template_id = kb.prompt_template_id || null
  // Load compilation config
  resetCompilationConfig()
  getCompilationConfig(kb.id).then(res => {
    const cfg = res.data
    if (cfg) {
      compilationConfig.enabled = cfg.enabled ?? false
      compilationConfig.auto_compile_on_ingest = cfg.auto_compile_on_ingest ?? true
      compilationConfig.compilation_model_id = cfg.compilation_model_id ?? null
      compilationConfig.max_tokens_per_article = cfg.max_tokens_per_article ?? 4000
      compilationConfig.max_chunks_per_group = cfg.max_chunks_per_group ?? 12
      compilationConfig.health_check_enabled = cfg.health_check_enabled ?? false
      compilationConfig.health_check_interval_hours = cfg.health_check_interval_hours ?? 168
      compilationConfig.incremental_synthesis = cfg.incremental_synthesis ?? true
      compilationConfig.synthesis_similarity_threshold = cfg.synthesis_similarity_threshold ?? 0.65
    }
  }).catch(() => {})
  showDialog.value = true
}

async function handleSubmit() {
  try { await kbFormRef.value?.validate() } catch { return }
  submitting.value = true
  try {
    if (editingKb.value) {
      await updateKnowledgeBase(editingKb.value.id, form)
      // Save compilation config
      await updateCompilationConfig(editingKb.value.id, { ...compilationConfig }).catch(() => {})
      ElMessage.success('更新成功')
    } else {
      const res = await createKnowledgeBase(form) as any
      // Save compilation config for new KB
      const newKbId = res?.id
      if (newKbId && compilationConfig.enabled) {
        await updateCompilationConfig(newKbId, { ...compilationConfig }).catch(() => {})
      }
      ElMessage.success('创建成功')
    }
    showDialog.value = false
    resetForm()
    await loadData()
  } finally {
    submitting.value = false
  }
}

async function removeKb(id: number) {
  const kb = kbList.value.find((k: any) => k.id === id)
  const name = kb?.name ? `「${kb.name}」` : '该知识库'
  try {
    await ElMessageBox.confirm(`${name}将移入回收站，可随时恢复。`, '确认删除', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteKnowledgeBase(id)
    ElMessage.success('已移入回收站')
    await loadData()
  } catch { /* interceptor handles */ }
}

async function handleRestore(id: number) {
  try {
    await restoreKnowledgeBase(id)
    ElMessage.success('知识库已恢复')
    await loadData()
  } catch { /* interceptor handles */ }
}

async function handlePermanentDelete(id: number) {
  const kb = trashedList.value.find((k: any) => k.id === id)
  const name = kb?.name ? `「${kb.name}」` : '该知识库'
  try {
    await ElMessageBox.confirm(`永久删除${name}后无法恢复，确定继续？`, '永久删除', { type: 'error', confirmButtonText: '永久删除' })
  } catch { return }
  try {
    await permanentDeleteKnowledgeBase(id)
    ElMessage.success('已永久删除')
    await loadData()
  } catch { /* interceptor handles */ }
}

function handleExport(kbId: number) {
  exportKnowledgeBase(kbId)
}

async function handleReindex(kbId: number) {
  try {
    await ElMessageBox.confirm('重建索引将删除现有向量数据并重新嵌入所有切片，耗时较长，确定继续？', '重建索引', { type: 'warning' })
  } catch { return }
  const loading = ElMessage({ message: '正在重建索引...', type: 'info', duration: 0 })
  try {
    const res: any = await reindexKnowledgeBase(kbId)
    loading.close()
    ElMessage.success(res.message || '重建完成')
  } catch (e: any) {
    loading.close()
    ElMessage.error(e.message || '重建失败')
  }
}

async function handleImport(file: File) {
  try {
    const res: any = await importKnowledgeBase(file)
    ElMessage.success(`导入成功：${res.kb_name}（${res.doc_count} 文档，${res.chunk_count} 片段）`)
    await loadData()
  } catch {
    // handled by interceptor
  }
  return false
}

onActivated(() => {
  loadData()
  loadTemplateOptions()
})
</script>

<style scoped>
/* ══════════════════════════════════════════
   Knowledge — Google Cloud Style Cards
   ══════════════════════════════════════════ */
.knowledge-page {
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

/* ── Cards ── */
.kb-card {
  margin-bottom: 16px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg) !important;
  box-shadow: var(--shadow-card) !important;
  transition: box-shadow var(--duration-base) var(--ease-out),
              transform var(--duration-base) var(--ease-out),
              border-color var(--duration-base) var(--ease-out);
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.kb-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--card-accent, var(--primary));
  opacity: 0.7;
  transition: opacity var(--duration-base) var(--ease-out);
}

.kb-card:hover {
  box-shadow: var(--shadow-lg) !important;
  transform: translateY(-3px);
  border-color: var(--border-color);
}

.kb-card:hover::before {
  opacity: 1;
  height: 4px;
}

.kb-card:active {
  transform: translateY(-1px);
  transition-duration: 80ms;
}

.kb-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.kb-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.more-icon {
  cursor: pointer;
  color: var(--gray-400);
  transition: color var(--duration-fast);
}

.more-icon:hover {
  color: var(--text-secondary);
}

.kb-desc {
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 16px;
  min-height: 36px;
  line-height: 1.5;
}

.kb-meta-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.kb-stats {
  display: flex;
  gap: 16px;
  color: var(--text-secondary);
  font-size: 12px;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: var(--gray-50);
  border-radius: var(--radius);
  border: 1px solid var(--border-subtle);
}

.kb-stats span {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}

.kb-processing {
  color: #f59e0b;
}

.pulse-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f59e0b;
  margin-right: 4px;
  animation: pulse-dot-anim 1.4s ease-in-out infinite;
}

@keyframes pulse-dot-anim {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.4); }
}

.kb-no-model {
  color: var(--el-color-warning);
}

.kb-update-time {
  margin-left: auto;
  font-weight: 400;
  color: var(--text-muted);
  font-size: 11px;
}

.kb-actions {
  display: flex;
  gap: 8px;
}

.kb-actions .el-button {
  flex: 1;
}

.kb-pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.danger {
  color: var(--danger) !important;
}

.advanced-collapse {
  border: none;
  margin-top: -10px;
}

.advanced-collapse :deep(.el-collapse-item__header) {
  background: transparent;
  font-size: 13px;
  color: var(--text-muted);
  border: none;
  height: 36px;
}

.advanced-collapse :deep(.el-collapse-item__wrap) {
  border: none;
}

.help-icon {
  color: var(--gray-400);
  margin-left: 4px;
  cursor: help;
}

.field-hint {
  font-size: 12px;
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.field-hint.warning {
  color: var(--warning);
}

.tag-input-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.question-tag {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kb-skeleton-card {
  padding: 20px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  background: var(--card-bg);
  margin-bottom: 16px;
}
</style>
