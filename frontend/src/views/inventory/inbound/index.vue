<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { listLocations, listTransactions, listWarehouses, stockIncrease } from '@/api/inventory'
import { listMaterials, listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { RemoteOption, Transaction } from '@/types/erp'

/** 手工入库：调用库存入库契约，写入库存流水 */
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  material_id: number | undefined
  warehouse_id: number | undefined
  location_id: number | undefined
  quantity: number
  unit_cost: number
  biz_date: string
  operator_id: number | undefined
  remark: string
}>({
  material_id: undefined,
  warehouse_id: undefined,
  location_id: undefined,
  quantity: 1,
  unit_cost: 0,
  biz_date: '',
  operator_id: undefined,
  remark: '',
})

const rules: FormRules = {
  material_id: [{ required: true, message: '请选择物料', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择仓库', trigger: 'change' }],
  quantity: [{ required: true, message: '请输入入库数量', trigger: 'blur' }],
}

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

async function loadLocationOptions(keyword: string): Promise<RemoteOption[]> {
  if (!form.warehouse_id) return []
  const data = await listLocations({ warehouse_id: form.warehouse_id, keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.location_code} ${item.location_name}` }))
}

async function loadOperatorOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Transaction, { keyword: string; warehouse_id: number | undefined; date_from: string; date_to: string }>(
    (params) => listTransactions({ ...params, transaction_type: 'IN' }),
    { keyword: '', warehouse_id: undefined, date_from: '', date_to: '' },
  )

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const result = await stockIncrease({
      material_id: form.material_id,
      warehouse_id: form.warehouse_id,
      location_id: form.location_id ?? null,
      quantity: form.quantity,
      unit_cost: form.unit_cost,
      biz_date: form.biz_date || null,
      operator_id: form.operator_id ?? null,
      remark: form.remark || null,
    })
    ElMessage.success(`入库成功，流水号 ${result.transaction_no}，结存 ${result.quantity_after}`)
    form.quantity = 1
    form.unit_cost = 0
    form.remark = ''
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">手工入库</span>
        </div>
      </template>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="物料" prop="material_id">
              <RemoteSelect v-model="form.material_id" :loader="loadMaterialOptions" placeholder="请选择物料" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="仓库" prop="warehouse_id">
              <RemoteSelect v-model="form.warehouse_id" :loader="loadWarehouseOptions" placeholder="请选择仓库" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="库位">
              <RemoteSelect
                v-model="form.location_id"
                :loader="loadLocationOptions"
                placeholder="可选（须先选仓库）"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="入库数量" prop="quantity">
              <el-input-number v-model="form.quantity" :min="0.0001" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="单位成本">
              <el-input-number v-model="form.unit_cost" :min="0" :precision="2" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="业务日期">
              <el-date-picker v-model="form.biz_date" type="date" value-format="YYYY-MM-DD" placeholder="缺省为当天" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="操作人">
              <RemoteSelect v-model="form.operator_id" :loader="loadOperatorOptions" placeholder="可选" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="16">
            <el-form-item label="备注">
              <el-input v-model="form.remark" placeholder="入库原因 / 说明" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item>
              <el-button type="primary" :loading="submitting" @click="submit">提交入库</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 12px">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">入库流水</span>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="物料">
          <el-input v-model="query.keyword" placeholder="物料编码 / 名称" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item label="仓库">
          <RemoteSelect v-model="query.warehouse_id" :loader="loadWarehouseOptions" placeholder="全部" style="width: 200px" />
        </el-form-item>
        <el-form-item label="业务日期">
          <el-date-picker v-model="query.date_from" type="date" value-format="YYYY-MM-DD" placeholder="开始" style="width: 150px" />
          <span style="margin: 0 6px">至</span>
          <el-date-picker v-model="query.date_to" type="date" value-format="YYYY-MM-DD" placeholder="结束" style="width: 150px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="流水号" prop="transaction_no" min-width="150" />
        <el-table-column label="类型" width="100">
          <template #default="{ row }"><StatusTag :status="row.transaction_type" /></template>
        </el-table-column>
        <el-table-column label="物料编码" prop="material_code" min-width="120" />
        <el-table-column label="物料名称" prop="material_name" min-width="150" />
        <el-table-column label="仓库ID" prop="warehouse_id" width="90" align="right" />
        <el-table-column label="入库数量" prop="quantity_change" width="110" align="right" />
        <el-table-column label="结存数量" prop="quantity_after" width="110" align="right" />
        <el-table-column label="单位成本" prop="unit_cost" width="110" align="right" />
        <el-table-column label="业务日期" prop="biz_date" width="110" />
        <el-table-column label="来源单据" prop="source_no" min-width="140" />
        <el-table-column label="备注" prop="remark" min-width="140" />
        <template #empty>暂无入库流水</template>
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