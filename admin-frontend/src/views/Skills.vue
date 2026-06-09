<template>
  <div>
    <div class="page-header">
      <div>
        <h2>技能市场管理</h2>
        <p class="page-subtitle">审核与管理技能上架</p>
      </div>
    </div>

    <el-card class="table-card">
      <div class="table-toolbar">
        <div class="toolbar-left">
          <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 120px" @change="() => { page = 1; loadSkills() }">
            <el-option label="待审核" value="pending" />
            <el-option label="已上架" value="approved" />
            <el-option label="已拒绝" value="rejected" />
            <el-option label="已下架" value="unlisted" />
          </el-select>
          <el-select v-model="categoryFilter" placeholder="分类筛选" clearable style="width: 120px" @change="() => { page = 1; loadSkills() }">
            <el-option label="通用" value="general" />
            <el-option label="开发" value="development" />
            <el-option label="数据" value="data" />
            <el-option label="效率" value="productivity" />
            <el-option label="检索" value="retrieval" />
            <el-option label="创意" value="creative" />
            <el-option label="通信" value="communication" />
            <el-option label="安全" value="security" />
            <el-option label="金融" value="finance" />
            <el-option label="销售" value="sales" />
          </el-select>
          <el-input v-model="searchText" placeholder="搜索名称、标识、描述..." clearable style="width: 220px" @keydown.enter="() => { page = 1; loadSkills() }" @clear="() => { page = 1; loadSkills() }">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-tag v-if="total > 0" type="info" effect="plain" round>共 {{ total }} 个技能</el-tag>
        </div>
        <div class="toolbar-right">
          <el-button type="danger" plain round @click="deleteAllOpenClaw">
            <el-icon><Delete /></el-icon>清空 OpenClaw
          </el-button>
          <el-upload
            :show-file-list="false"
            accept=".tar.gz,.tgz"
            :before-upload="uploadOpenClawTarball"
            :disabled="importRunning"
          >
            <el-button type="primary" :loading="importRunning" round>
              <el-icon><Upload /></el-icon>上传 OpenClaw 压缩包导入
            </el-button>
          </el-upload>
          <el-button type="success" :loading="importRunning" round @click="importLocalSkills">
            <el-icon><FolderOpened /></el-icon>导入本地技能目录
          </el-button>
          <el-button @click="loadSkills" :loading="loading" round>
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </div>
      </div>

      <div v-if="importRunning" class="import-progress">
        <div class="import-progress-header">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在导入 OpenClaw 技能...</span>
          <span class="import-stats">已导入 {{ importProgress.inserted }} / {{ importProgress.total || '...' }}，跳过 {{ importProgress.skipped }}</span>
        </div>
        <el-progress :percentage="importPercent" :stroke-width="6" :show-text="false" />
      </div>


      <el-table :data="skills" v-loading="loading" style="width: 100%" :empty-text="statusFilter ? '该状态下暂无技能' : '暂无技能数据'">
        <el-table-column prop="id" label="ID" width="60" align="center" />
        <el-table-column label="技能" min-width="200">
          <template #default="{ row }">
            <div class="skill-cell">
              <div class="skill-icon-wrap">
                <el-icon :size="18"><MagicStick /></el-icon>
              </div>
              <div>
                <div class="skill-name">{{ row.name }}</div>
                <code class="skill-slug">{{ row.slug }}</code>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" round>{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="author_name" label="作者" width="100" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small" effect="light" round>{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="下载量" width="90" align="center">
          <template #default="{ row }">
            <span class="download-count">{{ row.download_count || 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="80" align="center">
          <template #default="{ row }">
            <span class="version-tag">v{{ row.version }}</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }"><span class="text-secondary">{{ new Date(row.created_at).toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="viewSkillDetail(row)">查看</el-button>
            <el-divider direction="vertical" />
            <el-button link size="small" type="warning" @click="editSkillDirect(row)">编辑</el-button>
            <el-divider direction="vertical" />
            <template v-if="row.status === 'pending'">
              <el-button link size="small" type="success" @click="reviewSkill(row, 'approved')">通过</el-button>
              <el-divider direction="vertical" />
              <el-button link size="small" type="danger" @click="reviewSkill(row, 'rejected')">拒绝</el-button>
            </template>
            <el-button v-if="row.status === 'approved'" link size="small" type="warning" @click="reviewSkill(row, 'unlisted')">下架</el-button>
            <el-button v-if="row.status === 'rejected' || row.status === 'unlisted'" link size="small" type="success" @click="reviewSkill(row, 'approved')">重新上架</el-button>
            <el-divider direction="vertical" />
            <el-button link size="small" type="danger" @click="deleteSkill(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > pageSize" class="table-pagination">
        <el-pagination
          layout="total, prev, pager, next"
          :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="loadSkills"
        />
      </div>
    </el-card>

    <!-- 技能详情/编辑对话框 -->
    <el-dialog v-model="detailVisible" :title="detailEditing ? '编辑技能' : '技能详情'" width="640px">
      <div v-if="detailLoading" v-loading="true" style="min-height: 120px;"></div>
      <template v-else-if="detailData">
        <el-form v-if="detailEditing" :model="editForm" label-width="80px">
          <el-form-item label="名称">
            <el-input v-model="editForm.name" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="editForm.description" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="分类">
            <el-input v-model="editForm.category" />
          </el-form-item>
          <el-form-item label="版本">
            <el-input v-model="editForm.version" />
          </el-form-item>
          <el-form-item label="Prompt">
            <el-input v-model="editForm.promptContent" type="textarea" :rows="10" class="prompt-edit-textarea" placeholder="输入 Prompt 模板内容..." />
            <div style="font-size: 11px; color: var(--text-tertiary); margin-top: 4px;">编辑技能的 Prompt 模板。使用 <code v-text="'{{变量}}'"></code> 语法定义输入变量。</div>
          </el-form-item>
        </el-form>
        <div v-else class="detail-view">
          <div class="detail-row">
            <span class="detail-label">ID</span>
            <span>{{ detailData.id }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">名称</span>
            <span class="detail-value-primary">{{ detailData.name }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">标识</span>
            <code class="skill-slug">{{ detailData.slug }}</code>
          </div>
          <div class="detail-row">
            <span class="detail-label">描述</span>
            <span>{{ detailData.description || '—' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">分类</span>
            <el-tag size="small" effect="plain" round>{{ detailData.category }}</el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">类型</span>
            <span>{{ detailData.skill_type }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">版本</span>
            <span class="version-tag">v{{ detailData.version }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">状态</span>
            <el-tag :type="statusTag(detailData.status)" size="small" effect="light" round>{{ statusLabel(detailData.status) }}</el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">下载量</span>
            <span>{{ detailData.download_count || 0 }}</span>
          </div>
          <div v-if="detailData.config" class="detail-config">
            <span class="detail-label" style="margin-bottom: 8px; display: block;">配置 / Prompt</span>
            <pre class="config-pre">{{ formatConfig(detailData.config) }}</pre>
          </div>
        </div>
      </template>
      <template #footer>
        <template v-if="detailEditing">
          <el-button @click="detailEditing = false">取消编辑</el-button>
          <el-button type="primary" :loading="editSaving" @click="saveSkillEdit">保存</el-button>
        </template>
        <template v-else>
          <el-button @click="detailVisible = false">关闭</el-button>
          <el-button type="primary" @click="startEditing">编辑</el-button>
        </template>
      </template>
    </el-dialog>

    <!-- 拒绝技能对话框 -->
    <el-dialog v-model="reviewDialogVisible" title="拒绝技能" width="480px" destroy-on-close>
      <div v-if="reviewTarget" style="margin-bottom: 16px;">
        <span style="color: var(--text-secondary);">技能：</span>
        <strong>{{ reviewTarget.name }}</strong>
        <code style="margin-left: 8px; font-size: 12px; color: var(--text-tertiary);">{{ reviewTarget.slug }}</code>
      </div>
      <el-form label-position="top">
        <el-form-item label="拒绝原因">
          <el-input
            v-model="reviewComment"
            type="textarea"
            :rows="4"
            placeholder="请说明拒绝原因，帮助提交者改进（可选）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="reviewSubmitting" @click="submitReject">确认拒绝</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../utils/request'

const skills = ref<any[]>([])
const loading = ref(false)
const statusFilter = ref('')
const categoryFilter = ref('')
const searchText = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)

const importRunning = ref(false)
const importProgress = ref<any>({ inserted: 0, skipped: 0, total: 0 })
let importPollTimer: ReturnType<typeof setInterval> | null = null

const importPercent = computed(() => {
  const t = importProgress.value.total
  if (!t) return 0
  return Math.min(Math.round(((importProgress.value.inserted + importProgress.value.skipped) / t) * 100), 100)
})

function uploadOpenClawTarball(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  importRunning.value = true
  importProgress.value = { inserted: 0, skipped: 0, total: 0 }

  request.post('/skills/admin/openclaw/import-upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  }).then(() => {
    startPolling()
    ElMessage.success('文件上传成功，后台导入已启动')
  }).catch(() => {
    importRunning.value = false
  })
  return false
}

function startPolling() {
  stopPolling()
  importPollTimer = setInterval(async () => {
    try {
      const res: any = await request.get('/skills/admin/openclaw/import-progress')
      importProgress.value = res
      if (!res.running) {
        stopPolling()
        importRunning.value = false
        if (res.error) {
          ElMessage.error(`导入出错: ${res.error}`)
        } else {
          ElMessage.success(`导入完成！新增 ${res.inserted} 个技能，跳过 ${res.skipped} 个重复`)
          loadSkills()
        }
      }
    } catch { /* ignore polling errors */ }
  }, 2000)
}

function stopPolling() {
  if (importPollTimer) {
    clearInterval(importPollTimer)
    importPollTimer = null
  }
}

async function deleteAllOpenClaw() {
  try {
    await ElMessageBox.confirm(
      '将删除所有 OpenClaw 分类的技能，此操作不可撤销。\n\n确定清空？',
      '清空 OpenClaw 技能',
      { type: 'warning', confirmButtonText: '确定清空', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
    )
  } catch { return }
  try {
    const res: any = await request.delete('/skills/admin/openclaw/all')
    ElMessage.success(`已删除 ${res.deleted} 个 OpenClaw 技能`)
    loadSkills()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function importLocalSkills() {
  try {
    await ElMessageBox.confirm(
      '将从服务器本地 skills/ 目录批量导入所有技能到数据库。\n已存在的技能将自动跳过。',
      '导入本地技能',
      { type: 'info', confirmButtonText: '开始导入' },
    )
  } catch { return }
  try {
    importRunning.value = true
    await request.post('/skills/admin/openclaw/import-local')
    ElMessage.success('本地导入已启动，正在后台处理...')
    startPolling()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '启动失败')
    importRunning.value = false
  }
}


function statusLabel(s: string) {
  return { pending: '待审核', approved: '已上架', rejected: '已拒绝', unlisted: '已下架' }[s] || s
}
function statusTag(s: string) {
  return { pending: 'warning', approved: 'success', rejected: 'danger', unlisted: 'info' }[s] as any || 'info'
}

async function loadSkills() {
  loading.value = true
  try {
    const res: any = await request.get('/skills/admin/all', {
      params: {
        page: page.value,
        page_size: pageSize,
        status: statusFilter.value || undefined,
        category: categoryFilter.value || undefined,
        search: searchText.value.trim() || undefined,
      },
    })
    skills.value = res.items || []
    total.value = res.total || 0
  } finally { loading.value = false }
}

// ─── 查看 / 编辑 / 删除 ───
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailData = ref<any>(null)
const detailEditing = ref(false)
const editSaving = ref(false)
const editForm = ref({ name: '', description: '', category: '', version: '', promptContent: '' })

async function editSkillDirect(row: any) {
  detailVisible.value = true
  detailLoading.value = true
  detailEditing.value = false
  detailData.value = null
  try {
    const res: any = await request.get(`/skills/admin/${row.id}/detail`)
    detailData.value = res
    editForm.value = {
      name: res.name || '',
      description: res.description || '',
      category: res.category || '',
      version: res.version || '',
      promptContent: extractPrompt(res.config),
    }
    detailEditing.value = true
  } catch {
    ElMessage.error('获取技能详情失败')
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

function extractPrompt(config: string): string {
  try {
    const obj = typeof config === 'string' ? JSON.parse(config) : config
    return obj?.prompt_template || ''
  } catch {
    return ''
  }
}

async function viewSkillDetail(row: any) {
  detailVisible.value = true
  detailLoading.value = true
  detailEditing.value = false
  detailData.value = null
  try {
    const res: any = await request.get(`/skills/admin/${row.id}/detail`)
    detailData.value = res
  } catch {
    ElMessage.error('获取技能详情失败')
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

function startEditing() {
  if (!detailData.value) return
  editForm.value = {
    name: detailData.value.name || '',
    description: detailData.value.description || '',
    category: detailData.value.category || '',
    version: detailData.value.version || '',
    promptContent: extractPrompt(detailData.value.config),
  }
  detailEditing.value = true
}

async function saveSkillEdit() {
  if (!detailData.value) return
  editSaving.value = true
  try {
    const payload: any = {
      name: editForm.value.name,
      description: editForm.value.description,
      category: editForm.value.category,
      version: editForm.value.version,
    }
    if (editForm.value.promptContent !== undefined) {
      let configObj: any = {}
      try {
        configObj = typeof detailData.value.config === 'string'
          ? JSON.parse(detailData.value.config) : (detailData.value.config || {})
      } catch { configObj = {} }
      configObj.prompt_template = editForm.value.promptContent
      payload.config = JSON.stringify(configObj, null, 2)
    }
    await request.put(`/skills/admin/${detailData.value.id}`, payload)
    ElMessage.success('更新成功')
    detailEditing.value = false
    detailData.value = { ...detailData.value, ...payload }
    loadSkills()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  } finally {
    editSaving.value = false
  }
}

function formatConfig(config: string) {
  try {
    const obj = typeof config === 'string' ? JSON.parse(config) : config
    if (obj.prompt_template) return obj.prompt_template
    return JSON.stringify(obj, null, 2)
  } catch {
    return config
  }
}

async function deleteSkill(row: any) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.name}」？此操作不可撤销。`,
      '删除技能',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
    )
  } catch { return }
  try {
    const res: any = await request.delete(`/skills/admin/${row.id}`)
    ElMessage.success(res.message || '删除成功')
    loadSkills()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const reviewDialogVisible = ref(false)
const reviewTarget = ref<any>(null)
const reviewStatus = ref('')
const reviewComment = ref('')
const reviewSubmitting = ref(false)

async function reviewSkill(row: any, status: string) {
  const action = { approved: '通过', rejected: '拒绝', unlisted: '下架' }[status] || status
  if (status === 'rejected') {
    reviewTarget.value = row
    reviewStatus.value = status
    reviewComment.value = ''
    reviewDialogVisible.value = true
    return
  }
  try { await ElMessageBox.confirm(`确定${action}「${row.name}」？`, '确认') } catch { return }
  try {
    await request.post(`/skills/admin/${row.id}/review`, { status, comment: '' })
    ElMessage.success(`已${action}`)
    loadSkills()
  } catch { /* interceptor handles */ }
}

async function submitReject() {
  if (!reviewTarget.value) return
  reviewSubmitting.value = true
  try {
    await request.post(`/skills/admin/${reviewTarget.value.id}/review`, {
      status: reviewStatus.value,
      comment: reviewComment.value,
    })
    ElMessage.success('已拒绝')
    reviewDialogVisible.value = false
    loadSkills()
  } catch { /* interceptor handles */ }
  finally { reviewSubmitting.value = false }
}

onMounted(async () => {
  loadSkills()
  try {
    const res: any = await request.get('/skills/admin/openclaw/import-progress')
    if (res.running) {
      importRunning.value = true
      importProgress.value = res
      startPolling()
    }
  } catch { /* ignore */ }
})

onUnmounted(() => {
  stopPolling()
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
}

.toolbar-left { display: flex; gap: 12px; align-items: center; }

.skill-cell { display: flex; align-items: center; gap: 12px; }

.skill-icon-wrap {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--brand-primary-light);
  color: var(--brand-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.skill-name { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }

.skill-slug {
  font-size: 11px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--text-tertiary);
  background: #F8FAFC;
  padding: 1px 6px;
  border-radius: 3px;
}

.download-count {
  font-weight: 600;
  color: var(--text-secondary);
}

.version-tag {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.text-secondary { color: var(--text-secondary); font-size: 13px; }

.toolbar-right { display: flex; gap: 8px; align-items: center; }

.import-progress {
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-light);
  background: #F0F9FF;
}

.import-progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.import-stats {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.table-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid var(--border-light);
}

.detail-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.detail-label {
  flex-shrink: 0;
  width: 64px;
  font-weight: 600;
  color: var(--text-tertiary);
  font-size: 13px;
}

.detail-value-primary {
  font-weight: 600;
  color: var(--text-primary);
}

.detail-config {
  margin-top: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
}

.config-pre {
  margin: 0;
  padding: 14px;
  background: #F8FAFC;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.prompt-edit-textarea :deep(textarea) {
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
  font-size: 12px;
  line-height: 1.7;
}
</style>
