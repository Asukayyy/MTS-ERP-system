<script setup lang="ts">
import { useRoute } from 'vue-router'

import { useAppStore } from '@/stores/modules/app'

const route = useRoute()
const appStore = useAppStore()
</script>

<template>
  <div class="app-header">
    <el-button link type="primary" @click="appStore.toggleSidebar()">
      {{ appStore.sidebarCollapsed ? '展开菜单' : '收起菜单' }}
    </el-button>

    <span class="app-header__title">{{ route.meta.title ?? '' }}</span>

    <div class="app-header__right">
      <el-tag type="success" effect="plain">转椅制造 MTS · 使用中</el-tag>
    </div>
  </div>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 0 16px;
}

.app-header__title {
  font-size: 15px;
  font-weight: 600;
}

.app-header__right {
  margin-left: auto;
}
</style>
