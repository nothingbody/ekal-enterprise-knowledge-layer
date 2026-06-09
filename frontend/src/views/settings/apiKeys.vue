<template>
  <div class="apikeys-page">
    <div class="page-header">
      <h2>API Key 管理</h2>
      <el-button type="primary" @click="showCreateDialog = true">
        <PlusIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />创建 API Key
      </el-button>
    </div>

    <el-table :data="keys" stripe v-loading="loading">
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column label="Key" min-width="200">
        <template #default="{ row }">
          <code class="key-preview">{{ row.key_preview }}</code>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最后使用" width="180">
        <template #default="{ row }">
          {{ row.last_used_at ? new Date(row.last_used_at).toLocaleString() : '从未使用' }}
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button link :type="row.is_active ? 'warning' : 'success'" size="small" @click="toggleActive(row)">
            {{ row.is_active ? '禁用' : '启用' }}
          </el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && keys.length === 0">
      <template #description>
        <p>暂无 API Key，点击上方按钮创建</p>
        <p style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">API Key 用于通过 HTTP 接口调用知识库和对话功能，适用于集成到你自己的应用中</p>
      </template>
      <el-button type="primary" @click="showCreateDialog = true">创建第一个 API Key</el-button>
    </el-empty>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreateDialog" title="创建 API Key" width="420px" @closed="newKeyResult = null">
      <template v-if="!newKeyResult">
        <el-form @submit.prevent="handleCreate">
          <el-form-item label="名称">
            <el-input v-model="newKeyName" placeholder="例如：生产环境" />
          </el-form-item>
        </el-form>
      </template>
      <template v-else>
        <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 16px;">
          请立即复制此 Key，关闭后将无法再次查看完整 Key。
        </el-alert>
        <div class="key-display">
          <code>{{ newKeyResult.key }}</code>
          <el-button size="small" @click="copyKey(newKeyResult.key)">复制</el-button>
        </div>
      </template>
      <template #footer>
        <template v-if="!newKeyResult">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" @click="handleCreate" :loading="creating">创建</el-button>
        </template>
        <template v-else>
          <el-button type="primary" @click="showCreateDialog = false">完成</el-button>
        </template>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onActivated } from 'vue'
import { Plus as PlusIcon } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listApiKeys, createApiKey, updateApiKey, deleteApiKey } from '../../api/apiKeys'

const keys = ref<any[]>([])
const loading = ref(false)
const showCreateDialog = ref(false)
const newKeyName = ref('')
const creating = ref(false)
const newKeyResult = ref<any>(null)

async function loadKeys() {
  loading.value = true
  try {
    keys.value = (await listApiKeys()) as any
  } catch {}
  finally { loading.value = false }
}

async function handleCreate() {
  if (!newKeyName.value.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  creating.value = true
  try {
    const res: any = await createApiKey(newKeyName.value.trim())
    newKeyResult.value = res
    newKeyName.value = ''
    await loadKeys()
  } catch {}
  finally { creating.value = false }
}

async function toggleActive(row: any) {
  try {
    await updateApiKey(row.id, { is_active: !row.is_active })
    ElMessage.success(row.is_active ? '已禁用' : '已启用')
    await loadKeys()
  } catch {}
}

async function handleDelete(id: number) {
  const key = keys.value.find((k: any) => k.id === id)
  const label = key?.name ? `「${key.name}」` : '此 API Key'
  try {
    await ElMessageBox.confirm(`确定删除${label}？删除后使用该 Key 的应用将无法访问。`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteApiKey(id)
    ElMessage.success('已删除')
    await loadKeys()
  } catch {}
}

async function copyKey(key: string) {
  try {
    await navigator.clipboard.writeText(key)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败')
  }
}

onActivated(loadKeys)
</script>

<style scoped>
.apikeys-page {
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

.key-preview {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  background: var(--hover-bg);
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--text-secondary);
}

.key-display {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--hover-bg);
  padding: 12px 16px;
  border-radius: var(--radius);
}

.key-display code {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 13px;
  word-break: break-all;
  flex: 1;
  color: var(--text-primary);
}
</style>
