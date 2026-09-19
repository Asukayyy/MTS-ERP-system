<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goDashboard() {
  router.push('/dashboard')
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-page__card" shadow="never">
      <template #header>
        <span class="login-page__title">BH-ERP 登录</span>
      </template>

      <el-alert
        type="info"
        :closable="false"
        title="当前为简化登录，不校验权限"
        description="后端已提供 POST /api/v1/system/auth/login（简化版登录），但全系统不做 Authorization 校验；本页面用于建立「登录前 / 登录后」的路由结构。"
      />

      <el-button class="login-page__button" type="primary" @click="goDashboard">
        暂时跳过，进入工作台
      </el-button>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background-color: #f5f7fa;
}

.login-page__card {
  width: 420px;
}

.login-page__title {
  font-size: 16px;
  font-weight: 600;
}

.login-page__button {
  width: 100%;
  margin-top: 20px;
}
</style>
