<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createSupplierMaterial,
  deleteSupplierMaterial,
  listPurchaseMaterials,
  listSupplierMaterials,
  listSuppliers,
  updateSupplierMaterial,
} from '@/api/procurement'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { RemoteOption, SupplierMaterial } from '@/types/erp'

/** 供应商-物料供货关系：维护供货价、提前期、最小起订量，供采购计划取价 */
const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<SupplierMaterial, { supplier_id: number | undefined; material_id: number | undefined }>(
    (params) => listSupplierMaterials(params),
    { supplier_id: undefined, material_id: undefined },
  )

async function loadSupplierOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listSuppliers({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.supplier_code} ${item.supplier_name}` }))
}

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPurchaseMaterials(keyword)
  return data.slice(0, 50).map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const form = reactive<{
  supplier_id: number | undefined
  material_id: number | undefined
  is_primary: boolean
  supply_price: number
  lead_time_days: number
  min_order_qty: number
}>({
  supplier_id: undefined,
  material_id: undefined,
  is_primary: false,
  supply_price: 0,
  lead_time_days: 0,
  min_order_qty: 0,
})

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    supplier_id: undefined,
    material_id: undefined,
    is_primary: false,
    supply_price: 0,
    lead_time_days: 0,
    min_order_qty: 0,
  })
  dialogVisible.value = true
}

function openEdit(row: SupplierMaterial): void {
  editingId.value = row.id
  Object.assign(form, {
    supplier_id: row.supplier_id,
    material_id: row.material_id,
    is_primary: row.is_primary,
    supply_price: toNumber(row.supply_price),
    lead_time_days: row.lead_time_days,
    min_order_qty: toNumber(row.min_order_qty),
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  if (editingId.value === null) {
    if (!form.supplier_id || !form.material_id) {
      ElMessage.warning('请选择供应商与物料')
      return
    }
  }
  submitting.value = true
  try {
    if (editingId.value === null) {
      await createSupplierMaterial({
        supplier_id: form.supplier_id,
        material_id: form.material_id,
        is_primary: form.is_primary,
        supply_price: form.supply_price,
        lead_time_days: form.lead_time_days,
        min_order_qty: form.min_order_qty,
      })
      ElMessage.success('供货关系已新增')
    } else {
      await updateSupplierMaterial(editingId.value, {
        is_primary: form.is_primary,
        supply_price: form.supply_price,
        lead_time_days: form.lead_time_days,
        min_order_qty: form.min_order_qty,
      })
      ElMessage.success('供货关系已更新')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function remove(row: SupplierMaterial): Promise<void> {
  const confirmed = await ElMessageBox.confirm(
    `确认删除「${row.material_code ?? row.material_id}」的供货关系吗？`,
    '删除确认',
    { type: 'warning' },
  ).catch(() => false)
  if (!confirmed) return
  try {
    await deleteSupplierMaterial(row.id)
    ElMessage.success('供货关系已删除')
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
          <span class="page-title">供应商-物料关系</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增供货关系</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="供应商">
          <RemoteSelect v-model="query.supplier_id" :loader="loadSupplierOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item label="物料">
          <RemoteSelect v-model="query.material_id" :loader="loadMaterialOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="供应商" min-width="200">
          <template #default="{ row }">{{ row.supplier_name || `ID ${row.supplier_id}` }}</template>
        </el-table-column>
        <el-table-column label="物料" min-width="220">
          <template #default="{ row }">
            {{ row.material_code ? `${row.material_code} ${row.material_name ?? ''}` : `ID ${row.material_id}` }}
          </template>
        </el-table-column>
        <el-table-column label="主供应商" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_primary" type="success" size="small">是</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="供货单价" prop="supply_price" width="110" align="right" />
        <el-table-column label="提前期(天)" prop="lead_time_days" width="110" align="right" />
        <el-table-column label="最小起订量" prop="min_order_qty" width="110" align="right" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无供货关系数据</template>
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

    <el-dialog
      v-model="dialogVisible"
      :title="editingId === null ? '新增供货关系' : '编辑供货关系'"
      width="640px"
    >
      <el-form label-width="120px">
        <el-form-item label="供应商" required>
          <RemoteSelect
            v-model="form.supplier_id"
            :loader="loadSupplierOptions"
            placeholder="请选择供应商"
            :disabled="editingId !== null"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="物料" required>
          <RemoteSelect
            v-model="form.material_id"
            :loader="loadMaterialOptions"
            placeholder="请选择可采购物料"
            :disabled="editingId !== null"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="主供应商">
          <el-switch v-model="form.is_primary" />
        </el-form-item>
        <el-form-item label="供货单价">
          <el-input-number v-model="form.supply_price" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="供货提前期(天)">
          <el-input-number v-model="form.lead_time_days" :min="0" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="最小起订量">
          <el-input-number v-model="form.min_order_qty" :min="0" :controls="false" style="width: 100%" />
        </el-form-item>
        <div class="form-tip">同一供应商与物料只能存在一条供货关系；采购订单取价时优先使用主供应商价格。</div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>