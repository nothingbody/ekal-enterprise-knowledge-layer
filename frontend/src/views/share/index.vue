<template>
  <div class="share-page">
    <div v-if="appLoading" class="share-loading">
      <div class="share-spinner"></div>
      <p style="margin-top: 12px; color: #999;">正在加载应用...</p>
    </div>
    <template v-else>
    <div class="share-header">
      <div class="share-header-inner">
        <img v-if="appInfo.logo_url" :src="appInfo.logo_url" alt="Logo" class="share-logo" style="height: 32px; margin-right: 12px; border-radius: 4px;" />
        <div class="share-header-title">
          <h2>{{ appInfo.name || '智能问答' }}</h2>
          <p v-if="appInfo.description" class="share-desc">{{ appInfo.description }}</p>
        </div>
        <el-button v-if="messages.length" size="small" @click="handleNewConversation">
          <SquarePen :size="14" :stroke-width="1.5" style="margin-right: 4px" />新建对话
        </el-button>
      </div>
    </div>
    <div class="share-chat">
      <div class="messages-area" ref="messagesRef" v-loading="historyLoading">
        <div v-if="!messages.length && !streaming" class="welcome-area">
          <p v-if="appInfo.welcome_message" class="welcome-msg">{{ appInfo.welcome_message }}</p>
          <div v-if="appInfo.suggested_questions?.length" class="suggested">
            <el-button v-for="(q, i) in appInfo.suggested_questions" :key="i" size="small" round @click="askQuestion(q)">{{ q }}</el-button>
          </div>
          <p v-if="!appInfo.welcome_message" class="welcome-msg">你好！请输入你的问题。</p>
        </div>
        <div v-for="(msg, idx) in messages" :key="idx" class="message" :class="msg.role">
          <div class="msg-bubble" v-if="msg.role === 'user'">{{ msg.content }}</div>
          <div class="msg-bubble-wrap" v-else>
            <div class="msg-bubble md-body" v-html="renderMd(msg.content)"></div>
            <button class="copy-btn" @click="copyMessage(msg.content)" title="复制回答">
              <Copy :size="14" :stroke-width="1.5" />
            </button>
          </div>
          <div v-if="msg.references && parseRefs(msg.references).length" class="msg-refs-wrap">
            <button class="refs-toggle" @click="toggleRefs(idx)">
              <ChevronRight :size="14" :stroke-width="1.5" :class="{ 'refs-chevron-open': expandedRefs.has(idx) }" class="refs-chevron" />
              <span>引用来源 ({{ parseRefs(msg.references).length }})</span>
            </button>
            <div v-if="expandedRefs.has(idx)" class="msg-refs">
              <div v-for="(ref, ri) in parseRefs(msg.references)" :key="ri" class="ref-item">
                <el-tag size="small" type="info">{{ ref.doc_name }}</el-tag>
                <span class="ref-text">{{ truncate(ref.content, 120) }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="streaming" class="message assistant">
          <div class="msg-bubble md-body" v-html="renderMd(streamContent)"></div><span class="blink">|</span>
        </div>
      </div>
      <div v-if="!error" class="input-area">
        <el-input v-model="question" type="textarea" :autosize="{ minRows: 1, maxRows: 5 }" placeholder="输入你的问题..." @keydown.enter.exact.prevent="send" @keydown.escape="cancelStream" :disabled="streaming" resize="none" />
        <el-button v-if="!streaming" type="primary" @click="send" :disabled="!question.trim()">发送</el-button>
        <el-button v-else type="danger" @click="cancelStream">停止</el-button>
      </div>
    </div>
    <div v-if="error" class="error-msg-center">
      <el-icon :size="48" color="var(--danger, #f56c6c)"><WarningFilled /></el-icon>
      <h3>{{ error }}</h3>
      <p>请检查链接是否正确，或联系应用发布者</p>
    </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { Copy, SquarePen, ChevronRight } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { renderMarkdown } from '../../utils/markdown'
import { API_V1 } from '../../utils/apiBase'

function renderMd(text: string) {
  if (!text) return ''
  return renderMarkdown(text)
}

function parseRefs(refs: string) {
  try {
    return JSON.parse(refs)
  } catch {
    return []
  }
}

function truncate(text: string, len: number) {
  return text.length > len ? text.substring(0, len) + '...' : text
}

const route = useRoute()
const shareToken = route.params.token as string
const visitorStorageKey = `public-app-visitor:${shareToken}`
const convStorageKey = `public-app-conv:${shareToken}`
const messagesRef = ref<HTMLElement>()
const messages = ref<any[]>([])
const question = ref('')
const streaming = ref(false)
const streamContent = ref('')
const conversationId = ref<number | null>(null)
const error = ref('')
const visitorId = ref('')
const appLoading = ref(true)
const historyLoading = ref(false)
let abortController: AbortController | null = null

const appInfo = reactive({
  name: '',
  description: '',
  welcome_message: '',
  suggested_questions: [] as string[],
  brand_color: '' as string | null,
  logo_url: '' as string | null,
  custom_css: '' as string | null,
})

function ensureVisitorId() {
  if (visitorId.value) return visitorId.value
  const stored = localStorage.getItem(visitorStorageKey)
  if (stored) {
    visitorId.value = stored
    return stored
  }
  const generated = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
  localStorage.setItem(visitorStorageKey, generated)
  visitorId.value = generated
  return generated
}

onMounted(async () => {
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
    document.documentElement.setAttribute('data-theme', 'dark')
  }
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light')
  })

  ensureVisitorId()
  try {
    const resp = await fetch(`${API_V1}/apps/public/${shareToken}/info`)
    if (!resp.ok) {
      if (resp.status === 404) {
        error.value = '应用不存在或链接已失效'
      } else if (resp.status === 403) {
        error.value = '应用已停用，请联系发布者'
      } else {
        error.value = '服务暂时不可用，请稍后重试'
      }
      return
    }
    const data = await resp.json()
    Object.assign(appInfo, data)
    // Apply branding customization
    if (data.brand_color) {
      document.documentElement.style.setProperty('--el-color-primary', data.brand_color)
    }
    if (data.custom_css) {
      const style = document.createElement('style')
      style.textContent = data.custom_css
      document.head.appendChild(style)
    }
  } catch {
    error.value = '网络连接失败，请检查网络后重试'
    return
  } finally {
    appLoading.value = false
  }

  // Restore previous conversation
  const savedConvId = localStorage.getItem(convStorageKey)
  if (savedConvId) {
    const cid = parseInt(savedConvId, 10)
    if (cid > 0) {
      historyLoading.value = true
      try {
        const hResp = await fetch(`${API_V1}/apps/public/${shareToken}/history?visitor_id=${encodeURIComponent(ensureVisitorId())}&conversation_id=${cid}`)
        if (hResp.ok) {
          const hData = await hResp.json()
          if (hData.messages?.length) {
            messages.value = hData.messages
            conversationId.value = cid
            scrollToBottom()
          }
        }
      } catch { /* ignore, start fresh */ }
      finally { historyLoading.value = false }
    }
  }
})

