<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  cancelReturn,
  confirmReturn,
  createReturn,
  listCustomers,
  listOrders,
  listProducts,
  listReturns,
} from '@/api/sales'
import { listWarehouses } from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { RemoteOption, SalesReturn } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    SalesReturn,
    { order_id: number | undefined; customer_id: number | undefined; status: string }
  >((params) => listReturns(params), { order_id: undefined, customer_id: undefined, status: '' })

async function loadCustomerOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listCustomers({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.customer_code} ${item.customer_name}` }))
}

async function loadOrderOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listOrders({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.order_no} · ${item.customer_name ?? ''}` }))
}

async function loadProductOptions(keyword: string): Promise<RemoteOption[]> {
  const list = await listProducts({ keyword })
  return list.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

interface ReturnLineForm {
  material_id: number | undefined
  quantity: number
  quality_status: string
  reason: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  order_id: number | undefined
  customer_id: number | undefined
  return_date: string
  warehouse_id: number | undefined
  reason: string
  items: ReturnLineForm[]
}>({
  order_id: undefined,
  customer_id: undefined,
  return_date: '',
  warehouse_id: undefined,
  reason: '',
  items: [],
})

const rules: FormRules = {
  customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
  return_date: [{ required: true, message: '请选择退货日期', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择退回仓库', trigger: 'change' }],
}

function addLine(): void {
  form.items.push({ material_id: undefined, quantity: 1, quality_status: 'QUALIFIED', reason: '' })
}

function openCreate(): void {
  Object.assign(form, {
    order_id: undefined,
    customer_id: undefined,
    return_date: '',
    warehouse_id: undefined,
    reason: '',
    items: [],
  })
  addLine()
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.customer_id === undefined || form.warehouse_id === undefined) return
  const items = form.items.filter((item) => item.material_id !== undefined && item.quantity > 0)
  if (!items.length) {
    ElMessage.warning('请至少添加一行退货明细')
    return
  }
  submitting.value = true
  try {
    await createReturn({
      order_id: form.order_id ?? null,
      customer_id: form.customer_id,
      return_date: form.return_date,
      reason: form.reason || null,
      items: items.map((item) => ({
        material_id: item.material_id,
        warehouse_id: form.warehouse_id,
        quantity: item.quantity,
        quality_status: item.quality_status,
        reason: item.reason || null,
      })),
    })
    ElMessage.success('退货单已新增（草稿）')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doConfirm(row: SalesReturn): Promise<void> {
  try {
    await confirmReturn(row.id)
    ElMessage.success('退货已确认，库存已回写')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCancel(row: SalesReturn): Promise<void> {
  try {
    await cancelReturn(row.id)
    ElMessage.success('退货单已取消')
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
          <span class="page-title">退货管理</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增退货单</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="销售订单">
          <RemoteSelect v-model="query.order_id" :loader="loadOrderOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item label="客户">
          <RemoteSelect v-model="query.customer_id" :loader="loadCustomerOptions" placeholder="全部" style="width: 200px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="草稿" value="DRAFT" />
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
            <el-table :data="row.items" size="small" border class="nested-table">
              <el-table-column label="物料编码" prop="material_code" min-width="130" />
              <el-table-column label="物料名称" prop="material_name" min-width="150" />
              <el-table-column label="退回仓库ID" prop="warehouse_id" width="110" align="right" />
              <el-table-column label="数量" prop="quantity" width="100" align="right" />
              <el-table-column label="质量状态" width="100">
                <template #default="{ row: item }"><StatusTag :status="item.quality_status" /></template>
              </el-table-column>
              <el-table-column label="原因" prop="reason" min-width="140" />
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="退货单号" prop="return_no" min-width="150" />
        <el-table-column label="原订单号" prop="order_no" min-width="150" />
        <el-table-column label="客户" prop="customer_name" min-width="150" />
        <el-table-column label="退货日期" prop="return_date" width="110" />
        <el-table-column label="原因" prop="reason" min-width="150" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="doConfirm(row)">确认</el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="danger" @click="doCancel(row)">取消</el-button>
            <span v-if="row.status !== 'DRAFT'">-</span>
          </template>
        </el-table-column>
        <template #empty>暂无退货单数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增退货单" width="860px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="客户" prop="customer_id">
              <RemoteSelect v-model="form.customer_id" :loader="loadCustomerOptions" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="退货日期" prop="return_date">
              <el-date-picker v-model="form.return_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="退回仓库" prop="warehouse_id">
              <RemoteSelect v-model="form.warehouse_id" :loader="loadWarehouseOptions" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="原销售订单">
              <RemoteSelect v-model="form.order_id" :loader="loadOrderOptions" placeholder="可选" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="退货原因"><el-input v-model="form.reason" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="table-toolbar">
        <span class="page-title">退货明细</span>
        <span class="table-toolbar__spacer" />
        <el-button size="small" @click="addLine">添加行</el-button>
      </div>
      <el-table :data="form.items" border size="small">
        <el-table-column label="物料" min-width="240">
          <template #default="{ row }">
            <RemoteSelect v-model="row.material_id" :loader="loadProductOptions" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="数量" width="140">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0.0001" :controls="false" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="质量状态" width="140">
          <template #default="{ row }">
            <el-select v-model="row.quality_status">
              <el-option label="合格" value="QUALIFIED" />
              <el-option label="不良" value="DEFECTIVE" />
              <el-option label="报废" value="SCRAP" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="行原因" min-width="150">
          <template #default="{ row }"><el-input v-model="row.reason" /></template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ $index }">
            <el-button link type="danger" @click="form.items.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="form-tip">保存后为草稿状态，确认时才会写入库存流水。</p>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.nested-table {
  margin: 4px 0 4px 48px;
  width: calc(100% - 48px);
}
</style>