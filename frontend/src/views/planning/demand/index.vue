<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createDemand,
  importDemandsFromSales,
  listDemands,
  setDemandStatus,
} from '@/api/planning'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { Demand, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Demand, { source_type: string; status: string }>(
    (params) => listDemands(params),
    { source_type: '', status: '' },
  )

/** 物料选项 */
async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  source_type: string
  material_id: number | undefined
  quantity: number
  due_date: string
  source_no: string
  remark: string
}>({
  source_type: 'SALES',
  material_id: undefined,
  quantity: 1,
  due_date: '',
  source_no: '',
  remark: '',
})

const rules: FormRules = {
  source_type: [{ required: true, message: '请选择需求来源', trigger: 'change' }],
  material_id: [{ required: true, message: '请选择物料', trigger: 'change' }],
  quantity: [{ required: true, message: '请输入需求数量', trigger: 'blur' }],
  due_date: [{ required: true, message: '请选择需求日期', trigger: 'change' }],
}

function openCreate(): void {
  Object.assign(form, {
    source_type: 'SALES',
    material_id: undefined,
    quantity: 1,
    due_date: '',
    source_no: '',
    remark: '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await createDemand({
      source_type: form.source_type,
      material_id: form.material_id,
      quantity: form.quantity,
      due_date: form.due_date,
      source_no: form.source_no || null,
      remark: form.remark || null,
    })
    ElMessage.success('计划需求已新增')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function changeStatus(row: Demand, status: string): Promise<void> {
  try {
    await setDemandStatus(row.id, status)
    ElMessage.success('需求状态已更新')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

const importing = ref(false)

/** 从已确认销售订单导入计划需求 */
async function importFromSales(): Promise<void> {
  importing.value = true
  try {
    const result = await importDemandsFromSales()
    ElMessage.success(`导入完成：新建 ${result.created_count} 条，跳过 ${result.skipped_count} 条`)
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    importing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">需求管理</span>
          <span class="table-toolbar__spacer" />
          <el-button :loading="importing" @click="importFromSales">从销售订单导入</el-button>
          <el-button type="primary" @click="openCreate">新增需求</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="需求来源">
          <el-select v-model="query.source_type" clearable placeholder="全部" style="width: 140px">
            <el-option label="销售" value="SALES" />
            <el-option label="补库" value="STOCKFILL" />
            <el-option label="MPS" value="MPS" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已确认" value="CONFIRMED" />
            <el-option label="已下达" value="RELEASED" />
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
        <el-table-column label="需求单号" prop="demand_no" min-width="150" />
        <el-table-column label="来源" width="100">
          <template #default="{ row }"><StatusTag :status="row.source_type" /></template>
        </el-table-column>
        <el-table-column label="来源单号" prop="source_no" min-width="150" />
        <el-table-column label="物料ID" prop="material_id" width="100" align="right" />
        <el-table-column label="需求数量" prop="quantity" width="110" align="right" />
        <el-table-column label="需求日期" prop="due_date" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="changeStatus(row, 'CONFIRMED')">
              确认
            </el-button>
            <el-button
              v-if="row.status === 'DRAFT' || row.status === 'CONFIRMED'"
              link
              type="primary"
              @click="changeStatus(row, 'RELEASED')"
            >
              下达
            </el-button>
            <el-button
              v-if="row.status === 'CONFIRMED' || row.status === 'RELEASED'"
              link
              type="success"
              @click="changeStatus(row, 'COMPLETED')"
            >
              完成
            </el-button>
            <el-button
              v-if="row.status === 'DRAFT' || row.status === 'CONFIRMED' || row.status === 'RELEASED'"
              link
              type="danger"
              @click="changeStatus(row, 'CANCELLED')"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无计划需求数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增计划需求" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="需求来源" prop="source_type">
          <el-select v-model="form.source_type" style="width: 100%">
            <el-option label="销售 SALES" value="SALES" />
            <el-option label="补库 STOCKFILL" value="STOCKFILL" />
            <el-option label="MPS" value="MPS" />
          </el-select>
        </el-form-item>
        <el-form-item label="物料" prop="material_id">
          <RemoteSelect v-model="form.material_id" :loader="loadMaterialOptions" style="width: 100%" />
        </el-form-item>
        <el-form-item label="需求数量" prop="quantity">
          <el-input-number v-model="form.quantity" :min="0.0001" style="width: 100%" />
        </el-form-item>
        <el-form-item label="需求日期" prop="due_date">
          <el-date-picker v-model="form.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="来源单号"><el-input v-model="form.source_no" /></el-form-item>
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