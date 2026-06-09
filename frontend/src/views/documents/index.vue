<template>
  <div class="documents-page" @dragenter.prevent="onDragEnter" @dragover.prevent @dragleave.prevent="onDragLeave" @drop.prevent="onDrop">
    <!-- Drag overlay -->
    <transition name="fade">
      <div v-if="canWrite && dragOver" class="drop-overlay">
        <div class="drop-overlay-inner">
          <UploadCloudIcon :size="48" :stroke-width="1.2" />
          <h3>松开即可上传</h3>
          <p>支持 PDF、Word、Excel、PPT、TXT、Markdown、HTML 等格式</p>
        </div>
      </div>
    </transition>
    <!-- Error state for invalid KB -->
    <div v-if="kbLoadError" class="kb-error-state">
      <el-result icon="warning" :title="kbLoadError" sub-title="请检查链接是否正确，或返回知识库列表">
        <template #extra>
          <el-button type="primary" @click="$router.push('/knowledge')">返回知识库列表</el-button>
        </template>
      </el-result>
    </div>

    <template v-if="!kbLoadError">
    <div class="page-header">
      <div class="header-left">
        <el-button text @click="$router.push('/knowledge')">
          <ArrowLeftIcon :size="16" :stroke-width="1.5" style="margin-right: 2px" />返回
        </el-button>
        <h2>文档管理</h2>
      </div>
      <div class="header-actions">
        <el-button v-if="canWrite && failedDocIds.length" type="warning" plain @click="batchRetryFailed" :loading="batchRetryLoading">
          批量重试失败 ({{ failedDocIds.length }})
        </el-button>
        <el-button v-if="canWrite && selectedIds.length" type="danger" @click="batchDelete">
          批量删除 ({{ selectedIds.length }})
        </el-button>
        <el-tooltip content="选择文件预览分块效果，不会上传" placement="bottom" :show-after="300">
          <el-upload
            :show-file-list="false"
            :before-upload="handlePreviewChunk"
            accept=".pdf,.doc,.docx,.txt,.md,.csv,.xlsx,.xls,.pptx,.html,.htm,.png,.jpg,.jpeg,.gif,.bmp,.webp"
            :action="''"
          >
            <el-button type="info" plain><EyeIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />分块预览</el-button>
          </el-upload>
        </el-tooltip>
        <el-button v-if="canWrite" @click="showWebDialog = true">
          <LinkIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />添加网页
        </el-button>
        <el-upload
          v-if="canWrite"
          :show-file-list="false"
          :before-upload="handleUpload"
          accept=".pdf,.doc,.docx,.txt,.md,.csv,.xlsx,.xls,.pptx,.html,.htm,.png,.jpg,.jpeg,.gif,.bmp,.webp"
          multiple
          :action="''"
        >
          <el-tooltip content="支持 PDF、Word、Excel、图片等格式，也可直接拖拽文件到页面上传" placement="bottom" :show-after="300">
            <el-button type="primary">
              <UploadIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />上传文档
            </el-button>
          </el-tooltip>
          <template #tip>
            <div class="upload-tip">重新上传同名文件将自动替换旧版本（增量更新）</div>
          </template>
        </el-upload>
      </div>
    </div>

    <!-- Missing embedding model warning -->
    <el-alert v-if="kbInfo && !kbInfo.embedding_model_id" type="warning" show-icon :closable="false" style="margin-bottom: 12px;">
      <template #title>
        该知识库未配置 Embedding 模型，上传的文档将无法向量化。请先
        <el-button type="primary" link size="small" @click="$router.push(`/knowledge`)">编辑知识库</el-button>
        选择 Embedding 模型，或
        <el-button type="primary" link size="small" @click="$router.push('/models')">前往添加模型</el-button>。
      </template>
    </el-alert>

    <!-- 即将过期文档警告 -->
    <el-alert v-if="expiringDocs.length > 0" type="warning" show-icon :closable="false" style="margin-bottom: 12px;">
      <template #title>
        有 {{ expiringDocs.length }} 个文档将在 7 天内过期，请及时处理。
        <el-button type="primary" link size="small" @click="tagFilter = ''; statusFilter = ''; docSearch = ''">查看全部</el-button>
      </template>
    </el-alert>

    <div style="display: flex; gap: 8px; margin-bottom: 12px;">
      <el-input v-model="docSearch" placeholder="搜索文件名..." clearable style="width: 220px" />
      <el-input v-model="tagFilter" placeholder="按标签筛选" clearable style="width: 140px" />
      <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 140px">
        <el-option label="已完成" value="completed" />
        <el-option label="处理中" value="processing" />
        <el-option label="失败" value="failed" />
      </el-select>
      <el-tag v-if="kbInfo?.workspace_id" size="small" type="primary">{{ kbInfo.workspace_name }} / {{ roleLabel(kbInfo.access_role) }}</el-tag>
      <el-tag v-else-if="kbInfo" size="small" type="info">个人知识库</el-tag>
    </div>

    <DatabaseSources :kb-id="kbId" :can-manage="canManage" />
    <WebSources ref="webSourcesRef" :kb-id="kbId" :can-manage="canManage" @changed="loadDocs" />
    <CompiledArticles :kb-id="kbId" :can-manage="canManage" />
    <KnowledgeHealth :kb-id="kbId" :can-manage="canManage" />

    <div v-if="Object.keys(uploadProgress).length" class="upload-progress-list">
      <div v-for="(pct, name) in uploadProgress" :key="name" class="upload-progress-item">
        <span class="upload-filename">{{ name }}</span>
        <el-progress :percentage="pct" :stroke-width="6" style="flex: 1" />
      </div>
    </div>

    <div>
      <!-- Skeleton loading -->
      <div v-if="loading" class="doc-skeleton">
        <div v-for="i in 5" :key="'sk'+i" class="doc-skeleton-row">
          <div class="skeleton" style="width:40%;height:14px"></div>
          <div class="skeleton" style="width:50px;height:14px"></div>
          <div class="skeleton" style="width:60px;height:14px"></div>
          <div class="skeleton" style="width:40px;height:14px"></div>
          <div class="skeleton" style="width:70px;height:24px;border-radius:4px"></div>
        </div>
      </div>
      <el-table v-else-if="filteredDocs.length" :data="filteredDocs" stripe @selection-change="onSelectionChange">
        <el-table-column v-if="canWrite" type="selection" width="45" />
        <el-table-column prop="filename" label="文件名" min-width="200" />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.file_type === 'database'" size="small" type="warning">数据库同步</el-tag>
            <span v-else>{{ row.file_type }}</span>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="片段数" width="80" />
        <el-table-column label="标签" width="180">
          <template #default="{ row }">
            <div v-if="(row.auto_tags && row.auto_tags.length) || (row.tags && row.tags.length)" style="display: flex; flex-wrap: wrap; gap: 4px;">
              <el-tag
                v-for="tag in (row.auto_tags || row.tags || [])"
                :key="tag"
                size="small"
                type="info"
                style="cursor: pointer;"
                @click="tagFilter = tag"
              >
                {{ tag }}
              </el-tag>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="过期时间" width="160">
          <template #default="{ row }">
            <span v-if="row.expires_at" :class="{ 'expiry-warning': isExpiringSoon(row.expires_at) }">
              {{ formatExpiry(row.expires_at) }}
            </span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="160">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
              <el-tag :type="row.is_stalled ? 'danger' : statusType(row.status)" size="small">
                {{ row.is_stalled ? '可能卡住' : statusText(row.status) }}
              </el-tag>
              <el-tooltip v-if="row.is_stalled" content="文档处理超过 30 分钟未完成，可能需要重试" placement="top">
                <el-button size="small" type="warning" link @click="handleRetry(row.id)">重试</el-button>
              </el-tooltip>
              <el-tooltip v-if="row.status === 'failed' && row.error_message" :content="row.error_message" placement="top" :show-after="300" max-width="400">
                <span class="doc-error-hint">
                  {{ row.error_message.length > 60 ? row.error_message.slice(0, 60) + '...' : row.error_message }}
                </span>
              </el-tooltip>
            </div>
            <div v-if="row.auto_tags?.length" style="margin-top: 4px;">
              <el-tag v-for="tag in row.auto_tags" :key="tag" size="small" type="info" style="margin-right: 4px;">{{ tag }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="180">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="320">
          <template #default="{ row }">
            <el-button v-if="row.status === 'completed'" link type="primary" size="small" @click="handlePreviewDoc(row)">
              <EyeIcon :size="13" :stroke-width="1.5" style="margin-right: 2px" />预览
            </el-button>
            <el-button v-if="row.status === 'completed'" link type="primary" size="small" @click="viewChunks(row)">查看切片</el-button>
            <el-button v-if="canWrite" link type="primary" size="small" @click="openTagDialog(row)">编辑标签</el-button>
            <el-button v-if="canWrite" link type="primary" size="small" @click="openExpiryDialog(row)">设置过期</el-button>
            <el-button v-if="canWrite && row.status === 'failed' && row.file_type !== 'database'" link type="warning" size="small" @click="handleRetry(row.id)">重试</el-button>
            <el-button v-if="canWrite && row.file_type !== 'database'" link type="danger" size="small" @click="removeDoc(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && docList.length === 0" description="暂无文档" />
      <el-empty v-else-if="!loading && filteredDocs.length === 0" description="没有匹配的文档，请调整搜索条件" :image-size="80" />
    </div>

    <el-pagination
      v-if="total > pageSize"
      class="pagination"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      v-model:current-page="currentPage"
      @current-change="loadDocs"
    />

    <!-- Trash / Recycle Bin -->
    <el-collapse v-if="trashDocs.length" style="margin-top: 16px;">
      <el-collapse-item name="trash">
        <template #title>
          <span style="font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 4px;">
            回收站（{{ trashDocs.length }}）
          </span>
        </template>
        <el-table :data="trashDocs" size="small" stripe>
          <el-table-column prop="filename" label="文件名" min-width="200" show-overflow-tooltip />
          <el-table-column label="删除时间" width="170">
            <template #default="{ row }">{{ row.deleted_at ? new Date(row.deleted_at).toLocaleString() : '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="handleRestoreDoc(row.id)">恢复</el-button>
              <el-button link type="danger" size="small" @click="handlePermanentDelete(row.id)">永久删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <el-dialog v-model="showChunkDialog" :title="`切片列表 - ${chunkDocName}`" width="700px" destroy-on-close>
      <div v-if="canWrite" style="display: flex; justify-content: flex-end; margin-bottom: 12px;">
        <el-button type="primary" size="small" @click="openAddChunk">新增切片</el-button>
      </div>
      <div v-loading="chunkLoading">
        <div v-if="chunkList.length === 0 && !chunkLoading" style="text-align: center; color: #909399; padding: 20px;">暂无切片数据</div>
        <div v-for="(chunk, idx) in chunkList" :key="chunk.id || idx" class="chunk-item">
          <div class="chunk-header">
            <el-tag size="small" type="info">#{{ (chunkPage - 1) * chunkPageSize + idx + 1 }}</el-tag>
            <span v-if="chunk.token_count" class="chunk-tokens">{{ chunk.token_count }} tokens</span>
            <span style="flex:1"></span>
            <el-button v-if="canWrite" text size="small" type="primary" @click="openEditChunk(chunk)">编辑</el-button>
            <el-button v-if="canWrite" text size="small" type="danger" @click="handleDeleteChunk(chunk.id)">删除</el-button>
          </div>
          <div class="chunk-content">{{ chunk.content }}</div>
        </div>
      </div>
      <el-pagination
        v-if="chunkTotal > chunkPageSize"
        class="pagination"
        layout="total, prev, pager, next"
        :total="chunkTotal"
        :page-size="chunkPageSize"
        v-model:current-page="chunkPage"
        @current-change="loadChunks"
        style="margin-top: 12px;"
      />
    </el-dialog>

    <el-dialog v-model="showEditChunkDialog" title="编辑切片" width="600px" :close-on-click-modal="false">
      <el-input v-model="editChunkContent" type="textarea" :rows="8" placeholder="切片内容" />
      <template #footer>
        <el-button @click="showEditChunkDialog = false">取消</el-button>
        <el-button type="primary" :loading="chunkSaving" @click="saveEditChunk">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showAddChunkDialog" title="新增切片" width="600px" :close-on-click-modal="false">
      <el-input v-model="addChunkContent" type="textarea" :rows="8" placeholder="输入切片内容" />
      <template #footer>
        <el-button @click="showAddChunkDialog = false">取消</el-button>
        <el-button type="primary" :loading="chunkSaving" @click="saveAddChunk">添加</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showWebDialog" title="添加网页数据源" width="480px">
      <el-form label-width="100px">
        <el-form-item label="数据类型">
          <el-select v-model="webSourceType" style="width: 100%">
            <el-option label="普通网页 HTML" value="html" />
            <el-option label="接口 JSON" value="json" />
            <el-option label="RSS / Atom" value="rss" />
            <el-option label="Sitemap XML" value="sitemap" />
          </el-select>
        </el-form-item>
        <el-form-item label="源 URL">
          <el-input v-model="webUrl" placeholder="请输入 URL，如 https://example.com" />
        </el-form-item>
        <el-form-item label="抓取间隔">
          <el-select v-model="webCrawlInterval" placeholder="选择抓取间隔" style="width: 100%">
            <el-option label="不定时（仅手动抓取）" :value="null" />
            <el-option label="每1小时" :value="1" />
            <el-option label="每6小时" :value="6" />
            <el-option label="每12小时" :value="12" />
            <el-option label="每天" :value="24" />
            <el-option label="每周" :value="168" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容变更自动重建索引">
          <el-switch v-model="webAutoReindex" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showWebDialog = false">取消</el-button>
        <el-button type="primary" @click="handleAddWeb" :loading="webLoading">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDocPreviewDialog" :title="`文档预览 - ${docPreviewName}`" width="750px" destroy-on-close>
      <div v-if="docPreviewContent !== null" style="margin-bottom: 8px; font-size: 12px; color: var(--text-muted);">
        共 {{ docPreviewTotalChars }} 字符<span v-if="docPreviewTotalChars > 10000">（仅显示前 10000 字符）</span>
      </div>
      <div v-loading="docPreviewLoading" class="doc-preview-content">
        <pre v-if="docPreviewContent !== null">{{ docPreviewContent }}</pre>
        <el-empty v-else-if="!docPreviewLoading" description="暂无内容" />
      </div>
    </el-dialog>

    <el-dialog v-model="showTagDialog" title="编辑标签" width="480px" destroy-on-close>
      <div v-if="tagEditDoc" style="margin-bottom: 12px; font-size: 13px; color: var(--text-secondary);">
        文档：{{ tagEditDoc.filename }}
      </div>
      <div style="margin-bottom: 12px;">
        <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;">
          <el-tag
            v-for="tag in tagEditList"
            :key="tag"
            closable
            size="small"
            @close="tagEditList = tagEditList.filter(t => t !== tag)"
          >
            {{ tag }}
          </el-tag>
        </div>
        <div style="display: flex; gap: 8px;">
          <el-input
            v-model="tagInput"
            placeholder="输入标签，逗号分隔或回车添加"
            size="small"
            clearable
            style="flex: 1"
            @keyup.enter="addTagFromInput"
          />
          <el-button size="small" type="primary" @click="addTagFromInput">添加</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="showTagDialog = false">取消</el-button>
        <el-button type="primary" :loading="tagSaving" @click="saveTags">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showExpiryDialog" title="设置过期时间" width="400px" destroy-on-close>
      <div v-if="expiryEditDoc" style="margin-bottom: 12px; font-size: 13px; color: var(--text-secondary);">
        文档：{{ expiryEditDoc.filename }}
      </div>
      <el-date-picker
        v-model="expiryDate"
        type="datetime"
        placeholder="选择过期日期时间"
        format="YYYY-MM-DD HH:mm"
        value-format="YYYY-MM-DDTHH:mm:ss"
        style="width: 100%"
        clearable
      />
      <template #footer>
        <el-button @click="showExpiryDialog = false">取消</el-button>
        <el-button @click="saveExpiry(null)">清除过期</el-button>
        <el-button type="primary" :loading="expirySaving" @click="saveExpiry()">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showPreviewDialog" title="分块预览" width="700px" :close-on-click-modal="false">
      <div v-if="previewResult" style="margin-bottom: 12px; display: flex; gap: 16px; font-size: 13px; color: var(--text-secondary);">
        <span>文件: <strong>{{ previewFileName }}</strong></span>
        <span>文本长度: <strong>{{ previewResult.text_length }}</strong> 字</span>
        <span>分块数: <strong>{{ previewResult.total }}</strong></span>
      </div>
      <div style="display: flex; gap: 8px; margin-bottom: 12px;">
        <el-select v-model="previewStrategy" size="small" style="width: 120px" @change="rePreview">
          <el-option label="固定长度" value="fixed" />
          <el-option label="段落" value="paragraph" />
          <el-option label="递归" value="recursive" />
          <el-option label="标题" value="heading" />
        </el-select>
        <el-input-number v-model="previewChunkSize" :min="100" :max="5000" :step="100" size="small" placeholder="块大小" @change="rePreview" />
        <el-input-number v-model="previewOverlap" :min="0" :max="500" :step="10" size="small" placeholder="重叠" @change="rePreview" />
      </div>
      <div v-loading="previewLoading" class="preview-chunks-list">
        <div v-for="chunk in (previewResult?.chunks || [])" :key="chunk.index" class="preview-chunk-item">
          <div class="preview-chunk-header">
            <span class="preview-chunk-idx">#{{ chunk.index }}</span>
            <span class="preview-chunk-len">{{ chunk.length }} 字</span>
          </div>
          <div class="preview-chunk-text">{{ chunk.content }}</div>
        </div>
      </div>
    </el-dialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, onDeactivated } from 'vue'
