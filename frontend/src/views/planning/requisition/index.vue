<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { listWarehouses } from '@/api/inventory'
import {
  cancelRequisition,
  confirmRequisition,
  createRequisition,
  listRequisitions,
  listProductionPlans,
  updateRequisition,
} from '@/api/planning'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import GenerateFromPlansDialog from '@/components/planning/GenerateFromPlansDialog.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { RemoteOption, Requisition } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Requisition, { status: string; plan_id: number | undefined }>(
    (params) => listRequisitions(params),
    { status: '', plan_id: undefined },
  )

async function loadPlanOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listProductionPlans({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.plan_no} · 物料${item.material_id}` }))
}

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

interface ReqLineForm {
  material_id: number | undefined
  required_qty: number
  remark: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const generateRef = ref<InstanceType<typeof GenerateFromPlansDialog>>()
const form = reactive<{
  req_no: string
  plan_id: number | undefined
  warehouse_id: number | undefined
  req_date: string | null
  remark: string
  items: ReqLineForm[]
}>({
  req_no: '',
  plan_id: undefined,
  warehouse_id: undefined,
  req_date: null,
  remark: '',
  items: [],
})

// 领料日期与仓库为草稿阶段可留空的字段，由人工指定；确认领料前服务端会校验
const rules: FormRules = {}

function addLine(): void {
  form.items.push({ material_id: undefined, required_qty: 1, remark: '' })
}

function removeLine(index: number): void {
  form.items.splice(index, 1)
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    req_no: '',
    plan_id: undefined,
    warehouse_id: undefined,
    req_date: null,
    remark: '',
    items: [],
  })
  addLine()
  dialogVisible.value = true
}

function openEdit(row: Requisition): void {
  editingId.value = row.id
  Object.assign(form, {
    req_no: row.req_no,
    plan_id: row.plan_id ?? undefined,
    warehouse_id: row.warehouse_id ?? undefined,
    req_date: row.req_date ?? null,
    remark: row.remark ?? '',
    items: row.items.map((item) => ({
      material_id: item.material_id,
      required_qty: toNumber(item.required_qty),
      remark: item.remark ?? '',
    })),
  })
  if (form.items.length === 0) addLine()
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.items.length === 0) {
    ElMessage.warning('请至少添加一行领料明细')
    return
  }
  if (form.items.some((item) => !item.material_id)) {
    ElMessage.warning('请为每一行选择物料')
    return
  }
  submitting.value = true
  try {
    const items = form.items.map((item) => ({
      material_id: item.material_id,
      required_qty: item.required_qty,
      remark: item.remark || null,
    }))
    if (editingId.value === null) {
      await createRequisition({
        req_no: form.req_no || null,
        plan_id: form.plan_id ?? null,
        warehouse_id: form.warehouse_id ?? null,
        req_date: form.req_date || null,
        remark: form.remark || null,
        items,
      })
      ElMessage.success('领料单已新增')
    } else {
      await updateRequisition(editingId.value, {
        warehouse_id: form.warehouse_id ?? null,
        req_date: form.req_date || null,
        remark: form.remark || null,
        items,
      })
      ElMessage.success('领料单已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doConfirm(row: Requisition): Promise<void> {
  try {
    await confirmRequisition(row.id)
    ElMessage.success('领料已确认，库存已出库')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCancel(row: Requisition): Promise<void> {
  try {
    await cancelRequisition(row.id)
    ElMessage.success('领料单已取消')
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
          <span class="page-title">领料单</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="generateRef?.open()">按计划生成</el-button>
          <el-button type="primary" @click="openCreate">新增领料单</el-button>
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
        <el-table-column type="expand">
          <template #default="{ row }">
            <el-table class="nested-table" :data="row.items" border size="small">
              <el-table-column label="物料ID" prop="material_id" width="90" align="right" />
              <el-table-column label="需求数量" prop="required_qty" width="110" align="right" />
              <el-table-column label="已发数量" prop="issued_qty" width="110" align="right" />
              <el-table-column label="备注" prop="remark" min-width="140" />
              <template #empty>暂无领料明细</template>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="领料单号" prop="req_no" min-width="150" />
        <el-table-column label="来源" width="90">
          <template #default="{ row }"><StatusTag :status="row.source_type" /></template>
        </el-table-column>
        <el-table-column label="作业计划ID" prop="plan_id" width="110" align="right" />
        <el-table-column label="领料仓库ID" prop="warehouse_id" width="110" align="right">
          <template #default="{ row }">{{ row.warehouse_id ?? '待指定' }}</template>
        </el-table-column>
        <el-table-column label="领料日期" prop="req_date" width="110">
          <template #default="{ row }">{{ row.req_date || '待填写' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="openEdit(row)">
              编辑
            </el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="doConfirm(row)">
              确认领料
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
        <template #empty>暂无领料单数据</template>
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

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增领料单' : '编辑领料单'" width="900px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="领料单号">
              <el-input v-model="form.req_no" :disabled="editingId !== null" placeholder="留空自动生成" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="领料日期" prop="req_date">
              <el-date-picker
                v-model="form.req_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="确认领料前必填"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="作业计划">
              <RemoteSelect
                v-model="form.plan_id"
                :loader="loadPlanOptions"
                :disabled="editingId !== null"
                placeholder="可选"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="领料仓库">
              <RemoteSelect
                v-model="form.warehouse_id"
                :loader="loadWarehouseOptions"
                placeholder="可留空后补填"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">领料明细</el-divider>
        <div class="table-toolbar">
          <span class="table-toolbar__spacer" />
          <el-button size="small" @click="addLine">添加明细行</el-button>
        </div>
        <el-table :data="form.items" border size="small">
          <el-table-column label="物料" min-width="220">
            <template #default="{ row }">
              <RemoteSelect v-model="row.material_id" :loader="loadMaterialOptions" placeholder="请选择物料" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="需求数量" width="140">
            <template #default="{ row }">
              <el-input-number v-model="row.required_qty" :min="0.0001" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.remark" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeLine($index)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>请添加领料明细行</template>
        </el-table>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <GenerateFromPlansDialog ref="generateRef" mode="requisition" @generated="load" />
  </div>
</template>

<style scoped>
.nested-table {
  margin: 4px 0 4px 48px;
  width: calc(100% - 48px);
}
</style>