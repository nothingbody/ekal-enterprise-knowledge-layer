<template>
  <div class="not-found">
    <div class="error-code">404</div>
    <h2>页面未找到</h2>
    <p>您访问的页面不存在或已被移除</p>
    <el-button type="primary" size="large" @click="$router.push('/')">
      返回首页
    </el-button>
    <div class="quick-links">
      <span class="quick-links-label">或前往：</span>
      <el-button link @click="$router.push('/chat')">智能对话</el-button>
      <el-button link @click="$router.push('/knowledge')">知识库</el-button>
      <el-button link @click="$router.push('/guide')">使用指南</el-button>
    </div>
  </div>
</template>

<style scoped>
.not-found {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: var(--content-bg);
  font-family: var(--font-sans);
}

.error-code {
  font-size: 120px;
  font-weight: 800;
  background: linear-gradient(135deg, var(--primary), #7c6aff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
  letter-spacing: -0.05em;
}

.not-found h2 {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin-top: 8px;
}

.not-found p {
  font-size: 15px;
  color: var(--text-muted);
  margin-bottom: 16px;
}

.quick-links {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 20px;
  font-size: 13px;
}

.quick-links-label {
  color: var(--text-muted);
}
</style>
