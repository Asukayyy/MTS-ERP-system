import { createRouter, createWebHistory } from 'vue-router'
import type { Router } from 'vue-router'

import { constantRoutes } from './routes'
import { hasPermission, isLoggedIn } from '@/utils/auth'

const router: Router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: constantRoutes,
})

// 浏览器标题跟随路由 meta.title
router.afterEach((to) => {
  const appTitle = import.meta.env.VITE_APP_TITLE || 'BH-ERP'
  document.title = to.meta.title ? `${to.meta.title} - ${appTitle}` : appTitle
})

/**
 * 登录 + 权限路由守卫。
 *
 * - 未登录访问业务页 → 重定向 `/login` 并携带 redirect；
 * - 已登录但缺少 `meta.perm`（页面所需权限编码，见 `routes.ts`）→ 重定向 `/403`；
 * - 已登录访问 `/login` → 回工作台。
 *
 * 登录结果（含凭证与权限码）由登录页经 `utils/auth.ts` 写入 localStorage，
 * 退出登录 / 接口返回 401 时清除。
 */
const LOGIN_PATH = '/login'
const FORBIDDEN_PATH = '/403'
// 登录前可访问的公开页面（注册页不要求登录态）
const PUBLIC_PATHS = new Set([LOGIN_PATH, '/register'])

router.beforeEach((to) => {
  if (!PUBLIC_PATHS.has(to.path)) {
    if (!isLoggedIn()) {
      return { path: LOGIN_PATH, query: { redirect: to.fullPath } }
    }
    if (!hasPermission(to.meta.perm)) {
      return { path: FORBIDDEN_PATH }
    }
  }
  // 已登录访问登录页 → 回工作台（注册页不拦截）
  if (to.path === LOGIN_PATH && isLoggedIn()) {
    return { path: '/dashboard' }
  }
  return undefined
})

export default router