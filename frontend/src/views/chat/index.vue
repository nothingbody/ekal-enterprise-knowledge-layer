<template>
  <div class="chat-page">
    <ChatConversationSidebar
      :mobile-open="mobileSidebarOpen"
      :conversations="filteredConversations"
      :current-conv-id="currentConvId"
      :batch-mode="batchMode"
      :batch-selected="batchSelected"
      :search-text="convSearch"
      :search-loading="searchLoading"
      :is-search-mode="isSearchMode"
      :has-more="convHasMore"
      :loading-more="convLoadingMore"
      @close-mobile="mobileSidebarOpen = false"
      @start-new-chat="startNewChat"
      @toggle-batch-mode="toggleBatchMode"
      @toggle-select-all="(checked) => toggleSelectAll(checked)"
      @batch-delete="batchDelete"
      @update:search-text="convSearch = $event"
      @select-conversation="loadConversation"
      @toggle-batch-item="toggleBatchItem"
      @rename-conversation="renameConv"
      @remove-conversation="removeConv"
      @pin-conversation="pinConv"
      @load-more="loadMoreConvs"
    />

    <div class="chat-main">
      <ChatConfigBar
        :chat-config="chatConfig"
        :kb-list="kbList"
        :llm-models="llmModels"
        :chat-template-options="chatTemplateOptions"
        :show-export-button="!!currentConvId"
        @toggle-mobile-sidebar="mobileSidebarOpen = !mobileSidebarOpen"
        @kb-change="onKbChange"
        @export-conversation="exportConv"
      />

      <div class="messages-area" ref="messagesRef" v-loading="messagesLoading">
        <div v-if="!messages.length && !streaming && welcomeMessage" class="welcome-block">
          <div class="welcome-icon">
            <Sparkles :size="32" :stroke-width="1.5" />
          </div>
          <h2 class="welcome-title">有什么可以帮助你的？</h2>
          <div v-if="chatQuotaInfo && chatQuotaInfo.plan === 'trial'" class="trial-hint">
            免费试用中，剩余 <strong>{{ chatQuotaInfo.trial_remaining }}</strong> / {{ chatQuotaInfo.trial_total }} 次对话
          </div>
          <div class="welcome-mode-hint">当前模式：{{ chatModeLabel }}</div>
          <div class="welcome-text">{{ welcomeMessage }}</div>
          <div v-if="suggestedQuestions.length" class="suggested-questions">
            <div v-for="(sq, i) in suggestedQuestions" :key="i" class="suggest-card" @click="askSuggested(sq)">
              <span class="suggest-text">{{ sq }}</span>
              <ArrowRight :size="14" :stroke-width="1.5" />
            </div>
          </div>
        </div>
        <div v-if="!messages.length && !streaming && !welcomeMessage" class="cold-start">
          <div class="cold-icon-wrap">
            <MessageSquareText :size="32" :stroke-width="1.5" />
          </div>
          <h3>开始智能对话</h3>
          <p v-if="kbList.length && llmModels.length" class="cold-ready">在上方选择知识库和 LLM 模型，然后输入你的问题</p>
          <div v-else class="cold-start-actions">
            <p class="cold-desc">建议先完成：配置模型 → 创建知识库 → 选择后开始对话</p>
            <p v-if="!llmModels.length" class="cold-hint">
              尚未配置 LLM 模型
              <el-button link type="primary" size="small" @click="$router.push('/models')">前往配置</el-button>
            </p>
            <p v-if="!kbList.length" class="cold-hint">
              尚未创建知识库
              <el-button link type="primary" size="small" @click="$router.push('/knowledge')">前往创建</el-button>
            </p>
            <el-button link type="primary" size="small" style="margin-top: 8px" @click="$router.push('/guide')">查看使用指南</el-button>
          </div>
        </div>

        <div v-for="(msg, idx) in messages" :key="idx" class="message" :class="msg.role">
          <div class="msg-avatar">
            <UserIcon v-if="msg.role === 'user'" :size="16" :stroke-width="1.5" />
            <BotIcon v-else :size="16" :stroke-width="1.5" />
          </div>
          <div class="msg-content">
            <div class="msg-text-wrap" v-if="msg.role === 'user'">
              <div class="msg-text">{{ msg.content }}</div>
              <button v-if="canRecallUserMessage(msg)" class="msg-hover-btn user-recall-btn" title="撤回" @click="recallUserMessage(msg)">
                <Undo2 :size="14" :stroke-width="1.5" />
              </button>
              <button class="msg-hover-btn user-edit-btn" title="编辑" @click="editUserMessage(msg)">
                <Edit2 :size="14" :stroke-width="1.5" />
              </button>
            </div>
            <div v-else :ref="(el: any) => onMsgRendered(el, idx)" class="msg-text md-body" :style="msgCollapseStyle(idx)" v-html="renderMd(msg.content)"></div>
            <div v-if="msg.role === 'assistant' && needsCollapse(idx)" class="msg-collapse-bar">
              <div v-if="!expandedMsgs.has(idx)" class="msg-collapse-mask"></div>
              <button class="msg-collapse-btn" @click="toggleExpand(idx)">
                {{ expandedMsgs.has(idx) ? '收起 ▲' : '展开全文 ▼' }}
              </button>
            </div>
            <div v-if="msg.role === 'assistant' && msg.token_count" class="msg-token-info">
              <el-tooltip :content="`输入 ${msg.input_tokens || '?'} + 输出 ${msg.token_count} tokens`" placement="bottom">
                <span class="token-badge">{{ msg.token_count }} tokens</span>
              </el-tooltip>
            </div>
            <!-- Persisted agent tool calls from completed messages -->
            <div v-if="msg._agentToolCalls?.length" class="agent-tool-calls" style="margin-bottom: 8px;">
              <div v-for="tc in msg._agentToolCalls" :key="tc.id" class="tool-call-item" :class="{ 'tool-success': tc.result?.success, 'tool-error': tc.result && !tc.result.success }">
                <div class="tool-call-header">
                  <Wrench :size="13" :stroke-width="1.5" />
                  <span class="tool-name">{{ toolDisplayName(tc.name) }}</span>
                  <CheckCircle2 v-if="tc.result?.success" :size="13" :stroke-width="1.5" class="tool-ok" />
                  <XCircle v-else-if="tc.result" :size="13" :stroke-width="1.5" class="tool-fail" />
                </div>
              </div>
            </div>
            <div v-if="msg._multiAgentEvents?.length" class="multi-agent-events" style="margin-bottom: 8px;">
              <div v-for="ev in msg._multiAgentEvents" :key="ev.id" class="multi-agent-item">
                <div class="tool-call-header">
                  <BotIcon :size="13" :stroke-width="1.5" />
                  <span class="tool-name">{{ ev.agent_name }}</span>
                  <el-tag size="small" :type="ev.type === 'dispatch' ? 'info' : 'success'">
                    {{ ev.type === 'dispatch' ? '已分发' : '已完成' }}
                  </el-tag>
                </div>
                <div v-if="ev.sub_query" class="tool-call-args"><code>{{ ev.sub_query }}</code></div>
                <div v-if="ev.answer" class="tool-text-result">{{ ev.answer }}</div>
              </div>
            </div>
            <div class="msg-actions" v-if="msg.role === 'assistant'">
              <el-button link size="small" @click="playTTS(msg.content)" title="朗读">
                <Volume2 :size="13" :stroke-width="1.5" />
              </el-button>
              <el-button link size="small" @click="copyText(msg.content)">
                <Copy :size="13" :stroke-width="1.5" style="margin-right: 2px" />复制
              </el-button>
              <template v-if="msg.id">
                <el-popover
                  :visible="feedbackPopover.msgId === msg.id && feedbackPopover.type === 'like'"
                  placement="top"
                  :width="220"
                  trigger="manual"
                  @hide="closeFeedbackPopover"
                >
                  <template #reference>
                    <el-button link size="small" @click="openFeedbackPopover(msg.id, 'like')" :type="msg.feedback === 'like' ? 'success' : ''">
                      <ThumbsUp :size="13" :stroke-width="1.5" />
                    </el-button>
                  </template>
                  <div class="feedback-reasons">
                    <div class="feedback-reason-title">选择原因（可选）</div>
                    <el-tag
                      v-for="r in feedbackReasonOptions.like" :key="r.value"
                      :type="msg.feedback_reason === r.value ? 'success' : 'info'"
                      size="small" style="cursor:pointer;margin:2px"
                      @click="sendFeedback(msg.id, 'like', r.value)"
                    >{{ r.label }}</el-tag>
                    <el-button size="small" style="margin-top:6px;width:100%" @click="sendFeedback(msg.id, 'like')">直接提交</el-button>
                  </div>
                </el-popover>
                <el-popover
                  :visible="feedbackPopover.msgId === msg.id && feedbackPopover.type === 'dislike'"
                  placement="top"
                  :width="220"
                  trigger="manual"
                  @hide="closeFeedbackPopover"
                >
                  <template #reference>
                    <el-button link size="small" @click="openFeedbackPopover(msg.id, 'dislike')" :type="msg.feedback === 'dislike' ? 'danger' : ''">
                      <ThumbsDown :size="13" :stroke-width="1.5" />
                    </el-button>
                  </template>
                  <div class="feedback-reasons">
                    <div class="feedback-reason-title">选择原因（可选）</div>
                    <el-tag
                      v-for="r in feedbackReasonOptions.dislike" :key="r.value"
                      :type="msg.feedback_reason === r.value ? 'danger' : 'info'"
                      size="small" style="cursor:pointer;margin:2px"
                      @click="sendFeedback(msg.id, 'dislike', r.value)"
                    >{{ r.label }}</el-tag>
                    <el-button size="small" style="margin-top:6px;width:100%" @click="sendFeedback(msg.id, 'dislike')">直接提交</el-button>
                  </div>
                </el-popover>
                <el-button link size="small" @click="regenerateMsg(msg.id)">
                  <RotateCw :size="13" :stroke-width="1.5" style="margin-right: 2px" />重新生成
                </el-button>
              </template>
              <button v-if="isLastAssistantMsg(idx)" class="msg-hover-btn regenerate-btn" title="重新生成" @click="regenerateLastAssistant">
                <RefreshCw :size="14" :stroke-width="1.5" />
                <span>重新生成</span>
              </button>
            </div>
            <div v-if="msg.references && parseRefs(msg.references).length" class="msg-refs">
              <div class="refs-toggle" @click="toggleRefs(msg.id)">
                <FileText :size="14" :stroke-width="1.5" />
                <span>引用来源 ({{ parseRefs(msg.references).length }})</span>
                <ChevronDown :size="12" :stroke-width="1.5" :class="{ 'chevron-open': expandedRefs[msg.id] }" class="chevron-icon" />
              </div>
              <div v-show="expandedRefs[msg.id]" class="refs-list">
                <div v-for="(ref, ri) in parseRefs(msg.references)" :key="ri" class="ref-card" @click="expandedRefIdx === `${msg.id}-${ri}` ? (expandedRefIdx = '') : (expandedRefIdx = `${msg.id}-${ri}`)">
                  <div class="ref-card-header">
                    <span class="ref-doc-name">{{ ref.doc_name }}</span>
                    <span v-if="ref.chunk_index !== undefined" class="ref-chunk">#{{ ref.chunk_index }}</span>
                    <span v-if="ref.score" class="ref-score">{{ (ref.score * 100).toFixed(0) }}%</span>
                  </div>
                  <div class="ref-card-body" :class="{ 'ref-expanded': expandedRefIdx === `${msg.id}-${ri}` }">
                    {{ ref.content }}
                  </div>
                </div>
              </div>
            </div>
            <!-- Memory hits -->
            <div v-if="msg._memories?.length" class="msg-memories">
              <div class="memories-toggle" @click="expandedMemories[msg.id] = !expandedMemories[msg.id]">
                <Brain :size="14" :stroke-width="1.5" />
                <span>关联记忆 ({{ msg._memories.length }})</span>
                <ChevronDown :size="12" :stroke-width="1.5" :class="{ 'chevron-open': expandedMemories[msg.id] }" class="chevron-icon" />
              </div>
              <div v-show="expandedMemories[msg.id]" class="memories-list">
                <div v-for="(mem, mi) in msg._memories" :key="mi" class="memory-chip">
                  <el-tag size="small" :type="mem.category === 'preference' ? 'success' : mem.category === 'insight' ? 'warning' : 'info'">
                    {{ ({ preference: '偏好', fact: '事实', insight: '经验' } as Record<string, string>)[mem.category] || '记忆' }}
                  </el-tag>
                  <span class="memory-text">{{ mem.content }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="streamSqlData" class="message assistant">
          <div class="msg-avatar"><BotIcon :size="16" :stroke-width="1.5" /></div>
          <div class="msg-content">
            <div class="sql-result-block">
              <div class="sql-result-header">
                <el-tag size="small" type="warning">SQL</el-tag>
                <code class="sql-code">{{ streamSqlData.sql }}</code>
              </div>
              <div v-if="streamSqlData.rows && streamSqlData.rows.length" class="sql-result-table-wrap">
                <el-table :data="streamSqlData.rows" size="small" stripe max-height="300" style="width: 100%">
                  <el-table-column v-for="col in streamSqlData.columns" :key="col" :prop="col" :label="col" min-width="120" show-overflow-tooltip />
                </el-table>
                <div class="sql-row-count">{{ streamSqlData.row_count }} 行结果</div>
              </div>
              <div v-else class="sql-empty">查询结果为空</div>
            </div>
          </div>
        </div>

        <!-- Agent tool calls display (live during streaming) -->
        <div v-if="streaming && agentToolCalls.length" class="message assistant">
          <div class="msg-avatar"><BotIcon :size="16" :stroke-width="1.5" /></div>
          <div class="msg-content">
            <div class="agent-tool-calls">
              <div v-for="tc in agentToolCalls" :key="tc.id" class="tool-call-item" :class="{ 'tool-success': tc.result?.success, 'tool-error': tc.result && !tc.result.success }">
                <div class="tool-call-header">
                  <Wrench :size="13" :stroke-width="1.5" />
                  <span class="tool-name">{{ toolDisplayName(tc.name) }}</span>
                  <Loader2 v-if="!tc.result" :size="12" :stroke-width="1.5" class="status-spin" />
                  <CheckCircle2 v-else-if="tc.result.success" :size="13" :stroke-width="1.5" class="tool-ok" />
                  <XCircle v-else :size="13" :stroke-width="1.5" class="tool-fail" />
                </div>
                <div v-if="tc.args" class="tool-call-args" @click="tc._expanded = !tc._expanded">
                  <code>{{ tc.args }}</code>
                </div>
                <div v-if="tc.result" class="tool-call-result">
                  <div v-if="tc.result.display_type === 'table' && tc.result.data?.columns" class="tool-table-wrap">
                    <div class="tool-sql-badge"><el-tag size="small" type="warning">SQL</el-tag> <code>{{ tc.result.data.sql }}</code></div>
                    <el-table :data="tc.result.data.rows" size="small" stripe max-height="200" style="width: 100%">
                      <el-table-column v-for="col in tc.result.data.columns" :key="col" :prop="col" :label="col" min-width="100" show-overflow-tooltip />
                    </el-table>
                    <div class="tool-row-count">{{ tc.result.data.row_count }} 行</div>
                  </div>
                  <div v-else-if="tc.result.display_type === 'references' && tc.result.data?.references" class="tool-refs-summary">
                    <FileText :size="12" :stroke-width="1.5" />
                    <span>检索到 {{ tc.result.data.count }} 条相关文档</span>
                  </div>
                  <div v-else-if="!tc.result.success" class="tool-error-msg">{{ tc.result.error }}</div>
                  <div v-else-if="typeof tc.result.data === 'string'" class="tool-text-result">{{ tc.result.data }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="streaming && multiAgentEvents.length" class="message assistant">
          <div class="msg-avatar"><BotIcon :size="16" :stroke-width="1.5" /></div>
          <div class="msg-content">
            <div class="multi-agent-events">
              <div v-for="ev in multiAgentEvents" :key="ev.id" class="multi-agent-item">
                <div class="tool-call-header">
                  <BotIcon :size="13" :stroke-width="1.5" />
                  <span class="tool-name">{{ ev.agent_name }}</span>
                  <Loader2 v-if="ev.type === 'dispatch'" :size="12" :stroke-width="1.5" class="status-spin" />
                  <CheckCircle2 v-else :size="13" :stroke-width="1.5" class="tool-ok" />
                </div>
                <div v-if="ev.sub_query" class="tool-call-args"><code>{{ ev.sub_query }}</code></div>
                <div v-if="ev.answer" class="tool-text-result">{{ ev.answer }}</div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="streaming" class="message assistant">
          <div class="msg-avatar"><BotIcon :size="16" :stroke-width="1.5" /></div>
          <div class="msg-content">
            <div v-if="streamMode" class="mode-badge">
              <el-tag size="small" :type="streamMode === 'sql' ? 'warning' : streamMode === 'hybrid' ? 'success' : streamMode === 'agent' ? 'danger' : 'info'">{{ modeLabel(streamMode) }}</el-tag>
            </div>
            <div v-if="streamStatus && !streamContent" class="stream-status">
              <Loader2 :size="14" :stroke-width="1.5" class="status-spin" />
              <span>{{ streamStatus }}</span>
              <span v-if="streamElapsed > 0" class="elapsed-badge">{{ streamElapsed }}s</span>
              <span v-if="streamElapsed >= 10 && streamElapsed < 30" class="slow-hint">模型响应较慢，请耐心等待...</span>
              <span v-if="streamElapsed >= 30" class="slow-hint timeout-warn">等待时间较长，可点击取消后重试或切换模型</span>
            </div>
            <div v-if="streamRetrievalWarning" class="retrieval-warning">
              <el-alert :title="streamRetrievalWarning" type="warning" :closable="false" show-icon />
            </div>
            <div class="msg-text md-body" v-html="renderMd(streamContent)"></div>
            <span class="cursor-blink">|</span>
          </div>
        </div>
      </div>

      <div class="input-area">
        <div v-if="slashMenuVisible && slashFilteredSkills.length" class="slash-menu">
          <div class="slash-menu-header">选择技能</div>
          <div
            v-for="(sk, idx) in slashFilteredSkills"
            :key="sk.id"
            class="slash-menu-item"
            :class="{ active: slashActiveIndex === idx }"
            @mousedown.prevent="selectSlashSkill(sk)"
            @mouseenter="slashActiveIndex = idx"
          >
            <Wrench :size="14" :stroke-width="1.5" class="slash-icon" />
            <div class="slash-item-info">
              <span class="slash-item-name">{{ sk.name }}</span>
              <span class="slash-item-desc">{{ sk.description || sk.category }}</span>
            </div>
          </div>
        </div>
        <div v-if="attachedFile" class="attached-file-bar">
          <Paperclip :size="14" :stroke-width="1.5" />
          <span class="attached-name">{{ attachedFile.name }} ({{ (attachedFile.size / 1024).toFixed(0) }}KB)</span>
          <el-button link size="small" @click="attachedFile = null"><XIcon :size="14" :stroke-width="1.5" /></el-button>
        </div>
        <el-input
          v-model="question"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 6 }"
          placeholder="输入你的问题... (Enter 发送, Shift+Enter 换行, / 唤起技能)"
          @keydown.enter.exact.prevent="handleEnterKey"
          @keydown.escape="handleEscKey"
          @keydown.up.prevent="handleSlashArrowUp"
          @keydown.down.prevent="handleSlashArrowDown"
          @input="handleQuestionInput"
        />
        <el-tooltip content="上传文件分析" placement="top">
          <el-upload :show-file-list="false" :auto-upload="false" :on-change="handleChatFileSelect" accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.md,.json,.pptx">
            <el-button circle size="large" class="attach-btn">
              <Paperclip :size="16" :stroke-width="1.5" />
            </el-button>
          </el-upload>
        </el-tooltip>
        <el-tooltip :content="isRecording ? '停止录音' : '语音输入'" placement="top">
          <el-button
            :type="isRecording ? 'danger' : 'default'"
            circle
            size="large"
            @click="toggleVoiceInput"
            class="voice-btn"
          >
            <Mic :size="16" :stroke-width="2" />
          </el-button>
        </el-tooltip>
        <el-button
          v-if="!streaming"
          type="primary"
          :icon="SendHorizonal"
          circle
          size="large"
          @click="sendMessage"
          :disabled="!question.trim()"
          class="send-btn"
        />
        <el-button
          v-else
          type="danger"
          circle
          size="large"
          @click="cancelStream"
          class="send-btn"
        >
          <Square :size="16" :stroke-width="2" />
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onActivated, onDeactivated, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Sparkles, ArrowRight, MessageSquareText, TriangleAlert,
  User as UserIcon, Bot as BotIcon, Copy, ThumbsUp, ThumbsDown,
  RotateCw, FileText, ChevronDown, Loader2, SendHorizonal, Square,
 
  Wrench, CheckCircle2, XCircle, Edit2, RefreshCw, Mic, Volume2,
  Undo2, Brain, Paperclip, X as XIcon,
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { renderMarkdown } from '../../utils/markdown'
import { listConversations, searchConversations, getConversationMessages, deleteConversation, batchDeleteConversations, renameConversation, streamChat, messageFeedback, regenerateMessage, editMessage, recallMessage, exportConversation, togglePinConversation } from '../../api/chat'
import request, { getValidToken } from '../../utils/request'
import { API_V1 } from '../../utils/apiBase'
import { listKnowledgeBases } from '../../api/knowledgeBase'
import { listModels } from '../../api/models'
import { listRemoteSharedKbs, streamRemoteChat } from '../../api/remoteRelay'
import ChatConfigBar from '../../components/chat/ChatConfigBar.vue'
import ChatConversationSidebar from '../../components/chat/ChatConversationSidebar.vue'

const route = useRoute()
const messagesRef = ref<HTMLElement>()

const conversations = ref<any[]>([])
const convSearch = ref('')
const batchMode = ref(false)
const batchSelected = ref<Set<number>>(new Set())
const convPage = ref(1)
const convHasMore = ref(false)
const convLoadingMore = ref(false)
const searchResults = ref<any[]>([])
const searchLoading = ref(false)
const isSearchMode = computed(() => convSearch.value.trim().length > 0)
let searchTimer: ReturnType<typeof setTimeout> | null = null
const filteredConversations = computed(() => {
  if (isSearchMode.value) return searchResults.value
  return conversations.value
})
const currentConvId = ref<number | null>(null)
const currentRemoteConvId = ref<number | null>(null)
const messages = ref<any[]>([])
const question = ref('')
const streaming = ref(false)
const isRecording = ref(false)
const attachedFile = ref<File | null>(null)
let recognition: any = null
const mobileSidebarOpen = ref(false)
const streamContent = ref('')
const messagesLoading = ref(false)
let abortController: AbortController | null = null

const kbList = ref<any[]>([])
const llmModels = ref<any[]>([])

const chatConfig = reactive({
  kb_id: null as number | null,
  llm_model_id: null as number | null,
  top_k: 5,
  score_threshold: 0,
  enable_rewrite: true,
  chat_mode: 'auto' as string,
  context_strategy: 'sliding_window' as string,
  prompt_template_id: null as number | null,
})
let _prevKbId: number | null = null
const streamMode = ref('')
const streamStatus = ref('')
const streamRetrievalWarning = ref('')
const lastStreamTokens = ref<{ input: number; output: number } | null>(null)
const streamSqlData = ref<any>(null)
const streamElapsed = ref(0)
let streamTimer: ReturnType<typeof setInterval> | null = null
const agentToolCalls = ref<any[]>([])
const multiAgentEvents = ref<any[]>([])

function toolDisplayName(name: string) {
  const m: Record<string, string> = {
    knowledge_search: '📚 知识检索',
    sql_query: '🗄️ 数据库查询',
    calculator: '🧮 计算器',
    current_time: '🕐 当前时间',
  }
  return m[name] || name
}
const welcomeMessage = ref('')
const suggestedQuestions = ref<string[]>([])

function selectedKb() {
  return kbList.value.find((k: any) => k.id === chatConfig.kb_id)
}

const chatQuotaInfo = ref<any>(null)
const chatTemplateOptions = ref<{ id: number; name: string }[]>([])

async function loadChatQuota() {
  try { chatQuotaInfo.value = await request.get('/quota/me', { _silentError: true } as any) } catch (e: any) {
    console.warn('[Chat] 加载用量配额失败:', e?.message || e)
  }
}

async function loadChatTemplates() {
  try {
    const { listTemplates: _list } = await import('../../api/promptTemplates')
    chatTemplateOptions.value = (await _list()).map(t => ({ id: t.id, name: t.name }))
  } catch {}
}

const chatModeLabels: Record<string, string> = {
  auto: '自动（根据问题智能选择检索或 SQL）',
  rag: '知识检索（基于文档语义）',
  sql: '数据库查询（自然语言转 SQL）',
  hybrid: '混合（文档+数据库综合）',
  agent: '智能体（可调用工具）',
  multi_agent: '多Agent（跨知识库协作）',
}
const chatModeLabel = computed(() => chatModeLabels[chatConfig.chat_mode] || chatConfig.chat_mode)

function renderMd(text: string) {
  if (!text) return ''
  return renderMarkdown(text)
}


// Debounced server-side conversation search
watch(convSearch, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  const q = val.trim()
  if (!q) {
    searchResults.value = []
    searchLoading.value = false
    return
  }
  searchLoading.value = true
  searchTimer = setTimeout(async () => {
    try {
      const res: any = await searchConversations(q)
      searchResults.value = (res?.items || []).map((item: any) => ({
        ...item,
        _snippets: item.matching_messages || [],
      }))
    } catch {
      searchResults.value = []
    } finally {
      searchLoading.value = false
    }
  }, 350)
})

