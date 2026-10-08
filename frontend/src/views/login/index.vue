<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { login } from '@/api/system'

const router = useRouter()
const route = useRoute()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const form = reactive({
  username: (route.query.username as string) || '',
  password: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const result = await login({ username: form.username, password: form.password })
    localStorage.setItem('bh-erp-user', JSON.stringify(result))
    ElMessage.success(`欢迎，${result.user.display_name || result.user.username}`)
    const redirect = (route.query.redirect as string) || '/dashboard'
    router.replace(redirect)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-page__card" shadow="never">
      <template #header>
        <span class="login-page__title">BH-ERP 用户登录</span>
      </template>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="0" @keyup.enter="submit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" size="large" show-password />
        </el-form-item>
        <el-button class="login-page__button" type="primary" size="large" :loading="submitting" @click="submit">
          登 录
        </el-button>
      </el-form>

      <el-divider />

      <div class="login-page__footer">
        <span>没有账号？</span>
        <router-link class="login-page__link" to="/register">去注册</router-link>
        <span class="login-page__sep">|</span>
        <span>请联系管理员在「系统管理 → 用户」中创建</span>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background-color: #f5f7fa;
}

.login-page__card {
  width: 420px;
}

.login-page__title {
  font-size: 16px;
  font-weight: 600;
}

.login-page__button {
  width: 100%;
}

.login-page__footer {
  text-align: center;
  color: #909399;
  font-size: 13px;
}

.login-page__link {
  margin-left: 4px;
  color: #409eff;
  text-decoration: none;
}

.login-page__sep {
  margin: 0 8px;
}
</style>