<template>
  <div class="agents-page">
    <div class="page-header">
      <div>
        <h2>多 Agent 协作</h2>
        <p class="page-desc">配置多个专业 Agent，让它们协同处理跨知识库的复杂问题。</p>
      </div>
      <el-button type="primary" @click="openDialog()">
        <Plus :size="16" :stroke-width="1.5" style="margin-right: 4px" />新建 Agent
      </el-button>
    </div>

    <div v-if="loading" v-loading="true" style="min-height: 200px;"></div>
    <div v-else-if="!agents.length" class="empty-state">
      <Bot :size="48" :stroke-width="1" style="color: var(--el-text-color-secondary); margin-bottom: 16px;" />
      <p>还没有创建任何 Agent</p>
      <p class="sub-text">创建多个专业 Agent 后，可在对话中使用"多 Agent"模式进行跨知识库问答</p>
      <el-button type="primary" @click="openDialog()">创建第一个 Agent</el-button>
    </div>

    <div v-else class="agent-grid">
      <div v-for="agent in agents" :key="agent.id" class="agent-card" :class="{ inactive: !agent.is_active }">
        <div class="card-header">
          <div class="agent-avatar">
            <Bot :size="20" :stroke-width="1.5" />
          </div>
          <div class="card-title-area">
            <div class="card-title">{{ agent.name }}</div>
            <el-tag size="small" :type="agent.is_active ? 'success' : 'info'">
              {{ agent.is_active ? '已启用' : '已停用' }}
            </el-tag>
          </div>
          <el-dropdown trigger="click" @command="(cmd: string) => handleCommand(cmd, agent)">
            <el-button link><MoreHorizontal :size="16" :stroke-width="1.5" /></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">编辑</el-dropdown-item>
                <el-dropdown-item command="toggle">{{ agent.is_active ? '停用' : '启用' }}</el-dropdown-item>
                <el-dropdown-item command="delete" divided style="color: var(--el-color-danger);">删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div class="card-body">
          <p class="agent-desc">{{ agent.description || '无描述' }}</p>
          <div class="card-info-row">
            <span class="info-label">关联知识库</span>
            <span class="info-value">{{ agent.kb_ids?.length || 0 }} 个</span>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="editingAgent ? '编辑 Agent' : '新建 Agent'" width="560px" destroy-on-close>
      <el-form ref="agentFormRef" :model="form" :rules="agentFormRules" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：法务助手、技术文档专家" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="职责描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="描述该 Agent 的专长领域，用于路由判断" />
        </el-form-item>
        <el-form-item label="关联知识库">
          <el-select v-model="form.kb_ids" multiple placeholder="选择知识库" style="width: 100%">
            <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="LLM 模型">
          <el-select v-model="form.llm_model_id" placeholder="使用默认模型" clearable style="width: 100%">
            <el-option v-for="m in llmModels" :key="m.id" :label="`${m.provider} / ${m.model_name}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="系统提示词">
          <el-input v-model="form.system_prompt" type="textarea" :rows="3" placeholder="自定义系统提示词（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAgent">{{ editingAgent ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { Plus, Bot, MoreHorizontal } from 'lucide-vue-next'
import request from '../../utils/request'

const agents = ref<any[]>([])
const knowledgeBases = ref<any[]>([])
const llmModels = ref<any[]>([])
const loading = ref(true)
const saving = ref(false)
const dialogVisible = ref(false)
const editingAgent = ref<any>(null)
const agentFormRef = ref<FormInstance>()
const form = ref({ name: '', description: '', kb_ids: [] as number[], llm_model_id: null as number | null, system_prompt: '' })

const agentFormRules = {
  name: [
    { required: true, message: '请输入 Agent 名称', trigger: 'blur' },
    { max: 200, message: '名称长度不能超过 200 个字符', trigger: 'blur' },
  ],
}

const loadData = async () => {
  loading.value = true
  try {
    const [agentsRes, kbRes, modelsRes] = await Promise.all([
      request.get('/agents/'),
      request.get('/knowledge-bases/'),
      request.get('/models/'),
    ])
    agents.value = Array.isArray(agentsRes) ? agentsRes : []
    knowledgeBases.value = Array.isArray(kbRes) ? kbRes : []
    llmModels.value = (Array.isArray(modelsRes) ? modelsRes : []).filter((m: any) => m.model_type === 'llm')
  } catch (e: any) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const openDialog = (agent?: any) => {
  editingAgent.value = agent || null
  form.value = agent
    ? { name: agent.name, description: agent.description || '', kb_ids: [...(agent.kb_ids || [])], llm_model_id: agent.llm_model_id, system_prompt: agent.system_prompt || '' }
    : { name: '', description: '', kb_ids: [], llm_model_id: null, system_prompt: '' }
  dialogVisible.value = true
}

const saveAgent = async () => {
  try { await agentFormRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (editingAgent.value) {
      await request.put(`/agents/${editingAgent.value.id}`, form.value)
      ElMessage.success('Agent 已更新')
    } else {
      await request.post('/agents/', form.value)
      ElMessage.success('Agent 已创建')
    }
    dialogVisible.value = false
    await loadData()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

const handleCommand = async (cmd: string, agent: any) => {
  if (cmd === 'edit') { openDialog(agent); return }
  if (cmd === 'toggle') {
    try {
      await request.put(`/agents/${agent.id}`, { is_active: !agent.is_active })
      ElMessage.success(agent.is_active ? 'Agent 已停用' : 'Agent 已启用')
      await loadData()
    } catch { ElMessage.error('操作失败') }
    return
  }
  if (cmd === 'delete') {
    await ElMessageBox.confirm(`确定删除 Agent「${agent.name}」？`, '删除确认', { type: 'warning' })
    try {
      await request.delete(`/agents/${agent.id}`)
      ElMessage.success('Agent 已删除')
      await loadData()
    } catch { ElMessage.error('删除失败') }
  }
}

onMounted(loadData)
</script>

<style scoped>
.agents-page { padding: 24px; max-width: 1200px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h2 { margin: 0 0 4px; font-size: 20px; }
.page-desc { color: var(--el-text-color-secondary); font-size: 13px; margin: 0; }
.empty-state { text-align: center; padding: 80px 20px; color: var(--el-text-color-secondary); }
.sub-text { font-size: 13px; margin-top: 4px; }
.agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.agent-card { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 16px; transition: box-shadow 0.2s; }
.agent-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.agent-card.inactive { opacity: 0.6; }
.card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.agent-avatar { width: 36px; height: 36px; border-radius: 8px; background: var(--el-color-primary-light-9); color: var(--el-color-primary); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.card-title-area { flex: 1; min-width: 0; }
.card-title { font-weight: 600; font-size: 15px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-body { font-size: 13px; }
.agent-desc { color: var(--el-text-color-secondary); margin: 0 0 8px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-info-row { display: flex; justify-content: space-between; padding: 4px 0; }
.info-label { color: var(--el-text-color-secondary); }
.info-value { font-weight: 500; }
</style>
