import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/inter/800.css'
import '@fontsource/inter/900.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/jetbrains-mono/600.css'
import './styles/global.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { ElMessage } from 'element-plus'

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Error]', err, '\nComponent:', instance, '\nInfo:', info)
  const message = err instanceof Error ? err.message : String(err)
  // Chunk loading failures (lazy-loaded routes) — suggest page reload
  if (message.includes('Failed to fetch dynamically imported module') ||
      message.includes('Loading chunk')) {
    ElMessage.error('页面资源加载失败，请刷新页面重试')
    return
  }
  // Network errors
  if (message.includes('Network Error') || message.includes('Failed to fetch')) {
    ElMessage.error('网络连接失败，请检查网络设置')
    return
  }
}

// Capture unhandled promise rejections globally
window.addEventListener('unhandledrejection', (event) => {
  console.error('[Unhandled Rejection]', event.reason)
  // Suppress noisy rejections that are already handled via axios interceptors
  if (event.reason?.name === 'CanceledError' ||
      event.reason?.code === 'ERR_CANCELED') {
    event.preventDefault()
    return
  }
  const message = event.reason instanceof Error ? event.reason.message : String(event.reason)
  if (message.includes('Failed to fetch dynamically imported module')) {
    ElMessage.error('页面资源加载失败，请刷新页面重试')
    event.preventDefault()
  }
})

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')

if ((window as any).__APP_LOAD_TIMER) {
  clearTimeout((window as any).__APP_LOAD_TIMER)
}
