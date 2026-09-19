<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  createProductionPlansFromRun,
  createPurchasePlanFromRun,
  explainMrpResult,
  listMps,
  listMrpResults,
  listMrpRuns,
  runMrp,
} from '@/api/planning'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { MrpExplain, MrpResult, MrpRun, RemoteOption } from '@/types/erp'

// ---------------- 运行 MRP ----------------
async function loadMpsOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMps({ keyword, page: 1, page_size: 50 })
  return data.items
    .filter((item) => item.status !== 'CANCELLED')
    .map((item) => ({ id: item.id, label: `${item.mps_no} · ${item.mps_name ?? ''}` }))
}

const runForm = reactive<{ mps_id: number | undefined; include_sales_demand: boolean; remark: string }>({
  mps_id: undefined,
  include_sales_demand: false,
  remark: '',
})

const running = ref(false)

async function doRunMrp(): Promise<void> {
  if (runForm.mps_id === undefined && !runForm.include_sales_demand) {
    ElMessage.warning('请选择 MPS 或勾选「纳入销售订单需求」后再执行运算')
    return
  }
  running.value = true
  try {
    const run = await runMrp({
      mps_id: runForm.mps_id ?? null,
      demand_ids: [],
      include_sales_demand: runForm.include_sales_demand,
      remark: runForm.remark || null,
    })
    ElMessage.success(`MRP 运算完成：${run.run_no}，共 ${run.material_count} 条结果`)
    await loadRuns()
    selectRun(run)
    loadResults()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    running.value = false
  }
}

// ---------------- 批次历史 ----------------
const runs = ref<MrpRun[]>([])
const runsLoading = ref(false)
const currentRun = ref<MrpRun | null>(null)

async function loadRuns(): Promise<void> {
  runsLoading.value = true
  try {
    const data = await listMrpRuns({ page: 1, page_size: 20 })
    runs.value = data.items
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    runsLoading.value = false
  }
}

function selectRun(run: MrpRun): void {
  currentRun.value = run
  query.run_id = run.id
}

function onRunRowClick(run: MrpRun): void {
  selectRun(run)
  loadResults()
}

// ---------------- 运算结果 ----------------
const { loading, rows, total, page, pageSize, query, search, reset, changePage, changeSize } =
  usePagedTable<MrpResult, { run_id: number | undefined; supply_type: string; status: string }>(
    (params) => listMrpResults(params),
    { run_id: undefined, supply_type: '', status: '' },
  )

function loadResults(): Promise<void> {
  if (query.run_id === undefined) return Promise.resolve()
  return search()
}

// ---------------- 计算明细 ----------------
const explainVisible = ref(false)
const explainLoading = ref(false)
const explain = ref<MrpExplain | null>(null)

async function openExplain(materialId: number): Promise<void> {
  if (!currentRun.value) return
  explainVisible.value = true
  explainLoading.value = true
  explain.value = null
  try {
    explain.value = await explainMrpResult(currentRun.value.id, materialId)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    explainLoading.value = false
  }
}

// ---------------- 生成下游单据 ----------------
const generating = ref(false)

async function generatePurchasePlan(): Promise<void> {
  if (!currentRun.value) return
  generating.value = true
  try {
    const result = await createPurchasePlanFromRun(currentRun.value.id)
    const planNo = typeof result.plan_no === 'string' ? result.plan_no : ''
    ElMessage.success(planNo ? `采购计划已生成：${planNo}` : '采购计划已生成')
    await loadRuns()
    loadResults()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    generating.value = false
  }
}

async function generateProductionPlans(): Promise<void> {
  if (!currentRun.value) return
  generating.value = true
  try {
    const plans = await createProductionPlansFromRun(currentRun.value.id)
    ElMessage.success(`生产作业计划已生成 ${plans.length} 条`)
    await loadRuns()
    loadResults()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    generating.value = false
  }
}

