/**
 * 侧边栏菜单配置（规格 §26 导航树）。
 *
 * 路径需与 `router/routes.ts` 中的子路由保持一致。
 */

export interface MenuItem {
  /** 路由路径 */
  path: string
  /** 菜单显示名称 */
  title: string
  /** 对应模块标识，工作台为空 */
  module?: string
  /** 二级菜单 */
  children?: Array<{ path: string; title: string }>
}

export const menuItems: MenuItem[] = [
  { path: '/dashboard', title: '工作台' },
  {
    path: '/system/basic',
    title: '基础信息',
    module: 'system',
    children: [
      { path: '/system/material', title: '物料管理' },
      { path: '/system/bom', title: 'BOM管理' },
      { path: '/system/routing', title: '工艺路线' },
    ],
  },
  {
    path: '/sales',
    title: '销售管理',
    module: 'sales',
    children: [
      { path: '/sales/customer', title: '客户' },
      { path: '/sales/forecast', title: '销售预测' },
      { path: '/sales/order', title: '销售订单' },
      { path: '/sales/shipment', title: '发货管理' },
      { path: '/sales/return', title: '退货管理' },
    ],
  },
  {
    path: '/planning',
    title: '计划管理',
    module: 'planning',
    children: [
      { path: '/planning/demand', title: '需求管理' },
      { path: '/planning/mps', title: 'MPS' },
      { path: '/planning/mrp', title: 'MRP' },
      { path: '/planning/work-plan', title: '生产作业计划' },
      { path: '/planning/dispatch', title: '派工单' },
      { path: '/planning/requisition', title: '领料单' },
      { path: '/planning/completion', title: '完工报告' },
    ],
  },
  {
    path: '/procurement',
    title: '采购管理',
    module: 'procurement',
    children: [
      { path: '/procurement/supplier', title: '供应商' },
      { path: '/procurement/supplier-material', title: '供应商-物料关系' },
      { path: '/procurement/plan', title: '采购计划' },
      { path: '/procurement/order', title: '采购订单' },
      { path: '/procurement/receipt', title: '到货管理' },
      { path: '/procurement/evaluation', title: '供应商评价' },
      { path: '/procurement/report', title: '采购报表' },
    ],
  },
  {
    path: '/inventory',
    title: '库存管理',
    module: 'inventory',
    children: [
      { path: '/inventory/balance', title: '实时库存' },
      { path: '/inventory/inbound', title: '入库' },
      { path: '/inventory/outbound', title: '出库' },
      { path: '/inventory/transfer', title: '移库' },
      { path: '/inventory/stocktake', title: '盘点' },
      { path: '/inventory/transaction', title: '库存流水' },
      { path: '/inventory/reorder', title: '订货点' },
      { path: '/inventory/replenishment', title: '补库需求' },
    ],
  },
  {
    path: '/system/manage',
    title: '系统管理',
    module: 'system',
    children: [
      { path: '/system/organization', title: '组织机构' },
      { path: '/system/personnel', title: '员工' },
      { path: '/system/user', title: '用户' },
      { path: '/system/role', title: '角色' },
      { path: '/system/permission', title: '权限' },
      { path: '/system/dictionary', title: '公共字典' },
      { path: '/system/log', title: '操作日志' },
      { path: '/system/course-import', title: '课程数据导入' },
    ],
  },
]