<template>
  <el-drawer
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    size="720px"
    direction="rtl"
    :close-on-click-modal="false"
    class="editor-drawer"
  >
    <template #header>
      <div class="drawer-header-content">
        <span>{{ editingId ? '编辑内容' : '新增内容' }}</span>
        <el-tag v-if="editingId" type="info" size="small" effect="plain" round>ID: {{ editingId }}</el-tag>
      </div>
    </template>

    <el-form :model="form" :rules="formRules" ref="formRef" label-position="top" class="editor-form" @submit.prevent>
      <el-form-item label="内容类型" prop="content_type">
        <el-radio-group v-model="form.content_type">
          <el-radio-button value="announcement">公告</el-radio-button>
          <el-radio-button value="changelog">更新日志</el-radio-button>
          <el-radio-button value="faq">FAQ</el-radio-button>
          <el-radio-button value="page">页面</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="标题" prop="title">
        <el-input v-model="form.title" placeholder="请输入内容标题" maxlength="200" show-word-limit />
      </el-form-item>

      <el-form-item label="URL 标识 (Slug)">
        <el-input v-model="form.slug" placeholder="可选，用于 URL 访问">
          <template #prepend>/</template>
        </el-input>
      </el-form-item>

      <div v-if="form.content_type === 'changelog'" class="changelog-row">
        <el-form-item label="版本号" style="flex: 1">
          <el-input v-model="form.version" placeholder="如 v0.2.0" />
        </el-form-item>
        <el-form-item label="发布日期" style="flex: 1">
          <el-date-picker v-model="form.release_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" />
        </el-form-item>
      </div>

      <el-form-item label="摘要">
        <el-input v-model="form.summary" type="textarea" :rows="2" placeholder="简要描述（用于列表展示和 SEO）" maxlength="500" show-word-limit />
      </el-form-item>

      <div class="body-editor-section">
        <div class="body-editor-header">
          <span class="body-editor-label">正文 <span class="body-hint">支持 Markdown</span></span>
          <el-radio-group v-model="editorMode" size="small">
            <el-radio-button value="edit">编辑</el-radio-button>
            <el-radio-button value="preview">预览</el-radio-button>
          </el-radio-group>
        </div>
        <div v-if="editorMode === 'edit'" class="body-editor-pane">
          <el-input v-model="form.body" type="textarea" :rows="16" placeholder="在此输入 Markdown 格式的正文内容..." class="body-textarea" />
        </div>
        <div v-else class="body-preview-pane">
          <div v-if="form.body" class="markdown-body" v-html="renderedBody"></div>
          <div v-else class="preview-empty">输入正文内容后可在此预览</div>
        </div>
      </div>

      <div class="form-bottom-row">
        <el-form-item label="排序权重" style="flex: 0 0 180px">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" style="width: 100%" />
          <div class="form-hint">数值越大越靠前</div>
        </el-form-item>
        <el-form-item label="发布状态" style="flex: 0 0 auto">
          <el-switch
            v-model="form.is_published"
            inline-prompt
            active-text="发布"
            inactive-text="草稿"
            style="--el-switch-on-color: var(--el-color-success)"
          />
        </el-form-item>
      </div>
    </el-form>

    <template #footer>
      <div class="drawer-footer">
        <el-button @click="$emit('update:visible', false)">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveContent">
          {{ editingId ? '保存修改' : '创建内容' }}
        </el-button>
        <span class="shortcut-hint">Ctrl+S 快速保存</span>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { marked } from 'marked'
import request from '../../utils/request'

marked.use({ breaks: true })

const props = defineProps<{ visible: boolean; editingRow: any | null }>()
const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'saved'): void
}>()

const editingId = ref<number | null>(null)
const saving = ref(false)
const editorMode = ref<'edit' | 'preview'>('edit')
const formRef = ref<FormInstance>()
const originalExtra = ref<Record<string, any>>({})

const form = ref({
  content_type: 'announcement',
  title: '',
  slug: '',
  body: '',
  summary: '',
  sort_order: 0,
  is_published: true,
  version: '',
  release_date: '',
})

const formRules: FormRules = {
  content_type: [{ required: true, message: '请选择内容类型', trigger: 'change' }],
  title: [
    { required: true, message: '请输入标题', trigger: 'blur' },
    { max: 200, message: '标题不超过 200 个字符', trigger: 'blur' },
  ],
}

const renderedBody = computed(() => {
  if (!form.value.body) return ''
  try { return marked.parse(form.value.body) as string }
  catch { return '<p style="color: var(--el-color-danger)">Markdown 解析错误</p>' }
})

