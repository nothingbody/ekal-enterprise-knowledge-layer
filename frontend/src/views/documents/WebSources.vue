<template>
  <div v-if="sources.length || canManage" class="web-sources-section">
    <div class="section-header" @click="expanded = !expanded">
      <div class="section-title">
        <GlobeIcon :size="14" :stroke-width="1.5" />
        <span>网页数据源</span>
        <el-tag size="small" type="info" v-if="sources.length">{{ sources.length }}</el-tag>
      </div>
      <ChevronRightIcon :size="14" :stroke-width="1.5" class="expand-icon" :class="{ rotated: expanded }" />
    </div>

    <div v-show="expanded" class="section-body">
      <div v-loading="loading">
        <div v-if="!loading && sources.length === 0" class="empty-tip">暂无网页数据源</div>
        <div v-for="src in sources" :key="src.id" class="source-card">
          <div class="source-card-header">
            <div class="source-info">
              <GlobeIcon :size="14" :stroke-width="1.5" class="web-icon" />
              <a :href="src.url" target="_blank" rel="noopener noreferrer" class="source-url" @click.stop>{{ src.title || src.url }}</a>
              <el-tag size="small" type="info">{{ sourceTypeLabel(src.source_type) }}</el-tag>
              <el-tag size="small" :type="statusTagType(src.status)">{{ statusLabel(src.status) }}</el-tag>
              <el-tag v-if="src.crawl_count != null" size="small" type="info">抓取 {{ src.crawl_count }} 次</el-tag>
            </div>
            <div class="source-card-actions" v-if="canManage">
              <el-button v-if="src.status === 'completed'" link size="small" type="primary" @click="viewContent(src)">查看内容</el-button>
              <el-button link size="small" type="primary" @click="openScheduleDialog(src)">设置定时</el-button>
              <el-button link size="small" type="primary" @click="handleRecrawl(src)" :loading="src._recrawling">重新抓取</el-button>
              <el-button link size="small" type="danger" @click="handleDelete(src)">删除</el-button>
            </div>
          </div>
          <div class="source-meta" v-if="src.crawl_interval_hours != null || src.last_crawled_at || src.next_crawl_at">
            <span v-if="src.crawl_interval_hours != null" class="meta-item">{{ intervalLabel(src.crawl_interval_hours) }}</span>
            <span v-if="src.use_browser" class="meta-item">浏览器渲染</span>
            <span v-if="src.auto_reindex" class="meta-item">自动重建索引</span>
            <span v-if="src.last_crawled_at" class="meta-item">上次抓取: {{ relativeTime(src.last_crawled_at) }}</span>
            <span v-if="src.next_crawl_at" class="meta-item">下次抓取: {{ formatNextCrawl(src.next_crawl_at) }}</span>
          </div>
          <div v-if="src.error_message" class="source-error">
            <TriangleAlertIcon :size="13" :stroke-width="1.5" /> {{ src.error_message }}
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="scheduleDialogVisible" title="设置定时抓取" width="420px">
      <el-form label-width="120px">
        <el-form-item label="抓取间隔">
          <el-select v-model="scheduleForm.crawl_interval_hours" placeholder="选择抓取间隔" style="width: 100%">
            <el-option label="不定时（仅手动抓取）" :value="null" />
            <el-option label="每1小时" :value="1" />
            <el-option label="每6小时" :value="6" />
            <el-option label="每12小时" :value="12" />
            <el-option label="每天" :value="24" />
            <el-option label="每周" :value="168" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容变更自动重建索引">
          <el-switch v-model="scheduleForm.auto_reindex" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scheduleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSchedule" :loading="scheduleSaving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 查看抓取内容对话框 -->
    <el-dialog v-model="contentDialogVisible" :title="contentData.title || '网页内容'" width="720px" destroy-on-close>
      <div v-loading="contentLoading">
        <div v-if="contentData.content" style="margin-bottom: 12px;">
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="网址">
              <a :href="contentData.url" target="_blank" style="color: var(--el-color-primary);">{{ contentData.url }}</a>
            </el-descriptions-item>
            <el-descriptions-item label="字数">{{ contentData.content_length?.toLocaleString() }} 字</el-descriptions-item>
            <el-descriptions-item label="抓取次数">{{ contentData.crawl_count }} 次</el-descriptions-item>
            <el-descriptions-item label="上次抓取">{{ contentData.last_crawled_at ? relativeTime(contentData.last_crawled_at) : '-' }}</el-descriptions-item>
          </el-descriptions>
        </div>
        <el-input
          v-if="contentData.content"
          type="textarea"
          :model-value="contentData.content"
          :rows="18"
          readonly
          resize="vertical"
          style="font-size: 13px; line-height: 1.6;"
        />
        <el-empty v-else-if="!contentLoading" description="暂无抓取内容" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import {
  Globe as GlobeIcon,
  ChevronRight as ChevronRightIcon,
  TriangleAlert as TriangleAlertIcon,
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listWebSources, deleteWebSource, recrawlWebSource, updateWebSourceSchedule, getWebSourceContent } from '../../api/webSources'
import { relativeTime } from '../../utils/format'

const props = defineProps<{
  kbId: number
  canManage: boolean
}>()

const emit = defineEmits<{
  (e: 'changed'): void
}>()

const expanded = ref(true)
const loading = ref(false)
const sources = ref<(any & { _recrawling?: boolean })[]>([])

