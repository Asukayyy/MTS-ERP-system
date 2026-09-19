<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createProductionPlan,
  listProductionPlans,
  setProductionPlanStatus,
  updateProductionPlan,
} from '@/api/planning'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { ProductionPlan, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<ProductionPlan, { status: string; material_id: number | undefined }>(
    (params) => listProductionPlans(params),
    { status: '', material_id: undefined },
  )

async function loadMakeMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, supply_type: 'MAKE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  material_id: number | undefined
  planned_qty: number
  plan_date: string
  start_date: string
  end_date: string
  remark: string
}>({
  material_id: undefined,
  planned_qty: 1,
  plan_date: '',
  start_date: '',
  end_date: '',
  remark: '',
})

const rules: FormRules = {
  material_id: [{ required: true, message: '请选择自制件物料', trigger: 'change' }],
  planned_qty: [{ required: true, message: '请输入计划数量', trigger: 'blur' }],
  plan_date: [{ required: true, message: '请选择计划日期', trigger: 'change' }],
  start_date: [{ required: true, message: '请选择开始日期', trigger: 'change' }],
  end_date: [{ required: true, message: '请选择完成日期', trigger: 'change' }],
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    material_id: undefined,
    planned_qty: 1,
    plan_date: '',
    start_date: '',
    end_date: '',
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: ProductionPlan): void {
  editingId.value = row.id
  Object.assign(form, {
    material_id: row.material_id,
    planned_qty: toNumber(row.planned_qty),
    plan_date: row.plan_date,
    start_date: row.start_date,
    end_date: row.end_date,
    remark: row.remark ?? '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editingId.value === null) {
      await createProductionPlan({
        material_id: form.material_id,
        planned_qty: form.planned_qty,
        plan_date: form.plan_date,
        start_date: form.start_date,
        end_date: form.end_date,
        remark: form.remark || null,
      })
      ElMessage.success('生产作业计划已新增')
    } else {
      await updateProductionPlan(editingId.value, {
        planned_qty: form.planned_qty,
        plan_date: form.plan_date,
        start_date: form.start_date,
        end_date: form.end_date,
        remark: form.remark || null,
      })
      ElMessage.success('生产作业计划已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function changeStatus(row: ProductionPlan, status: string): Promise<void> {
  try {
    await setProductionPlanStatus(row.id, status)
    ElMessage.success('作业计划状态已更新')
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
          <span class="page-title">生产作业计划</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增作业计划</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="自制件物料">
          <RemoteSelect v-model="query.material_id" :loader="loadMakeMaterialOptions" placeholder="全部" style="width: 220px" />
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
        <el-table-column label="计划编号" prop="plan_no" min-width="150" />
        <el-table-column label="物料ID" prop="material_id" width="100" align="right" />
        <el-table-column label="来源" width="100">
          <template #default="{ row }"><StatusTag :status="row.source_type" /></template>
        </el-table-column>
        <el-table-column label="计划数量" prop="planned_qty" width="110" align="right" />
        <el-table-column label="已完工" prop="completed_qty" width="100" align="right" />
        <el-table-column label="计划日期" prop="plan_date" width="110" />
        <el-table-column label="开始日期" prop="start_date" width="110" />
        <el-table-column label="完成日期" prop="end_date" width="110" />
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
              开始执行
            </el-button>
            <el-button v-if="row.status === 'IN_PROGRESS'" link type="success" @click="changeStatus(row, 'COMPLETED')">
              完成
            </el-button>
            <el-button
              v-if="['DRAFT', 'CONFIRMED', 'RELEASED'].includes(row.status)"
              link
              type="danger"
              @click="changeStatus(row, 'CANCELLED')"
            >
              取消
            </el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无生产作业计划数据</template>
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

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增生产作业计划' : '修改生产作业计划'" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="自制件物料" prop="material_id">
          <RemoteSelect v-model="form.material_id" :loader="loadMakeMaterialOptions" :disabled="editingId !== null" style="width: 100%" />
        </el-form-item>
        <el-form-item label="计划数量" prop="planned_qty">
          <el-input-number v-model="form.planned_qty" :min="0.0001" style="width: 100%" />
        </el-form-item>
        <el-form-item label="计划日期" prop="plan_date">
          <el-date-picker v-model="form.plan_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="开始日期" prop="start_date">
          <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="完成日期" prop="end_date">
          <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
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