function initForm() {
  editorMode.value = 'edit'
  const row = props.editingRow
  if (row) {
    editingId.value = row.id ?? null
    const extra = typeof row.extra === 'object' ? row.extra : {}
    originalExtra.value = { ...extra }
    form.value = {
      content_type: row.content_type, title: row.title || '', slug: row.slug || '',
      body: row.body || '', summary: row.summary || '', sort_order: row.sort_order || 0,
      is_published: row.is_published ?? true, version: row.version || '',
      release_date: extra?.release_date || '',
    }
  } else {
    editingId.value = null
    originalExtra.value = {}
    form.value = {
      content_type: 'announcement', title: '', slug: '', body: '', summary: '',
      sort_order: 0, is_published: true, version: '', release_date: '',
    }
  }
  formRef.value?.clearValidate()
}

watch([() => props.visible, () => props.editingRow], ([vis]) => {
  if (vis) initForm()
})

async function saveContent() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload: any = { ...form.value }
    const extra = { ...originalExtra.value }
    if (payload.release_date) {
      extra.release_date = payload.release_date
    } else {
      delete extra.release_date
    }
    delete payload.release_date
    if (Object.keys(extra).length > 0) {
      payload.extra = extra
    }
    if (editingId.value) {
      await request.put(`/site/admin/${editingId.value}`, payload)
      ElMessage.success('更新成功')
    } else {
      await request.post('/site/admin/create', payload)
      ElMessage.success('创建成功')
    }
    emit('update:visible', false)
    emit('saved')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}

function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    if (props.visible && !saving.value) saveContent()
  }
}

onMounted(() => { document.addEventListener('keydown', handleKeydown) })
onUnmounted(() => { document.removeEventListener('keydown', handleKeydown) })
</script>

<style scoped>
.drawer-header-content {
  display: flex; align-items: center; gap: 12px; font-size: 16px; font-weight: 600;
}
.editor-form { padding: 0 4px; }
.changelog-row { display: flex; gap: 16px; }
.body-editor-section { margin-bottom: 22px; }
.body-editor-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
}
.body-editor-label { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.body-hint { font-size: 12px; font-weight: 400; color: var(--text-tertiary); margin-left: 6px; }
.body-textarea :deep(textarea) {
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 13px; line-height: 1.7;
}
.body-preview-pane {
  border: 1px solid var(--el-border-color); border-radius: 4px; padding: 16px 20px;
  min-height: 360px; max-height: 500px; overflow-y: auto; background: #FAFBFC;
}
.preview-empty {
  color: var(--text-tertiary); font-size: 14px; text-align: center; padding: 80px 0;
}

/* ── Markdown Preview Styles ── */
.markdown-body { font-size: 14px; line-height: 1.8; color: var(--text-primary); word-break: break-word; }
.markdown-body :deep(h1) { font-size: 24px; font-weight: 700; margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border-light); }
.markdown-body :deep(h2) { font-size: 20px; font-weight: 600; margin: 20px 0 10px; }
.markdown-body :deep(h3) { font-size: 16px; font-weight: 600; margin: 16px 0 8px; }
.markdown-body :deep(p) { margin: 8px 0; }
.markdown-body :deep(code) { font-family: 'SF Mono', 'Cascadia Code', monospace; font-size: 13px; padding: 2px 6px; background: #F1F5F9; border-radius: 4px; color: #E11D48; }
.markdown-body :deep(pre) { background: #1E293B; color: #E2E8F0; padding: 16px; border-radius: 8px; overflow-x: auto; margin: 12px 0; }
.markdown-body :deep(pre code) { background: none; color: inherit; padding: 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 24px; margin: 8px 0; }
.markdown-body :deep(li) { margin: 4px 0; }
.markdown-body :deep(blockquote) { border-left: 4px solid var(--el-color-primary-light-5); padding: 8px 16px; margin: 12px 0; color: var(--text-secondary); background: #F8FAFC; border-radius: 0 4px 4px 0; }
.markdown-body :deep(a) { color: var(--el-color-primary); text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; margin: 12px 0; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid var(--border-light); padding: 8px 12px; text-align: left; }
.markdown-body :deep(th) { background: #F8FAFC; font-weight: 600; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid var(--border-light); margin: 20px 0; }
.markdown-body :deep(img) { max-width: 100%; border-radius: 4px; }

.form-bottom-row { display: flex; align-items: flex-start; gap: 32px; }
.form-hint { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; }
.drawer-footer { display: flex; align-items: center; gap: 12px; }
.shortcut-hint {
  font-size: 12px; color: var(--text-tertiary); margin-left: auto;
  padding: 2px 8px; background: #F1F5F9; border-radius: 4px;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}
</style>
