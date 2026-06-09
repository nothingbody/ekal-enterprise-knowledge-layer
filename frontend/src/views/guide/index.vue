<template>
  <div class="guide-page">
    <!-- Hero -->
    <div class="guide-hero">
      <div class="hero-icon">
        <Rocket :size="32" :stroke-width="1.5" />
      </div>
      <h1>欢迎使用企业多模态知识协作共享服务平台</h1>
      <p class="hero-desc">只需 3 步即可开始：配置模型 → 创建知识库 → 开始对话</p>
      <div style="display: flex; gap: 12px; justify-content: center; margin-top: 12px;">
        <el-button type="primary" size="large" @click="launchWizard">
          <Zap :size="16" :stroke-width="1.5" style="margin-right: 6px;" />
          启动配置向导
        </el-button>
        <el-button link type="info" class="skip-guide-btn" @click="skipGuide">
          跳过引导，直接进入
        </el-button>
      </div>
    </div>

    <!-- Quick Setup Progress Card -->
    <div v-if="readinessLoaded" class="quick-setup-card">
      <div class="qsc-header">
        <div class="qsc-title">
          <Zap :size="18" :stroke-width="1.5" />
          <span>快速配置进度</span>
          <span class="qsc-badge" :class="{ done: readinessReady }">{{ readinessCompleted }}/{{ readinessTotal }}</span>
        </div>
        <span v-if="readinessReady" class="qsc-done-label">✅ 全部就绪</span>
      </div>
      <div class="qsc-progress-bar">
        <div class="qsc-progress-fill" :style="{ width: (readinessCompleted / readinessTotal * 100) + '%' }"></div>
      </div>
      <div class="qsc-steps">
        <div
          v-for="step in readinessSteps"
          :key="step.key"
          class="qsc-step"
          :class="{ done: step.done }"
          @click="!step.done && $router.push(step.route)"
        >
          <div class="qsc-step-icon" :class="{ done: step.done }">
            <Check v-if="step.done" :size="14" :stroke-width="2.5" />
            <component v-else :is="stepIcons[step.key]" :size="14" :stroke-width="1.5" />
          </div>
          <div class="qsc-step-text">
            <span class="qsc-step-label">{{ step.label }}</span>
            <span v-if="!step.done" class="qsc-step-hint">{{ step.hint }}</span>
          </div>
          <ChevronRight v-if="!step.done" :size="14" :stroke-width="2" class="qsc-step-arrow" />
        </div>
      </div>
      <div v-if="!readinessReady" class="qsc-tip">
        <Lightbulb :size="14" :stroke-width="1.5" />
        <span>点击未完成的步骤直接跳转操作，完成后回来即可看到进度更新。</span>
      </div>
    </div>

    <!-- Role selector -->
    <div class="role-selector">
      <div
        class="role-card"
        :class="{ active: activeRole === 'admin' }"
        @click="activeRole = 'admin'"
      >
        <div class="role-icon admin-icon"><Shield :size="22" :stroke-width="1.5" /></div>
        <div>
          <h3>管理员指南</h3>
          <p>配置模型、创建工作空间、接入数据、邀请成员</p>
        </div>
      </div>
      <div
        class="role-card"
        :class="{ active: activeRole === 'employee' }"
        @click="activeRole = 'employee'"
      >
        <div class="role-icon employee-icon"><UserCheck :size="22" :stroke-width="1.5" /></div>
        <div>
          <h3>员工指南</h3>
          <p>加入工作空间、使用知识库进行智能问答</p>
        </div>
      </div>
    </div>

    <!-- ═══════════════════════════════════════ -->
    <!-- ADMIN GUIDE                            -->
    <!-- ═══════════════════════════════════════ -->
    <template v-if="activeRole === 'admin'">
      <!-- Admin flow bar -->
      <div class="flow-bar">
        <div class="flow-step" v-for="(s, i) in adminFlowSteps" :key="i" @click="scrollTo(s.anchor)">
          <div class="flow-num">{{ i + 1 }}</div>
          <span>{{ s.label }}</span>
          <ChevronRight v-if="i < adminFlowSteps.length - 1" :size="14" :stroke-width="2" class="flow-arrow" />
        </div>
      </div>

      <!-- Admin Step 1: Configure Models -->
      <section class="guide-section" id="admin-step-models">
        <div class="section-header">
          <div class="section-num">1</div>
          <div>
            <h2>配置 AI 模型</h2>
            <p class="section-desc">平台依赖 AI 模型运行，管理员需要先配置好模型才能使用其他功能。</p>
          </div>
        </div>

        <div class="model-types">
          <div class="model-type-card">
            <div class="mtc-header">
              <MessageSquare :size="20" :stroke-width="1.5" />
              <h3>LLM 对话模型 <span class="required-badge">必需</span></h3>
            </div>
            <p>用于生成对话回答，如 GPT-4o、DeepSeek、Qwen 等。没有 LLM 模型，对话功能无法使用。</p>
          </div>
          <div class="model-type-card">
            <div class="mtc-header">
              <Layers :size="20" :stroke-width="1.5" />
              <h3>Embedding 向量模型 <span class="required-badge">必需</span></h3>
            </div>
            <p>用于将文档转换为向量实现语义搜索，如 text-embedding-3-small。没有向量模型，知识库无法创建。</p>
          </div>
          <div class="model-type-card optional">
            <div class="mtc-header">
              <ArrowUpDown :size="20" :stroke-width="1.5" />
              <h3>Reranker 重排模型 <span class="optional-badge">可选</span></h3>
            </div>
            <p>对检索结果二次排序，提升回答准确率。不配置也可正常使用。</p>
          </div>
        </div>

        <h3 class="sub-title">各平台配置方法</h3>

        <el-tabs v-model="activeProvider" class="provider-tabs">
          <el-tab-pane label="DeepSeek" name="deepseek" />
          <el-tab-pane label="OpenAI" name="openai" />
          <el-tab-pane label="Ollama 本地" name="ollama" />
          <el-tab-pane label="其他兼容接口" name="custom" />
        </el-tabs>

        <!-- DeepSeek -->
        <div v-if="activeProvider === 'deepseek'" class="provider-guide">
          <div class="guide-callout tip">
            <Lightbulb :size="16" :stroke-width="1.5" />
            <span>DeepSeek 是国内优秀的大模型服务，性价比极高，推荐新手首选。</span>
          </div>
          <ol class="step-list">
            <li>
              <strong>获取 API Key</strong>
              <p>访问 <a href="https://platform.deepseek.com" target="_blank">platform.deepseek.com</a>，注册账号后在「API Keys」页面创建密钥。</p>
            </li>
            <li>
              <strong>添加 LLM 模型</strong>
              <p>进入<router-link to="/models">模型管理</router-link>页面，点击「添加模型」→ 点击「DeepSeek」快速填充按钮，粘贴你的 API Key 即可。</p>
              <div class="config-preview">
                <div class="config-row"><span class="config-label">模型类型</span><span>LLM</span></div>
                <div class="config-row"><span class="config-label">提供商</span><span>OpenAI / 兼容接口</span></div>
                <div class="config-row"><span class="config-label">显示名称</span><span>DeepSeek-V3</span></div>
                <div class="config-row"><span class="config-label">模型标识</span><span>deepseek-chat</span></div>
                <div class="config-row"><span class="config-label">API 地址</span><span>https://api.deepseek.com</span></div>
                <div class="config-row"><span class="config-label">API Key</span><span>api-key-placeholder（你的密钥）</span></div>
              </div>
            </li>
            <li>
              <strong>添加 Embedding 模型（推荐搭配 OpenAI）</strong>
              <p>DeepSeek 目前不提供 Embedding 模型，推荐搭配 OpenAI 的 text-embedding-3-small 或使用 Ollama 本地向量模型。</p>
            </li>
          </ol>
        </div>

        <!-- OpenAI -->
        <div v-if="activeProvider === 'openai'" class="provider-guide">
          <ol class="step-list">
            <li>
              <strong>获取 API Key</strong>
              <p>访问 <a href="https://platform.openai.com/api-keys" target="_blank">platform.openai.com</a>，登录后创建 API Key。</p>
            </li>
            <li>
              <strong>添加 LLM 模型</strong>
              <p>进入<router-link to="/models">模型管理</router-link>，点击「添加模型」→「OpenAI GPT-4o」快速填充。</p>
              <div class="config-preview">
                <div class="config-row"><span class="config-label">模型标识</span><span>gpt-4o</span></div>
                <div class="config-row"><span class="config-label">API 地址</span><span>https://api.openai.com/v1</span></div>
                <div class="config-row"><span class="config-label">API Key</span><span>api-key-placeholder（你的密钥）</span></div>
              </div>
            </li>
            <li>
              <strong>添加 Embedding 模型</strong>
              <p>同样在模型管理页面，点击「添加模型」→「OpenAI Embedding」快速填充，使用同一个 API Key。</p>
              <div class="config-preview">
                <div class="config-row"><span class="config-label">模型类型</span><span>Embedding</span></div>
                <div class="config-row"><span class="config-label">模型标识</span><span>text-embedding-3-small</span></div>
                <div class="config-row"><span class="config-label">API 地址</span><span>https://api.openai.com/v1</span></div>
              </div>
            </li>
          </ol>
          <div class="guide-callout tip">
            <Lightbulb :size="16" :stroke-width="1.5" />
            <span>如果你使用第三方 OpenAI 代理（如 API2D、OpenRouter），只需将 API 地址替换为代理地址即可，其他不变。</span>
          </div>
        </div>

        <!-- Ollama -->
        <div v-if="activeProvider === 'ollama'" class="provider-guide">
          <div class="guide-callout tip">
            <Lightbulb :size="16" :stroke-width="1.5" />
            <span>Ollama 允许你在本地运行开源模型，完全免费且数据不出本机，适合对隐私要求高的场景。</span>
          </div>
          <ol class="step-list">
            <li>
              <strong>安装 Ollama</strong>
              <p>访问 <a href="https://ollama.com" target="_blank">ollama.com</a> 下载并安装。安装后在终端执行：</p>
              <div class="code-block">
                <code>ollama pull qwen2.5:7b</code>
                <span class="code-comment"># 下载 LLM 模型</span>
              </div>
              <div class="code-block">
                <code>ollama pull nomic-embed-text</code>
                <span class="code-comment"># 下载 Embedding 模型</span>
              </div>
            </li>
            <li>
              <strong>添加 LLM 模型</strong>
              <p>在<router-link to="/models">模型管理</router-link>中点击「Ollama Qwen」快速填充。</p>
              <div class="config-preview">
                <div class="config-row"><span class="config-label">提供商</span><span>Ollama 本地模型</span></div>
                <div class="config-row"><span class="config-label">模型标识</span><span>qwen2.5:7b</span></div>
                <div class="config-row"><span class="config-label">API 地址</span><span>http://localhost:11434</span></div>
                <div class="config-row"><span class="config-label">API Key</span><span>（无需填写）</span></div>
              </div>
            </li>
            <li>
              <strong>添加 Embedding 模型</strong>
              <p>同样点击「Ollama Embedding」快速填充。</p>
              <div class="config-preview">
                <div class="config-row"><span class="config-label">模型类型</span><span>Embedding</span></div>
                <div class="config-row"><span class="config-label">模型标识</span><span>nomic-embed-text</span></div>
                <div class="config-row"><span class="config-label">API 地址</span><span>http://localhost:11434</span></div>
              </div>
            </li>
          </ol>
        </div>

        <!-- Custom -->
        <div v-if="activeProvider === 'custom'" class="provider-guide">
          <p>本平台兼容所有提供 OpenAI 格式 API 的服务，包括但不限于：</p>
          <div class="compat-list">
            <div class="compat-item" v-for="c in compatProviders" :key="c.name">
              <strong>{{ c.name }}</strong>
              <span class="compat-url">{{ c.apiBase }}</span>
            </div>
          </div>
          <div class="guide-callout warning">
            <TriangleAlert :size="16" :stroke-width="1.5" />
            <span>配置时将「提供商」选为「OpenAI / 兼容接口」，填入对应的 API 地址和 Key 即可。</span>
          </div>
        </div>

        <div class="action-bar">
          <el-button type="primary" @click="$router.push('/models')">
            <BrainCircuit :size="16" :stroke-width="1.5" style="margin-right:6px" />前往配置模型
          </el-button>
        </div>
      </section>

      <!-- Admin Step 2: Create Workspace -->
      <section class="guide-section" id="admin-step-workspace">
        <div class="section-header">
          <div class="section-num">2</div>
          <div>
            <h2>创建工作空间</h2>
            <p class="section-desc">工作空间是团队协作的基本单元，用于隔离不同项目或部门的数据和权限。</p>
          </div>
        </div>

        <ol class="step-list">
          <li>
            <strong>进入工作空间页面</strong>
            <p>在左侧导航栏点击<router-link to="/workspaces">工作空间</router-link>，点击「创建工作空间」。</p>
          </li>
          <li>
            <strong>填写工作空间信息</strong>
            <p>输入名称和描述，例如：「市场部」「产品文档」「客服知识库」等。</p>
          </li>
        </ol>

        <div class="guide-callout tip">
          <Lightbulb :size="16" :stroke-width="1.5" />
          <span>建议按部门或项目创建独立的工作空间，便于权限管理和数据隔离。</span>
        </div>

        <div class="action-bar">
          <el-button type="primary" @click="$router.push('/workspaces')">
            <Building2 :size="16" :stroke-width="1.5" style="margin-right:6px" />前往工作空间
          </el-button>
        </div>
      </section>

      <!-- Admin Step 3: Connect Database -->
      <section class="guide-section" id="admin-step-database">
        <div class="section-header">
          <div class="section-num">3</div>
          <div>
            <h2>接入数据库</h2>
            <p class="section-desc">将企业数据库接入平台，系统将自动同步数据并建立索引，支持对数据库内容进行智能问答。</p>
          </div>
        </div>

        <ol class="step-list">
          <li>
            <strong>添加数据库源</strong>
            <p>进入<router-link to="/databases">数据库管理</router-link>页面，点击「添加数据库」，填写连接信息（主机、端口、用户名、密码、数据库名）。</p>
          </li>
          <li>
            <strong>测试连接</strong>
            <p>填写完成后点击「测试连接」，确认数据库可以正常访问。</p>
          </li>
          <li>
            <strong>选择同步表</strong>
            <p>连接成功后，选择需要同步到知识库的数据表。系统会将表数据转换为文本并向量化。</p>
          </li>
        </ol>

        <div class="guide-callout tip">
          <Lightbulb :size="16" :stroke-width="1.5" />
          <span>目前支持 PostgreSQL 和 MySQL 数据库。建议使用只读账号连接，避免对生产数据造成影响。</span>
        </div>

        <div class="action-bar">
          <el-button type="primary" @click="$router.push('/databases')">
            <Database :size="16" :stroke-width="1.5" style="margin-right:6px" />前往数据库管理
          </el-button>
        </div>
      </section>

      <!-- Admin Step 4: Create Knowledge Base -->
      <section class="guide-section" id="admin-step-kb">
        <div class="section-header">
          <div class="section-num">4</div>
          <div>
            <h2>创建知识库</h2>
            <p class="section-desc">知识库是数据的智能索引容器。你可以通过数据库同步或上传文档两种方式填充数据。</p>
          </div>
        </div>

        <ol class="step-list">
          <li>
            <strong>创建知识库</strong>
            <p>进入<router-link to="/knowledge">知识库</router-link>页面，点击「创建知识库」，填写名称并选择 Embedding 模型。</p>
          </li>
          <li>
            <strong>导入数据（二选一或两者兼用）</strong>
            <div class="two-methods">
              <div class="method-card">
                <div class="method-header">
                  <Database :size="16" :stroke-width="1.5" />
                  <strong>方式一：数据库同步</strong>
                </div>
                <p>在数据库管理中创建数据源时，直接关联到该知识库，数据将自动同步。</p>
              </div>
              <div class="method-card">
                <div class="method-header">
                  <Upload :size="16" :stroke-width="1.5" />
                  <strong>方式二：上传文档</strong>
                </div>
                <p>进入知识库后点击「上传文档」，支持 PDF、Word、Excel、PPT、CSV、TXT、Markdown，还支持直接上传图片（PNG/JPG等）自动 OCR 识别文字。</p>
              </div>
            </div>
          </li>
          <li>
            <strong>等待处理完成</strong>
            <p>导入数据后系统会自动进行文本提取 → 分块 → 向量化。文档状态变为「已完成」即可使用。</p>
          </li>
        </ol>

        <div class="action-bar">
          <el-button type="primary" @click="$router.push('/knowledge')">
            <LibraryBig :size="16" :stroke-width="1.5" style="margin-right:6px" />前往知识库
          </el-button>
        </div>
      </section>

      <!-- Admin Step 5: Invite Members -->
      <section class="guide-section" id="admin-step-invite">
        <div class="section-header">
          <div class="section-num">5</div>
          <div>
            <h2>邀请成员</h2>
            <p class="section-desc">将团队成员添加到工作空间，他们即可使用该空间下的知识库进行问答。</p>
          </div>
        </div>

        <ol class="step-list">
          <li>
            <strong>确保成员已注册</strong>
            <p>被邀请的员工需要先在平台上注册账号。管理员也可以在<router-link to="/admin/users">用户管理</router-link>中直接创建账号。</p>
          </li>
          <li>
            <strong>添加成员到工作空间</strong>
            <p>进入<router-link to="/workspaces">工作空间</router-link>，点击进入具体的工作空间，在「成员管理」中添加成员并分配角色。</p>
          </li>
          <li>
            <strong>成员角色说明</strong>
            <div class="role-table">
              <div class="role-row header">
                <span>角色</span><span>权限</span>
              </div>
              <div class="role-row">
                <span><strong>管理员</strong></span><span>管理工作空间设置、管理成员、管理知识库</span>
              </div>
              <div class="role-row">
                <span><strong>成员</strong></span><span>使用知识库进行问答、查看数据</span>
              </div>
            </div>
          </li>
        </ol>

        <div class="guide-callout tip">
          <Lightbulb :size="16" :stroke-width="1.5" />
          <span>添加成员后，通知他们登录平台切换到对应的工作空间即可开始使用。</span>
        </div>

        <div class="action-bar">
          <el-button type="primary" @click="$router.push('/workspaces')">
            <Users :size="16" :stroke-width="1.5" style="margin-right:6px" />前往管理成员
          </el-button>
        </div>
      </section>
    </template>

    <!-- ═══════════════════════════════════════ -->
    <!-- EMPLOYEE GUIDE                         -->
    <!-- ═══════════════════════════════════════ -->
    <template v-if="activeRole === 'employee'">
      <!-- Employee flow bar -->
      <div class="flow-bar">
        <div class="flow-step" v-for="(s, i) in employeeFlowSteps" :key="i" @click="scrollTo(s.anchor)">
          <div class="flow-num">{{ i + 1 }}</div>
          <span>{{ s.label }}</span>
          <ChevronRight v-if="i < employeeFlowSteps.length - 1" :size="14" :stroke-width="2" class="flow-arrow" />
        </div>
      </div>

      <!-- Employee Step 1: Join Workspace -->
      <section class="guide-section" id="emp-step-join">
        <div class="section-header">
          <div class="section-num emp">1</div>
          <div>
            <h2>加入工作空间</h2>
            <p class="section-desc">管理员会将你添加到工作空间，你登录后即可看到。</p>
          </div>
        </div>

        <ol class="step-list">
          <li>
            <strong>注册并登录</strong>
            <p>使用管理员提供的账号信息登录平台，或通过注册页面创建账号后告知管理员。</p>
          </li>
          <li>
            <strong>切换工作空间</strong>
            <p>登录后进入<router-link to="/workspaces">工作空间</router-link>页面，选择管理员邀请你加入的工作空间。</p>
          </li>
        </ol>
      </section>

      <!-- Employee Step 2: Chat -->
      <section class="guide-section" id="emp-step-chat">
        <div class="section-header">
          <div class="section-num emp">2</div>
          <div>
            <h2>使用智能问答</h2>
            <p class="section-desc">在工作空间中选择知识库，即可基于企业数据进行智能问答。</p>
          </div>
        </div>

        <ol class="step-list">
          <li>
            <strong>进入对话页面</strong>
            <p>点击左侧导航栏的<router-link to="/chat">智能对话</router-link>，进入问答界面。</p>
          </li>
          <li>
            <strong>选择知识库</strong>
            <p>在对话界面顶部选择你要查询的知识库。不同知识库包含不同的数据，选择合适的知识库可以获得更准确的回答。</p>
          </li>
          <li>
            <strong>开始提问</strong>
            <p>在输入框中输入问题，系统会自动检索知识库中的相关内容，并结合 AI 模型生成回答。</p>
          </li>
          <li>
            <strong>查看引用来源</strong>
            <p>回答中会标注引用来源（如 <span class="cite-demo">[1]</span> <span class="cite-demo">[2]</span>），点击可查看原文出处，方便验证答案的准确性。</p>
          </li>
        </ol>

        <div class="guide-callout tip">
          <Lightbulb :size="16" :stroke-width="1.5" />
          <span>提问越具体，回答越准确。例如把「销售情况如何？」改为「2025 年 Q1 华东区的销售额是多少？」。</span>
        </div>

        <div class="action-bar">
          <el-button type="primary" @click="$router.push('/chat')">
            <MessageSquare :size="16" :stroke-width="1.5" style="margin-right:6px" />开始对话
          </el-button>
        </div>
      </section>

      <!-- Employee Step 3: Tips -->
      <section class="guide-section" id="emp-step-tips">
        <div class="section-header">
          <div class="section-num emp">3</div>
          <div>
            <h2>使用技巧</h2>
            <p class="section-desc">掌握以下技巧可以让你获得更好的问答体验。</p>
          </div>
        </div>

        <div class="tips-grid">
          <div class="tip-card">
            <div class="tip-icon"><Target :size="18" :stroke-width="1.5" /></div>
            <strong>提问要具体</strong>
            <p>越具体的问题越能得到准确回答。避免过于笼统的提问。</p>
          </div>
          <div class="tip-card">
            <div class="tip-icon"><History :size="18" :stroke-width="1.5" /></div>
            <strong>利用上下文</strong>
            <p>在同一对话中连续提问，AI 会记住之前的内容，可以用「它」「这个」等代词追问。</p>
          </div>
          <div class="tip-card">
            <div class="tip-icon"><FileCheck :size="18" :stroke-width="1.5" /></div>
            <strong>检查引用</strong>
            <p>重要信息建议点击引用标签核对原文，确保回答的准确性。</p>
          </div>
          <div class="tip-card">
            <div class="tip-icon"><RefreshCw :size="18" :stroke-width="1.5" /></div>
            <strong>重新生成</strong>
            <p>如果回答不满意，可以点击「重新生成」按钮获取新的回答。</p>
          </div>
        </div>
      </section>
    </template>

    <!-- ═══════════════════════════════════════ -->
    <!-- FAQ (shared)                           -->
    <!-- ═══════════════════════════════════════ -->
    <section class="guide-section" id="faq">
      <div class="section-header">
        <div class="section-num faq-icon">
          <CircleHelp :size="18" :stroke-width="1.5" />
        </div>
        <div>
          <h2>常见问题</h2>
        </div>
      </div>

      <el-collapse v-model="activeFaq" class="faq-collapse">
        <el-collapse-item v-for="faq in currentFaqs" :key="faq.q" :title="faq.q" :name="faq.q">
          <div v-html="faq.a" class="faq-answer"></div>
        </el-collapse-item>
      </el-collapse>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, markRaw } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Rocket, ChevronRight, MessageSquare, Layers, ArrowUpDown,
  Lightbulb, TriangleAlert, BrainCircuit, LibraryBig, CircleHelp,
  Shield, UserCheck, Building2, Database, Users, Upload,
  Target, History, FileCheck, RefreshCw, Zap, Check,
} from 'lucide-vue-next'
import { getSystemReadiness } from '../../api/system'

