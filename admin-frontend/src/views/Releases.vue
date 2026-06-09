<template>
  <div>
    <div class="page-header">
      <div>
        <h2>版本管理</h2>
        <p class="page-subtitle">管理桌面版安装包，上传新版本，设置自动更新</p>
      </div>
      <el-button type="primary" @click="uploadVisible = true" round>
        <el-icon><Upload /></el-icon>上传新版本
      </el-button>
    </div>

    <el-card class="table-card">
      <el-table :data="releases" v-loading="loading" empty-text="暂无安装包" style="width: 100%">
        <el-table-column prop="filename" label="文件名" min-width="250">
          <template #default="{ row }">
            <div>
              <span class="text-primary-bold">{{ row.filename }}</span>
              <el-tag v-if="row.is_latest" type="success" size="small" effect="light" round style="margin-left: 8px">当前版本</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="版本号" width="120">
          <template #default="{ row }">
            <span>v{{ row.version }}</span>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">
            <span>{{ row.size_mb }} MB</span>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="180">
          <template #default="{ row }">
            <span class="text-secondary">{{ formatTime(row.uploaded_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center">
          <template #default="{ row }">
            <el-button v-if="!row.is_latest" link type="primary" size="small" @click="setLatest(row.filename)">设为当前</el-button>
            <el-button link size="small" @click="downloadFile(row.filename)">下载</el-button>
            <el-button link type="danger" size="small" @click="deleteRelease(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="uploadVisible" title="上传新版本" width="460px" destroy-on-close>
      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        accept=".exe,.dmg,.AppImage,.deb"
        :on-change="(f: any) => { selectedFile = f.raw }"
        :on-exceed="() => ElMessage.warning('只能上传一个文件')"
      >
        <el-icon :size="48" style="color: var(--el-color-primary)"><Upload /></el-icon>
        <div style="margin-top: 8px">拖拽安装包到此处，或<em>点击选择</em></div>
        <template #tip>
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 8px;">
            支持 .exe / .dmg / .AppImage / .deb 格式
          </div>
        </template>
      </el-upload>
      <el-checkbox v-model="setAsLatest" style="margin-top: 12px">上传后设为最新版本（用于自动更新）</el-checkbox>
      <el-progress v-if="uploading && uploadProgress > 0" :percentage="uploadProgress" :stroke-width="8" style="margin-top: 12px" />
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import api from '../utils/request'
import { ADMIN_API_BASE } from '../config/adminApi'

const loading = ref(false)
const releases = ref<any[]>([])
const uploadVisible = ref(false)
const uploading = ref(false)
const setAsLatest = ref(true)
const selectedFile = ref<File | null>(null)
const uploadProgress = ref(0)

function formatTime(iso: string) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString()
}

async function loadReleases() {
  loading.value = true
  try {
    const res: any = await api.get('/releases')
    releases.value = res.releases || []
  } catch {
    ElMessage.error('加载版本列表失败')
  } finally {
    loading.value = false
  }
}

async function handleUpload() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', selectedFile.value)
    const res: any = await api.post(`/releases/upload?set_as_latest=${setAsLatest.value}`, fd, {
      timeout: 600000,
      onUploadProgress: (e: any) => {
        if (e.total) uploadProgress.value = Math.round((e.loaded / e.total) * 100)
      },
    })
    uploadProgress.value = 0
    ElMessage.success(res.message || '上传成功')
    uploadVisible.value = false
    selectedFile.value = null
    await loadReleases()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function setLatest(filename: string) {
  try {
    await api.post(`/releases/${encodeURIComponent(filename)}/set-latest`)
    ElMessage.success('已设为最新版本')
    await loadReleases()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '设置失败')
  }
}

async function deleteRelease(row: any) {
  const msg = row.is_latest
    ? `「${row.filename}」是当前正在使用的版本，删除后用户将无法下载。确定删除？`
    : `确定删除 ${row.filename}？`
  try {
    await ElMessageBox.confirm(msg, '确认删除', { type: 'warning' })
  } catch { return }
  try {
    await api.delete(`/releases/${encodeURIComponent(row.filename)}`)
    ElMessage.success('已删除')
    await loadReleases()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

function downloadFile(filename: string) {
  const base = import.meta.env.DEV ? `${ADMIN_API_BASE}/releases/download` : '/downloads'
  window.open(`${base}/${filename}`, '_blank')
}

onMounted(loadReleases)
</script>
