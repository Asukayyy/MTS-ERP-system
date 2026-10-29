<script setup lang="ts">
import InoutPendingTable from '@/components/inventory/InoutPendingTable.vue'

/**
 * 入库管理：只维护「入库单」。
 *
 * 采购到货、销售退货、生产完工在各自模块确认后，会在这里生成一张入库单；
 * **业务模块不再自选仓库**，由仓库管理人员在确认时决定入哪个仓库，结存才真正增加。
 */
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">入库管理</span>
        </div>
      </template>

      <div class="form-tip">
        采购到货、销售退货、生产完工确认后在此生成入库单；确认入库时选择仓库，结存才真正增加。
      </div>

      <InoutPendingTable op-type="INBOUND" />
    </el-card>
  </div>
</template>