async function loadInitData() {
  const [convsRes, kbsRes, remoteKbsRes, modelsRes] = await Promise.allSettled([
    listConversations(),
    listKnowledgeBases(),
    listRemoteSharedKbs(),
    listModels('llm'),
  ])
  if (convsRes.status === 'fulfilled') {
    const data = convsRes.value as any
    conversations.value = data?.items || data
    convPage.value = 1
    convHasMore.value = !!(data?.total && data.total > (data?.items?.length || 0))
  }
  const localKbs = kbsRes.status === 'fulfilled' ? (kbsRes.value as any) : []
  const remoteKbs = remoteKbsRes.status === 'fulfilled'
    ? ((remoteKbsRes.value as any) || []).map((kb: any) => ({
      ...kb,
      id: -Number(kb.remote_kb_id || kb.id),
      name: `[远程] ${kb.workspace_name ? `${kb.workspace_name} / ` : ''}${kb.name}${kb.host_online ? '' : '（离线）'}`,
      is_remote: true,
      remote_kb_id: Number(kb.remote_kb_id || kb.id),
    }))
    : []
  kbList.value = [...localKbs, ...remoteKbs]
  if (modelsRes.status === 'fulfilled') {
    llmModels.value = modelsRes.value as any
    const models = llmModels.value
    if (!chatConfig.llm_model_id && models.length) {
      const defaultModel = models.find((m: any) => m.is_default)
      chatConfig.llm_model_id = defaultModel?.id || models[0].id
    }
  }

  // 自动选择知识库：单知识库场景自动选中
  if (kbsRes.status === 'fulfilled') {
    const kbs = kbList.value
    if (!chatConfig.kb_id && kbs.length === 1) {
      chatConfig.kb_id = kbs[0].id
      _prevKbId = kbs[0].id
      onKbChange(kbs[0].id)
    }
  }

  if (route.query.kb_id && !chatConfig.kb_id) {
    chatConfig.kb_id = Number(route.query.kb_id)
    _prevKbId = chatConfig.kb_id
    onKbChange(chatConfig.kb_id)
  }
}