function askQuestion(q: string) {
  question.value = q
  send()
}

async function send() {
  if (!question.value.trim() || streaming.value) return
  const q = question.value.trim()
  question.value = ''
  messages.value.push({ role: 'user', content: q })
  streaming.value = true
  streamContent.value = ''
  let currentRefs: any = null
  abortController = new AbortController()

  await nextTick()
  scrollToBottom()

  try {
    const resp = await fetch(`${API_V1}/apps/public/${shareToken}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, conversation_id: conversationId.value, visitor_id: ensureVisitorId() }),
      signal: abortController.signal,
    })
    if (!resp.ok || !resp.body) throw new Error('请求失败')

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

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
            streamContent.value += chunk.data
            scrollToBottom()
          } else if (chunk.type === 'error') {
            streamContent.value += `\n\n⚠️ ${chunk.data || chunk.message || '服务器处理失败'}`
            scrollToBottom()
          } else if (chunk.type === 'references') {
            currentRefs = chunk.data
          } else if (chunk.type === 'done') {
            conversationId.value = chunk.conversation_id
            if (chunk.conversation_id) {
              localStorage.setItem(convStorageKey, String(chunk.conversation_id))
            }
          }
        } catch {}
      }
    }
    // Flush any remaining data in buffer
    if (buffer.trim()) {
      try {
        const chunk = JSON.parse(buffer)
        if (chunk.type === 'content') {
          streamContent.value += chunk.data
        } else if (chunk.type === 'error') {
          streamContent.value += `\n\n⚠️ ${chunk.data || chunk.message || '服务器处理失败'}`
        } else if (chunk.type === 'references') {
          currentRefs = chunk.data
        } else if (chunk.type === 'done') {
          conversationId.value = chunk.conversation_id
          if (chunk.conversation_id) {
            localStorage.setItem(convStorageKey, String(chunk.conversation_id))
          }
        }
      } catch { /* skip */ }
    }
    messages.value.push({
      role: 'assistant',
      content: streamContent.value,
      references: currentRefs ? JSON.stringify(currentRefs) : null,
    })
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      messages.value.push({ role: 'assistant', content: '抱歉，发生了错误。' })
    } else if (streamContent.value) {
      messages.value.push({ role: 'assistant', content: streamContent.value })
    }
  } finally {
    streaming.value = false
    streamContent.value = ''
    abortController = null
  }
}

function cancelStream() {
  abortController?.abort()
}

const expandedRefs = ref<Set<number>>(new Set())

function toggleRefs(idx: number) {
  const s = new Set(expandedRefs.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedRefs.value = s
}

async function copyMessage(content: string) {
  try {
    const plain = content.replace(/<[^>]+>/g, '')
    await navigator.clipboard.writeText(plain)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败')
  }
}

function handleNewConversation() {
  messages.value = []
  conversationId.value = null
  localStorage.removeItem(convStorageKey)
  expandedRefs.value = new Set()
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  })
}
</script>

<style scoped>
.share-page {
  max-width: 860px;
  margin: 0 auto;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--card-bg);
}

.share-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
}

.share-header-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.share-header-title {
  text-align: center;
  flex: 1;
}

.share-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.03em;
  font-family: var(--font-sans);
}

.share-desc {
  color: var(--text-muted);
  font-size: 14px;
  margin-top: 6px;
}

.share-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.welcome-area {
  text-align: center;
  padding: 60px 0;
}

.welcome-msg {
  color: var(--text-secondary);
  font-size: 16px;
  margin-bottom: 20px;
  line-height: 1.6;
}

.suggested {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.suggested .el-button {
  border-color: var(--border-color);
  color: var(--text-secondary);
}

.suggested .el-button:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-lighter);
}

.message {
  margin-bottom: 20px;
  display: flex;
  animation: msgIn var(--duration-base) var(--ease-out);
}

@keyframes msgIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
  flex-wrap: wrap;
}

.msg-bubble {
  max-width: 75%;
  padding: 12px 18px;
  border-radius: var(--radius-lg);
  line-height: 1.7;
  font-size: 14px;
  word-break: break-word;
  white-space: pre-wrap;
}

.message.user .msg-bubble {
  background: linear-gradient(135deg, var(--primary), #7c6aff);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant .msg-bubble {
  background: var(--gray-50);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-bottom-left-radius: 4px;
}

.message.assistant .msg-bubble.md-body {
  white-space: normal;
}

.message.assistant .msg-bubble.md-body :deep(pre) {
  background: var(--gray-950);
  color: #e2e8f0;
  padding: 14px;
  border-radius: var(--radius);
  overflow-x: auto;
  margin: 8px 0;
}

.message.assistant .msg-bubble.md-body :deep(code) {
  font-family: var(--font-mono);
  font-size: 13px;
}

.message.assistant .msg-bubble.md-body :deep(p:last-child) {
  margin-bottom: 0;
}

.msg-bubble-wrap {
  position: relative;
  max-width: 75%;
  display: flex;
  flex-direction: column;
}

.msg-bubble-wrap .msg-bubble {
  max-width: 100%;
}

.copy-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 4px;
  cursor: pointer;
  color: var(--text-muted);
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.msg-bubble-wrap:hover .copy-btn {
  opacity: 1;
}

.copy-btn:hover {
  color: var(--primary);
}

.msg-refs-wrap {
  width: 100%;
  margin-top: 8px;
  max-width: 75%;
}

.refs-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
  padding: 4px 0;
  letter-spacing: 0.3px;
}

.refs-toggle:hover {
  color: var(--primary);
}

.refs-chevron {
  transition: transform 0.2s;
}

.refs-chevron-open {
  transform: rotate(90deg);
}

.msg-refs {
  margin-top: 6px;
  padding: 10px 14px;
  background: var(--gray-50);
  border-radius: var(--radius);
  border: 1px solid var(--border-color);
  font-size: 12px;
  animation: msgIn var(--duration-base) var(--ease-out);
}

.ref-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 4px;
}

.ref-text {
  color: var(--text-muted);
  line-height: 1.5;
}

.input-area {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
  display: flex;
  gap: 12px;
  align-items: flex-end;
  background: var(--card-bg);
}

.input-area :deep(.el-textarea) {
  flex: 1;
}

.input-area :deep(.el-textarea__inner) {
  box-shadow: none;
}

.input-area .el-button {
  font-weight: 600;
}

.error-msg-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px;
  text-align: center;
  gap: 12px;
}

.error-msg-center h3 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.error-msg-center p {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

.blink {
  animation: blink 1s infinite;
  color: var(--primary);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.share-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
}

.share-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e5e7eb;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: share-spin 0.8s linear infinite;
}

@keyframes share-spin {
  to { transform: rotate(360deg); }
}
</style>
