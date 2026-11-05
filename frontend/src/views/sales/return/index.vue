<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  cancelReturn,
  confirmReturn,
  createReturn,
  getOrder,
  listCustomers,
  listOrders,
  listProducts,
  listReturns,
} from '@/api/sales'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { Order, RemoteOption, SalesReturn } from '@/types/erp'

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

/** 已选原销售订单的物料清单；为空表示尚未选订单，退回全部成品 */
const orderMaterialOptions = ref<RemoteOption[] | null>(null)
/** 已选原销售订单的完整信息，用于在弹窗中回显 */
const selectedOrder = ref<Order | null>(null)

async function loadProductOptions(keyword: string): Promise<RemoteOption[]> {
  const scoped = orderMaterialOptions.value
  if (scoped) {
    const kw = keyword.trim().toLowerCase()
    if (!kw) return scoped
    return scoped.filter((item) => item.label.toLowerCase().includes(kw))
  }
  const list = await listProducts({ keyword })
  return list.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

/**
 * 退货不再选择仓库：确认退货后只向「库存管理 → 入库管理」推送待入库单，
 * 由仓库管理人员决定入库仓库并确认，库存才真正增加。
 */
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
  reason: string
  items: ReturnLineForm[]
}>({
  order_id: undefined,
  customer_id: undefined,
  return_date: '',
  reason: '',
  items: [],
})

const rules: FormRules = {
  order_id: [{ required: true, message: '请选择原销售订单', trigger: 'change' }],
  customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
  return_date: [{ required: true, message: '请选择退货日期', trigger: 'change' }],
}

/** 退货额度按原订单已发数量核算，选订单后自动带出该订单客户，并限定物料只能选该订单的 */
async function onOrderChange(value: number | undefined): Promise<void> {
  form.customer_id = undefined
  orderMaterialOptions.value = null
  selectedOrder.value = null
  // 换订单后旧行物料可能不属于新订单，统一清空重选
  form.items.forEach((line) => {
    line.material_id = undefined
  })
  if (value === undefined) return
  const order = await getOrder(value)
  selectedOrder.value = order
  form.customer_id = order.customer_id
  const seen = new Set<number>()
  const options: RemoteOption[] = []
  order.items.forEach((item) => {
    if (seen.has(item.material_id)) return
    seen.add(item.material_id)
    options.push({
      id: item.material_id,
      label: `${item.material_code ?? ''} ${item.material_name ?? ''}`.trim() || `物料 #${item.material_id}`,
    })
  })
  orderMaterialOptions.value = options
}

function addLine(): void {
  form.items.push({ material_id: undefined, quantity: 1, quality_status: 'QUALIFIED', reason: '' })
}

function openCreate(): void {
  Object.assign(form, {
    order_id: undefined,
    customer_id: undefined,
    return_date: '',
    reason: '',
    items: [],
  })
  orderMaterialOptions.value = null
  selectedOrder.value = null
  addLine()
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.order_id === undefined || form.customer_id === undefined) return
  const items = form.items.filter((item) => item.material_id !== undefined && item.quantity > 0)
  if (!items.length) {
    ElMessage.warning('请至少添加一行退货明细')
    return
  }
  submitting.value = true
  try {
    await createReturn({
      order_id: form.order_id,
      customer_id: form.customer_id,
      return_date: form.return_date,
      reason: form.reason || null,
      items: items.map((item) => ({
        material_id: item.material_id,
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
    ElMessage.success('退货已确认，已推送库存入库单（待仓库确认入库）')
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
            <el-form-item label="原销售订单" prop="order_id">
              <RemoteSelect
                v-model="form.order_id"
                :loader="loadOrderOptions"
                placeholder="必选"
                style="width: 100%"
                @change="onOrderChange"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="退货原因"><el-input v-model="form.reason" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div v-if="selectedOrder" class="order-info">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="订单号">{{ selectedOrder.order_no }}</el-descriptions-item>
          <el-descriptions-item label="客户">{{ selectedOrder.customer_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="订单状态"><StatusTag :status="selectedOrder.status" /></el-descriptions-item>
          <el-descriptions-item label="订单日期">{{ selectedOrder.order_date }}</el-descriptions-item>
          <el-descriptions-item label="交货日期">{{ selectedOrder.delivery_date }}</el-descriptions-item>
          <el-descriptions-item label="销售员">{{ selectedOrder.salesperson_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="订单金额">{{ selectedOrder.total_amount }}</el-descriptions-item>
          <el-descriptions-item label="明细行数">{{ selectedOrder.items.length }}</el-descriptions-item>
          <el-descriptions-item label="已发数量">
            {{ selectedOrder.items.reduce((sum, item) => sum + Number(item.delivered_qty ?? 0), 0) }}
          </el-descriptions-item>
        </el-descriptions>

        <el-table :data="selectedOrder.items" border size="small" class="order-items">
          <el-table-column label="物料编码" prop="material_code" min-width="140" />
          <el-table-column label="物料名称" prop="material_name" min-width="160" />
          <el-table-column label="订单数量" width="110" align="right">
            <template #default="{ row }">{{ row.quantity }}</template>
          </el-table-column>
          <el-table-column label="已发数量" width="110" align="right">
            <template #default="{ row }">{{ row.delivered_qty }}</template>
          </el-table-column>
          <el-table-column label="未发数量" width="110" align="right">
            <template #default="{ row }">{{ Number(row.quantity) - Number(row.delivered_qty ?? 0) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div class="table-toolbar">
        <span class="page-title">退货明细</span>
        <span class="table-toolbar__spacer" />
        <el-button size="small" @click="addLine">添加行</el-button>
      </div>
      <el-table :data="form.items" border size="small">
        <el-table-column label="物料" min-width="240">
          <template #default="{ row, $index }">
            <RemoteSelect
              :key="`${form.order_id ?? 0}-${$index}`"
              v-model="row.material_id"
              :loader="loadProductOptions"
              style="width: 100%"
            />
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
      <p class="form-tip">
        退货单必须关联原销售订单，数量不得超过该订单该物料的已发货数量（草稿单也占额度）。
        <strong>本单不再选择退回仓库</strong>：点击「确认」后只向「库存管理 → 入库管理」推送待入库单，
        由仓库管理人员决定入库仓库并确认，库存才真正增加。
      </p>
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

.order-info {
  margin-bottom: 12px;
}

.order-items {
  margin-top: 8px;
}
</style>