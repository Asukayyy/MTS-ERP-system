import type { RouteRecordRaw } from 'vue-router'

/**
 * 路由表。
 *
 * 页面统一作为主布局的直接子路由（扁平结构，URL 形如 `/system/material`），
 * 侧边栏通过 `layouts/menu.ts` 组织二级分组，避免中间层空组件。
 */
export const constantRoutes: RouteRecordRaw[] = [
  // ---------- 登录前 ----------
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/register/index.vue'),
    meta: { title: '注册' },
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

      // ---------- 基础信息 ----------
      {
        path: 'system/material',
        name: 'SystemMaterial',
        component: () => import('@/views/system/material/index.vue'),
        meta: { title: '物料管理' },
      },
      {
        path: 'system/bom',
        name: 'SystemBom',
        component: () => import('@/views/system/bom/index.vue'),
        meta: { title: 'BOM管理' },
      },
      {
        path: 'system/routing',
        name: 'SystemRouting',
        component: () => import('@/views/system/routing/index.vue'),
        meta: { title: '工艺路线' },
      },

      // ---------- 销售管理 ----------
      {
        path: 'sales/customer',
        name: 'SalesCustomer',
        component: () => import('@/views/sales/customer/index.vue'),
        meta: { title: '客户' },
      },
      {
        path: 'sales/forecast',
        name: 'SalesForecast',
        component: () => import('@/views/sales/forecast/index.vue'),
        meta: { title: '销售预测' },
      },
      {
        path: 'sales/order',
        name: 'SalesOrder',
        component: () => import('@/views/sales/order/index.vue'),
        meta: { title: '销售订单' },
      },
      {
        path: 'sales/shipment',
        name: 'SalesShipment',
        component: () => import('@/views/sales/shipment/index.vue'),
        meta: { title: '发货管理' },
      },
      {
        path: 'sales/return',
        name: 'SalesReturn',
        component: () => import('@/views/sales/return/index.vue'),
        meta: { title: '退货管理' },
      },

      // ---------- 计划管理 ----------
      {
        path: 'planning/demand',
        name: 'PlanningDemand',
        component: () => import('@/views/planning/demand/index.vue'),
        meta: { title: '需求管理' },
      },
      {
        path: 'planning/mps',
        name: 'PlanningMps',
        component: () => import('@/views/planning/mps/index.vue'),
        meta: { title: '主生产计划 MPS' },
      },
      {
        path: 'planning/mrp',
        name: 'PlanningMrp',
        component: () => import('@/views/planning/mrp/index.vue'),
        meta: { title: '物料需求计划 MRP' },
      },
      {
        path: 'planning/work-plan',
        name: 'PlanningWorkPlan',
        component: () => import('@/views/planning/work-plan/index.vue'),
        meta: { title: '生产作业计划' },
      },
      {
        path: 'planning/dispatch',
        name: 'PlanningDispatch',
        component: () => import('@/views/planning/dispatch/index.vue'),
        meta: { title: '派工单' },
      },
      {
        path: 'planning/requisition',
        name: 'PlanningRequisition',
        component: () => import('@/views/planning/requisition/index.vue'),
        meta: { title: '领料单' },
      },
      {
        path: 'planning/completion',
        name: 'PlanningCompletion',
        component: () => import('@/views/planning/completion/index.vue'),
        meta: { title: '完工报告' },
      },

      // ---------- 采购管理 ----------
      {
        path: 'procurement/supplier',
        name: 'ProcurementSupplier',
        component: () => import('@/views/procurement/supplier/index.vue'),
        meta: { title: '供应商' },
      },
      {
        path: 'procurement/supplier-material',
        name: 'ProcurementSupplierMaterial',
        component: () => import('@/views/procurement/supplier-material/index.vue'),
        meta: { title: '供应商-物料关系' },
      },
      {
        path: 'procurement/plan',
        name: 'ProcurementPlan',
        component: () => import('@/views/procurement/plan/index.vue'),
        meta: { title: '采购计划' },
      },
      {
        path: 'procurement/order',
        name: 'ProcurementOrder',
        component: () => import('@/views/procurement/order/index.vue'),
        meta: { title: '采购订单' },
      },
      {
        path: 'procurement/receipt',
        name: 'ProcurementReceipt',
        component: () => import('@/views/procurement/receipt/index.vue'),
        meta: { title: '到货管理' },
      },
      {
        path: 'procurement/evaluation',
        name: 'ProcurementEvaluation',
        component: () => import('@/views/procurement/evaluation/index.vue'),
        meta: { title: '供应商评价' },
      },
      {
        path: 'procurement/report',
        name: 'ProcurementReport',
        component: () => import('@/views/procurement/report/index.vue'),
        meta: { title: '采购报表' },
      },

      // ---------- 库存管理 ----------
      {
        path: 'inventory/balance',
        name: 'InventoryBalance',
        component: () => import('@/views/inventory/balance/index.vue'),
        meta: { title: '实时库存' },
      },
      {
        path: 'inventory/inbound',
        name: 'InventoryInbound',
        component: () => import('@/views/inventory/inbound/index.vue'),
        meta: { title: '入库' },
      },
      {
        path: 'inventory/outbound',
        name: 'InventoryOutbound',
        component: () => import('@/views/inventory/outbound/index.vue'),
        meta: { title: '出库' },
      },
      {
        path: 'inventory/transfer',
        name: 'InventoryTransfer',
        component: () => import('@/views/inventory/transfer/index.vue'),
        meta: { title: '移库' },
      },
      {
        path: 'inventory/stocktake',
        name: 'InventoryStocktake',
        component: () => import('@/views/inventory/stocktake/index.vue'),
        meta: { title: '盘点' },
      },
      {
        path: 'inventory/transaction',
        name: 'InventoryTransaction',
        component: () => import('@/views/inventory/transaction/index.vue'),
        meta: { title: '库存流水' },
      },
      {
        path: 'inventory/reorder',
        name: 'InventoryReorder',
        component: () => import('@/views/inventory/reorder/index.vue'),
        meta: { title: '订货点' },
      },
      {
        path: 'inventory/replenishment',
        name: 'InventoryReplenishment',
        component: () => import('@/views/inventory/replenishment/index.vue'),
        meta: { title: '补库需求' },
      },

      // ---------- 系统管理 ----------
      {
        path: 'system/organization',
        name: 'SystemOrganization',
        component: () => import('@/views/system/organization/index.vue'),
        meta: { title: '组织机构' },
      },
      {
        path: 'system/personnel',
        name: 'SystemPersonnel',
        component: () => import('@/views/system/personnel/index.vue'),
        meta: { title: '员工' },
      },
      {
        path: 'system/user',
        name: 'SystemUser',
        component: () => import('@/views/system/user/index.vue'),
        meta: { title: '用户' },
      },
      {
        path: 'system/role',
        name: 'SystemRole',
        component: () => import('@/views/system/role/index.vue'),
        meta: { title: '角色' },
      },
      {
        path: 'system/permission',
        name: 'SystemPermission',
        component: () => import('@/views/system/permission/index.vue'),
        meta: { title: '权限' },
      },
      {
        path: 'system/dictionary',
        name: 'SystemDictionary',
        component: () => import('@/views/system/dictionary/index.vue'),
        meta: { title: '公共字典' },
      },
      {
        path: 'system/log',
        name: 'SystemLog',
        component: () => import('@/views/system/log/index.vue'),
        meta: { title: '操作日志' },
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