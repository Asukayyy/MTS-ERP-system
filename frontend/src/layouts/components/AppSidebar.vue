<script setup lang="ts">
import { useRoute } from 'vue-router'

import { useAppStore } from '@/stores/modules/app'

import { menuItems } from '../menu'

const route = useRoute()
const appStore = useAppStore()
</script>

<template>
  <el-menu
    class="app-sidebar"
    :default-active="route.path"
    :collapse="appStore.sidebarCollapsed"
    :collapse-transition="false"
    router
  >
    <template v-for="item in menuItems" :key="item.path">
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
