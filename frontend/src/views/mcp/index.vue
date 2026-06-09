<template>
  <div class="mcp-page">
    <div class="page-header">
      <div>
        <h2>MCP 服务器</h2>
        <p class="page-desc">管理 MCP (Model Context Protocol) 服务器，为 Agent 提供外部工具能力。</p>
      </div>
      <el-button type="primary" @click="openDialog()">
        <Plus :size="16" :stroke-width="1.5" style="margin-right: 4px" />添加服务器
      </el-button>
    </div>

    <div v-if="loading" v-loading="true" style="min-height: 200px"></div>
    <div v-else-if="!servers.length" class="empty-state">
      <Server :size="48" :stroke-width="1" style="color: var(--el-text-color-secondary); margin-bottom: 16px;" />
      <p>还没有配置任何 MCP 服务器</p>
      <p class="sub-text">添加 MCP 服务器后，Agent 可以调用外部工具完成更复杂的任务</p>
      <el-button type="primary" @click="openDialog()">添加第一个服务器</el-button>
    </div>

    <div v-else class="server-grid">
      <div v-for="srv in servers" :key="srv.id" class="server-card" :class="{ inactive: !srv.is_active }">
        <div class="card-header">
          <div class="server-icon" :class="srv.transport_type">
            <Server :size="20" :stroke-width="1.5" />
          </div>
          <div class="card-title-area">
            <div class="card-title">{{ srv.name }}</div>
            <div class="card-badges">
              <el-tag size="small" effect="plain" :type="transportTagType(srv.transport_type)">{{ transportLabel(srv.transport_type) }}</el-tag>
              <el-tag size="small" :type="srv.connected ? 'success' : (srv.is_active ? 'warning' : 'info')">
                {{ srv.connected ? '已连接' : (srv.is_active ? '断开' : '已停用') }}
              </el-tag>
            </div>
          </div>
          <el-dropdown trigger="click" @command="(cmd: string) => handleCommand(cmd, srv)">
            <el-button link><MoreHorizontal :size="16" :stroke-width="1.5" /></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">编辑</el-dropdown-item>
                <el-dropdown-item command="toggle">{{ srv.is_active ? '停用' : '启用' }}</el-dropdown-item>
                <el-dropdown-item command="test">测试连接</el-dropdown-item>
                <el-dropdown-item command="tools">查看工具</el-dropdown-item>
                <el-dropdown-item command="delete" divided style="color: var(--el-color-danger);">删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="card-body">
          <div v-if="srv.transport_type === 'stdio'" class="card-info-row">
            <span class="info-label">命令</span>
            <span class="info-value mono">{{ srv.command || '-' }}</span>
          </div>
          <div v-else class="card-info-row">
            <span class="info-label">URL</span>
            <span class="info-value mono">{{ srv.url || '-' }}</span>
          </div>
          <div v-if="srv.tool_filter" class="card-info-row">
            <span class="info-label">工具过滤</span>
            <span class="info-value">{{ srv.tool_filter }}</span>
          </div>
          <div class="card-info-row">
            <span class="info-label">创建时间</span>
            <span class="info-value">{{ formatTime(srv.created_at) }}</span>
          </div>
        </div>

        <div class="card-footer">
          <el-button size="small" :loading="srv._testing" @click="handleTest(srv)">
            <Zap :size="13" :stroke-width="1.5" style="margin-right: 3px" />测试
          </el-button>
          <el-button size="small" :disabled="!srv.connected" @click="handleViewTools(srv)">
            <Wrench :size="13" :stroke-width="1.5" style="margin-right: 3px" />工具列表
          </el-button>
        </div>
      </div>
    </div>

    <!-- Create / Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑 MCP 服务器' : '添加 MCP 服务器'" width="560px" destroy-on-close>
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="给服务器起个名字" />
        </el-form-item>
        <el-form-item label="传输类型" prop="transport_type">
          <el-radio-group v-model="form.transport_type">
            <el-radio-button value="http">HTTP (Streamable)</el-radio-button>
            <el-radio-button value="sse">SSE</el-radio-button>
            <el-radio-button value="stdio">Stdio</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- Stdio fields -->
        <template v-if="form.transport_type === 'stdio'">
          <el-form-item label="命令" prop="command">
            <el-input v-model="form.command" placeholder="如: npx, python, node" />
          </el-form-item>
          <el-form-item label="参数">
            <el-input v-model="form.args" placeholder='JSON 数组，如: ["-m", "mcp_server"]' />
            <div class="field-hint">JSON 数组格式的命令行参数</div>
          </el-form-item>
          <el-form-item label="环境变量">
            <el-input v-model="form.env" type="textarea" :rows="2" placeholder='JSON 对象，如: {"API_KEY": "xxx"}' />
          </el-form-item>
        </template>

        <!-- HTTP / SSE fields -->
        <template v-else>
          <el-form-item label="URL" prop="url">
            <el-input v-model="form.url" :placeholder="form.transport_type === 'sse' ? 'http://localhost:3000/sse' : 'http://localhost:3000/mcp'" />
          </el-form-item>
          <el-form-item label="请求头">
            <el-input v-model="form.headers" type="textarea" :rows="2" placeholder='JSON 对象，如: {"Authorization": "Bearer xxx"}' />
          </el-form-item>
        </template>

        <el-form-item label="工具过滤">
          <el-input v-model="form.tool_filter" placeholder="仅暴露匹配的工具名（正则表达式，留空不过滤）" />
          <div class="field-hint">可选。用正则表达式过滤工具，仅匹配的工具会暴露给 Agent</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">{{ editingId ? '保存' : '添加' }}</el-button>
      </template>
    </el-dialog>

    <!-- Tools Dialog -->
    <el-dialog v-model="toolsVisible" :title="`${toolsServerName} — 工具列表`" width="640px" destroy-on-close>
      <div v-loading="toolsLoading">
        <el-empty v-if="!toolsLoading && !toolsList.length" description="该服务器没有注册任何工具" />
        <div v-for="(tool, i) in toolsList" :key="i" class="tool-item">
          <div class="tool-name">
            <Wrench :size="14" :stroke-width="1.5" style="margin-right: 6px; color: var(--el-color-primary);" />
            {{ tool.name }}
          </div>
          <div class="tool-desc">{{ tool.description || '无描述' }}</div>
          <el-collapse v-if="tool.input_schema">
            <el-collapse-item title="参数 Schema">
              <pre class="tool-schema">{{ JSON.stringify(tool.input_schema, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onActivated } from 'vue'
import { Plus, Server, MoreHorizontal, Zap, Wrench } from 'lucide-vue-next'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import {
  listMcpServers,
  createMcpServer,
  updateMcpServer,
  deleteMcpServer,
  toggleMcpServer,
  testMcpServer,
  listMcpServerTools,
} from '../../api/mcpServers'

const loading = ref(false)
const servers = ref<any[]>([])

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  transport_type: 'http' as 'stdio' | 'http' | 'sse',
  command: '',
  args: '',
  env: '',
  url: '',
  headers: '',
  tool_filter: '',
})

const formRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  transport_type: [{ required: true, message: '请选择传输类型', trigger: 'change' }],
  command: [{
    validator: (_: any, val: string, cb: Function) => {
      if (form.transport_type === 'stdio' && !val) cb(new Error('stdio 类型必须填写命令'))
      else cb()
    },
    trigger: 'blur',
  }],
  url: [{
    validator: (_: any, val: string, cb: Function) => {
      if (form.transport_type !== 'stdio' && !val) cb(new Error('请输入服务器 URL'))
      else cb()
    },
    trigger: 'blur',
  }],
}

const toolsVisible = ref(false)
const toolsLoading = ref(false)
const toolsServerName = ref('')
const toolsList = ref<any[]>([])

function transportLabel(t: string) {
  return { stdio: 'Stdio', http: 'HTTP', sse: 'SSE' }[t] || t
}

function transportTagType(t: string) {
  return { stdio: 'danger', http: 'primary', sse: 'warning' }[t] || 'info'
}

function formatTime(iso: string) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString()
}

async function loadServers() {
  loading.value = true
  try {
    const res: any = await listMcpServers({ page: 1, page_size: 200 })
    servers.value = (res.data?.items || res.items || []).map((s: any) => ({ ...s, _testing: false }))
  } catch {
    ElMessage.error('加载 MCP 服务器列表失败')
  } finally {
    loading.value = false
  }
}

