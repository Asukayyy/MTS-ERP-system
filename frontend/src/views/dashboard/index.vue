<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getInventoryStats, getLowStockReport, getStockSummary } from '@/api/inventory'
import {
  getPlanningStats,
  listDemands,
  listMrpResults,
  listMrpRuns,
  listMps,
  listProductionPlans,
} from '@/api/planning'
import { getSalesStats, listReturns } from '@/api/sales'
import { getProcurementStats } from '@/api/procurement'
import { listMaterials } from '@/api/system'
import StatusTag from '@/components/common/StatusTag.vue'
import { toNumber } from '@/composables/usePagedTable'
import type {
  InventoryStats,
  LowStock,
  PlanningStats,
  ProcurementStats,
  SalesReturn,
  SalesStats,
} from '@/types/erp'

/** 制造企业工作台：全部指标均来自各模块真实接口，不含任何模拟数据 */

const router = useRouter()

const loading = ref(false)
const errors = ref<string[]>([])
const planning = ref<PlanningStats | null>(null)
const inventory = ref<InventoryStats | null>(null)
const sales = ref<SalesStats | null>(null)
const procurement = ref<ProcurementStats | null>(null)
const lowStock = ref<LowStock[]>([])
const recentReturns = ref<SalesReturn[]>([])
const mpsPlanQty = ref(0)
const mrpShortageCount = ref(0)
const mrpRunNo = ref('')
const finishedStockQty = ref(0)
const demandCount = ref(0)
const inProgressPlanCount = ref(0)

/** 单个指标加载，失败时记录后端返回的真实错误 */
async function guard(label: string, task: () => Promise<void>): Promise<void> {
  try {
    await task()
  } catch (error) {
    errors.value.push(`${label}：${(error as Error).message}`)
  }
}

async function loadMpsQuantity(): Promise<void> {
  const data = await listMps({ page: 1, page_size: 200 })
  mpsPlanQty.value = data.items.reduce(
    (sum, mps) => sum + mps.items.reduce((sub, item) => sub + toNumber(item.planned_qty), 0),
    0,
  )
}

async function loadMrpShortage(): Promise<void> {
  const runs = await listMrpRuns({ page: 1, page_size: 1 })
  const run = runs.items[0]
  mrpRunNo.value = run ? run.run_no : ''
  if (!run) {
    mrpShortageCount.value = 0
    return
  }
  const results = await listMrpResults({ run_id: run.id, page: 1, page_size: 500 })
  mrpShortageCount.value = results.items.filter((row) => toNumber(row.net_requirement) > 0).length
}

async function loadFinishedStock(): Promise<void> {
  const [materials, summary] = await Promise.all([
    listMaterials({ material_type: 'FINISHED', page: 1, page_size: 200 }),
    getStockSummary(),
  ])
  const finishedIds = new Set(materials.items.map((item) => item.id))
  finishedStockQty.value = summary
    .filter((row) => finishedIds.has(row.material_id))
    .reduce((sum, row) => sum + toNumber(row.on_hand), 0)
}

async function loadAll(): Promise<void> {
  loading.value = true
  errors.value = []
  await Promise.all([
    guard('计划统计', async () => {
      planning.value = await getPlanningStats()
    }),
    guard('库存统计', async () => {
      inventory.value = await getInventoryStats()
    }),
    guard('销售统计', async () => {
      sales.value = await getSalesStats()
    }),
    guard('采购统计', async () => {
      procurement.value = await getProcurementStats()
    }),
    guard('库存预警', async () => {
      lowStock.value = await getLowStockReport()
    }),
    guard('近期退货', async () => {
      const data = await listReturns({ page: 1, page_size: 5 })
      recentReturns.value = data.items
    }),
    guard('本期 MPS 计划量', loadMpsQuantity),
    guard('MRP 缺料项', loadMrpShortage),
    guard('成品库存', loadFinishedStock),
    guard('需求总量', async () => {
      const data = await listDemands({ page: 1, page_size: 1 })
      demandCount.value = data.total
    }),
    guard('执行中生产任务', async () => {
      const data = await listProductionPlans({ status: 'IN_PROGRESS', page: 1, page_size: 1 })
      inProgressPlanCount.value = data.total
    }),
  ])
  loading.value = false
}

/** 九项核心指标（规格 §28，不含任何访问量类虚荣指标） */
const metrics = computed(() => [
  { label: '本期 MPS 计划量', value: mpsPlanQty.value, unit: '件', path: '/planning/mps', type: 'primary' },
  {
    label: 'MRP 缺料项',
    value: mrpShortageCount.value,
    unit: mrpRunNo.value ? `项（${mrpRunNo.value}）` : '项',
    path: '/planning/mrp',
    type: 'danger',
  },
  {
    label: '待采购物料',
    value: planning.value?.buy_count ?? 0,
    unit: '项',
    path: '/procurement/plan',
    type: 'warning',
  },
  {
    label: '未到货订单行',
    value: procurement.value?.pending_receipt_line_count ?? 0,
    unit: '行',
    path: '/procurement/report',
    type: 'danger',
  },
  {
    label: '待领料任务',
    value: planning.value?.open_requisition_count ?? 0,
    unit: '单',
    path: '/planning/requisition',
    type: 'warning',
  },
  {
    label: '执行中生产任务',
    value: inProgressPlanCount.value,
    unit: '单',
    path: '/planning/work-plan',
    type: 'primary',
  },
  { label: '成品库存', value: finishedStockQty.value, unit: '件', path: '/inventory/balance', type: 'success' },
  {
    label: '库存预警',
    value: inventory.value?.low_stock_count ?? lowStock.value.length,
    unit: '项',
    path: '/inventory/reorder',
    type: 'danger',
  },
  {
    label: '待发货订单',
    value: sales.value?.pending_shipment_order_count ?? 0,
    unit: '单',
    path: '/sales/order',
    type: 'warning',
  },
  {
    label: '近期退货',
    value: sales.value?.return_count ?? 0,
    unit: '单',
    path: '/sales/return',
    type: 'info',
  },
])