const route = useRoute()
const router = useRouter()
const activeRole = ref('admin')
const activeProvider = ref('deepseek')
const activeFaq = ref<string[]>([])

// ── Readiness progress ──
const readinessLoaded = ref(false)
const readinessReady = ref(false)
const readinessCompleted = ref(0)
const readinessTotal = ref(5)
const readinessSteps = ref<any[]>([])

const stepIcons: Record<string, any> = {
  llm: markRaw(BrainCircuit),
  embedding: markRaw(Layers),
  knowledge_base: markRaw(LibraryBig),
  document: markRaw(Upload),
  workspace: markRaw(Building2),
}

async function loadReadiness() {
  try {
    const res: any = await getSystemReadiness()
    readinessSteps.value = res.steps
    readinessCompleted.value = res.completed
    readinessTotal.value = res.total
    readinessReady.value = res.ready
    readinessLoaded.value = true
  } catch {
    // silent
  }
}

onMounted(loadReadiness)
watch(() => route.path, loadReadiness)

const adminFlowSteps = [
  { label: '配置模型', anchor: 'admin-step-models' },
  { label: '创建工作空间', anchor: 'admin-step-workspace' },
  { label: '接入数据库', anchor: 'admin-step-database' },
  { label: '创建知识库', anchor: 'admin-step-kb' },
  { label: '邀请成员', anchor: 'admin-step-invite' },
]