async function loadMoreConvs() {
  convLoadingMore.value = true
  try {
    const nextPage = convPage.value + 1
    const res: any = await listConversations(nextPage)
    const items = res?.items || res
    if (items?.length) {
      conversations.value = [...conversations.value, ...items]
      convPage.value = nextPage
      convHasMore.value = conversations.value.length < (res?.total || 0)
    } else {
      convHasMore.value = false
    }
  } finally {
    convLoadingMore.value = false
  }
}

function startNewChat() {
  currentConvId.value = null
  currentRemoteConvId.value = null
  messages.value = []
  streamContent.value = ''
}

async function loadConversation(convId: number) {
  currentConvId.value = convId
  messagesLoading.value = true
  try {
    const res: any = await getConversationMessages(convId)
    messages.value = res
    const conv = conversations.value.find((c: any) => c.id === convId)
    if (conv) {
      chatConfig.kb_id = conv.kb_id
      _prevKbId = conv.kb_id
      if (conv.llm_model_id) chatConfig.llm_model_id = conv.llm_model_id
    }
    await nextTick()
    scrollToBottom()
  } catch {
    ElMessage.error('加载对话消息失败')
  } finally {
    messagesLoading.value = false
  }
}

function handleChatFileSelect(uploadFile: any) {
  attachedFile.value = uploadFile.raw || uploadFile
}

