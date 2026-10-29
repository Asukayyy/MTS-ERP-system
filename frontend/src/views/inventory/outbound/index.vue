<script setup lang="ts">
import InoutPendingTable from '@/components/inventory/InoutPendingTable.vue'

/**
 * 出库管理：只维护「出库单」。
 *
 * 销售发货、生产领料在各自模块确认后，会在这里生成一张出库单；
 * **业务模块不再自选仓库**，由仓库管理人员在确认时决定从哪个仓库出，结存才真正减少。
 */
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">出库管理</span>
        </div>
      </template>

      <div class="form-tip">
        销售发货、生产领料确认后在此生成出库单；确认出库时选择仓库，结存才真正减少。
      </div>

      <InoutPendingTable op-type="OUTBOUND" />
    </el-card>
  </div>
</template>
