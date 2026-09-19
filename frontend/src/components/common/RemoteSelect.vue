<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { StyleValue } from 'vue'

import type { RemoteOption } from '@/types/erp'

/**
 * 远程下拉选择器。
 *
 * 通过传入的 `loader` 调用真实后端接口获取选项，不使用任何本地枚举假数据。
 */
const props = defineProps<{
  modelValue?: number | null
  /** 选项加载函数，参数为搜索关键字 */
  loader: (keyword: string) => Promise<RemoteOption[]>
  placeholder?: string
  clearable?: boolean
  disabled?: boolean
  style?: StyleValue
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: number | undefined): void
  (e: 'change', value: number | undefined): void
}>()

const options = ref<RemoteOption[]>([])
const loading = ref(false)

async function query(keyword = ''): Promise<void> {
  loading.value = true
  try {
    options.value = await props.loader(keyword)
  } finally {
    loading.value = false
  }
}

function onChange(value: number | undefined): void {
  emit('update:modelValue', value ?? undefined)
  emit('change', value ?? undefined)
}

onMounted(() => query())
</script>

<template>
  <el-select
    :model-value="modelValue ?? undefined"
    :style="style"
    filterable
    remote
    :remote-method="query"
    :loading="loading"
    :placeholder="placeholder || '请选择'"
    :clearable="clearable !== false"
    :disabled="disabled"
    @change="onChange"
  >
    <el-option v-for="item in options" :key="item.id" :label="item.label" :value="item.id" />
  </el-select>
</template>