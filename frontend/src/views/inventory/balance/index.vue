<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getLowStockReport, listBalances, listWarehouses } from '@/api/inventory'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { Balance, LowStock, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Balance, { keyword: string; warehouse_id: number | undefined }>(
    (params) => listBalances(params),
    { keyword: '', warehouse_id: undefined },
  )

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

// ---------------- 低库存 / 缺料报表 ----------------

const lowStockLoading = ref(false)
const lowStockRows = ref<LowStock[]>([])

async function loadLowStock(): Promise<void> {
  lowStockLoading.value = true
  try {
    lowStockRows.value = await getLowStockReport()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    lowStockLoading.value = false
  }
}

// ---------------- 低库存 / 缺料报表 ----------------

function refreshAll(): void {
  search()
  loadLowStock()
}

onMounted(() => {
  load()
  loadLowStock()
})
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">实时库存</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="refreshAll">刷新</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="关键词">
          <el-input v-model="query.keyword" placeholder="物料编码 / 名称" clearable style="width: 200px" />
        </el-form-item>
        <el-form-item label="仓库">
          <RemoteSelect v-model="query.warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="160" />
        <el-table-column label="仓库" min-width="150">
          <template #default="{ row }">{{ row.warehouse_name || `ID ${row.warehouse_id}` }}</template>
        </el-table-column>
        <el-table-column label="现有量" prop="on_hand" width="110" align="right" />
        <el-table-column label="锁定量" prop="locked_quantity" width="110" align="right" />
        <el-table-column label="可用量" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'qty-zero': toNumber(row.available_quantity) <= 0 }">{{ row.available_quantity }}</span>
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

    <el-card shadow="never" style="margin-top: 12px">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">库存预警（低于安全库存）</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="loadLowStock">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="lowStockLoading" :data="lowStockRows" border size="small">
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="160" />
        <el-table-column label="可用量" prop="available_quantity" width="120" align="right" />
        <el-table-column label="安全库存" prop="safety_stock" width="120" align="right" />
        <el-table-column label="缺口数量" prop="shortage_qty" width="120" align="right" />
        <template #empty>暂无低于安全库存的物料</template>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.qty-zero {
  color: var(--el-color-danger);
  font-weight: 600;
}
</style>