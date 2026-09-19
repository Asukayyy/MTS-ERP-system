<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createPersonnel,
  listOrganizationsFlat,
  listPersonnel,
  setPersonnelStatus,
  updatePersonnel,
} from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { Personnel, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Personnel, { keyword: string; org_id: number | undefined; status: string }>(
    (params) => listPersonnel(params),
    { keyword: '', org_id: undefined, status: '' },
  )

/** 组织选项 */
async function loadOrgOptions(keyword: string): Promise<RemoteOption[]> {
  const list = await listOrganizationsFlat()
  const text = keyword.trim()
  return list
    .filter((item) => !text || item.org_code.includes(text) || item.org_name.includes(text))
    .map((item) => ({ id: item.id, label: `${item.org_code} ${item.org_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  employee_no: string
  person_name: string
  org_id: number | undefined
  position: string
  phone: string
  email: string
  hire_date: string
  status: string
  remark: string
}>({
  employee_no: '',
  person_name: '',
  org_id: undefined,
  position: '',
  phone: '',
  email: '',
  hire_date: '',
  status: 'ACTIVE',
  remark: '',
})

const rules: FormRules = {
  employee_no: [{ required: true, message: '请输入员工工号', trigger: 'blur' }],
  person_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  org_id: [{ required: true, message: '请选择所属组织', trigger: 'change' }],
}

function resetForm(): void {
  Object.assign(form, {
    employee_no: '',
    person_name: '',
    org_id: undefined,
    position: '',
    phone: '',
    email: '',
    hire_date: '',
    status: 'ACTIVE',
    remark: '',
  })
}

function openCreate(): void {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: Personnel): void {
  editingId.value = row.id
  Object.assign(form, {
    employee_no: row.employee_no,
    person_name: row.person_name,
    org_id: row.org_id,
    position: row.position ?? '',
    phone: row.phone ?? '',
    email: row.email ?? '',
    hire_date: row.hire_date ?? '',
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
    const payload = {
      person_name: form.person_name,
      org_id: form.org_id,
      position: form.position || null,
      phone: form.phone || null,
      email: form.email || null,
      hire_date: form.hire_date || null,
      status: form.status,
      remark: form.remark || null,
    }
    if (editingId.value === null) {
      await createPersonnel({ ...payload, employee_no: form.employee_no })
      ElMessage.success('员工已新增')
    } else {
      await updatePersonnel(editingId.value, payload)
      ElMessage.success('员工已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function toggleStatus(row: Personnel): Promise<void> {
  const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'
  try {
    await setPersonnelStatus(row.id, next)
    ElMessage.success(next === 'ACTIVE' ? '员工已启用' : '员工已停用')
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
          <span class="page-title">员工</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增员工</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="关键字">
          <el-input v-model="query.keyword" placeholder="工号 / 姓名" clearable style="width: 180px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="所属组织">
          <RemoteSelect v-model="query.org_id" :loader="loadOrgOptions" placeholder="全部" style="width: 200px" />
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
        <el-table-column label="工号" prop="employee_no" min-width="120" />
        <el-table-column label="姓名" prop="person_name" min-width="120" />
        <el-table-column label="组织ID" prop="org_id" width="100" align="right" />
        <el-table-column label="岗位" prop="position" min-width="120" />
        <el-table-column label="电话" prop="phone" min-width="130" />
        <el-table-column label="邮箱" prop="email" min-width="180" show-overflow-tooltip />
        <el-table-column label="入职日期" prop="hire_date" width="120" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button
              link
              :type="row.status === 'ACTIVE' ? 'danger' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无员工数据</template>
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

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增员工' : '修改员工'" width="620px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="工号" prop="employee_no">
              <el-input v-model="form.employee_no" :disabled="editingId !== null" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓名" prop="person_name">
              <el-input v-model="form.person_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属组织" prop="org_id">
              <RemoteSelect v-model="form.org_id" :loader="loadOrgOptions" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="岗位"><el-input v-model="form.position" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="电话"><el-input v-model="form.phone" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="入职日期">
              <el-date-picker v-model="form.hire_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
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
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
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