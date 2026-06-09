<template>
  <div class="analytics-page">
    <div class="page-header">
      <h2>系统统计与用户管理</h2>
      <span class="user-count">共 {{ total }} 位用户</span>
    </div>

    <!-- Stats Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ formatNumber(adminStats.total_users) }}</div>
        <div class="stat-label">总用户数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ formatNumber(adminStats.total_conversations) }}</div>
        <div class="stat-label">总对话数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ formatNumber(adminStats.total_messages) }}</div>
        <div class="stat-label">总消息数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ formatNumber(adminStats.total_tokens) }}</div>
        <div class="stat-label">总 Token 消耗</div>
      </div>
    </div>

    <!-- User Table -->
    <el-table v-loading="loading" :data="users" stripe class="analytics-table" @row-click="openUserDetail">
      <el-table-column prop="username" label="用户名" min-width="120">
        <template #default="{ row }">
          <div class="user-cell">
            <UserIcon :size="14" :stroke-width="1.5" />
            <span>{{ row.username }}</span>
            <el-tag v-if="row.role?.toLowerCase() === 'admin'" type="danger" size="small" style="margin-left: 4px">管理员</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="email" label="邮箱" min-width="180" />
      <el-table-column label="对话数" width="90" sortable :sort-method="(a:any,b:any) => a.conv_count - b.conv_count">
        <template #default="{ row }">
          <span class="stat-num">{{ row.conv_count }}</span>
        </template>
      </el-table-column>
      <el-table-column label="消息数" width="90" sortable :sort-method="(a:any,b:any) => a.msg_count - b.msg_count">
        <template #default="{ row }">
          <span class="stat-num">{{ row.msg_count }}</span>
        </template>
      </el-table-column>
      <el-table-column label="Token 消耗" width="120" sortable :sort-method="(a:any,b:any) => a.total_tokens - b.total_tokens">
        <template #default="{ row }">
          <span class="stat-num token">{{ formatNumber(row.total_tokens) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="平均延迟" width="100">
        <template #default="{ row }">
          <span v-if="row.avg_latency" class="stat-num">{{ row.avg_latency.toFixed(0) }}ms</span>
          <span v-else class="stat-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="最后活跃" width="160">
        <template #default="{ row }">
          <span v-if="row.last_active" class="stat-muted">{{ relativeTime(row.last_active) }}</span>
          <span v-else class="stat-muted">从未对话</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '正常' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="" width="60">
        <template #default>
          <ChevronRight :size="14" :stroke-width="1.5" class="row-arrow" />
        </template>
      </el-table-column>
    </el-table>

    <div v-if="total > pageSize" style="margin-top: 16px; display: flex; justify-content: flex-end;">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadAnalytics"
      />
    </div>

    <!-- Conversation Drawer -->
    <el-drawer v-model="drawerVisible" :title="`${selectedUser?.username} 的对话记录`" size="720px" direction="rtl">
      <template v-if="selectedUser">
        <!-- User Summary -->
        <div class="user-summary">
          <div class="summary-item">
            <MessageSquare :size="16" :stroke-width="1.5" />
            <div>
              <div class="summary-value">{{ selectedUser.conv_count }}</div>
              <div class="summary-label">对话</div>
            </div>
          </div>
          <div class="summary-item">
            <Hash :size="16" :stroke-width="1.5" />
            <div>
              <div class="summary-value">{{ selectedUser.msg_count }}</div>
              <div class="summary-label">消息</div>
            </div>
          </div>
          <div class="summary-item">
            <Zap :size="16" :stroke-width="1.5" />
            <div>
              <div class="summary-value">{{ formatNumber(selectedUser.total_tokens) }}</div>
              <div class="summary-label">Token</div>
            </div>
          </div>
        </div>

        <!-- Conversation List -->
        <div v-loading="convLoading" class="conv-list-section">
          <div v-if="!conversations.length && !convLoading" class="conv-empty-hint">该用户暂无对话记录</div>
          <div
            v-for="conv in conversations" :key="conv.id"
            class="conv-row"
            :class="{ expanded: expandedConvId === conv.id }"
            @click="toggleConv(conv)"
          >
            <div class="conv-row-header">
              <div class="conv-title-area">
                <ChevronRight :size="14" :stroke-width="1.5" class="expand-icon" :class="{ rotated: expandedConvId === conv.id }" />
                <span class="conv-title">{{ conv.title }}</span>
                <el-tag size="small" type="info">{{ conv.kb_name }}</el-tag>
              </div>
              <div class="conv-meta">
                <span><MessageSquare :size="12" :stroke-width="1.5" /> {{ conv.msg_count }}</span>
                <span><Zap :size="12" :stroke-width="1.5" /> {{ formatNumber(conv.tokens) }}</span>
                <span class="conv-time">{{ relativeTime(conv.created_at) }}</span>
              </div>
            </div>

            <!-- Expanded Messages -->
            <div v-if="expandedConvId === conv.id" class="conv-messages" @click.stop>
              <div v-if="msgLoading" v-loading="true" style="min-height: 80px"></div>
              <div v-else-if="!messages.length" class="conv-empty-hint">暂无消息</div>
              <div v-for="msg in messages" :key="msg.id" class="msg-item" :class="msg.role">
                <div class="msg-header">
                  <span class="msg-role">{{ msg.role === 'user' ? '用户' : 'AI' }}</span>
                  <span class="msg-meta">
                    <span v-if="msg.token_count">{{ msg.token_count }} tokens</span>
                    <span v-if="msg.latency_ms">{{ msg.latency_ms.toFixed(0) }}ms</span>
                    <ThumbsUp v-if="msg.feedback === 'like'" :size="12" :stroke-width="1.5" class="feedback-icon like" />
                    <ThumbsDown v-if="msg.feedback === 'dislike'" :size="12" :stroke-width="1.5" class="feedback-icon dislike" />
                  </span>
                </div>
                <div class="msg-content">{{ msg.content }}</div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="convTotal > convPageSize" style="margin-top: 16px; display: flex; justify-content: center;">
          <el-pagination
            v-model:current-page="convPage"
            :page-size="convPageSize"
            :total="convTotal"
            layout="prev, pager, next"
            small
            @current-change="loadConversations"
          />
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onActivated } from 'vue'
import {
  User as UserIcon, ChevronRight, MessageSquare, Hash, Zap,
  ThumbsUp, ThumbsDown,
} from 'lucide-vue-next'
import request from '../../utils/request'
import { relativeTime } from '../../utils/format'

const adminStats = ref({
  total_users: 0,
  total_conversations: 0,
  total_messages: 0,
  total_tokens: 0,
})

const users = ref<any[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20
const loading = ref(false)

const drawerVisible = ref(false)
const selectedUser = ref<any>(null)
const conversations = ref<any[]>([])
const convTotal = ref(0)
const convPage = ref(1)
const convPageSize = 20
const convLoading = ref(false)

const expandedConvId = ref<number | null>(null)
const messages = ref<any[]>([])
const msgLoading = ref(false)

function formatNumber(n: number): string {
  if (!n) return '0'
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}


async function loadAdminStats() {
  try {
    const res: any = await request.get('/system/admin-stats')
    adminStats.value = res
  } catch { /* interceptor */ }
}

async function loadAnalytics() {
  loading.value = true
  try {
    const res: any = await request.get('/users/analytics', { params: { page: currentPage.value, page_size: pageSize } })
    users.value = res?.items || []
    total.value = res?.total || 0
  } catch { /* interceptor */ }
  finally { loading.value = false }
}

function openUserDetail(row: any) {
  selectedUser.value = row
  convPage.value = 1
  expandedConvId.value = null
  messages.value = []
  drawerVisible.value = true
  loadConversations()
}

async function loadConversations() {
  convLoading.value = true
  try {
    const res: any = await request.get(`/users/${selectedUser.value.id}/conversations`, {
      params: { page: convPage.value, page_size: convPageSize },
    })
    conversations.value = res?.items || []
    convTotal.value = res?.total || 0
  } catch { /* interceptor */ }
  finally { convLoading.value = false }
}

async function toggleConv(conv: any) {
  if (expandedConvId.value === conv.id) {
    expandedConvId.value = null
    return
  }
  expandedConvId.value = conv.id
  msgLoading.value = true
  try {
    messages.value = (await request.get(`/users/${selectedUser.value.id}/conversations/${conv.id}/messages`)) as any
  } catch { messages.value = [] }
  finally { msgLoading.value = false }
}

onActivated(() => {
  loadAdminStats()
  loadAnalytics()
})
</script>

<style scoped>
.analytics-page { max-width: 1200px; }

/* ── Stats Cards ── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}
.stat-card {
  padding: 20px 24px;
  background: var(--bg-muted, #f5f7fa);
  border-radius: 12px;
  border: 1px solid var(--border-color, #e4e7ed);
  transition: all 150ms;
}
.stat-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  letter-spacing: -0.02em;
}
.stat-label {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 6px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}
.page-header h2 { font-size: 16px; font-weight: 500; color: var(--text-primary); letter-spacing: -0.03em; }
.user-count { font-size: 13px; color: var(--text-muted); }

.analytics-table { cursor: pointer; }
.user-cell { display: flex; align-items: center; gap: 6px; }
.stat-num { font-weight: 600; font-size: 13px; color: var(--text-primary); }
.stat-num.token { color: var(--el-color-warning); }
.stat-muted { font-size: 12px; color: var(--text-muted); }
.row-arrow { color: var(--text-muted); }

/* ── User Summary ── */
.user-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.summary-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  background: var(--bg-muted, #f5f7fa);
  border-radius: 10px;
}
.summary-value { font-size: 18px; font-weight: 700; color: var(--text-primary); line-height: 1.2; }
.summary-label { font-size: 12px; color: var(--text-muted); }

/* ── Conversation List ── */
.conv-list-section { display: flex; flex-direction: column; gap: 4px; }
.conv-empty-hint { text-align: center; padding: 24px; color: var(--text-muted); font-size: 13px; }

.conv-row {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 150ms;
}
.conv-row:hover { border-color: var(--el-color-primary-light-5); }
.conv-row.expanded { border-color: var(--el-color-primary); }

.conv-row-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  gap: 12px;
}

.conv-title-area {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.expand-icon { transition: transform 200ms; flex-shrink: 0; color: var(--text-muted); }
.expand-icon.rotated { transform: rotate(90deg); }
.conv-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.conv-meta span { display: flex; align-items: center; gap: 3px; }
.conv-time { white-space: nowrap; }

/* ── Messages ── */
.conv-messages {
  border-top: 1px solid var(--border-color);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 400px;
  overflow-y: auto;
}

.msg-item {
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--bg-muted, #f5f7fa);
}
.msg-item.assistant { background: var(--el-color-primary-light-9, #ecf5ff); }

.msg-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.msg-role { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; }
.msg-meta { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--text-muted); }
.feedback-icon.like { color: var(--el-color-success); }
.feedback-icon.dislike { color: var(--el-color-danger); }

.msg-content {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