const employeeFlowSteps = [
  { label: '加入工作空间', anchor: 'emp-step-join' },
  { label: '智能问答', anchor: 'emp-step-chat' },
  { label: '使用技巧', anchor: 'emp-step-tips' },
]

const compatProviders = [
  { name: '智谱 AI (GLM)', apiBase: 'https://open.bigmodel.cn/api/paas/v4' },
  { name: '百川 AI', apiBase: 'https://api.baichuan-ai.com/v1' },
  { name: '月之暗面 (Kimi)', apiBase: 'https://api.moonshot.cn/v1' },
  { name: '零一万物 (Yi)', apiBase: 'https://api.lingyiwanwu.com/v1' },
  { name: 'Groq', apiBase: 'https://api.groq.com/openai/v1' },
  { name: 'OpenRouter', apiBase: 'https://openrouter.ai/api/v1' },
  { name: 'Together AI', apiBase: 'https://api.together.xyz/v1' },
]

const adminFaqs = [
  {
    q: '什么是 API Key？去哪里获取？',
    a: 'API Key 是调用 AI 模型服务的凭证（类似密码）。每个模型提供商都有自己的 API Key。<br>一般在提供商的官网 → 控制台 → API 管理页面创建。大多数平台新注册会赠送免费额度。',
  },
  {
    q: 'API 地址是什么？为什么不能乱填？',
    a: 'API 地址是模型服务的访问入口。不同提供商地址不同，填错会导致连接失败。<br>建议使用「快速填充」按钮自动填入正确地址，手动填写时注意不要遗漏 <code>/v1</code> 后缀。',
  },
  {
    q: 'LLM 模型和 Embedding 模型有什么区别？',
    a: '<strong>LLM（大语言模型）</strong>：负责理解问题、生成回答，类似你跟 ChatGPT 对话。<br><strong>Embedding（向量模型）</strong>：负责将文字转为数字向量，用于搜索相关文档。两者缺一不可。',
  },
  {
    q: '我没有 API Key，可以用免费的模型吗？',
    a: '可以！安装 <a href="https://ollama.com" target="_blank">Ollama</a> 即可在本地免费运行开源模型。<br>参考「Ollama 本地」配置指南，无需 API Key，完全离线运行。',
  },
  {
    q: '数据库连接需要什么权限？',
    a: '只需 SELECT（只读）权限即可。建议创建一个只读数据库账号专门用于平台连接，<br>避免使用高权限账号，确保生产数据安全。',
  },
  {
    q: '知识库的"分块策略"是什么意思？',
    a: '上传的文档会被切成小段（称为"分块"），每段独立进行向量化和检索。<br>默认参数适合大多数场景，你也可以在知识库设置中调整分块大小和重叠量。',
  },
  {
    q: '员工回答不准确怎么办？',
    a: '1. 在「检索测试」页面查看检索到的文档片段是否相关<br>2. 尝试调整分块大小（太大或太小都会影响效果）<br>3. 确保上传的文档内容确实包含相关信息<br>4. 考虑配置 Reranker 模型来提升排序准确率',
  },
]

