import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export interface WorkspaceInfo {
  id: number
  name: string
  role?: string
  member_count?: number
  kb_count?: number
}

const STORAGE_KEY = 'current_workspace'

export const useWorkspaceStore = defineStore('workspace', () => {
  // Restore from localStorage on init
  const saved = localStorage.getItem(STORAGE_KEY)
  const initial = saved ? (() => { try { return JSON.parse(saved) } catch { return null } })() : null

  const currentWorkspace = ref<WorkspaceInfo | null>(initial)

  function setCurrent(ws: WorkspaceInfo | null) {
    currentWorkspace.value = ws
  }

  function clear() {
    currentWorkspace.value = null
  }

  // Persist to localStorage whenever workspace changes
  watch(currentWorkspace, (ws) => {
    if (ws) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ws))
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, { deep: true })

  return { currentWorkspace, setCurrent, clear }
})