import { useRoute } from 'vue-router'
import {
  UploadCloud as UploadCloudIcon, ArrowLeft as ArrowLeftIcon,
  Eye as EyeIcon, Link as LinkIcon, Upload as UploadIcon,
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listDocuments, uploadDocument, deleteDocument, retryDocument, getDocumentChunks, updateChunk, createChunk, deleteChunk, previewChunks, previewDocument, getExpiringDocuments, updateDocumentTags, updateDocumentExpiry, listTrash, restoreDocument } from '../../api/documents'
import { addWebSource } from '../../api/webSources'
import { roleLabel } from '../../utils/format'
import { getKnowledgeBase } from '../../api/knowledgeBase'
import DatabaseSources from './DatabaseSources.vue'
import WebSources from './WebSources.vue'
import CompiledArticles from './CompiledArticles.vue'
import KnowledgeHealth from './KnowledgeHealth.vue'

const webSourcesRef = ref<InstanceType<typeof WebSources> | null>(null)

const route = useRoute()

const ACCEPTED_EXTS = ['.pdf', '.doc', '.docx', '.txt', '.md', '.csv', '.xlsx', '.xls', '.pptx', '.html', '.htm', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']
const dragOver = ref(false)
let dragCounter = 0

function onDragEnter(e: DragEvent) {
  dragCounter++
  if (e.dataTransfer?.types?.includes('Files')) dragOver.value = true
}
function onDragLeave() {
  dragCounter--
  if (dragCounter <= 0) { dragOver.value = false; dragCounter = 0 }
}
async function onDrop(e: DragEvent) {
  dragOver.value = false
  dragCounter = 0
  if (!canWrite.value) return
  const files = e.dataTransfer?.files
  if (!files?.length) return
  for (const file of Array.from(files)) {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!ACCEPTED_EXTS.includes(ext)) {
      ElMessage.warning(`不支持的文件格式: ${file.name}`)
      continue
    }
    await handleUpload(file)
  }
}

