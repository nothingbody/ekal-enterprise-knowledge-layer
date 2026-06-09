<template>
  <div class="platform-models-page">
    <div class="page-header">
      <div>
        <h2>平台模型管理</h2>
        <p class="page-subtitle">管理全局共享模型，标记为"共享"的模型将自动同步到所有客户端</p>
      </div>
      <el-button type="primary" round @click="openDialog()">
        <el-icon><Plus /></el-icon>添加模型
      </el-button>
    </div>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ allModelsStats.total }}</div>
        <div class="stat-label">模型总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ allModelsStats.shared }}</div>
        <div class="stat-label">共享模型</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ allModelsStats.llm }}</div>
        <div class="stat-label">LLM</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ allModelsStats.embedding }}</div>
        <div class="stat-label">Embedding</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ allModelsStats.todayTokens.toLocaleString() }}</div>
        <div class="stat-label">今日 Token</div>
      </div>
    </div>

    <el-card class="table-card" shadow="never">
      <div class="table-toolbar">
        <div class="toolbar-left">
          <el-radio-group v-model="typeFilter" size="small" @change="loadModels">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="llm">LLM</el-radio-button>
            <el-radio-button value="embedding">Embedding</el-radio-button>
            <el-radio-button value="reranker">Reranker</el-radio-button>
          </el-radio-group>
          <el-checkbox v-model="sharedOnly" @change="loadModels" label="仅共享" />
        </div>
        <el-button size="small" @click="loadModels" :loading="loading">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>

      <el-table :data="filteredModels" v-loading="loading" stripe size="default" empty-text="暂无模型配置">
        <el-table-column label="模型" min-width="220">
          <template #default="{ row }">
            <div class="model-cell">
              <div class="model-cell-name">{{ row.display_name }}</div>
              <div class="model-cell-id">{{ row.model_name }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag
              size="small"
              effect="plain"
              round
              :type="row.model_type === 'llm' ? 'primary' : row.model_type === 'embedding' ? '' : 'success'"
            >{{ row.model_type.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提供商" prop="provider" width="120">
          <template #default="{ row }">{{ providerLabel(row.provider) }}</template>
        </el-table-column>
        <el-table-column label="API 地址" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="api-base-cell">{{ row.api_base }}</code>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="180">
          <template #default="{ row }">
            <div class="status-tags">
              <el-tag v-if="row.is_shared" size="small" type="warning" effect="dark" round>共享</el-tag>
              <el-tag v-if="row.is_default" size="small" type="success" effect="plain" round>默认</el-tag>
              <el-tag v-if="row.api_key_set" size="small" type="success" effect="plain" round>Key 已配</el-tag>
              <el-tag v-else size="small" type="info" effect="plain" round>无 Key</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="今日用量" width="140">
          <template #default="{ row }">
            <div v-if="row.tokens_used_today || row.max_tokens_per_day" style="font-size: 12px;">
              <span style="font-family: monospace; font-weight: 600;">{{ (row.tokens_used_today || 0).toLocaleString() }}</span>
              <span v-if="row.max_tokens_per_day" style="color: var(--el-text-color-secondary);"> / {{ row.max_tokens_per_day.toLocaleString() }}</span>
              <el-progress
                v-if="row.max_tokens_per_day"
                :percentage="Math.min(100, Math.round((row.tokens_used_today || 0) / row.max_tokens_per_day * 100))"
                :stroke-width="4"
                :show-text="false"
                :color="(row.tokens_used_today || 0) / row.max_tokens_per_day > 0.8 ? '#f56c6c' : '#409eff'"
                style="margin-top: 4px;"
              />
            </div>
            <span v-else style="color: var(--el-text-color-secondary); font-size: 12px;">无限制</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="testModel(row)">测试</el-button>
            <el-button link size="small" @click="toggleShared(row)">
              {{ row.is_shared ? '取消共享' : '设为共享' }}
            </el-button>
            <el-button link size="small" @click="openDialog(row)">编辑</el-button>
            <el-button link size="small" type="danger" @click="deleteModel(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="models.length > 1" class="table-card" shadow="never" style="margin-top: 20px;">
      <template #header><span style="font-weight: 600; font-size: 15px;">Token 消耗排行</span></template>
      <el-table :data="modelsByUsage" stripe size="small">
        <el-table-column label="#" width="50"><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
        <el-table-column label="模型" min-width="180">
          <template #default="{ row }">
            <div style="font-weight: 600;">{{ row.display_name }}</div>
            <div style="font-size: 11px; color: var(--el-text-color-secondary);">{{ row.model_name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="90">
          <template #default="{ row }"><el-tag size="small" effect="plain" round>{{ row.model_type?.toUpperCase() }}</el-tag></template>
        </el-table-column>
        <el-table-column label="今日消耗" width="130">
          <template #default="{ row }">
            <span style="font-family: monospace; font-weight: 600;">{{ (row.tokens_used_today || 0).toLocaleString() }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日限额" width="130">
          <template #default="{ row }">
            <span v-if="row.max_tokens_per_day">{{ row.max_tokens_per_day.toLocaleString() }}</span>
            <span v-else style="color: var(--el-text-color-secondary);">无限制</span>
          </template>
        </el-table-column>
        <el-table-column label="使用率" width="140">
          <template #default="{ row }">
            <el-progress
              v-if="row.max_tokens_per_day"
              :percentage="Math.min(100, Math.round((row.tokens_used_today || 0) / row.max_tokens_per_day * 100))"
              :stroke-width="6"
              :color="(row.tokens_used_today || 0) / row.max_tokens_per_day > 0.8 ? '#f56c6c' : '#409eff'"
            />
            <span v-else style="color: var(--el-text-color-secondary); font-size: 12px;">—</span>
          </template>
        </el-table-column>
        <el-table-column label="共享" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_shared" size="small" type="warning" effect="dark" round>是</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="table-card" shadow="never" style="margin-top: 20px;" v-loading="userRankLoading">
      <template #header><span style="font-weight: 600; font-size: 15px;">用户 Token 消耗排行</span></template>
      <el-table v-if="userRank.length" :data="userRank" stripe size="small">
        <el-table-column label="#" width="50"><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
        <el-table-column label="用户名" min-width="140">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/users/${row.id}/detail`)">{{ row.username }}</el-button>
          </template>
        </el-table-column>
        <el-table-column label="方案" width="90">
          <template #default="{ row }">
            <el-tag :type="({ trial: 'info', basic: '', pro: 'warning', enterprise: 'success' } as Record<string, string>)[row.plan] || 'info'" size="small" effect="light" round>
              {{ ({ trial: '试用', basic: '基础', pro: '专业', enterprise: '企业' } as Record<string, string>)[row.plan] || row.plan || '试用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="总消耗" width="130"><template #default="{ row }"><span style="font-family:monospace;font-weight:600">{{ (row.token_used || 0).toLocaleString() }}</span></template></el-table-column>
        <el-table-column label="额度" width="130"><template #default="{ row }">{{ (row.token_credit || 0).toLocaleString() }}</template></el-table-column>
        <el-table-column label="对话数" width="80"><template #default="{ row }">{{ row.conversation_count || row.total_conversations || 0 }}</template></el-table-column>
        <el-table-column label="使用率" width="130">
          <template #default="{ row }">
            <el-progress v-if="row.token_credit" :percentage="Math.min(100, Math.round((row.token_used || 0) / row.token_credit * 100))" :stroke-width="6" />
            <span v-else style="color:var(--el-text-color-secondary);font-size:12px">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无用户用量数据" :image-size="40" />
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingModel ? '编辑模型' : '添加模型'"
      width="580px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="100px" @submit.prevent>
        <el-form-item label="模型类型" v-if="!editingModel">
          <el-radio-group v-model="form.model_type">
            <el-radio-button value="llm">LLM</el-radio-button>
            <el-radio-button value="embedding">Embedding</el-radio-button>
            <el-radio-button value="reranker">Reranker</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="提供商">
          <el-select v-model="form.provider" style="width: 100%">
            <el-option label="OpenAI / 兼容接口" value="openai" />
            <el-option label="Anthropic (Claude)" value="anthropic" />
            <el-option label="Ollama 本地模型" value="ollama" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="form.display_name" placeholder="例如：GPT-4o" />
        </el-form-item>
        <el-form-item label="模型标识">
          <el-input v-model="form.model_name" placeholder="例如：gpt-4o" />
        </el-form-item>
        <el-form-item label="API 地址">
          <el-input v-model="form.api_base" placeholder="例如：https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password
            :placeholder="editingModel ? '留空保持不变；输入 CLEAR 清除' : 'API Key'" />
          <div v-if="editingModel" class="form-hint">
            留空 = 保持原有 Key 不变 · 输入 <code>CLEAR</code> = 清除已有 Key
          </div>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
        </el-form-item>
        <el-form-item label="共享到客户端">
          <el-switch v-model="form.is_shared" />
          <div class="form-hint">开启后，此模型将自动同步到所有桌面客户端，用户无需手动配置</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="testBeforeSave" :loading="testing" round>
            <el-icon><Connection /></el-icon>测试连接
          </el-button>
          <div>
            <el-button @click="dialogVisible = false" round>取消</el-button>
            <el-button type="primary" @click="saveModel" :loading="saving" round>保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../utils/request'

const models = ref<any[]>([])
const allModelsStats = ref({ total: 0, shared: 0, llm: 0, embedding: 0, todayTokens: 0 })
const loading = ref(false)
const typeFilter = ref('')
const sharedOnly = ref(false)

const userRank = ref<any[]>([])
const userRankLoading = ref(false)

const dialogVisible = ref(false)
const editingModel = ref<any>(null)
const saving = ref(false)
const testing = ref(false)

const form = ref({
  model_type: 'llm',
  provider: 'openai',
  display_name: '',
  model_name: '',
  api_base: '',
  api_key: '',
  is_default: false,
  is_shared: true,
})

const filteredModels = computed(() => {
  let list = models.value
  if (sharedOnly.value) list = list.filter(m => m.is_shared)
  return list
})
const modelsByUsage = computed(() => [...models.value].sort((a, b) => (b.tokens_used_today || 0) - (a.tokens_used_today || 0)))

const providerLabels: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google',
  ollama: 'Ollama',
  custom: '自定义',
}
function providerLabel(p: string) { return providerLabels[p] || p }

async function loadModels() {
  loading.value = true
  try {
    const params: Record<string, string> = {}
    if (typeFilter.value) params.model_type = typeFilter.value
    const res: any = await request.get('/models', { params })
    models.value = res?.items || res || []

    // Load all models for stats if we have a type filter active
    if (typeFilter.value) {
      try {
        const allRes: any = await request.get('/models')
        const all = allRes?.items || allRes || []
        allModelsStats.value = {
          total: all.length,
          shared: all.filter((m: any) => m.is_shared).length,
          llm: all.filter((m: any) => m.model_type === 'llm').length,
          embedding: all.filter((m: any) => m.model_type === 'embedding').length,
          todayTokens: all.reduce((s: number, m: any) => s + (m.tokens_used_today || 0), 0),
        }
      } catch { /* use filtered data as fallback */ }
    } else {
      allModelsStats.value = {
        total: models.value.length,
        shared: models.value.filter((m: any) => m.is_shared).length,
        llm: models.value.filter((m: any) => m.model_type === 'llm').length,
        embedding: models.value.filter((m: any) => m.model_type === 'embedding').length,
        todayTokens: models.value.reduce((s: number, m: any) => s + (m.tokens_used_today || 0), 0),
      }
    }
  } catch { /* interceptor handles */ }
  finally { loading.value = false }
}

function openDialog(model?: any) {
  if (model) {
    editingModel.value = model
    form.value = {
      model_type: model.model_type,
      provider: model.provider,
      display_name: model.display_name,
      model_name: model.model_name,
      api_base: model.api_base,
      api_key: '',
      is_default: model.is_default,
      is_shared: model.is_shared || false,
    }
  } else {
    editingModel.value = null
    form.value = {
      model_type: typeFilter.value || 'llm',
      provider: 'openai',
      display_name: '',
      model_name: '',
      api_base: '',
      api_key: '',
      is_default: false,
      is_shared: true,
    }
  }
  dialogVisible.value = true
}

async function saveModel() {
  if (!form.value.display_name || !form.value.model_name || !form.value.api_base) {
    ElMessage.warning('请填写显示名称、模型标识和 API 地址')
    return
  }
  saving.value = true
  try {
    if (editingModel.value) {
      const payload: Record<string, any> = {
        provider: form.value.provider,
        display_name: form.value.display_name,
        model_name: form.value.model_name,
        api_base: form.value.api_base,
        is_default: form.value.is_default,
        is_shared: form.value.is_shared,
      }
      const ki = form.value.api_key
      if (ki === 'CLEAR') payload.api_key = ''
      else if (ki) payload.api_key = ki
      await request.put(`/models/${editingModel.value.id}`, payload)
      ElMessage.success('模型已更新')
    } else {
      const payload: Record<string, any> = {
        model_type: form.value.model_type,
        provider: form.value.provider,
        display_name: form.value.display_name,
        model_name: form.value.model_name,
        api_base: form.value.api_base,
        is_default: form.value.is_default,
        is_shared: form.value.is_shared,
      }
      if (form.value.api_key) payload.api_key = form.value.api_key
      await request.post('/models', payload)
      ElMessage.success('模型已添加')
    }
    dialogVisible.value = false
    await loadModels()
  } catch { /* interceptor handles */ }
  finally { saving.value = false }
}

async function deleteModel(model: any) {
  try {
    await ElMessageBox.confirm(
      `确定删除模型「${model.display_name}」？${model.is_shared ? '此模型为共享模型，删除后客户端也将失去访问权限。' : ''}`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await request.delete(`/models/${model.id}`)
    ElMessage.success('已删除')
    await loadModels()
  } catch { /* interceptor handles */ }
}

async function toggleShared(model: any) {
  const newShared = !model.is_shared
  const action = newShared ? '共享' : '取消共享'
  try {
    await ElMessageBox.confirm(
      newShared
        ? `将「${model.display_name}」设为共享模型，所有客户端将自动同步此模型。`
        : `取消「${model.display_name}」的共享状态，客户端将不再自动获取此模型。`,
      `确认${action}`,
      { type: 'warning' },
    )
  } catch { return }
  try {
    await request.put(`/models/${model.id}`, { is_shared: newShared })
    ElMessage.success(`已${action}`)
    await loadModels()
  } catch { /* interceptor handles */ }
}

async function testModel(model: any) {
  testing.value = true
  try {
    const res: any = await request.post(`/models/${model.id}/test`)
    ElMessage.success(res?.message || res?.display_name ? `连接成功 (${res.display_name})` : '连接成功')
  } catch (e: any) {
    ElMessage.error('测试失败: ' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally { testing.value = false }
}

async function testBeforeSave() {
  if (!form.value.api_base || !form.value.model_name) {
    ElMessage.warning('请先填写 API 地址和模型标识')
    return
  }
  testing.value = true
  try {
    const payload: Record<string, any> = {
      api_base: form.value.api_base,
      model_name: form.value.model_name,
      provider: form.value.provider,
    }
    if (form.value.api_key && form.value.api_key !== 'CLEAR') {
      payload.api_key = form.value.api_key
    }
    await request.post('/models/test', payload)
    ElMessage.success('连接测试通过')
  } catch (e: any) {
    ElMessage.error('测试失败: ' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally { testing.value = false }
}

async function loadUserRank() {
  userRankLoading.value = true
  try {
    const res: any = await request.get('/users', { params: { page: 1, page_size: 100 } })
    const items = res?.items || []
    userRank.value = items
      .filter((u: any) => u.token_used > 0)
      .sort((a: any, b: any) => (b.token_used || 0) - (a.token_used || 0))
      .slice(0, 20)
  } catch { /* ignore */ }
  finally { userRankLoading.value = false }
}

onMounted(() => {
  loadModels()
  loadUserRank()
})
</script>

<style scoped>
.platform-models-page { max-width: 1400px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.page-header h2 { margin: 0 0 4px; }
.page-subtitle { font-size: 13px; color: var(--el-text-color-secondary); margin: 0; }

.stats-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 20px;
}
.stat-card {
  background: #FFF;
  border: 1px solid var(--border-color, #E5E7EB);
  border-radius: 10px;
  padding: 18px 20px;
  text-align: center;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
  letter-spacing: -0.02em;
}
.stat-label {
  font-size: 12px;
  color: var(--text-tertiary, #94a3b8);
  margin-top: 4px;
}

.table-card { margin-bottom: 20px; }

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.model-cell { display: flex; flex-direction: column; gap: 2px; }
.model-cell-name { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.model-cell-id { font-size: 12px; color: var(--el-text-color-secondary); font-family: var(--el-font-family-mono, monospace); }

.api-base-cell {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: var(--el-font-family-mono, monospace);
  background: var(--el-fill-color-lighter);
  padding: 2px 6px;
  border-radius: 4px;
}

.status-tags { display: flex; gap: 4px; flex-wrap: wrap; }

.form-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.5;
}
.form-hint code {
  background: rgba(43, 90, 237, 0.08);
  color: var(--el-color-primary);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.dialog-footer > div { display: flex; gap: 8px; }
</style>
