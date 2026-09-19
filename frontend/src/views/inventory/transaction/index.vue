<script setup lang="ts">
import { onMounted } from 'vue'

import { listTransactions, listWarehouses } from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { RemoteOption, Transaction } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    Transaction,
    {
      keyword: string
      transaction_type: string
      source_type: string
      warehouse_id: number | undefined
      date_from: string
      date_to: string
    }
  >((params) => listTransactions(params), {
    keyword: '',
    transaction_type: '',
    source_type: '',
    warehouse_id: undefined,
    date_from: '',
    date_to: '',
  })

const TXN_TYPES = [
  { label: '入库', value: 'IN' },
  { label: '出库', value: 'OUT' },
  { label: '移库入库', value: 'TRANSFER_IN' },
  { label: '移库出库', value: 'TRANSFER_OUT' },
  { label: '盘点调整', value: 'ADJUST' },
]

const SOURCE_TYPES = [
  { label: '采购到货', value: 'PURCHASE_RECEIPT' },
  { label: '生产完工', value: 'PRODUCTION_COMPLETION' },
  { label: '生产领料', value: 'MATERIAL_REQUISITION' },
  { label: '销售发货', value: 'SALES_SHIPMENT' },
  { label: '销售退货', value: 'SALES_RETURN' },
  { label: '移库', value: 'TRANSFER' },
  { label: '盘点', value: 'STOCKTAKE' },
  { label: '手工', value: 'MANUAL' },
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
          <span class="page-title">库存流水</span>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="物料">
          <el-input v-model="query.keyword" placeholder="物料编码 / 名称" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item label="流水类型">
          <el-select v-model="query.transaction_type" clearable placeholder="全部" style="width: 140px">
            <el-option v-for="item in TXN_TYPES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源业务">
          <el-select v-model="query.source_type" clearable placeholder="全部" style="width: 150px">
            <el-option v-for="item in SOURCE_TYPES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="仓库">
          <RemoteSelect v-model="query.warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 200px" />
        </el-form-item>
        <el-form-item label="业务日期">
          <el-date-picker v-model="query.date_from" type="date" value-format="YYYY-MM-DD" placeholder="开始" style="width: 150px" />
          <span style="margin: 0 6px">至</span>
          <el-date-picker v-model="query.date_to" type="date" value-format="YYYY-MM-DD" placeholder="结束" style="width: 150px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="流水号" prop="transaction_no" min-width="150" />
        <el-table-column label="类型" width="110">
          <template #default="{ row }"><StatusTag :status="row.transaction_type" /></template>
        </el-table-column>
        <el-table-column label="物料编码" prop="material_code" min-width="120" />
        <el-table-column label="物料名称" prop="material_name" min-width="150" />
        <el-table-column label="仓库ID" prop="warehouse_id" width="90" align="right" />
        <el-table-column label="库位ID" prop="location_id" width="90" align="right" />
        <el-table-column label="变动数量" prop="quantity_change" width="110" align="right" />
        <el-table-column label="结存数量" prop="quantity_after" width="110" align="right" />
        <el-table-column label="单位成本" prop="unit_cost" width="110" align="right" />
        <el-table-column label="业务日期" prop="biz_date" width="110" />
        <el-table-column label="来源单据" prop="source_no" min-width="140" />
        <el-table-column label="来源" width="130">
          <template #default="{ row }">
            {{ SOURCE_TYPES.find((item) => item.value === row.source_type)?.label || row.source_type }}
          </template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="140" />
        <template #empty>暂无库存流水数据</template>
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