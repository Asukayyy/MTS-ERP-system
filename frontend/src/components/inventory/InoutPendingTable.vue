<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  cancelStockOperation,
  confirmStockOperation,
  listStockOperations,
  listWarehouses,
} from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import { fmtQty } from '@/utils/format'
import type { RemoteOption, StockOperation } from '@/types/erp'

/**
 * 入库单 / 出库单列表（库存管理 → 入库管理 / 出库管理）。
 *
 * - 入库单来源只有三种：销售退货、采购到货、生产完工；
 * - 出库单来源只有两种：销售发货、生产领料；
 * - 业务单据不再自行选择仓库，**由仓库管理人员在这里决定仓库并确认**，
 *   确认后才真正增加 / 减少结存；
 * - 表单信息：来源模块 / 来源单据 / 物料编码、名称、规格、单位、数量 / 备注 / 状态。
 */
const props = defineProps<{ opType: 'INBOUND' | 'OUTBOUND' }>()

const isInbound = props.opType === 'INBOUND'
const actionLabel = isInbound ? '入库' : '出库'

const SOURCE_MODULE_NAMES: Record<string, string> = {
  sales: '销售',
  procurement: '采购',
  planning: '计划',
  inventory: '库存',
}

/** 来源类型按方向隔离：入库只有三种业务来源，出库只有两种，互不串台 */
const SOURCE_TYPE_OPTIONS: Record<'INBOUND' | 'OUTBOUND', { value: string; label: string }[]> = {
  INBOUND: [
    { value: 'SALES_RETURN', label: '销售退货' },
    { value: 'PURCHASE_RECEIPT', label: '采购到货' },
    { value: 'PRODUCTION_COMPLETION', label: '生产完工' },
  ],
  OUTBOUND: [
    { value: 'SALES_SHIPMENT', label: '销售发货' },
    { value: 'MATERIAL_REQUISITION', label: '生产领料' },
  ],
}

const sourceTypeOptions = SOURCE_TYPE_OPTIONS[props.opType]

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<StockOperation, { status: string; source_type: string; keyword: string }>(
    (params) => listStockOperations({ ...params, op_type: props.opType }),
    { status: '', source_type: '', keyword: '' },
  )

function sourceModuleName(moduleName?: string | null): string {
  if (!moduleName) return '手工'
  return SOURCE_MODULE_NAMES[moduleName] ?? moduleName
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({
    id: item.id,
    label: `${item.warehouse_code} ${item.warehouse_name}`,
  }))
}

// ---------------- 确认（在此选择仓库） ----------------

const confirmVisible = ref(false)
const confirming = ref<StockOperation | null>(null)
const submitting = ref(false)
const confirmForm = reactive<{ warehouse_id: number | undefined }>({ warehouse_id: undefined })

function openConfirm(row: StockOperation): void {
  confirming.value = row
  confirmForm.warehouse_id = row.warehouse_id ?? undefined
  confirmVisible.value = true
}

