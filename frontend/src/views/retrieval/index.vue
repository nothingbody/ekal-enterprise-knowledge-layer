<template>
  <div class="retrieval-page">
    <div class="page-header">
      <h2>检索测试</h2>
      <span class="page-desc">测试知识库检索效果，调优参数</span>
    </div>

    <el-alert v-if="!searchDone && !searching" type="info" :closable="true" style="margin-bottom: 16px;" show-icon>
      <template #title>
        <span>选择一个知识库，输入问题后点击「检索」，系统会返回最相关的文档片段及相关度评分。您可以通过调整「返回数量」和「最低相关度」参数来优化检索效果。</span>
      </template>
    </el-alert>

    <el-card class="query-card">
      <div class="query-form">
        <div class="query-row">
          <el-select v-model="kbId" placeholder="选择知识库" style="width: 220px" filterable>
            <el-option v-for="kb in kbList" :key="kb.id" :label="kb.name" :value="kb.id" />
          </el-select>
          <el-input v-model="query" placeholder="输入检索查询..." style="flex: 1" @keyup.enter="doSearch" clearable>
            <template #prefix><SearchIcon :size="14" :stroke-width="1.5" /></template>
          </el-input>
          <el-button type="primary" @click="doSearch" :loading="searching" :disabled="!kbId || !query.trim()">
            检索
          </el-button>
        </div>
        <div class="query-params">
          <div class="param-item">
            <span class="param-label">返回数量</span>
            <el-input-number v-model="topK" :min="1" :max="50" size="small" />
          </div>
          <div class="param-item">
            <el-tooltip content="过滤低相关度结果。推荐值：0.3~0.5，设为 0 则不过滤" placement="top" :show-after="300">
              <span class="param-label">最低相关度</span>
            </el-tooltip>
            <el-input-number v-model="threshold" :min="0" :max="1" :step="0.05" :precision="2" size="small" />
          </div>
          <div class="param-item">
            <el-checkbox v-model="multiKb">跨知识库检索</el-checkbox>
          </div>
          <div v-if="multiKb" class="param-item">
            <el-select v-model="extraKbIds" placeholder="选择其他知识库" multiple style="width: 220px" size="small" filterable>
              <el-option v-for="kb in kbList.filter((k: any) => k.id !== kbId)" :key="kb.id" :label="kb.name" :value="kb.id" />
            </el-select>
          </div>
        </div>
      </div>
    </el-card>

    <!-- searching state -->
    <div v-if="searching" class="searching-hint">
      <Loader2Icon :size="18" :stroke-width="1.5" class="spin-icon" />
      <span>正在检索知识库，请稍候…</span>
    </div>

    <!-- result summary -->
    <div v-if="searchDone && !searching" class="result-summary">
      <span v-if="results.length">共找到 <strong>{{ results.length }}</strong> 条相关结果</span>
      <span v-else>未找到相关内容</span>
      <span v-if="searchTime" class="search-time">{{ formatTime(searchTime) }}</span>
      <el-tag v-if="rerankerUsed === true" type="success" size="small">Reranker 已启用</el-tag>
      <el-tag v-else-if="rerankerUsed === false" type="info" size="small">Reranker 未使用</el-tag>
    </div>

    <div class="results-list">
      <div v-for="(r, idx) in results" :key="idx" class="result-card" :class="{ expanded: expandedSet.has(idx) }">
        <div class="result-header" @click="toggleExpand(idx)">
          <div class="result-rank" :class="scoreClass(r.score)">{{ idx + 1 }}</div>
          <div class="result-meta">
            <span class="result-doc">
              <FileTextIcon :size="13" :stroke-width="1.5" style="margin-right: 3px; vertical-align: -2px; opacity: .5" />
              {{ r.doc_name || '未知文档' }}
            </span>
            <el-tag size="small" :type="scoreTagType(r.score)" disable-transitions>{{ scoreLabel(r.score) }}</el-tag>
          </div>
          <div class="result-actions">
            <el-tooltip content="复制内容" placement="top" :show-after="400">
              <el-button text size="small" @click.stop="copyContent(r.content)">
                <CopyIcon :size="14" :stroke-width="1.5" />
              </el-button>
            </el-tooltip>
            <ChevronDownIcon :size="14" :stroke-width="1.5" class="expand-chevron" :class="{ rotated: expandedSet.has(idx) }" />
          </div>
        </div>
        <div class="result-content" :class="{ collapsed: !expandedSet.has(idx) }">
          <div v-html="highlightContent(r.content)" class="content-text"></div>
        </div>
        <div class="result-footer">
          <span class="footer-item">相关度 {{ (r.score * 100).toFixed(1) }}%</span>
          <span class="footer-sep">·</span>
          <span class="footer-item">片段 #{{ r.chunk_index ?? '-' }}</span>
        </div>
      </div>

      <el-empty v-if="searchDone && !searching && !results.length" description="未找到相关内容，尝试调整查询词或降低最低相关度" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onActivated } from 'vue'
import { Search as SearchIcon, FileText as FileTextIcon, Copy as CopyIcon, ChevronDown as ChevronDownIcon, Loader2 as Loader2Icon } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { listKnowledgeBases } from '../../api/knowledgeBase'
import { searchKnowledge, searchMultiKb } from '../../api/chat'
import { formatDuration as formatTime } from '../../utils/format'

