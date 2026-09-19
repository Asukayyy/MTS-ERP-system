<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createReorderRule,
  listReorderRules,
  listReorderSuggestions,
  listWarehouses,
  setReorderRuleStatus,
  updateReorderRule,
} from '@/api/inventory'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { ReorderRule, ReorderSuggestion, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<ReorderRule, { status: string; material_id: number | undefined; warehouse_id: number | undefined }>(
    (params) => listReorderRules(params),
    { status: '', material_id: undefined, warehouse_id: undefined },
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
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  material_id: number | undefined
  warehouse_id: number | undefined
  reorder_point: number
  reorder_quantity: number
  remark: string
}>({ material_id: undefined, warehouse_id: undefined, reorder_point: 0, reorder_quantity: 0, remark: '' })

const rules: FormRules = {
  material_id: [{ required: true, message: '请选择物料', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择仓库', trigger: 'change' }],
  reorder_point: [{ required: true, message: '请输入订货点', trigger: 'blur' }],
  reorder_quantity: [{ required: true, message: '请输入建议订货量', trigger: 'blur' }],
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    material_id: undefined,
    warehouse_id: undefined,
    reorder_point: 0,
    reorder_quantity: 0,
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: ReorderRule): void {
  editingId.value = row.id
  Object.assign(form, {
    material_id: row.material_id,
    warehouse_id: row.warehouse_id,
    reorder_point: Number(row.reorder_point),
    reorder_quantity: Number(row.reorder_quantity),
    remark: row.remark ?? '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editingId.value === null) {
      await createReorderRule({
        material_id: form.material_id,
        warehouse_id: form.warehouse_id,
        reorder_point: form.reorder_point,
        reorder_quantity: form.reorder_quantity,
        remark: form.remark || null,
      })
      ElMessage.success('订货点规则已新增')
    } else {
      await updateReorderRule(editingId.value, {
        reorder_point: form.reorder_point,
        reorder_quantity: form.reorder_quantity,
        remark: form.remark || null,
      })
      ElMessage.success('订货点规则已更新')
    }
    dialogVisible.value = false
    await load()
    await loadSuggestions()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function toggleStatus(row: ReorderRule): Promise<void> {
  const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'
  try {
    await setReorderRuleStatus(row.id, next)
    ElMessage.success(next === 'ACTIVE' ? '规则已启用' : '规则已停用')
    await load()
    await loadSuggestions()
  } catch (error) {
    ElMessage.error((error as Error).message)
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
          <el-button type="primary" @click="openCreate">新增订货点规则</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="物料">
          <RemoteSelect v-model="query.material_id" :loader="loadMaterialOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item label="仓库">
          <RemoteSelect v-model="query.warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 200px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="启用" value="ACTIVE" />
            <el-option label="停用" value="INACTIVE" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="160" />
        <el-table-column label="仓库ID" prop="warehouse_id" width="100" align="right" />
        <el-table-column label="订货点" prop="reorder_point" width="110" align="right" />
        <el-table-column label="建议订货量" prop="reorder_quantity" width="120" align="right" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="140" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link :type="row.status === 'ACTIVE' ? 'danger' : 'success'" @click="toggleStatus(row)">
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无订货点规则</template>
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
        <el-table-column label="物料ID" prop="material_id" width="100" align="right" />
        <el-table-column label="仓库ID" prop="warehouse_id" width="100" align="right" />
        <el-table-column label="订货点" prop="reorder_point" width="110" align="right" />
        <el-table-column label="当前库存" prop="current_qty" width="110" align="right" />
        <el-table-column label="建议补库量" prop="suggested_qty" width="120" align="right" />
        <el-table-column label="目标库存" prop="target_qty" width="110" align="right" />
        <template #empty>暂无补库建议</template>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId === null ? '新增订货点规则' : '编辑订货点规则'"
      width="620px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="物料" prop="material_id">
          <RemoteSelect
            v-model="form.material_id"
            :loader="loadMaterialOptions"
            :disabled="editingId !== null"
            placeholder="请选择物料"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="仓库" prop="warehouse_id">
          <RemoteSelect
            v-model="form.warehouse_id"
            :loader="loadWarehouseOptions"
            :disabled="editingId !== null"
            placeholder="请选择仓库"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="订货点" prop="reorder_point">
          <el-input-number v-model="form.reorder_point" :min="0" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="建议订货量" prop="reorder_quantity">
          <el-input-number v-model="form.reorder_quantity" :min="0" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>