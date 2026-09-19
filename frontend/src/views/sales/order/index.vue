<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  confirmReturn,
  createOrder,
  createReturn,
  createShipment,
  deleteOrder,
  listCustomers,
  listOrders,
  listProducts,
  setOrderStatus,
  updateOrder,
} from '@/api/sales'
import { listPersonnel } from '@/api/system'
import { listWarehouses } from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { Order, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    Order,
    { customer_id: number | undefined; status: string; keyword: string; date_from: string; date_to: string }
  >((params) => listOrders(params), {
    customer_id: undefined,
    status: '',
    keyword: '',
    date_from: '',
    date_to: '',
  })

// ---------------- 远程选项 ----------------
async function loadCustomerOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listCustomers({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.customer_code} ${item.customer_name}` }))
}

async function loadProductOptions(keyword: string): Promise<RemoteOption[]> {
  const list = await listProducts({ keyword })
  return list.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadSalespersonOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

// ---------------- 新增 / 修改订单 ----------------
interface OrderLineForm {
  material_id: number | undefined
  quantity: number
  unit_price: number
  remark: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  customer_id: number | undefined
  order_date: string
  delivery_date: string
  salesperson_id: number | undefined
  remark: string
  items: OrderLineForm[]
}>({
  customer_id: undefined,
  order_date: '',
  delivery_date: '',
  salesperson_id: undefined,
  remark: '',
  items: [],
})

const rules: FormRules = {
  customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
  order_date: [{ required: true, message: '请选择订单日期', trigger: 'change' }],
  delivery_date: [{ required: true, message: '请选择要求交货日期', trigger: 'change' }],
}

const orderAmount = computed(() =>
  form.items.reduce((sum, item) => sum + item.quantity * item.unit_price, 0),
)

function addLine(): void {
  form.items.push({ material_id: undefined, quantity: 1, unit_price: 0, remark: '' })
}

function removeLine(index: number): void {
  form.items.splice(index, 1)
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    customer_id: undefined,
    order_date: '',
    delivery_date: '',
    salesperson_id: undefined,
    remark: '',
    items: [],
  })
  addLine()
  dialogVisible.value = true
}

function openEdit(row: Order): void {
  editingId.value = row.id
  Object.assign(form, {
    customer_id: row.customer_id,
    order_date: row.order_date,
    delivery_date: row.delivery_date,
    salesperson_id: row.salesperson_id ?? undefined,
    remark: row.remark ?? '',
    items: row.items.map((item) => ({
      material_id: item.material_id,
      quantity: toNumber(item.quantity),
      unit_price: toNumber(item.unit_price),
      remark: item.remark ?? '',
    })),
  })
  if (!form.items.length) addLine()
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const items = form.items.filter((item) => item.material_id !== undefined)
  if (!items.length) {
    ElMessage.warning('请至少添加一行订单明细')
    return
  }
  submitting.value = true
  try {
    const payload = {
      customer_id: form.customer_id,
      order_date: form.order_date,
      delivery_date: form.delivery_date,
      salesperson_id: form.salesperson_id ?? null,
      remark: form.remark || null,
      items: items.map((item) => ({
        material_id: item.material_id,
        quantity: item.quantity,
        unit_price: item.unit_price,
        remark: item.remark || null,
      })),
    }
    if (editingId.value === null) {
      await createOrder(payload)
      ElMessage.success('销售订单已新增')
    } else {
      await updateOrder(editingId.value, payload)
      ElMessage.success('销售订单已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function changeStatus(row: Order, status: string): Promise<void> {
  try {
    await setOrderStatus(row.id, status)
    ElMessage.success('订单状态已更新')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(row: Order): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除订单「${row.order_no}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteOrder(row.id)
    ElMessage.success('销售订单已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

// ---------------- 生成发货单 ----------------
interface ShipmentLineForm {
  order_item_id: number
  material_label: string
  remaining: number
  quantity: number
}

const shipDialogVisible = ref(false)
const shipSubmitting = ref(false)
const shipFormRef = ref<FormInstance>()
const shipForm = reactive<{
  order_id: number | null
  shipment_date: string
  warehouse_id: number | undefined
  remark: string
  items: ShipmentLineForm[]
}>({
  order_id: null,
  shipment_date: '',
  warehouse_id: undefined,
  remark: '',
  items: [],
})

const shipRules: FormRules = {
  shipment_date: [{ required: true, message: '请选择发货日期', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择发货仓库', trigger: 'change' }],
}

function openShipment(row: Order): void {
  shipForm.order_id = row.id
  shipForm.shipment_date = ''
  shipForm.warehouse_id = undefined
  shipForm.remark = ''
  shipForm.items = row.items.map((item) => ({
    order_item_id: item.id,
    material_label: `${item.material_code ?? ''} ${item.material_name ?? ''}`.trim(),
    remaining: toNumber(item.quantity) - toNumber(item.delivered_qty),
    quantity: toNumber(item.quantity) - toNumber(item.delivered_qty),
  }))
  shipDialogVisible.value = true
}

async function submitShipment(): Promise<void> {
  const valid = await shipFormRef.value?.validate().catch(() => false)
  if (!valid) return
  if (shipForm.order_id === null || shipForm.warehouse_id === undefined) return
  const items = shipForm.items.filter((item) => item.quantity > 0)
  if (!items.length) {
    ElMessage.warning('请填写发货数量')
    return
  }
  shipSubmitting.value = true
  try {
    await createShipment({
      order_id: shipForm.order_id,
      shipment_date: shipForm.shipment_date,
      remark: shipForm.remark || null,
      items: items.map((item) => ({
        order_item_id: item.order_item_id,
        warehouse_id: shipForm.warehouse_id,
        quantity: item.quantity,
      })),
    })
    ElMessage.success('发货单已生成（草稿）')
    shipDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    shipSubmitting.value = false
  }
}

// ---------------- 生成退货单 ----------------
interface ReturnLineForm {
  material_id: number | undefined
  material_label: string
  quantity: number
  quality_status: string
  reason: string
}

const returnDialogVisible = ref(false)
const returnSubmitting = ref(false)
const returnFormRef = ref<FormInstance>()
const returnForm = reactive<{
  order_id: number | null
  customer_id: number | undefined
  return_date: string
  warehouse_id: number | undefined
  reason: string
  items: ReturnLineForm[]
}>({
  order_id: null,
  customer_id: undefined,
  return_date: '',
  warehouse_id: undefined,
  reason: '',
  items: [],
})

const returnRules: FormRules = {
  customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
  return_date: [{ required: true, message: '请选择退货日期', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择退回仓库', trigger: 'change' }],
}

function addReturnLine(): void {
  returnForm.items.push({
    material_id: undefined,
    material_label: '',
    quantity: 1,
    quality_status: 'QUALIFIED',
    reason: '',
  })
}

function openReturnFromOrder(row: Order): void {
  returnForm.order_id = row.id
  returnForm.customer_id = row.customer_id
  returnForm.return_date = ''
  returnForm.warehouse_id = undefined
  returnForm.reason = ''
  returnForm.items = row.items.map((item) => ({
    material_id: item.material_id,
    material_label: `${item.material_code ?? ''} ${item.material_name ?? ''}`.trim(),
    quantity: toNumber(item.quantity),
    quality_status: 'QUALIFIED',
    reason: '',
  }))
  returnDialogVisible.value = true
}

function openReturnBlank(): void {
  returnForm.order_id = null
  returnForm.customer_id = undefined
  returnForm.return_date = ''
  returnForm.warehouse_id = undefined
  returnForm.reason = ''
  returnForm.items = []
  addReturnLine()
  returnDialogVisible.value = true
}

async function submitReturn(): Promise<void> {
  const valid = await returnFormRef.value?.validate().catch(() => false)
  if (!valid) return
  if (returnForm.customer_id === undefined || returnForm.warehouse_id === undefined) return
  const items = returnForm.items.filter((item) => item.material_id !== undefined && item.quantity > 0)
  if (!items.length) {
    ElMessage.warning('请至少添加一行退货明细')
    return
  }
  returnSubmitting.value = true
  try {
    const created = await createReturn({
      order_id: returnForm.order_id,
      customer_id: returnForm.customer_id,
      return_date: returnForm.return_date,
      reason: returnForm.reason || null,
      items: items.map((item) => ({
        material_id: item.material_id,
        warehouse_id: returnForm.warehouse_id,
        quantity: item.quantity,
        quality_status: item.quality_status,
        reason: item.reason || null,
      })),
    })
    await confirmReturn(created.id)
    ElMessage.success('退货单已创建并确认（已产生库存流水）')
    returnDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    returnSubmitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">销售订单</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="openReturnBlank">登记退货</el-button>
          <el-button type="primary" @click="openCreate">新增订单</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="客户">
          <RemoteSelect v-model="query.customer_id" :loader="loadCustomerOptions" placeholder="全部" style="width: 200px" />
        </el-form-item>
        <el-form-item label="订单号">
          <el-input v-model="query.keyword" placeholder="订单号关键字" clearable style="width: 170px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="订单日期">
          <el-date-picker v-model="query.date_from" type="date" value-format="YYYY-MM-DD" placeholder="起" clearable style="width: 140px" />
          <span style="margin: 0 4px">-</span>
          <el-date-picker v-model="query.date_to" type="date" value-format="YYYY-MM-DD" placeholder="止" clearable style="width: 140px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已确认" value="CONFIRMED" />
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
            <el-table :data="row.items" size="small" border class="nested-table">
              <el-table-column label="行号" prop="line_no" width="70" align="right" />
              <el-table-column label="物料编码" prop="material_code" min-width="130" />
              <el-table-column label="物料名称" prop="material_name" min-width="150" />
              <el-table-column label="订单数量" prop="quantity" width="110" align="right" />
              <el-table-column label="已发货" prop="delivered_qty" width="100" align="right" />
              <el-table-column label="单价" prop="unit_price" width="100" align="right" />
              <el-table-column label="金额" prop="amount" width="120" align="right" />
              <el-table-column label="备注" prop="remark" min-width="140" />
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="订单号" prop="order_no" min-width="150" />
        <el-table-column label="客户" prop="customer_name" min-width="150" />
        <el-table-column label="订单日期" prop="order_date" width="110" />
        <el-table-column label="要求交货" prop="delivery_date" width="110" />
        <el-table-column label="销售员" prop="salesperson_name" min-width="110" />
        <el-table-column label="总金额" prop="total_amount" width="120" align="right" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="270" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="changeStatus(row, 'CONFIRMED')">
              确认
            </el-button>
            <el-button v-if="row.status === 'CONFIRMED'" link type="primary" @click="changeStatus(row, 'IN_PROGRESS')">
              开始执行
            </el-button>
            <el-button v-if="row.status === 'IN_PROGRESS'" link type="success" @click="changeStatus(row, 'COMPLETED')">
              完成
            </el-button>
            <el-button
              v-if="row.status === 'CONFIRMED' || row.status === 'IN_PROGRESS'"
              link
              type="warning"
              @click="openShipment(row)"
            >
              生成发货单
            </el-button>
            <el-button link type="info" @click="openReturnFromOrder(row)">生成退货单</el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button
              v-if="row.status === 'DRAFT' || row.status === 'CONFIRMED'"
              link
              type="danger"
              @click="changeStatus(row, 'CANCELLED')"
            >
              取消
            </el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无销售订单数据</template>
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

    <!-- 新增 / 修改订单 -->
    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增销售订单' : '修改销售订单'" width="900px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="客户" prop="customer_id">
              <RemoteSelect v-model="form.customer_id" :loader="loadCustomerOptions" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="订单日期" prop="order_date">
              <el-date-picker v-model="form.order_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="要求交货" prop="delivery_date">
              <el-date-picker v-model="form.delivery_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="销售员">
              <RemoteSelect v-model="form.salesperson_id" :loader="loadSalespersonOptions" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="16">
            <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="table-toolbar">
        <span class="page-title">订单明细（合计金额 {{ orderAmount.toFixed(2) }}）</span>
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
        <el-table-column label="单价" width="140">
          <template #default="{ row }">
            <el-input-number v-model="row.unit_price" :min="0" :controls="false" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">{{ (row.quantity * row.unit_price).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }"><el-input v-model="row.remark" /></template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ $index }">
            <el-button link type="danger" @click="removeLine($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 生成发货单 -->
    <el-dialog v-model="shipDialogVisible" title="生成发货单" width="760px">
      <el-form ref="shipFormRef" :model="shipForm" :rules="shipRules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="发货日期" prop="shipment_date">
              <el-date-picker v-model="shipForm.shipment_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="发货仓库" prop="warehouse_id">
              <RemoteSelect v-model="shipForm.warehouse_id" :loader="loadWarehouseOptions" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注"><el-input v-model="shipForm.remark" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <el-table :data="shipForm.items" border size="small">
        <el-table-column label="物料" prop="material_label" min-width="200" />
        <el-table-column label="可发数量" prop="remaining" width="110" align="right" />
        <el-table-column label="本次发货" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0" :max="row.remaining" :controls="false" style="width: 100%" />
          </template>
        </el-table-column>
      </el-table>
      <p class="form-tip">发货单保存后为草稿状态，请在「发货管理」中确认以实际出库。</p>
      <template #footer>
        <el-button @click="shipDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="shipSubmitting" @click="submitShipment">生成发货单</el-button>
      </template>
    </el-dialog>

    <!-- 生成退货单 -->
    <el-dialog v-model="returnDialogVisible" title="登记退货" width="820px">
      <el-form ref="returnFormRef" :model="returnForm" :rules="returnRules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="客户" prop="customer_id">
              <RemoteSelect v-model="returnForm.customer_id" :loader="loadCustomerOptions" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="退货日期" prop="return_date">
              <el-date-picker v-model="returnForm.return_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="退回仓库" prop="warehouse_id">
              <RemoteSelect v-model="returnForm.warehouse_id" :loader="loadWarehouseOptions" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="退货原因"><el-input v-model="returnForm.reason" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="table-toolbar">
        <span class="page-title">退货明细</span>
        <span class="table-toolbar__spacer" />
        <el-button size="small" @click="addReturnLine">添加行</el-button>
      </div>
      <el-table :data="returnForm.items" border size="small">
        <el-table-column label="物料" min-width="230">
          <template #default="{ row }">
            <RemoteSelect v-model="row.material_id" :loader="loadProductOptions" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="数量" width="130">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0.0001" :controls="false" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="质量状态" width="130">
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
            <el-button link type="danger" @click="returnForm.items.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="form-tip">保存后将自动确认退货单并写入库存流水。</p>
      <template #footer>
        <el-button @click="returnDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="returnSubmitting" @click="submitReturn">保存并确认</el-button>
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