<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <el-result icon="error" title="403" sub-title="当前身份无权访问该功能，请联系管理员分配权限">
    <template #extra>
      <el-button type="primary" @click="router.push('/dashboard')">返回工作台</el-button>
    </template>
  </el-result>
</template>