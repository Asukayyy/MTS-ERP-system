<script setup lang="ts">
import { ref } from 'vue'

import CreateInoutDialog from '@/components/inventory/CreateInoutDialog.vue'
import InoutPendingTable from '@/components/inventory/InoutPendingTable.vue'

/**
 * 入库管理：只维护「入库单」。
 *
 * - 采购到货、销售退货、生产完工在各自模块确认后，会在这里生成一张入库单；
 * - 仓库也可以直接「新建入库单」（来源类型限销售退货 / 采购到货 / 生产完工）；
 * - **业务模块不再自选仓库**，由仓库管理人员在确认时决定入哪个仓库，结存才真正增加。
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
          <span class="page-title">入库管理</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="createVisible = true">新建入库单</el-button>
        </div>
      </template>

      <InoutPendingTable ref="tableRef" op-type="INBOUND" />
    </el-card>

    <CreateInoutDialog v-model="createVisible" op-type="INBOUND" @created="onCreated" />
  </div>
</template>
