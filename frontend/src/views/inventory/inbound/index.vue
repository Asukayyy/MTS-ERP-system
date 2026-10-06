<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { listWarehouses, stockIncrease } from '@/api/inventory'
import { listMaterials, listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import type { RemoteOption } from '@/types/erp'

/** 手工入库：直接更新库存结存（不再维护独立流水表） */
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  material_id: number | undefined
  warehouse_id: number | undefined
  quantity: number
  unit_cost: number
  biz_date: string
  operator_id: number | undefined
  remark: string
}>({
  material_id: undefined,
  warehouse_id: undefined,
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

async function loadOperatorOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const result = await stockIncrease({
      material_id: form.material_id,
      warehouse_id: form.warehouse_id,
      quantity: form.quantity,
      unit_cost: form.unit_cost,
      biz_date: form.biz_date || null,
      operator_id: form.operator_id ?? null,
      remark: form.remark || null,
    })
    ElMessage.success(`入库成功，结存数量 ${result.quantity_after}`)
    form.quantity = 1
    form.unit_cost = 0
    form.remark = ''
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}
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
  </div>
</template>
