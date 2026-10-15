<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAppStore } from '@/stores/modules/app'
import { hasPermission } from '@/utils/auth'

import { menuItems } from '../menu'
import type { MenuItem } from '../menu'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

/**
 * 从路由表读取页面所需权限码（`router/routes.ts` 的 `meta.perm`）。
 * 菜单配置不重复声明权限，避免两处漂移。
 */
function permOf(path: string): string | string[] | undefined {
  const matched = router.resolve(path).matched
  return matched[matched.length - 1]?.meta.perm
}

/** 按当前账号权限过滤菜单：无权限的页面不展示，子项全被过滤掉的分组一并隐藏 */
const visibleMenu = computed<MenuItem[]>(() =>
  menuItems.reduce<MenuItem[]>((acc, item) => {
    if (!item.children || item.children.length === 0) {
      if (hasPermission(permOf(item.path))) acc.push(item)
      return acc
    }
    const children = item.children.filter((child) => hasPermission(permOf(child.path)))
    if (children.length > 0) acc.push({ ...item, children })
    return acc
  }, []),
)
</script>

<template>
  <el-menu
    class="app-sidebar"
    :default-active="route.path"
    :collapse="appStore.sidebarCollapsed"
    :collapse-transition="false"
    router
  >
    <template v-for="item in visibleMenu" :key="item.path">
      <el-sub-menu v-if="item.children && item.children.length" :index="item.path">
        <template #title>
          <span class="app-sidebar__label">{{ item.title }}</span>
        </template>
        <el-menu-item v-for="child in item.children" :key="child.path" :index="child.path">
          <span class="app-sidebar__label">{{ child.title }}</span>
        </el-menu-item>
      </el-sub-menu>
      <el-menu-item v-else :index="item.path">
        <span class="app-sidebar__label">{{ item.title }}</span>
      </el-menu-item>
    </template>
  </el-menu>
</template>

<style scoped>
.app-sidebar {
  flex: 1;
  overflow-y: auto;
  border-right: none;
}

.app-sidebar__label {
  white-space: nowrap;
}
</style>