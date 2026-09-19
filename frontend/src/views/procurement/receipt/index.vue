<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  cancelReceipt,
  confirmReceipt,
  createReceipt,
  getPurchaseOrder,
  listPurchaseOrders,
  listReceipts,
} from '@/api/procurement'
import { listWarehouses } from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { Receipt, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Receipt, { status: string }>((params) => listReceipts(params), { status: '' })

async function loadOrderOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPurchaseOrders({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.order_no} · 供应商${item.supplier_id}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

interface ReceiptLineForm {
  order_item_id: number
  material_id: number
  quantity: number
  qualified_qty: number
  remark: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const loadingLines = ref(false)
const form = reactive<{
  purchase_order_id: number | undefined
  supplier_id: number | undefined
  warehouse_id: number | undefined
  receipt_date: string
  remark: string
  items: ReceiptLineForm[]
}>({
  purchase_order_id: undefined,
  supplier_id: undefined,
  warehouse_id: undefined,
  receipt_date: '',
  remark: '',
  items: [],
})

function openCreate(): void {
  Object.assign(form, {
    purchase_order_id: undefined,
    supplier_id: undefined,
    warehouse_id: undefined,
    receipt_date: '',
    remark: '',
    items: [],
  })
  dialogVisible.value = true
}

/** 选择采购订单后拉取订单明细，按未到货数量生成到货行 */
async function onOrderChange(orderId: number | undefined): Promise<void> {
  form.items = []
  if (!orderId) return
  loadingLines.value = true
  try {
    const order = await getPurchaseOrder(orderId)
    form.supplier_id = order.supplier_id
    form.items = order.items.map((item) => {
      const remaining = toNumber(item.quantity) - toNumber(item.received_qty)
      return {
        order_item_id: item.id,
        material_id: item.material_id,
        quantity: remaining > 0 ? remaining : 0,
        qualified_qty: remaining > 0 ? remaining : 0,
        remark: '',
      }
    })
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loadingLines.value = false
  }
}

async function submit(): Promise<void> {
  if (!form.purchase_order_id) {
    ElMessage.warning('请选择采购订单')
    return
  }
  if (!form.warehouse_id) {
    ElMessage.warning('请选择收货仓库')
    return
  }
  if (!form.receipt_date) {
    ElMessage.warning('请选择到货日期')
    return
  }
  const items = form.items.filter((item) => item.quantity > 0)
  if (items.length === 0) {
    ElMessage.warning('到货数量必须大于 0')
    return
  }
  submitting.value = true
  try {
    // 后端按订单行带出物料与供应商，前端只需提交订单行ID与数量
    await createReceipt({
      purchase_order_id: form.purchase_order_id,
      warehouse_id: form.warehouse_id,
      receipt_date: form.receipt_date,
      remark: form.remark || null,
      items: items.map((item) => ({
        order_item_id: item.order_item_id,
        quantity: item.quantity,
        qualified_qty: item.qualified_qty,
        remark: item.remark || null,
      })),
    })
    ElMessage.success('到货单已新增，确认后合格品入库')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doConfirm(row: Receipt): Promise<void> {
  try {
    await confirmReceipt(row.id)
    ElMessage.success('到货已确认，合格品已入库')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCancel(row: Receipt): Promise<void> {
  try {
    await cancelReceipt(row.id)
    ElMessage.success('到货单已取消')
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
          <span class="page-title">到货管理</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增到货单</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
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
        <el-table-column type="expand">
          <template #default="{ row }">
            <el-table class="nested-table" :data="row.items" border size="small">
              <el-table-column label="订单行ID" prop="order_item_id" width="100" align="right" />
              <el-table-column label="物料ID" prop="material_id" width="90" align="right" />
              <el-table-column label="到货数量" prop="quantity" width="110" align="right" />
              <el-table-column label="合格数量" prop="qualified_qty" width="110" align="right" />
              <el-table-column label="收货库位ID" prop="location_id" width="110" align="right" />
              <el-table-column label="备注" prop="remark" min-width="140" />
              <template #empty>暂无到货明细</template>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="到货单号" prop="receipt_no" min-width="150" />
        <el-table-column label="采购订单" min-width="150">
          <template #default="{ row }">{{ row.order_no || `ID ${row.purchase_order_id}` }}</template>
        </el-table-column>
        <el-table-column label="供应商" min-width="160">
          <template #default="{ row }">{{ row.supplier_name || `ID ${row.supplier_id}` }}</template>
        </el-table-column>
        <el-table-column label="收货仓库ID" prop="warehouse_id" width="110" align="right" />
        <el-table-column label="到货日期" prop="receipt_date" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
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
        <template #empty>暂无到货单数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增到货单" width="860px">
      <el-form label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="采购订单">
              <RemoteSelect
                v-model="form.purchase_order_id"
                :loader="loadOrderOptions"
                placeholder="请选择采购订单"
                style="width: 100%"
                @change="onOrderChange"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="供应商ID">
              <el-input :model-value="form.supplier_id" disabled placeholder="选择采购订单后自动带出" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="收货仓库">
              <RemoteSelect
                v-model="form.warehouse_id"
                :loader="loadWarehouseOptions"
                placeholder="请选择仓库"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="到货日期">
              <el-date-picker v-model="form.receipt_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">到货明细</el-divider>
        <el-table v-loading="loadingLines" :data="form.items" border size="small">
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
          <el-table-column label="备注" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.remark" />
            </template>
          </el-table-column>
          <template #empty>请先选择采购订单</template>
        </el-table>
        <div class="form-tip">确认到货后系统按合格数量调用库存入库契约，写入库存流水与结存。</div>
      </el-form>
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