const kbId = Number(route.params.id)
const kbInfo = ref<any>(null)
const kbLoadError = ref('')
const docList = ref<any[]>([])
const docSearch = ref('')
const tagFilter = ref('')
const statusFilter = ref('')
const expiringDocs = ref<any[]>([])
const canWrite = computed(() => !!kbInfo.value?.can_write)
const canManage = computed(() => !!kbInfo.value?.can_manage)

const showPreviewDialog = ref(false)
const previewLoading = ref(false)
const previewResult = ref<any>(null)
const previewFileName = ref('')
const previewStrategy = ref('fixed')
const previewChunkSize = ref(500)
const previewOverlap = ref(50)
let previewFile: File | null = null

async function handlePreviewChunk(file: File) {
  previewFile = file
  previewFileName.value = file.name
  showPreviewDialog.value = true
  await runPreview(file)
  return false
}

async function runPreview(file: File) {
  previewLoading.value = true
  try {
    const res = await previewChunks(file, previewStrategy.value, previewChunkSize.value, previewOverlap.value)
    previewResult.value = res
  } catch (e: any) {
    ElMessage.error(e.message || '预览失败')
    previewResult.value = null
  } finally {
    previewLoading.value = false
  }
}

function rePreview() {
  if (previewFile) runPreview(previewFile)
}
const filteredDocs = computed(() => {
  let list = docList.value
  if (docSearch.value.trim()) {
    const q = docSearch.value.toLowerCase()
    list = list.filter((d: any) => d.filename.toLowerCase().includes(q))
  }
  if (tagFilter.value.trim()) {
    const tag = tagFilter.value.toLowerCase()
    list = list.filter((d: any) => {
      const tags = d.auto_tags || d.tags || []
      return tags.some((t: string) => t.toLowerCase().includes(tag))
    })
  }
  if (statusFilter.value) {
    if (statusFilter.value === 'processing') {
      list = list.filter((d: any) => ['uploading', 'parsing', 'embedding'].includes(d.status))
    } else {
      list = list.filter((d: any) => d.status === statusFilter.value)
    }
  }
  return list
})