const employeeFaqs = [
  {
    q: '我看不到任何知识库怎么办？',
    a: '请确认管理员已将你添加到工作空间，并且该工作空间下已经创建了知识库。<br>在「工作空间」页面检查你是否在正确的工作空间中。',
  },
  {
    q: '回答的内容不准确怎么办？',
    a: '1. 尝试将问题描述得更具体<br>2. 查看回答中的引用来源，确认检索到的内容是否相关<br>3. 联系管理员检查知识库的数据是否完整',
  },
  {
    q: '可以对回答进行反馈吗？',
    a: '可以！每条回答下方有「赞」和「踩」按钮，你的反馈会帮助管理员优化知识库和检索效果。',
  },
  {
    q: '对话记录会保存吗？',
    a: '会的。你的对话历史会自动保存，下次登录时可以继续之前的对话，也可以创建新的对话。',
  },
  {
    q: '我可以同时查询多个知识库吗？',
    a: '目前每次对话需要选择一个知识库。如果需要查询不同数据源的内容，可以在不同的对话中切换知识库。',
  },
]

const currentFaqs = computed(() => activeRole.value === 'admin' ? adminFaqs : employeeFaqs)

function scrollTo(anchor: string) {
  document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function skipGuide() {
  localStorage.setItem('has_visited', '1')
  router.push('/knowledge')
}

function launchWizard() {
  // Clear wizard dismissal so it shows immediately
  localStorage.removeItem('setup_wizard_dismissed')
  // Navigate to knowledge page where SetupWizard is mounted in layout
  localStorage.setItem('has_visited', '1')
  localStorage.setItem('force_setup_wizard', '1')
  router.push('/knowledge')
}
</script>

<style scoped>
.guide-page {
  max-width: 860px;
  margin: 0 auto;
  padding-bottom: 60px;
}

/* ── Hero ── */
.guide-hero {
  text-align: center;
  padding: 32px 0 16px;
}

/* ── Quick Setup Card ── */
.quick-setup-card {
  background: var(--card-bg, #fff);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 0;
  margin-bottom: 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.qsc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px 12px;
}

.qsc-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.qsc-title svg {
  color: #f59e0b;
}

.qsc-badge {
  font-size: 12px;
  font-weight: 600;
  color: #2563eb;
  background: rgba(37, 99, 235, 0.08);
  padding: 2px 8px;
  border-radius: 10px;
}

.qsc-badge.done {
  color: #059669;
  background: rgba(5, 150, 105, 0.08);
}

.qsc-done-label {
  font-size: 13px;
  color: #059669;
  font-weight: 600;
}

.qsc-progress-bar {
  height: 3px;
  background: var(--border-color);
  margin: 0 20px;
  border-radius: 2px;
  overflow: hidden;
}

.qsc-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #2563eb, #0ea5e9);
  border-radius: 2px;
  transition: width 500ms ease;
}

.qsc-steps {
  padding: 10px 14px;
}

.qsc-step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 150ms;
}