const kbList = ref<any[]>([])
const kbId = ref<number | null>(null)
const query = ref('')
const topK = ref(10)
const threshold = ref(0)
const multiKb = ref(false)
const extraKbIds = ref<number[]>([])
const results = ref<any[]>([])
const rerankerUsed = ref<boolean | null>(null)
const searching = ref(false)
const searchDone = ref(false)
const searchTime = ref(0)
const expandedSet = reactive(new Set<number>())

function scoreClass(score: number) {
  if (score >= 0.7) return 'score-high'
  if (score >= 0.4) return 'score-mid'
  return 'score-low'
}

function scoreLabel(score: number) {
  if (score >= 0.7) return '高度相关'
  if (score >= 0.4) return '中等相关'
  if (score >= 0.2) return '低相关'
  return '弱相关'
}

function scoreTagType(score: number) {
  if (score >= 0.7) return 'success'
  if (score >= 0.4) return 'warning'
  return 'info'
}


function toggleExpand(idx: number) {
  if (expandedSet.has(idx)) expandedSet.delete(idx)
  else expandedSet.add(idx)
}

function highlightContent(content: string) {
  if (!content || !query.value.trim()) return escapeHtml(content || '')
  const keywords = query.value.trim().split(/\s+/).filter(Boolean)
  let html = escapeHtml(content)
  for (const kw of keywords) {
    const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    html = html.replace(new RegExp(escaped, 'gi'), m => `<mark>${m}</mark>`)
  }
  return html
}

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

async function copyContent(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败')
  }
}

async function doSearch() {
  if (!kbId.value || !query.value.trim()) return
  searching.value = true
  searchDone.value = false
  expandedSet.clear()
  const start = Date.now()
  try {
    let res: any
    const scoreThreshold = threshold.value > 0 ? threshold.value : undefined
    if (multiKb.value && extraKbIds.value.length) {
      const allIds = [kbId.value, ...extraKbIds.value]
      res = await searchMultiKb({
        kb_ids: allIds,
        query: query.value,
        top_k: topK.value,
        score_threshold: scoreThreshold,
      })
      results.value = (res as any[]) || []
      rerankerUsed.value = null
    } else {
      res = await searchKnowledge({
        kb_id: kbId.value,
        query: query.value,
        top_k: topK.value,
        score_threshold: scoreThreshold,
      })
      const wrapped = res as any
      results.value = wrapped.results || wrapped || []
      rerankerUsed.value = wrapped.reranker_used ?? null
    }
    // Auto-expand first result
    if (results.value.length) expandedSet.add(0)
  } catch (e: any) {
    ElMessage.error(e.message || '检索失败')
    results.value = []
  }
  searchTime.value = Date.now() - start
  searchDone.value = true
  searching.value = false
}

onActivated(async () => {
  try {
    kbList.value = (await listKnowledgeBases()) as any
  } catch {
    ElMessage.error('知识库列表加载失败，请刷新页面重试')
  }
})
</script>

<style scoped>
.retrieval-page {
  max-width: 900px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  margin-bottom: 4px;
}

.page-desc {
  font-size: 13px;
  color: var(--text-muted);
}

.query-card {
  margin-bottom: 20px;
}

.query-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.query-params {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-top: 12px;
  flex-wrap: wrap;
}

.param-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.param-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
}

/* --- searching hint --- */
.searching-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 0;
  font-size: 13px;
  color: var(--text-muted);
}

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* --- result summary --- */
.result-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.search-time {
  color: var(--text-muted);
  font-size: 12px;
  background: var(--gray-100);
  padding: 1px 8px;
  border-radius: var(--radius-sm);
}

/* --- results list --- */
.results-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 60px;
}

.result-card {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  transition: border-color var(--duration-fast), box-shadow var(--duration-fast);
  overflow: hidden;
}

.result-card:hover {
  border-color: var(--primary-lighter, #b3d8ff);
}

.result-card.expanded {
  box-shadow: var(--shadow-sm);
}

/* --- header --- */
.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}

.result-rank {
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--gray-300);
}

.result-rank.score-high {
  background: var(--success, #059669);
}

.result-rank.score-mid {
  background: var(--warning, #d97706);
}

.result-rank.score-low {
  background: var(--gray-400, #9ca3af);
}

.result-meta {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.result-doc {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.expand-chevron {
  color: var(--text-muted);
  transition: transform 0.2s;
}

.expand-chevron.rotated {
  transform: rotate(180deg);
}

/* --- content --- */
.result-content {
  padding: 0 16px;
  overflow: hidden;
  transition: max-height 0.25s ease, padding 0.25s ease;
}

.result-content.collapsed {
  max-height: 72px;
  /* 3 lines preview */
}

.result-content:not(.collapsed) {
  max-height: 600px;
  overflow-y: auto;
  padding-bottom: 8px;
}

.content-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.content-text :deep(mark) {
  background: #fef08a;
  color: inherit;
  border-radius: 2px;
  padding: 0 2px;
}

/* --- footer --- */
.result-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px 10px;
  font-size: 11px;
  color: var(--text-muted);
}

.footer-sep {
  opacity: 0.4;
}

@media (max-width: 768px) {
  .query-row {
    flex-direction: column;
  }

  .query-row .el-select,
  .query-row .el-input {
    width: 100% !important;
  }

  .query-params {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
