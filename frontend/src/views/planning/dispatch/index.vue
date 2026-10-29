<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  batchDeleteDispatchOrders,
  createDispatchOrder,
  deleteDispatchOrder,
  listDispatchOrders,
  listProductionPlans,
  setDispatchOrderStatus,
  updateDispatchOrder,
} from '@/api/planning'
import { listPersonnel, listOrganizationsFlat } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import GenerateFromPlansDialog from '@/components/planning/GenerateFromPlansDialog.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
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

/** 承接单位只列加工中心与车间：派工整单下给加工中心，再由其指派具体作业人员。 */
async function loadOrgOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listOrganizationsFlat()
  const keywordText = keyword.trim()
  return data
    .filter((item) => item.status === 'ACTIVE' && ['FACTORY', 'WORKSHOP'].includes(item.org_type))
    .filter(
      (item) =>
        !keywordText ||
        item.org_code.includes(keywordText) ||
        item.org_name.includes(keywordText),
    )
    .slice(0, 50)
    .map((item) => ({ id: item.id, label: `${item.org_code} ${item.org_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const generateRef = ref<InstanceType<typeof GenerateFromPlansDialog>>()
const form = reactive<{
  plan_id: number | undefined
  operation: string
  planned_qty: number
  worker_id: number | undefined
  org_id: number | undefined
  planned_start: string | null
  planned_end: string | null
  remark: string
}>({
  plan_id: undefined,
  operation: '',
  planned_qty: 1,
  worker_id: undefined,
  org_id: undefined,
  planned_start: null,
  planned_end: null,
  remark: '',
})

// 日期与作业人员为草稿阶段可留空的字段，由人工指定；确认前服务端会校验
const rules: FormRules = {
  planned_qty: [{ required: true, message: '请输入派工数量', trigger: 'blur' }],
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    plan_id: undefined,
    operation: '',
    planned_qty: 1,
    worker_id: undefined,
    org_id: undefined,
    planned_start: null,
    planned_end: null,
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: DispatchOrder): void {
  editingId.value = row.id
  Object.assign(form, {
    plan_id: row.plan_id ?? undefined,
    operation: row.operation ?? '',
    planned_qty: toNumber(row.planned_qty),
    worker_id: row.worker_id ?? undefined,
    org_id: row.org_id ?? undefined,
    planned_start: row.planned_start ?? null,
    planned_end: row.planned_end ?? null,
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
      await createDispatchOrder({
        plan_id: form.plan_id ?? null,
        operation: form.operation || null,
        planned_qty: form.planned_qty,
        worker_id: form.worker_id ?? null,
        org_id: form.org_id ?? null,
        planned_start: form.planned_start || null,
        planned_end: form.planned_end || null,
        remark: form.remark || null,
      })
      ElMessage.success('派工单已新增')
    } else {
      await updateDispatchOrder(editingId.value, {
        operation: form.operation || null,
        planned_qty: form.planned_qty,
        worker_id: form.worker_id ?? null,
        org_id: form.org_id ?? null,
        planned_start: form.planned_start || null,
        planned_end: form.planned_end || null,
        remark: form.remark || null,
      })
      ElMessage.success('派工单已修改')
    }
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

// ---------------- 删除（仅草稿 / 已取消可删） ----------------
const selection = ref<DispatchOrder[]>([])

function onSelectionChange(rows: DispatchOrder[]): void {
  selection.value = rows
}

function isDeletable(row: DispatchOrder): boolean {
  return ['DRAFT', 'CANCELLED'].includes(row.status)
}

async function remove(row: DispatchOrder): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除派工单「${row.dispatch_no}」？`, '删除确认', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteDispatchOrder(row.id)
    ElMessage.success('派工单已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function removeSelected(): Promise<void> {
  const ids = selection.value.map((item) => item.id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${ids.length} 张派工单？`, '批量删除确认', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    const result = await batchDeleteDispatchOrders(ids)
    if (result.skipped.length) {
      ElMessage.warning(
        `已删除 ${result.deleted_count} 条，${result.skipped.length} 条未删除：${result.skipped
          .map((item) => item.reason)
          .join('；')}`,
      )
    } else {
      ElMessage.success(`已删除 ${result.deleted_count} 张派工单`)
    }
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
          <el-button :disabled="!selection.length" type="danger" plain @click="removeSelected">
            删除选中
          </el-button>
          <el-button @click="generateRef?.open()">按计划生成</el-button>
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

      <el-table
        v-loading="loading"
        :data="rows"
        border
        size="small"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="44" :selectable="isDeletable" />
        <el-table-column label="派工单号" prop="dispatch_no" min-width="150" />
        <el-table-column label="来源" width="90">
          <template #default="{ row }"><StatusTag :status="row.source_type" /></template>
        </el-table-column>
        <el-table-column label="作业计划编号" prop="plan_no" min-width="150" />
        <el-table-column label="承接单位" prop="org_name" min-width="140">
          <template #default="{ row }">{{ row.org_name ?? '待指派' }}</template>
        </el-table-column>
        <el-table-column label="工序" prop="operation" min-width="130">
          <template #default="{ row }">{{ row.operation ?? '整单' }}</template>
        </el-table-column>
        <el-table-column label="派工数量" prop="planned_qty" width="110" align="right" />
        <el-table-column label="已完工" prop="completed_qty" width="100" align="right" />
        <el-table-column label="作业人员" prop="worker_name" width="120">
          <template #default="{ row }">{{ row.worker_name ?? '待指派' }}</template>
        </el-table-column>
        <el-table-column label="计划开始" prop="planned_start" width="110">
          <template #default="{ row }">{{ row.planned_start || '待填写' }}</template>
        </el-table-column>
        <el-table-column label="计划结束" prop="planned_end" width="110">
          <template #default="{ row }">{{ row.planned_end || '待填写' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="330" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="openEdit(row)">
              编辑
            </el-button>
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
            <el-button v-if="isDeletable(row)" link type="danger" @click="remove(row)">删除</el-button>
            <span v-if="row.status === 'COMPLETED'">-</span>
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

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增派工单' : '编辑派工单'" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="作业计划">
          <RemoteSelect
            v-model="form.plan_id"
            :loader="loadPlanOptions"
            :disabled="editingId !== null"
            placeholder="可选"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="工序">
          <el-input v-model="form.operation" placeholder="整单派工时留空" />
        </el-form-item>
        <el-form-item label="派工数量" prop="planned_qty">
          <el-input-number v-model="form.planned_qty" :min="0.0001" style="width: 100%" />
        </el-form-item>
        <el-form-item label="承接单位">
          <RemoteSelect
            v-model="form.org_id"
            :loader="loadOrgOptions"
            placeholder="留空默认智能加工中心"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="作业人员">
          <RemoteSelect v-model="form.worker_id" :loader="loadWorkerOptions" placeholder="由加工中心指派，可留空" style="width: 100%" />
        </el-form-item>
        <el-form-item label="计划开始日期" prop="planned_start">
          <el-date-picker
            v-model="form.planned_start"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="确认前必填"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="计划结束日期" prop="planned_end">
          <el-date-picker
            v-model="form.planned_end"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="确认前必填"
            style="width: 100%"
          />
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

    <GenerateFromPlansDialog ref="generateRef" mode="dispatch" @generated="load" />
  </div>
</template>