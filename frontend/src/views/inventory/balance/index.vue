<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  getBalanceSummary,
  listBalances,
  listWarehouses,
} from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import { fmtQty } from '@/utils/format'
import type { Balance, BalanceSummary, RemoteOption } from '@/types/erp'

type SortQuery = {
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    Balance,
    { keyword: string; warehouse_id: number | undefined; sales_category: string; quantity_gt: number | undefined } & SortQuery
  >((params) => listBalances(params), {
    keyword: '',
    warehouse_id: undefined,
    sales_category: '',
    quantity_gt: 0,
    sort_by: undefined,
    sort_order: undefined,
  })

/** 销售类别：整机 / 可售备件（如转椅轮子）/ 内部件 */
const SALES_CATEGORIES = [
  { value: 'MACHINE', label: '整机' },
  { value: 'SPARE', label: '可售备件' },
  { value: 'INTERNAL', label: '内部件' },
]

const summary = ref<BalanceSummary[]>([])

function summaryOf(category: string): { onHand: number; available: number; count: number } {
  const hit = summary.value.find((item) => item.sales_category === category)
  return {
    onHand: hit ? toNumber(hit.on_hand) : 0,
    available: hit ? toNumber(hit.available_quantity) : 0,
    count: hit?.count ?? 0,
  }
}

async function loadSummary(): Promise<void> {
  try {
    summary.value = await getBalanceSummary({
      keyword: query.keyword || undefined,
      warehouse_id: query.warehouse_id,
      sales_category: query.sales_category || undefined,
    })
  } catch {
    summary.value = []
  }
}

async function doSearch(): Promise<void> {
  await search()
  await loadSummary()
}

async function doReset(): Promise<void> {
  await reset()
  await loadSummary()
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

onMounted(() => {
  load()
  loadSummary()
})

/** 点击表头排序 → 全量后端排序（跨分页） */
const SORT_BY_MAP: Record<string, string> = {
  material_code: 'material_code',
  material_name: 'material_name',
  material_sales_category: 'material_sales_category',
  material_abc_class: 'material_abc_class',
  warehouse_name: 'warehouse_name',
  warehouse_code: 'warehouse_code',
  on_hand: 'quantity',
  available_quantity: 'available_quantity',
  safety_stock: 'safety_stock',
}

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  if (!prop || !order) {
    query.sort_by = undefined
    query.sort_order = undefined
  } else {
    query.sort_by = SORT_BY_MAP[prop] || prop
    query.sort_order = order === 'ascending' ? 'asc' : 'desc'
  }
  changePage(1) // 回到第 1 页
  load()
}
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">实时库存</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="load">刷新</el-button>
        </div>
      </template>

      <div class="summary-cards">
        <div class="summary-card summary-card--machine">
          <span class="summary-card__label">整机库存</span>
          <span class="summary-card__value">{{ summaryOf('MACHINE').onHand }}</span>
          <span class="summary-card__meta">
            可用 {{ summaryOf('MACHINE').available }} · {{ summaryOf('MACHINE').count }} 条结存
          </span>
        </div>
        <div class="summary-card summary-card--spare">
          <span class="summary-card__label">可售备件库存</span>
          <span class="summary-card__value">{{ summaryOf('SPARE').onHand }}</span>
          <span class="summary-card__meta">
            可用 {{ summaryOf('SPARE').available }} · {{ summaryOf('SPARE').count }} 条结存
          </span>
        </div>
        <div class="summary-card summary-card--internal">
          <span class="summary-card__label">内部件库存</span>
          <span class="summary-card__value">{{ summaryOf('INTERNAL').onHand }}</span>
          <span class="summary-card__meta">
            可用 {{ summaryOf('INTERNAL').available }} · {{ summaryOf('INTERNAL').count }} 条结存
          </span>
        </div>
      </div>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="关键词">
          <el-input v-model="query.keyword" placeholder="物料编码 / 名称" clearable style="width: 200px" />
        </el-form-item>
        <el-form-item label="销售类别">
          <el-select v-model="query.sales_category" clearable placeholder="全部" style="width: 130px">
            <el-option v-for="item in SALES_CATEGORIES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="仓库">
          <RemoteSelect v-model="query.warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doSearch">查询</el-button>
          <el-button @click="doReset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small" @sort-change="handleSortChange">
        <el-table-column label="物料编码" prop="material_code" min-width="130" sortable="custom" />
        <el-table-column label="物料名称" prop="material_name" min-width="160" sortable="custom" />
        <el-table-column label="销售类别" width="100" sortable="custom" prop="material_sales_category">
          <template #default="{ row }">
            {{ SALES_CATEGORIES.find((item) => item.value === row.material_sales_category)?.label ?? '内部件' }}
          </template>
        </el-table-column>
        <el-table-column label="ABC" width="70" align="center" sortable="custom" prop="material_abc_class">
          <template #default="{ row }">
            <el-tag v-if="row.material_abc_class" :type="row.material_abc_class === 'A' ? 'danger' : row.material_abc_class === 'B' ? 'warning' : 'info'" size="small">
              {{ row.material_abc_class }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="仓库" min-width="180" sortable="custom" prop="warehouse_name">
          <template #default="{ row }">
            {{ row.warehouse_name || `ID ${row.warehouse_id}` }}
            <span style="color: #98a2ad; font-size: 12px; margin-left: 4px" v-if="row.warehouse_code">
              ({{ row.warehouse_code }})
            </span>
            <el-tag v-if="row.is_available_warehouse === false" type="info" size="small" style="margin-left: 4px">
              废品
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="现有量" width="110" align="right" prop="on_hand" sortable="custom">
          <template #default="{ row }">{{ fmtQty(row.on_hand) }}</template>
        </el-table-column>
        <el-table-column label="可用量" width="110" align="right" prop="available_quantity" sortable="custom">
          <template #default="{ row }">
            <template v-if="row.is_available_warehouse === false">
              <span style="color: #98a2ad">已报废</span>
            </template>
            <template v-else>
              <span :class="{ 'qty-zero': toNumber(row.available_quantity) <= 0 }">{{ fmtQty(row.available_quantity) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="安全库存" width="110" align="right" prop="safety_stock" sortable="custom">
          <template #default="{ row }">
            <template v-if="row.is_available_warehouse === false">
              <span style="color: #c0c4cc">—</span>
            </template>
            <template v-else>
              <span
                :class="{
                  'qty-zero':
                    toNumber(row.material_total_available) < toNumber(row.safety_stock),
                }"
                >{{ fmtQty(row.safety_stock) }}</span
              >
            </template>
          </template>
        </el-table-column>
        <template #empty>暂无库存结存数据</template>
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
  </div>
</template>

<style scoped>
.qty-zero {
  color: var(--el-color-danger);
  font-weight: 600;
}

.summary-cards {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.summary-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid #e6ebf2;
  background: #f7f9fc;
}

.summary-card--machine {
  border-color: #cfe3ff;
  background: #f2f8ff;
}

.summary-card--spare {
  border-color: #c8ebe4;
  background: #f1fbf8;
}

.summary-card__label {
  font-size: 12px;
  color: #5b6b7c;
}

.summary-card__value {
  font-size: 20px;
  font-weight: 600;
  color: #1f2d3d;
}

.summary-card__meta {
  font-size: 12px;
  color: #98a2ad;
}
</style>