<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createOrganization,
  getOrganizationTree,
  listOrganizationsFlat,
  listPersonnel,
  setOrganizationStatus,
  updateOrganization,
} from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { Organization, RemoteOption } from '@/types/erp'

/** 组织类型（对应后端 org_type 取值） */
const ORG_TYPES = [
  { value: 'COMPANY', label: '公司' },
  { value: 'FACTORY', label: '工厂' },
  { value: 'DEPARTMENT', label: '部门' },
  { value: 'WORKSHOP', label: '车间' },
  { value: 'WAREHOUSE', label: '仓库' },
]

const loading = ref(false)
const rows = ref<Organization[]>([])

/** 组织选项：用于上级组织下拉 */
async function loadOrgOptions(keyword: string): Promise<RemoteOption[]> {
  const list = await listOrganizationsFlat()
  const text = keyword.trim()
  return list
    .filter((item) => !text || item.org_code.includes(text) || item.org_name.includes(text))
    .map((item) => ({ id: item.id, label: `${item.org_code} ${item.org_name}` }))
}

/** 负责人选项：来源 system 员工 */
async function loadPersonnelOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await getOrganizationTree()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  org_code: string
  org_name: string
  parent_id: number | undefined
  org_type: string
  manager_id: number | undefined
  status: string
  remark: string
}>({
  org_code: '',
  org_name: '',
  parent_id: undefined,
  org_type: 'DEPARTMENT',
  manager_id: undefined,
  status: 'ACTIVE',
  remark: '',
})

const rules: FormRules = {
  org_code: [{ required: true, message: '请输入组织编码', trigger: 'blur' }],
  org_name: [{ required: true, message: '请输入组织名称', trigger: 'blur' }],
  org_type: [{ required: true, message: '请选择组织类型', trigger: 'change' }],
}

function resetForm(): void {
  Object.assign(form, {
    org_code: '',
    org_name: '',
    parent_id: undefined,
    org_type: 'DEPARTMENT',
    manager_id: undefined,
    status: 'ACTIVE',
    remark: '',
  })
}

function openCreate(): void {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: Organization): void {
  editingId.value = row.id
  Object.assign(form, {
    org_code: row.org_code,
    org_name: row.org_name,
    parent_id: row.parent_id ?? undefined,
    org_type: row.org_type,
    manager_id: row.manager_id ?? undefined,
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
      org_name: form.org_name,
      parent_id: form.parent_id ?? null,
      org_type: form.org_type,
      manager_id: form.manager_id ?? null,
      status: form.status,
      remark: form.remark || null,
    }
    if (editingId.value === null) {
      await createOrganization({ ...payload, org_code: form.org_code })
      ElMessage.success('组织已新增')
    } else {
      await updateOrganization(editingId.value, payload)
      ElMessage.success('组织已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function toggleStatus(row: Organization): Promise<void> {
  const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'
  try {
    await setOrganizationStatus(row.id, next)
    ElMessage.success(next === 'ACTIVE' ? '组织已启用' : '组织已停用')
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
          <span class="page-title">组织机构</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="load">刷新</el-button>
          <el-button type="primary" @click="openCreate">新增组织</el-button>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="rows"
        row-key="id"
        :tree-props="{ children: 'children' }"
        default-expand-all
        border
        size="small"
      >
        <el-table-column label="组织编码" prop="org_code" min-width="150" />
        <el-table-column label="组织名称" prop="org_name" min-width="180" />
        <el-table-column label="组织类型" width="110">
          <template #default="{ row }">
            {{ ORG_TYPES.find((item) => item.value === row.org_type)?.label ?? row.org_type }}
          </template>
        </el-table-column>
        <el-table-column label="负责人ID" prop="manager_id" width="100" align="right" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="140" show-overflow-tooltip />
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
        <template #empty>暂无组织数据</template>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增组织' : '修改组织'" width="620px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="组织编码" prop="org_code">
              <el-input v-model="form.org_code" :disabled="editingId !== null" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="组织名称" prop="org_name">
              <el-input v-model="form.org_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="上级组织">
              <RemoteSelect v-model="form.parent_id" :loader="loadOrgOptions" placeholder="顶级组织" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="组织类型" prop="org_type">
              <el-select v-model="form.org_type" style="width: 100%">
                <el-option v-for="item in ORG_TYPES" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="负责人">
              <RemoteSelect v-model="form.manager_id" :loader="loadPersonnelOptions" placeholder="请选择员工" style="width: 100%" />
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