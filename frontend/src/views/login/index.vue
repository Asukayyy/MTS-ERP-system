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
    <div class="login__art" aria-hidden="true"></div>

    <div class="login__brand">
      <svg class="login__brand-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 21v-7" stroke="#3d9d94" stroke-width="2" stroke-linecap="round" />
        <circle cx="12" cy="8" r="5" fill="#e0944a" />
        <circle cx="6.5" cy="12.5" r="2.8" fill="#3d9d94" />
        <circle cx="17.5" cy="12.5" r="2.8" fill="#3d9d94" />
      </svg>
      <span class="login__brand-name">大树科技有限公司</span>
    </div>

    <form class="login__card" @submit.prevent="submit">
      <span class="login__ribbon" aria-hidden="true"></span>
      <span class="login__tab" aria-hidden="true"></span>

      <div class="login__header">
        <h3 class="login__title">大树科技有限公司</h3>
      </div>

      <div class="login__body">
        <div class="login__field">
          <input
            v-model="form.username"
            class="login__input"
            type="text"
            placeholder="用户名"
            autocomplete="username"
          />
        </div>

        <div class="login__field">
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

        <button class="login__submit" type="submit" :disabled="submitting">
          {{ submitting ? '登录中…' : '登 录' }}
        </button>
      </div>

      <div class="login__footer">
        <div class="login__links">账号由人事部统一开通</div>
        <div class="login__links">忘记密码请联系系统管理员</div>
      </div>
    </form>
  </div>
</template>

<style scoped>
.login {
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

/* 左侧沿用设计稿的插画，右边缘渐变淡出与页面底色衔接 */
.login__art {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 60%;
  background: url('../../assets/auth-left.png') left bottom / cover no-repeat;
  -webkit-mask-image: linear-gradient(90deg, #000 92%, transparent 100%);
  mask-image: linear-gradient(90deg, #000 92%, transparent 100%);
}

.login__brand {
  display: none;
}

.login__card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 420px;
  border: 1px solid #ece8e0;
  border-radius: 20px;
  background-color: #fff;
  box-shadow: 0 22px 50px rgba(80, 92, 88, 0.13);
}

/* 卡纸叠层：一片薄荷绿 + 一片白，轻微旋转，呼应设计稿的层叠卡片 */
.login__card::before,
.login__card::after {
  content: '';
  position: absolute;
  z-index: -1;
  inset: 0;
  border-radius: 20px;
}

.login__card::before {
  transform: rotate(-2.4deg) translate(-10px, 8px);
  background-color: #d8e7e2;
}

.login__card::after {
  transform: rotate(1.4deg) translate(10px, 4px);
  border: 1px solid #e8e4dc;
  background-color: #fff;
}

/* 右上角橙色书签 */
.login__ribbon {
  position: absolute;
  top: -9px;
  right: 30px;
  width: 22px;
  height: 34px;
  border-radius: 2px;
  background-color: #f0a24e;
  clip-path: polygon(0 0, 100% 0, 100% 100%, 50% 76%, 0 100%);
  box-shadow: 0 3px 6px rgba(240, 162, 78, 0.32);
}

/* 右侧边缘的薄荷绿小标签 */
.login__tab {
  position: absolute;
  top: 44%;
  right: -13px;
  width: 26px;
  height: 58px;
  border-radius: 8px;
  background-color: #5cb6ae;
}

.login__header {
  padding: 30px 30px 4px;
}

.login__title {
  margin: 0;
  color: #33413f;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 2px;
}

.login__body {
  padding: 20px 30px 26px;
}

.login__field {
  margin-bottom: 14px;
}

.login__input {
  width: 100%;
  height: 46px;
  padding: 0 14px;
  border: 1px solid #e6e2da;
  border-radius: 10px;
  background-color: #fff;
  color: #33413f;
  font-size: 15px;
  font-family: inherit;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.login__input:focus {
  border-color: #5cb6ae;
  outline: none;
  box-shadow: 0 0 0 3px rgba(92, 182, 174, 0.16);
}

.login__input::placeholder {
  color: #a9a294;
}

/* 浏览器自动填充会给输入框刷上浅黄底，这里压回白底 */
.login__input:-webkit-autofill {
  -webkit-text-fill-color: #33413f;
  box-shadow: inset 0 0 0 100px #fff;
}

.login__remember {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 4px 0 18px;
  color: #6f6858;
  font-size: 14px;
  cursor: pointer;
}

.login__remember input {
  width: 18px;
  height: 18px;
  accent-color: #5cb6ae;
  cursor: pointer;
}

.login__submit {
  width: 100%;
  height: 46px;
  border: 0;
  border-radius: 23px;
  background-color: #5cb6ae;
  color: #fff;
  font-size: 15px;
  font-family: inherit;
  letter-spacing: 4px;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(92, 182, 174, 0.3);
  transition: background-color 0.2s, box-shadow 0.2s;
}

.login__submit:hover:not(:disabled) {
  background-color: #4fa9a1;
  box-shadow: 0 10px 22px rgba(92, 182, 174, 0.36);
}

.login__submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login__footer {
  padding: 14px 30px 22px;
  border-top: 1px solid #f2eee7;
  text-align: center;
  font-size: 13px;
}

.login__links {
  color: #8a8375;
  line-height: 1.9;
}

.login__links a {
  margin-left: 4px;
  color: #4fa9a1;
  text-decoration: none;
}

.login__links a:hover {
  text-decoration: underline;
}

@media (max-width: 1100px) {
  .login {
    justify-content: center;
    padding: 96px 20px 40px;
  }

  .login__art {
    display: none;
  }

  .login__brand {
    position: absolute;
    top: 24px;
    left: 22px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .login__brand-icon {
    width: 26px;
    height: 26px;
  }

  .login__brand-name {
    color: #33413f;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 1px;
  }
}

@media (max-width: 480px) {
  .login__title {
    font-size: 18px;
  }

  .login__header,
  .login__body {
    padding-right: 22px;
    padding-left: 22px;
  }
}
</style>
