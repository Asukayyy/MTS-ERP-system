<script setup lang="ts">
/**
 * 模块占位组件。
 *
 * 当前五个业务模块页面统一使用它，只展示模块名称、说明与开发状态。
 * 模块负责人开始开发时，请直接替换自己模块 `views/<module>/index.vue` 的内容，
 * **不要修改本组件**（它被五个模块共用）。
 */
defineProps<{
  /** 模块名称，例如「销售管理」 */
  title: string
  /** 模块说明，例如「Sales Module — 功能开发中」 */
  description: string
  /** 负责人，占位阶段固定为 TBD */
  owner?: string
}>()
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <span class="module-placeholder__title">{{ title }}</span>
    </template>

    <p class="module-placeholder__desc">{{ description }}</p>

    <el-descriptions :column="2" border>
      <el-descriptions-item label="负责人">{{ owner || 'TBD' }}</el-descriptions-item>
      <el-descriptions-item label="开发状态">
        <el-tag type="info">Not Started</el-tag>
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<style scoped>
.module-placeholder__title {
  font-size: 15px;
  font-weight: 600;
}

.module-placeholder__desc {
  margin: 0 0 16px;
  color: #909399;
}
</style>
