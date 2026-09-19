<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  getOrderReport,
  getPendingReceiptReport,
  getPlanReport,
  getReceiptReport,
  getSupplierEvaluationReport,
} from '@/api/procurement'
import StatusTag from '@/components/common/StatusTag.vue'
import type {
  OrderReportRow,
  PendingReceiptRow,
  PlanReportRow,
  ReceiptReportRow,
  SupplierEvaluationSummary,
} from '@/types/erp'

/** 采购报表：全部数据均来自后端报表接口，不做前端聚合或模拟 */

const activeTab = ref('pending')
const loading = ref(false)

const pendingRows = ref<PendingReceiptRow[]>([])
const planRows = ref<PlanReportRow[]>([])
const orderRows = ref<OrderReportRow[]>([])
const receiptRows = ref<ReceiptReportRow[]>([])
const evaluationRows = ref<SupplierEvaluationSummary[]>([])

const dateRange = ref<[string, string] | null>(null)

const SOURCE_LABELS: Record<string, string> = {
  MRP: 'MRP 运算',
  REORDER: '订货点补库',
  MANUAL: '手工录入',
}

function defaultRange(): [string, string] {
  const today = new Date()
  const start = new Date(today.getTime() - 30 * 24 * 3600 * 1000)
  const format = (value: Date): string => value.toISOString().slice(0, 10)
  return [format(start), format(today)]
}

async function loadPending(): Promise<void> {
  pendingRows.value = await getPendingReceiptReport()
}

async function loadPlans(): Promise<void> {
  planRows.value = await getPlanReport()
}

async function loadOrders(): Promise<void> {
  orderRows.value = await getOrderReport()
}

async function loadReceipts(): Promise<void> {
  const range = dateRange.value ?? defaultRange()
  dateRange.value = range
  receiptRows.value = await getReceiptReport(range[0], range[1])
}

async function loadEvaluations(): Promise<void> {
  evaluationRows.value = await getSupplierEvaluationReport()
}

