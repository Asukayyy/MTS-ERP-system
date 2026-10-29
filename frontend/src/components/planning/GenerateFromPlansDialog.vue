<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { listWarehouses } from '@/api/inventory'
import {
  generateCompletionReportsFromPlans,
  generateDispatchOrdersFromPlans,
  generateRequisitionsFromPlans,
  listProductionPlans,
} from '@/api/planning'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { GenerationResult, ProductionPlan, RemoteOption } from '@/types/erp'

/**
 * 按生产作业计划生成单据的通用弹窗。
 *
 * - `mode='dispatch'`：每张计划生成一张派工单，整单派给智能加工中心
 * - `mode='requisition'`：按物料 BOM 直接子件生成领料单
 * - `mode='completion'`：按计划产出物料与剩余数量生成完工报告
 *
 * 生成结果是**预填草稿**：工序 / 数量 / 明细等可从计划推导的数据自动带出，
 * 需要人工决策的字段（派工的承接单位与作业人员、领料的日期与仓库、
 * 完工的报工日期与入库仓库）一律留空或取默认值，由使用者在单据编辑页确认。
 * 计划无 BOM 时不产生领料单，会在结果区以明细表显式展示，
 * 避免被误认为"生成失败"。
 */
const props = defineProps<{ mode: 'dispatch' | 'requisition' | 'completion' }>()

const emit = defineEmits<{ (e: 'generated'): void }>()

const visible = ref(false)
const loading = ref(false)
const submitting = ref(false)
const rows = ref<ProductionPlan[]>([])
const selected = ref<ProductionPlan[]>([])
const result = ref<GenerationResult | null>(null)
const warehouseId = ref<number | undefined>(undefined)
const query = reactive<{ status: string; material_id: number | undefined }>({
  status: '',
  material_id: undefined,
})

const TITLES: Record<'dispatch' | 'requisition' | 'completion', string> = {
  dispatch: '按计划生成派工单',
  requisition: '按计划生成领料单',
  completion: '按计划生成完工报告',
}

const title = TITLES[props.mode]

async function loadMakeMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, supply_type: 'MAKE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

async function loadPlans(): Promise<void> {
  loading.value = true
  try {
    const data = await listProductionPlans({
      status: query.status || undefined,
      material_id: query.material_id,
      page: 1,
      page_size: 100,
    })
    rows.value = data.items
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function open(): void {
  query.status = ''
  query.material_id = undefined
  warehouseId.value = undefined
  selected.value = []
  result.value = null
  visible.value = true
  void loadPlans()
}

function onSelectionChange(picked: ProductionPlan[]): void {
  selected.value = picked
}

function resetQuery(): void {
  query.status = 'RELEASED'
  query.material_id = undefined
  void loadPlans()
}

async function submit(): Promise<void> {
  if (selected.value.length === 0) {
    ElMessage.warning('请先勾选要生成的生产作业计划')
    return
  }
  submitting.value = true
  try {
    const planIds = selected.value.map((item) => item.id)
    if (props.mode === 'dispatch') {
      result.value = await generateDispatchOrdersFromPlans(planIds)
    } else if (props.mode === 'requisition') {
      result.value = await generateRequisitionsFromPlans(planIds, warehouseId.value ?? null)
    } else {
      result.value = await generateCompletionReportsFromPlans(planIds)
    }
    if (result.value.created_count > 0) {
      ElMessage.success(`生成完成：新建 ${result.value.created_count} 张，跳过 ${result.value.skipped_count} 张`)
      emit('generated')
    } else {
      ElMessage.warning(`未新建单据：跳过 ${result.value.skipped_count} 张，失败 ${result.value.errors.length} 张`)
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <el-dialog v-model="visible" :title="title" width="900px">
    <el-form class="filter-bar" :inline="true" @submit.prevent>
      <el-form-item label="计划状态">
        <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
          <el-option label="草稿" value="DRAFT" />
          <el-option label="已确认" value="CONFIRMED" />
          <el-option label="已下达" value="RELEASED" />
          <el-option label="执行中" value="IN_PROGRESS" />
        </el-select>
      </el-form-item>
      <el-form-item label="自制件物料">
        <RemoteSelect
          v-model="query.material_id"
          :loader="loadMakeMaterialOptions"
          placeholder="全部"
          style="width: 220px"
        />
      </el-form-item>
      <el-form-item v-if="mode === 'requisition'" label="领料仓库">
        <RemoteSelect
          v-model="warehouseId"
          :loader="loadWarehouseOptions"
          placeholder="可留空后补填"
          style="width: 220px"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="loadPlans">查询</el-button>
        <el-button @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table
      v-loading="loading"
      :data="rows"
      border
      size="small"
      max-height="360"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="45" />
      <el-table-column label="计划编号" prop="plan_no" min-width="150" />
      <el-table-column label="物料编码" prop="material_code" min-width="140" />
      <el-table-column label="物料名称" prop="material_name" min-width="140" />
      <el-table-column label="来源" width="90">
        <template #default="{ row }"><StatusTag :status="row.source_type" /></template>
      </el-table-column>
      <el-table-column label="计划数量" prop="planned_qty" width="110" align="right" />
      <el-table-column label="开始日期" prop="start_date" width="110" />
      <el-table-column label="完成日期" prop="end_date" width="110" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }"><StatusTag :status="row.status" /></template>
      </el-table-column>
      <template #empty>暂无可生成的生产作业计划</template>
    </el-table>
    <div class="generate-tip">
      已勾选 {{ selected.length }} 张。
      <template v-if="mode === 'dispatch'">
        每张计划生成一张派工单（不再按工序拆分），整单派给智能加工中心，
        派工数量取"计划量 − 已完工量"、计划起止日期沿用计划行；
        作业人员留空，由加工中心自行指派后确认开工。
      </template>
      <template v-else-if="mode === 'requisition'">
        每张计划按其 BOM 直接子件生成一条领料单，明细数量预填，
        领料日期留空（仓库可留空），请到领料单列表点"编辑"补填后再确认领料。
      </template>
      <template v-else>
        每张计划生成一条完工报告，产出物料与剩余完工数量预填，
        报工日期和入库仓库留空，请到完工报告列表点"编辑"补填后再确认入库。
      </template>
    </div>

    <template v-if="result">
      <el-divider content-position="left">生成结果</el-divider>
      <el-alert
        :type="result.created_count > 0 ? 'success' : 'warning'"
        :closable="false"
        show-icon
        :title="`新建 ${result.created_count} 张 / 跳过 ${result.skipped_count} 张 / 失败 ${result.errors.length} 张`"
      />
      <el-table v-if="result.errors.length > 0" :data="result.errors" border size="small" class="result-table">
        <el-table-column label="计划" prop="plan_no" min-width="150" />
        <el-table-column label="物料编码" prop="material_code" width="150" />
        <el-table-column label="未能生成的原因" prop="reason" min-width="200" />
      </el-table>
      <el-table v-if="result.skipped.length > 0" :data="result.skipped" border size="small" class="result-table">
        <el-table-column label="跳过的计划" prop="plan_no" min-width="150" />
        <el-table-column label="跳过原因" prop="reason" min-width="200" />
      </el-table>
    </template>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">生成草稿单据</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.generate-tip {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.result-table {
  margin-top: 8px;
}
</style>
