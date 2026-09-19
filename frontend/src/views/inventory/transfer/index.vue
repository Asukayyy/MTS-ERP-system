<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { cancelTransfer, confirmTransfer, createTransfer, listLocations, listTransfers, listWarehouses } from '@/api/inventory'
import { listMaterials, listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { RemoteOption, Transfer } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Transfer, { status: string; from_warehouse_id: number | undefined }>(
    (params) => listTransfers(params),
    { status: '', from_warehouse_id: undefined },
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

async function loadFromLocationOptions(keyword: string): Promise<RemoteOption[]> {
  if (!form.from_warehouse_id) return []
  const data = await listLocations({ warehouse_id: form.from_warehouse_id, keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.location_code} ${item.location_name}` }))
}

async function loadToLocationOptions(keyword: string): Promise<RemoteOption[]> {
  if (!form.to_warehouse_id) return []
  const data = await listLocations({ warehouse_id: form.to_warehouse_id, keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.location_code} ${item.location_name}` }))
}

interface TransferLineForm {
  material_id: number | undefined
  from_location_id: number | undefined
  to_location_id: number | undefined
  quantity: number
  remark: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  transfer_no: string
  from_warehouse_id: number | undefined
  to_warehouse_id: number | undefined
  transfer_date: string
  operator_id: number | undefined
  remark: string
  items: TransferLineForm[]
}>({
  transfer_no: '',
  from_warehouse_id: undefined,
  to_warehouse_id: undefined,
  transfer_date: '',
  operator_id: undefined,
  remark: '',
  items: [],
})

const rules: FormRules = {
  from_warehouse_id: [{ required: true, message: '请选择源仓库', trigger: 'change' }],
  to_warehouse_id: [{ required: true, message: '请选择目标仓库', trigger: 'change' }],
  transfer_date: [{ required: true, message: '请选择移库日期', trigger: 'change' }],
}

function addLine(): void {
  form.items.push({
    material_id: undefined,
    from_location_id: undefined,
    to_location_id: undefined,
    quantity: 1,
    remark: '',
  })
}

function removeLine(index: number): void {
  form.items.splice(index, 1)
}

function openCreate(): void {
  Object.assign(form, {
    transfer_no: '',
    from_warehouse_id: undefined,
    to_warehouse_id: undefined,
    transfer_date: '',
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
  if (form.from_warehouse_id === form.to_warehouse_id) {
    ElMessage.warning('源仓库与目标仓库不能相同')
    return
  }
  if (form.items.length === 0 || form.items.some((item) => !item.material_id)) {
    ElMessage.warning('请为每一行选择物料')
    return
  }
  submitting.value = true
  try {
    await createTransfer({
      transfer_no: form.transfer_no || null,
      from_warehouse_id: form.from_warehouse_id,
      to_warehouse_id: form.to_warehouse_id,
      transfer_date: form.transfer_date,
      operator_id: form.operator_id ?? null,
      remark: form.remark || null,
      items: form.items.map((item) => ({
        material_id: item.material_id,
        from_location_id: item.from_location_id ?? null,
        to_location_id: item.to_location_id ?? null,
        quantity: item.quantity,
        remark: item.remark || null,
      })),
    })
    ElMessage.success('移库单已新增')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doConfirm(row: Transfer): Promise<void> {
  try {
    await confirmTransfer(row.id)
    ElMessage.success('移库已确认，库存已转移')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCancel(row: Transfer): Promise<void> {
  try {
    await cancelTransfer(row.id)
    ElMessage.success('移库单已取消')
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
          <span class="page-title">移库</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增移库单</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="源仓库">
          <RemoteSelect v-model="query.from_warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 220px" />
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
              <el-table-column label="源库位ID" prop="from_location_id" width="110" align="right" />
              <el-table-column label="目标库位ID" prop="to_location_id" width="110" align="right" />
              <el-table-column label="移库数量" prop="quantity" width="110" align="right" />
              <el-table-column label="备注" prop="remark" min-width="140" />
              <template #empty>暂无移库明细</template>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="移库单号" prop="transfer_no" min-width="150" />
        <el-table-column label="源仓库ID" prop="from_warehouse_id" width="110" align="right" />
        <el-table-column label="目标仓库ID" prop="to_warehouse_id" width="110" align="right" />
        <el-table-column label="移库日期" prop="transfer_date" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="140" />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="doConfirm(row)">
              确认移库
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
        <template #empty>暂无移库单数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增移库单" width="960px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="移库单号">
              <el-input v-model="form.transfer_no" placeholder="留空自动生成" />
            </el-form-item>
          </el-col>
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
          <el-col :span="8">
            <el-form-item label="移库日期" prop="transfer_date">
              <el-date-picker v-model="form.transfer_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
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

        <el-divider content-position="left">移库明细</el-divider>
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
          <el-table-column label="源库位" min-width="180">
            <template #default="{ row }">
              <RemoteSelect v-model="row.from_location_id" :loader="loadFromLocationOptions" placeholder="可选" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="目标库位" min-width="180">
            <template #default="{ row }">
              <RemoteSelect v-model="row.to_location_id" :loader="loadToLocationOptions" placeholder="可选" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="移库数量" width="140">
            <template #default="{ row }">
              <el-input-number v-model="row.quantity" :min="0.0001" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeLine($index)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>请添加移库明细行</template>
        </el-table>
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