<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
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
 *
 * 主表展示**全部**结存行（不再只显示已配置订货点的行），行内可编辑；
 * 工具栏「设置订货点」按 物料 + 仓库 定位结存行后配置订货点，
 * 避免"表里没有已配置行 → 无处配置第一条订货点"的死锁。
 */
const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Balance, { material_id: number | undefined; warehouse_id: number | undefined }>(
    (params) => listBalances({ ...params }),
    { material_id: undefined, warehouse_id: undefined },
  )

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
/** 编辑既有结存行时保存该行；为 null 表示新增（按 物料 + 仓库 定位结存行） */
const editingBalance = ref<Balance | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  material_id?: number
  warehouse_id?: number
  reorder_point: number
  reorder_quantity: number
}>({
  material_id: undefined,
  warehouse_id: undefined,
  reorder_point: 0,
  reorder_quantity: 0,
})

const rules: FormRules = {
  material_id: [{ required: true, message: '请选择物料', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择仓库', trigger: 'change' }],
  reorder_point: [{ required: true, message: '请输入订货点', trigger: 'blur' }],
  reorder_quantity: [{ required: true, message: '请输入建议订货量', trigger: 'blur' }],
}

function openCreate(): void {
  editingBalance.value = null
  Object.assign(form, {
    material_id: undefined,
    warehouse_id: undefined,
    reorder_point: 0,
    reorder_quantity: 0,
  })
  dialogVisible.value = true
}

function openEdit(row: Balance): void {
  editingBalance.value = row
  Object.assign(form, {
    material_id: row.material_id,
    warehouse_id: row.warehouse_id,
    reorder_point: Number(row.reorder_point) || 0,
    reorder_quantity: Number(row.reorder_quantity) || 0,
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    let balanceId = editingBalance.value?.id
    if (!balanceId) {
      // 订货点挂在结存行上，没有结存的物料需先入库
      const data = await listBalances({
        material_id: form.material_id,
        warehouse_id: form.warehouse_id,
        page: 1,
        page_size: 1,
      })
      const row = data.items[0]
      if (!row) {
        ElMessage.warning('该物料在该仓库还没有结存，请先在「入库」页入库后再设置订货点')
        return
      }
      balanceId = row.id
    }
    await updateBalanceReorder(balanceId, {
      reorder_point: form.reorder_point,
      reorder_quantity: form.reorder_quantity,
    })
    ElMessage.success(editingBalance.value ? '订货点已更新' : '订货点已设置')
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
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">设置订货点</el-button>
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

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="160" />
        <el-table-column label="仓库" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.warehouse_code }} {{ row.warehouse_name }}</template>
        </el-table-column>
        <el-table-column label="现存量" prop="on_hand" width="110" align="right" />
        <el-table-column label="可用量" prop="available_quantity" width="110" align="right" />
        <el-table-column label="订货点" prop="reorder_point" width="110" align="right" />
        <el-table-column label="建议订货量" prop="reorder_quantity" width="120" align="right" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑订货点</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无库存结存</template>
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
          <span class="page-title">补库建议（当前库存低于订货点）</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="loadSuggestions">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="suggestionLoading" :data="suggestions" border size="small">
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="150" />
        <el-table-column label="仓库" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.warehouse_code }} {{ row.warehouse_name }}</template>
        </el-table-column>
        <el-table-column label="订货点" prop="reorder_point" width="110" align="right" />
        <el-table-column label="当前库存" prop="current_qty" width="110" align="right" />
        <el-table-column label="建议补库量" prop="suggested_qty" width="120" align="right" />
        <el-table-column label="目标库存" prop="target_qty" width="110" align="right" />
        <template #empty>暂无补库建议</template>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingBalance ? '编辑订货点' : '设置订货点'" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <template v-if="!editingBalance">
          <el-form-item label="物料" prop="material_id">
            <RemoteSelect v-model="form.material_id" :loader="loadMaterialOptions" placeholder="请选择物料" style="width: 100%" />
          </el-form-item>
          <el-form-item label="仓库" prop="warehouse_id">
            <RemoteSelect v-model="form.warehouse_id" :loader="loadWarehouseOptions" placeholder="请选择仓库" style="width: 100%" />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="物料">
            <span>{{ editingBalance?.material_code }} {{ editingBalance?.material_name }}</span>
          </el-form-item>
          <el-form-item label="仓库">
            <span>{{ editingBalance?.warehouse_code }} {{ editingBalance?.warehouse_name }}</span>
          </el-form-item>
        </template>
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
