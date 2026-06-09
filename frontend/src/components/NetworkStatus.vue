<template>
  <transition name="net-slide">
    <div v-if="!online" class="network-bar">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="1" y1="1" x2="23" y2="23"/>
        <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/>
        <path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/>
        <path d="M10.71 5.05A16 16 0 0 1 22.56 9"/>
        <path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/>
        <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
        <line x1="12" y1="20" x2="12.01" y2="20"/>
      </svg>
      <span>网络连接已断开，请检查网络设置</span>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const online = ref(navigator.onLine)

function onOnline() { online.value = true }
function onOffline() { online.value = false }

onMounted(() => {
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
})

onUnmounted(() => {
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
})
</script>

<style scoped>
.network-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  background: linear-gradient(135deg, #dc2626, #ef4444);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-sans);
  box-shadow: 0 2px 12px rgba(220, 38, 38, 0.3);
}

.net-slide-enter-active,
.net-slide-leave-active {
  transition: transform 300ms ease, opacity 300ms ease;
}
.net-slide-enter-from,
.net-slide-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>
