import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 应用级 UI 状态。
 *
 * 只放全局布局相关的状态；各模块的业务状态请在自己模块内新建 store，
 * 不要往这里堆，避免多人同时改同一个文件。
 */
export const useAppStore = defineStore('app', () => {
  /** 侧边栏是否折叠 */
  const sidebarCollapsed = ref(false)

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return {
    sidebarCollapsed,
    toggleSidebar,
  }
})
