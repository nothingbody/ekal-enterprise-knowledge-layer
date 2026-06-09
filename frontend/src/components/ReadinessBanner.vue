<template>
  <div v-if="warnings.length && !dismissed" class="readiness-banner">
    <div class="banner-content">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span class="banner-text">{{ warnings[0]?.text }}</span>
      <button class="banner-action" @click="$router.push(warnings[0]?.route ?? '/models')">{{ warnings[0]?.action }}</button>
      <button class="banner-dismiss" @click="dismiss" title="关闭">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getSystemReadiness } from '../api/system'
import { setShareBaseUrl } from '../utils/apiBase'

interface Warning {
  text: string
  action: string
  route: string
}

const router = useRouter()
const route = useRoute()
const warnings = ref<Warning[]>([])
const dismissed = ref(false)

const DISMISS_KEY = 'readiness_banner_ts'
const DISMISS_TTL = 4 * 3600 * 1000 // re-show after 4 hours

function isDismissed(): boolean {
  const ts = localStorage.getItem(DISMISS_KEY)
  return !!(ts && Date.now() - Number(ts) < DISMISS_TTL)
}

async function checkReadiness() {
  if (isDismissed()) {
    dismissed.value = true
    return
  }
  dismissed.value = false
  try {
    const res: any = await getSystemReadiness()
    if (res.share_base_url) {
      setShareBaseUrl(res.share_base_url)
    }
    const w: Warning[] = []
    for (const step of res.steps) {
      if (step.done) continue
      if (step.key === 'llm') {
        w.push({ text: '尚未配置 LLM 模型，对话功能不可用', action: '去配置', route: '/models' })
      } else if (step.key === 'embedding') {
        w.push({ text: '尚未配置 Embedding 模型，知识库向量化不可用', action: '去配置', route: '/models' })
      }
    }
    warnings.value = w
  } catch {
    // silent
  }
}

onMounted(checkReadiness)

// Re-check on route change (user may have configured models)
watch(() => route.path, checkReadiness)

function dismiss() {
  dismissed.value = true
  localStorage.setItem(DISMISS_KEY, String(Date.now()))
}
</script>

<style scoped>
.readiness-banner {
  background: linear-gradient(90deg, #fef3c7 0%, #fde68a 100%);
  border-bottom: 1px solid #fbbf24;
  padding: 0;
  z-index: 51;
  flex-shrink: 0;
}

.banner-content {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 28px;
  font-size: 13px;
  color: #92400e;
}

.banner-content svg {
  flex-shrink: 0;
  color: #d97706;
}

.banner-text {
  font-weight: 600;
}

.banner-action {
  background: #d97706;
  color: #fff;
  border: none;
  padding: 3px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 150ms;
}
.banner-action:hover {
  background: #b45309;
}

.banner-dismiss {
  background: none;
  border: none;
  cursor: pointer;
  color: #92400e;
  padding: 2px;
  border-radius: 4px;
  display: flex;
  margin-left: auto;
  transition: all 150ms;
}
.banner-dismiss:hover {
  background: rgba(0, 0, 0, 0.08);
}
</style>
