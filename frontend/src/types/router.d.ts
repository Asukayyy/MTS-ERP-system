import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** 菜单与浏览器标题显示的名称 */
    title?: string
    /**
     * 访问该页面所需的权限编码（对应后端 `sys_permission.perm_code`）。
     * 缺省表示登录即可访问；字符串或数组表示命中其中任意一个权限码才放行。
     */
    perm?: string | string[]
  }
}