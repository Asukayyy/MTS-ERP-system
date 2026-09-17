import type { RouteRecordRaw } from 'vue-router'

/**
 * 路由表。
 *
 * 五个模块的路径已提前规划好，模块负责人请**在自己模块的路由节点下添加子路由**，
 * 例如销售模块新增订单页：
 *
 * ```ts
 * {
 *   path: 'sales',
 *   children: [
 *     { path: 'orders', name: 'SalesOrder', component: () => import('@/views/sales/order/index.vue') },
 *   ],
 * }
 * ```
 *
 * 不要修改别人的模块节点。
 */
export const constantRoutes: RouteRecordRaw[] = [
  // ---------- 登录前 ----------
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录' },
  },

  // ---------- 登录后（主布局） ----------
  {
    path: '/',
    component: () => import('@/layouts/BasicLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '工作台' },
      },
      {
        path: 'system',
        name: 'System',
        component: () => import('@/views/system/index.vue'),
        meta: { title: '系统与基础信息管理' },
      },
      {
        path: 'sales',
        name: 'Sales',
        component: () => import('@/views/sales/index.vue'),
        meta: { title: '销售管理' },
      },
      {
        path: 'planning',
        name: 'Planning',
        component: () => import('@/views/planning/index.vue'),
        meta: { title: '计划管理' },
        children: [
          {
            path: 'mps',
            name: 'PlanningMps',
            component: () => import('@/views/planning/mps/index.vue'),
            meta: { title: '主生产计划 MPS' },
          },
          {
            path: 'mrp',
            name: 'PlanningMrp',
            component: () => import('@/views/planning/mrp/index.vue'),
            meta: { title: '物料需求计划 MRP' },
          },
          {
            path: 'work-plan',
            name: 'PlanningWorkPlan',
            component: () => import('@/views/planning/work-plan/index.vue'),
            meta: { title: '生产作业计划' },
          },
          {
            path: 'dispatch',
            name: 'PlanningDispatch',
            component: () => import('@/views/planning/dispatch/index.vue'),
            meta: { title: '派工单管理' },
          },
          {
            path: 'requisition',
            name: 'PlanningRequisition',
            component: () => import('@/views/planning/requisition/index.vue'),
            meta: { title: '领料单管理' },
          },
          {
            path: 'analysis',
            name: 'PlanningAnalysis',
            component: () => import('@/views/planning/analysis/index.vue'),
            meta: { title: '综合查询与统计分析' },
          },
        ],
      },
      {
        path: 'procurement',
        name: 'Procurement',
        component: () => import('@/views/procurement/index.vue'),
        meta: { title: '采购管理' },
      },
      {
        path: 'inventory',
        name: 'Inventory',
        component: () => import('@/views/inventory/index.vue'),
        meta: { title: '库存管理' },
      },
    ],
  },

  // ---------- 兜底 ----------
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/NotFound.vue'),
    meta: { title: '页面不存在' },
  },
]
