<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createUser,
  listPersonnel,
  listRoles,
  listUsers,
  setUserRoles,
  setUserStatus,
  updateUser,
} from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { RemoteOption, Role, User } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<User, { keyword: string; status: string }>(
    (params) => listUsers(params),
    { keyword: '', status: '' },
  )

/** 全部角色（用于分配角色） */
const roleOptions = ref<Role[]>([])

/** 员工选项 */
async function loadPersonnelOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

async function loadRoles(): Promise<void> {
  try {
    roleOptions.value = await listRoles()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

/** 表格展示角色名 */
function roleNames(row: User): string {
  return row.roles.length ? row.roles.map((item) => item.role_name).join('、') : '-'
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  username: string
  password: string
  display_name: string
  personnel_id: number | undefined
  status: string
  remark: string
}>({
  username: '',
  password: '',
  display_name: '',
  personnel_id: undefined,
  status: 'ACTIVE',
  remark: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入登录名', trigger: 'blur' }],
  display_name: [{ required: true, message: '请输入显示名', trigger: 'blur' }],
}

function resetForm(): void {
  Object.assign(form, {
    username: '',
    password: '',
    display_name: '',
    personnel_id: undefined,
    status: 'ACTIVE',
    remark: '',
  })
}

function openCreate(): void {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: User): void {
  editingId.value = row.id
  Object.assign(form, {
    username: row.username,
    password: '',
    display_name: row.display_name,
    personnel_id: row.personnel_id ?? undefined,
    status: row.status,
    remark: row.remark ?? '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (editingId.value === null && !form.password) {
    ElMessage.warning('请为新用户设置初始密码')
    return
  }
  submitting.value = true
  try {
    if (editingId.value === null) {
      await createUser({
        username: form.username,
        password: form.password,
        display_name: form.display_name,
        personnel_id: form.personnel_id ?? null,
        status: form.status,
        remark: form.remark || null,
      })
      ElMessage.success('用户已新增')
    } else {
      await updateUser(editingId.value, {
        display_name: form.display_name,
        password: form.password || null,
        personnel_id: form.personnel_id ?? null,
        status: form.status,
        remark: form.remark || null,
      })
      ElMessage.success('用户已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function toggleStatus(row: User): Promise<void> {
  const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'
  try {
    await setUserStatus(row.id, next)
    ElMessage.success(next === 'ACTIVE' ? '用户已启用' : '用户已停用')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

// ---------------- 分配角色 ----------------
const roleDialogVisible = ref(false)
const roleSubmitting = ref(false)
const roleTargetId = ref<number | null>(null)
const selectedRoleIds = ref<number[]>([])

function openRoles(row: User): void {
  roleTargetId.value = row.id
  selectedRoleIds.value = row.roles.map((item) => item.id)
  roleDialogVisible.value = true
}

async function submitRoles(): Promise<void> {
  if (roleTargetId.value === null) return
  roleSubmitting.value = true
  try {
    await setUserRoles(roleTargetId.value, selectedRoleIds.value)
    ElMessage.success('角色已保存')
    roleDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    roleSubmitting.value = false
  }
}

onMounted(() => {
  load()
  loadRoles()
})
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">用户</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增用户</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="关键字">
          <el-input v-model="query.keyword" placeholder="登录名 / 显示名" clearable style="width: 180px" @keyup.enter="search" />
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
        <el-table-column label="登录名" prop="username" min-width="130" />
        <el-table-column label="显示名" prop="display_name" min-width="130" />
        <el-table-column label="关联员工ID" prop="personnel_id" width="110" align="right" />
        <el-table-column label="角色" min-width="180">
          <template #default="{ row }">{{ roleNames(row) }}</template>
        </el-table-column>
        <el-table-column label="最近登录" prop="last_login_at" min-width="170" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" @click="openRoles(row)">分配角色</el-button>
            <el-button
              link
              :type="row.status === 'ACTIVE' ? 'danger' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无用户数据</template>
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

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增用户' : '修改用户'" width="620px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="登录名" prop="username">
              <el-input v-model="form.username" :disabled="editingId !== null" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="显示名" prop="display_name">
              <el-input v-model="form.display_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码">
              <el-input
                v-model="form.password"
                type="password"
                show-password
                :placeholder="editingId === null ? '请输入初始密码' : '留空则不修改'"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联员工">
              <RemoteSelect v-model="form.personnel_id" :loader="loadPersonnelOptions" style="width: 100%" />
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

    <el-dialog v-model="roleDialogVisible" title="分配角色" width="480px">
      <el-select v-model="selectedRoleIds" multiple placeholder="请选择角色" style="width: 100%">
        <el-option
          v-for="item in roleOptions"
          :key="item.id"
          :label="`${item.role_code} ${item.role_name}`"
          :value="item.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="roleSubmitting" @click="submitRoles">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>