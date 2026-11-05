<script setup lang="ts">
import { ref } from 'vue'
import { RefreshRight, Search } from '@element-plus/icons-vue'

import { listStockJournal, listWarehouses } from '@/api/inventory'
import { usePagedTable } from '@/composables/usePagedTable'
import { fmtQty } from '@/utils/format'
import StatusTag from '@/components/common/StatusTag.vue'
import type { StockJournal, Warehouse } from '@/types/erp'

/**
 * 库存变动流水：展示任何导致 inv_balance.quantity 变化的动作，
 * 包括手工入库/出库、采购收货、销售出库、移库、盘点调整、自动补库触发的出库等。
 *
 * 所有操作统一记录在 inv_stock_journal 表，调用 increase_stock / decrease_stock /
 * _apply_adjust / 移库确认 / 盘点确认 时在同一事务内追加，因此不会出现
 * 业务成功但流水丢失的情况。
 */

const warehouses = ref<Warehouse[]>([])

async function loadWarehouses() {
  const data = await listWarehouses({ page: 1, page_size: 100 })
  warehouses.value = data.items
}
loadWarehouses()

const { loading, rows, total, page, pageSize, query, search, reset, changePage, changeSize } =
  usePagedTable<
    StockJournal,
    {
      keyword: string
      warehouse_id: number | undefined
      direction: string
      date_from: string
      date_to: string
    }
  >(
    (params) => listStockJournal(params),
    { keyword: '', warehouse_id: undefined, direction: '', date_from: '', date_to: '' },
  )

function fmtBeforeAfter(row: StockJournal) {
  return `${fmtQty(row.qty_before)} → ${fmtQty(row.qty_after)}`
}

const DIRECTION_LABEL: Record<string, { label: string; type: 'success' | 'danger' | 'warning' }> = {
  IN: { label: '入库', type: 'success' },
  OUT: { label: '出库', type: 'danger' },
  ADJUST: { label: '调整', type: 'warning' },
}
</script>

<template>
  <div class="p-4">
    <!-- 筛选区 -->
    <el-card shadow="never" class="mb-3">
      <el-form
        :inline="true"
        :model="query"
        @submit.prevent="search"
        class="flex flex-wrap gap-x-2 gap-y-1"
      >
        <el-form-item label="关键字">
          <el-input
            v-model="query.keyword"
            placeholder="物料编码/名称/单据号"
            clearable
            style="width: 200px"
            @keyup.enter="search"
          />
        </el-form-item>
        <el-form-item label="仓库">
          <el-select
            v-model="query.warehouse_id"
            placeholder="全部"
            clearable
            style="width: 180px"
          >
            <el-option
              v-for="w in warehouses"
              :key="w.id"
              :value="w.id"
              :label="`${w.warehouse_code} ${w.warehouse_name}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="方向">
          <el-select v-model="query.direction" placeholder="全部" clearable style="width: 110px">
            <el-option label="入库" value="IN" />
            <el-option label="出库" value="OUT" />
            <el-option label="调整" value="ADJUST" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker
            v-model="query.date_from"
            type="date"
            placeholder="起"
            value-format="YYYY-MM-DD"
            style="width: 140px"
          />
          <span class="mx-1 text-gray-400">~</span>
          <el-date-picker
            v-model="query.date_to"
            type="date"
            placeholder="止"
            value-format="YYYY-MM-DD"
            style="width: 140px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="search">查询</el-button>
          <el-button :icon="RefreshRight" @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-card shadow="never">
      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="日期" prop="op_date" width="110" sortable />
        <el-table-column label="物料编码" prop="material_code" min-width="140" sortable />
        <el-table-column label="物料名称" prop="material_name" min-width="150" sortable />
        <el-table-column label="仓库" min-width="170" sortable prop="warehouse_name">
          <template #default="{ row }">
            {{ row.warehouse_name || `ID ${row.warehouse_id}` }}
            <span style="color: #98a2ad; font-size: 12px; margin-left: 4px" v-if="row.warehouse_code">
              ({{ row.warehouse_code }})
            </span>
          </template>
        </el-table-column>
        <el-table-column label="方向" width="80" align="center" sortable prop="direction">
          <template #default="{ row }">
            <StatusTag
              v-if="DIRECTION_LABEL[row.direction]"
              :status="DIRECTION_LABEL[row.direction].type"
            >
              {{ DIRECTION_LABEL[row.direction].label }}
            </StatusTag>
            <span v-else>{{ row.direction }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数量变化" width="110" align="right" sortable>
          <template #default="{ row }">
            <span
              :style="{
                color: row.delta_qty > 0 ? '#16a34a' : row.delta_qty < 0 ? '#dc2626' : '#64748b',
                fontWeight: 500,
              }"
            >
              {{ row.delta_qty > 0 ? '+' : '' }}{{ fmtQty(row.delta_qty) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="结存变化" width="160" align="center">
          <template #default="{ row }">
            {{ fmtBeforeAfter(row) }}
          </template>
        </el-table-column>
        <el-table-column label="来源模块" width="100" align="center" sortable prop="source_module">
          <template #default="{ row }">{{ row.source_module || '—' }}</template>
        </el-table-column>
        <el-table-column label="来源类型" width="120" sortable prop="source_type">
          <template #default="{ row }">{{ row.source_type || '—' }}</template>
        </el-table-column>
        <el-table-column label="来源单据号" min-width="150" sortable prop="source_no">
          <template #default="{ row }">{{ row.source_no || '—' }}</template>
        </el-table-column>
        <el-table-column label="备注" min-width="180">
          <template #default="{ row }">{{ row.remark || '—' }}</template>
        </el-table-column>
        <template #empty>暂无库存变动记录</template>
      </el-table>

      <div class="flex justify-end mt-3">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="total"
          :current-page="page"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="changePage"
          @size-change="changeSize"
        />
      </div>
    </el-card>
  </div>
</template>