const scheduleDialogVisible = ref(false)
const scheduleSaving = ref(false)
const scheduleTargetId = ref<number | null>(null)
const scheduleForm = reactive({ crawl_interval_hours: null as number | null, auto_reindex: false })

let pollTimer: ReturnType<typeof setInterval> | null = null

// Content viewer
const contentDialogVisible = ref(false)
const contentLoading = ref(false)
const contentData = ref<any>({})

async function viewContent(src: any) {
  contentDialogVisible.value = true
  contentLoading.value = true
  contentData.value = {}
  try {
    const res: any = await getWebSourceContent(src.id)
    contentData.value = res
  } catch {
    ElMessage.error('获取内容失败')
  } finally {
    contentLoading.value = false
  }
}

const INTERVAL_LABELS: Record<number, string> = {
  1: '每1小时',
  6: '每6小时',
  12: '每12小时',
  24: '每天',
  168: '每周',
}

function intervalLabel(hours: number | null | undefined): string {
  if (hours == null) return '不定时'
  return INTERVAL_LABELS[hours] ?? `每${hours}小时`
}

function formatNextCrawl(dateStr: string | null | undefined): string {
  if (!dateStr || dateStr === 'None') return ''
  const d = new Date(dateStr)
  const diff = d.getTime() - Date.now()
  if (diff <= 0) return '即将抓取'
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}分钟后`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}小时后`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天后`
  return d.toLocaleString()
}

function statusTagType(s: string) {
  const m: Record<string, string> = { completed: 'success', crawling: 'warning', failed: 'danger', pending: 'info' }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = { completed: '已完成', crawling: '抓取中', failed: '失败', pending: '待抓取' }
  return m[s] || s
}

function sourceTypeLabel(type: string | null | undefined) {
  const m: Record<string, string> = {
    html: 'HTML',
    json: 'JSON',
    rss: 'RSS',
    sitemap: 'Sitemap',
  }
  return m[type || 'html'] || 'HTML'
}

async function loadSources(silent = false) {
  if (!silent) loading.value = true
  try {
    sources.value = (await listWebSources(props.kbId) as any) || []
    const hasCrawling = sources.value.some(s => ['pending', 'crawling'].includes(s.status))
    if (hasCrawling && !pollTimer) {
      pollTimer = setInterval(async () => {
        await loadSources(true)
      }, 5000)
    } else if (!hasCrawling && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  } finally {
    if (!silent) loading.value = false
  }
}

async function handleRecrawl(src: any) {
  try {
    await ElMessageBox.confirm(`确定重新抓取「${src.title || src.url}」？旧文档将被删除后重新抓取。`, '重新抓取', { type: 'warning' })
  } catch { return }
  src._recrawling = true
  try {
    await recrawlWebSource(src.id)
    ElMessage.success('重新抓取已启动')
    emit('changed')
    await loadSources()
  } catch {
    // handled by global interceptor
  } finally {
    src._recrawling = false
  }
}

async function handleDelete(src: any) {
  try {
    await ElMessageBox.confirm(`确定删除网页源「${src.title || src.url}」？相关文档将被清除。`, '确认删除', { type: 'warning' })
  } catch { return }
  try {
    await deleteWebSource(src.id)
    ElMessage.success('删除成功')
    emit('changed')
    await loadSources()
  } catch {
    // handled by global interceptor
  }
}

function openScheduleDialog(src: any) {
  scheduleTargetId.value = src.id
  scheduleForm.crawl_interval_hours = src.crawl_interval_hours ?? null
  scheduleForm.auto_reindex = !!src.auto_reindex
  scheduleDialogVisible.value = true
}

async function saveSchedule() {
  if (scheduleTargetId.value == null) return
  scheduleSaving.value = true
  try {
    await updateWebSourceSchedule(scheduleTargetId.value, {
      crawl_interval_hours: scheduleForm.crawl_interval_hours,
      auto_reindex: scheduleForm.auto_reindex,
    })
    ElMessage.success('定时设置已保存')
    scheduleDialogVisible.value = false
    emit('changed')
    await loadSources()
  } catch {
    // handled by global interceptor
  } finally {
    scheduleSaving.value = false
  }
}

defineExpose({ loadSources })

onMounted(() => {
  loadSources()
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<style scoped>
.web-sources-section {
  margin-bottom: 20px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  background: var(--bg-secondary, #fafafa);
  user-select: none;
  transition: background var(--duration-fast, 0.15s);
}

.section-header:hover {
  background: var(--bg-hover, #f0f0f0);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.expand-icon {
  transition: transform var(--duration-fast, 0.15s);
}

.expand-icon.rotated {
  transform: rotate(90deg);
}

.section-body {
  padding: 16px;
}

.empty-tip {
  text-align: center;
  color: #909399;
  padding: 20px 0;
  font-size: 13px;
}

.source-card {
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 10px 14px;
  margin-bottom: 8px;
  transition: border-color var(--duration-fast, 0.15s);
}

.source-card:hover {
  border-color: var(--primary-lighter, #409eff);
}

.source-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.source-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.web-icon {
  color: var(--primary, #409eff);
  flex-shrink: 0;
}

.source-url {
  color: var(--text-primary);
  text-decoration: none;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.source-url:hover {
  color: var(--primary, #409eff);
  text-decoration: underline;
}

.source-card-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.source-meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted, #909399);
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.source-meta .meta-item {
  white-space: nowrap;
}

.source-error {
  margin-top: 6px;
  padding: 6px 10px;
  background: var(--bg-danger, #fef0f0);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-danger, #f56c6c);
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
</style>
