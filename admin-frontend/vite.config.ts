import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(() => {
  const apiTarget = process.env.VITE_API_TARGET || 'http://localhost:8080'
  const basePath = process.env.VITE_BASE_PATH || '/'
  const adminApiBase = process.env.VITE_ADMIN_API_BASE
  return {
    base: basePath,
    define: {
      ...(adminApiBase ? { 'import.meta.env.VITE_ADMIN_API_BASE': JSON.stringify(adminApiBase) } : {}),
    },
    plugins: [vue()],
    server: {
      port: 5173,
      proxy: {
        // 管理后台 API：与节点后端的 /api/v1 区分，统一走 /api/central/v1 → 中心 server
        '/api/central/v1': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/central\/v1/, '/api/v1'),
        },
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