const failedDocIds = computed(() =>
  filteredDocs.value
    .filter((d: any) => d.status === 'failed' && d.file_type !== 'database')
    .map((d: any) => d.id)
)
const batchRetryLoading = ref(false)
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
let pollTimer: ReturnType<typeof setInterval> | null = null

const showChunkDialog = ref(false)
const chunkLoading = ref(false)
const chunkList = ref<any[]>([])
const chunkTotal = ref(0)
const chunkPage = ref(1)
const chunkPageSize = 10
const chunkDocId = ref<number>(0)
const chunkDocName = ref('')

const showWebDialog = ref(false)
const webUrl = ref('')
const webLoading = ref(false)
const webSourceType = ref<'html' | 'json' | 'rss' | 'sitemap'>('html')
const webCrawlInterval = ref<number | null>(null)
const webAutoReindex = ref(false)

let isFirstLoad = true
let previouslyProcessing = new Set<number>()
let pollCount = 0


async function loadKbInfo() {
  try {
    kbInfo.value = await getKnowledgeBase(kbId)
    kbLoadError.value = ''
  } catch (err: any) {
    const status = err?.response?.status
    if (status === 404) {
      kbLoadError.value = '知识库不存在或已被删除'
    } else if (status === 403) {
      kbLoadError.value = '无权访问此知识库'
    } else {
      kbLoadError.value = '加载知识库信息失败，请稍后重试'
    }
  }
}

