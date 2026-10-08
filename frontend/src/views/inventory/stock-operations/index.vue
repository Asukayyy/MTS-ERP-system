<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  cancelStockOperation,
  confirmStockOperation,
  createStockOperation,
  listStockOperations,
  listWarehouses,
} from '@/api/inventory'
import { listMaterials, listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { RemoteOption, StockOperation } from '@/types/erp'

/**
 * 移库 / 盘点共用页面组件。
 *
 * - `opType = 'TRANSFER'`：移库模式（源仓库 + 目标仓库 + 移库数量）
 * - `opType = 'STOCKTAKE'`：盘点模式（仓库 + 账面 / 实盘数量）
 * 后端统一走 `/inventory/stock-operations`，按 `op_type` 区分。
 */
const props = defineProps<{ opType: 'TRANSFER' | 'STOCKTAKE' }>()

const isTransfer = props.opType === 'TRANSFER'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<StockOperation, { status: string; warehouse_id: number | undefined }>(
    (params) => listStockOperations({ ...params, op_type: props.opType }),
    { status: '', warehouse_id: undefined },
  )

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadOperatorOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

interface OperationLineForm {
  material_id: number | undefined
  quantity: number
  book_qty: number | undefined
  actual_qty: number
  remark: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  operation_no: string
  from_warehouse_id: number | undefined
  to_warehouse_id: number | undefined
  warehouse_id: number | undefined
  op_date: string
  operator_id: number | undefined
  remark: string
  items: OperationLineForm[]
}>({
  operation_no: '',
  from_warehouse_id: undefined,
  to_warehouse_id: undefined,
  warehouse_id: undefined,
  op_date: '',
  operator_id: undefined,
  remark: '',
  items: [],
})

const rules = reactive<FormRules>({
  ...(isTransfer
    ? {
        from_warehouse_id: [{ required: true, message: '请选择源仓库', trigger: 'change' }],
        to_warehouse_id: [{ required: true, message: '请选择目标仓库', trigger: 'change' }],
      }
    : {
        warehouse_id: [{ required: true, message: '请选择盘点仓库', trigger: 'change' }],
      }),
  op_date: [{ required: true, message: isTransfer ? '请选择移库日期' : '请选择盘点日期', trigger: 'change' }],
})

function addLine(): void {
  form.items.push(
    isTransfer
      ? { material_id: undefined, quantity: 1, book_qty: undefined, actual_qty: 0, remark: '' }
      : { material_id: undefined, quantity: 0, book_qty: undefined, actual_qty: 0, remark: '' },
  )
}

function removeLine(index: number): void {
  form.items.splice(index, 1)
}

function openCreate(): void {
  Object.assign(form, {
    operation_no: '',
    from_warehouse_id: undefined,
    to_warehouse_id: undefined,
    warehouse_id: undefined,
    op_date: '',
    operator_id: undefined,
    remark: '',
    items: [],
  })
  addLine()
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.items.length === 0 || form.items.some((item) => !item.material_id)) {
    ElMessage.warning('请为每一行选择物料')
    return
  }
  if (isTransfer && form.from_warehouse_id === form.to_warehouse_id) {
    ElMessage.warning('源仓库与目标仓库不能相同')
    return
  }
  submitting.value = true
  try {
    const payload: Record<string, unknown> = isTransfer
      ? {
          op_type: 'TRANSFER',
          operation_no: form.operation_no || null,
          from_warehouse_id: form.from_warehouse_id,
          to_warehouse_id: form.to_warehouse_id,
          op_date: form.op_date,
          operator_id: form.operator_id ?? null,
          remark: form.remark || null,
          items: form.items.map((item) => ({
            material_id: item.material_id,
            quantity: item.quantity,
            remark: item.remark || null,
          })),
        }
      : {
          op_type: 'STOCKTAKE',
          operation_no: form.operation_no || null,
          warehouse_id: form.warehouse_id,
          op_date: form.op_date,
          operator_id: form.operator_id ?? null,
          remark: form.remark || null,
          items: form.items.map((item) => ({
            material_id: item.material_id,
            book_qty: item.book_qty ?? null,
            actual_qty: item.actual_qty,
            remark: item.remark || null,
          })),
        }
    await createStockOperation(payload)
    ElMessage.success(isTransfer ? '移库单已新增' : '盘点单已新增')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doConfirm(row: StockOperation): Promise<void> {
  try {
    await confirmStockOperation(row.id)
    ElMessage.success(isTransfer ? '移库已确认，库存已转移' : '盘点已确认，差异已生成调整流水')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCancel(row: StockOperation): Promise<void> {
  try {
    await cancelStockOperation(row.id)
    ElMessage.success(isTransfer ? '移库单已取消' : '盘点单已取消')
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
          <span class="page-title">{{ isTransfer ? '移库' : '盘点' }}</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">
            {{ isTransfer ? '新增移库单' : '新增盘点单' }}
          </el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item :label="isTransfer ? '仓库' : '盘点仓库'">
          <RemoteSelect v-model="query.warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 220px" />
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
            <el-table class="nested-table" :data="row.items" border size="small">
              <el-table-column label="物料ID" prop="material_id" width="90" align="right" />
              <template v-if="isTransfer">
                <el-table-column label="移库数量" prop="quantity" width="110" align="right" />
              </template>
              <template v-else>
                <el-table-column label="账面数量" prop="book_qty" width="110" align="right" />
                <el-table-column label="实盘数量" prop="actual_qty" width="110" align="right" />
                <el-table-column label="差异" prop="difference" width="110" align="right" />
              </template>
              <el-table-column label="备注" prop="remark" min-width="140" />
              <template #empty>暂无明细</template>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column :label="isTransfer ? '移库单号' : '盘点单号'" prop="operation_no" min-width="150" />
        <el-table-column label="类型" prop="op_type" width="110" />
        <template v-if="isTransfer">
          <el-table-column label="源仓库ID" prop="from_warehouse_id" width="110" align="right" />
          <el-table-column label="目标仓库ID" prop="to_warehouse_id" width="110" align="right" />
        </template>
        <el-table-column v-else label="仓库ID" prop="warehouse_id" width="110" align="right" />
        <el-table-column :label="isTransfer ? '移库日期' : '盘点日期'" prop="op_date" width="110" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="140" />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="doConfirm(row)">
              {{ isTransfer ? '确认移库' : '确认盘点' }}
            </el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="danger" @click="doCancel(row)">
              取消
            </el-button>
            <span v-if="row.status !== 'DRAFT'">-</span>
          </template>
        </el-table-column>
        <template #empty>暂无数据</template>
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

    <el-dialog v-model="dialogVisible" :title="isTransfer ? '新增移库单' : '新增盘点单'" width="960px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item :label="isTransfer ? '移库单号' : '盘点单号'">
              <el-input v-model="form.operation_no" placeholder="留空自动生成" />
            </el-form-item>
          </el-col>
          <template v-if="isTransfer">
            <el-col :span="8">
              <el-form-item label="源仓库" prop="from_warehouse_id">
                <RemoteSelect v-model="form.from_warehouse_id" :loader="loadWarehouseOptions" placeholder="请选择" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="目标仓库" prop="to_warehouse_id">
                <RemoteSelect v-model="form.to_warehouse_id" :loader="loadWarehouseOptions" placeholder="请选择" style="width: 100%" />
              </el-form-item>
            </el-col>
          </template>
          <el-col v-else :span="8">
            <el-form-item label="盘点仓库" prop="warehouse_id">
              <RemoteSelect v-model="form.warehouse_id" :loader="loadWarehouseOptions" placeholder="请选择仓库" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="isTransfer ? '移库日期' : '盘点日期'" prop="op_date">
              <el-date-picker v-model="form.op_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="操作人">
              <RemoteSelect v-model="form.operator_id" :loader="loadOperatorOptions" placeholder="可选" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="备注">
              <el-input v-model="form.remark" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">{{ isTransfer ? '移库明细' : '盘点明细' }}</el-divider>
        <div class="table-toolbar">
          <span class="table-toolbar__spacer" />
          <el-button size="small" @click="addLine">添加明细行</el-button>
        </div>
        <el-table :data="form.items" border size="small">
          <el-table-column label="物料" min-width="200">
            <template #default="{ row }">
              <RemoteSelect v-model="row.material_id" :loader="loadMaterialOptions" placeholder="请选择物料" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column v-if="isTransfer" label="移库数量" width="160">
            <template #default="{ row }">
              <el-input-number v-model="row.quantity" :min="0.0001" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <template v-else>
            <el-table-column label="账面数量" width="150">
              <template #default="{ row }">
                <el-input-number v-model="row.book_qty" :min="0" :controls="false" placeholder="留空自动取" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column label="实盘数量" width="150">
              <template #default="{ row }">
                <el-input-number v-model="row.actual_qty" :min="0" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
          </template>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeLine($index)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>请添加明细行</template>
        </el-table>
        <div v-if="!isTransfer" class="form-tip">账面数量留空时，确认盘点由后端按当前结存自动带出。</div>
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
