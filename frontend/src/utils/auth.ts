import type { LoginResult } from '@/types/erp'

/** 登录结果在 localStorage 中的键（与既有代码保持一致） */
export const AUTH_STORAGE_KEY = 'bh-erp-user'

/** 权限码集合缓存，避免每次路由跳转 / 菜单渲染都重新解析 JSON */
let permissionCache: Set<string> | null = null

/** 读取登录结果，未登录或数据损坏时返回 null */
export function getAuth(): LoginResult | null {
  const raw = localStorage.getItem(AUTH_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as LoginResult
  } catch {
    return null
  }
}

/** 登录成功后写入登录结果（含凭证与权限码） */
export function saveAuth(result: LoginResult): void {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(result))
  permissionCache = null
}

/** 退出登录 / 登录态失效时清除本地登录结果 */
export function clearAuth(): void {
  localStorage.removeItem(AUTH_STORAGE_KEY)
  permissionCache = null
}

export function isLoggedIn(): boolean {
  return getAuth() !== null
}

/** 当前登录凭证，供 axios 请求头使用；未登录返回空串 */
export function getToken(): string {
  return getAuth()?.token ?? ''
}

/** 当前账号持有的权限编码集合 */
export function getPermCodes(): Set<string> {
  if (permissionCache === null) {
    permissionCache = new Set((getAuth()?.permissions ?? []).map((item) => item.perm_code))
  }
  return permissionCache
}

/**
 * 是否持有指定权限。
 *
 * - `perm` 为空（页面不限制权限）→ 放行；
 * - `perm` 为字符串 → 命中该权限编码即放行；
 * - `perm` 为数组 → 命中任意一个即放行（与后端「任意一个权限」语义一致）。
 */
export function hasPermission(perm?: string | string[]): boolean {
  if (!perm || (Array.isArray(perm) && perm.length === 0)) return true
  const owned = getPermCodes()
  const required = Array.isArray(perm) ? perm : [perm]
  return required.some((code) => owned.has(code))
}