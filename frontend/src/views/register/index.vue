<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { listOrganizationsFlat, listRegisterRoles, register } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import type { RemoteOption, Role } from '@/types/erp'

const router = useRouter()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const rolesLoading = ref(false)
const roleOptions = ref<Role[]>([])

const form = reactive({
  username: '',
  display_name: '',
  password: '',
  password2: '',
  employee_no: '',
  org_id: undefined as number | undefined,
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

/** 部门下拉数据源：组织树扁平化 + 关键字过滤（与「员工管理」页保持一致） */
async function loadOrgOptions(keyword: string): Promise<RemoteOption[]> {
  const list = await listOrganizationsFlat()
  const text = (keyword || '').trim()
  return list
    .filter((item) => !text || item.org_code.includes(text) || item.org_name.includes(text))
    .map((item) => ({ id: item.id, label: `${item.org_code} ${item.org_name}` }))
}

onMounted(async () => {
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
      org_id: form.org_id as number,
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
          <RemoteSelect
            v-model="form.org_id"
            :loader="loadOrgOptions"
            placeholder="选择你的部门"
            class="register-page__org"
          />
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
          <el-select v-model="form.role_id" placeholder="选择你的身份" size="large" class="register-page__org">
            <el-option
              v-for="role in roleOptions"
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