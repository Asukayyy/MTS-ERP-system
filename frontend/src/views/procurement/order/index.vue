<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  confirmReceipt,
  createOrderFromPlan,
  createPurchaseOrder,
  createReceipt,
  getPurchaseOrder,
  listPurchaseOrders,
  listPurchasePlans,
  listSuppliers,
  setPurchaseOrderStatus,
  updatePurchaseOrder,
} from '@/api/procurement'
import { listWarehouses } from '@/api/inventory'
import { listMaterials, listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { PurchaseOrder, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<PurchaseOrder, { status: string; supplier_id: number | undefined; keyword: string }>(
    (params) => listPurchaseOrders(params),
    { status: '', supplier_id: undefined, keyword: '' },
  )

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, supply_type: 'BUY', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadSupplierOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listSuppliers({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.supplier_code} ${item.supplier_name}` }))
}

async function loadBuyerOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

// ---------------- 新增 / 编辑 ----------------

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
  order_no: string
  supplier_id: number | undefined
  order_date: string
  expected_date: string
  buyer_id: number | undefined
  remark: string
  items: OrderLineForm[]
}>({
  order_no: '',
  supplier_id: undefined,
  order_date: '',
  expected_date: '',
  buyer_id: undefined,
  remark: '',
  items: [],
})

const rules: FormRules = {
  supplier_id: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  order_date: [{ required: true, message: '请选择下单日期', trigger: 'change' }],
  expected_date: [{ required: true, message: '请选择预计到货日期', trigger: 'change' }],
}

function addLine(): void {
  form.items.push({ material_id: undefined, quantity: 1, unit_price: 0, remark: '' })
}

function removeLine(index: number): void {
  form.items.splice(index, 1)
}

/** 订单总金额（与后端按行金额汇总口径一致，仅做界面预览） */
const previewTotal = computed(() =>
  form.items.reduce((sum, item) => sum + (item.quantity || 0) * (item.unit_price || 0), 0),
)

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    order_no: '',
    supplier_id: undefined,
    order_date: '',
    expected_date: '',
    buyer_id: undefined,
    remark: '',
    items: [],
  })
  addLine()
  dialogVisible.value = true
}

async function openEdit(row: PurchaseOrder): Promise<void> {
  try {
    const detail = await getPurchaseOrder(row.id)
    editingId.value = detail.id
    Object.assign(form, {
      order_no: detail.order_no,
      supplier_id: detail.supplier_id,
      order_date: detail.order_date,
      expected_date: detail.expected_date,
      buyer_id: detail.buyer_id ?? undefined,
      remark: detail.remark ?? '',
      items: detail.items.map((item) => ({
        material_id: item.material_id,
        quantity: toNumber(item.quantity),
        unit_price: toNumber(item.unit_price),
        remark: item.remark ?? '',
      })),
    })
    if (form.items.length === 0) addLine()
    dialogVisible.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.items.length === 0) {
    ElMessage.warning('请至少添加一行采购明细')
    return
  }
  if (form.items.some((item) => !item.material_id)) {
    ElMessage.warning('请为每一行选择物料')
    return
  }
  submitting.value = true
  const payload = {
    order_no: form.order_no || null,
    supplier_id: form.supplier_id,
    order_date: form.order_date,
    expected_date: form.expected_date,
    buyer_id: form.buyer_id ?? null,
    remark: form.remark || null,
    items: form.items.map((item) => ({
      material_id: item.material_id,
      quantity: item.quantity,
      unit_price: item.unit_price,
      remark: item.remark || null,
    })),
  }
  try {
    if (editingId.value === null) {
      await createPurchaseOrder(payload)
      ElMessage.success('采购订单已新增')
    } else {
      await updatePurchaseOrder(editingId.value, payload)
      ElMessage.success('采购订单已更新')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function changeStatus(row: PurchaseOrder, status: string): Promise<void> {
  try {
    await setPurchaseOrderStatus(row.id, status)
    ElMessage.success('采购订单状态已更新')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

// ---------------- 生成到货单 ----------------

interface ReceiptLineForm {
  order_item_id: number
  material_id: number
  quantity: number
  qualified_qty: number
}

const receiptVisible = ref(false)
const receiptSubmitting = ref(false)
const receiptOrder = ref<PurchaseOrder | null>(null)
const receiptForm = reactive<{
  warehouse_id: number | undefined
  receipt_date: string
  remark: string
  items: ReceiptLineForm[]
}>({ warehouse_id: undefined, receipt_date: '', remark: '', items: [] })

async function openReceipt(row: PurchaseOrder): Promise<void> {
  try {
    const detail = await getPurchaseOrder(row.id)
    receiptOrder.value = detail
    receiptForm.warehouse_id = undefined
    receiptForm.receipt_date = ''
    receiptForm.remark = ''
    receiptForm.items = detail.items.map((item) => {
      const remaining = toNumber(item.quantity) - toNumber(item.received_qty)
      return {
        order_item_id: item.id,
        material_id: item.material_id,
        quantity: remaining > 0 ? remaining : 0,
        qualified_qty: remaining > 0 ? remaining : 0,
      }
    })
    receiptVisible.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function submitReceipt(): Promise<void> {
  if (!receiptOrder.value) return
  if (!receiptForm.warehouse_id) {
    ElMessage.warning('请选择收货仓库')
    return
  }
  if (!receiptForm.receipt_date) {
    ElMessage.warning('请选择到货日期')
    return
  }
  const items = receiptForm.items.filter((item) => item.quantity > 0)
  if (items.length === 0) {
    ElMessage.warning('到货数量必须大于 0')
    return
  }
  receiptSubmitting.value = true
  try {
    const receipt = await createReceipt({
      purchase_order_id: receiptOrder.value.id,
      warehouse_id: receiptForm.warehouse_id,
      receipt_date: receiptForm.receipt_date,
      remark: receiptForm.remark || null,
      items: items.map((item) => ({
        order_item_id: item.order_item_id,
        quantity: item.quantity,
        qualified_qty: item.qualified_qty,
      })),
    })
    // 生成后立即确认入库，写真实库存流水
    await confirmReceipt(receipt.id)
    ElMessage.success('到货单已生成并确认入库')
    receiptVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    receiptSubmitting.value = false
  }
}

// ---------------- 从采购计划生成订单 ----------------

async function loadPlanOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPurchasePlans({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.plan_no} ${item.status}` }))
}

