<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAppStore } from '@/stores/modules/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

interface LoginUser {
  user: { display_name?: string; username?: string }
  roles?: { role_name?: string }[]
}

function readUser(): LoginUser | null {
  const raw = localStorage.getItem('bh-erp-user')
  if (!raw) return null
  try {
    return JSON.parse(raw) as LoginUser
  } catch {
    return null
  }
}

const loginUser = ref<LoginUser | null>(readUser())

function logout(): void {
  localStorage.removeItem('bh-erp-user')
  loginUser.value = null
  ElMessage.success('已退出登录')
  router.replace('/login')
}
</script>

<template>
  <div class="app-header">
    <el-button link type="primary" @click="appStore.toggleSidebar()">
      {{ appStore.sidebarCollapsed ? '展开菜单' : '收起菜单' }}
    </el-button>

    <span class="app-header__title">{{ route.meta.title ?? '' }}</span>

    <div class="app-header__right">
      <template v-if="loginUser">
        <span class="app-header__role">
          {{ (loginUser.roles ?? []).map((item) => item.role_name).filter(Boolean).join('、') || '未分配角色' }}
        </span>
        <span class="app-header__user">{{ loginUser.user.display_name || loginUser.user.username }}</span>
        <el-button link type="danger" @click="logout">退出</el-button>
      </template>
      <el-tag v-else type="info" effect="plain">未登录</el-tag>
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
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.app-header__role {
  color: #909399;
  font-size: 12px;
}

.app-header__user {
  font-weight: 600;
}
</style>
