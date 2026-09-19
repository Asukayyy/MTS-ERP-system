<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { createMaterial, listMaterials, setMaterialStatus, updateMaterial } from '@/api/system'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { Material } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    Material,
    { keyword: string; material_type: string; supply_type: string; status: string }
  >((params) => listMaterials(params), {
    keyword: '',
    material_type: '',
    supply_type: '',
    status: '',
  })

const MATERIAL_TYPES = [
  { value: 'RAW', label: '原材料' },
  { value: 'PURCHASED', label: '采购件' },
  { value: 'SEMI', label: '半成品' },
  { value: 'FINISHED', label: '成品' },
]

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  material_code: '',
  material_name: '',
  material_type: 'RAW',
  supply_type: 'BUY',
  unit_code: 'PCS',
  specification: '',
  material_group: '',
  lead_time_days: 0,
  safety_stock: 0,
  standard_cost: 0,
  status: 'ACTIVE',
  remark: '',
})

const rules: FormRules = {
  material_code: [{ required: true, message: '请输入物料编码', trigger: 'blur' }],
  material_name: [{ required: true, message: '请输入物料名称', trigger: 'blur' }],
  material_type: [{ required: true, message: '请选择物料类型', trigger: 'change' }],
  supply_type: [{ required: true, message: '请选择供应类型', trigger: 'change' }],
  unit_code: [{ required: true, message: '请输入计量单位', trigger: 'blur' }],
}

function resetForm(): void {
  Object.assign(form, {
    material_code: '',
    material_name: '',
    material_type: 'RAW',
    supply_type: 'BUY',
    unit_code: 'PCS',
    specification: '',
    material_group: '',
    lead_time_days: 0,
    safety_stock: 0,
    standard_cost: 0,
    status: 'ACTIVE',
    remark: '',
  })
}

function openCreate(): void {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: Material): void {
  editingId.value = row.id
  Object.assign(form, {
    material_code: row.material_code,
    material_name: row.material_name,
    material_type: row.material_type,
    supply_type: row.supply_type,
    unit_code: row.unit_code,
    specification: row.specification ?? '',
    material_group: row.material_group ?? '',
    lead_time_days: row.lead_time_days,
    safety_stock: Number(row.safety_stock),
    standard_cost: Number(row.standard_cost),
    status: row.status,
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
      await createMaterial({ ...form })
      ElMessage.success('物料已新增')
    } else {
      const { material_code: _code, ...payload } = form
      await updateMaterial(editingId.value, payload)
      ElMessage.success('物料已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function toggleStatus(row: Material): Promise<void> {
  const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'
  try {
    await setMaterialStatus(row.id, next)
    ElMessage.success(next === 'ACTIVE' ? '物料已启用' : '物料已停用')
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
          <span class="page-title">物料管理</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增物料</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="关键字">
          <el-input v-model="query.keyword" placeholder="编码 / 名称" clearable style="width: 180px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="物料类型">
          <el-select v-model="query.material_type" clearable placeholder="全部" style="width: 140px">
            <el-option v-for="item in MATERIAL_TYPES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="供应类型">
          <el-select v-model="query.supply_type" clearable placeholder="全部" style="width: 120px">
            <el-option label="自制" value="MAKE" />
            <el-option label="采购" value="BUY" />
          </el-select>
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
        <el-table-column label="物料名称" prop="material_name" min-width="150" />
        <el-table-column label="类型" width="100">
          <template #default="{ row }"><StatusTag :status="row.material_type" /></template>
        </el-table-column>
        <el-table-column label="供应" width="90">
          <template #default="{ row }"><StatusTag :status="row.supply_type" /></template>
        </el-table-column>
        <el-table-column label="单位" prop="unit_code" width="80" />
        <el-table-column label="提前期(天)" prop="lead_time_days" width="100" align="right" />
        <el-table-column label="安全库存" prop="safety_stock" width="100" align="right" />
        <el-table-column label="标准成本" prop="standard_cost" width="100" align="right" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link :type="row.status === 'ACTIVE' ? 'danger' : 'success'" @click="toggleStatus(row)">
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无物料数据</template>
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

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增物料' : '修改物料'" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="物料编码" prop="material_code">
              <el-input v-model="form.material_code" :disabled="editingId !== null" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="物料名称" prop="material_name">
              <el-input v-model="form.material_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="物料类型" prop="material_type">
              <el-select v-model="form.material_type" style="width: 100%">
                <el-option v-for="item in MATERIAL_TYPES" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="供应类型" prop="supply_type">
              <el-select v-model="form.supply_type" style="width: 100%">
                <el-option label="自制 MAKE" value="MAKE" />
                <el-option label="采购 BUY" value="BUY" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="计量单位" prop="unit_code"><el-input v-model="form.unit_code" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="规格型号"><el-input v-model="form.specification" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="物料分组"><el-input v-model="form.material_group" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="提前期(天)">
              <el-input-number v-model="form.lead_time_days" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="安全库存">
              <el-input-number v-model="form.safety_stock" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标准成本">
              <el-input-number v-model="form.standard_cost" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="启用" value="ACTIVE" />
                <el-option label="停用" value="INACTIVE" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>