<template>
  <div class="automations-page">
    <div class="page-header">
      <div>
        <h2>自动化任务</h2>
        <p class="page-desc">创建定时、Webhook 或事件驱动的自动化任务，实现工作流自动执行。</p>
      </div>
      <el-button type="primary" @click="openCreateDialog">
        <Zap :size="16" :stroke-width="1.5" style="margin-right: 4px" />创建任务
      </el-button>
    </div>

    <div v-if="loading" v-loading="true" style="min-height: 200px"></div>
    <div v-else-if="!tasks.length" class="empty-state">
      <Zap :size="48" :stroke-width="1" style="color: var(--el-text-color-secondary); margin-bottom: 16px" />
      <p>还没有创建任何自动化任务</p>
      <el-button type="primary" @click="openCreateDialog">创建第一个任务</el-button>
      <el-button link type="primary" style="margin-left: 8px" @click="$router.push('/guide')">查看使用指南</el-button>
    </div>

    <el-table v-else :data="tasks" stripe class="task-table">
      <el-table-column prop="name" label="任务名称" min-width="180">
        <template #default="{ row }">
          <div class="task-name-cell">
            <span class="task-name">{{ row.name }}</span>
            <span v-if="row.description" class="task-desc">{{ row.description }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="typeTagMap[row.task_type]?.type || 'info'" effect="plain">
            <component :is="typeTagMap[row.task_type]?.icon" :size="12" :stroke-width="1.5" style="margin-right: 3px; vertical-align: -1px" />
            {{ typeTagMap[row.task_type]?.label || row.task_type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-switch
            v-model="row.is_active"
            size="small"
            :loading="row._toggling"
            @change="(val: any) => handleToggle(row, val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上次执行" width="170">
        <template #default="{ row }">
          <span v-if="row.last_run_at" class="cell-secondary">{{ formatTime(row.last_run_at) }}</span>
          <span v-else class="cell-muted">从未执行</span>
        </template>
      </el-table-column>
      <el-table-column label="执行结果" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.last_status === 'success'" size="small" type="success" effect="plain">成功</el-tag>
          <el-tag v-else-if="row.last_status === 'failed'" size="small" type="danger" effect="plain">失败</el-tag>
          <span v-else class="cell-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="run_count" label="执行次数" width="100" align="center">
        <template #default="{ row }">
          <span class="cell-secondary">{{ row.run_count ?? 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <div class="action-buttons">
            <el-tooltip content="手动执行" placement="top" :show-after="400">
              <el-button link size="small" :loading="row._running" @click="handleRun(row)">
                <Play :size="15" :stroke-width="1.5" />
              </el-button>
            </el-tooltip>
            <el-tooltip content="编辑" placement="top" :show-after="400">
              <el-button link size="small" @click="openEditDialog(row)">
                <Pencil :size="15" :stroke-width="1.5" />
              </el-button>
            </el-tooltip>
            <el-tooltip content="执行日志" placement="top" :show-after="400">
              <el-button link size="small" @click="openLogsDialog(row)">
                <FileText :size="15" :stroke-width="1.5" />
              </el-button>
            </el-tooltip>
            <el-tooltip content="删除" placement="top" :show-after="400">
              <el-button link size="small" type="danger" @click="handleDelete(row)">
                <Trash2 :size="15" :stroke-width="1.5" />
              </el-button>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="total > pageSize" class="pagination-wrap">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadTasks"
      />
    </div>

    <!-- Create / Edit dialog -->
    <el-dialog
      v-model="showFormDialog"
      :title="editingTask ? '编辑任务' : '创建任务'"
      width="620px"
      @close="resetForm"
      destroy-on-close
    >
      <el-form :model="form" label-width="100px" class="task-form">
        <el-form-item label="任务名称" required>
          <el-input v-model="form.name" placeholder="输入任务名称" maxlength="100" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选描述" maxlength="500" />
        </el-form-item>

        <el-divider content-position="left">触发方式</el-divider>

        <el-form-item label="任务类型" required>
          <el-select v-model="form.task_type" style="width: 100%" :disabled="!!editingTask" @change="onTaskTypeChange">
            <el-option label="定时任务" value="scheduled">
              <div class="option-row"><Clock :size="14" :stroke-width="1.5" /><span>定时任务</span></div>
            </el-option>
            <el-option label="Webhook" value="webhook">
              <div class="option-row"><Webhook :size="14" :stroke-width="1.5" /><span>Webhook</span></div>
            </el-option>
            <el-option label="事件触发" value="event">
              <div class="option-row"><Zap :size="14" :stroke-width="1.5" /><span>事件触发</span></div>
            </el-option>
          </el-select>
        </el-form-item>

        <!-- Scheduled fields -->
        <template v-if="form.task_type === 'scheduled'">
          <el-form-item label="调度方式">
            <el-radio-group v-model="scheduleMode">
              <el-radio value="interval">间隔执行</el-radio>
              <el-radio value="cron">Cron 表达式</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="scheduleMode === 'interval'" label="间隔（分钟）" required>
            <el-input-number v-model="form.interval_minutes" :min="1" :max="43200" style="width: 200px" />
          </el-form-item>
          <el-form-item v-else label="Cron 表达式" required>
            <el-input v-model="form.cron_expression" placeholder="例如: 0 */6 * * *" style="width: 300px" />
            <span class="form-hint">支持标准五段式 Cron 表达式</span>
          </el-form-item>
        </template>

        <!-- Webhook fields -->
        <template v-if="form.task_type === 'webhook'">
          <el-form-item label="Webhook URL">
            <div class="webhook-url-display">
              <el-input
                :model-value="webhookDisplayUrl"
                readonly
                class="webhook-input"
              >
                <template #append>
                  <el-button @click="copyWebhookUrl">
                    <Copy :size="14" :stroke-width="1.5" />
                  </el-button>
                </template>
              </el-input>
              <span class="form-hint" v-if="!editingTask">创建后将生成 Webhook URL</span>
            </div>
          </el-form-item>
        </template>

        <!-- Event fields -->
        <template v-if="form.task_type === 'event'">
          <el-form-item label="触发事件" required>
            <el-select v-model="form.event_trigger" placeholder="选择触发事件" style="width: 100%">
              <el-option label="文档上传" value="document.uploaded" />
              <el-option label="文档处理完成" value="document.processed" />
              <el-option label="知识库创建" value="kb.created" />
            </el-select>
          </el-form-item>
        </template>

        <el-divider content-position="left">执行动作</el-divider>

        <el-form-item label="动作" required>
          <el-select v-model="form.config.action" placeholder="选择执行动作" style="width: 100%" @change="onActionChange">
            <el-option label="知识库摘要" value="summarize_kb" />
            <el-option label="智能体查询" value="run_agent_query" />
            <el-option label="导出报告" value="export_report" />
            <el-option label="通知渠道" value="notify_channel" />
            <el-option label="执行链" value="run_chain" />
          </el-select>
        </el-form-item>

        <!-- Action params: summarize_kb -->
        <template v-if="form.config.action === 'summarize_kb'">
          <el-form-item label="知识库" required>
            <el-select v-model="form.config.kb_id" placeholder="选择知识库" style="width: 100%">
              <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
            </el-select>
          </el-form-item>
        </template>

        <!-- Action params: run_agent_query -->
        <template v-if="form.config.action === 'run_agent_query'">
          <el-form-item label="知识库" required>
            <el-select v-model="form.config.kb_id" placeholder="选择知识库" style="width: 100%">
              <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="查询内容" required>
            <el-input v-model="form.config.query" type="textarea" :rows="2" placeholder="输入查询内容" />
          </el-form-item>
          <el-form-item label="LLM 模型">
            <el-select v-model="form.config.llm_model_id" placeholder="使用默认模型" clearable style="width: 100%">
              <el-option v-for="m in llmModels" :key="m.id" :label="m.display_name || m.model_name" :value="m.id" />
            </el-select>
          </el-form-item>
        </template>

        <!-- Action params: export_report -->
        <template v-if="form.config.action === 'export_report'">
          <el-form-item label="知识库" required>
            <el-select v-model="form.config.kb_id" placeholder="选择知识库" style="width: 100%">
              <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
            </el-select>
          </el-form-item>
        </template>

        <!-- Action params: notify_channel -->
        <template v-if="form.config.action === 'notify_channel'">
          <el-form-item label="通知渠道" required>
            <el-input v-model="form.config.channel" placeholder="例如：log、dingtalk、feishu" />
          </el-form-item>
          <el-form-item label="Webhook 地址">
            <el-input v-model="form.config.webhook_url" placeholder="可选，填写后将发送到指定 Webhook" />
          </el-form-item>
          <el-form-item label="消息模板" required>
            <el-input v-model="form.config.message" type="textarea" :rows="3" placeholder="可直接填写通知内容" />
          </el-form-item>
        </template>

        <!-- Action params: run_chain -->
        <template v-if="form.config.action === 'run_chain'">
          <el-form-item label="链 ID" required>
            <el-input v-model="form.config.chain_id" placeholder="输入执行链 ID" />
          </el-form-item>
          <el-form-item label="知识库">
            <el-select v-model="form.config.kb_id" placeholder="可选，用于知识检索类技能" clearable style="width: 100%">
              <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="初始输入">
            <el-input v-model="form.config.initial_input" type="textarea" :rows="2" placeholder="可选，作为技能链的初始输入" />
          </el-form-item>
        </template>

        <el-alert
          v-if="automationTemplateHints.length"
          type="info"
          :closable="false"
          class="template-hint-alert"
        >
          <template #title>可用模板变量</template>
          <div class="template-hint-list">
            <code v-for="hint in automationTemplateHints" :key="hint" class="template-code">{{ hint }}</code>
          </div>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="showFormDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          {{ editingTask ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Logs dialog -->
    <el-dialog v-model="showLogsDialog" title="执行日志" width="750px" destroy-on-close>
      <div class="logs-header">
        <span class="logs-task-name">{{ logsTaskName }}</span>
        <el-button link @click="loadLogs">
          <RefreshCw :size="14" :stroke-width="1.5" style="margin-right: 4px" />刷新
        </el-button>
      </div>
      <el-table :data="logs" v-loading="logsLoading" stripe class="logs-table" empty-text="暂无执行记录">
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'success'" size="small" type="success" effect="plain">成功</el-tag>
            <el-tag v-else-if="row.status === 'failed'" size="small" type="danger" effect="plain">失败</el-tag>
            <el-tag v-else-if="row.status === 'running'" size="small" type="warning" effect="plain">运行中</el-tag>
            <el-tag v-else size="small" effect="plain">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="触发方式" width="100">
          <template #default="{ row }">
            <span class="cell-secondary">{{ row.triggered_by || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            <span class="cell-secondary">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">
            <span v-if="row.duration_ms != null" class="cell-secondary">{{ (row.duration_ms / 1000).toFixed(1) }}s</span>
            <span v-else class="cell-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="结果 / 错误" min-width="200">
          <template #default="{ row }">
            <span v-if="row.error_message" class="log-error">{{ row.error_message }}</span>
            <span v-else-if="row.output" class="cell-secondary log-output">{{ row.output }}</span>
            <span v-else class="cell-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="logsTotal > logsPageSize" class="pagination-wrap">
        <el-pagination
          v-model:current-page="logsPage"
          :page-size="logsPageSize"
          :total="logsTotal"
          layout="total, prev, pager, next"
          @current-change="loadLogs"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onActivated, markRaw, type Component } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Zap, Clock, Webhook, Play, Pencil, FileText, Trash2,
  Copy, RefreshCw,
} from 'lucide-vue-next'
import {
  listAutomations, createAutomation, updateAutomation,
  deleteAutomation, runAutomation, getAutomationLogs,
  type AutomationTask,
} from '../../api/automations'
import { listKnowledgeBases } from '../../api/knowledgeBase'
import { getBackendOrigin } from '../../utils/apiBase'
import { listModels } from '../../api/models'

const loading = ref(false)
const tasks = ref<(AutomationTask & { _running?: boolean; _toggling?: boolean })[]>([])
const currentPage = ref(1)
const pageSize = 15
const total = ref(0)

const knowledgeBases = ref<any[]>([])
const llmModels = ref<any[]>([])

const typeTagMap: Record<string, { label: string; type: string; icon: Component }> = {
  scheduled: { label: '定时', type: '', icon: markRaw(Clock) },
  webhook:   { label: 'Webhook', type: 'warning', icon: markRaw(Webhook) },
  event:     { label: '事件', type: 'success', icon: markRaw(Zap) },
}

// --- Form dialog ---
const showFormDialog = ref(false)
const saving = ref(false)
const editingTask = ref<AutomationTask | null>(null)
const scheduleMode = ref<'interval' | 'cron'>('interval')

const defaultConfig = (): Record<string, any> => ({ action: '' })

function normalizeAutomationConfig(config: Record<string, any> | string | null | undefined) {
  const raw = typeof config === 'string' ? JSON.parse(config) : (config || {})
  const action = raw.action || ''
  const params = raw.params && typeof raw.params === 'object' ? raw.params : raw

  if (action === 'run_agent_query') {
    return {
      action,
      kb_id: params.kb_id,
      query: params.query,
      llm_model_id: params.model_id ?? params.llm_model_id,
    }
  }
  if (action === 'summarize_kb' || action === 'export_report') {
    return {
      action,
      kb_id: params.kb_id,
      llm_model_id: params.model_id ?? params.llm_model_id,
    }
  }
  if (action === 'notify_channel') {
    return {
      action,
      channel: params.channel ?? params.channel_id ?? 'log',
      webhook_url: params.webhook_url ?? '',
      message: params.message ?? params.message_template ?? '',
    }
  }
  if (action === 'run_chain') {
    return {
      action,
      chain_id: params.chain_id,
      kb_id: params.kb_id,
      initial_input: params.initial_input ?? '',
      llm_model_id: params.model_id ?? params.llm_model_id,
    }
  }

  return { ...raw }
}

function buildAutomationConfigPayload(config: Record<string, any>) {
  const action = config.action
  const params: Record<string, any> = {}

  if (action === 'summarize_kb') {
    params.kb_id = config.kb_id
    if (config.llm_model_id) params.model_id = config.llm_model_id
  } else if (action === 'run_agent_query') {
    params.kb_id = config.kb_id
    params.query = config.query
    if (config.llm_model_id) params.model_id = config.llm_model_id
  } else if (action === 'export_report') {
    params.kb_id = config.kb_id
  } else if (action === 'notify_channel') {
    params.channel = config.channel || 'log'
    params.webhook_url = config.webhook_url || undefined
    params.message = config.message
  } else if (action === 'run_chain') {
    params.chain_id = config.chain_id
    params.kb_id = config.kb_id || undefined
    params.initial_input = config.initial_input || undefined
    if (config.llm_model_id) params.model_id = config.llm_model_id
  }

  return { action, params }
}

const form = reactive({
  name: '',
  description: '',
  task_type: 'scheduled' as string,
  cron_expression: '',
  interval_minutes: 60,
  event_trigger: '',
  config: defaultConfig(),
})

// --- Logs dialog ---
const showLogsDialog = ref(false)
const logsLoading = ref(false)
const logsTaskId = ref<number | null>(null)
const logsTaskName = ref('')
const logs = ref<any[]>([])
const logsPage = ref(1)
const logsPageSize = 20
const logsTotal = ref(0)

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

const webhookDisplayUrl = computed(() => {
  if (editingTask.value?.webhook_token) {
    const base = getBackendOrigin()
    return `${base}/api/v1/webhooks/${editingTask.value.webhook_token}`
  }
  return '创建后自动生成'
})

const automationTemplateHints = computed(() => {
  const hints = ['{{initial_input}}']
  if (form.task_type === 'event' || form.task_type === 'webhook') {
    hints.push('{{event}}', '{{event.doc_id}}', '{{event.kb_id}}')
    if (form.event_trigger === 'document.uploaded' || form.event_trigger === 'document.processed') {
      hints.push('{{doc_id}}', '{{kb_id}}')
    }
    if (form.event_trigger === 'kb.created') {
      hints.push('{{kb_id}}')
    }
  }
  return Array.from(new Set(hints))
})

async function loadTasks() {
  loading.value = true
  try {
    const res: any = await listAutomations({ page: currentPage.value, page_size: pageSize })
    tasks.value = (res?.items || res?.data || res || []).map((t: any) => ({ ...t, _running: false, _toggling: false }))
    total.value = res?.total ?? tasks.value.length
  } catch { /* interceptor handles */ }
  finally { loading.value = false }
}

async function loadReferenceData() {
  const [kbRes, modelRes] = await Promise.allSettled([
    listKnowledgeBases(),
    listModels('llm'),
  ])
  if (kbRes.status === 'fulfilled') knowledgeBases.value = (kbRes.value as any) || []
  if (modelRes.status === 'fulfilled') llmModels.value = (modelRes.value as any) || []
}

function openCreateDialog() {
  editingTask.value = null
  form.name = ''
  form.description = ''
  form.task_type = 'scheduled'
  form.cron_expression = ''
  form.interval_minutes = 60
  form.event_trigger = ''
  form.config = defaultConfig()
  scheduleMode.value = 'interval'
  loadReferenceData()
  showFormDialog.value = true
}

function openEditDialog(task: AutomationTask) {
  editingTask.value = task
  form.name = task.name
  form.description = task.description || ''
  form.task_type = task.task_type
  form.cron_expression = task.cron_expression || ''
  form.interval_minutes = task.interval_minutes || 60
  form.event_trigger = task.event_trigger || ''
  form.config = normalizeAutomationConfig(task.config)
  scheduleMode.value = task.cron_expression ? 'cron' : 'interval'
  loadReferenceData()
  showFormDialog.value = true
}

function resetForm() {
  editingTask.value = null
}

function onTaskTypeChange() {
  form.cron_expression = ''
  form.interval_minutes = 60
  form.event_trigger = ''
  scheduleMode.value = 'interval'
}

function onActionChange() {
  const action = form.config.action
  form.config = { action }
}

function validateAutomationForm() {
  if (form.task_type === 'scheduled') {
    if (scheduleMode.value === 'cron' && !form.cron_expression?.trim()) {
      ElMessage.warning('请输入 Cron 表达式')
      return false
    }
    if (scheduleMode.value === 'interval' && !form.interval_minutes) {
      ElMessage.warning('请设置执行间隔')
      return false
    }
  }

  if (form.task_type === 'event' && !form.event_trigger) {
    ElMessage.warning('请选择触发事件')
    return false
  }

  if (form.config.action === 'summarize_kb' && !form.config.kb_id) {
    ElMessage.warning('请选择知识库')
    return false
  }
  if (form.config.action === 'run_agent_query') {
    if (!form.config.kb_id) {
      ElMessage.warning('请选择知识库')
      return false
    }
    if (!form.config.query?.trim()) {
      ElMessage.warning('请输入查询内容')
      return false
    }
  }
  if (form.config.action === 'export_report' && !form.config.kb_id) {
    ElMessage.warning('请选择知识库')
    return false
  }
  if (form.config.action === 'notify_channel') {
    if (!form.config.channel?.trim()) {
      ElMessage.warning('请输入通知渠道')
      return false
    }
    if (!form.config.message?.trim()) {
      ElMessage.warning('请输入消息模板')
      return false
    }
  }
  if (form.config.action === 'run_chain' && !String(form.config.chain_id || '').trim()) {
    ElMessage.warning('请输入链 ID')
    return false
  }

  return true
}

async function copyWebhookUrl() {
  if (!editingTask.value?.webhook_token) {
    ElMessage.info('请先保存任务以生成 Webhook URL')
    return
  }
  try {
    await navigator.clipboard.writeText(webhookDisplayUrl.value)
    ElMessage.success('已复制 Webhook URL')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入任务名称')
    return
  }
  if (!form.config.action) {
    ElMessage.warning('请选择执行动作')
    return
  }
  if (!validateAutomationForm()) {
    return
  }

  saving.value = true
  try {
    const payload: Record<string, any> = {
      name: form.name,
      description: form.description || undefined,
      task_type: form.task_type,
      config: buildAutomationConfigPayload(form.config),
    }

    if (form.task_type === 'scheduled') {
      if (scheduleMode.value === 'cron') {
        payload.cron_expression = form.cron_expression
        payload.interval_minutes = undefined
      } else {
        payload.interval_minutes = form.interval_minutes
        payload.cron_expression = undefined
      }
    }
    if (form.task_type === 'event') {
      payload.event_trigger = form.event_trigger
    }

    if (editingTask.value) {
      await updateAutomation(editingTask.value.id, payload)
      ElMessage.success('任务已更新')
    } else {
      await createAutomation(payload as any)
      ElMessage.success('任务已创建')
    }
    showFormDialog.value = false
    await loadTasks()
  } catch { /* interceptor handles */ }
  finally { saving.value = false }
}

async function handleToggle(task: any, val: boolean) {
  task._toggling = true
  try {
    await updateAutomation(task.id, { is_active: val })
    ElMessage.success(val ? '已启用' : '已停用')
  } catch {
    task.is_active = !val
  }
  finally { task._toggling = false }
}

async function handleRun(task: any) {
  task._running = true
  try {
    await runAutomation(task.id)
    ElMessage.success(`任务「${task.name}」已触发执行`)
    setTimeout(() => loadTasks(), 2000)
  } catch { /* interceptor handles */ }
  finally { task._running = false }
}

async function handleDelete(task: AutomationTask) {
  try {
    await ElMessageBox.confirm(`确定删除任务「${task.name}」？删除后不可恢复。`, '删除任务', { type: 'warning' })
  } catch { return }
  try {
    await deleteAutomation(task.id)
    ElMessage.success('已删除')
    await loadTasks()
  } catch { /* interceptor handles */ }
}

function openLogsDialog(task: AutomationTask) {
  logsTaskId.value = task.id
  logsTaskName.value = task.name
  logsPage.value = 1
  logs.value = []
  logsTotal.value = 0
  showLogsDialog.value = true
  loadLogs()
}

async function loadLogs() {
  if (!logsTaskId.value) return
  logsLoading.value = true
  try {
    const res: any = await getAutomationLogs(logsTaskId.value, { page: logsPage.value, page_size: logsPageSize })
    logs.value = res?.items || res?.data || res || []
    logsTotal.value = res?.total ?? logs.value.length
  } catch { /* interceptor handles */ }
  finally { logsLoading.value = false }
}

onActivated(() => {
  loadTasks()
})
</script>

<style scoped>
.automations-page {
  max-width: 1200px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
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
  color: var(--el-text-color-secondary);
}

.empty-state {
  text-align: center;
  padding: 60px 0;
  color: var(--el-text-color-secondary);
}

.empty-state p {
  margin-bottom: 16px;
  font-size: 14px;
}

/* ── Table ── */
.task-table {
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.task-name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.task-name {
  font-weight: 500;
  color: var(--text-primary);
}

.task-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.cell-secondary {
  font-size: 13px;
  color: var(--text-secondary);
}

.cell-muted {
  font-size: 13px;
  color: var(--text-muted);
}

.action-buttons {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* ── Form dialog ── */
.task-form .option-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.form-hint {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

.webhook-url-display {
  width: 100%;
}

.webhook-input :deep(.el-input__inner) {
  font-family: var(--font-mono);
  font-size: 12px;
}

.template-hint-alert {
  margin-top: 8px;
}

.template-hint-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}

.template-code {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--gray-100);
  color: var(--primary);
}

:deep(.el-divider__text) {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* ── Logs dialog ── */
.logs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.logs-task-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.logs-table {
  border-radius: var(--radius);
  overflow: hidden;
}

.log-error {
  font-size: 12px;
  color: var(--danger);
  word-break: break-all;
}

.log-output {
  font-size: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>
