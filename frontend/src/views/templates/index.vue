<template>
  <div class="templates-page">
    <div class="page-header">
      <h2>输出模板</h2>
      <el-button type="primary" @click="openCreate">
        <PlusIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />新建模板
      </el-button>
    </div>

    <div class="templates-grid" v-loading="loading">
      <div
        v-for="tpl in templates"
        :key="tpl.id"
        class="template-card"
        :class="{ builtin: tpl.is_builtin }"
        @click="openEdit(tpl)"
      >
        <div class="card-header">
          <div class="card-title">
            <FileTextIcon :size="16" :stroke-width="1.5" />
            <span>{{ tpl.name }}</span>
          </div>
          <div class="card-badges">
            <el-tag v-if="tpl.is_builtin" size="small" type="info">内置</el-tag>
            <el-tag size="small" :type="categoryType(tpl.category)">{{ categoryLabel(tpl.category) }}</el-tag>
          </div>
        </div>
        <div class="card-desc">{{ tpl.description || '暂无描述' }}</div>
        <div class="card-preview">{{ tpl.content.slice(0, 120) }}{{ tpl.content.length > 120 ? '...' : '' }}</div>
        <div class="card-footer">
          <span class="card-time">{{ tpl.updated_at ? new Date(tpl.updated_at).toLocaleDateString() : '' }}</span>
          <div class="card-actions" v-if="!tpl.is_builtin" @click.stop>
            <el-button link size="small" type="danger" @click="handleDelete(tpl)">删除</el-button>
          </div>
        </div>
      </div>

      <el-empty v-if="!loading && templates.length === 0" description="暂无模板" />
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? (isReadonly ? '查看模板' : '编辑模板') : '新建模板'"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="模板名称" :disabled="isReadonly" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%" :disabled="isReadonly">
            <el-option label="通用" value="general" />
            <el-option label="学术" value="academic" />
            <el-option label="简洁" value="concise" />
            <el-option label="报告" value="report" />
            <el-option label="技术" value="technical" />
            <el-option label="对话" value="conversational" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="模板描述（可选）" :disabled="isReadonly" />
        </el-form-item>
        <el-form-item label="模板内容">
          <div class="variable-hints">
            <span class="hint-label">可用变量：</span>
            <el-tag
              v-for="v in variables"
              :key="v.name"
              size="small"
              type="info"
              class="var-tag"
              @click="insertVariable(v.example)"
            >
              {{ v.example }} {{ v.label }}
            </el-tag>
          </div>
          <el-input
            ref="contentInput"
            v-model="form.content"
            type="textarea"
            :rows="12"
            placeholder="输入模板内容，使用 {context}、{question} 等变量"
            :disabled="isReadonly"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ isReadonly ? '关闭' : '取消' }}</el-button>
        <el-button v-if="isReadonly && editingId" type="primary" @click="duplicateTemplate">复制为新模板</el-button>
        <el-button v-if="!isReadonly" type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { Plus as PlusIcon, FileText as FileTextIcon } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listTemplates, createTemplate, updateTemplate, deleteTemplate, getVariables } from '../../api/promptTemplates'
import type { PromptTemplate, TemplateVariable } from '../../api/promptTemplates'

const loading = ref(false)
const saving = ref(false)
const templates = ref<PromptTemplate[]>([])
const variables = ref<TemplateVariable[]>([])
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const isReadonly = ref(false)
const contentInput = ref<any>(null)

const form = ref({
  name: '',
  description: '',
  content: '',
  category: 'custom',
})

const CATEGORY_MAP: Record<string, { label: string; type: string }> = {
  general: { label: '通用', type: '' },
  academic: { label: '学术', type: 'warning' },
  concise: { label: '简洁', type: 'success' },
  report: { label: '报告', type: 'primary' },
  technical: { label: '技术', type: 'danger' },
  conversational: { label: '对话', type: 'info' },
  custom: { label: '自定义', type: '' },
}

function categoryLabel(cat: string) { return CATEGORY_MAP[cat]?.label || cat }
function categoryType(cat: string) { return (CATEGORY_MAP[cat]?.type || '') as any }

async function loadTemplates() {
  loading.value = true
  try {
    templates.value = await listTemplates()
  } catch {} finally {
    loading.value = false
  }
}

async function loadVariables() {
  try { variables.value = await getVariables() } catch {}
}

function openCreate() {
  editingId.value = null
  isReadonly.value = false
  form.value = { name: '', description: '', content: '', category: 'custom' }
  dialogVisible.value = true
}

function openEdit(tpl: PromptTemplate) {
  editingId.value = tpl.id
  isReadonly.value = tpl.is_builtin
  form.value = {
    name: tpl.name,
    description: tpl.description || '',
    content: tpl.content,
    category: tpl.category,
  }
  dialogVisible.value = true
}

function duplicateTemplate() {
  editingId.value = null
  isReadonly.value = false
  form.value = { ...form.value, name: form.value.name + ' (副本)' }
}

function insertVariable(example: string) {
  if (isReadonly.value) return
  const el = contentInput.value?.$el?.querySelector('textarea') as HTMLTextAreaElement | null
  if (el) {
    const start = el.selectionStart ?? form.value.content.length
    const end = el.selectionEnd ?? start
    const before = form.value.content.slice(0, start)
    const after = form.value.content.slice(end)
    form.value.content = before + example + after
    nextTick(() => {
      const pos = start + example.length
      el.setSelectionRange(pos, pos)
      el.focus()
    })
  } else {
    form.value.content += example
  }
}

async function handleSave() {
  if (!form.value.name.trim()) { ElMessage.warning('请输入模板名称'); return }
  if (!form.value.content.trim()) { ElMessage.warning('请输入模板内容'); return }
  saving.value = true
  try {
    if (editingId.value) {
      await updateTemplate(editingId.value, form.value)
      ElMessage.success('模板已更新')
    } else {
      await createTemplate(form.value)
      ElMessage.success('模板已创建')
    }
    dialogVisible.value = false
    await loadTemplates()
  } catch {} finally {
    saving.value = false
  }
}

async function handleDelete(tpl: PromptTemplate) {
  try {
    await ElMessageBox.confirm(`确定删除模板「${tpl.name}」？`, '确认删除', { type: 'warning' })
  } catch { return }
  try {
    await deleteTemplate(tpl.id)
    ElMessage.success('模板已删除')
    await loadTemplates()
  } catch {}
}

onMounted(() => {
  loadTemplates()
  loadVariables()
})
</script>

<style scoped>
.templates-page {
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

.templates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.template-card {
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 16px;
  cursor: pointer;
  transition: border-color var(--duration-fast, 0.15s), box-shadow var(--duration-fast, 0.15s);
}

.template-card:hover {
  border-color: var(--primary-lighter, #409eff);
  box-shadow: var(--shadow-sm);
}

.template-card.builtin {
  background: var(--bg-secondary, #fafafa);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.card-badges {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.card-desc {
  font-size: 12px;
  color: var(--text-muted, #909399);
  margin-bottom: 8px;
  line-height: 1.4;
}

.card-preview {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  background: var(--gray-50, #f9f9f9);
  border-radius: 4px;
  padding: 8px 10px;
  max-height: 80px;
  overflow: hidden;
  font-family: var(--font-mono, monospace);
  white-space: pre-wrap;
  word-break: break-word;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
}

.card-time {
  font-size: 11px;
  color: var(--text-muted, #909399);
}

.variable-hints {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
}

.hint-label {
  font-size: 12px;
  color: var(--text-muted, #909399);
}

.var-tag {
  cursor: pointer;
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}

.var-tag:hover {
  opacity: 0.7;
}
</style>
