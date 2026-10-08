<script setup lang="ts">
import { onMounted } from 'vue'

import { listStockOperations, listWarehouses } from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { RemoteOption, StockOperation } from '@/types/erp'

/**
 * 库存变动记录页：流水表已删除，变动记录从库存操作单（移库+盘点）聚合展示。
 * 手工入/出库直接改结存、不留单据，不在此页展示。
 */
const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    StockOperation,
    {
      op_type: string
      warehouse_id: number | undefined
      status: string
    }
  >((params) => listStockOperations(params), {
    op_type: '',
    warehouse_id: undefined,
    status: '',
  })

const OP_TYPES = [
  { label: '移库', value: 'TRANSFER' },
  { label: '盘点', value: 'STOCKTAKE' },
]

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">库存变动记录</span>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="操作类型">
          <el-select v-model="query.op_type" clearable placeholder="全部" style="width: 140px">
            <el-option v-for="item in OP_TYPES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="仓库">
          <RemoteSelect v-model="query.warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 200px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已完成" value="COMPLETED" />
            <el-option label="已取消" value="CANCELLED" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column type="expand">
          <template #default="{ row }">
            <el-table class="nested-table" :data="row.items" border size="small">
              <el-table-column label="物料ID" prop="material_id" width="90" align="right" />
              <template v-if="row.op_type === 'TRANSFER'">
                <el-table-column label="移库数量" prop="quantity" width="110" align="right" />
              </template>
              <template v-else>
                <el-table-column label="账面数量" prop="book_qty" width="110" align="right" />
                <el-table-column label="实盘数量" prop="actual_qty" width="110" align="right" />
                <el-table-column label="差异" prop="difference" width="110" align="right" />
              </template>
              <el-table-column label="备注" prop="remark" min-width="140" />
              <template #empty>暂无明细</template>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="单号" prop="operation_no" min-width="150" />
        <el-table-column label="类型" prop="op_type" width="100">
          <template #default="{ row }">{{ OP_TYPES.find((t) => t.value === row.op_type)?.label || row.op_type }}</template>
        </el-table-column>
        <el-table-column label="源仓库ID" prop="from_warehouse_id" width="100" align="right" />
        <el-table-column label="目标/盘点仓库ID" prop="warehouse_id" width="130" align="right" />
        <el-table-column label="日期" prop="op_date" width="110" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="140" />
        <template #empty>暂无库存变动记录</template>
      </el-table>

      <div class="pager">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="changePage"
          @size-change="changeSize"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.nested-table {
  margin: 4px 0 4px 48px;
  width: calc(100% - 48px);
}
</style>
