<script setup lang="ts">
import { ref } from 'vue'

import CreateInoutDialog from '@/components/inventory/CreateInoutDialog.vue'
import InoutPendingTable from '@/components/inventory/InoutPendingTable.vue'

/**
 * 出库管理：只维护「出库单」。
 *
 * - 销售发货、生产领料在各自模块确认后，会在这里生成一张出库单；
 * - 仓库也可以直接「新建出库单」（来源类型限销售发货 / 生产领料）；
 * - **业务模块不再自选仓库**，由仓库管理人员在确认时决定从哪个仓库出，结存才真正减少。
 */
const tableRef = ref<{ reload: () => void } | null>(null)
const createVisible = ref(false)

function onCreated(): void {
  tableRef.value?.reload()
}
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">出库管理</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="createVisible = true">新建出库单</el-button>
        </div>
      </template>

      <InoutPendingTable ref="tableRef" op-type="OUTBOUND" />
    </el-card>

    <CreateInoutDialog v-model="createVisible" op-type="OUTBOUND" @created="onCreated" />
  </div>
</template>