async function loadExpiringDocs() {
  try {
    const res = await getExpiringDocuments(kbId, 7)
    expiringDocs.value = Array.isArray(res) ? res : []
  } catch {
    expiringDocs.value = []
  }
}

const trashDocs = ref<any[]>([])

async function loadTrash() {
  try { const res: any = await listTrash(kbId); trashDocs.value = res?.items || [] }
  catch { trashDocs.value = [] }
}

async function handleRestoreDoc(docId: number) {
  try {
    await restoreDocument(docId)
    ElMessage.success('已恢复')
    await loadDocs()
    await loadTrash()
  } catch { /* interceptor handles */ }
}

async function handlePermanentDelete(docId: number) {
  try {
    await ElMessageBox.confirm('永久删除后无法恢复，确定继续？', '永久删除', { type: 'error' })
  } catch { return }
  try {
    await deleteDocument(docId, true)
    ElMessage.success('已永久删除')
    await loadTrash()
  } catch { /* interceptor handles */ }
}

async function loadDocs() {
  if (isFirstLoad) loading.value = true
  try {
    const res: any = await listDocuments(kbId, currentPage.value, pageSize)
    docList.value = res?.items ?? []
    total.value = res?.total ?? 0

    const processingStatuses = ['uploading', 'parsing', 'embedding']
    const currentlyProcessing = new Set<number>(res.items.filter((d: any) => processingStatuses.includes(d.status)).map((d: any) => d.id as number))
    const hasProcessing = currentlyProcessing.size > 0

    if (!isFirstLoad && previouslyProcessing.size > 0) {
      for (const docId of previouslyProcessing) {
        if (!currentlyProcessing.has(docId)) {
          const doc = res.items.find((d: any) => d.id === docId)
          if (doc) {
            if (doc.status === 'completed') {
              ElMessage.success(`文档「${doc.filename}」处理完成`)
            } else if (doc.status === 'failed') {
              ElMessage.error(`文档「${doc.filename}」处理失败`)
            }
          }
        }
      }
    }
    previouslyProcessing = currentlyProcessing

    if (hasProcessing) {
      pollCount++
      const interval = pollCount > 20 ? 10000 : pollCount > 10 ? 5000 : 2000
      if (pollTimer) clearInterval(pollTimer)
      pollTimer = setInterval(loadDocs, interval)
    } else if (!hasProcessing && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
      pollCount = 0
    }
  } finally {
    loading.value = false
    isFirstLoad = false
  }
}