async function loadAll(): Promise<void> {
  loading.value = true
  try {
    await Promise.all([loadPending(), loadPlans(), loadOrders(), loadReceipts(), loadEvaluations()])
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function refresh(): Promise<void> {
  try {
    if (activeTab.value === 'receipt') {
      await loadReceipts()
    } else if (activeTab.value === 'plan') {
      await loadPlans()
    } else if (activeTab.value === 'order') {
      await loadOrders()
    } else if (activeTab.value === 'evaluation') {
      await loadEvaluations()
    } else {
      await loadPending()
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(loadAll)
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">采购报表</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="refresh">刷新当前报表</el-button>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="未到货" name="pending">
          <el-table :data="pendingRows" border size="small" max-height="560">
            <el-table-column label="采购订单号" prop="order_no" min-width="150" />
            <el-table-column label="供应商" min-width="170">
              <template #default="{ row }">{{ row.supplier_name || `ID ${row.supplier_id}` }}</template>
            </el-table-column>
            <el-table-column label="物料" min-width="200">
              <template #default="{ row }">
                {{ row.material_code ? `${row.material_code} ${row.material_name ?? ''}` : `ID ${row.material_id}` }}
              </template>
            </el-table-column>
            <el-table-column label="采购数量" prop="quantity" width="110" align="right" />
            <el-table-column label="已到货" prop="received_qty" width="110" align="right" />
            <el-table-column label="未到货" width="110" align="right">
              <template #default="{ row }">
                <span class="text-danger">{{ row.remaining_qty }}</span>
              </template>
            </el-table-column>
            <el-table-column label="预计到货" prop="expected_date" width="110" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><StatusTag :status="row.status" /></template>
            </el-table-column>
            <template #empty>暂无未到货订单行</template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="采购计划执行" name="plan">
          <el-table :data="planRows" border size="small" max-height="560">
            <el-table-column label="计划编号" prop="plan_no" min-width="150" />
            <el-table-column label="计划日期" prop="plan_date" width="110" />
            <el-table-column label="物料" min-width="200">
              <template #default="{ row }">
                {{ row.material_code ? `${row.material_code} ${row.material_name ?? ''}` : `ID ${row.material_id}` }}
              </template>
            </el-table-column>
            <el-table-column label="需求数量" prop="required_qty" width="110" align="right" />
            <el-table-column label="已下单" prop="ordered_qty" width="110" align="right" />
            <el-table-column label="剩余未下单" width="120" align="right">
              <template #default="{ row }">
                <span class="text-danger">{{ row.remaining_qty }}</span>
              </template>
            </el-table-column>
            <el-table-column label="需求日期" prop="required_date" width="110" />
            <el-table-column label="来源" width="110">
              <template #default="{ row }">{{ SOURCE_LABELS[row.source_type] || row.source_type }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><StatusTag :status="row.status" /></template>
            </el-table-column>
            <template #empty>暂无采购计划数据</template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="订单到货进度" name="order">
          <el-table :data="orderRows" border size="small" max-height="560">
            <el-table-column label="采购订单号" prop="order_no" min-width="150" />
            <el-table-column label="供应商" min-width="170">
              <template #default="{ row }">{{ row.supplier_name || `ID ${row.supplier_id}` }}</template>
            </el-table-column>
            <el-table-column label="物料" min-width="200">
              <template #default="{ row }">
                {{ row.material_code ? `${row.material_code} ${row.material_name ?? ''}` : `ID ${row.material_id}` }}
              </template>
            </el-table-column>
            <el-table-column label="采购数量" prop="quantity" width="110" align="right" />
            <el-table-column label="已到货" prop="received_qty" width="110" align="right" />
            <el-table-column label="到货率" width="110" align="right">
              <template #default="{ row }">{{ row.receipt_rate }}</template>
            </el-table-column>
            <el-table-column label="金额" prop="amount" width="120" align="right" />
            <el-table-column label="下单日期" prop="order_date" width="110" />
            <el-table-column label="预计到货" prop="expected_date" width="110" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><StatusTag :status="row.status" /></template>
            </el-table-column>
            <template #empty>暂无采购订单数据</template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="到货记录" name="receipt">
          <el-form class="filter-bar" :inline="true" @submit.prevent>
            <el-form-item label="到货日期">
              <el-date-picker
                v-model="dateRange"
                type="daterange"
                value-format="YYYY-MM-DD"
                start-placeholder="起始日期"
                end-placeholder="结束日期"
                style="width: 260px"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadReceipts">查询</el-button>
            </el-form-item>
          </el-form>
          <el-table :data="receiptRows" border size="small" max-height="520">
            <el-table-column label="到货单号" prop="receipt_no" min-width="150" />
            <el-table-column label="到货日期" prop="receipt_date" width="110" />
            <el-table-column label="采购订单号" min-width="150">
              <template #default="{ row }">{{ row.order_no || '-' }}</template>
            </el-table-column>
            <el-table-column label="供应商" min-width="170">
              <template #default="{ row }">{{ row.supplier_name || `ID ${row.supplier_id}` }}</template>
            </el-table-column>
            <el-table-column label="物料" min-width="200">
              <template #default="{ row }">
                {{ row.material_code ? `${row.material_code} ${row.material_name ?? ''}` : `ID ${row.material_id}` }}
              </template>
            </el-table-column>
            <el-table-column label="到货数量" prop="quantity" width="110" align="right" />
            <el-table-column label="合格数量" prop="qualified_qty" width="110" align="right" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><StatusTag :status="row.status" /></template>
            </el-table-column>
            <template #empty>所选区间内暂无到货记录</template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="供应商评分汇总" name="evaluation">
          <el-table :data="evaluationRows" border size="small" max-height="560">
            <el-table-column label="供应商" min-width="200">
              <template #default="{ row }">{{ row.supplier_name || `ID ${row.supplier_id}` }}</template>
            </el-table-column>
            <el-table-column label="评价次数" prop="evaluation_count" width="110" align="right" />
            <el-table-column label="平均综合得分" width="130" align="right">
              <template #default="{ row }">
                <span :class="{ 'score-low': Number(row.avg_total_score) < 60 }">{{ row.avg_total_score }}</span>
              </template>
            </el-table-column>
            <el-table-column label="平均质量得分" prop="avg_quality_score" width="130" align="right" />
            <el-table-column label="平均交付得分" prop="avg_delivery_score" width="130" align="right" />
            <el-table-column label="平均价格得分" prop="avg_price_score" width="130" align="right" />
            <template #empty>暂无供应商评价数据</template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.text-danger {
  color: var(--el-color-danger);
}

.score-low {
  color: var(--el-color-danger);
  font-weight: 600;
}
</style>