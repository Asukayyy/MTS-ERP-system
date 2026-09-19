<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  addRoutingOperation,
  createRouting,
  listMaterials,
  listRoutings,
  setRoutingStatus,
} from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { RemoteOption, Routing } from '@/types/erp'

/** 工艺路线：路线头 + 工序明细 */

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Routing, { material_id: number | undefined; status: string }>(
    (params) => listRoutings(params),
    { material_id: undefined, status: '' },
  )

async function materialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, page: 1, page_size: 20 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

interface OperationForm {
  sequence_no: number
  operation_code: string
  operation_name: string
  work_center: string
  setup_time: number
  run_time: number
  remark: string
}

function emptyOperation(): OperationForm {
  return {
    sequence_no: 1,
    operation_code: '',
    operation_name: '',
    work_center: '',
    setup_time: 0,
    run_time: 0,
    remark: '',
  }
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({
  material_id: undefined as number | undefined,
  routing_version: 'V1.0',
  remark: '',
  operations: [emptyOperation()] as OperationForm[],
})

const rules: FormRules = {
  material_id: [{ required: true, message: '请选择自制件物料', trigger: 'change' }],
  routing_version: [{ required: true, message: '请输入工艺版本', trigger: 'blur' }],
}

function openCreate(): void {
  Object.assign(form, { material_id: undefined, routing_version: 'V1.0', remark: '', operations: [emptyOperation()] })
  dialogVisible.value = true
}

function addOperationRow(): void {
  const next = emptyOperation()
  next.sequence_no = form.operations.length + 1
  form.operations.push(next)
}

function removeOperationRow(index: number): void {
  form.operations.splice(index, 1)
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await createRouting({ ...form })
    ElMessage.success('工艺路线已新增')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function toggleStatus(row: Routing): Promise<void> {
  const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'
  try {
    await setRoutingStatus(row.id, next)
    ElMessage.success('工艺路线状态已更新')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

// ---------------- 追加工序 ----------------
const opDialogVisible = ref(false)
const opSubmitting = ref(false)
const opTargetId = ref<number | null>(null)
const opFormRef = ref<FormInstance>()
const opForm = reactive(emptyOperation())
const opRules: FormRules = {
  sequence_no: [{ required: true, message: '请输入工序顺序号', trigger: 'blur' }],
  operation_code: [{ required: true, message: '请输入工序编码', trigger: 'blur' }],
  operation_name: [{ required: true, message: '请输入工序名称', trigger: 'blur' }],
}

function openAddOperation(row: Routing): void {
  opTargetId.value = row.id
  Object.assign(opForm, emptyOperation())
  opForm.sequence_no = row.operations.length + 1
  opDialogVisible.value = true
}

async function submitOperation(): Promise<void> {
  const valid = await opFormRef.value?.validate().catch(() => false)
  if (!valid || opTargetId.value === null) return
  opSubmitting.value = true
  try {
    await addRoutingOperation(opTargetId.value, { ...opForm })
    ElMessage.success('工序已追加')
    opDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    opSubmitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">工艺路线</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增工艺路线</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="物料">
          <RemoteSelect v-model="query.material_id" :loader="materialOptions" placeholder="全部物料" style="width: 220px" />
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

      <el-table v-loading="loading" :data="rows" border size="small" row-key="id">
        <el-table-column type="expand">
          <template #default="{ row }">
            <el-table :data="row.operations" size="small" border class="nested-table">
              <el-table-column label="顺序" prop="sequence_no" width="70" />
              <el-table-column label="工序编码" prop="operation_code" width="120" />
              <el-table-column label="工序名称" prop="operation_name" min-width="140" />
              <el-table-column label="工作中心" prop="work_center" width="120" />
              <el-table-column label="准备工时(分)" prop="setup_time" width="110" align="right" />
              <el-table-column label="加工工时(分)" prop="run_time" width="110" align="right" />
              <template #empty>暂无工序</template>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="工艺编码" prop="routing_code" min-width="130" />
        <el-table-column label="物料ID" prop="material_id" width="100" />
        <el-table-column label="版本" prop="routing_version" width="90" />
        <el-table-column label="工序数" width="90" align="right">
          <template #default="{ row }">{{ row.operations.length }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openAddOperation(row)">追加工序</el-button>
            <el-button link :type="row.status === 'ACTIVE' ? 'danger' : 'success'" @click="toggleStatus(row)">
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无工艺路线</template>
      </el-table>

      <div class="pager">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="changePage"
          @size-change="changeSize"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" title="新增工艺路线" width="760px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="自制件物料" prop="material_id">
              <RemoteSelect v-model="form.material_id" :loader="materialOptions" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="工艺版本" prop="routing_version"><el-input v-model="form.routing_version" /></el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">工序明细</el-divider>
        <el-table :data="form.operations" size="small" border>
          <el-table-column label="顺序" width="90">
            <template #default="{ row }"><el-input-number v-model="row.sequence_no" :min="1" size="small" /></template>
          </el-table-column>
          <el-table-column label="工序编码" width="130">
            <template #default="{ row }"><el-input v-model="row.operation_code" size="small" /></template>
          </el-table-column>
          <el-table-column label="工序名称" min-width="140">
            <template #default="{ row }"><el-input v-model="row.operation_name" size="small" /></template>
          </el-table-column>
          <el-table-column label="工作中心" width="120">
            <template #default="{ row }"><el-input v-model="row.work_center" size="small" /></template>
          </el-table-column>
          <el-table-column label="准备工时" width="110">
            <template #default="{ row }"><el-input-number v-model="row.setup_time" :min="0" size="small" /></template>
          </el-table-column>
          <el-table-column label="加工工时" width="110">
            <template #default="{ row }"><el-input-number v-model="row.run_time" :min="0" size="small" /></template>
          </el-table-column>
          <el-table-column label="操作" width="70">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeOperationRow($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button class="add-op" @click="addOperationRow">添加工序</el-button>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="opDialogVisible" title="追加工序" width="560px">
      <el-form ref="opFormRef" :model="opForm" :rules="opRules" label-width="100px">
        <el-form-item label="顺序" prop="sequence_no"><el-input-number v-model="opForm.sequence_no" :min="1" /></el-form-item>
        <el-form-item label="工序编码" prop="operation_code"><el-input v-model="opForm.operation_code" /></el-form-item>
        <el-form-item label="工序名称" prop="operation_name"><el-input v-model="opForm.operation_name" /></el-form-item>
        <el-form-item label="工作中心"><el-input v-model="opForm.work_center" /></el-form-item>
        <el-form-item label="准备工时"><el-input-number v-model="opForm.setup_time" :min="0" /></el-form-item>
        <el-form-item label="加工工时"><el-input-number v-model="opForm.run_time" :min="0" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="opForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="opDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="opSubmitting" @click="submitOperation">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.nested-table {
  margin: 8px 16px;
}

.add-op {
  margin-top: 8px;
}
</style>