const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50MB
const ALLOWED_EXTENSIONS = ['pdf', 'doc', 'docx', 'txt', 'md', 'csv', 'xlsx', 'xls', 'pptx', 'html', 'htm', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp']

const uploadProgress = ref<Record<string, number>>({})

async function handleUpload(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    ElMessage.error(`不支持的文件类型「.${ext}」，支持：${ALLOWED_EXTENSIONS.map(e => '.' + e).join('、')}`)
    return false
  }
  if (file.size > MAX_FILE_SIZE) {
    ElMessage.error(`文件「${file.name}」超过 50MB 大小限制`)
    return false
  }
  if (kbInfo.value && !kbInfo.value.embedding_model_id) {
    ElMessage.warning('该知识库未配置 Embedding 模型，文档上传后将无法向量化。请先在知识库设置中选择模型。')
    return false
  }
  const showProgress = file.size > 5 * 1024 * 1024
  const progressKey = file.name
  if (showProgress) uploadProgress.value[progressKey] = 0
  try {
    await uploadDocument(kbId, file, showProgress ? (pct) => {
      uploadProgress.value[progressKey] = pct
    } : undefined)
    ElMessage.success(`「${file.name}」上传成功，正在处理中...`)
    await loadDocs()
  } catch {
    // handled by interceptor
  } finally {
    delete uploadProgress.value[progressKey]
  }
  return false
}

async function handleRetry(docId: number) {
  try {
    await retryDocument(docId)
    ElMessage.success('已重新提交处理')
    await loadDocs()
  } catch { /* interceptor handles */ }
}

const selectedIds = ref<number[]>([])

function onSelectionChange(rows: any[]) {
  selectedIds.value = rows.map((r: any) => r.id)
}

