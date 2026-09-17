import { createRouter, createWebHistory } from 'vue-router'
import type { Router } from 'vue-router'

import { constantRoutes } from './routes'

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
 * 登录前 / 登录后路由结构已经建好：
 * - `/login` 位于主布局之外
 * - `/dashboard`、`/system`、`/sales`、`/planning`、`/procurement`、`/inventory` 位于主布局之内
 *
 * 真实的登录态校验请由 system 模块负责人通过 `router.beforeEach` 接入，
 * 本阶段**不实现任何鉴权逻辑**。
 */

export default router