// ─── 斜杠命令 ───
const slashSkills = ref<any[]>([])
const slashMenuVisible = ref(false)
const slashActiveIndex = ref(0)
const slashQuery = ref('')
let slashSkillsLoaded = false

const slashFilteredSkills = computed(() => {
  const q = slashQuery.value.toLowerCase()
  if (!q) return slashSkills.value.slice(0, 10)
  return slashSkills.value
    .filter((s: any) => s.name.toLowerCase().includes(q) || (s.slug || '').toLowerCase().includes(q))
    .slice(0, 10)
})

async function loadSlashSkills() {
  if (slashSkillsLoaded) return
  try {
    const res: any = await request.get('/skills/installed')
    slashSkills.value = (res.items || res.data || res || [])
      .filter((s: any) => s.is_active !== false)
    slashSkillsLoaded = true
  } catch { /* ignore */ }
}

function handleQuestionInput() {
  const val = question.value
  if (val.startsWith('/')) {
    const rest = val.slice(1).split(/\s/, 1)[0] ?? ''
    slashQuery.value = rest
    if (!slashMenuVisible.value) {
      loadSlashSkills()
      slashMenuVisible.value = true
      slashActiveIndex.value = 0
    }
  } else {
    slashMenuVisible.value = false
  }
}

function selectSlashSkill(sk: any) {
  question.value = `/${sk.name} `
  slashMenuVisible.value = false
  slashQuery.value = ''
}

function handleEnterKey() {
  if (slashMenuVisible.value && slashFilteredSkills.value.length) {
    selectSlashSkill(slashFilteredSkills.value[slashActiveIndex.value])
    return
  }
  sendMessage()
}

function handleEscKey() {
  if (slashMenuVisible.value) {
    slashMenuVisible.value = false
    return
  }
  cancelStream()
}

function handleSlashArrowUp() {
  if (!slashMenuVisible.value) return
  slashActiveIndex.value = Math.max(0, slashActiveIndex.value - 1)
}

function handleSlashArrowDown() {
  if (!slashMenuVisible.value) return
  slashActiveIndex.value = Math.min(slashFilteredSkills.value.length - 1, slashActiveIndex.value + 1)
}

