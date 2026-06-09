<template>
  <div class="not-found">
    <div class="error-code">404</div>
    <h2>页面未找到</h2>
    <p>您访问的页面不存在或已被移除</p>
    <el-button type="primary" size="large" @click="$router.push('/dashboard')">
      返回仪表板
    </el-button>
    <div class="quick-links">
      <span class="quick-links-label">或前往：</span>
      <el-button link @click="$router.push('/dashboard')">仪表板</el-button>
      <el-button link @click="$router.push('/users')">用户管理</el-button>
      <el-button link @click="$router.push('/organizations')">组织管理</el-button>
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
  background: #FAFBFC;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

.error-code {
  font-size: 120px;
  font-weight: 800;
  background: var(--brand-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
}

.not-found h2 {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
  margin-top: 8px;
}

.not-found p {
  font-size: 15px;
  color: #64748b;
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
  color: #64748b;
}
</style>
