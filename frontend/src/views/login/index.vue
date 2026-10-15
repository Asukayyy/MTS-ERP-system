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
        <!-- 卡片右上角悬浮的金色图标组（纯装饰） -->
        <div class="login__badges" aria-hidden="true">
          <span class="login__badge">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3L18.7 8 12 11.7 5.3 8 12 4.3ZM5 9.7v6.1l6 3.3v-6.1L5 9.7Zm14 0-6 3.3v6.1l6-3.3V9.7Z" />
            </svg>
          </span>
          <span class="login__badge">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M4 19h3v-6H4v6Zm5 0h3V5H9v14Zm5 0h3v-9h-3v9Z" />
            </svg>
          </span>
          <span class="login__badge">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M4 5h16v3H4V5Zm1 5h14v9H5v-9Zm2 2v5h4v-5H7Z" />
            </svg>
          </span>
        </div>
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
  justify-content: center;
  height: 100%;
  min-height: 100%;
  padding: 80px 24px 40px;
  overflow-y: auto;
  background: #171a1f url('../../assets/login-bg.jpg') center / cover no-repeat;
  font-family: 'Numans', 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* 压暗背景，保证半透明卡片上的文字可读 */
.login::before {
  content: '';
  position: fixed;
  inset: 0;
  background: linear-gradient(rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.65));
}

.login__card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 400px;
  background-color: rgba(0, 0, 0, 0.5);
  border-radius: 6px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
  color: #fff;
}

.login__header {
  position: relative;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}

.login__title {
  margin: 0;
  font-size: 28px;
  font-weight: 500;
  color: #fff;
}

/* 悬浮在卡片右上角、探出卡片边缘的图标组 */
.login__badges {
  position: absolute;
  right: 20px;
  top: -52px;
  display: flex;
  gap: 14px;
}

.login__badge {
  display: block;
  color: #ffc312;
  line-height: 0;
}

.login__badge svg {
  width: 48px;
  height: 48px;
}

.login__body {
  padding: 20px;
}

.login__field {
  display: flex;
  margin-bottom: 16px;
  border-radius: 4px;
  overflow: hidden;
  transition: box-shadow 0.2s;
}

.login__field:focus-within {
  box-shadow: 0 0 0 2px rgba(255, 195, 18, 0.65);
}

.login__icon {
  display: flex;
  flex: 0 0 50px;
  align-items: center;
  justify-content: center;
  background-color: #ffc312;
  color: #1a1a1a;
}

.login__icon svg {
  width: 22px;
  height: 22px;
}

.login__input {
  flex: 1;
  min-width: 0;
  height: 44px;
  padding: 0 12px;
  border: 0;
  background-color: #fff;
  color: #222;
  font-size: 15px;
  font-family: inherit;
}

.login__input:focus {
  outline: none;
}

.login__input::placeholder {
  color: #9aa0a6;
}

.login__remember {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 14px;
  color: #fff;
  cursor: pointer;
}

.login__remember input {
  width: 18px;
  height: 18px;
  accent-color: #ffc312;
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
  border-radius: 4px;
  background-color: #ffc312;
  color: #1a1a1a;
  font-size: 15px;
  font-family: inherit;
  cursor: pointer;
  transition: background-color 0.2s;
}

.login__submit:hover:not(:disabled) {
  background-color: #fff;
}

.login__submit:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.login__footer {
  padding: 14px 20px 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  text-align: center;
  font-size: 13px;
}

.login__links {
  color: #fff;
  line-height: 1.9;
}

.login__links a {
  margin-left: 4px;
  color: #ffc312;
  text-decoration: none;
}

.login__links a:hover {
  text-decoration: underline;
}

@media (max-width: 480px) {
  .login {
    padding: 64px 16px 24px;
  }

  .login__badges {
    top: -40px;
    gap: 10px;
  }

  .login__badge svg {
    width: 36px;
    height: 36px;
  }

  .login__title {
    font-size: 22px;
  }
}
</style>