async function sendMessage() {
  if (!question.value.trim() && !attachedFile.value) return
  if (streaming.value) {
    cancelStream()
    await new Promise(r => setTimeout(r, 300))
  }
  const kb = selectedKb()
  const remoteChat = !!kb?.is_remote
  if (!chatConfig.kb_id || (!remoteChat && !chatConfig.llm_model_id)) {
    ElMessage.warning(remoteChat ? '请先选择知识库' : '请先选择知识库和 LLM 模型')
    return
  }
  if (remoteChat && kb?.host_online === false) {
    ElMessage.warning('知识库主机离线')
    return
  }

  let q = question.value.trim()

  if (attachedFile.value) {
    try {
      const { analyzeFile } = await import('../../api/chat')
      const res: any = await analyzeFile(attachedFile.value)
      const fileContent = res.data?.content || res.content || ''
      if (fileContent) {
        q = q ? `${q}\n\n[附件: ${attachedFile.value.name}]\n${fileContent}` : `请分析以下文件内容:\n\n[附件: ${attachedFile.value.name}]\n${fileContent}`
      } else {
        ElMessage.warning('文件内容提取失败，仅发送文本消息')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.detail || '文件上传失败')
      return
    } finally {
      attachedFile.value = null
    }
  }

  if (!q) return
  question.value = ''
  messages.value.push({ role: 'user', content: q })
  streaming.value = true
  streamContent.value = ''
  streamMode.value = ''
  streamStatus.value = ''
  streamRetrievalWarning.value = ''
  streamSqlData.value = null
  streamElapsed.value = 0
  agentToolCalls.value = []
  multiAgentEvents.value = []
  abortController = new AbortController()
  const t0 = Date.now()
  streamTimer = setInterval(() => { streamElapsed.value = Math.round((Date.now() - t0) / 1000) }, 1000)

  await nextTick()
  scrollToBottom()

  try {
    const gen = remoteChat
      ? streamRemoteChat(
        {
          conversation_id: currentRemoteConvId.value || undefined,
          remote_kb_id: Number(kb.remote_kb_id),
          question: q,
          top_k: chatConfig.top_k,
          score_threshold: chatConfig.score_threshold > 0 ? chatConfig.score_threshold : undefined,
          enable_rewrite: chatConfig.enable_rewrite,
          chat_mode: chatConfig.chat_mode,
          context_strategy: chatConfig.context_strategy,
          prompt_template_id: chatConfig.prompt_template_id ?? undefined,
        },
        abortController.signal
      )
      : streamChat(
        {
          conversation_id: currentConvId.value || undefined,
          kb_id: chatConfig.kb_id!,
          llm_model_id: chatConfig.llm_model_id!,
          question: q,
          top_k: chatConfig.top_k,
          score_threshold: chatConfig.score_threshold > 0 ? chatConfig.score_threshold : undefined,
          enable_rewrite: chatConfig.enable_rewrite,
          chat_mode: chatConfig.chat_mode,
          context_strategy: chatConfig.context_strategy,
          prompt_template_id: chatConfig.prompt_template_id ?? undefined,
        },
        abortController.signal
      )

    let refs: any = null
    let hitMemories: any[] = []
    for await (const chunk of gen) {
      if (chunk.type === 'content') {
        if (streamStatus.value) streamStatus.value = ''
        streamContent.value += chunk.data
        scrollToBottom()
      } else if (chunk.type === 'memories') {
        hitMemories = chunk.data || []
      } else if (chunk.type === 'references') {
        if (remoteChat) currentRemoteConvId.value = chunk.conversation_id
        else currentConvId.value = chunk.conversation_id
        refs = chunk.data
      } else if (chunk.type === 'done') {
        if (remoteChat) currentRemoteConvId.value = chunk.conversation_id
        else currentConvId.value = chunk.conversation_id
        // Attach token usage to the last assistant message
        if (chunk.data?.output_tokens) {
          lastStreamTokens.value = {
            input: chunk.data.input_tokens || 0,
            output: chunk.data.output_tokens || 0,
          }
        }
      } else if (chunk.type === 'error') {
        ElMessage.error(chunk.data)
      } else if (chunk.type === 'mode') {
        streamMode.value = chunk.data
      } else if (chunk.type === 'status') {
        streamStatus.value = chunk.data
      } else if (chunk.type === 'sql') {
        streamSqlData.value = chunk.data
        scrollToBottom()
      } else if (chunk.type === 'retrieval_info') {
        // Show retrieval status warning to user
        const info = chunk.data
        if (info.status === 'filtered_all') {
          ElMessage.warning({ message: info.message, duration: 8000 })
        } else if (info.status === 'no_results') {
          streamRetrievalWarning.value = info.message
        } else if (info.status === 'skipped') {
          ElMessage.warning({ message: info.message, duration: 5000 })
        }
      } else if (chunk.type === 'sql_error') {
        ElMessage.warning(chunk.data)
      } else if (chunk.type === 'tool_call') {
        // Agent: a tool is being called
        agentToolCalls.value.push({
          id: chunk.data.id,
          name: chunk.data.name,
          args: chunk.data.arguments,
          result: null,
          _expanded: false,
        })
        scrollToBottom()
      } else if (chunk.type === 'tool_result') {
        // Agent: tool result received
        const tc = agentToolCalls.value.find((t: any) => t.id === chunk.data.id)
        if (tc) tc.result = chunk.data.result
        scrollToBottom()
      } else if (chunk.type === 'agent_dispatch') {
        multiAgentEvents.value.push({
          id: `dispatch-${multiAgentEvents.value.length + 1}`,
          type: 'dispatch',
          agent_name: chunk.data.agent_name,
          sub_query: chunk.data.sub_query,
        })
        scrollToBottom()
      } else if (chunk.type === 'agent_result') {
        multiAgentEvents.value.push({
          id: `result-${multiAgentEvents.value.length + 1}`,
          type: 'result',
          agent_name: chunk.data.agent_name,
          answer: chunk.data.answer,
          references: chunk.data.references,
        })
        scrollToBottom()
      } else if (chunk.type === 'agent_complete') {
        // Agent loop finished
      }
    }

    messages.value.push({
      role: 'assistant',
      content: streamContent.value,
      references: refs ? JSON.stringify(refs) : null,
      _agentToolCalls: agentToolCalls.value.length ? [...agentToolCalls.value] : undefined,
      _multiAgentEvents: multiAgentEvents.value.length ? [...multiAgentEvents.value] : undefined,
      _memories: hitMemories.length ? hitMemories : undefined,
    })

    // Refresh messages with server-side IDs, preserving local-only fields
    if (!remoteChat && currentConvId.value) {
      try {
        const savedToolCalls = agentToolCalls.value.length ? [...agentToolCalls.value] : undefined
        const savedMultiAgentEvents = multiAgentEvents.value.length ? [...multiAgentEvents.value] : undefined
        const savedMemories = hitMemories.length ? [...hitMemories] : undefined
        const msgRes: any = await getConversationMessages(currentConvId.value)
        if (msgRes) {
          const lastAssistant = [...msgRes].reverse().find((m: any) => m.role === 'assistant')
          if (lastAssistant) {
            if (savedToolCalls?.length) lastAssistant._agentToolCalls = savedToolCalls
            if (savedMultiAgentEvents?.length) lastAssistant._multiAgentEvents = savedMultiAgentEvents
            if (savedMemories?.length) lastAssistant._memories = savedMemories
          }
          messages.value = msgRes
        }
      } catch { /* keep local messages */ }
    }
    // Lightweight: only refresh conversation list if it's a new conversation
    if (!remoteChat && !conversations.value.some((c: any) => c.id === currentConvId.value)) {
      try {
        const convRes: any = await listConversations()
        conversations.value = convRes?.items || convRes
      } catch {}
    } else if (!remoteChat) {
      // Update title of existing conversation in place
      const conv = conversations.value.find((c: any) => c.id === currentConvId.value)
      if (conv && !conv.title) conv.title = q.substring(0, 30)
    }
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      ElMessage.error('对话出错：' + (e.message || '未知错误'))
    }
    if (streamContent.value) {
      messages.value.push({
        role: 'assistant',
        content: streamContent.value,
        token_count: lastStreamTokens.value?.output || 0,
        input_tokens: lastStreamTokens.value?.input || 0,
      })
      lastStreamTokens.value = null
    }
  } finally {
    streaming.value = false
    streamContent.value = ''
    streamMode.value = ''
    streamSqlData.value = null
    agentToolCalls.value = []
    multiAgentEvents.value = []
    abortController = null
    if (streamTimer) { clearInterval(streamTimer); streamTimer = null }
    streamElapsed.value = 0
    // 流式结束后自动聚焦输入框
    nextTick(() => {
      const textarea = document.querySelector('.input-area textarea') as HTMLTextAreaElement
      textarea?.focus()
    })
  }
}

function modeLabel(mode: string) {
  const m: Record<string, string> = { rag: '知识检索', sql: '数据库查询', hybrid: '混合模式', agent: '🤖 智能体', multi_agent: '🔗 多Agent' }
  return m[mode] || mode
}

function cancelStream() {
  abortController?.abort()
}

function toggleVoiceInput() {
  if (isRecording.value) {
    recognition?.stop()
    isRecording.value = false
    return
  }
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) {
    ElMessage.warning('当前浏览器不支持语音识别，请使用 Chrome 浏览器')
    return
  }
  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.continuous = false
  recognition.interimResults = true
  recognition.onresult = (event: any) => {
    let transcript = ''
    for (let i = 0; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript
    }
    question.value = transcript
  }
  recognition.onerror = (event: any) => {
    if (event.error !== 'aborted') {
      ElMessage.error('语音识别出错: ' + event.error)
    }
    isRecording.value = false
  }
  recognition.onend = () => { isRecording.value = false }
  recognition.start()
  isRecording.value = true
  ElMessage.info('请说话...')
}

async function playTTS(text: string) {
  try {
    const token = await getValidToken()
    const resp = await fetch(`${API_V1}/tts/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ text: text.substring(0, 5000) }),
    })
    if (!resp.ok) throw new Error('TTS 请求失败')
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.play()
    audio.onended = () => URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error('语音播放失败')
  }
}

async function renameConv(conv: any) {
  try {
    const { value } = await ElMessageBox.prompt('输入新标题', '重命名对话', {
      inputValue: conv.title || '',
      inputPattern: /\S+/,
      inputErrorMessage: '标题不能为空',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await renameConversation(conv.id, value.trim())
    conv.title = value.trim()
    ElMessage.success('标题已更新')
  } catch { /* cancelled */ }
}

function toggleBatchMode() {
  batchMode.value = !batchMode.value
  batchSelected.value = new Set()
}

function toggleBatchItem(id: number) {
  const s = new Set(batchSelected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  batchSelected.value = s
}

function toggleSelectAll(checked: boolean) {
  if (checked) {
    batchSelected.value = new Set(filteredConversations.value.map((c: any) => c.id))
  } else {
    batchSelected.value = new Set()
  }
}

async function batchDelete() {
  const count = batchSelected.value.size
  if (!count) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${count} 个对话？此操作不可恢复。`, '批量删除', { type: 'warning' })
  } catch { return }
  try {
    await batchDeleteConversations([...batchSelected.value])
    ElMessage.success(`已删除 ${count} 个对话`)
    if (currentConvId.value && batchSelected.value.has(currentConvId.value)) startNewChat()
    batchSelected.value = new Set()
    batchMode.value = false
    const res: any = await listConversations()
    conversations.value = res?.items || res
  } catch { /* interceptor handles */ }
}

