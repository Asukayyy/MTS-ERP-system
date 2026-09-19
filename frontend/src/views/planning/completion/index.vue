<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { listLocations, listWarehouses } from '@/api/inventory'
import {
  cancelCompletionReport,
  confirmCompletionReport,
  createCompletionReport,
  listCompletionReports,
  listDispatchOrders,
  listProductionPlans,
} from '@/api/planning'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { CompletionReport, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<CompletionReport, { status: string; plan_id: number | undefined }>(
    (params) => listCompletionReports(params),
    { status: '', plan_id: undefined },
  )

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, supply_type: 'MAKE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadPlanOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listProductionPlans({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.plan_no} · 物料${item.material_id}` }))
}

async function loadDispatchOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listDispatchOrders({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({
    id: item.id,
    label: `${item.dispatch_no}${item.operation ? ' · ' + item.operation : ''}`,
  }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  report_no: string
  plan_id: number | undefined
  dispatch_id: number | undefined
  material_id: number | undefined
  completed_qty: number
  qualified_qty: number
  scrap_qty: number
  warehouse_id: number | undefined
  location_id: number | undefined
  report_date: string
  remark: string
}>({
  report_no: '',
  plan_id: undefined,
  dispatch_id: undefined,
  material_id: undefined,
  completed_qty: 1,
  qualified_qty: 1,
  scrap_qty: 0,
  warehouse_id: undefined,
  location_id: undefined,
  report_date: '',
  remark: '',
})

const rules: FormRules = {
  material_id: [{ required: true, message: '请选择产出物料', trigger: 'change' }],
  completed_qty: [{ required: true, message: '请输入完工数量', trigger: 'blur' }],
  qualified_qty: [{ required: true, message: '请输入合格数量', trigger: 'blur' }],
  warehouse_id: [{ required: true, message: '请选择入库仓库', trigger: 'change' }],
  report_date: [{ required: true, message: '请选择报工日期', trigger: 'change' }],
}

async function loadLocationOptions(keyword: string): Promise<RemoteOption[]> {
  if (!form.warehouse_id) return []
  const data = await listLocations({ warehouse_id: form.warehouse_id, keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.location_code} ${item.location_name}` }))
}

function openCreate(): void {
  Object.assign(form, {
    report_no: '',
    plan_id: undefined,
    dispatch_id: undefined,
    material_id: undefined,
    completed_qty: 1,
    qualified_qty: 1,
    scrap_qty: 0,
    warehouse_id: undefined,
    location_id: undefined,
    report_date: '',
    remark: '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await createCompletionReport({
      report_no: form.report_no || null,
      plan_id: form.plan_id ?? null,
      dispatch_id: form.dispatch_id ?? null,
      material_id: form.material_id,
      completed_qty: form.completed_qty,
      qualified_qty: form.qualified_qty,
      scrap_qty: form.scrap_qty,
      warehouse_id: form.warehouse_id,
      location_id: form.location_id ?? null,
      report_date: form.report_date,
      remark: form.remark || null,
    })
    ElMessage.success('完工报告已登记')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doConfirm(row: CompletionReport): Promise<void> {
  try {
    await confirmCompletionReport(row.id)
    ElMessage.success('完工报告已确认，合格品已入库')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCancel(row: CompletionReport): Promise<void> {
  try {
    await cancelCompletionReport(row.id)
    ElMessage.success('完工报告已取消')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">完工报告</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">登记完工报告</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="作业计划">
          <RemoteSelect v-model="query.plan_id" :loader="loadPlanOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已确认" value="CONFIRMED" />
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
        <el-table-column label="报告单号" prop="report_no" min-width="150" />
        <el-table-column label="作业计划ID" prop="plan_id" width="110" align="right" />
        <el-table-column label="派工单ID" prop="dispatch_id" width="110" align="right" />
        <el-table-column label="产出物料ID" prop="material_id" width="110" align="right" />
        <el-table-column label="完工数量" prop="completed_qty" width="110" align="right" />
        <el-table-column label="合格数量" prop="qualified_qty" width="110" align="right" />
        <el-table-column label="报废数量" prop="scrap_qty" width="100" align="right" />
        <el-table-column label="入库仓库ID" prop="warehouse_id" width="110" align="right" />
        <el-table-column label="报工日期" prop="report_date" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="doConfirm(row)">
              确认入库
            </el-button>
            <el-button
              v-if="['DRAFT', 'CONFIRMED'].includes(row.status)"
              link
              type="danger"
              @click="doCancel(row)"
            >
              取消
            </el-button>
            <span v-if="!['DRAFT', 'CONFIRMED'].includes(row.status)">-</span>
          </template>
        </el-table-column>
        <template #empty>暂无完工报告数据</template>
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

    <el-dialog v-model="dialogVisible" title="登记完工报告" width="720px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="报告单号">
              <el-input v-model="form.report_no" placeholder="留空自动生成" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="报工日期" prop="report_date">
              <el-date-picker v-model="form.report_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="产出物料" prop="material_id">
              <RemoteSelect v-model="form.material_id" :loader="loadMaterialOptions" placeholder="请选择自制件" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="作业计划">
              <RemoteSelect v-model="form.plan_id" :loader="loadPlanOptions" placeholder="可选" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="派工单">
              <RemoteSelect v-model="form.dispatch_id" :loader="loadDispatchOptions" placeholder="可选" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="入库仓库" prop="warehouse_id">
              <RemoteSelect v-model="form.warehouse_id" :loader="loadWarehouseOptions" placeholder="请选择仓库" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="入库库位">
              <RemoteSelect
                v-model="form.location_id"
                :loader="loadLocationOptions"
                placeholder="可选（须先选仓库）"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="完工数量" prop="completed_qty">
              <el-input-number v-model="form.completed_qty" :min="0.0001" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合格数量" prop="qualified_qty">
              <el-input-number v-model="form.qualified_qty" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="报废数量">
              <el-input-number v-model="form.scrap_qty" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="form-tip">确认后按合格数量调用库存入库契约，写入库存流水与结存。</div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>