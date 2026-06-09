<template>
  <div class="chat-config-bar">
    <el-button class="mobile-sidebar-toggle" size="small" @click="$emit('toggle-mobile-sidebar')">
      <MessageCircle :size="14" :stroke-width="1.5" />
    </el-button>
    <el-select v-model="chatConfig.kb_id" placeholder="选择知识库 *" size="small" style="width: 220px" @change="onKbChangeInternal">
      <el-option v-for="kb in kbList" :key="kb.id" :label="kb.name" :value="kb.id">
        <span>{{ kb.name }}</span>
        <el-tag v-if="kb.is_remote" size="small" :type="kb.host_online ? 'success' : 'danger'" style="margin-left: 6px">
          {{ kb.host_online ? '远程' : '离线' }}
        </el-tag>
      </el-option>
    </el-select>
    <el-select v-model="chatConfig.llm_model_id" placeholder="选择 LLM 模型 *" size="small" style="width: 200px">
      <el-option v-for="m in llmModels" :key="m.id" :label="m.display_name" :value="m.id" />
    </el-select>
    <el-popover trigger="click" :width="280" placement="bottom-end">
      <template #reference>
        <el-button size="small"><SlidersHorizontal :size="14" :stroke-width="1.5" style="margin-right: 4px" />检索设置</el-button>
      </template>
      <div style="display: flex; flex-direction: column; gap: 12px;">
        <div>
          <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 4px;">Top-K 召回数量</div>
          <el-slider v-model="chatConfig.top_k" :min="1" :max="20" :step="1" show-input size="small" :show-input-controls="false" />
        </div>
        <div>
          <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 4px;">相关度阈值（0=不过滤）</div>
          <el-slider v-model="chatConfig.score_threshold" :min="0" :max="1" :step="0.05" show-input size="small" :show-input-controls="false" />
        </div>
        <div>
          <el-checkbox v-model="chatConfig.enable_rewrite" label="启用查询改写" />
        </div>
      </div>
    </el-popover>
    <el-select v-model="chatConfig.chat_mode" size="small" style="width: 140px">
      <el-option label="自动" value="auto" />
      <el-option label="知识检索" value="rag" />
      <el-option label="数据库查询" value="sql" />
      <el-option label="混合模式" value="hybrid" />
      <el-option label="🤖 智能体" value="agent" />
      <el-option label="🔗 多Agent" value="multi_agent" />
    </el-select>
    <el-select v-model="chatConfig.prompt_template_id" size="small" style="width: 130px" clearable placeholder="输出模板">
      <el-option v-for="tpl in chatTemplateOptions" :key="tpl.id" :label="tpl.name" :value="tpl.id" />
    </el-select>
    <el-tooltip placement="bottom" :show-after="200">
      <template #content>
        <div class="chat-mode-tooltip">
          <div><strong>自动</strong>：根据问题智能选择检索或 SQL</div>
          <div><strong>知识检索</strong>：基于文档语义检索</div>
          <div><strong>数据库查询</strong>：自然语言转 SQL</div>
          <div><strong>混合</strong>：文档+数据库综合回答</div>
          <div><strong>智能体</strong>：可调用工具自主任务</div>
          <div><strong>多Agent</strong>：跨知识库协作</div>
        </div>
      </template>
      <CircleHelp :size="16" :stroke-width="1.5" class="chat-mode-help" />
    </el-tooltip>
    <el-select v-model="chatConfig.context_strategy" size="small" style="width: 130px" placeholder="上下文策略">
      <el-option label="滑动窗口" value="sliding_window" />
      <el-option label="语义摘要" value="semantic_summary" />
      <el-option label="完整上下文" value="full_context" />
    </el-select>
    <el-button v-if="showExportButton" size="small" @click="$emit('export-conversation')">
      <DownloadIcon :size="14" :stroke-width="1.5" style="margin-right: 4px" />导出对话
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { CircleHelp, Download as DownloadIcon, MessageCircle, SlidersHorizontal } from 'lucide-vue-next'

interface KnowledgeBaseOption {
  id: number
  name: string
  is_remote?: boolean
  host_online?: boolean
}

interface ModelOption {
  id: number
  display_name: string
}

interface TemplateOption {
  id: number
  name: string
}

interface ChatConfig {
  kb_id: number | null
  llm_model_id: number | null
  top_k: number
  score_threshold: number
  enable_rewrite: boolean
  chat_mode: string
  context_strategy: string
  prompt_template_id: number | null
}

const props = defineProps<{
  chatConfig: ChatConfig
  kbList: KnowledgeBaseOption[]
  llmModels: ModelOption[]
  chatTemplateOptions: TemplateOption[]
  showExportButton: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-mobile-sidebar'): void
  (e: 'kb-change', value: number | null): void
  (e: 'export-conversation'): void
}>()

function onKbChangeInternal(value: number | null) {
  emit('kb-change', value)
}
</script>

<style scoped>
.chat-config-bar {
  display: flex;
  gap: 8px;
  padding: 10px 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--gray-25);
  align-items: center;
  flex-wrap: wrap;
}

.chat-mode-help {
  margin-left: 4px;
  color: var(--text-muted);
  cursor: help;
  vertical-align: middle;
}

.chat-mode-tooltip div {
  padding: 2px 0;
  font-size: 12px;
}

.mobile-sidebar-toggle {
  display: none;
}

@media (max-width: 768px) {
  .mobile-sidebar-toggle {
    display: inline-flex;
    flex-shrink: 0;
  }

  .chat-config-bar {
    flex-wrap: wrap;
    gap: 6px;
  }

  .chat-config-bar :deep(.el-select) {
    width: 100% !important;
    min-width: 0;
  }
}
</style>
