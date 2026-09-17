<script setup lang="ts">
import { useAppStore } from '@/stores/modules/app'

import AppHeader from './components/AppHeader.vue'
import AppSidebar from './components/AppSidebar.vue'

const appStore = useAppStore()
</script>

<template>
  <el-container class="basic-layout">
    <el-aside class="basic-layout__aside" :width="appStore.sidebarCollapsed ? '64px' : '220px'">
      <div class="basic-layout__logo">{{ appStore.sidebarCollapsed ? 'BH' : 'BH-ERP' }}</div>
      <AppSidebar />
    </el-aside>

    <el-container>
      <el-header class="basic-layout__header" height="56px">
        <AppHeader />
      </el-header>

      <el-main class="basic-layout__main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.basic-layout {
  height: 100%;
}

.basic-layout__aside {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #ffffff;
  border-right: 1px solid #e4e7ed;
  transition: width 0.2s;
}

.basic-layout__logo {
  height: 56px;
  line-height: 56px;
  padding: 0 16px;
  font-size: 16px;
  font-weight: 600;
  color: #409eff;
  white-space: nowrap;
  border-bottom: 1px solid #e4e7ed;
}

.basic-layout__header {
  display: flex;
  align-items: center;
  padding: 0;
  background-color: #ffffff;
  border-bottom: 1px solid #e4e7ed;
}

.basic-layout__main {
  padding: 16px;
  overflow: auto;
  background-color: #f5f7fa;
}
</style>