/** 业务流状态：需求 → MPS → MRP → BUY/MAKE → 采购/生产 → 库存 → 发货/退货 */
const flow = computed(() => [
  { title: '需求', value: demandCount.value, hint: '计划需求单', path: '/planning/demand' },
  { title: 'MPS', value: planning.value?.mps_count ?? 0, hint: '主生产计划', path: '/planning/mps' },
  { title: 'MRP', value: planning.value?.mrp_run_count ?? 0, hint: '运算批次', path: '/planning/mrp' },
  { title: 'BUY', value: planning.value?.buy_count ?? 0, hint: '采购件需求', path: '/procurement/plan' },
  { title: 'MAKE', value: planning.value?.make_count ?? 0, hint: '自制件需求', path: '/planning/work-plan' },
  { title: '采购到货', value: inventory.value?.transaction_count ?? 0, hint: '库存流水', path: '/inventory/transaction' },
  { title: '库存', value: inventory.value?.balance_count ?? 0, hint: '结存记录', path: '/inventory/balance' },
  { title: '发货/退货', value: sales.value?.shipment_count ?? 0, hint: '发货单', path: '/sales/shipment' },
])

onMounted(loadAll)
</script>

<template>
  <div v-loading="loading" class="dashboard">
    <el-alert
      v-for="(msg, index) in errors"
      :key="index"
      class="dashboard__error"
      type="error"
      :closable="false"
      :title="msg"
    />

    <el-row :gutter="12">
      <el-col v-for="item in metrics" :key="item.label" :xs="12" :sm="8" :md="6" :lg="5" :xl="4">
        <el-card class="metric" shadow="never" @click="router.push(item.path)">
          <div class="metric__label">{{ item.label }}</div>
          <div class="metric__value">
            {{ item.value }}
            <span class="metric__unit">{{ item.unit }}</span>
          </div>
          <el-progress
            v-if="item.type !== 'info'"
            :percentage="100"
            :show-text="false"
            :stroke-width="3"
            :color="`var(--el-color-${item.type})`"
          />
        </el-card>
      </el-col>
    </el-row>

    <el-card class="dashboard__block" shadow="never">
      <template #header>
        <span class="dashboard__block-title">业务流状态</span>
      </template>
      <div class="flow">
        <template v-for="(node, index) in flow" :key="node.title">
          <div class="flow__node" @click="router.push(node.path)">
            <div class="flow__title">{{ node.title }}</div>
            <div class="flow__value">{{ node.value }}</div>
            <div class="flow__hint">{{ node.hint }}</div>
          </div>
          <div v-if="index < flow.length - 1" class="flow__arrow">→</div>
        </template>
      </div>
    </el-card>

    <el-row :gutter="12">
      <el-col :xs="24" :lg="12">
        <el-card class="dashboard__block" shadow="never">
          <template #header>
            <div class="dashboard__block-header">
              <span class="dashboard__block-title">库存预警（可用量低于安全库存）</span>
              <el-button link type="primary" @click="router.push('/inventory/reorder')">去处理</el-button>
            </div>
          </template>
          <el-table :data="lowStock" size="small" border max-height="280">
            <el-table-column label="物料编码" prop="material_code" min-width="120" />
            <el-table-column label="物料名称" prop="material_name" min-width="140" />
            <el-table-column label="可用量" prop="available_quantity" width="100" align="right" />
            <el-table-column label="安全库存" prop="safety_stock" width="100" align="right" />
            <el-table-column label="缺口" width="100" align="right">
              <template #default="{ row }">
                <span class="text-danger">{{ row.shortage_qty }}</span>
              </template>
            </el-table-column>
            <template #empty>暂无库存预警</template>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card class="dashboard__block" shadow="never">
          <template #header>
            <div class="dashboard__block-header">
              <span class="dashboard__block-title">近期退货</span>
              <el-button link type="primary" @click="router.push('/sales/return')">查看全部</el-button>
            </div>
          </template>
          <el-table :data="recentReturns" size="small" border max-height="280">
            <el-table-column label="退货单号" prop="return_no" min-width="140" />
            <el-table-column label="客户" prop="customer_name" min-width="120" />
            <el-table-column label="退货日期" prop="return_date" width="110" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <StatusTag :status="row.status" />
              </template>
            </el-table-column>
            <template #empty>暂无退货记录</template>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.dashboard__error {
  margin-bottom: 12px;
}

.metric {
  margin-bottom: 12px;
  cursor: pointer;
}

.metric__label {
  color: #606266;
  font-size: 13px;
}

.metric__value {
  margin: 8px 0 10px;
  font-size: 22px;
  font-weight: 600;
}

.metric__unit {
  margin-left: 4px;
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.dashboard__block {
  margin-bottom: 12px;
}

.dashboard__block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dashboard__block-title {
  font-weight: 600;
}

.flow {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: stretch;
}

.flow__node {
  flex: 1 1 110px;
  padding: 10px 12px;
  background-color: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  cursor: pointer;
}

.flow__node:hover {
  border-color: #409eff;
}

.flow__title {
  color: #606266;
  font-size: 13px;
}

.flow__value {
  margin: 4px 0;
  font-size: 18px;
  font-weight: 600;
}

.flow__hint {
  color: #909399;
  font-size: 12px;
}

.flow__arrow {
  display: flex;
  align-items: center;
  color: #c0c4cc;
}

.text-danger {
  color: #f56c6c;
}
</style>