.qsc-step:hover:not(.done) {
  background: var(--hover-bg, #f7f8fa);
}

.qsc-step.done {
  cursor: default;
  opacity: 0.5;
}

.qsc-step-icon {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--hover-bg, #f2f3f5);
  color: var(--text-muted);
}

.qsc-step-icon.done {
  background: #d1fae5;
  color: #059669;
}

.qsc-step-text {
  flex: 1;
  min-width: 0;
}

.qsc-step-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.qsc-step.done .qsc-step-label {
  text-decoration: line-through;
  color: var(--text-muted);
}

.qsc-step-hint {
  display: block;
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 1px;
}

.qsc-step-arrow {
  color: var(--text-muted);
  flex-shrink: 0;
}

.qsc-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px 14px;
  font-size: 12px;
  color: var(--text-muted);
}

.hero-icon {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.guide-hero h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
  letter-spacing: -0.02em;
}

.hero-desc {
  font-size: 15px;
  color: var(--text-secondary);
  margin: 0;
}

.skip-guide-btn {
  margin-top: 12px;
  font-size: 13px;
}

/* ── Flow bar ── */
.flow-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 16px 0 32px;
}

.flow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: var(--radius-full);
  background: var(--card-bg, #fff);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  transition: all 150ms;
}

.flow-step:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.flow-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
}

