<template>
  <div class="site-content-page">
    <div class="page-header">
      <div>
        <h2>官网内容管理</h2>
        <p class="page-subtitle">管理官网公告、更新日志、FAQ 和页面内容</p>
      </div>
    </div>

    <el-card class="table-card">
      <div class="table-toolbar">
        <div class="toolbar-left">
          <el-select v-model="typeFilter" placeholder="全部类型" clearable style="width: 140px" @change="onFilterChange">
            <el-option label="公告" value="announcement" />
            <el-option label="更新日志" value="changelog" />
            <el-option label="FAQ" value="faq" />
            <el-option label="页面" value="page" />
          </el-select>
          <el-select v-model="sortBy" style="width: 140px" @change="onFilterChange">
            <el-option label="按排序权重" value="sort_order" />
            <el-option label="按创建时间" value="created_at" />
            <el-option label="按更新时间" value="updated_at" />
            <el-option label="按标题排序" value="title" />
          </el-select>
          <el-input v-model="searchText" placeholder="搜索标题..." clearable style="width: 220px" @keydown.enter="onFilterChange" @clear="onFilterChange">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-tag v-if="total > 0" type="info" effect="plain" round>共 {{ total }} 条</el-tag>
        </div>
        <div class="toolbar-right">
          <el-button type="primary" round @click="openEditor()">
            <el-icon><Plus /></el-icon>新增内容
          </el-button>
          <el-button @click="loadContents" :loading="loading" round>
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </div>
      </div>

      <!-- Batch actions bar -->
      <transition name="batch-bar">
        <div v-if="selectedRows.length > 0" class="batch-bar">
          <span class="batch-count">已选择 <strong>{{ selectedRows.length }}</strong> 项</span>
          <el-button size="small" type="success" plain round @click="batchPublish(true)">
            <el-icon><CircleCheck /></el-icon>批量发布
          </el-button>
          <el-button size="small" type="warning" plain round @click="batchPublish(false)">
            <el-icon><Remove /></el-icon>取消发布
          </el-button>
          <el-button size="small" type="danger" plain round @click="batchDelete">
            <el-icon><Delete /></el-icon>批量删除
          </el-button>
          <el-button link size="small" @click="clearSelection">取消选择</el-button>
        </div>
      </transition>

      <el-table
        ref="tableRef"
        :data="contents"
        v-loading="loading"
        style="width: 100%"
        :row-class-name="tableRowClass"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.content_type)" size="small" effect="light" round>
              {{ typeLabel(row.content_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="240">
          <template #default="{ row }">
            <div class="title-cell" @click="openEditor(row)">
              <span class="content-title">{{ row.title }}</span>
              <span v-if="row.version" class="content-version">{{ row.version }}</span>
            </div>
            <div v-if="row.slug" class="content-slug">/{{ row.slug }}</div>
            <div v-if="row.summary" class="content-summary">{{ row.summary }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_published"
              size="small"
              inline-prompt
              active-text="发布"
              inactive-text="草稿"
              :loading="row._toggling"
              :before-change="() => confirmToggle(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="排序" width="90" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.sort_order"
              :min="0" :max="9999"
              size="small"
              controls-position="right"
              style="width: 70px"
              @change="(val: number) => updateSortOrder(row, val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">
            <el-tooltip :content="formatFullTime(row.updated_at || row.created_at)" placement="top">
              <span class="text-secondary">{{ formatRelativeTime(row.updated_at || row.created_at) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="openEditor(row)">编辑</el-button>
            <el-dropdown trigger="click" @command="(cmd: string) => handleRowCommand(cmd, row)">
              <el-button link size="small" class="more-btn">
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="preview" v-if="row.is_published && row.slug">
                    <el-icon><View /></el-icon>预览
                  </el-dropdown-item>
                  <el-dropdown-item command="duplicate">
                    <el-icon><CopyDocument /></el-icon>复制为新内容
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <span class="danger-action"><el-icon><Delete /></el-icon>删除</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>

        <template #empty>
          <div v-if="!loading" class="empty-state">
            <el-empty description="暂无内容" :image-size="120">
              <el-button type="primary" round @click="openEditor()">
                <el-icon><Plus /></el-icon>创建第一条内容
              </el-button>
            </el-empty>
          </div>
        </template>
      </el-table>

      <div v-if="total > pageSize" class="table-pagination">
        <el-pagination layout="total, prev, pager, next" :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="loadContents" />
      </div>
    </el-card>

    <!-- Editor Drawer -->
    <SiteContentEditor
      v-model:visible="editorVisible"
      :editingRow="editingRow"
      @saved="loadContents"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import request from '../utils/request'
import SiteContentEditor from '../components/site/SiteContentEditor.vue'

const contents = ref<any[]>([])
const loading = ref(false)
const typeFilter = ref('')
const sortBy = ref('sort_order')
const searchText = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)

const editorVisible = ref(false)
const editingRow = ref<any>(null)
const tableRef = ref<any>()
const selectedRows = ref<any[]>([])
const recentlyToggled = ref<Set<number>>(new Set())

function typeLabel(t: string) {
  return { announcement: '公告', changelog: '更新日志', faq: 'FAQ', page: '页面' }[t] || t
}

function typeTag(t: string) {
  return { announcement: 'danger', changelog: 'warning', faq: '', page: 'info' }[t] as any || 'info'
}

function tableRowClass({ row }: { row: any }) {
  const cls: string[] = []
  if (!row.is_published) cls.push('draft-row')
  if (recentlyToggled.value.has(row.id)) cls.push('row-toggled')
  return cls.join(' ')
}

function flashRow(id: number) {
  recentlyToggled.value.add(id)
  setTimeout(() => recentlyToggled.value.delete(id), 1500)
}

function formatRelativeTime(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} 天前`
  return d.toLocaleDateString()
}

function formatFullTime(dateStr: string) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString()
}

function onFilterChange() {
  page.value = 1
  loadContents()
}

function onSelectionChange(rows: any[]) {
  selectedRows.value = rows
}

function clearSelection() {
  tableRef.value?.clearSelection()
}

async function loadContents() {
  loading.value = true
  try {
    const res: any = await request.get('/site/admin/list', {
      params: {
        page: page.value,
        page_size: pageSize,
        content_type: typeFilter.value || undefined,
        sort_by: sortBy.value || undefined,
        search: searchText.value.trim() || undefined,
      },
    })
    contents.value = (res.items || []).map((item: any) => ({ ...item, _toggling: false }))
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

function openEditor(row?: any) {
  editingRow.value = row || null
  editorVisible.value = true
}

function confirmToggle(row: any): Promise<boolean> {
  const willPublish = !row.is_published
  const msg = willPublish
    ? '确认发布此内容？发布后将在官网上展示。'
    : '确认取消发布？取消后该内容将从官网隐藏。'
  const title = willPublish ? '发布确认' : '取消发布确认'

  return ElMessageBox.confirm(msg, title, {
    confirmButtonText: willPublish ? '确认发布' : '确认取消',
    cancelButtonText: '取消',
    type: willPublish ? 'info' : 'warning',
  }).then(() => {
    doTogglePublish(row, willPublish)
    return true
  }).catch(() => false)
}

async function doTogglePublish(row: any, publish: boolean) {
  row._toggling = true
  try {
    await request.put(`/site/admin/${row.id}`, { is_published: publish })
    flashRow(row.id)
    ElNotification({
      title: publish ? '已发布' : '已取消发布',
      message: `「${row.title}」${publish ? '已发布到官网' : '已从官网隐藏'}`,
      type: 'success',
      duration: 3000,
    })
  } catch {
    row.is_published = !publish
    ElMessage.error('操作失败')
  } finally {
    row._toggling = false
  }
}

async function batchPublish(publish: boolean) {
  const ids = selectedRows.value.map((r: any) => r.id)
  const action = publish ? '发布' : '取消发布'
  try {
    await ElMessageBox.confirm(
      `确定将选中的 ${ids.length} 项内容${action}？`,
      `批量${action}`,
      { type: 'warning', confirmButtonText: `确认${action}`, cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await request.post('/site/admin/batch-update', { ids, updates: { is_published: publish } })
    ElNotification({ title: `批量${action}成功`, message: `已${action} ${ids.length} 项内容`, type: 'success', duration: 3000 })
    clearSelection()
    loadContents()
  } catch {
    ElMessage.error(`批量${action}失败`)
  }
}

async function batchDelete() {
  const ids = selectedRows.value.map((r: any) => r.id)
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${ids.length} 项内容？此操作不可恢复。`,
      '批量删除',
      { type: 'error', confirmButtonText: '确认删除', confirmButtonClass: 'el-button--danger', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await request.post('/site/admin/batch-delete', { ids })
    ElNotification({ title: '批量删除成功', message: `已删除 ${ids.length} 项内容`, type: 'success', duration: 3000 })
    clearSelection()
    loadContents()
  } catch {
    ElMessage.error('批量删除失败')
  }
}

async function deleteContent(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.title}」？此操作不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      confirmButtonClass: 'el-button--danger',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await request.delete(`/site/admin/${row.id}`)
    ElMessage.success('删除成功')
    loadContents()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

function duplicateContent(row: any) {
  const extra = typeof row.extra === 'object' ? row.extra : {}
  editingRow.value = {
    ...row,
    id: undefined,
    title: `${row.title}（副本）`,
    slug: '',
    is_published: false,
    extra,
  }
  editorVisible.value = true
}

async function updateSortOrder(row: any, val: number) {
  try {
    await request.put(`/site/admin/${row.id}`, { sort_order: val })
  } catch {
    ElMessage.error('更新排序失败')
    loadContents()
  }
}

function previewContent(row: any) {
  const baseUrl = window.location.origin
  const slug = row.slug || row.id
  const typeMap: Record<string, string> = { changelog: 'changelog', faq: 'faq', announcement: 'blog', page: '' }
  const prefix = typeMap[row.content_type] || ''
  const url = prefix ? `${baseUrl}/${prefix}/${slug}` : `${baseUrl}/${slug}`
  window.open(url, '_blank')
}

function handleRowCommand(cmd: string, row: any) {
  if (cmd === 'duplicate') duplicateContent(row)
  else if (cmd === 'delete') deleteContent(row)
  else if (cmd === 'preview') previewContent(row)
}

onMounted(() => {
  loadContents()
})
</script>

<style scoped>
.page-subtitle { font-size: 14px; color: var(--text-tertiary); margin-top: 4px; }
.table-card :deep(.el-card__body) { padding: 0 !important; }

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-light);
  flex-wrap: wrap;
  gap: 12px;
}
.toolbar-left { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }

/* ── Batch Actions Bar ── */

.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  background: var(--el-color-primary-light-9);
  border-bottom: 1px solid var(--el-color-primary-light-7);
}

.batch-count { font-size: 13px; color: var(--text-secondary); margin-right: 4px; }
.batch-count strong { color: var(--el-color-primary); }

.batch-bar-enter-active,
.batch-bar-leave-active { transition: all 0.25s ease; }
.batch-bar-enter-from,
.batch-bar-leave-to { opacity: 0; height: 0; padding-top: 0; padding-bottom: 0; overflow: hidden; }

/* ── Table Cells ── */

.title-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.title-cell:hover .content-title { color: var(--el-color-primary); }

.content-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  transition: color 0.2s;
}

.content-version {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
  font-weight: 500;
  flex-shrink: 0;
}

.content-slug {
  font-size: 11px;
  font-family: 'SF Mono', 'Cascadia Code', Consolas, monospace;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.content-summary {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 360px;
}

.sort-num { font-variant-numeric: tabular-nums; color: var(--text-secondary); }
.text-secondary { color: var(--text-secondary); font-size: 13px; }

:deep(.draft-row) { opacity: 0.6; }

:deep(.row-toggled) { animation: row-flash 1.5s ease-out; }

@keyframes row-flash {
  0%, 20% { background-color: var(--el-color-success-light-9); }
  100% { background-color: transparent; }
}

.more-btn { margin-left: 4px; }

.danger-action { color: var(--el-color-danger); display: flex; align-items: center; gap: 4px; }

.empty-state { padding: 40px 20px; }

.table-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid var(--border-light);
}

</style>
