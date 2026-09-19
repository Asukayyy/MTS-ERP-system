<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { createDispatchOrder, listDispatchOrders, listProductionPlans, setDispatchOrderStatus } from '@/api/planning'
import { listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { DispatchOrder, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<DispatchOrder, { status: string; plan_id: number | undefined }>(
    (params) => listDispatchOrders(params),
    { status: '', plan_id: undefined },
  )

async function loadPlanOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listProductionPlans({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.plan_no} · 物料${item.material_id}` }))
}

async function loadWorkerOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  plan_id: number | undefined
  operation: string
  planned_qty: number
  worker_id: number | undefined
  planned_start: string
  planned_end: string
  remark: string
}>({
  plan_id: undefined,
  operation: '',
  planned_qty: 1,
  worker_id: undefined,
  planned_start: '',
  planned_end: '',
  remark: '',
})

const rules: FormRules = {
  planned_qty: [{ required: true, message: '请输入派工数量', trigger: 'blur' }],
  planned_start: [{ required: true, message: '请选择计划开始日期', trigger: 'change' }],
  planned_end: [{ required: true, message: '请选择计划结束日期', trigger: 'change' }],
}

function openCreate(): void {
  Object.assign(form, {
    plan_id: undefined,
    operation: '',
    planned_qty: 1,
    worker_id: undefined,
    planned_start: '',
    planned_end: '',
    remark: '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await createDispatchOrder({
      plan_id: form.plan_id ?? null,
      operation: form.operation || null,
      planned_qty: form.planned_qty,
      worker_id: form.worker_id ?? null,
      planned_start: form.planned_start,
      planned_end: form.planned_end,
      remark: form.remark || null,
    })
    ElMessage.success('派工单已新增')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function changeStatus(row: DispatchOrder, status: string): Promise<void> {
  try {
    await setDispatchOrderStatus(row.id, status)
    ElMessage.success('派工单状态已更新')
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
          <span class="page-title">派工单</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增派工单</el-button>
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
            <el-option label="已下达" value="RELEASED" />
            <el-option label="执行中" value="IN_PROGRESS" />
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
        <el-table-column label="派工单号" prop="dispatch_no" min-width="150" />
        <el-table-column label="作业计划ID" prop="plan_id" width="110" align="right" />
        <el-table-column label="工序" prop="operation" min-width="130" />
        <el-table-column label="派工数量" prop="planned_qty" width="110" align="right" />
        <el-table-column label="已完工" prop="completed_qty" width="100" align="right" />
        <el-table-column label="作业人员ID" prop="worker_id" width="110" align="right" />
        <el-table-column label="计划开始" prop="planned_start" width="110" />
        <el-table-column label="计划结束" prop="planned_end" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="changeStatus(row, 'CONFIRMED')">
              确认
            </el-button>
            <el-button v-if="row.status === 'CONFIRMED'" link type="primary" @click="changeStatus(row, 'RELEASED')">
              下达
            </el-button>
            <el-button v-if="row.status === 'RELEASED'" link type="warning" @click="changeStatus(row, 'IN_PROGRESS')">
              开工
            </el-button>
            <el-button v-if="row.status === 'IN_PROGRESS'" link type="success" @click="changeStatus(row, 'COMPLETED')">
              完工
            </el-button>
            <el-button
              v-if="['DRAFT', 'CONFIRMED', 'RELEASED'].includes(row.status)"
              link
              type="danger"
              @click="changeStatus(row, 'CANCELLED')"
            >
              取消
            </el-button>
            <span v-if="row.status === 'COMPLETED' || row.status === 'CANCELLED'">-</span>
          </template>
        </el-table-column>
        <template #empty>暂无派工单数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增派工单" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="作业计划">
          <RemoteSelect v-model="form.plan_id" :loader="loadPlanOptions" placeholder="可选" style="width: 100%" />
        </el-form-item>
        <el-form-item label="工序">
          <el-input v-model="form.operation" placeholder="如 组装 / 喷涂" />
        </el-form-item>
        <el-form-item label="派工数量" prop="planned_qty">
          <el-input-number v-model="form.planned_qty" :min="0.0001" style="width: 100%" />
        </el-form-item>
        <el-form-item label="作业人员">
          <RemoteSelect v-model="form.worker_id" :loader="loadWorkerOptions" placeholder="可选" style="width: 100%" />
        </el-form-item>
        <el-form-item label="计划开始日期" prop="planned_start">
          <el-date-picker v-model="form.planned_start" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="计划结束日期" prop="planned_end">
          <el-date-picker v-model="form.planned_end" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>