onMounted(async () => {
  await loadRuns()
  if (runs.value.length) {
    selectRun(runs.value[0])
    loadResults()
  }
})
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">MRP 运算</span>
        </div>
      </template>
      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="主生产计划 MPS">
          <RemoteSelect v-model="runForm.mps_id" :loader="loadMpsOptions" placeholder="选择要展开的 MPS" style="width: 260px" />
        </el-form-item>
        <el-form-item label="运算基准">
          <el-checkbox v-model="runForm.include_sales_demand">纳入已确认销售订单需求</el-checkbox>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="runForm.remark" placeholder="可选" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="running" @click="doRunMrp">执行 MRP 运算</el-button>
        </el-form-item>
      </el-form>
      <p class="form-tip">
        运算按多层 BOM 展开，逐层计算毛需求、可用量、安全库存与净需求，并给出建议下达日期与 MAKE/BUY 分流。
      </p>
    </el-card>

    <el-card shadow="never" style="margin-top: 12px">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">运算批次历史</span>
        </div>
      </template>
      <el-table
        v-loading="runsLoading"
        :data="runs"
        border
        size="small"
        highlight-current-row
        @row-click="onRunRowClick"
      >
        <el-table-column label="批次号" prop="run_no" min-width="160" />
        <el-table-column label="MPS ID" prop="mps_id" width="100" align="right" />
        <el-table-column label="运算时间" prop="run_at" min-width="180" />
        <el-table-column label="结果条数" prop="material_count" width="110" align="right" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <template #empty>暂无 MRP 运算批次，请先执行一次运算</template>
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-top: 12px">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">
            MRP 运算结果{{ currentRun ? ` · ${currentRun.run_no}` : '' }}
          </span>
          <span class="table-toolbar__spacer" />
          <el-button :disabled="!currentRun" :loading="generating" @click="generatePurchasePlan">
            生成采购需求
          </el-button>
          <el-button :disabled="!currentRun" :loading="generating" type="primary" @click="generateProductionPlans">
            生成生产计划
          </el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="供应类型">
          <el-select v-model="query.supply_type" clearable placeholder="全部" style="width: 120px">
            <el-option label="自制 MAKE" value="MAKE" />
            <el-option label="采购 BUY" value="BUY" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已确认" value="CONFIRMED" />
            <el-option label="已下达" value="RELEASED" />
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
        <el-table-column label="层级" prop="bom_level" width="70" align="right" />
        <el-table-column label="物料ID" prop="material_id" width="100" align="right" />
        <el-table-column label="毛需求" prop="gross_requirement" width="110" align="right" />
        <el-table-column label="现有库存" prop="on_hand" width="110" align="right" />
        <el-table-column label="可用量" prop="available_quantity" width="110" align="right" />
        <el-table-column label="安全库存" prop="safety_stock" width="110" align="right" />
        <el-table-column label="净需求" prop="net_requirement" width="110" align="right" />
        <el-table-column label="建议下达量" prop="order_qty" width="120" align="right" />
        <el-table-column label="需求日期" prop="requirement_date" width="110" />
        <el-table-column label="建议下达日期" prop="planned_release_date" width="120" />
        <el-table-column label="提前期(天)" prop="lead_time_days" width="100" align="right" />
        <el-table-column label="供应" width="90">
          <template #default="{ row }"><StatusTag :status="row.supply_type" /></template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openExplain(row.material_id)">计算明细</el-button>
          </template>
        </el-table-column>
        <template #empty>
          {{ currentRun ? '该批次暂无结果' : '请选择或执行一次 MRP 运算' }}
        </template>
      </el-table>

      <div class="pager">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100, 200]"
          layout="total, sizes, prev, pager, next"
          @current-change="changePage"
          @size-change="changeSize"
        />
      </div>
    </el-card>

    <el-dialog v-model="explainVisible" title="MRP 计算明细" width="680px">
      <div v-loading="explainLoading">
        <template v-if="explain">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="物料">
              {{ explain.material_code }} {{ explain.material_name }}
            </el-descriptions-item>
            <el-descriptions-item label="层级">{{ explain.bom_level }}</el-descriptions-item>
            <el-descriptions-item label="上级物料">
              {{ explain.parent_material_code ?? '-' }} {{ explain.parent_material_name ?? '' }}
            </el-descriptions-item>
            <el-descriptions-item label="供应类型">
              <StatusTag :status="explain.supply_type" />
            </el-descriptions-item>
            <el-descriptions-item label="毛需求">{{ explain.gross_requirement }}</el-descriptions-item>
            <el-descriptions-item label="现有库存">{{ explain.on_hand }}</el-descriptions-item>
            <el-descriptions-item label="可用量">{{ explain.available_quantity }}</el-descriptions-item>
            <el-descriptions-item label="安全库存">{{ explain.safety_stock }}</el-descriptions-item>
            <el-descriptions-item label="净需求">{{ explain.net_requirement }}</el-descriptions-item>
            <el-descriptions-item label="建议下达量">{{ explain.order_qty }}</el-descriptions-item>
            <el-descriptions-item label="提前期(天)">{{ explain.lead_time_days }}</el-descriptions-item>
            <el-descriptions-item label="需求日期">{{ explain.requirement_date }}</el-descriptions-item>
            <el-descriptions-item label="建议下达日期">
              {{ explain.planned_release_date ?? '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="结果状态">
              <StatusTag :status="explain.status" />
            </el-descriptions-item>
          </el-descriptions>
          <el-alert type="info" :closable="false" show-icon style="margin-top: 12px" title="计算说明">
            <p>{{ explain.formula }}</p>
          </el-alert>
        </template>
      </div>
      <template #footer>
        <el-button @click="explainVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>