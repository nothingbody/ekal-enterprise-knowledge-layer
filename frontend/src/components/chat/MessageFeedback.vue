<template>
  <div class="message-feedback" v-if="messageId">
    <el-popover
      :visible="popoverType === 'like'"
      placement="top"
      :width="220"
      trigger="manual"
    >
      <template #reference>
        <el-button link size="small" @click="openPopover('like')" :type="feedback === 'like' ? 'success' : ''">
          <ThumbsUp :size="13" :stroke-width="1.5" />
        </el-button>
      </template>
      <div class="feedback-reasons">
        <div class="feedback-reason-title">选择原因（可选）</div>
        <el-tag
          v-for="r in likeReasons" :key="r.value"
          :type="feedbackReason === r.value ? 'success' : 'info'"
          size="small" style="cursor:pointer;margin:2px"
          @click="submit('like', r.value)"
        >{{ r.label }}</el-tag>
        <el-button size="small" style="margin-top:6px;width:100%" @click="submit('like')">直接提交</el-button>
      </div>
    </el-popover>

    <el-popover
      :visible="popoverType === 'dislike'"
      placement="top"
      :width="220"
      trigger="manual"
    >
      <template #reference>
        <el-button link size="small" @click="openPopover('dislike')" :type="feedback === 'dislike' ? 'danger' : ''">
          <ThumbsDown :size="13" :stroke-width="1.5" />
        </el-button>
      </template>
      <div class="feedback-reasons">
        <div class="feedback-reason-title">选择原因（可选）</div>
        <el-tag
          v-for="r in dislikeReasons" :key="r.value"
          :type="feedbackReason === r.value ? 'danger' : 'info'"
          size="small" style="cursor:pointer;margin:2px"
          @click="submit('dislike', r.value)"
        >{{ r.label }}</el-tag>
        <el-button size="small" style="margin-top:6px;width:100%" @click="submit('dislike')">直接提交</el-button>
      </div>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ThumbsUp, ThumbsDown } from 'lucide-vue-next'
import { messageFeedback } from '../../api/chat'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  messageId: number
  feedback: string | null
  feedbackReason: string | null
}>()

const emit = defineEmits<{
  (e: 'update', payload: { feedback: string | null; feedbackReason: string | null }): void
}>()

const popoverType = ref('')

const likeReasons = [
  { value: 'accurate', label: '回答准确' },
  { value: 'helpful', label: '很有帮助' },
  { value: 'well_written', label: '表述清晰' },
  { value: 'creative', label: '富有创意' },
]

const dislikeReasons = [
  { value: 'inaccurate', label: '回答不准确' },
  { value: 'irrelevant', label: '答非所问' },
  { value: 'incomplete', label: '回答不完整' },
  { value: 'harmful', label: '内容不当' },
  { value: 'too_long', label: '过于冗长' },
]

function openPopover(type: string) {
  if (props.feedback === type) {
    submit(type)
    return
  }
  popoverType.value = type
}

async function submit(type: string, reason?: string) {
  const newFeedback = props.feedback === type ? null : type
  try {
    await messageFeedback(props.messageId, newFeedback, reason)
    emit('update', {
      feedback: newFeedback,
      feedbackReason: newFeedback ? (reason || null) : null,
    })
    popoverType.value = ''
  } catch {
    ElMessage.error('反馈提交失败')
  }
}
</script>

<style scoped>
.message-feedback {
  display: inline-flex;
  align-items: center;
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
</style>
