<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  cancelShipment,
  confirmShipment,
  createShipment,
  getOrder,
  listOrders,
  listShipments,
} from '@/api/sales'
import { listWarehouses } from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { RemoteOption, Shipment } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Shipment, { order_id: number | undefined; status: string }>(
    (params) => listShipments(params),
    { order_id: undefined, status: '' },
  )

/** 可发货订单（已确认 / 执行中） */
async function loadOrderOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listOrders({ keyword, page: 1, page_size: 50 })
  return data.items
    .filter((item) => item.status === 'CONFIRMED' || item.status === 'IN_PROGRESS')
    .map((item) => ({ id: item.id, label: `${item.order_no} · ${item.customer_name ?? ''}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

interface ShipLineForm {
  order_item_id: number
  material_label: string
  remaining: number
  quantity: number
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  order_id: number | undefined
  shipment_date: string
  warehouse_id: number | undefined
  remark: string
  items: ShipLineForm[]
}>({
  order_id: undefined,
  shipment_date: '',
  warehouse_id: undefined,
  remark: '',
  items: [],
})

const rules: FormRules = {
  order_id: [{ required: true, message: '请选择销售订单', trigger: 'change' }],
  shipment_date: [{ required: true, message: '请选择发货日期', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择发货仓库', trigger: 'change' }],
}

/** 选择订单后带出订单行 */
async function onOrderChange(orderId: number | undefined): Promise<void> {
  form.items = []
  if (orderId === undefined) return
  try {
    const order = await getOrder(orderId)
    form.items = order.items.map((item) => ({
      order_item_id: item.id,
      material_label: `${item.material_code ?? ''} ${item.material_name ?? ''}`.trim(),
      remaining: toNumber(item.quantity) - toNumber(item.delivered_qty),
      quantity: toNumber(item.quantity) - toNumber(item.delivered_qty),
    }))
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function openCreate(): void {
  Object.assign(form, {
    order_id: undefined,
    shipment_date: '',
    warehouse_id: undefined,
    remark: '',
    items: [],
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.order_id === undefined || form.warehouse_id === undefined) return
  const items = form.items.filter((item) => item.quantity > 0)
  if (!items.length) {
    ElMessage.warning('请填写发货数量')
    return
  }
  submitting.value = true
  try {
    await createShipment({
      order_id: form.order_id,
      shipment_date: form.shipment_date,
      remark: form.remark || null,
      items: items.map((item) => ({
        order_item_id: item.order_item_id,
        warehouse_id: form.warehouse_id,
        quantity: item.quantity,
      })),
    })
    ElMessage.success('发货单已新增（草稿）')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doConfirm(row: Shipment): Promise<void> {
  try {
    await confirmShipment(row.id)
    ElMessage.success('发货已确认，库存已出库')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCancel(row: Shipment): Promise<void> {
  try {
    await cancelShipment(row.id)
    ElMessage.success('发货单已取消')
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
          <span class="page-title">发货管理</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增发货单</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="销售订单">
          <RemoteSelect v-model="query.order_id" :loader="loadOrderOptions" placeholder="全部" style="width: 240px" />
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
              <el-table-column label="仓库ID" prop="warehouse_id" width="100" align="right" />
              <el-table-column label="库位ID" prop="location_id" width="100" align="right" />
              <el-table-column label="发货数量" prop="quantity" width="110" align="right" />
              <el-table-column label="备注" prop="remark" min-width="140" />
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="发货单号" prop="shipment_no" min-width="150" />
        <el-table-column label="销售订单号" prop="order_no" min-width="150" />
        <el-table-column label="客户" prop="customer_name" min-width="150" />
        <el-table-column label="发货日期" prop="shipment_date" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="doConfirm(row)">确认发货</el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="danger" @click="doCancel(row)">取消</el-button>
            <span v-if="row.status !== 'DRAFT'">-</span>
          </template>
        </el-table-column>
        <template #empty>暂无发货单数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增发货单" width="760px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="销售订单" prop="order_id">
              <RemoteSelect
                v-model="form.order_id"
                :loader="loadOrderOptions"
                style="width: 100%"
                @change="onOrderChange"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="发货日期" prop="shipment_date">
              <el-date-picker v-model="form.shipment_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="发货仓库" prop="warehouse_id">
              <RemoteSelect v-model="form.warehouse_id" :loader="loadWarehouseOptions" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <el-table :data="form.items" border size="small">
        <el-table-column label="物料" prop="material_label" min-width="200" />
        <el-table-column label="未发数量" prop="remaining" width="110" align="right" />
        <el-table-column label="本次发货" width="160">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0" :max="row.remaining" :controls="false" style="width: 100%" />
          </template>
        </el-table-column>
      </el-table>
      <p class="form-tip">选择订单后自动带出订单行；保存后请在列表中「确认发货」以实际出库。</p>
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