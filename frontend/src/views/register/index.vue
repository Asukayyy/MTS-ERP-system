<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { listOrganizationsFlat, listRegisterRoles, register } from '@/api/system'
import type { Organization, Role } from '@/types/erp'

const router = useRouter()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const rolesLoading = ref(false)
const roleOptions = ref<Role[]>([])
const orgLoading = ref(false)
const orgs = ref<Organization[]>([])

const form = reactive({
  username: '',
  display_name: '',
  password: '',
  password2: '',
  employee_no: '',
  org_id: undefined as number | undefined,
  workshop_id: undefined as number | undefined,
  role_id: undefined as number | undefined,
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  display_name: [{ required: true, message: '请输入显示名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度需为 6~64 位', trigger: 'blur' },
  ],
  password2: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        callback(value === form.password ? undefined : new Error('两次输入的密码不一致'))
      },
      trigger: 'blur',
    },
  ],
  org_id: [{ required: true, message: '请选择所属部门', trigger: 'change' }],
  role_id: [{ required: true, message: '请选择身份', trigger: 'change' }],
}

/** 部门编码 → 该部门可选身份（职能身份 + 部长；总经办本身即管理岗，只留管理人员） */
const ORG_ROLE_MAP: Record<string, string[]> = {
  'DEP-ADMIN': ['ADMIN'],
  'DEP-DESIGN': ['DESIGN', 'DEPT_HEAD'],
  'DEP-PLAN': ['PLAN', 'DEPT_HEAD'],
  'DEP-PURCHASE': ['PURCHASE', 'DEPT_HEAD'],
  'DEP-SALES': ['SALES', 'DEPT_HEAD'],
  'DEP-WAREHOUSE': ['INVENTORY', 'DEPT_HEAD'],
  'DEP-QC': ['QC', 'DEPT_HEAD'],
  'DEP-FINANCE': ['FINANCE', 'DEPT_HEAD'],
  'MFG-CTR': ['MAKE', 'DIRECTOR'],
}

/** 车间可选身份：工人 / 组长 */
const WORKSHOP_ROLE_CODES = ['WORKER', 'GROUP_LEADER']

/** 一级可选：各部门 + 工厂（去掉公司根节点与车间） */
const topLevelOrgs = computed(() =>
  orgs.value.filter((item) => item.org_type !== 'COMPANY' && item.org_type !== 'WORKSHOP'),
)

/** 当前选中的一级组织 */
const selectedOrg = computed(() => orgs.value.find((item) => item.id === form.org_id) ?? null)

/** 是否选中了工厂（智能加工中心） */
const isFactory = computed(() => selectedOrg.value?.org_type === 'FACTORY')

/** 工厂下的车间 */
const workshopOptions = computed(() =>
  isFactory.value ? orgs.value.filter((item) => item.parent_id === form.org_id && item.org_type === 'WORKSHOP') : [],
)

/** 当前选中的车间 */
const selectedWorkshop = computed(
  () => workshopOptions.value.find((item) => item.id === form.workshop_id) ?? null,
)

/** 身份过滤依据的组织：工厂下若选了车间以车间为准，否则用工厂本身 */
const effectiveOrg = computed(() =>
  isFactory.value ? (selectedWorkshop.value ?? selectedOrg.value) : selectedOrg.value,
)

/** 当前组织可选的身份（随部门 / 车间联动） */
const availableRoles = computed(() => {
  const org = effectiveOrg.value
  if (!org) return []
  const codes = org.org_type === 'WORKSHOP' ? WORKSHOP_ROLE_CODES : (ORG_ROLE_MAP[org.org_code] ?? [])
  return roleOptions.value.filter((role) => codes.includes(role.role_code))
})

// 切换一级组织时清空车间，避免残留上一次的选择
watch(
  () => form.org_id,
  () => {
    form.workshop_id = undefined
  },
)

