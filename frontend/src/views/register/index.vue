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
    <div class="register-page__art" aria-hidden="true"></div>

    <div class="register-page__brand">
      <svg class="register-page__brand-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 21v-7" stroke="#3d9d94" stroke-width="2" stroke-linecap="round" />
        <circle cx="12" cy="8" r="5" fill="#e0944a" />
        <circle cx="6.5" cy="12.5" r="2.8" fill="#3d9d94" />
        <circle cx="17.5" cy="12.5" r="2.8" fill="#3d9d94" />
      </svg>
      <span class="register-page__brand-name">大树科技有限公司</span>
    </div>

    <div class="register-page__stack">
      <span class="register-page__ribbon" aria-hidden="true"></span>
      <span class="register-page__tab" aria-hidden="true"></span>
      <el-card class="register-page__card" shadow="never">
        <template #header>
          <span class="register-page__title">账号注册</span>
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
  </div>
</template>

<style scoped>
/* 注册页：沿用设计稿的插画与卡纸叠层，只把表单换成本系统的注册表单 */
.register-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-height: 100%;
  padding: 48px clamp(28px, 5vw, 80px) 48px 24px;
  overflow: hidden;
  background: #faf8f4;
  font-family: 'Numans', 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.register-page__art {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 60%;
  background: url('../../assets/auth-left.png') left bottom / cover no-repeat;
  -webkit-mask-image: linear-gradient(90deg, #000 92%, transparent 100%);
  mask-image: linear-gradient(90deg, #000 92%, transparent 100%);
}

.register-page__brand {
  display: none;
}

.register-page__stack {
  position: relative;
  z-index: 1;
  flex: 0 1 520px;
  width: 100%;
  max-width: 520px;
}

.register-page__card {
  position: relative;
  overflow: visible;
  border: 1px solid #ece8e0;
  border-radius: 20px;
  box-shadow: 0 22px 50px rgba(80, 92, 88, 0.13);
  /* Element Plus 控件跟随设计稿的橙青配色 */
  --el-color-primary: #5cb6ae;
  --el-color-primary-light-3: #7cc6bf;
  --el-color-primary-light-5: #9dd5d0;
  --el-color-primary-light-7: #bee3df;
  --el-color-primary-light-8: #cfece9;
  --el-color-primary-light-9: #e6f3f1;
  --el-color-primary-dark-2: #4fa9a1;
  --el-text-color-primary: #33413f;
  --el-text-color-regular: #5c5648;
  --el-text-color-placeholder: #a9a294;
  --el-border-color: #e6e2da;
  --el-border-color-light: #f2eee7;
  --el-border-color-hover: #cdc3ae;
  --el-border-radius-base: 10px;
}

/* 卡纸叠层：薄荷绿 + 白，与登录卡片一致 */
.register-page__card::before,
.register-page__card::after {
  content: '';
  position: absolute;
  z-index: -1;
  inset: 0;
  border-radius: 20px;
}

.register-page__card::before {
  transform: rotate(-2.2deg) translate(-9px, 8px);
  background-color: #d8e7e2;
}

.register-page__card::after {
  transform: rotate(1.4deg) translate(9px, 4px);
  border: 1px solid #e8e4dc;
  background-color: #fff;
}

.register-page__ribbon {
  position: absolute;
  top: -9px;
  right: 34px;
  z-index: 2;
  width: 22px;
  height: 34px;
  border-radius: 2px;
  background-color: #f0a24e;
  clip-path: polygon(0 0, 100% 0, 100% 100%, 50% 76%, 0 100%);
  box-shadow: 0 3px 6px rgba(240, 162, 78, 0.32);
}

.register-page__tab {
  position: absolute;
  top: 42%;
  right: -13px;
  z-index: 2;
  width: 26px;
  height: 58px;
  border-radius: 8px;
  background-color: #5cb6ae;
}

.register-page__title {
  color: #33413f;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 2px;
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
  color: #8a8375;
  white-space: normal;
}

.register-page__button {
  width: 100%;
  height: 46px;
  margin-top: 6px;
  border-radius: 23px;
  letter-spacing: 4px;
  box-shadow: 0 8px 18px rgba(92, 182, 174, 0.3);
}

.register-page__footer {
  color: #8a8375;
  font-size: 13px;
  text-align: center;
}

.register-page__link {
  margin-left: 6px;
  color: #4fa9a1;
  text-decoration: none;
}

.register-page__link:hover {
  text-decoration: underline;
}

@media (max-width: 1279px) {
  .register-page {
    justify-content: center;
    padding: 96px 20px 40px;
  }

  .register-page__art {
    display: none;
  }

  .register-page__brand {
    position: absolute;
    top: 24px;
    left: 22px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .register-page__brand-icon {
    width: 26px;
    height: 26px;
  }

  .register-page__brand-name {
    color: #33413f;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 1px;
  }

  .register-page__stack {
    flex: 0 1 520px;
  }
}
</style>
