<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { cancelStocktake, confirmStocktake, createStocktake, listLocations, listStocktakes, listWarehouses } from '@/api/inventory'
import { listMaterials, listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { RemoteOption, Stocktake } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Stocktake, { status: string; warehouse_id: number | undefined }>(
    (params) => listStocktakes(params),
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

async function loadLocationOptions(keyword: string): Promise<RemoteOption[]> {
  if (!form.warehouse_id) return []
  const data = await listLocations({ warehouse_id: form.warehouse_id, keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.location_code} ${item.location_name}` }))
}

interface StocktakeLineForm {
  material_id: number | undefined
  location_id: number | undefined
  book_qty: number | undefined
  actual_qty: number
  remark: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  stocktake_no: string
  warehouse_id: number | undefined
  stocktake_date: string
  operator_id: number | undefined
  remark: string
  items: StocktakeLineForm[]
}>({
  stocktake_no: '',
  warehouse_id: undefined,
  stocktake_date: '',
  operator_id: undefined,
  remark: '',
  items: [],
})

const rules: FormRules = {
  warehouse_id: [{ required: true, message: '请选择盘点仓库', trigger: 'change' }],
  stocktake_date: [{ required: true, message: '请选择盘点日期', trigger: 'change' }],
}

function addLine(): void {
  form.items.push({ material_id: undefined, location_id: undefined, book_qty: undefined, actual_qty: 0, remark: '' })
}

function removeLine(index: number): void {
  form.items.splice(index, 1)
}

function openCreate(): void {
  Object.assign(form, {
    stocktake_no: '',
    warehouse_id: undefined,
    stocktake_date: '',
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
  submitting.value = true
  try {
    await createStocktake({
      stocktake_no: form.stocktake_no || null,
      warehouse_id: form.warehouse_id,
      stocktake_date: form.stocktake_date,
      operator_id: form.operator_id ?? null,
      remark: form.remark || null,
      items: form.items.map((item) => ({
        material_id: item.material_id,
        location_id: item.location_id ?? null,
        book_qty: item.book_qty ?? null,
        actual_qty: item.actual_qty,
        remark: item.remark || null,
      })),
    })
    ElMessage.success('盘点单已新增')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doConfirm(row: Stocktake): Promise<void> {
  try {
    await confirmStocktake(row.id)
    ElMessage.success('盘点已确认，差异已生成调整流水')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCancel(row: Stocktake): Promise<void> {
  try {
    await cancelStocktake(row.id)
    ElMessage.success('盘点单已取消')
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
          <span class="page-title">盘点</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增盘点单</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="盘点仓库">
          <RemoteSelect v-model="query.warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
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
              <el-table-column label="物料ID" prop="material_id" width="90" align="right" />
              <el-table-column label="库位ID" prop="location_id" width="90" align="right" />
              <el-table-column label="账面数量" prop="book_qty" width="110" align="right" />
              <el-table-column label="实盘数量" prop="actual_qty" width="110" align="right" />
              <el-table-column label="差异" prop="difference" width="110" align="right" />
              <el-table-column label="备注" prop="remark" min-width="140" />
              <template #empty>暂无盘点明细</template>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="盘点单号" prop="stocktake_no" min-width="150" />
        <el-table-column label="盘点仓库ID" prop="warehouse_id" width="110" align="right" />
        <el-table-column label="盘点日期" prop="stocktake_date" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="140" />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="doConfirm(row)">
              确认盘点
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
        <template #empty>暂无盘点单数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增盘点单" width="940px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="盘点单号">
              <el-input v-model="form.stocktake_no" placeholder="留空自动生成" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="盘点仓库" prop="warehouse_id">
              <RemoteSelect v-model="form.warehouse_id" :loader="loadWarehouseOptions" placeholder="请选择仓库" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="盘点日期" prop="stocktake_date">
              <el-date-picker v-model="form.stocktake_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="操作人">
              <RemoteSelect v-model="form.operator_id" :loader="loadOperatorOptions" placeholder="可选" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="16">
            <el-form-item label="备注">
              <el-input v-model="form.remark" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">盘点明细</el-divider>
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
          <el-table-column label="库位" min-width="170">
            <template #default="{ row }">
              <RemoteSelect v-model="row.location_id" :loader="loadLocationOptions" placeholder="可选" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="账面数量" width="140">
            <template #default="{ row }">
              <el-input-number v-model="row.book_qty" :min="0" :controls="false" placeholder="留空自动取" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="实盘数量" width="140">
            <template #default="{ row }">
              <el-input-number v-model="row.actual_qty" :min="0" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeLine($index)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>请添加盘点明细行</template>
        </el-table>
        <div class="form-tip">账面数量留空时，确认盘点由后端按当前结存自动带出。</div>
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