async function submitConfirm(): Promise<void> {
  const row = confirming.value
  if (!row) return
  if (!confirmForm.warehouse_id) {
    ElMessage.warning('请选择本次出入库的仓库')
    return
  }
  submitting.value = true
  try {
    await confirmStockOperation(row.id, { warehouse_id: confirmForm.warehouse_id })
    ElMessage.success(`已确认${actionLabel}，库存结存已更新`)
    confirmVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doCancel(row: StockOperation): Promise<void> {
  try {
    await cancelStockOperation(row.id)
    ElMessage.success(`${actionLabel}单已取消`)
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-form class="filter-bar" :inline="true" @submit.prevent>
      <el-form-item label="状态">
        <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
          <el-option label="待处理" value="DRAFT" />
          <el-option label="已完成" value="COMPLETED" />
          <el-option label="已取消" value="CANCELLED" />
        </el-select>
      </el-form-item>
      <el-form-item label="来源">
        <el-select v-model="query.source_type" clearable placeholder="全部" style="width: 150px">
          <el-option
            v-for="item in sourceTypeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="关键字">
        <el-input
          v-model="query.keyword"
          clearable
          placeholder="单号 / 来源单号 / 备注"
          style="width: 220px"
          @keyup.enter="search"
        />
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
            <el-table-column label="物料编码" prop="material_code" width="140" />
            <el-table-column label="物料名称" prop="material_name" min-width="160" />
            <el-table-column label="规格" prop="material_spec" min-width="140" />
            <el-table-column label="单位" prop="unit" width="80" />
            <el-table-column :label="`${actionLabel}数量`" width="110" align="right">
              <template #default="{ row: line }">{{ fmtQty(line.quantity) }}</template>
            </el-table-column>
            <el-table-column label="备注" prop="remark" min-width="160" />
            <template #empty>暂无明细</template>
          </el-table>
        </template>
      </el-table-column>
      <el-table-column :label="`${actionLabel}单号`" prop="operation_no" min-width="160" />
      <el-table-column label="来源模块" width="100">
        <template #default="{ row }">{{ sourceModuleName(row.source_module) }}</template>
      </el-table-column>
      <el-table-column label="来源单据" width="110">
        <template #default="{ row }"><StatusTag :status="row.source_type" /></template>
      </el-table-column>
      <el-table-column label="来源单号" prop="source_no" min-width="160">
        <template #default="{ row }">{{ row.source_no ?? '-' }}</template>
      </el-table-column>
      <el-table-column :label="`${actionLabel}日期`" prop="op_date" width="110" />
      <el-table-column label="仓库" width="120">
        <template #default="{ row }">
          {{ row.warehouse_id ? `#${row.warehouse_id}` : '待选择' }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }"><StatusTag :status="row.status" /></template>
      </el-table-column>
      <el-table-column label="备注" prop="remark" min-width="220" show-overflow-tooltip />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'DRAFT'">
            <el-button link type="primary" @click="openConfirm(row)">确认{{ actionLabel }}</el-button>
            <el-button link type="danger" @click="doCancel(row)">取消</el-button>
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <template #empty>暂无{{ actionLabel }}单</template>
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

    <el-dialog v-model="confirmVisible" :title="`确认${actionLabel}`" width="860px">
      <el-descriptions v-if="confirming" :column="2" border size="small" class="confirm-head">
        <el-descriptions-item :label="`${actionLabel}单号`">{{ confirming.operation_no }}</el-descriptions-item>
        <el-descriptions-item label="来源">
          {{ sourceModuleName(confirming.source_module) }}
          <StatusTag :status="confirming.source_type" />
          {{ confirming.source_no ?? '' }}
        </el-descriptions-item>
        <el-descriptions-item label="业务日期">{{ confirming.op_date }}</el-descriptions-item>
        <el-descriptions-item label="备注">{{ confirming.remark ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="明细行数">{{ confirming.items.length }}</el-descriptions-item>
        <el-descriptions-item label="合计数量">
          {{ fmtQty(confirming.items.reduce((sum, line) => sum + Number(line.quantity ?? 0), 0)) }}
        </el-descriptions-item>
      </el-descriptions>

      <el-table v-if="confirming" :data="confirming.items" border size="small">
        <el-table-column label="物料编码" prop="material_code" width="140" />
        <el-table-column label="物料名称" prop="material_name" min-width="160" />
        <el-table-column label="规格" prop="material_spec" min-width="140" />
        <el-table-column label="单位" prop="unit" width="80" />
        <el-table-column :label="`${actionLabel}数量`" width="110" align="right">
          <template #default="{ row }">{{ fmtQty(row.quantity) }}</template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="160" />
      </el-table>

      <el-form label-width="110px" class="confirm-form">
        <el-form-item :label="`${actionLabel}仓库`" required>
          <RemoteSelect
            v-model="confirmForm.warehouse_id"
            :loader="loadWarehouseOptions"
            placeholder="请选择仓库"
            style="width: 100%"
          />
        </el-form-item>
        <div class="form-tip">
          确认后按明细数量{{ isInbound ? '增加' : '减少' }}所选仓库的结存；出库时可用库存不足会被拒绝（错误码 5001），整单回滚。
        </div>
      </el-form>

      <template #footer>
        <el-button @click="confirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitConfirm">
          确认{{ actionLabel }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.nested-table {
  margin: 4px 0 4px 48px;
  width: calc(100% - 48px);
}

.confirm-head {
  margin-bottom: 12px;
}

.confirm-form {
  margin-top: 12px;
}
</style>
