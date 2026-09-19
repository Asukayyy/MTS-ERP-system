<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createRole,
  getPermissionTree,
  listRoles,
  setRolePermissions,
  updateRole,
} from '@/api/system'
import StatusTag from '@/components/common/StatusTag.vue'
import type { Permission, Role } from '@/types/erp'

/** el-tree 暴露的方法（仅声明用到的部分，避免引入 any） */
interface TreeExpose {
  setCheckedKeys: (keys: number[]) => void
  getCheckedKeys: (leafOnly?: boolean) => number[]
  getHalfCheckedKeys: () => number[]
}

const loading = ref(false)
const rows = ref<Role[]>([])
const permissionTree = ref<Permission[]>([])

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await listRoles()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadPermissions(): Promise<void> {
  try {
    permissionTree.value = await getPermissionTree()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function permissionCount(row: Role): number {
  return row.permissions.length
}

// ---------------- 新增 / 修改 ----------------
const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  role_code: '',
  role_name: '',
  description: '',
  status: 'ACTIVE',
})

const rules: FormRules = {
  role_code: [{ required: true, message: '请输入角色编码', trigger: 'blur' }],
  role_name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, { role_code: '', role_name: '', description: '', status: 'ACTIVE' })
  dialogVisible.value = true
}

function openEdit(row: Role): void {
  editingId.value = row.id
  Object.assign(form, {
    role_code: row.role_code,
    role_name: row.role_name,
    description: row.description ?? '',
    status: row.status,
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editingId.value === null) {
      await createRole({
        role_code: form.role_code,
        role_name: form.role_name,
        description: form.description || null,
        status: form.status,
      })
      ElMessage.success('角色已新增')
    } else {
      await updateRole(editingId.value, {
        role_name: form.role_name,
        description: form.description || null,
        status: form.status,
      })
      ElMessage.success('角色已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

// ---------------- 分配权限 ----------------
const permDialogVisible = ref(false)
const permSubmitting = ref(false)
const permTargetId = ref<number | null>(null)
const checkedIds = ref<number[]>([])
const permTreeRef = ref<TreeExpose>()

function openPermissions(row: Role): void {
  permTargetId.value = row.id
  checkedIds.value = row.permissions.map((item) => item.id)
  permDialogVisible.value = true
  // 等待 el-tree 挂载后回显勾选项
  setTimeout(() => permTreeRef.value?.setCheckedKeys(checkedIds.value), 0)
}

async function submitPermissions(): Promise<void> {
  if (permTargetId.value === null) return
  const checked = permTreeRef.value?.getCheckedKeys() ?? []
  const half = permTreeRef.value?.getHalfCheckedKeys() ?? []
  const ids = [...half, ...checked].map((item) => Number(item))
  permSubmitting.value = true
  try {
    await setRolePermissions(permTargetId.value, ids)
    ElMessage.success('权限已保存')
    permDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    permSubmitting.value = false
  }
}

onMounted(() => {
  load()
  loadPermissions()
})
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">角色</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="load">刷新</el-button>
          <el-button type="primary" @click="openCreate">新增角色</el-button>
        </div>
      </template>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="角色编码" prop="role_code" min-width="150" />
        <el-table-column label="角色名称" prop="role_name" min-width="150" />
        <el-table-column label="说明" prop="description" min-width="180" show-overflow-tooltip />
        <el-table-column label="权限点数量" width="110" align="right">
          <template #default="{ row }">{{ permissionCount(row) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" @click="openPermissions(row)">分配权限</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无角色数据</template>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增角色' : '修改角色'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="角色编码" prop="role_code">
          <el-input v-model="form.role_code" :disabled="editingId !== null" />
        </el-form-item>
        <el-form-item label="角色名称" prop="role_name">
          <el-input v-model="form.role_name" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="启用" value="ACTIVE" />
            <el-option label="停用" value="INACTIVE" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="permDialogVisible" title="分配权限" width="520px">
      <el-tree
        ref="permTreeRef"
        :data="permissionTree"
        node-key="id"
        show-checkbox
        default-expand-all
        :props="{ label: 'perm_name', children: 'children' }"
      />
      <template #footer>
        <el-button @click="permDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="permSubmitting" @click="submitPermissions">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>