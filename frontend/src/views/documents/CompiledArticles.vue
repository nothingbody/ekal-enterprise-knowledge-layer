<template>
  <div class="compiled-articles-section">
    <div class="section-header" @click="expanded = !expanded">
      <div class="section-title">
        <BookOpenIcon :size="14" :stroke-width="1.5" />
        <span>编译文章</span>
        <el-tag size="small" type="success" v-if="articles.length">{{ articles.length }}</el-tag>
      </div>
      <ChevronRightIcon :size="14" :stroke-width="1.5" class="expand-icon" :class="{ rotated: expanded }" />
    </div>

    <div v-show="expanded" class="section-body">
      <div class="section-toolbar">
        <div class="toolbar-left">
          <el-tag v-if="status" size="small" :type="statusEnabled ? 'success' : 'info'">
            {{ statusEnabled ? '已启用' : '未启用' }}
          </el-tag>
          <span v-if="status && status.total_articles" class="stat-text">
            {{ status.compiled_articles }} 篇已编译
            <span v-if="status.outdated_articles"> / {{ status.outdated_articles }} 篇待更新</span>
          </span>
        </div>
        <div class="toolbar-right" v-if="canManage">
          <el-button size="small" type="primary" plain @click="handleCompileAll" :loading="compiling">
            <RefreshCwIcon :size="13" :stroke-width="1.5" style="margin-right: 4px" />全量编译
          </el-button>
        </div>
      </div>

      <div v-loading="loading">
        <div v-if="!loading && articles.length === 0" class="empty-tip">
          暂无编译文章
          <template v-if="canManage">
            <span v-if="!statusEnabled">，请先在知识库设置中启用「知识编译」功能</span>
            <el-button v-else link type="primary" @click="handleCompileAll" style="margin-left: 4px">开始编译</el-button>
          </template>
        </div>

        <div v-for="article in articles" :key="article.id" class="article-card">
          <div class="article-card-header">
            <div class="article-info">
              <span class="article-title">{{ article.title }}</span>
              <el-tag size="small" :type="articleStatusType(article.status)">{{ articleStatusLabel(article.status) }}</el-tag>
              <el-tag size="small" type="info">v{{ article.version }}</el-tag>
            </div>
            <div class="article-actions">
              <el-button link size="small" type="primary" @click="toggleExpand(article.id)">
                {{ expandedArticles.has(article.id) ? '收起' : '展开' }}
              </el-button>
              <el-button v-if="canManage" link size="small" type="primary" @click="openEdit(article)">编辑</el-button>
              <el-button v-if="canManage" link size="small" type="danger" @click="handleDelete(article)">删除</el-button>
            </div>
          </div>
          <div class="article-meta">
            <span v-if="article.summary" class="article-summary">{{ article.summary }}</span>
            <div v-if="article.tags?.length" class="article-tags">
              <el-tag v-for="tag in article.tags" :key="tag" size="small" type="info" effect="plain">{{ tag }}</el-tag>
            </div>
          </div>
          <div v-if="expandedArticles.has(article.id)" class="article-content">
            <div v-html="renderMarkdown(article.content)" class="markdown-body"></div>
            <div v-if="article.source_doc_ids?.length" class="article-sources">
              <span class="sources-label">来源文档 ID:</span> {{ article.source_doc_ids.join(', ') }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Edit dialog -->
    <el-dialog v-model="editDialog" title="编辑文章" width="700px" destroy-on-close>
      <el-form v-if="editForm" label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="editForm.title" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="editForm.summary" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="editForm.content" type="textarea" :rows="12" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEdit" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { BookOpen as BookOpenIcon, ChevronRight as ChevronRightIcon, RefreshCw as RefreshCwIcon } from 'lucide-vue-next'
import { renderMarkdown } from '../../utils/markdown'
import {
  listArticles, updateArticle, deleteArticle,
  triggerCompileKb, getCompilationStatus,
} from '../../api/knowledgeCompilation'

const props = defineProps<{
  kbId: number
  canManage: boolean
}>()

const expanded = ref(false)
const loading = ref(false)
const compiling = ref(false)
const saving = ref(false)
const articles = ref<any[]>([])
const status = ref<any>(null)
const expandedArticles = ref<Set<number>>(new Set())
const editDialog = ref(false)
const editForm = ref<any>(null)

const statusEnabled = computed(() => status.value?.enabled ?? false)

function articleStatusType(s: string) {
  const map: Record<string, string> = { compiled: 'success', drafting: 'warning', outdated: 'danger', archived: 'info' }
  return map[s] || 'info'
}
function articleStatusLabel(s: string) {
  const map: Record<string, string> = { compiled: '已编译', drafting: '草稿', outdated: '待更新', archived: '已归档' }
  return map[s] || s
}

function toggleExpand(id: number) {
  if (expandedArticles.value.has(id)) expandedArticles.value.delete(id)
  else expandedArticles.value.add(id)
}

function openEdit(article: any) {
  editForm.value = { id: article.id, title: article.title, summary: article.summary, content: article.content }
  editDialog.value = true
}

async function handleSaveEdit() {
  if (!editForm.value) return
  saving.value = true
  try {
    await updateArticle(editForm.value.id, {
      title: editForm.value.title,
      summary: editForm.value.summary,
      content: editForm.value.content,
    })
    ElMessage.success('保存成功')
    editDialog.value = false
    loadData()
  } catch { ElMessage.error('保存失败') } finally { saving.value = false }
}

async function handleDelete(article: any) {
  await ElMessageBox.confirm(`确定删除文章「${article.title}」？`, '确认删除', { type: 'warning' })
  try {
    await deleteArticle(article.id)
    ElMessage.success('已删除')
    loadData()
  } catch { ElMessage.error('删除失败') }
}

async function handleCompileAll() {
  await ElMessageBox.confirm('全量编译将重新编译所有文档，可能需要较长时间和较多 Token，确定继续？', '全量编译', { type: 'info' })
  compiling.value = true
  try {
    await triggerCompileKb(props.kbId)
    ElMessage.success('编译任务已提交，请稍后刷新查看')
  } catch { ElMessage.error('提交失败') } finally { compiling.value = false }
}

async function loadData() {
  loading.value = true
  try {
    const [articlesRes, statusRes] = await Promise.all([
      listArticles(props.kbId, { limit: 50 }),
      getCompilationStatus(props.kbId),
    ])
    articles.value = articlesRes.data || []
    status.value = statusRes.data || null
  } catch { /* ignore */ } finally { loading.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.compiled-articles-section { margin-bottom: 20px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; cursor: pointer; border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px; background: var(--el-fill-color-blank);
  transition: background 0.2s;
}
.section-header:hover { background: var(--el-fill-color-light); }
.section-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 500; }
.expand-icon { transition: transform 0.2s; }
.expand-icon.rotated { transform: rotate(90deg); }
.section-body { padding: 12px 0; }
.section-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.toolbar-left { display: flex; align-items: center; gap: 8px; }
.stat-text { font-size: 12px; color: var(--el-text-color-secondary); }
.empty-tip { text-align: center; color: var(--el-text-color-secondary); padding: 24px 0; font-size: 13px; }

.article-card {
  border: 1px solid var(--el-border-color-lighter); border-radius: 8px;
  padding: 12px 16px; margin-bottom: 10px;
  transition: box-shadow 0.2s;
}
.article-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.article-card-header { display: flex; align-items: center; justify-content: space-between; }
.article-info { display: flex; align-items: center; gap: 8px; }
.article-title { font-weight: 500; font-size: 14px; }
.article-meta { margin-top: 6px; }
.article-summary { font-size: 12px; color: var(--el-text-color-secondary); display: block; margin-bottom: 4px; }
.article-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.article-content { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.article-sources { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.sources-label { font-weight: 500; }
.markdown-body { font-size: 13px; line-height: 1.7; }
.markdown-body h1, .markdown-body h2, .markdown-body h3 { margin-top: 12px; margin-bottom: 6px; }
</style>
