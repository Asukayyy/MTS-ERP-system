<script setup lang="ts">
import { useRoute } from 'vue-router'

import { listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import { useCurrentOperator } from '@/composables/useCurrentOperator'
import { useAppStore } from '@/stores/modules/app'
import type { RemoteOption } from '@/types/erp'

const route = useRoute()
const appStore = useAppStore()

const { currentOperator, clearOperator, setOperator } = useCurrentOperator()

/** 已加载过的选项 id -> 文案，用于选中时回填姓名（RemoteSelect 的 change 只给出 id） */
const optionLabels = new Map<number, string>()

/** 复用系统人员接口，与库存各页面"操作人"下拉框保持一致 */
async function loadOperatorOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  const options = data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
  options.forEach((option) => optionLabels.set(option.id, option.label))
  // 刷新后当前操作人可能不在首屏列表内，补进选项以便下拉框正确回显姓名
  const current = currentOperator.value
  if (!keyword && current && !options.some((option) => option.id === current.id)) {
    options.unshift({ id: current.id, label: current.name || `操作人 #${current.id}` })
  }
  return options
}

function onOperatorChange(value: number | undefined): void {
  if (value === undefined) {
    clearOperator()
    return
  }
  setOperator({ id: value, name: optionLabels.get(value) ?? '' })
}
</script>

<template>
  <div class="app-header">
    <el-button link type="primary" @click="appStore.toggleSidebar()">
      {{ appStore.sidebarCollapsed ? '展开菜单' : '收起菜单' }}
    </el-button>

    <span class="app-header__title">{{ route.meta.title ?? '' }}</span>

    <div class="app-header__right">
      <span class="app-header__operator-label">当前操作人</span>
      <RemoteSelect
        :model-value="currentOperator?.id ?? undefined"
        :loader="loadOperatorOptions"
        placeholder="请选择当前操作人"
        style="width: 220px"
        @change="onOperatorChange"
      />
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
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.app-header__operator-label {
  font-size: 13px;
  color: #606266;
}
</style>
