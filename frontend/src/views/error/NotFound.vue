<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <el-result icon="warning" title="404" sub-title="页面不存在，或该功能尚未开发">
    <template #extra>
      <el-button type="primary" @click="router.push('/dashboard')">返回工作台</el-button>
    </template>
  </el-result>
</template>