// 部门 / 车间变化时清空已选身份，避免残留不匹配的选择
watch([() => form.org_id, () => form.workshop_id], () => {
  form.role_id = undefined
})

onMounted(async () => {
  orgLoading.value = true
  try {
    orgs.value = await listOrganizationsFlat()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    orgLoading.value = false
  }

  rolesLoading.value = true
  try {
    roleOptions.value = await listRegisterRoles()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    rolesLoading.value = false
  }
})

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await register({
      username: form.username,
      password: form.password,
      display_name: form.display_name,
      org_id: (form.workshop_id ?? form.org_id) as number,
      employee_no: form.employee_no.trim() || undefined,
      role_ids: [form.role_id as number],
    })
    ElMessage.success('注册成功，请使用新账号登录')
    router.replace({ path: '/login', query: { username: form.username } })
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="register-page">
    <el-card class="register-page__card" shadow="never">
      <template #header>
        <span class="register-page__title">BH-ERP 账号注册</span>
      </template>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="登录名（唯一）" size="large" />
        </el-form-item>
        <el-form-item label="显示名" prop="display_name">
          <el-input v-model="form.display_name" placeholder="姓名（同时作为员工姓名）" size="large" />
        </el-form-item>
        <el-form-item label="所属部门" prop="org_id">
          <el-select
            v-model="form.org_id"
            placeholder="选择你的部门"
            size="large"
            class="register-page__org"
            :loading="orgLoading"
          >
            <el-option
              v-for="org in topLevelOrgs"
              :key="org.id"
              :label="`${org.org_code} ${org.org_name}`"
              :value="org.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="isFactory" label="所属车间" prop="workshop_id">
          <el-select
            v-model="form.workshop_id"
            placeholder="选择具体车间（选填）"
            size="large"
            class="register-page__org"
            clearable
          >
            <el-option
              v-for="ws in workshopOptions"
              :key="ws.id"
              :label="`${ws.org_code} ${ws.org_name}`"
              :value="ws.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="工号" prop="employee_no">
          <el-input
            v-model="form.employee_no"
            placeholder="留空自动生成（如 EMP00001）"
            size="large"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="至少 6 位"
            size="large"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="password2">
          <el-input
            v-model="form.password2"
            type="password"
            placeholder="再次输入密码"
            size="large"
            show-password
          />
        </el-form-item>
        <el-form-item label="选择身份" prop="role_id">
          <el-select
            v-model="form.role_id"
            :placeholder="isFactory && !form.workshop_id ? '选车间后可选工人/组长' : '请选择你的身份'"
            size="large"
            class="register-page__org"
            :disabled="!availableRoles.length"
          >
            <el-option
              v-for="role in availableRoles"
              :key="role.id"
              :label="role.role_name"
              :value="role.id"
            >
              <div class="register-page__role-name">{{ role.role_name }}</div>
              <div v-if="role.description" class="register-page__role-desc">{{ role.description }}</div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-button
          class="register-page__button"
          type="primary"
          size="large"
          :loading="submitting || rolesLoading"
          @click="submit"
        >
          注 册
        </el-button>
      </el-form>

      <el-divider />

      <div class="register-page__footer">
        <span>注册同时创建员工档案，归属所选部门，工号自动或手动分配。</span>
        <router-link class="register-page__link" to="/login">去登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.register-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 24px 0;
  background-color: #f5f7fa;
}

.register-page__card {
  width: 520px;
}

.register-page__title {
  font-size: 16px;
  font-weight: 600;
}

.register-page__org {
  width: 100%;
}

.register-page__role-name {
  font-weight: 500;
}

.register-page__role-desc {
  font-size: 12px;
  line-height: 1.4;
  color: #909399;
  white-space: normal;
}

.register-page__button {
  width: 100%;
}

.register-page__footer {
  text-align: center;
  color: #909399;
  font-size: 13px;
}

.register-page__link {
  margin-left: 6px;
  color: #409eff;
  text-decoration: none;
}
</style>