const fromPlanVisible = ref(false)
const fromPlanSubmitting = ref(false)
const fromPlanForm = reactive<{
  plan_id: number | undefined
  supplier_id: number | undefined
  order_date: string
  expected_date: string
  buyer_id: number | undefined
  remark: string
}>({
  plan_id: undefined,
  supplier_id: undefined,
  order_date: '',
  expected_date: '',
  buyer_id: undefined,
  remark: '',
})

function openFromPlan(): void {
  Object.assign(fromPlanForm, {
    plan_id: undefined,
    supplier_id: undefined,
    order_date: '',
    expected_date: '',
    buyer_id: undefined,
    remark: '',
  })
  fromPlanVisible.value = true
}

async function submitFromPlan(): Promise<void> {
  if (!fromPlanForm.plan_id) {
    ElMessage.warning('请选择采购计划')
    return
  }
  if (!fromPlanForm.supplier_id) {
    ElMessage.warning('请选择供应商')
    return
  }
  fromPlanSubmitting.value = true
  try {
    const order = await createOrderFromPlan({
      plan_id: fromPlanForm.plan_id,
      supplier_id: fromPlanForm.supplier_id,
      order_date: fromPlanForm.order_date || null,
      expected_date: fromPlanForm.expected_date || null,
      buyer_id: fromPlanForm.buyer_id ?? null,
      remark: fromPlanForm.remark || null,
    })
    ElMessage.success(`采购订单 ${order.order_no} 已生成`)
    fromPlanVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    fromPlanSubmitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">采购订单</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="openFromPlan">从采购计划生成订单</el-button>
          <el-button type="primary" @click="openCreate">新增采购订单</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="订单号">
          <el-input v-model="query.keyword" placeholder="订单号" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item label="供应商">
          <RemoteSelect v-model="query.supplier_id" :loader="loadSupplierOptions" placeholder="全部" style="width: 220px" />
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
              <el-table-column label="行号" prop="line_no" width="70" align="right" />
              <el-table-column label="物料ID" prop="material_id" width="90" align="right" />
              <el-table-column label="采购数量" prop="quantity" width="110" align="right" />
              <el-table-column label="已到货" prop="received_qty" width="110" align="right" />
              <el-table-column label="单价" prop="unit_price" width="110" align="right" />
              <el-table-column label="金额" prop="amount" width="120" align="right" />
              <el-table-column label="备注" prop="remark" min-width="140" />
              <template #empty>暂无采购明细</template>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="采购订单号" prop="order_no" min-width="150" />
        <el-table-column label="供应商" min-width="180">
          <template #default="{ row }">{{ row.supplier_name || `ID ${row.supplier_id}` }}</template>
        </el-table-column>
        <el-table-column label="下单日期" prop="order_date" width="110" />
        <el-table-column label="预计到货" prop="expected_date" width="110" />
        <el-table-column label="采购员" min-width="120">
          <template #default="{ row }">{{ row.buyer_name || (row.buyer_id ? `ID ${row.buyer_id}` : '-') }}</template>
        </el-table-column>
        <el-table-column label="订单金额" prop="total_amount" width="120" align="right" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="openEdit(row)">编辑</el-button>
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
              v-if="['DRAFT', 'CONFIRMED', 'RELEASED', 'IN_PROGRESS'].includes(row.status)"
              link
              type="primary"
              @click="openReceipt(row)"
            >
              生成到货单
            </el-button>
            <el-button
              v-if="['DRAFT', 'CONFIRMED', 'RELEASED'].includes(row.status)"
              link
              type="danger"
              @click="changeStatus(row, 'CANCELLED')"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无采购订单数据</template>
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

    <el-dialog
      v-model="dialogVisible"
      :title="editingId === null ? '新增采购订单' : '编辑采购订单'"
      width="960px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="采购订单号">
              <el-input v-model="form.order_no" placeholder="留空自动生成" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="供应商" prop="supplier_id">
              <RemoteSelect v-model="form.supplier_id" :loader="loadSupplierOptions" placeholder="请选择供应商" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="下单日期" prop="order_date">
              <el-date-picker v-model="form.order_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="预计到货" prop="expected_date">
              <el-date-picker v-model="form.expected_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="采购员">
              <RemoteSelect v-model="form.buyer_id" :loader="loadBuyerOptions" placeholder="可选" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">采购明细</el-divider>
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
          <el-table-column label="采购数量" width="140">
            <template #default="{ row }">
              <el-input-number v-model="row.quantity" :min="0.0001" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="140">
            <template #default="{ row }">
              <el-input-number v-model="row.unit_price" :min="0" :precision="2" :controls="false" style="width: 100%" />
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
          <template #empty>请添加采购明细行</template>
        </el-table>
        <div class="form-tip">界面预估金额：{{ previewTotal.toFixed(2) }}（最终以系统计算为准）</div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="receiptVisible" title="生成到货单" width="800px">
      <el-form label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="采购订单号">
              <el-input :model-value="receiptOrder?.order_no" disabled />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="收货仓库">
              <RemoteSelect
                v-model="receiptForm.warehouse_id"
                :loader="loadWarehouseOptions"
                placeholder="请选择仓库"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="到货日期">
              <el-date-picker v-model="receiptForm.receipt_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="备注">
              <el-input v-model="receiptForm.remark" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-table :data="receiptForm.items" border size="small">
          <el-table-column label="订单行ID" prop="order_item_id" width="100" align="right" />
          <el-table-column label="物料ID" prop="material_id" width="90" align="right" />
          <el-table-column label="到货数量" width="150">
            <template #default="{ row }">
              <el-input-number v-model="row.quantity" :min="0" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="合格数量" width="150">
            <template #default="{ row }">
              <el-input-number v-model="row.qualified_qty" :min="0" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <template #empty>该订单没有可到货的明细</template>
        </el-table>
        <div class="form-tip">到货数量默认取「采购数量 - 已到货数量」，可手工调整。</div>
      </el-form>
      <template #footer>
        <el-button @click="receiptVisible = false">取消</el-button>
        <el-button type="primary" :loading="receiptSubmitting" @click="submitReceipt">生成到货单</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="fromPlanVisible" title="从采购计划生成订单" width="640px">
      <el-form label-width="120px">
        <el-form-item label="采购计划" required>
          <RemoteSelect
            v-model="fromPlanForm.plan_id"
            :loader="loadPlanOptions"
            placeholder="请选择待下单的采购计划"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="供应商" required>
          <RemoteSelect
            v-model="fromPlanForm.supplier_id"
            :loader="loadSupplierOptions"
            placeholder="请选择供应商（决定供货价与提前期）"
            style="width: 100%"
          />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="下单日期">
              <el-date-picker
                v-model="fromPlanForm.order_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="默认今天"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预计到货">
              <el-date-picker
                v-model="fromPlanForm.expected_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="按供货提前期推算"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="采购员">
          <RemoteSelect v-model="fromPlanForm.buyer_id" :loader="loadBuyerOptions" placeholder="可选" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="fromPlanForm.remark" type="textarea" :rows="2" />
        </el-form-item>
        <div class="form-tip">订单明细与单价由后端根据采购计划行及供应商供货价自动生成。</div>
      </el-form>
      <template #footer>
        <el-button @click="fromPlanVisible = false">取消</el-button>
        <el-button type="primary" :loading="fromPlanSubmitting" @click="submitFromPlan">生成订单</el-button>
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