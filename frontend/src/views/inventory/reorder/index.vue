<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { listBalances, listReorderSuggestions, listWarehouses, updateBalanceReorder } from '@/api/inventory'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { Balance, ReorderSuggestion, RemoteOption } from '@/types/erp'

/**
 * 订货点维护页：订货点 / 建议订货量直接维护在库存结存（inv_balance）上，
 * 不再使用独立的订货点规则表。
 */
const { loading, rows, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Balance, { material_id: number | undefined; warehouse_id: number | undefined }>(
    (params) => listBalances(params),
    { material_id: undefined, warehouse_id: undefined },
  )

/** 只展示已配置订货点（reorder_point 不为空）的结存行 */
const configuredRows = computed(() => rows.value.filter((r) => r.reorder_point != null))
const configuredTotal = computed(() => configuredRows.value.length)

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingBalance = ref<Balance | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{ reorder_point: number; reorder_quantity: number }>({
  reorder_point: 0,
  reorder_quantity: 0,
})

const rules: FormRules = {
  reorder_point: [{ required: true, message: '请输入订货点', trigger: 'blur' }],
  reorder_quantity: [{ required: true, message: '请输入建议订货量', trigger: 'blur' }],
}

function openEdit(row: Balance): void {
  editingBalance.value = row
  Object.assign(form, {
    reorder_point: Number(row.reorder_point) || 0,
    reorder_quantity: Number(row.reorder_quantity) || 0,
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (!editingBalance.value) return
  submitting.value = true
  try {
    await updateBalanceReorder(editingBalance.value.id, {
      reorder_point: form.reorder_point,
      reorder_quantity: form.reorder_quantity,
    })
    ElMessage.success('订货点已更新')
    dialogVisible.value = false
    await load()
    await loadSuggestions()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

// ---------------- 补库建议 ----------------

const suggestionLoading = ref(false)
const suggestions = ref<ReorderSuggestion[]>([])

async function loadSuggestions(): Promise<void> {
  suggestionLoading.value = true
  try {
    suggestions.value = await listReorderSuggestions()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    suggestionLoading.value = false
  }
}

onMounted(() => {
  load()
  loadSuggestions()
})
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">订货点</span>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="物料">
          <RemoteSelect v-model="query.material_id" :loader="loadMaterialOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item label="仓库">
          <RemoteSelect v-model="query.warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="configuredRows" border size="small">
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="160" />
        <el-table-column label="仓库ID" prop="warehouse_id" width="100" align="right" />
        <el-table-column label="现存量" prop="on_hand" width="110" align="right" />
        <el-table-column label="可用量" prop="available_quantity" width="110" align="right" />
        <el-table-column label="订货点" prop="reorder_point" width="110" align="right" />
        <el-table-column label="建议订货量" prop="reorder_quantity" width="120" align="right" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑订货点</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无已配置订货点的库存结存</template>
      </el-table>

      <div class="pager">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="configuredTotal"
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
          <span class="page-title">补库建议（当前库存低于订货点）</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="loadSuggestions">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="suggestionLoading" :data="suggestions" border size="small">
        <el-table-column label="物料ID" prop="material_id" width="100" align="right" />
        <el-table-column label="仓库ID" prop="warehouse_id" width="100" align="right" />
        <el-table-column label="订货点" prop="reorder_point" width="110" align="right" />
        <el-table-column label="当前库存" prop="current_qty" width="110" align="right" />
        <el-table-column label="建议补库量" prop="suggested_qty" width="120" align="right" />
        <el-table-column label="目标库存" prop="target_qty" width="110" align="right" />
        <template #empty>暂无补库建议</template>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="编辑订货点" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="物料">
          <span>{{ editingBalance?.material_code }} {{ editingBalance?.material_name }}</span>
        </el-form-item>
        <el-form-item label="仓库ID">
          <span>{{ editingBalance?.warehouse_id }}</span>
        </el-form-item>
        <el-form-item label="订货点" prop="reorder_point">
          <el-input-number v-model="form.reorder_point" :min="0" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="建议订货量" prop="reorder_quantity">
          <el-input-number v-model="form.reorder_quantity" :min="0" :controls="false" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
