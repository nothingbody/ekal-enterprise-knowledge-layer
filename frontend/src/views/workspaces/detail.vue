<template>
  <div class="ws-detail-page">
    <!-- Back + Header -->
    <div class="detail-header">
      <el-button link @click="$router.push('/workspaces')">
        <ArrowLeft :size="16" :stroke-width="1.5" style="margin-right: 4px" />返回
      </el-button>
    </div>

    <div v-loading="loading" class="detail-body">
      <template v-if="workspace">
        <!-- Workspace Info -->
        <div class="ws-info-card">
          <div class="ws-info-main">
            <div class="ws-icon"><Building2 :size="24" :stroke-width="1.5" /></div>
            <div>
              <h1>{{ workspace.name }}</h1>
              <p v-if="workspace.description" class="ws-desc">{{ workspace.description }}</p>
              <div class="ws-meta">
                <span><Users :size="13" :stroke-width="1.5" /> {{ workspace.member_count }} 名成员</span>
                <span><LibraryBig :size="13" :stroke-width="1.5" /> {{ workspace.kb_count }} 个知识库</span>
                <el-tag size="small" :type="workspace.role === 'owner' ? 'danger' : workspace.role === 'admin' ? 'warning' : 'info'">
                  {{ roleMap[workspace.role] || workspace.role }}
                </el-tag>
              </div>
            </div>
          </div>
          <div class="ws-actions">
            <el-button v-if="workspace.role !== 'owner'" type="danger" plain @click="handleLeave">
              <LogOut :size="14" :stroke-width="1.5" style="margin-right: 4px" />退出工作空间
            </el-button>
          </div>
          <div v-if="canManage" class="ws-actions">
            <el-button type="primary" @click="openCreateKb">
              <Plus :size="14" :stroke-width="1.5" style="margin-right: 4px" />创建知识库
            </el-button>
            <el-dropdown trigger="click">
              <el-button>
                <UserPlus :size="14" :stroke-width="1.5" style="margin-right: 4px" />邀请成员
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="showMemberDialog = true">通过用户名添加</el-dropdown-item>
                  <el-dropdown-item @click="openInviteLinkDialog">生成邀请链接</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <!-- Tabs -->
        <el-tabs v-model="activeTab" class="detail-tabs">
          <el-tab-pane name="kbs">
            <template #label><LibraryBig :size="14" :stroke-width="1.5" style="margin-right: 4px" />知识库 ({{ kbList.length }})</template>
          </el-tab-pane>
          <el-tab-pane name="models">
            <template #label><Cpu :size="14" :stroke-width="1.5" style="margin-right: 4px" />模型 ({{ wsModels.length }})</template>
          </el-tab-pane>
          <el-tab-pane name="channels">
            <template #label><Radio :size="14" :stroke-width="1.5" style="margin-right: 4px" />渠道 ({{ wsChannels.length }})</template>
          </el-tab-pane>
          <el-tab-pane name="members">
            <template #label><Users :size="14" :stroke-width="1.5" style="margin-right: 4px" />成员 ({{ members.length }})</template>
          </el-tab-pane>
        </el-tabs>

        <!-- KB Tab -->
        <div v-if="activeTab === 'kbs'">
          <div v-if="kbLoading" v-loading="true" style="min-height: 120px"></div>
          <el-empty v-else-if="!kbList.length" description="暂无知识库">
            <el-button v-if="canManage" type="primary" @click="openCreateKb">创建知识库</el-button>
          </el-empty>
          <el-row v-else :gutter="16">
            <el-col :xs="24" :sm="12" :md="8" v-for="kb in kbList" :key="kb.id">
              <el-card shadow="hover" class="kb-card" @click="$router.push(`/knowledge/${kb.id}/documents`)">
                <div class="kb-card-name">{{ kb.name }}</div>
                <p class="kb-card-desc">{{ kb.description || '暂无描述' }}</p>
                <div class="kb-card-stats">
                  <span><FileText :size="13" :stroke-width="1.5" /> {{ kb.doc_count }} 文档</span>
                  <span><Layers :size="13" :stroke-width="1.5" /> {{ kb.chunk_count }} 片段</span>
                </div>
                <div class="kb-card-actions">
                  <el-button size="small" @click.stop="$router.push(`/knowledge/${kb.id}/documents`)">管理文档</el-button>
                  <el-button size="small" type="primary" @click.stop="$router.push({ path: '/chat', query: { kb_id: kb.id } })">
                    <MessageSquare :size="13" :stroke-width="1.5" style="margin-right: 4px" />开始对话
                  </el-button>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>

        <!-- Models Tab -->
        <div v-if="activeTab === 'models'">
          <div v-if="canManage" style="margin-bottom: 16px">
            <el-button type="primary" @click="openShareModel">
              <Share2 :size="14" :stroke-width="1.5" style="margin-right: 4px" />共享模型到工作空间
            </el-button>
          </div>
          <el-alert v-if="!wsModels.length && !wsModelsLoading" type="info" :closable="false" style="margin-bottom: 16px">
            <template #title>尚未共享模型到此工作空间。管理员可将自己配置的模型共享给团队成员使用，团队成员无需自己配置 API Key。</template>
          </el-alert>
          <div v-loading="wsModelsLoading">
            <el-table v-if="wsModels.length" :data="wsModels" stripe>
              <el-table-column prop="display_name" label="显示名称" min-width="150" />
              <el-table-column label="类型" width="110">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.model_type === 'llm' ? 'primary' : row.model_type === 'embedding' ? 'success' : 'info'">
                    {{ row.model_type === 'llm' ? 'LLM' : row.model_type === 'embedding' ? 'Embedding' : 'Reranker' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="provider" label="提供商" width="110">
                <template #default="{ row }"><el-tag size="small">{{ row.provider }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="model_name" label="模型标识" min-width="160" />
              <el-table-column prop="shared_by_username" label="共享者" width="120" />
              <el-table-column v-if="canManage" label="操作" width="100">
                <template #default="{ row }">
                  <el-button link type="danger" size="small" @click="handleUnshareModel(row)">取消共享</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <!-- Channels Tab -->
        <div v-if="activeTab === 'channels'">
          <div v-if="canManage" style="margin-bottom: 16px">
            <el-button type="primary" @click="$router.push({ path: '/channels', query: { ws_id: wsId } })">
              <Plus :size="14" :stroke-width="1.5" style="margin-right: 4px" />管理渠道
            </el-button>
          </div>
          <div v-loading="wsChannelsLoading">
            <el-table v-if="wsChannels.length" :data="wsChannels" stripe>
              <el-table-column prop="name" label="渠道名称" min-width="150" />
              <el-table-column label="平台" width="120">
                <template #default="{ row }">
                  <el-tag size="small">{{ { wecom: '企微', dingtalk: '钉钉', feishu: '飞书' }[row.platform as string] || row.platform }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '已启用' : '已停用' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="对话模式" width="110">
                <template #default="{ row }">
                  {{ { auto: '自动', rag: '知识检索', sql: '数据库查询', hybrid: '混合', agent: '智能体' }[row.chat_mode as string] || row.chat_mode }}
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!wsChannelsLoading && !wsChannels.length" description="还没有工作空间渠道">
              <el-button v-if="canManage" type="primary" @click="$router.push({ path: '/channels', query: { ws_id: wsId } })">前往创建</el-button>
            </el-empty>
          </div>
        </div>

        <!-- Members Tab -->
        <div v-if="activeTab === 'members'">
          <div v-if="canManage" class="add-member-row">
            <el-input v-model="memberUsername" placeholder="输入用户名" style="flex: 1" />
            <el-select v-model="memberRole" style="width: 120px">
              <el-option label="管理员" value="admin" />
              <el-option label="成员" value="member" />
              <el-option label="只读" value="viewer" />
            </el-select>
            <el-button type="primary" @click="handleAddMember" :loading="addingMember">添加</el-button>
          </div>
          <el-table :data="members" stripe>
            <el-table-column prop="username" label="用户名" />
            <el-table-column prop="email" label="邮箱" />
            <el-table-column label="角色" width="100">
              <template #default="{ row }">
                <el-tag :type="row.role === 'owner' ? 'danger' : row.role === 'admin' ? 'warning' : 'info'" size="small">
                  {{ roleMap[row.role] || row.role }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="canManage" label="操作" width="160">
              <template #default="{ row }">
                <el-select
                  v-if="row.role !== 'owner'"
                  :model-value="row.role"
                  size="small"
                  style="width: 80px; margin-right: 4px;"
                  @change="(val: string) => handleRoleChange(row, val)"
                >
                  <el-option label="管理员" value="admin" />
                  <el-option label="成员" value="member" />
                  <el-option label="只读" value="viewer" />
                </el-select>
                <el-button v-if="row.role !== 'owner'" link type="danger" size="small" @click="handleRemoveMember(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </div>

    <!-- Create KB Dialog -->
    <el-dialog v-model="showCreateKb" title="创建知识库" width="480px">
      <el-form :model="kbForm" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="kbForm.name" placeholder="请输入知识库名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="kbForm.description" type="textarea" :rows="2" placeholder="请输入描述" />
        </el-form-item>
        <el-form-item label="Embedding">
          <el-select v-model="kbForm.embedding_model_id" placeholder="选择 Embedding 模型" clearable style="width: 100%">
            <el-option v-for="m in embeddingModels" :key="m.id" :label="m.display_name" :value="m.id" />
          </el-select>
          <div v-if="!embeddingModels.length" style="font-size: 12px; color: var(--el-color-warning); margin-top: 4px">
            尚未配置 Embedding 模型，<el-button link type="primary" size="small" @click="$router.push('/models')">前往添加</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateKb = false">取消</el-button>
        <el-button type="primary" @click="handleCreateKb" :loading="creatingKb">创建</el-button>
      </template>
    </el-dialog>

    <!-- Invite Member Dialog -->
    <el-dialog v-model="showMemberDialog" title="邀请成员" width="420px">
      <div class="add-member-row">
        <el-input v-model="memberUsername" placeholder="输入用户名" style="flex: 1" />
        <el-select v-model="memberRole" style="width: 120px">
          <el-option label="管理员" value="admin" />
          <el-option label="成员" value="member" />
          <el-option label="只读" value="viewer" />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="showMemberDialog = false">取消</el-button>
        <el-button type="primary" @click="handleAddMember" :loading="addingMember">添加</el-button>
      </template>
    </el-dialog>

    <!-- Generate Invite Link Dialog -->
    <el-dialog v-model="showInviteLinkDialog" title="生成邀请链接" width="480px" :close-on-click-modal="false">
      <div v-if="!generatedLink">
        <el-form label-width="100px">
          <el-form-item label="加入角色">
            <el-select v-model="inviteForm.role" style="width: 100%">
              <el-option label="管理员" value="admin" />
              <el-option label="成员" value="member" />
              <el-option label="只读" value="viewer" />
            </el-select>
          </el-form-item>
          <el-form-item label="有效期">
            <el-select v-model="inviteForm.expires_hours" style="width: 100%">
              <el-option :value="24" label="1 天" />
              <el-option :value="72" label="3 天" />
              <el-option :value="168" label="7 天" />
              <el-option :value="720" label="30 天" />
            </el-select>
          </el-form-item>
          <el-form-item label="使用次数">
            <el-input-number v-model="inviteForm.max_uses" :min="0" :max="1000" style="width: 100%" />
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px">设为 0 或留空表示不限次数</div>
          </el-form-item>
        </el-form>
      </div>
      <div v-else style="text-align: center; padding: 20px 0">
        <p style="margin-bottom: 16px; color: var(--text-secondary)">链接已生成，将以下链接发送给同事：</p>
        <div v-if="generatedRemoteLink" class="invite-link-label">局域网链接</div>
        <el-input :model-value="generatedLink" readonly>
          <template #append>
            <el-button @click="copyLink">复制</el-button>
          </template>
        </el-input>
        <template v-if="generatedRemoteLink">
          <div class="invite-link-label">跨网链接</div>
          <el-input :model-value="generatedRemoteLink" readonly>
            <template #append>
              <el-button @click="copyRemoteLink">复制</el-button>
            </template>
          </el-input>
        </template>
        <p style="margin-top: 12px; font-size: 12px; color: var(--text-muted)">同事打开链接后注册/登录即可自动加入工作空间</p>
      </div>
      <template #footer>
        <template v-if="!generatedLink">
          <el-button @click="showInviteLinkDialog = false">取消</el-button>
          <el-button type="primary" @click="handleGenerateLink" :loading="generatingLink">生成链接</el-button>
        </template>
        <template v-else>
          <el-button type="primary" @click="showInviteLinkDialog = false; generatedLink = ''; generatedRemoteLink = ''">完成</el-button>
        </template>
      </template>
    </el-dialog>

    <!-- Share Model Dialog -->
    <el-dialog v-model="showShareModelDialog" title="共享模型到工作空间" width="480px">
      <p style="margin-bottom: 12px; color: var(--text-secondary); font-size: 13px">选择你配置的模型共享给团队成员使用，成员无需自己配置 API Key。</p>
      <el-table :data="myUnsharedModels" stripe max-height="360" v-loading="loadingMyModels">
        <el-table-column prop="display_name" label="名称" min-width="140" />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.model_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型标识" min-width="140" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleShareModel(row)">共享</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loadingMyModels && !myUnsharedModels.length" description="没有可共享的模型">
        <el-button type="primary" @click="$router.push('/models')">前往配置模型</el-button>
      </el-empty>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import {
  ArrowLeft, Building2, Users, LibraryBig, Plus, UserPlus,
  FileText, Layers, MessageSquare, Cpu, Share2, Link, Radio, LogOut,
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getWorkspace, listWorkspaceKbs, listMembers,
  addMember, updateMemberRole, removeMember,
  listWorkspaceModels, shareModelToWorkspace, unshareModelFromWorkspace,
  createInvitation, leaveWorkspace,
} from '../../api/workspaces'
import { createKnowledgeBase } from '../../api/knowledgeBase'
import { listModels } from '../../api/models'
import { roleMap } from '../../utils/format'
import { listChannels } from '../../api/channels'
import { useWorkspaceStore } from '../../stores/workspace'
import { getShareBaseUrl } from '../../utils/apiBase'

const route = useRoute()
const router = useRouter()
const wsId = computed(() => Number(route.params.id))

const loading = ref(false)
const workspace = ref<any>(null)
const activeTab = ref('kbs')

const kbList = ref<any[]>([])
const kbLoading = ref(false)

const members = ref<any[]>([])
const memberUsername = ref('')
const memberRole = ref('member')
const addingMember = ref(false)
const showMemberDialog = ref(false)

const showCreateKb = ref(false)
const creatingKb = ref(false)
const embeddingModels = ref<any[]>([])
const kbForm = ref({ name: '', description: '', embedding_model_id: null as number | null })

const showInviteLinkDialog = ref(false)
const generatingLink = ref(false)
const generatedLink = ref('')
const generatedRemoteLink = ref('')
const inviteForm = ref({ role: 'member', expires_hours: 168, max_uses: undefined as number | undefined })

const wsChannels = ref<any[]>([])
const wsChannelsLoading = ref(false)

const wsModels = ref<any[]>([])
const wsModelsLoading = ref(false)
const showShareModelDialog = ref(false)
const loadingMyModels = ref(false)
const myModels = ref<any[]>([])
const myUnsharedModels = computed(() => {
  const sharedIds = new Set(wsModels.value.map((m: any) => m.model_id))
  return myModels.value.filter((m: any) => !sharedIds.has(m.id))
})

const canManage = computed(() => {
  const r = workspace.value?.role
  return r === 'owner' || r === 'admin'
})


const workspaceStore = useWorkspaceStore()

async function loadWorkspace() {
  loading.value = true
  try {
    workspace.value = await getWorkspace(wsId.value)
    if (workspace.value) {
      workspaceStore.setCurrent({ id: workspace.value.id, name: workspace.value.name })
    }
  } catch {
    ElMessage.error('工作空间不存在或无权访问')
    router.push('/workspaces')
  } finally {
    loading.value = false
  }
}

async function loadKbs() {
  kbLoading.value = true
  try {
    kbList.value = (await listWorkspaceKbs(wsId.value)) as any
  } finally {
    kbLoading.value = false
  }
}

async function loadMembers() {
  try {
    members.value = (await listMembers(wsId.value)) as any
  } catch { /* */ }
}

async function loadWsChannels() {
  wsChannelsLoading.value = true
  try {
    const res: any = await listChannels({ workspace_id: wsId.value } as any)
    wsChannels.value = res?.items || []
  } catch { /* */ }
  finally { wsChannelsLoading.value = false }
}

async function loadWsModels() {
  wsModelsLoading.value = true
  try {
    wsModels.value = (await listWorkspaceModels(wsId.value)) as any
  } finally {
    wsModelsLoading.value = false
  }
}

async function loadEmbeddingModels() {
  try {
    // Prefer workspace shared models; fall back to user's own
    const wsRes: any = await listWorkspaceModels(wsId.value, 'embedding')
    if (wsRes.length) {
      embeddingModels.value = wsRes.map((m: any) => ({ id: m.model_id, display_name: m.display_name }))
    } else {
      const res: any = await listModels()
      embeddingModels.value = res.filter((m: any) => m.model_type === 'embedding')
    }
  } catch { /* */ }
}

async function openShareModel() {
  showShareModelDialog.value = true
  loadingMyModels.value = true
  try {
    const res: any = await listModels()
    myModels.value = res
  } finally {
    loadingMyModels.value = false
  }
}

async function handleShareModel(model: any) {
  try {
    await shareModelToWorkspace(wsId.value, model.id)
    ElMessage.success(`已共享「${model.display_name}」到工作空间`)
    await loadWsModels()
  } catch { /* interceptor handles */ }
}

async function handleUnshareModel(row: any) {
  try {
    await ElMessageBox.confirm(`确定取消共享「${row.display_name}」？团队成员将无法再使用此模型。`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await unshareModelFromWorkspace(wsId.value, row.link_id)
    ElMessage.success('已取消共享')
    await loadWsModels()
  } catch { /* interceptor handles */ }
}

function openInviteLinkDialog() {
  generatedLink.value = ''
  generatedRemoteLink.value = ''
  inviteForm.value = { role: 'member', expires_hours: 168, max_uses: undefined }
  showInviteLinkDialog.value = true
}

async function handleGenerateLink() {
  generatingLink.value = true
  try {
    const res: any = await createInvitation(wsId.value, {
      role: inviteForm.value.role,
      expires_hours: inviteForm.value.expires_hours,
      max_uses: inviteForm.value.max_uses || null,
    })
    const localOrLanLink = `${getShareBaseUrl()}/invite/${res.invite_token}`
    generatedLink.value = localOrLanLink
    generatedRemoteLink.value = res.remote_invite_url && res.remote_invite_url !== localOrLanLink
      ? res.remote_invite_url
      : ''
  } finally {
    generatingLink.value = false
  }
}

function copyLink() {
  navigator.clipboard.writeText(generatedLink.value).then(() => {
    ElMessage.success('链接已复制到剪贴板')
  }).catch(() => {
    ElMessage.warning('复制失败，请手动复制')
  })
}

function copyRemoteLink() {
  navigator.clipboard.writeText(generatedRemoteLink.value).then(() => {
    ElMessage.success('跨网链接已复制到剪贴板')
  }).catch(() => {
    ElMessage.warning('复制失败，请手动复制')
  })
}

function openCreateKb() {
  kbForm.value = { name: '', description: '', embedding_model_id: null }
  loadEmbeddingModels()
  showCreateKb.value = true
}

async function handleCreateKb() {
  if (!kbForm.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  creatingKb.value = true
  try {
    await createKnowledgeBase({
      name: kbForm.value.name.trim(),
      description: kbForm.value.description || undefined,
      workspace_id: wsId.value,
      embedding_model_id: kbForm.value.embedding_model_id,
    })
    ElMessage.success('知识库创建成功')
    showCreateKb.value = false
    await loadKbs()
    await loadWorkspace()
  } finally {
    creatingKb.value = false
  }
}

async function handleAddMember() {
  if (!memberUsername.value.trim()) {
    ElMessage.warning('请输入用户名')
    return
  }
  addingMember.value = true
  try {
    await addMember(wsId.value, { username: memberUsername.value, role: memberRole.value })
    ElMessage.success('添加成功')
    memberUsername.value = ''
    showMemberDialog.value = false
    await loadMembers()
    await loadWorkspace()
  } catch (err: any) {
    const detail = err?.response?.data?.detail || ''
    if (err?.response?.status === 404) {
      ElMessage.error(`用户「${memberUsername.value}」不存在，请确认用户名是否正确`)
    } else if (err?.response?.status === 409 || detail.includes('已是成员')) {
      ElMessage.warning('该用户已经是工作空间成员')
    } else if (detail) {
      ElMessage.error(detail)
    }
  } finally {
    addingMember.value = false
  }
}

async function handleRoleChange(member: any, newRole: string) {
  try {
    await updateMemberRole(wsId.value, member.id, newRole)
    member.role = newRole
    ElMessage.success('角色已更新')
  } catch { /* interceptor handles */ }
}

async function handleRemoveMember(member: any) {
  try {
    await ElMessageBox.confirm(`确定移除成员「${member.username}」？`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await removeMember(wsId.value, member.id)
    ElMessage.success('已移除')
    await loadMembers()
    await loadWorkspace()
  } catch { /* interceptor handles */ }
}

async function handleLeave() {
  try {
    await ElMessageBox.confirm('确定退出该工作空间？退出后将无法访问其中的资源。', '退出工作空间', { type: 'warning', confirmButtonText: '确认退出', cancelButtonText: '取消' })
  } catch { return }
  try {
    await leaveWorkspace(wsId.value)
    ElMessage.success('已退出工作空间')
    router.push('/workspaces')
  } catch { /* interceptor handles */ }
}

watch(activeTab, (tab) => {
  if (tab === 'members' && !members.value.length) loadMembers()
  if (tab === 'models' && !wsModels.value.length) loadWsModels()
  if (tab === 'channels' && !wsChannels.value.length) loadWsChannels()
})

onActivated(async () => {
  await loadWorkspace()
  loadKbs()
  loadMembers()
  loadWsModels()
})

onBeforeRouteLeave((to) => {
  if (to.path === '/workspaces' && !to.params.id) {
    workspaceStore.setCurrent(null)
  }
})
</script>

<style scoped>
.ws-detail-page {
  max-width: 1100px;
}

.detail-header {
  margin-bottom: 16px;
}

/* ── Info Card ── */
.ws-info-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  background: var(--card-bg, #fff);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 4px;
}

.ws-info-main {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.ws-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.ws-info-main h1 {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.ws-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.ws-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  color: var(--text-muted);
}

.ws-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ws-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* ── Tabs ── */
.detail-tabs {
  margin-bottom: 16px;
}

:deep(.detail-tabs .el-tabs__item) {
  font-weight: 600;
}

/* ── KB Cards ── */
.kb-card {
  margin-bottom: 16px;
  cursor: pointer;
  border-radius: 10px !important;
  transition: all 150ms;
}

.kb-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg, 0 4px 12px rgba(0,0,0,0.1)) !important;
}

.kb-card-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.kb-card-desc {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0 0 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.kb-card-stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.kb-card-stats span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.kb-card-actions {
  display: flex;
  gap: 8px;
}

/* ── Member row ── */
.add-member-row {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.invite-link-label {
  text-align: left;
  margin: 12px 0 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .ws-info-card {
    flex-direction: column;
  }

  .ws-actions {
    width: 100%;
  }
}
</style>