async function batchDelete() {
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 个文档？`, '批量删除', { type: 'warning' })
  } catch { return }
  try {
    const results = await Promise.allSettled(selectedIds.value.map(id => deleteDocument(id)))
    const succeeded = results.filter(r => r.status === 'fulfilled').length
    const failed = results.filter(r => r.status === 'rejected').length
    if (failed > 0) {
      ElMessage.warning(`已删除 ${succeeded} 个文档，${failed} 个删除失败`)
    } else {
      ElMessage.success(`已删除 ${succeeded} 个文档`)
    }
    selectedIds.value = []
    await loadDocs()
  } catch {}
}

async function batchRetryFailed() {
  const ids = failedDocIds.value
  if (!ids.length) return
  batchRetryLoading.value = true
  try {
    const results = await Promise.allSettled(ids.map((id: number) => retryDocument(id)))
    const succeeded = results.filter((r) => r.status === 'fulfilled').length
    const failed = results.filter((r) => r.status === 'rejected').length
    if (failed > 0) {
      ElMessage.warning(`已重试 ${succeeded} 个，${failed} 个失败`)
    } else {
      ElMessage.success(`已对 ${succeeded} 个文档发起重试`)
    }
    await loadDocs()
  } catch (e: any) {
    ElMessage.error(e?.message || '批量重试失败')
  } finally {
    batchRetryLoading.value = false
  }
}

async function removeDoc(id: number) {
  const doc = docList.value.find((d: any) => d.id === id)
  const name = doc?.filename ? `「${doc.filename}」` : '该文档'
  try {
    await ElMessageBox.confirm(`${name}将移入回收站，可随时恢复。`, '确认删除', { type: 'warning' })
  } catch { return }
  try {
    await deleteDocument(id)
    ElMessage.success('已移入回收站')
    await loadDocs()
    await loadTrash()
  } catch { /* interceptor handles */ }
}

function viewChunks(doc: any) {
  chunkDocId.value = doc.id
  chunkDocName.value = doc.filename
  chunkPage.value = 1
  chunkList.value = []
  chunkTotal.value = 0
  showChunkDialog.value = true
  loadChunks()
}

const showEditChunkDialog = ref(false)
const showAddChunkDialog = ref(false)
const editChunkContent = ref('')
const addChunkContent = ref('')
const editChunkId = ref(0)
const chunkSaving = ref(false)

async function loadChunks() {
  chunkLoading.value = true
  try {
    const res: any = await getDocumentChunks(chunkDocId.value, chunkPage.value, chunkPageSize)
    chunkList.value = res.items || res
    chunkTotal.value = res.total || chunkList.value.length
  } finally {
    chunkLoading.value = false
  }
}

function openEditChunk(chunk: any) {
  editChunkId.value = chunk.id
  editChunkContent.value = chunk.content
  showEditChunkDialog.value = true
}

async function saveEditChunk() {
  if (!editChunkContent.value.trim()) { ElMessage.warning('内容不能为空'); return }
  chunkSaving.value = true
  try {
    await updateChunk(editChunkId.value, editChunkContent.value)
    ElMessage.success('切片已更新')
    showEditChunkDialog.value = false
    await loadChunks()
  } catch {} finally { chunkSaving.value = false }
}

function openAddChunk() {
  addChunkContent.value = ''
  showAddChunkDialog.value = true
}

async function saveAddChunk() {
  if (!addChunkContent.value.trim()) { ElMessage.warning('内容不能为空'); return }
  chunkSaving.value = true
  try {
    await createChunk({ doc_id: chunkDocId.value, kb_id: kbId, content: addChunkContent.value })
    ElMessage.success('切片已添加')
    showAddChunkDialog.value = false
    await loadChunks()
  } catch {} finally { chunkSaving.value = false }
}

async function handleDeleteChunk(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该切片？', '确认', { type: 'warning' })
    await deleteChunk(id)
    ElMessage.success('切片已删除')
    await loadChunks()
  } catch {}
}

const showDocPreviewDialog = ref(false)
const docPreviewLoading = ref(false)
const docPreviewContent = ref<string | null>(null)
const docPreviewTotalChars = ref(0)
const docPreviewName = ref('')

async function handlePreviewDoc(doc: any) {
  docPreviewName.value = doc.filename
  docPreviewContent.value = null
  docPreviewTotalChars.value = 0
  showDocPreviewDialog.value = true
  docPreviewLoading.value = true
  try {
    const res: any = await previewDocument(doc.id)
    docPreviewContent.value = res.content
    docPreviewTotalChars.value = res.total_chars
  } catch (e: any) {
    ElMessage.error(e.message || '预览失败')
  } finally {
    docPreviewLoading.value = false
  }
}

async function handleAddWeb() {
  const url = webUrl.value.trim()
  if (!url) {
    ElMessage.warning('请输入网页 URL')
    return
  }
  if (!/^https?:\/\/.+/i.test(url)) {
    ElMessage.warning('请输入有效的网页地址（以 http:// 或 https:// 开头）')
    return
  }
  webLoading.value = true
  try {
    await addWebSource({
      kb_id: kbId,
      url: webUrl.value.trim(),
      source_type: webSourceType.value,
      crawl_interval_hours: webCrawlInterval.value ?? undefined,
      auto_reindex: webAutoReindex.value,
    })
    ElMessage.success('网页源已提交，正在抓取中...')
    showWebDialog.value = false
    webUrl.value = ''
    webSourceType.value = 'html'
    webCrawlInterval.value = null
    webAutoReindex.value = false
    await loadDocs()
    webSourcesRef.value?.loadSources()
  } catch {
    // handled by interceptor
  } finally {
    webLoading.value = false
  }
}

function formatSize(bytes: number) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function statusType(status: string) {
  const map: Record<string, string> = {
    completed: 'success',
    failed: 'danger',
    uploading: 'info',
    parsing: 'warning',
    embedding: 'warning',
  }
  return map[status] || 'info'
}

function statusText(status: string) {
  const map: Record<string, string> = {
    uploading: '上传中',
    parsing: '解析中',
    embedding: '向量化中',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
}

const showTagDialog = ref(false)
const tagEditDoc = ref<any>(null)
const tagEditList = ref<string[]>([])
const tagInput = ref('')
const tagSaving = ref(false)

function openTagDialog(doc: any) {
  tagEditDoc.value = doc
  tagEditList.value = [...(doc.auto_tags || doc.tags || [])]
  tagInput.value = ''
  showTagDialog.value = true
}

function addTagFromInput() {
  const val = tagInput.value.trim()
  if (!val) return
  const parts = val.split(/[,，\s]+/).map((s: string) => s.trim()).filter(Boolean)
  for (const p of parts) {
    if (p && !tagEditList.value.includes(p)) tagEditList.value.push(p)
  }
  tagInput.value = ''
}

async function saveTags() {
  if (!tagEditDoc.value) return
  tagSaving.value = true
  try {
    await updateDocumentTags(tagEditDoc.value.id, tagEditList.value)
    ElMessage.success('标签已更新')
    showTagDialog.value = false
    const idx = docList.value.findIndex((d: any) => d.id === tagEditDoc.value?.id)
    if (idx >= 0) {
      docList.value[idx] = { ...docList.value[idx], auto_tags: [...tagEditList.value], tags: [...tagEditList.value] }
    }
  } catch {} finally {
    tagSaving.value = false
  }
}

const showExpiryDialog = ref(false)
const expiryEditDoc = ref<any>(null)
const expiryDate = ref<string | null>(null)
const expirySaving = ref(false)

function openExpiryDialog(doc: any) {
  expiryEditDoc.value = doc
  expiryDate.value = doc.expires_at ? doc.expires_at.slice(0, 19) : null
  showExpiryDialog.value = true
}

async function saveExpiry(overrideValue?: string | null) {
  if (!expiryEditDoc.value) return
  const value = overrideValue !== undefined ? overrideValue : expiryDate.value
  expirySaving.value = true
  try {
    await updateDocumentExpiry(expiryEditDoc.value.id, value)
    ElMessage.success('过期时间已更新')
    showExpiryDialog.value = false
    const idx = docList.value.findIndex((d: any) => d.id === expiryEditDoc.value?.id)
    if (idx >= 0) docList.value[idx] = { ...docList.value[idx], expires_at: value }
    await loadExpiringDocs()
  } catch {} finally {
    expirySaving.value = false
  }
}

function formatExpiry(expiresAt: string) {
  if (!expiresAt) return '-'
  return new Date(expiresAt).toLocaleString()
}

function isExpiringSoon(expiresAt: string) {
  if (!expiresAt) return false
  const d = new Date(expiresAt).getTime()
  const now = Date.now()
  return d - now < 7 * 24 * 60 * 60 * 1000
}

onActivated(async () => {
  await Promise.allSettled([loadKbInfo(), loadDocs(), loadExpiringDocs(), loadTrash()])
})

onDeactivated(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  pollCount = 0
})
</script>

<style scoped>
/* ══════════════════════════════════════════
   Documents — Google Cloud Style
   ══════════════════════════════════════════ */
.documents-page {
  position: relative;
  max-width: 1200px;
}

.doc-error-hint {
  font-size: 12px;
  color: var(--el-color-danger);
  line-height: 1.4;
}

.drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  background: rgba(26, 115, 232, 0.06);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px dashed var(--primary);
  border-radius: var(--radius-lg);
}

.drop-overlay-inner {
  text-align: center;
  color: var(--primary);
}

.drop-overlay-inner h3 {
  font-size: 16px;
  font-weight: 500;
  margin: 12px 0 4px;
}

.drop-overlay-inner p {
  font-size: 13px;
  color: var(--text-secondary);
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 200ms;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
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

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.chunk-item {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  padding: 14px;
  margin-bottom: 8px;
  transition: box-shadow var(--duration-fast) var(--ease-out), border-color var(--duration-fast);
}

.chunk-item:hover {
  border-color: var(--border-color);
  box-shadow: var(--shadow-sm);
}

.chunk-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.chunk-tokens {
  font-size: 12px;
  color: var(--text-muted);
}

.chunk-content {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

.preview-chunks-list {
  max-height: 450px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.preview-chunk-item {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
}

.preview-chunk-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.preview-chunk-idx {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
}

.preview-chunk-len {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.preview-chunk-text {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
}

.upload-tip {
  font-size: 12px;
  color: var(--text-muted, #909399);
  margin-top: 4px;
}

.upload-progress-list {
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.upload-progress-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--gray-25);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.upload-filename {
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
}

.doc-preview-content {
  max-height: 500px;
  overflow-y: auto;
  background: var(--gray-50, #fafafa);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  padding: 16px;
  min-height: 100px;
}

.doc-preview-content pre {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  color: var(--text-secondary);
}

.doc-skeleton {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  overflow: hidden;
}
.doc-skeleton-row {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-subtle);
}
.doc-skeleton-row:last-child { border-bottom: none; }

.text-muted {
  font-size: 12px;
  color: var(--text-muted, #909399);
}

.expiry-warning {
  color: var(--el-color-warning);
  font-weight: 500;
}
</style>