function openDialog(srv?: any) {
  editingId.value = srv?.id || null
  form.name = srv?.name || ''
  form.transport_type = srv?.transport_type || 'http'
  form.command = srv?.command || ''
  form.args = srv?.args || ''
  form.env = srv?.env || ''
  form.url = srv?.url || ''
  form.headers = srv?.headers || ''
  form.tool_filter = srv?.tool_filter || ''
  dialogVisible.value = true
}

async function handleSave() {
  if (!formRef.value) return
  await formRef.value.validate()
  saving.value = true
  try {
    const payload: any = {
      name: form.name,
      transport_type: form.transport_type,
      tool_filter: form.tool_filter || undefined,
    }
    if (form.transport_type === 'stdio') {
      payload.command = form.command
      payload.args = form.args || undefined
      payload.env = form.env || undefined
    } else {
      payload.url = form.url
      payload.headers = form.headers || undefined
    }
    if (editingId.value) {
      await updateMcpServer(editingId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await createMcpServer(payload)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    await loadServers()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

async function handleCommand(cmd: string, srv: any) {
  if (cmd === 'edit') openDialog(srv)
  else if (cmd === 'toggle') await handleToggle(srv)
  else if (cmd === 'test') await handleTest(srv)
  else if (cmd === 'tools') await handleViewTools(srv)
  else if (cmd === 'delete') await handleDelete(srv)
}

async function handleToggle(srv: any) {
  try {
    const res: any = await toggleMcpServer(srv.id)
    const data = res.data || res
    srv.is_active = data.is_active
    srv.connected = data.connected
    ElMessage.success(data.is_active ? '已启用' : '已停用')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

async function handleTest(srv: any) {
  srv._testing = true
  try {
    const res: any = await testMcpServer(srv.id)
    const data = res.data || res
    srv.connected = true
    ElMessage.success(`连接成功！发现 ${data.tool_count ?? '?'} 个工具`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '连接测试失败')
  } finally {
    srv._testing = false
  }
}

async function handleViewTools(srv: any) {
  toolsServerName.value = srv.name
  toolsList.value = []
  toolsVisible.value = true
  toolsLoading.value = true
  try {
    const res: any = await listMcpServerTools(srv.id)
    toolsList.value = (res.data?.tools || res.tools || [])
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取工具列表失败')
  } finally {
    toolsLoading.value = false
  }
}

async function handleDelete(srv: any) {
  await ElMessageBox.confirm(`确定删除 MCP 服务器「${srv.name}」？`, '确认删除', { type: 'warning' })
  try {
    await deleteMcpServer(srv.id)
    ElMessage.success('删除成功')
    await loadServers()
  } catch {
    ElMessage.error('删除失败')
  }
}

onActivated(() => {
  loadServers()
})
</script>

<style scoped>
.mcp-page {
  padding: 0;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}
.page-header h2 {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 4px;
}
.page-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 0;
}
.empty-state {
  text-align: center;
  padding: 80px 24px;
}
.empty-state p {
  font-size: 14px;
  color: var(--el-text-color-primary);
  margin: 0;
}
.sub-text {
  font-size: 12px !important;
  color: var(--el-text-color-secondary) !important;
  margin-top: 4px !important;
  margin-bottom: 16px !important;
}

.server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}
.server-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 20px;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.server-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.server-card.inactive {
  opacity: 0.6;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.server-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.server-icon.stdio {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.server-icon.sse {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}
.card-title-area {
  flex: 1;
  min-width: 0;
}
.card-title {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-badges {
  display: flex;
  gap: 6px;
}
.card-body {
  margin-bottom: 16px;
}
.card-info-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}
.card-info-row:last-child {
  border-bottom: none;
}
.info-label {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.info-value {
  color: var(--el-text-color-primary);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}
.info-value.mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}
.card-footer {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-extra-light);
}

.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.tool-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}
.tool-item:last-child {
  border-bottom: none;
}
.tool-name {
  font-weight: 600;
  font-size: 14px;
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}
.tool-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.tool-schema {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

@media (max-width: 768px) {
  .server-grid {
    grid-template-columns: 1fr;
  }
  .page-header {
    flex-direction: column;
    gap: 12px;
  }
}
</style>
