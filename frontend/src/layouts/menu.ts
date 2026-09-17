/**
 * 侧边栏菜单配置。
 *
 * 只列五个业务模块 + 工作台。新增菜单项请加在**自己模块的条目内部**，
 * 不要调整别人的顺序与命名。
 */

export interface MenuItem {
  /** 路由路径，与 router/routes.ts 中的路径保持一致 */
  path: string
  /** 菜单显示名称 */
  title: string
  /** 对应模块标识，工作台为空 */
  module?: string
  /** 子菜单（可选），如 planning 的功能树子项 */
  children?: Array<{ path: string; title: string }>
}

export const menuItems: MenuItem[] = [
  { path: '/dashboard', title: '工作台' },
  { path: '/system', title: '系统与基础信息管理', module: 'system' },
  { path: '/sales', title: '销售管理', module: 'sales' },
  {
    path: '/planning',
    title: '计划管理',
    module: 'planning',
    children: [
      { path: '/planning/mps', title: '主生产计划 MPS' },
      { path: '/planning/mrp', title: '物料需求计划 MRP' },
      { path: '/planning/work-plan', title: '生产作业计划' },
      { path: '/planning/dispatch', title: '派工单管理' },
      { path: '/planning/requisition', title: '领料单管理' },
      { path: '/planning/analysis', title: '综合查询与统计分析' },
    ],
  },
  { path: '/procurement', title: '采购管理', module: 'procurement' },
  { path: '/inventory', title: '库存管理', module: 'inventory' },
]