async function removeConv(id: number) {
  const conv = conversations.value.find((c: any) => c.id === id)
  const title = conv?.title ? `「${conv.title}」` : '该对话'
  try {
    await ElMessageBox.confirm(`确定删除${title}？相关消息将被清除。`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteConversation(id)
    if (currentConvId.value === id) startNewChat()
    const res: any = await listConversations()
    conversations.value = res?.items || res
  } catch { /* interceptor handles */ }
}

async function pinConv(id: number) {
  try {
    const res: any = await togglePinConversation(id)
    const conv = conversations.value.find((c: any) => c.id === id)
    if (conv) conv.is_pinned = res.is_pinned
    // Re-sort: pinned first, then by created_at desc
    conversations.value.sort((a: any, b: any) => {
      if (a.is_pinned !== b.is_pinned) return b.is_pinned ? 1 : -1
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
  } catch { /* interceptor handles */ }
}

let _scrollRAF: number | null = null
function scrollToBottom() {
  if (_scrollRAF) return
  _scrollRAF = requestAnimationFrame(() => {
    _scrollRAF = null
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    ElMessageBox.alert(text, '复制失败，请手动选择复制', {
      confirmButtonText: '关闭',
      customStyle: { whiteSpace: 'pre-wrap', wordBreak: 'break-all' },
    })
  }
}

function truncate(text: string, len: number) {
  return text.length > len ? text.substring(0, len) + '...' : text
}

const expandedRefs = reactive<Record<number, boolean>>({})
const expandedRefIdx = ref('')
const expandedMemories = reactive<Record<number, boolean>>({})

// 撤回时限：2 分钟（与后端一致）
const RECALL_MAX_SECONDS = 120

function canRecallUserMessage(msg: any): boolean {
  if (!msg?.id || msg.role !== 'user') return false
  const created = msg.created_at
  if (!created) return false
  const t = new Date(created).getTime()
  return (Date.now() - t) / 1000 <= RECALL_MAX_SECONDS
}

async function recallUserMessage(msg: any) {
  if (!msg?.id) return
  try {
    const res = await recallMessage(msg.id)
    const content = (res as any)?.content ?? msg.content
    question.value = content
    // 从 messages 中移除该用户消息及紧随其后的助手消息
    const idx = messages.value.findIndex((m: any) => m.id === msg.id)
    if (idx >= 0) {
      const toRemove: number[] = [idx]
      if (messages.value[idx + 1]?.role === 'assistant') toRemove.push(idx + 1)
      messages.value = messages.value.filter((_: any, i: number) => !toRemove.includes(i))
    }
    ElMessage.success('已撤回')
    nextTick(() => {
      const textarea = document.querySelector('.input-area textarea') as HTMLTextAreaElement
      textarea?.focus()
    })
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '撤回失败')
  }
}

// Task 1: Edit user message & regenerate last assistant
async function editUserMessage(msg: any) {
  // Prompt user to edit the message content
  try {
    const { value: newContent } = await ElMessageBox.prompt(
      '编辑后将删除此消息及之后的所有对话，并用新内容重新生成回复。',
      '编辑消息',
      {
        inputValue: msg.content,
        inputType: 'textarea',
        confirmButtonText: '编辑并重新生成',
        cancelButtonText: '取消',
        inputValidator: (v: string) => (v?.trim() ? true : '内容不能为空'),
      },
    )
    if (!newContent?.trim() || newContent.trim() === msg.content) return

    // Remove this message and all after it from local state
    const idx = messages.value.findIndex((m: any) => m.id === msg.id)
    if (idx >= 0) messages.value.splice(idx)

    // Set question and trigger send (backend stream_chat handles persistence)
    question.value = newContent.trim()
    await sendMessage()
  } catch {
    // User cancelled
  }
}

function isLastAssistantMsg(idx: number) {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'assistant') return i === idx
  }
  return false
}

function regenerateLastAssistant() {
  const lastAssistant = [...messages.value].reverse().find((m: any) => m.role === 'assistant')
  if (lastAssistant?.id) {
    regenerateMsg(lastAssistant.id)
  }
}

// Task 3: Long message collapse/expand
const expandedMsgs = ref<Set<number>>(new Set())
const msgHeights = ref<Map<number, number>>(new Map())
const MSG_COLLAPSE_THRESHOLD = 500

function onMsgRendered(el: HTMLElement | null, idx: number) {
  if (!el) return
  nextTick(() => {
    requestAnimationFrame(() => {
      msgHeights.value.set(idx, el.scrollHeight)
    })
  })
}

function needsCollapse(idx: number) {
  const h = msgHeights.value.get(idx)
  return h !== undefined && h > MSG_COLLAPSE_THRESHOLD
}

function msgCollapseStyle(idx: number) {
  if (needsCollapse(idx) && !expandedMsgs.value.has(idx)) {
    return { maxHeight: MSG_COLLAPSE_THRESHOLD + 'px', overflow: 'hidden' }
  }
  return {}
}

function toggleExpand(idx: number) {
  const s = new Set(expandedMsgs.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedMsgs.value = s
}

function toggleRefs(msgId: number) {
  expandedRefs[msgId] = !expandedRefs[msgId]
}

function parseRefs(refs: string) {
  try {
    return JSON.parse(refs)
  } catch {
    return []
  }
}

async function onKbChange(kbId: number | null) {
  if (!kbId) {
    welcomeMessage.value = ''
    suggestedQuestions.value = []
    _prevKbId = null
    return
  }
  if (messages.value.length > 0 && currentConvId.value) {
    try {
      await ElMessageBox.confirm(
        '切换知识库后，当前对话的上下文将不再匹配。建议新建对话以获得最佳效果。',
        '切换知识库',
        { confirmButtonText: '新建对话', cancelButtonText: '继续使用', type: 'warning' }
      )
      startNewChat()
    } catch {
      chatConfig.kb_id = _prevKbId
      return
    }
  }
  _prevKbId = kbId
  const kb = kbList.value.find((k: any) => k.id === kbId)
  if (kb) {
    if (kb.is_remote) {
      welcomeMessage.value = kb.host_online === false ? '远程知识库主机当前离线' : `正在使用远程知识库：${kb.workspace_name || ''}`
      suggestedQuestions.value = []
      currentRemoteConvId.value = null
      return
    }
    welcomeMessage.value = kb.welcome_message || ''
    try {
      suggestedQuestions.value = kb.suggested_questions ? JSON.parse(kb.suggested_questions) : []
    } catch {
      suggestedQuestions.value = []
    }
  }
}

function askSuggested(q: string) {
  question.value = q
  sendMessage()
}

const feedbackReasonOptions = {
  like: [
    { value: 'accurate', label: '回答准确' },
    { value: 'helpful', label: '很有帮助' },
    { value: 'well_written', label: '表述清晰' },
    { value: 'creative', label: '富有创意' },
  ],
  dislike: [
    { value: 'inaccurate', label: '回答不准确' },
    { value: 'irrelevant', label: '答非所问' },
    { value: 'incomplete', label: '回答不完整' },
    { value: 'harmful', label: '内容不当' },
    { value: 'too_long', label: '过于冗长' },
  ],
}
const feedbackPopover = reactive({ msgId: null as number | null, type: '' })

function openFeedbackPopover(msgId: number, type: string) {
  const msg = messages.value.find((m: any) => m.id === msgId)
  if (msg?.feedback === type) {
    sendFeedback(msgId, type)
    return
  }
  feedbackPopover.msgId = msgId
  feedbackPopover.type = type
}

function closeFeedbackPopover() {
  feedbackPopover.msgId = null
  feedbackPopover.type = ''
}

async function sendFeedback(msgId: number, type: string, reason?: string) {
  if (!msgId) return
  const msg = messages.value.find((m: any) => m.id === msgId)
  const newFeedback = msg?.feedback === type ? null : type
  try {
    await messageFeedback(msgId, newFeedback, reason)
    if (msg) {
      msg.feedback = newFeedback
      msg.feedback_reason = newFeedback ? (reason || null) : null
    }
    closeFeedbackPopover()
  } catch {
    ElMessage.error('反馈提交失败')
  }
}

async function regenerateMsg(msgId: number) {
  if (!msgId || streaming.value) return
  const idx = messages.value.findIndex((m: any) => m.id === msgId)
  if (idx < 0) return

  messages.value.splice(idx, 1)
  streaming.value = true
  streamContent.value = ''
  streamMode.value = ''
  streamStatus.value = ''
  streamSqlData.value = null
  streamElapsed.value = 0
  agentToolCalls.value = []
  abortController = new AbortController()
  const t0 = Date.now()
  streamTimer = setInterval(() => { streamElapsed.value = Math.round((Date.now() - t0) / 1000) }, 1000)

  await nextTick()
  scrollToBottom()

  try {
    const token = await getValidToken()
    const response = await fetch(`${API_V1}/chat/messages/${msgId}/regenerate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      signal: abortController.signal,
    })
    if (response.status === 401) {
      const { forceLogout } = await import('../../utils/request')
      forceLogout('登录已过期，请重新登录')
      return
    }
    if (!response.ok || !response.body) throw new Error('请求失败')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let refs: any = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const chunk = JSON.parse(line)
          if (chunk.type === 'content') {
            if (streamStatus.value) streamStatus.value = ''
            streamContent.value += chunk.data
            scrollToBottom()
          } else if (chunk.type === 'references') {
            refs = chunk.data
            if (chunk.conversation_id) currentConvId.value = chunk.conversation_id
          } else if (chunk.type === 'done') {
            if (chunk.conversation_id) currentConvId.value = chunk.conversation_id
          } else if (chunk.type === 'error') {
            ElMessage.error(chunk.data)
          } else if (chunk.type === 'mode') {
            streamMode.value = chunk.data
          } else if (chunk.type === 'status') {
            streamStatus.value = chunk.data
          } else if (chunk.type === 'sql') {
            streamSqlData.value = chunk.data
            scrollToBottom()
          } else if (chunk.type === 'sql_error') {
            ElMessage.warning(chunk.data)
          } else if (chunk.type === 'tool_call') {
            agentToolCalls.value.push({
              id: chunk.data.id,
              name: chunk.data.name,
              args: chunk.data.arguments,
              result: null,
              _expanded: false,
            })
            scrollToBottom()
          } else if (chunk.type === 'tool_result') {
            const tc = agentToolCalls.value.find((t: any) => t.id === chunk.data.id)
            if (tc) tc.result = chunk.data.result
            scrollToBottom()
          } else if (chunk.type === 'agent_dispatch') {
            multiAgentEvents.value.push({
              id: `dispatch-${multiAgentEvents.value.length + 1}`,
              type: 'dispatch',
              agent_name: chunk.data.agent_name,
              sub_query: chunk.data.sub_query,
            })
            scrollToBottom()
          } else if (chunk.type === 'agent_result') {
            multiAgentEvents.value.push({
              id: `result-${multiAgentEvents.value.length + 1}`,
              type: 'result',
              agent_name: chunk.data.agent_name,
              answer: chunk.data.answer,
              references: chunk.data.references,
            })
            scrollToBottom()
          } else if (chunk.type === 'agent_complete') {
            // Agent loop finished
          }
        } catch { /* skip malformed lines */ }
      }
    }

    // Flush any remaining data in buffer
    if (buffer.trim()) {
      try {
        const chunk = JSON.parse(buffer)
        if (chunk.type === 'content') {
          streamContent.value += chunk.data
        } else if (chunk.type === 'references') {
          refs = chunk.data
          if (chunk.conversation_id) currentConvId.value = chunk.conversation_id
        } else if (chunk.type === 'done') {
          if (chunk.conversation_id) currentConvId.value = chunk.conversation_id
        }
      } catch { /* skip */ }
    }

    messages.value.push({
      role: 'assistant',
      content: streamContent.value,
      references: refs ? JSON.stringify(refs) : null,
      _agentToolCalls: agentToolCalls.value.length ? [...agentToolCalls.value] : undefined,
      _multiAgentEvents: multiAgentEvents.value.length ? [...multiAgentEvents.value] : undefined,
    })

    if (currentConvId.value) {
      const savedToolCalls = agentToolCalls.value.length ? [...agentToolCalls.value] : undefined
      const savedMultiAgentEvents = multiAgentEvents.value.length ? [...multiAgentEvents.value] : undefined
      const [convRes, msgRes]: any = await Promise.allSettled([
        listConversations(),
        getConversationMessages(currentConvId.value),
      ])
      if (convRes.status === 'fulfilled') conversations.value = (convRes.value as any)?.items || convRes.value
      if (msgRes.status === 'fulfilled' && msgRes.value) {
        if (savedToolCalls?.length) {
          const lastAssistant = [...msgRes.value].reverse().find((m: any) => m.role === 'assistant')
          if (lastAssistant) lastAssistant._agentToolCalls = savedToolCalls
        }
        if (savedMultiAgentEvents?.length) {
          const lastAssistant = [...msgRes.value].reverse().find((m: any) => m.role === 'assistant')
          if (lastAssistant) lastAssistant._multiAgentEvents = savedMultiAgentEvents
        }
        messages.value = msgRes.value
      }
    }
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      ElMessage.error('重新生成失败：' + (e.message || '未知错误'))
    }
    if (streamContent.value) {
      messages.value.push({
        role: 'assistant',
        content: streamContent.value,
        token_count: lastStreamTokens.value?.output || 0,
        input_tokens: lastStreamTokens.value?.input || 0,
      })
      lastStreamTokens.value = null
    }
  } finally {
    streaming.value = false
    streamContent.value = ''
    streamMode.value = ''
    streamSqlData.value = null
    agentToolCalls.value = []
    multiAgentEvents.value = []
    abortController = null
    if (streamTimer) { clearInterval(streamTimer); streamTimer = null }
    streamElapsed.value = 0
  }
}

async function exportConv() {
  if (!currentConvId.value) return
  try {
    await exportConversation(currentConvId.value)
    ElMessage.success('对话导出成功')
  } catch {
    ElMessage.error('对话导出失败，请重试')
  }
}

onActivated(() => {
  loadInitData()
  loadChatTemplates()
  loadChatQuota()
})

onDeactivated(() => {
  abortController?.abort()
  if (streamTimer) { clearInterval(streamTimer); streamTimer = null }
  if (searchTimer) { clearTimeout(searchTimer); searchTimer = null }
})
</script>

<style scoped>
.chat-page {
  display: flex;
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--border-color);
}

/* ── Chat Main ── */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--card-bg);
}

/* ── Messages ── */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
}

.message {
  display: flex;
  gap: 14px;
  padding: 16px clamp(24px, 5%, 64px);
  margin-bottom: 0;
  transition: background var(--duration-fast) var(--ease-out);
}

.message.user {
  background: transparent;
  justify-content: flex-end;
}

.message.assistant {
  background: var(--gray-25);
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

.msg-avatar {
  width: 30px;
  height: 30px;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
  font-size: 12px;
  font-weight: 500;
}

.message.user .msg-avatar {
  order: 2;
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  color: #fff;
  box-shadow: var(--shadow-primary);
}

.message.assistant .msg-avatar {
  background: linear-gradient(135deg, #059669, #34d399);
  color: #fff;
  box-shadow: 0 2px 6px rgba(5, 150, 105, 0.2);
}

.msg-content {
  flex: 1;
  max-width: 740px;
  min-width: 0;
}

.message.user .msg-content {
  order: 1;
  display: flex;
  justify-content: flex-end;
}

.msg-text {
  line-height: 1.75;
  font-size: 14px;
  word-break: break-word;
  color: var(--text-primary);
}

.message.user .msg-text {
  white-space: pre-wrap;
  font-weight: 500;
}

.message.user .msg-text-wrap {
  justify-content: flex-end;
}

/* User message text + edit button wrapper */
.msg-text-wrap {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.msg-text-wrap .msg-text {
  flex: 1;
  min-width: 0;
}

/* Hover action buttons (edit / regenerate) */
.msg-hover-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 4px 6px;
  cursor: pointer;
  color: var(--text-muted);
  opacity: 0;
  transition: opacity var(--duration-fast), color var(--duration-fast), background var(--duration-fast);
  flex-shrink: 0;
  font-size: 12px;
  line-height: 1;
}

.message:hover .msg-hover-btn {
  opacity: 1;
}

.msg-hover-btn:hover {
  color: var(--primary);
  background: var(--primary-lighter);
  border-color: var(--primary-light);
}

.regenerate-btn {
  margin-left: 4px;
}

.regenerate-btn span {
  font-size: 12px;
}

@media (pointer: coarse) {
  .msg-hover-btn {
    opacity: 1;
  }
}

.feedback-reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.feedback-reason-title {
  width: 100%;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

/* Long message collapse */
.msg-collapse-bar {
  position: relative;
  text-align: center;
  padding-top: 4px;
}

.msg-collapse-mask {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  height: 80px;
  background: linear-gradient(to bottom, transparent, var(--gray-25));
  pointer-events: none;
}

.msg-collapse-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  padding: 4px 16px;
  cursor: pointer;
  font-size: 12px;
  color: var(--primary);
  font-weight: 500;
  transition: all var(--duration-fast);
  margin-top: 4px;
}

.msg-collapse-btn:hover {
  background: var(--primary-lighter);
  border-color: var(--primary-light);
}

.msg-actions {
  margin-top: 8px;
  opacity: 0;
  transition: opacity var(--duration-fast);
  display: flex;
  gap: 2px;
}

.message:hover .msg-actions {
  opacity: 1;
}

@media (pointer: coarse) {
  .msg-actions {
    opacity: 1;
  }
}

/* ── Markdown ── */
.md-body :deep(pre) {
  background: var(--gray-950);
  color: #e2e8f0;
  padding: 16px 18px;
  border-radius: var(--radius);
  overflow-x: auto;
  margin: 12px 0;
  font-size: 13px;
}

.md-body :deep(code) {
  font-family: var(--font-mono);
  font-size: 13px;
}

.md-body :deep(p code) {
  background: var(--primary-lighter);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  color: var(--primary-dark);
  font-size: 12.5px;
}

.md-body :deep(ul), .md-body :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}

.md-body :deep(table) {
  border-collapse: collapse;
  margin: 12px 0;
  width: 100%;
}

.md-body :deep(th) {
  background: var(--gray-50);
  font-weight: 500;
  text-align: left;
}

.md-body :deep(th), .md-body :deep(td) {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  font-size: 13px;
}

.md-body :deep(blockquote) {
  border-left: 3px solid var(--primary);
  padding-left: 14px;
  color: var(--text-tertiary);
  margin: 12px 0;
}

/* ── References ── */
.msg-refs {
  margin-top: 12px;
}

.refs-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-full);
  transition: all var(--duration-fast) var(--ease-out);
  user-select: none;
}

.refs-toggle:hover {
  background: var(--hover-bg);
  color: var(--text-secondary);
}

.chevron-icon {
  transition: transform var(--duration-fast) var(--ease-out);
}

.chevron-open {
  transform: rotate(180deg);
}

.msg-memories {
  margin-top: 8px;
}

.memories-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-full);
  transition: all var(--duration-fast) var(--ease-out);
  user-select: none;
}

.memories-toggle:hover {
  background: var(--hover-bg);
  color: var(--text-secondary);
}

.memories-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--gray-50);
  border-radius: var(--radius);
  border: 1px solid var(--border-color);
}

.memory-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.memory-text {
  color: var(--text-secondary);
  line-height: 1.5;
}

.refs-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.ref-card {
  padding: 10px 14px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.ref-card:hover {
  box-shadow: var(--shadow-sm);
}

.ref-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.ref-doc-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.ref-chunk {
  font-size: 10px;
  color: var(--text-muted);
  background: var(--gray-100);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-weight: 500;
}

.ref-score {
  font-size: 10px;
  font-weight: 500;
  color: var(--primary);
  margin-left: auto;
}

.ref-card-body {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-tertiary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 48px;
  overflow: hidden;
  transition: max-height 0.3s var(--ease-out);
}

.ref-expanded {
  max-height: 400px;
  overflow-y: auto;
}

/* ── Input Area ── */
.input-area {
  position: relative;
  padding: 14px 24px 18px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  gap: 12px;
  align-items: flex-end;
  background: var(--card-bg);
}

.input-area :deep(.el-textarea__inner) {
  resize: none;
  border-radius: var(--radius-xl) !important;
  padding: 12px 18px;
  font-family: var(--font-sans);
  background: var(--gray-25);
  border: 1px solid var(--border-subtle);
  transition: border-color var(--duration-fast), box-shadow var(--duration-fast);
}
.input-area :deep(.el-textarea__inner:focus) {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
  background: var(--card-bg);
}

.send-btn {
  flex-shrink: 0;
}

.voice-btn {
  flex-shrink: 0;
}

.stream-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0 8px;
}
.status-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.elapsed-badge {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--gray-100);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}
.slow-hint {
  font-size: 11px;
  color: var(--el-color-warning);
}
.timeout-warn {
  color: var(--el-color-danger);
  font-weight: 500;
}
.retrieval-warning {
  margin-bottom: 8px;
}
.retrieval-warning .el-alert {
  padding: 6px 12px;
  font-size: 12px;
}
.msg-token-info {
  margin-top: 4px;
}
.token-badge {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--gray-100);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.conv-action.pinned {
  color: var(--el-color-primary);
}

.cursor-blink {
  animation: blink 1s infinite;
  color: var(--primary);
  font-weight: 300;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ── Welcome / Cold Start ── */
.welcome-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px 40px;
  text-align: center;
}

.welcome-icon {
  width: 64px;
  height: 64px;
  border-radius: 18px;
  background: linear-gradient(135deg, var(--primary-lighter), var(--primary-glow));
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
  color: var(--primary);
}

.welcome-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}

.trial-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 16px;
  background: linear-gradient(90deg, #fff7ed, #fffbeb);
  border: 1px solid #fed7aa;
  border-radius: 20px;
  font-size: 13px;
  color: #92400e;
  margin-bottom: 12px;
}

.welcome-mode-hint {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.welcome-text {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 32px;
  max-width: 480px;
  line-height: 1.6;
}

.suggested-questions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px;
  max-width: 560px;
  width: 100%;
}

.suggest-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: var(--radius);
  border: 1px solid var(--border-subtle);
  background: var(--card-bg);
  cursor: pointer;
  transition: all var(--duration-base) var(--ease-out);
  text-align: left;
  box-shadow: var(--shadow-xs);
}

.suggest-card:hover {
  background: var(--gray-25);
  border-color: var(--primary-lighter);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.suggest-card:hover svg {
  color: var(--primary);
}

.suggest-text {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 400;
  line-height: 1.5;
}

.suggest-card svg {
  color: var(--gray-300);
  flex-shrink: 0;
  transition: color var(--duration-fast);
}

.cold-start {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 120px 20px;
  text-align: center;
}

.cold-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  background: var(--gray-50);
  border: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gray-400);
}

.cold-start h3 {
  margin: 20px 0 8px;
  color: var(--text-primary);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.cold-start p {
  color: var(--text-secondary);
  font-size: 14px;
}

.cold-ready {
  color: var(--text-secondary);
}

.cold-desc {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.cold-start-actions {
  margin-top: 20px;
}

.cold-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 14px;
  color: var(--text-secondary);
}

/* ── SQL Result Block ── */
.sql-result-block {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  overflow: hidden;
}

.sql-result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--gray-50);
  border-bottom: 1px solid var(--border-subtle);
}

.sql-code {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
  flex: 1;
  line-height: 1.5;
}

.sql-result-table-wrap {
  padding: 0;
}

.sql-row-count {
  padding: 6px 14px;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--gray-25);
  border-top: 1px solid var(--border-subtle);
}

.sql-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

/* ── Mode Badge ── */
.mode-badge {
  margin-bottom: 8px;
}

/* ── Agent Tool Calls ── */
.agent-tool-calls {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.multi-agent-events {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-call-item {
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--gray-25);
  transition: border-color 0.2s;
}

.multi-agent-item {
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--gray-25);
}

.tool-call-item.tool-success {
  border-color: var(--success-color);
  border-left: 3px solid var(--success-color);
}

.tool-call-item.tool-error {
  border-color: var(--danger-color);
  border-left: 3px solid var(--danger-color);
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.tool-name {
  flex: 1;
}

.tool-ok {
  color: var(--success-color);
}

.tool-fail {
  color: var(--danger-color);
}

.tool-call-args {
  padding: 0 12px 6px;
  cursor: pointer;
}

.tool-call-args code {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  background: var(--gray-50);
  padding: 2px 6px;
  border-radius: 4px;
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-call-result {
  border-top: 1px solid var(--border-subtle);
}

.tool-table-wrap {
  overflow: hidden;
}

.tool-sql-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--gray-50);
  border-bottom: 1px solid var(--border-subtle);
}

.tool-sql-badge code {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
  word-break: break-all;
  flex: 1;
}

.tool-row-count {
  padding: 4px 12px;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--gray-25);
  border-top: 1px solid var(--border-subtle);
}

.tool-refs-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--primary-color);
}

.tool-error-msg {
  padding: 8px 12px;
  font-size: 12px;
  color: var(--danger-color);
}

.tool-text-result {
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

@media (max-width: 768px) {
  .msg-content {
    max-width: 100%;
  }

  .input-area {
    padding: 12px;
  }

  .welcome-block {
    padding: 20px 16px;
  }

  .suggested-questions {
    grid-template-columns: 1fr;
  }
}

.attached-file-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px 8px 0 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.attached-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attach-btn {
  flex-shrink: 0;
}

/* ── Slash command menu ── */
.slash-menu {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  margin-bottom: 4px;
  background: var(--card-bg, #fff);
  border: 1px solid var(--border-subtle, #e2e8f0);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  max-height: 280px;
  overflow-y: auto;
  z-index: 100;
}

.slash-menu-header {
  padding: 8px 14px 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.slash-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.slash-menu-item:hover,
.slash-menu-item.active {
  background: var(--primary-lighter, #eff6ff);
}

.slash-icon {
  flex-shrink: 0;
  color: var(--primary, #2563eb);
}

.slash-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.slash-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #1e293b);
}

.slash-item-desc {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
