<template>
  <div class="kb-page">
    <div class="page-header">
      <div>
        <h2>知识库总览</h2>
        <p class="page-subtitle">查看平台所有用户的知识库和文档</p>
      </div>
    </div>

    <el-card class="table-card" shadow="never" v-loading="loading">
      <div class="table-toolbar">
        <el-input v-model="search" placeholder="搜索知识库..." clearable size="small" style="width: 240px" @clear="() => { page = 1; loadData() }" @keyup.enter="() => { page = 1; loadData() }" />
        <el-button size="small" @click="loadData"><el-icon><Refresh /></el-icon>刷新</el-button>
      </div>

      <el-table :data="items" stripe size="default" empty-text="暂无知识库">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="font-weight: 600; cursor: pointer; color: var(--el-color-primary);" @click="viewDocs(row)">{{ row.name }}</div>
            <div v-if="row.description" style="font-size: 12px; color: var(--el-text-color-secondary); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="所有者" width="120">
          <template #default="{ row }">{{ row.owner_username || row.user_id || '—' }}</template>
        </el-table-column>
        <el-table-column label="文档数" width="80" align="center">
          <template #default="{ row }">{{ row.document_count ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="工作空间" width="120">
          <template #default="{ row }">{{ row.workspace_name || row.workspace_id || '—' }}</template>
        </el-table-column>
        <el-table-column label="Embedding" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.embedding_model_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="viewDocs(row)">文档</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > 20" style="margin-top: 12px; display: flex; justify-content: flex-end;">
        <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" size="small" @current-change="loadData" />
      </div>
    </el-card>

    <el-dialog v-model="docDialogVisible" :title="`${selectedKb?.name} — 文档列表`" width="700px">
      <el-table :data="docs" size="small" v-loading="docsLoading" empty-text="暂无文档">
        <el-table-column prop="filename" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column label="大小" width="80">
          <template #default="{ row }">{{ row.file_size ? (row.file_size / 1024).toFixed(0) + 'KB' : '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : 'info'" size="small" effect="plain" round>
              {{ ({ completed: '已完成', processing: '处理中', failed: '失败', pending: '待处理' } as Record<string, string>)[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分块数" width="70" align="center">
          <template #default="{ row }">{{ row.chunk_count ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="上传时间" width="170">
          <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import request from '../utils/request'

const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const search = ref('')

const docDialogVisible = ref(false)
const selectedKb = ref<any>(null)
const docs = ref<any[]>([])
const docsLoading = ref(false)

async function loadData() {
  loading.value = true
  try {
    const params: Record<string, any> = { page: page.value, page_size: 20 }
    if (search.value) params.search = search.value
    const res: any = await request.get('/knowledge-bases', { params })
    items.value = res?.items || []
    total.value = res?.total || 0
  } catch { /* */ }
  finally { loading.value = false }
}

async function viewDocs(kb: any) {
  selectedKb.value = kb
  docDialogVisible.value = true
  docsLoading.value = true
  try {
    const res: any = await request.get(`/knowledge-bases/${kb.id}/documents`, { params: { page_size: 100 } })
    docs.value = res?.items || []
  } catch { docs.value = [] }
  finally { docsLoading.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.kb-page { max-width: 1200px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-header h2 { margin: 0 0 4px; }
.page-subtitle { font-size: 13px; color: var(--el-text-color-secondary); margin: 0; }
.table-card { margin-bottom: 20px; }
.table-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