.flow-arrow {
  color: var(--text-muted);
  margin: 0 4px;
}

/* ── Sections ── */
.guide-section {
  background: var(--card-bg, #fff);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 28px 32px;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
}

.section-num {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}

.section-num.faq-icon {
  background: var(--primary-lighter, #eff6ff);
  color: var(--primary);
}

.section-header h2 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.section-desc {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

/* ── Model type cards ── */
.model-types {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 28px;
}

.model-type-card {
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 16px;
  background: var(--hover-bg, #fafafa);
}

.model-type-card.optional {
  opacity: 0.75;
}

.mtc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.mtc-header h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}

.model-type-card p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.6;
}

.required-badge {
  font-size: 11px;
  background: #fef2f2;
  color: #dc2626;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.optional-badge {
  font-size: 11px;
  background: #f0fdf4;
  color: #16a34a;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}

/* ── Sub title ── */
.sub-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
}

/* ── Provider tabs ── */
.provider-tabs {
  margin-bottom: 4px;
}

:deep(.provider-tabs .el-tabs__item) {
  font-weight: 600;
}

/* ── Provider guide ── */
.provider-guide {
  padding: 4px 0 0;
}

.provider-guide > p {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 16px;
  line-height: 1.7;
}

/* ── Step list ── */
.step-list {
  padding-left: 20px;
  margin: 0 0 16px;
}

.step-list li {
  margin-bottom: 16px;
  font-size: 14px;
  color: var(--text-primary);
}

.step-list li strong {
  display: block;
  font-size: 14px;
  margin-bottom: 4px;
}

.step-list li p {
  color: var(--text-secondary);
  margin: 0 0 8px;
  line-height: 1.7;
}

.step-list li a,
.step-list li :deep(a) {
  color: var(--primary);
  text-decoration: none;
  font-weight: 500;
}

.step-list li a:hover {
  text-decoration: underline;
}

/* ── Config preview ── */
.config-preview {
  background: var(--hover-bg, #f8fafc);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px 16px;
  margin-top: 8px;
}

.config-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
  font-size: 13px;
  border-bottom: 1px dashed var(--border-color);
}

.config-row:last-child {
  border-bottom: none;
}

.config-label {
  width: 80px;
  flex-shrink: 0;
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 12px;
}

.config-row > span:last-child {
  color: var(--text-primary);
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
  font-size: 12.5px;
}

/* ── Code block ── */
.code-block {
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 10px 16px;
  margin: 8px 0;
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.code-comment {
  color: #64748b;
  font-size: 12px;
}

/* ── Callout ── */
.guide-callout {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.7;
  margin: 12px 0;
}

.guide-callout.tip {
  background: var(--callout-tip-bg, #eff6ff);
  color: var(--callout-tip-color, #1e40af);
  border: 1px solid var(--callout-tip-border, #bfdbfe);
}

.guide-callout.warning {
  background: var(--callout-warn-bg, #fffbeb);
  color: var(--callout-warn-color, #92400e);
  border: 1px solid var(--callout-warn-border, #fde68a);
}

.guide-callout svg {
  flex-shrink: 0;
  margin-top: 2px;
}

/* ── Compat list ── */
.compat-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
  margin: 12px 0 16px;
}

.compat-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 13px;
}

.compat-item strong {
  color: var(--text-primary);
}

.compat-url {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: 11px;
  color: var(--text-muted);
}

/* ── Format tags ── */
.format-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 4px 0;
}

/* ── Action bar ── */
.action-bar {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

/* ── Cite demo ── */
.cite-demo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 4px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 11px;
  font-weight: 700;
  vertical-align: super;
}

/* ── FAQ ── */
.faq-collapse {
  border: none;
}

:deep(.faq-collapse .el-collapse-item__header) {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  height: 44px;
}

.faq-answer {
  font-size: 13.5px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.faq-answer :deep(code) {
  background: var(--hover-bg, #f1f5f9);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.faq-answer :deep(a) {
  color: var(--primary);
  text-decoration: none;
}

.faq-answer :deep(a:hover) {
  text-decoration: underline;
}

/* ── Role selector ── */
.role-selector {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 8px;
}

.role-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  border: 2px solid var(--border-color);
  border-radius: 12px;
  cursor: pointer;
  background: var(--card-bg, #fff);
  transition: all 200ms;
}

.role-card:hover {
  border-color: var(--primary);
}

.role-card.active {
  border-color: var(--primary);
  background: rgba(37, 99, 235, 0.04);
  box-shadow: 0 0 0 1px var(--primary);
}

.role-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.admin-icon {
  background: #fef3c7;
  color: #d97706;
}

.employee-icon {
  background: #dbeafe;
  color: #2563eb;
}

.role-card h3 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 2px;
}

.role-card p {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
  line-height: 1.5;
}

/* ── Employee section num ── */
.section-num.emp {
  background: #2563eb;
}

/* ── Two methods cards ── */
.two-methods {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin: 8px 0;
}

.method-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px;
  background: var(--hover-bg, #fafafa);
}

.method-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  color: var(--text-primary);
}

.method-header strong {
  font-size: 13px;
}

.method-card p {
  font-size: 12.5px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.6;
}

/* ── Role table ── */
.role-table {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  margin-top: 8px;
}

.role-row {
  display: grid;
  grid-template-columns: 100px 1fr;
  padding: 10px 16px;
  font-size: 13px;
  border-bottom: 1px solid var(--border-color);
}

.role-row:last-child {
  border-bottom: none;
}

.role-row.header {
  background: var(--hover-bg, #f8fafc);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 12px;
}

/* ── Tips grid ── */
.tips-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.tip-card {
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 16px;
  background: var(--hover-bg, #fafafa);
}

.tip-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--primary-lighter, #eff6ff);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 10px;
}

.tip-card strong {
  display: block;
  font-size: 13px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.tip-card p {
  font-size: 12.5px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.6;
}

/* ── Responsive ── */
@media (max-width: 640px) {
  .guide-section {
    padding: 20px 16px;
  }

  .flow-bar {
    flex-direction: column;
  }

  .flow-arrow {
    transform: rotate(90deg);
  }

  .compat-list {
    grid-template-columns: 1fr;
  }

  .compat-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .role-selector {
    grid-template-columns: 1fr;
  }

  .two-methods {
    grid-template-columns: 1fr;
  }

  .tips-grid {
    grid-template-columns: 1fr;
  }
}

[data-theme="dark"] .guide-callout.tip {
  --callout-tip-bg: rgba(59, 130, 246, 0.1);
  --callout-tip-color: #93bbfc;
  --callout-tip-border: rgba(59, 130, 246, 0.25);
}

[data-theme="dark"] .guide-callout.warning {
  --callout-warn-bg: rgba(245, 158, 11, 0.1);
  --callout-warn-color: #fbbf24;
  --callout-warn-border: rgba(245, 158, 11, 0.25);
}
</style>
