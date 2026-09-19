<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { createPermission, getPermissionTree, updatePermission } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { Permission, RemoteOption } from '@/types/erp'

/** 权限类型 */
const PERM_TYPES = [
  { value: 'MENU', label: '菜单' },
  { value: 'PAGE', label: '页面' },
  { value: 'ACTION', label: '按钮' },
]

const loading = ref(false)
const rows = ref<Permission[]>([])

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await getPermissionTree()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

/** 把权限树拍平为下拉选项，带层级缩进便于识别 */
function flatten(list: Permission[], level = 0): Array<{ id: number; label: string }> {
  return list.flatMap((item) => [
    { id: item.id, label: `${'　'.repeat(level)}${item.perm_code} ${item.perm_name}` },
    ...flatten(item.children ?? [], level + 1),
  ])
}

async function loadParentOptions(keyword: string): Promise<RemoteOption[]> {
  const options = flatten(rows.value)
  const text = keyword.trim()
  return text ? options.filter((item) => item.label.includes(text)) : options
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  perm_code: string
  perm_name: string
  perm_type: string
  parent_id: number | undefined
  path: string
  module: string
  sort_no: number
  status: string
}>({
  perm_code: '',
  perm_name: '',
  perm_type: 'MENU',
  parent_id: undefined,
  path: '',
  module: '',
  sort_no: 0,
  status: 'ACTIVE',
})

const rules: FormRules = {
  perm_code: [{ required: true, message: '请输入权限编码', trigger: 'blur' }],
  perm_name: [{ required: true, message: '请输入权限名称', trigger: 'blur' }],
  perm_type: [{ required: true, message: '请选择权限类型', trigger: 'change' }],
}

function resetForm(): void {
  Object.assign(form, {
    perm_code: '',
    perm_name: '',
    perm_type: 'MENU',
    parent_id: undefined,
    path: '',
    module: '',
    sort_no: 0,
    status: 'ACTIVE',
  })
}

function openCreate(parent?: Permission): void {
  editingId.value = null
  resetForm()
  if (parent) form.parent_id = parent.id
  dialogVisible.value = true
}

function openEdit(row: Permission): void {
  editingId.value = row.id
  Object.assign(form, {
    perm_code: row.perm_code,
    perm_name: row.perm_name,
    perm_type: row.perm_type,
    parent_id: row.parent_id ?? undefined,
    path: row.path ?? '',
    module: row.module ?? '',
    sort_no: row.sort_no,
    status: row.status,
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const payload = {
      perm_name: form.perm_name,
      perm_type: form.perm_type,
      parent_id: form.parent_id ?? null,
      path: form.path || null,
      module: form.module || null,
      sort_no: form.sort_no,
      status: form.status,
    }
    if (editingId.value === null) {
      await createPermission({ ...payload, perm_code: form.perm_code })
      ElMessage.success('权限点已新增')
    } else {
      await updatePermission(editingId.value, payload)
      ElMessage.success('权限点已修改')
    }
    dialogVisible.value = false
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
          <span class="page-title">权限</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="load">刷新</el-button>
          <el-button type="primary" @click="openCreate()">新增权限点</el-button>
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
        <el-table-column label="权限编码" prop="perm_code" min-width="180" />
        <el-table-column label="权限名称" prop="perm_name" min-width="170" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            {{ PERM_TYPES.find((item) => item.value === row.perm_type)?.label ?? row.perm_type }}
          </template>
        </el-table-column>
        <el-table-column label="所属模块" prop="module" width="110" />
        <el-table-column label="路由 / 接口路径" prop="path" min-width="180" show-overflow-tooltip />
        <el-table-column label="排序" prop="sort_no" width="80" align="right" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="success" @click="openCreate(row)">新增子项</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无权限数据</template>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增权限点' : '修改权限点'" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="权限编码" prop="perm_code">
              <el-input v-model="form.perm_code" :disabled="editingId !== null" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="权限名称" prop="perm_name">
              <el-input v-model="form.perm_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="权限类型" prop="perm_type">
              <el-select v-model="form.perm_type" style="width: 100%">
                <el-option v-for="item in PERM_TYPES" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="上级权限">
              <RemoteSelect v-model="form.parent_id" :loader="loadParentOptions" placeholder="顶级权限" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属模块">
              <el-input v-model="form.module" placeholder="system / sales / planning / procurement / inventory" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="排序号">
              <el-input-number v-model="form.sort_no" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="路由 / 接口路径">
              <el-input v-model="form.path" />
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
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>