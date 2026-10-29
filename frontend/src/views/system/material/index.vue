<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  autoClassifyAbc,
  createMaterial,
  listMaterials,
  setMaterialStatus,
  updateMaterial,
} from '@/api/system'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { Material } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    Material,
    {
      keyword: string
      material_type: string
      supply_type: string
      status: string
      abc_class: string
      sales_category: string
    }
  >((params) => listMaterials(params), {
    keyword: '',
    material_type: '',
    supply_type: '',
    status: '',
    abc_class: '',
    sales_category: '',
  })

const MATERIAL_TYPES = [
  { value: 'RAW', label: '原材料' },
  { value: 'PURCHASED', label: '采购件' },
  { value: 'SEMI', label: '半成品' },
  { value: 'FINISHED', label: '成品' },
]

/** 经典 ABC 分类：A 高价值、B 中等、C 低值 */
const ABC_CLASSES = [
  { value: 'A', label: 'A 类（高价值）' },
  { value: 'B', label: 'B 类（中等）' },
  { value: 'C', label: 'C 类（低值）' },
]

/** 销售类别：整机 / 可单独售卖备件 / 内部件 */
const SALES_CATEGORIES = [
  { value: 'MACHINE', label: '整机' },
  { value: 'SPARE', label: '可售备件' },
  { value: 'INTERNAL', label: '内部件' },
]

function salesCategoryLabel(value?: string | null): string {
  return SALES_CATEGORIES.find((item) => item.value === value)?.label ?? '内部件'
}

/** 自动 ABC 分类：按价值累计占比重算，覆盖现有分类 */
const classifying = ref(false)

async function runAbcClassify(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '按近 12 个月「采购到货金额 + 销售出库金额」从高到低累计，累计占比 < 70% 归 A 类、< 90% 归 B 类、其余归 C 类；窗口内无业务数据时自动回退库存金额。会覆盖现有分类，是否继续？',
      '自动 ABC 分类',
      { type: 'warning', confirmButtonText: '开始分类', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  classifying.value = true
  try {
    const result = await autoClassifyAbc()
    ElMessage.success(
      `分类完成：A ${result.a_count} / B ${result.b_count} / C ${result.c_count}（依据：${result.basis}，采购 ${result.purchase_value} / 销售 ${result.sales_value}）`,
    )
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    classifying.value = false
  }
}

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
  abc_class: '',
  sales_category: 'INTERNAL',
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
    abc_class: '',
    sales_category: 'INTERNAL',
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
    abc_class: row.abc_class ?? '',
    sales_category: row.sales_category ?? 'INTERNAL',
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
  const { abc_class, ...rest } = form
  const payload = { ...rest, abc_class: abc_class || null }
  try {
    if (editingId.value === null) {
      await createMaterial(payload)
      ElMessage.success('物料已新增')
    } else {
      const { material_code: _code, ...editable } = payload
      await updateMaterial(editingId.value, editable)
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
          <el-button :loading="classifying" @click="runAbcClassify">自动 ABC 分类</el-button>
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
        <el-form-item label="销售类别">
          <el-select v-model="query.sales_category" clearable placeholder="全部" style="width: 130px">
            <el-option v-for="item in SALES_CATEGORIES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="ABC">
          <el-select v-model="query.abc_class" clearable placeholder="全部" style="width: 110px">
            <el-option v-for="item in ABC_CLASSES" :key="item.value" :label="item.label" :value="item.value" />
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
        <el-table-column label="销售类别" width="100">
          <template #default="{ row }">{{ salesCategoryLabel(row.sales_category) }}</template>
        </el-table-column>
        <el-table-column label="ABC" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.abc_class" :type="row.abc_class === 'A' ? 'danger' : row.abc_class === 'B' ? 'warning' : 'info'" size="small">
              {{ row.abc_class }}
            </el-tag>
            <span v-else>—</span>
          </template>
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
            <el-form-item label="销售类别">
              <el-select v-model="form.sales_category" style="width: 100%">
                <el-option v-for="item in SALES_CATEGORIES" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="ABC 分类">
              <el-select v-model="form.abc_class" clearable placeholder="未分类" style="width: 100%">
                <el-option v-for="item in ABC_CLASSES" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
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