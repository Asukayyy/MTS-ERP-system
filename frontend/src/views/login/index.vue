<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { login } from '@/api/system'
import { saveAuth } from '@/utils/auth'

/** 「记住用户名」在 localStorage 中的键 */
const REMEMBER_KEY = 'bh-erp-remember-username'

const router = useRouter()
const route = useRoute()

const submitting = ref(false)
const remember = ref(localStorage.getItem(REMEMBER_KEY) !== null)
const form = reactive({
  username: (route.query.username as string) || localStorage.getItem(REMEMBER_KEY) || '',
  password: '',
})

/** 原生表单没有 el-form 的校验，这里做最小必要校验后交给后端判定密码 */
function validate(): string | null {
  if (!form.username.trim()) return '请输入用户名'
  if (!form.password) return '请输入密码'
  return null
}

async function submit(): Promise<void> {
  const message = validate()
  if (message) {
    ElMessage.warning(message)
    return
  }
  submitting.value = true
  try {
    const result = await login({ username: form.username, password: form.password })
    saveAuth(result)
    if (remember.value) {
      localStorage.setItem(REMEMBER_KEY, form.username)
    } else {
      localStorage.removeItem(REMEMBER_KEY)
    }
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
  <div class="login">
    <form class="login__card" @submit.prevent="submit">
      <div class="login__header">
        <h3 class="login__title">大牛技术有限公司</h3>
      </div>

      <div class="login__body">
        <div class="login__field">
          <span class="login__icon">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5Z" />
            </svg>
          </span>
          <input
            v-model="form.username"
            class="login__input"
            type="text"
            placeholder="用户名"
            autocomplete="username"
          />
        </div>

        <div class="login__field">
          <span class="login__icon">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5Zm0 2a3 3 0 0 1 3 3v3H9V7a3 3 0 0 1 3-3Zm0 11a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z" />
            </svg>
          </span>
          <input
            v-model="form.password"
            class="login__input"
            type="password"
            placeholder="密码"
            autocomplete="current-password"
          />
        </div>

        <label class="login__remember">
          <input v-model="remember" type="checkbox" />
          记住用户名
        </label>

        <div class="login__actions">
          <button class="login__submit" type="submit" :disabled="submitting">
            {{ submitting ? '登录中…' : '登 录' }}
          </button>
        </div>
      </div>

      <div class="login__footer">
        <div class="login__links">
          没有账号？<router-link to="/register">去注册</router-link>
        </div>
        <div class="login__links">忘记密码请联系系统管理员</div>
      </div>
    </form>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  align-items: center;
  justify-content: flex-end; /* 表单压在插画右侧的留白区 */
  height: 100%;
  min-height: 100%;
  padding: 40px 7vw 40px 24px;
  overflow-y: auto;
  background: #f5f7fa url('../../assets/login-bg.png') center / cover no-repeat;
  font-family: 'Numans', 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.login__card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 400px;
  border: 1px solid #e6ebf2;
  border-radius: 14px;
  background-color: #fff;
  box-shadow: 0 18px 44px rgba(31, 45, 61, 0.12);
  color: #1f2d3d;
}

/* 卡片上沿的蓝橙点缀，呼应插画配色 */
.login__card::before {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 3px;
  border-radius: 13px 13px 0 0;
  background: linear-gradient(90deg, #3a7bd5, #f0a13c);
}

.login__header {
  padding: 20px 22px 16px;
  border-bottom: 1px solid #f0f3f8;
}

.login__title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #1f2d3d;
}

.login__body {
  padding: 20px 22px;
}

.login__field {
  display: flex;
  margin-bottom: 16px;
  border: 1px solid #dfe5ee;
  border-radius: 8px;
  overflow: hidden;
  background-color: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.login__field:focus-within {
  border-color: #3a7bd5;
  box-shadow: 0 0 0 3px rgba(58, 123, 213, 0.14);
}

.login__icon {
  display: flex;
  flex: 0 0 46px;
  align-items: center;
  justify-content: center;
  border-right: 1px solid #e8eef7;
  background-color: #f2f6fd;
  color: #3a7bd5;
}

.login__icon svg {
  width: 22px;
  height: 22px;
}

.login__input {
  flex: 1;
  min-width: 0;
  height: 42px;
  padding: 0 12px;
  border: 0;
  background-color: #fff;
  color: #1f2d3d;
  font-size: 15px;
  font-family: inherit;
}

.login__input:focus {
  outline: none;
}

.login__input::placeholder {
  color: #9aa7b8;
}

/* 浏览器自动填充会给输入框刷上浅黄底，这里压回白底 */
.login__input:-webkit-autofill {
  -webkit-text-fill-color: #1f2d3d;
  box-shadow: inset 0 0 0 100px #fff;
}

.login__remember {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 14px;
  color: #4a5568;
  cursor: pointer;
}

.login__remember input {
  width: 18px;
  height: 18px;
  accent-color: #3a7bd5;
  cursor: pointer;
}

.login__actions {
  display: flex;
  justify-content: flex-end;
}

.login__submit {
  min-width: 100px;
  height: 40px;
  padding: 0 18px;
  border: 0;
  border-radius: 8px;
  background-color: #3a7bd5;
  color: #fff;
  font-size: 15px;
  font-family: inherit;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(58, 123, 213, 0.28);
  transition: background-color 0.2s, box-shadow 0.2s;
}

.login__submit:hover:not(:disabled) {
  background-color: #3268b7;
  box-shadow: 0 8px 20px rgba(58, 123, 213, 0.36);
}

.login__submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login__footer {
  padding: 14px 22px 18px;
  border-top: 1px solid #f0f3f8;
  text-align: center;
  font-size: 13px;
}

.login__links {
  color: #7a8699;
  line-height: 1.9;
}

.login__links a {
  margin-left: 4px;
  color: #3a7bd5;
  text-decoration: none;
}

.login__links a:hover {
  text-decoration: underline;
}

/* 窄屏时插画会被卡片压住，卡片回到居中并把背景压淡保证对比 */
@media (max-width: 1000px) {
  .login {
    justify-content: center;
    padding: 48px 20px;
    background-image:
      linear-gradient(rgba(247, 249, 252, 0.88), rgba(247, 249, 252, 0.95)),
      url('../../assets/login-bg.png');
  }
}

@media (max-width: 480px) {
  .login__title {
    font-size: 19px;
  }
}
</style>
