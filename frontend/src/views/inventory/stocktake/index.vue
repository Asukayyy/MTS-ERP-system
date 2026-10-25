<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getStocktakeSummary, listWarehouses } from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StockOperations from '@/views/inventory/stock-operations/index.vue'
import type { RemoteOption, StocktakeSummary } from '@/types/erp'

/**
 * 盘点页：上方为盘点单操作（新建 / 确认 / 取消），下方为盘点汇总（盘盈盘亏报表）。
 *
 * 汇总只统计**已确认**的盘点单，差异口径 = 实盘 − 账面：
 * 正数盘盈、负数盘亏；差异金额 = 差异数量 × 物料标准成本。
 */
const dateRange = ref<[string, string] | null>(null)
const warehouseId = ref<number | undefined>()

const loading = ref(false)
const summary = ref<StocktakeSummary | null>(null)

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const params: Record<string, unknown> = {}
    if (dateRange.value && dateRange.value.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    if (warehouseId.value) params.warehouse_id = warehouseId.value
    summary.value = await getStocktakeSummary(params)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function reset(): void {
  dateRange.value = null
  warehouseId.value = undefined
  load()
}

function num(value: unknown): string {
  return Number(value ?? 0).toFixed(2)
}

function signed(value: unknown, digits = 2): string {
  const n = Number(value ?? 0)
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`
}

function percent(value: unknown): string {
  return `${(Number(value ?? 0) * 100).toFixed(2)}%`
}

function resultType(result: string): 'success' | 'danger' | 'info' {
  if (result === 'GAIN') return 'success'
  if (result === 'LOSS') return 'danger'
  return 'info'
}

function resultLabel(result: string): string {
  if (result === 'GAIN') return '盘盈'
  if (result === 'LOSS') return '盘亏'
  return '相符'
}

onMounted(load)
</script>

<template>
  <div>
    <StockOperations op-type="STOCKTAKE" />

    <el-card shadow="never" style="margin-top: 12px">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">盘点汇总（盘盈盘亏，仅统计已确认盘点单）</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="load">刷新</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="盘点日期">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 260px"
          />
        </el-form-item>
        <el-form-item label="仓库">
          <RemoteSelect v-model="warehouseId" :loader="loadWarehouseOptions" placeholder="全部" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-descriptions v-loading="loading" :column="4" border size="small">
        <el-descriptions-item label="盘点单数">{{ summary?.operation_count ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="明细行数">{{ summary?.line_count ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="账实相符行数">{{ summary?.matched_count ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="账实相符率">{{ percent(summary?.accuracy_rate) }}</el-descriptions-item>

        <el-descriptions-item label="盘盈（行 / 数量）">
          {{ summary?.gain_count ?? 0 }} 行 / +{{ num(summary?.gain_qty) }}
        </el-descriptions-item>
        <el-descriptions-item label="盘亏（行 / 数量）">
          {{ summary?.loss_count ?? 0 }} 行 / -{{ num(summary?.loss_qty) }}
        </el-descriptions-item>
        <el-descriptions-item label="盘盈金额">+{{ num(summary?.gain_amount) }}</el-descriptions-item>
        <el-descriptions-item label="盘亏金额">-{{ num(summary?.loss_amount) }}</el-descriptions-item>

        <el-descriptions-item label="净盈亏数量">{{ signed(summary?.net_qty) }}</el-descriptions-item>
        <el-descriptions-item label="净差异金额">{{ signed(summary?.net_amount) }}</el-descriptions-item>
      </el-descriptions>
      <div style="margin-top: 8px; font-size: 12px; color: #909399">
        差异金额 = 差异数量 × 物料标准成本；物料未维护标准成本时金额为 0。
      </div>

      <el-table v-loading="loading" :data="summary?.items ?? []" border size="small" style="margin-top: 12px">
        <el-table-column label="盘点单号" prop="operation_no" min-width="160" />
        <el-table-column label="日期" prop="op_date" width="110" />
        <el-table-column label="仓库" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.warehouse_code }} {{ row.warehouse_name }}</template>
        </el-table-column>
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="150" />
        <el-table-column label="账面数" prop="book_qty" width="100" align="right" />
        <el-table-column label="实盘数" prop="actual_qty" width="100" align="right" />
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">{{ signed(row.difference) }}</template>
        </el-table-column>
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag :type="resultType(row.result)" size="small">{{ resultLabel(row.result) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="单价" prop="standard_cost" width="100" align="right" />
        <el-table-column label="差异金额" width="110" align="right">
          <template #default="{ row }">{{ signed(row.diff_amount) }}</template>
        </el-table-column>
        <template #empty>暂无已确认的盘点记录</template>
      </el-table>
    </el-card>
  </div>
</template>
