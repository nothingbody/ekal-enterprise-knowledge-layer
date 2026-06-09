<template>
  <div class="diagnostics-page">
    <div class="page-header">
      <div>
        <h2>系统诊断</h2>
        <p class="page-desc">自动检测系统配置状态，发现问题并提供修复建议。</p>
      </div>
      <el-button type="primary" :loading="loading" @click="runDiagnostics">
        <RefreshCw :size="16" :stroke-width="1.5" style="margin-right: 4px" />{{ loading ? '检测中...' : '重新检测' }}
      </el-button>
    </div>

    <div v-if="loading && !results.length" class="empty-state">
      <el-icon class="is-loading" :size="48" style="color: var(--el-color-primary); margin-bottom: 16px;">
        <RefreshCw :size="48" :stroke-width="1" />
      </el-icon>
      <p>正在检测系统状态，请稍候...</p>
    </div>

    <div v-if="!results.length && !loading" class="empty-state">
      <Stethoscope :size="48" :stroke-width="1" style="color: var(--el-text-color-secondary); margin-bottom: 16px;" />
      <p>点击"重新检测"开始系统诊断</p>
    </div>

    <div v-if="results.length" class="summary-bar">
      <div class="summary-item ok">
        <CheckCircle :size="18" :stroke-width="1.5" />
        <span>{{ counts.ok }} 项正常</span>
      </div>
      <div v-if="counts.warning" class="summary-item warning">
        <AlertTriangle :size="18" :stroke-width="1.5" />
        <span>{{ counts.warning }} 项警告</span>
      </div>
      <div v-if="counts.error" class="summary-item error">
        <XCircle :size="18" :stroke-width="1.5" />
        <span>{{ counts.error }} 项异常</span>
      </div>
    </div>

    <div class="check-grid">
      <div v-for="(item, i) in results" :key="i" class="check-card" :class="item.status">
        <div class="check-icon">
          <CheckCircle v-if="item.status === 'ok'" :size="22" :stroke-width="1.5" />
          <AlertTriangle v-else-if="item.status === 'warning'" :size="22" :stroke-width="1.5" />
          <XCircle v-else :size="22" :stroke-width="1.5" />
        </div>
        <div class="check-content">
          <div class="check-name">{{ item.name }}</div>
          <div class="check-message">{{ item.message }}</div>
          <div v-if="item.suggestion" class="check-suggestion">
            <Lightbulb :size="14" :stroke-width="1.5" />
            {{ item.suggestion }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { RefreshCw, Stethoscope, CheckCircle, AlertTriangle, XCircle, Lightbulb } from 'lucide-vue-next'
import request from '../../utils/request'

interface DiagResult { name: string; status: string; message: string; suggestion: string }

const results = ref<DiagResult[]>([])
const loading = ref(false)

const counts = computed(() => {
  const c = { ok: 0, warning: 0, error: 0 }
  results.value.forEach(r => { if (r.status in c) c[r.status as keyof typeof c]++ })
  return c
})

const runDiagnostics = async () => {
  loading.value = true
  try {
    const res = await request.get('/diagnostics/run')
    results.value = Array.isArray(res) ? res : []
  } catch (e: any) {
    ElMessage.error('诊断请求失败')
  } finally {
    loading.value = false
  }
}

onMounted(runDiagnostics)
</script>

<style scoped>
.diagnostics-page { padding: 24px; max-width: 900px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h2 { margin: 0 0 4px; font-size: 20px; }
.page-desc { color: var(--el-text-color-secondary); font-size: 13px; margin: 0; }
.empty-state { text-align: center; padding: 80px 20px; color: var(--el-text-color-secondary); }
.summary-bar { display: flex; gap: 16px; margin-bottom: 20px; padding: 12px 16px; background: var(--el-fill-color-light); border-radius: 8px; }
.summary-item { display: flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 500; }
.summary-item.ok { color: var(--el-color-success); }
.summary-item.warning { color: var(--el-color-warning); }
.summary-item.error { color: var(--el-color-danger); }
.check-grid { display: flex; flex-direction: column; gap: 12px; }
.check-card { display: flex; gap: 14px; padding: 16px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--el-bg-color); }
.check-card.ok .check-icon { color: var(--el-color-success); }
.check-card.warning .check-icon { color: var(--el-color-warning); }
.check-card.warning { border-color: var(--el-color-warning-light-5); }
.check-card.error .check-icon { color: var(--el-color-danger); }
.check-card.error { border-color: var(--el-color-danger-light-5); }
.check-icon { flex-shrink: 0; padding-top: 2px; }
.check-content { flex: 1; min-width: 0; }
.check-name { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
.check-message { font-size: 13px; color: var(--el-text-color-regular); }
.check-suggestion { margin-top: 8px; font-size: 12px; color: var(--el-color-primary); display: flex; align-items: center; gap: 4px; padding: 6px 10px; background: var(--el-color-primary-light-9); border-radius: 4px; }
</style>
