<template>
  <div class="skills-page">
    <div class="page-header">
      <h2>技能管理</h2>
    </div>

    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <el-tab-pane label="技能市场" name="marketplace" />
      <el-tab-pane label="已安装" name="installed" />
      <el-tab-pane label="Prompt 技能" name="prompt" />
      <el-tab-pane label="技能链" name="chains" />
    </el-tabs>

    <!-- ═══════════ 技能市场 ═══════════ -->
    <div v-if="activeTab === 'marketplace'">
      <div class="toolbar">
        <div class="filter-group">
          <el-select v-model="marketCategory" placeholder="全部分类" clearable style="width: 140px" @change="loadMarketplace">
            <el-option label="全部分类" value="" />
            <el-option label="通用" value="general" />
            <el-option label="开发" value="development" />
            <el-option label="数据" value="data" />
            <el-option label="效率" value="productivity" />
            <el-option label="检索" value="retrieval" />
            <el-option label="创意" value="creative" />
            <el-option label="通信" value="communication" />
            <el-option label="安全" value="security" />
            <el-option label="金融" value="finance" />
            <el-option label="销售" value="sales" />
          </el-select>
          <el-input v-model="marketSearch" placeholder="搜索技能..." clearable style="width: 220px" @keydown.enter="loadMarketplace()" @clear="loadMarketplace()">
            <template #prefix><SearchIcon :size="15" :stroke-width="1.5" /></template>
          </el-input>
        </div>
      </div>

      <!-- 技能列表 -->
      <div v-loading="marketLoading">
        <el-row v-if="marketSkills.length" :gutter="16">
          <el-col :xs="24" :sm="12" :md="8" v-for="skill in marketSkills" :key="skill.id">
            <div class="skill-card" @click="viewSkillDetail(skill)">
              <div class="skill-card-icon">
                <PuzzleIcon :size="22" :stroke-width="1.5" />
              </div>
              <div class="skill-card-body">
                <div class="skill-card-title">{{ skill.name }}</div>
                <p class="skill-card-desc">{{ skill.description || '暂无描述' }}</p>
                <div class="skill-card-tags">
                  <el-tag size="small" :type="categoryTagType(skill.category)">{{ categoryLabel(skill.category) }}</el-tag>
                  <el-tag size="small" type="info" effect="plain">{{ skillTypeLabel(skill.skill_type) }}</el-tag>
                </div>
                <div class="skill-card-footer">
                  <div class="skill-stats">
                    <span class="install-count"><DownloadIcon :size="13" :stroke-width="1.5" />{{ skill.download_count ?? skill.install_count ?? 0 }}</span>
                    <span v-if="skill.avg_rating" class="skill-rating">
                      <StarIcon :size="13" :stroke-width="1.5" class="star-filled" />{{ skill.avg_rating.toFixed(1) }}
                    </span>
                  </div>
                  <el-button v-if="isSkillInstalled(skill)" type="success" size="small" plain disabled @click.stop>
                    <CheckIcon :size="14" :stroke-width="2" style="margin-right: 2px" />已安装
                  </el-button>
                  <el-button v-else type="primary" size="small" :loading="installingId === skill.id" @click.stop="installSkill(skill)">
                    <PlusIcon :size="14" :stroke-width="1.5" style="margin-right: 2px" />安装
                  </el-button>
                </div>
              </div>
            </div>
          </el-col>
        </el-row>
        <el-empty v-if="!marketLoading && !marketSkills.length" description="暂无技能" />
      </div>

      <el-pagination
        v-if="marketTotal > marketPageSize"
        class="skills-pagination"
        layout="total, prev, pager, next"
        :total="marketTotal"
        :page-size="marketPageSize"
        v-model:current-page="marketPage"
        @current-change="loadMarketplace"
      />

    </div>

    <!-- ═══════════ 已安装 ═══════════ -->
    <div v-if="activeTab === 'installed'">
      <div class="toolbar">
        <div class="filter-group">
          <el-button type="warning" plain :loading="translateRunning" @click="startBatchTranslate">
            <LanguagesIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />批量翻译 OpenClaw 技能
          </el-button>
        </div>
        <div v-if="translateProgress.total > 0" class="translate-progress">
          <el-progress
            :percentage="translatePercentage"
            :status="translateRunning ? '' : 'success'"
            :stroke-width="8"
            style="width: 200px;"
          />
          <span class="translate-stats">
            {{ translateProgress.translated }} 已翻译 / {{ translateProgress.skipped }} 已跳过 / {{ translateProgress.failed }} 失败
          </span>
        </div>
      </div>
      <div v-loading="installedLoading">
        <el-table v-if="installedSkills.length" :data="installedSkills" stripe>
          <el-table-column prop="skill_name" label="技能名称" min-width="160">
            <template #default="{ row }">
              <div class="skill-name-cell">
                <PuzzleIcon :size="15" :stroke-width="1.5" class="skill-name-icon" />
                <span>{{ row.name || row.skill_name || row.skill?.name || '—' }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="分类" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="categoryTagType(row.skill?.category)">{{ categoryLabel(row.skill?.category) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-switch v-model="row.is_active" :loading="togglingId === row.install_id" @change="toggleInstalled(row)" />
            </template>
          </el-table-column>
          <el-table-column label="安装时间" width="180">
            <template #default="{ row }">{{ new Date(row.installed_at || row.created_at).toLocaleString() }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="uninstallSkill(row)">
                <Trash2Icon :size="14" :stroke-width="1.5" style="margin-right: 2px" />卸载
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!installedLoading && !installedSkills.length">
          <template #description>
            <p>暂未安装任何技能</p>
            <p style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px">技能需要模型支持，若未配置请先前往配置</p>
          </template>
          <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
            <el-button type="primary" @click="switchToMarketplace">前往技能市场</el-button>
            <el-button link type="primary" @click="$router.push('/models')">前往配置模型</el-button>
            <el-button link type="primary" @click="$router.push('/guide')">查看使用指南</el-button>
          </div>
        </el-empty>
      </div>
    </div>

    <!-- ═══════════ Prompt 技能 ═══════════ -->
    <div v-if="activeTab === 'prompt'">
      <div class="toolbar">
        <el-button type="primary" @click="openPromptDialog()">
          <PlusIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />创建 Prompt 技能
        </el-button>
        <el-dropdown @command="applyTemplate" trigger="click">
          <el-button>
            <LayersIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />从模板创建
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="tpl in skillTemplates" :key="tpl.slug" :command="tpl">
                {{ tpl.name }} — <span style="color: var(--el-text-color-secondary); font-size: 12px;">{{ tpl.description }}</span>
              </el-dropdown-item>
              <el-dropdown-item v-if="!skillTemplates.length" disabled>加载中...</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <div v-loading="promptLoading">
        <el-table v-if="promptSkills.length" :data="promptSkills" stripe>
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column prop="slug" label="标识" min-width="120">
            <template #default="{ row }">
              <code class="slug-code">{{ row.slug }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
          <el-table-column label="输出格式" width="100">
            <template #default="{ row }">
              <el-tag size="small" type="info">{{ row.output_format || 'text' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="公开" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_public ? 'success' : 'info'" size="small">{{ row.is_public ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openPromptDialog(row)">编辑</el-button>
              <el-button link type="primary" size="small" :loading="publishingId === row.id" @click="publishToCloud(row)">
                <UploadCloudIcon :size="14" :stroke-width="1.5" style="margin-right: 2px" />发布到市场
              </el-button>
              <el-button link type="danger" size="small" @click="deletePromptSkill(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!promptLoading && !promptSkills.length" description="暂无 Prompt 技能，点击上方按钮创建" />
      </div>
    </div>

    <!-- ═══════════ 技能链 ═══════════ -->
    <div v-if="activeTab === 'chains'">
      <div class="toolbar">
        <el-button type="primary" @click="openChainDialog()">
          <PlusIcon :size="16" :stroke-width="1.5" style="margin-right: 4px" />创建技能链
        </el-button>
      </div>

      <div v-loading="chainLoading">
        <div v-if="chains.length" class="chain-list">
          <div v-for="chain in chains" :key="chain.id" class="chain-card">
            <div class="chain-card-header">
              <div class="chain-card-title">
                <Link2Icon :size="16" :stroke-width="1.5" class="chain-icon" />
                <span>{{ chain.name }}</span>
              </div>
              <div class="chain-card-actions">
                <el-button type="primary" size="small" plain @click="openExecuteDialog(chain)">
                  <PlayIcon :size="14" :stroke-width="1.5" style="margin-right: 2px" />执行
                </el-button>
                <el-button type="danger" size="small" plain @click="deleteChain(chain)">
                  <Trash2Icon :size="14" :stroke-width="1.5" />
                </el-button>
              </div>
            </div>
            <p v-if="chain.description" class="chain-desc">{{ chain.description }}</p>
            <div class="chain-steps">
              <template v-for="(step, idx) in chain.steps" :key="idx">
                <div class="chain-step-badge">
                  <ZapIcon :size="12" :stroke-width="1.5" />
                  <span>{{ step.skill_name || `技能 #${step.skill_id}` }}</span>
                </div>
                <div v-if="Number(idx) < (chain.steps?.length || 0) - 1" class="chain-arrow">→</div>
              </template>
            </div>
          </div>
        </div>
        <el-empty v-if="!chainLoading && !chains.length" description="暂无技能链，点击上方按钮创建" />
      </div>
    </div>

    <!-- ═══════════ Prompt 技能对话框 ═══════════ -->
    <el-dialog v-model="promptDialogVisible" :title="editingPrompt ? '编辑 Prompt 技能' : '创建 Prompt 技能'" width="600px">
      <el-form :model="promptForm" :rules="promptRules" ref="promptFormRef" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="promptForm.name" placeholder="技能名称" @input="autoSlug" />
        </el-form-item>
        <el-form-item label="标识" prop="slug">
          <el-input v-model="promptForm.slug" placeholder="自动生成，可手动修改">
            <template #prepend>slug</template>
          </el-input>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="promptForm.description" type="textarea" :rows="2" placeholder="简要描述该技能的功能" />
        </el-form-item>
        <el-form-item label="Prompt 模板" prop="prompt_template">
          <el-input
            v-model="promptForm.prompt_template"
            type="textarea"
            :rows="8"
            placeholder="使用 {{variable}} 语法定义变量&#10;&#10;示例：&#10;请将以下文本翻译为 {{target_language}}：&#10;&#10;{{text}}"
            class="prompt-textarea"
          />
          <div class="field-hint">
            <ZapIcon :size="12" :stroke-width="1.5" />
            使用 <code>{<!-- -->{variable}}</code> 语法定义输入变量
          </div>
        </el-form-item>
        <el-form-item label="输出格式">
          <el-select v-model="promptForm.output_format" style="width: 100%">
            <el-option label="纯文本" value="text" />
            <el-option label="JSON" value="json" />
            <el-option label="Markdown" value="markdown" />
          </el-select>
        </el-form-item>
        <el-form-item label="公开">
          <el-switch v-model="promptForm.is_public" />
          <span class="switch-label">其他用户可以在市场中发现并安装此技能</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="promptDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="promptSubmitting" @click="submitPromptSkill">{{ editingPrompt ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <!-- ═══════════ 创建技能链对话框 ═══════════ -->
    <el-dialog v-model="chainDialogVisible" title="创建技能链" width="640px">
      <el-form :model="chainForm" :rules="chainRules" ref="chainFormRef" label-width="90px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="chainForm.name" placeholder="技能链名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="chainForm.description" type="textarea" :rows="2" placeholder="简要描述" />
        </el-form-item>
        <el-form-item label="步骤" prop="steps">
          <div class="chain-builder">
            <div v-for="(step, idx) in chainForm.steps" :key="idx" class="chain-builder-step">
              <div class="step-top">
                <div class="step-number">{{ idx + 1 }}</div>
                <el-select v-model="step.skill_id" placeholder="选择技能" style="flex: 1">
                  <el-option v-for="s in allSkillsForChain" :key="s.id" :label="s.name" :value="s.id" />
                </el-select>
                <el-input v-model="step.output_key" placeholder="输出 Key" style="width: 120px" />
                <el-button link type="danger" @click="chainForm.steps.splice(idx, 1)" :disabled="chainForm.steps.length <= 1">
                  <Trash2Icon :size="14" :stroke-width="1.5" />
                </el-button>
              </div>
              <div class="step-body">
                <div class="step-hint">
                  可用变量：<code v-text="'{{initial_input}}'"></code>
                  <span v-if="idx > 0">、前序步骤输出如 <code v-text="'{{step' + idx + '.output}}'"></code></span>
                </div>
                <div v-if="getSkillVariableHints(step.skill_id).length" class="step-hint">
                  推荐参数：
                  <span
                    v-for="hint in getSkillVariableHints(step.skill_id)"
                    :key="hint.key"
                    class="mapping-hint-chip"
                    @click="applySuggestedMapping(step, hint.key, hint.value)"
                  >
                    {{ hint.key }} = {{ hint.value }}
                  </span>
                </div>
                <div class="mapping-list">
                  <div v-for="(mapping, mIdx) in step.mapping_rows" :key="mIdx" class="mapping-row">
                    <el-input v-model="mapping.key" placeholder="参数名，如 query" style="width: 180px" />
                    <el-input v-model="mapping.value" placeholder="参数值，如 {{initial_input}}" style="flex: 1" />
                    <el-button link type="danger" @click="step.mapping_rows.splice(mIdx, 1)">
                      <Trash2Icon :size="14" :stroke-width="1.5" />
                    </el-button>
                  </div>
                </div>
                <el-button size="small" plain @click="step.mapping_rows.push({ key: '', value: '' })">
                  添加参数映射
                </el-button>
              </div>
            </div>
            <el-button size="small" @click="chainForm.steps.push(createChainStep(chainForm.steps.length + 1))">
              <PlusIcon :size="14" :stroke-width="1.5" style="margin-right: 2px" />添加步骤
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="公开">
          <el-switch v-model="chainForm.is_public" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="chainDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="chainSubmitting" @click="submitChain">创建</el-button>
      </template>
    </el-dialog>

    <!-- ═══════════ 技能详情对话框 ═══════════ -->
    <el-dialog v-model="detailVisible" title="技能详情" width="560px" @closed="detailData = null">
      <div v-if="detailLoading" v-loading="true" style="min-height: 120px;"></div>
      <template v-else-if="detailData">
        <div class="detail-view">
          <div class="detail-header">
            <div class="detail-icon">
              <PuzzleIcon :size="28" :stroke-width="1.5" />
            </div>
            <div>
              <div class="detail-title">{{ detailData.name }}</div>
              <code class="slug-code">{{ detailData.slug }}</code>
            </div>
          </div>
          <div class="detail-row">
            <span class="detail-label">描述</span>
            <span>{{ detailData.description || '暂无描述' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">分类</span>
            <el-tag size="small" :type="categoryTagType(detailData.category)">{{ categoryLabel(detailData.category) }}</el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">类型</span>
            <el-tag size="small" type="info" effect="plain">{{ skillTypeLabel(detailData.skill_type) }}</el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">版本</span>
            <span class="version-tag">v{{ detailData.version }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">下载量</span>
            <span>{{ detailData.download_count ?? detailData.install_count ?? 0 }}</span>
          </div>
          <div v-if="detailData.avg_rating" class="detail-row">
            <span class="detail-label">评分</span>
            <span class="skill-rating"><StarIcon :size="14" :stroke-width="1.5" class="star-filled" />{{ detailData.avg_rating.toFixed(1) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">创建时间</span>
            <span class="text-secondary">{{ detailData.created_at ? new Date(detailData.created_at).toLocaleString() : '—' }}</span>
          </div>
          <div v-if="detailData.prompt_template" class="detail-config">
            <span class="detail-label" style="margin-bottom: 8px; display: block;">Prompt 模板</span>
            <pre class="config-pre">{{ detailData.prompt_template }}</pre>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button v-if="detailData && isSkillInstalled(detailData)" type="success" plain disabled>
          <CheckIcon :size="14" :stroke-width="2" style="margin-right: 2px" />已安装
        </el-button>
        <el-button v-else-if="detailData" type="primary" :loading="installingId === detailData?.id" @click="installSkill(detailData!)">
          <PlusIcon :size="14" :stroke-width="1.5" style="margin-right: 2px" />安装
        </el-button>
      </template>
    </el-dialog>

    <!-- ═══════════ 执行技能链对话框 ═══════════ -->
    <el-dialog v-model="executeDialogVisible" :title="'执行：' + (executingChain?.name || '')" width="600px">
      <el-form label-width="90px">
        <el-form-item label="知识库">
          <el-select v-model="executeKbId" placeholder="可选，用于知识检索类技能" clearable style="width: 100%">
            <el-option v-for="kb in executeKnowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="输入内容">
          <el-input v-model="executeInput" type="textarea" :rows="5" placeholder="输入初始数据..." />
        </el-form-item>
        <div class="field-hint">
          不输入也可以执行，但如果技能链映射里使用了 <code v-text="'{{initial_input}}'"></code>，这里需要提供内容。
        </div>
      </el-form>
      <div v-if="executeResult !== null" class="execute-result">
        <div class="execute-result-header">
          <ZapIcon :size="15" :stroke-width="1.5" />
          <span>执行结果</span>
        </div>
        <pre class="execute-result-content">{{ typeof executeResult === 'object' ? JSON.stringify(executeResult, null, 2) : executeResult }}</pre>
      </div>
      <template #footer>
        <el-button @click="executeDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="executing" @click="executeChain">
          <PlayIcon :size="14" :stroke-width="1.5" style="margin-right: 2px" />执行
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, onDeactivated } from 'vue'
import {
  Puzzle as PuzzleIcon,
  Plus as PlusIcon,
  Search as SearchIcon,
  Play as PlayIcon,
  Trash2 as Trash2Icon,
  Link2 as Link2Icon,
  Zap as ZapIcon,
  Download as DownloadIcon,
  Check as CheckIcon,
  UploadCloud as UploadCloudIcon,
  Star as StarIcon,
  Layers as LayersIcon,
  Languages as LanguagesIcon,
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listKnowledgeBases } from '../../api/knowledgeBase'
import type { FormInstance } from 'element-plus'
import request from '../../utils/request'

const activeTab = ref('marketplace')

// ─── 批量翻译 OpenClaw 技能 ───
const translateRunning = ref(false)
const translateProgress = ref({ translated: 0, skipped: 0, failed: 0, total: 0, error: null as string | null })
const translatePercentage = computed(() => {
  const t = translateProgress.value.total
  if (t === 0) return 0
  const done = translateProgress.value.translated + translateProgress.value.skipped + translateProgress.value.failed
  return Math.min(Math.round((done / t) * 100), 100)
})

let translatePollTimer: ReturnType<typeof setInterval> | null = null

async function startBatchTranslate() {
  try {
    await ElMessageBox.confirm(
      '将使用你配置的默认 LLM 模型，对所有已导入的 OpenClaw 英文技能名称和描述进行中文翻译。已经是中文的会自动跳过。\n\n确定开始？',
      '批量翻译 OpenClaw 技能',
      { type: 'info', confirmButtonText: '开始翻译', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  translateRunning.value = true
  try {
    const res: any = await request.post('/skills/openclaw/translate-batch')
    if (res.status === 'already_running') {
      ElMessage.warning('翻译任务正在进行中')
      translateProgress.value = res.progress
    } else {
      ElMessage.success('翻译任务已启动')
      translateProgress.value = { translated: 0, skipped: 0, failed: 0, total: res.total || 0, error: null }
    }
    startTranslatePoll()
  } catch (e: any) {
    translateRunning.value = false
    const detail = e.response?.data?.detail || '启动翻译失败'
    ElMessage.error(detail)
  }
}

function startTranslatePoll() {
  if (translatePollTimer) clearInterval(translatePollTimer)
  translatePollTimer = setInterval(async () => {
    try {
      const res: any = await request.get('/skills/openclaw/translate-progress')
      translateProgress.value = res
      if (!res.running) {
        translateRunning.value = false
        if (translatePollTimer) clearInterval(translatePollTimer)
        translatePollTimer = null
        if (res.error) {
          ElMessage.error(`翻译出错: ${res.error}`)
        } else {
          ElMessage.success(`翻译完成：${res.translated} 条已翻译，${res.skipped} 条已跳过`)
          loadInstalled()
          loadMarketplace()
        }
      }
    } catch {
      /* ignore poll errors */
    }
  }, 2000)
}

// ─── 技能市场 ───
const marketSkills = ref<any[]>([])
const marketLoading = ref(false)
const marketCategory = ref('')
const marketSearch = ref('')
const marketPage = ref(1)
const marketPageSize = 15
const marketTotal = ref(0)
const skillTemplates = ref<any[]>([])

async function loadTemplates() {
  try {
    const res = await request.get('/skills/templates')
    skillTemplates.value = Array.isArray(res) ? res : []
  } catch { /* ignore */ }
}

function applyTemplate(tpl: any) {
  openPromptDialog()
  promptForm.value.name = tpl.name
  promptForm.value.slug = tpl.slug
  promptForm.value.description = tpl.description
  promptForm.value.prompt_template = tpl.prompt_template
  promptForm.value.output_format = tpl.output_format || 'text'
}

loadTemplates()
const installingId = ref<number | null>(null)

const installedSkillSlugs = ref<Set<string>>(new Set())

async function loadMarketplace() {
  marketLoading.value = true
  try {
    const [marketRes, installedRes] = await Promise.allSettled([
      request.get('/skills/marketplace', {
        params: {
          category: marketCategory.value || undefined,
          search: marketSearch.value || undefined,
          page: marketPage.value,
          page_size: marketPageSize,
        },
      }),
      request.get('/skills/installed'),
    ])
    if (marketRes.status === 'fulfilled') {
      const res: any = marketRes.value
      marketSkills.value = res.items || res.data || res || []
      marketTotal.value = res.total ?? marketSkills.value.length
    }
    if (installedRes.status === 'fulfilled') {
      const list: any[] = (installedRes.value as any).items || (installedRes.value as any).data || installedRes.value as any || []
      installedSkillSlugs.value = new Set(list.map((s: any) => s.slug || s.skill?.slug || '').filter(Boolean))
    }
  } catch {
    /* interceptor */
  } finally {
    marketLoading.value = false
  }
}

function isSkillInstalled(skill: any) {
  return installedSkillSlugs.value.has(skill.slug || '')
}

async function installSkill(skill: any) {
  installingId.value = skill.id
  try {
    await request.post('/skills/cloud-install', { skill_id: skill.id })
    installedSkillSlugs.value = new Set([...installedSkillSlugs.value, skill.slug])
    ElMessage.success(`「${skill.name}」安装成功`)
    loadMarketplace()
  } catch {
    /* interceptor */
  } finally {
    installingId.value = null
  }
}

// ─── 已安装 ───
const installedSkills = ref<any[]>([])
const installedLoading = ref(false)
const togglingId = ref<number | null>(null)

async function loadInstalled() {
  installedLoading.value = true
  try {
    const res: any = await request.get('/skills/installed')
    installedSkills.value = res.items || res.data || res || []
  } catch {
    /* interceptor */
  } finally {
    installedLoading.value = false
  }
}

async function toggleInstalled(row: any) {
  togglingId.value = row.install_id
  try {
    await request.put(`/skills/installed/${row.install_id}`, { is_active: row.is_active })
    ElMessage.success(row.is_active ? '已启用' : '已停用')
  } catch {
    row.is_active = !row.is_active
  } finally {
    togglingId.value = null
  }
}

async function uninstallSkill(row: any) {
  try {
    await ElMessageBox.confirm(`确定卸载「${row.name || row.skill_name || row.skill?.name || '该技能'}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await request.delete(`/skills/installed/${row.install_id}`)
    const slug = row.slug || row.skill?.slug
    if (slug) {
      const s = new Set(installedSkillSlugs.value)
      s.delete(slug)
      installedSkillSlugs.value = s
    }
    ElMessage.success('已卸载')
    await loadInstalled()
  } catch {
    /* interceptor */
  }
}

// ─── Prompt 技能 ───
const promptSkills = ref<any[]>([])
const promptLoading = ref(false)
const publishingId = ref<number | null>(null)
const promptDialogVisible = ref(false)
const promptSubmitting = ref(false)
const editingPrompt = ref<any>(null)
const promptFormRef = ref<FormInstance>()

const promptForm = ref({
  name: '',
  slug: '',
  description: '',
  prompt_template: '',
  output_format: 'text',
  is_public: false,
})

const promptRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  slug: [{ required: true, message: '请输入标识', trigger: 'blur' }],
  prompt_template: [{ required: true, message: '请输入 Prompt 模板', trigger: 'blur' }],
}

function autoSlug() {
  if (editingPrompt.value) return
  const raw = promptForm.value.name.trim()
  const asciiPart = raw
    .toLowerCase()
    .replace(/[\s]+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
  promptForm.value.slug = (asciiPart || `skill-${Date.now()}`).substring(0, 50)
}

async function loadPromptSkills() {
  promptLoading.value = true
  try {
    const res: any = await request.get('/skills/prompt-skills')
    promptSkills.value = res.items || res.data || res || []
  } catch {
    /* interceptor */
  } finally {
    promptLoading.value = false
  }
}

function openPromptDialog(skill?: any) {
  if (skill) {
    const config = typeof skill.config === 'string'
      ? JSON.parse(skill.config || '{}')
      : (skill.config || {})
    editingPrompt.value = skill
    promptForm.value = {
      name: skill.name,
      slug: skill.slug || '',
      description: skill.description || '',
      prompt_template: skill.prompt_template || config.prompt_template || '',
      output_format: skill.output_format || config.output_format || 'text',
      is_public: skill.is_public ?? false,
    }
  } else {
    editingPrompt.value = null
    promptForm.value = { name: '', slug: '', description: '', prompt_template: '', output_format: 'text', is_public: false }
  }
  promptDialogVisible.value = true
}

async function submitPromptSkill() {
  try {
    await promptFormRef.value?.validate()
  } catch {
    return
  }
  promptSubmitting.value = true
  try {
    if (editingPrompt.value) {
      await request.put(`/skills/${editingPrompt.value.id}`, promptForm.value)
      ElMessage.success('更新成功')
    } else {
      await request.post('/skills/prompt-skills', promptForm.value)
      ElMessage.success('创建成功')
    }
    promptDialogVisible.value = false
    await loadPromptSkills()
  } catch {
    /* interceptor */
  } finally {
    promptSubmitting.value = false
  }
}

async function deletePromptSkill(skill: any) {
  try {
    await ElMessageBox.confirm(`确定删除「${skill.name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await request.delete(`/skills/${skill.id}`)
    ElMessage.success('删除成功')
    await loadPromptSkills()
  } catch {
    /* interceptor */
  }
}

async function publishToCloud(skill: any) {
  publishingId.value = skill.id
  try {
    const res: any = await request.post(`/skills/${skill.id}/publish-to-cloud`)
    ElMessage.success(res?.message || '已提交审核，管理员通过后将出现在云端市场')
    loadPromptSkills()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : detail?.msg || e?.message || '发布失败')
  } finally {
    publishingId.value = null
  }
}

// ─── 技能链 ───
const chains = ref<any[]>([])
const chainLoading = ref(false)
const chainDialogVisible = ref(false)
const chainSubmitting = ref(false)
const chainFormRef = ref<FormInstance>()
const allSkillsForChain = ref<any[]>([])

type ChainMappingRow = { key: string; value: string }
type ChainStepForm = {
  skill_id: number | null
  output_key: string
  mapping_rows: ChainMappingRow[]
}

const chainForm = ref<{
  name: string
  description: string
  steps: ChainStepForm[]
  is_public: boolean
}>({
  name: '',
  description: '',
  steps: [createChainStep(1)],
  is_public: false,
})

const chainRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
}

const executeDialogVisible = ref(false)
const executingChain = ref<any>(null)
const executeInput = ref('')
const executeKbId = ref<number | null>(null)
const executeKnowledgeBases = ref<any[]>([])
const executeResult = ref<any>(null)
const executing = ref(false)

async function loadChains() {
  chainLoading.value = true
  try {
    const [chainsRes, skillsRes] = await Promise.allSettled([
      request.get('/skills/chains'),
      request.get('/skills/installed'),
    ])
    if (chainsRes.status === 'fulfilled') {
      const data: any = chainsRes.value
      chains.value = data.items || data.data || data || []
    }
    if (skillsRes.status === 'fulfilled') {
      const data: any = skillsRes.value
      allSkillsForChain.value = data.items || data.data || data || []
    }
  } catch {
    /* interceptor */
  } finally {
    chainLoading.value = false
  }
}

function createChainStep(index: number): ChainStepForm {
  return {
    skill_id: null,
    output_key: `step${index}`,
    mapping_rows: [],
  }
}

function parseSkillConfig(skill: any) {
  if (!skill?.config) return {}
  if (typeof skill.config === 'string') {
    try {
      return JSON.parse(skill.config)
    } catch {
      return {}
    }
  }
  return skill.config || {}
}

function getSkillVariableHints(skillId: number | null) {
  const skill = allSkillsForChain.value.find((s) => s.id === skillId)
  if (!skill) return []
  const config = parseSkillConfig(skill)
  if (skill.slug === 'knowledge_search') {
    return [{ key: 'query', value: '{{initial_input}}' }]
  }
  if (skill.slug === 'sql_query') {
    return [{ key: 'question', value: '{{initial_input}}' }]
  }
  if (Array.isArray(skill.variables) && skill.variables.length) {
    return skill.variables.map((v: string) => ({ key: v, value: v === 'query' ? '{{initial_input}}' : '' }))
  }
  if (Array.isArray(config.variables) && config.variables.length) {
    return config.variables.map((v: string) => ({ key: v, value: v === 'query' ? '{{initial_input}}' : '' }))
  }
  return []
}

function applySuggestedMapping(step: ChainStepForm, key: string, value: string) {
  const existing = step.mapping_rows.find((row) => row.key === key)
  if (existing) {
    existing.value = value
    return
  }
  step.mapping_rows.push({ key, value })
}

function openChainDialog() {
  chainForm.value = {
    name: '',
    description: '',
    steps: [createChainStep(1)],
    is_public: false,
  }
  chainDialogVisible.value = true
}

async function submitChain() {
  try {
    await chainFormRef.value?.validate()
  } catch {
    return
  }
  const validSteps = chainForm.value.steps.filter((s) => s.skill_id)
  if (!validSteps.length) {
    ElMessage.warning('请至少添加一个有效步骤')
    return
  }
  chainSubmitting.value = true
  try {
    await request.post('/skills/chains', {
      name: chainForm.value.name,
      description: chainForm.value.description,
      steps: validSteps.map((s) => ({
        skill_id: s.skill_id,
        input_mapping: s.mapping_rows
          .filter((row) => row.key.trim())
          .reduce((acc, row) => {
            acc[row.key.trim()] = row.value
            return acc
          }, {} as Record<string, string>),
        output_key: s.output_key || undefined,
      })),
      is_public: chainForm.value.is_public,
    })
    ElMessage.success('创建成功')
    chainDialogVisible.value = false
    await loadChains()
  } catch {
    /* interceptor */
  } finally {
    chainSubmitting.value = false
  }
}

function openExecuteDialog(chain: any) {
  executingChain.value = chain
  executeInput.value = ''
  executeKbId.value = null
  executeResult.value = null
  executeDialogVisible.value = true
  loadExecuteKnowledgeBases()
}

async function loadExecuteKnowledgeBases() {
  try {
    const res: any = await listKnowledgeBases()
    executeKnowledgeBases.value = res.items || res.data || res || []
  } catch {
    executeKnowledgeBases.value = []
  }
}

async function executeChain() {
  executing.value = true
  try {
    const res: any = await request.post(`/skills/chains/${executingChain.value.id}/execute`, {
      initial_input: executeInput.value,
      kb_id: executeKbId.value || undefined,
    })
    executeResult.value = res.result ?? res.output ?? res
    ElMessage.success('执行完成')
  } catch {
    /* interceptor */
  } finally {
    executing.value = false
  }
}

async function deleteChain(chain: any) {
  try {
    await ElMessageBox.confirm(`确定删除技能链「${chain.name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await request.delete(`/skills/chains/${chain.id}`)
    ElMessage.success('删除成功')
    await loadChains()
  } catch {
    /* interceptor */
  }
}

// ─── 技能详情 ───
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailData = ref<any>(null)

async function viewSkillDetail(skill: any) {
  detailVisible.value = true
  detailLoading.value = true
  detailData.value = null
  try {
    // 中心市场列表的 id 是中心服技能 ID，需走节点后端代理；本地市场 id 为本地 Skill 表主键
    const isCloud = skill.marketplace_source === 'cloud'
    const url = isCloud ? `/skills/cloud/${skill.id}` : `/skills/${skill.id}`
    const res: any = await request.get(url)
    detailData.value = res
  } catch {
    detailData.value = skill
  } finally {
    detailLoading.value = false
  }
}

// ─── 辅助 ───
function categoryLabel(cat?: string) {
  const map: Record<string, string> = {
    general: '通用', development: '开发', data: '数据', productivity: '效率',
    retrieval: '检索', creative: '创意', communication: '通信', security: '安全',
    finance: '金融', sales: '销售', utility: '工具', prompt: 'Prompt', openclaw: 'OpenClaw',
  }
  return map[cat || ''] || cat || '其他'
}

function categoryTagType(cat?: string) {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = { retrieval: '', data: 'success', utility: 'warning', general: 'info' }
  return map[cat || ''] || 'info'
}

function skillTypeLabel(type?: string) {
  const map: Record<string, string> = { builtin: '内置', prompt: 'Prompt', custom: '自定义', chain: '技能链' }
  return map[type || ''] || type || '—'
}

function handleTabChange(tab: string) {
  if (tab === 'marketplace') loadMarketplace()
  else if (tab === 'installed') loadInstalled()
  else if (tab === 'prompt') loadPromptSkills()
  else if (tab === 'chains') loadChains()
}

function switchToMarketplace() {
  activeTab.value = 'marketplace'
  loadMarketplace()
}

onActivated(() => {
  loadMarketplace()
})

onDeactivated(() => {
  if (translatePollTimer) {
    clearInterval(translatePollTimer)
    translatePollTimer = null
  }
})
</script>

<style scoped>
.skills-page {
  max-width: 1200px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.filter-group {
  display: flex;
  gap: 10px;
  align-items: center;
}

/* ── Tabs ── */
:deep(.el-tabs__item) {
  font-size: 14px;
  font-weight: 500;
}

:deep(.el-table) {
  border-radius: var(--radius);
  overflow: hidden;
}

:deep(.el-empty) {
  padding: 60px 0;
}

/* ── Skill Cards ── */
.skill-card {
  background: var(--card-bg);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-card);
  transition: box-shadow var(--duration-base) var(--ease-out),
              transform var(--duration-base) var(--ease-out),
              border-color var(--duration-base) var(--ease-out);
  display: flex;
  gap: 14px;
  height: 200px;
  cursor: pointer;
}

.skill-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-color: var(--border-color);
}

.skill-card-icon {
  flex-shrink: 0;
  width: 42px;
  height: 42px;
  border-radius: var(--radius);
  background: var(--primary-lighter);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.skill-card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.skill-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
  letter-spacing: -0.01em;
}

.skill-card-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  flex: 1;
}

.skill-card-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.skill-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: auto;
}

.skill-stats {
  display: flex;
  align-items: center;
  gap: 10px;
}

.install-count {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.skill-rating {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--el-color-warning);
  font-weight: 600;
}

.star-filled {
  fill: var(--el-color-warning);
  color: var(--el-color-warning);
}

.skills-pagination {
  margin-top: 20px;
  justify-content: flex-end;
}

/* ── Installed table ── */
.skill-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.skill-name-icon {
  color: var(--primary);
  flex-shrink: 0;
}

/* ── Prompt skills ── */
.slug-code {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-tertiary);
  background: var(--gray-100);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.prompt-textarea :deep(textarea) {
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
}

.field-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.field-hint code {
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--gray-100);
  padding: 1px 4px;
  border-radius: 3px;
  color: var(--primary);
}

.switch-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 8px;
}

/* ── Chains ── */
.chain-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chain-card {
  background: var(--card-bg);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  box-shadow: var(--shadow-card);
  transition: box-shadow var(--duration-base) var(--ease-out),
              border-color var(--duration-base) var(--ease-out);
}

.chain-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--border-color);
}

.chain-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.chain-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.chain-icon {
  color: var(--primary);
}

.chain-card-actions {
  display: flex;
  gap: 6px;
}

.chain-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  line-height: 1.5;
}

.chain-steps {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 14px;
  background: var(--gray-50);
  border-radius: var(--radius);
  border: 1px solid var(--border-subtle);
}

.chain-step-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--primary);
  background: var(--primary-lighter);
  padding: 4px 10px;
  border-radius: var(--radius-full);
}

.chain-arrow {
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 600;
}

/* ── Chain builder ── */
.chain-builder {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chain-builder-step {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  background: var(--card-bg);
}

.step-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 32px;
}

.step-number {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--primary);
  color: var(--text-inverse);
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.step-hint {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.6;
}

.step-hint code {
  font-family: var(--font-mono);
  background: var(--gray-100);
  padding: 1px 4px;
  border-radius: 4px;
}

.mapping-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mapping-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mapping-hint-chip {
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--primary-lighter);
  color: var(--primary);
  cursor: pointer;
}

/* ── Execute result ── */
.execute-result {
  margin-top: 16px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  overflow: hidden;
}

.execute-result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  background: var(--gray-50);
  border-bottom: 1px solid var(--border-subtle);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.execute-result-content {
  padding: 14px;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  background: var(--card-bg);
}

/* ── Skill detail dialog ── */
.detail-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.detail-icon {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  border-radius: var(--radius-lg);
  background: var(--primary-lighter);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.detail-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.detail-label {
  flex-shrink: 0;
  width: 64px;
  font-weight: 600;
  color: var(--text-tertiary);
  font-size: 13px;
}

.version-tag {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.text-secondary {
  color: var(--text-secondary);
  font-size: 13px;
}

.detail-config {
  margin-top: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
}

.config-pre {
  margin: 0;
  padding: 14px;
  background: var(--gray-50);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
}

/* ── Translate progress ── */
.translate-progress {
  display: flex;
  align-items: center;
  gap: 12px;
}

.translate-stats {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .skills-page {
    padding: 0 8px;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .toolbar {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .filter-group {
    flex-direction: column;
    width: 100%;
  }

  .filter-group .el-select,
  .filter-group .el-input {
    width: 100% !important;
  }

  .skill-card {
    flex-direction: column;
    gap: 10px;
  }

  .chain-steps {
    flex-direction: column;
    align-items: flex-start;
  }

  .chain-arrow {
    transform: rotate(90deg);
    align-self: center;
  }
}
</style>
