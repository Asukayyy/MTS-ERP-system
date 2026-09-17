import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** 菜单与浏览器标题显示的名称 */
    title?: string
  }
}
