import axios from 'axios'
import type { AxiosError, AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'

import { getCurrentOperatorId } from '@/composables/useCurrentOperator'
import type { ApiResponse } from '@/types/api'
import { SUCCESS_CODE } from '@/types/api'

/**
 * 全局 axios 实例。
 *
 * - baseURL 取 `VITE_API_BASE_URL`（默认 `/api/v1`）
 * - 开发环境由 `vite.config.ts` 的 proxy 转发到后端 http://127.0.0.1:8000
 * - 下方 `get/post/put/del` 会自动拆包统一响应 `{ code, message, data }`，
 *   业务代码直接拿到 `data`；`code !== 0` 时抛出 `Error(message)`
 */
const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** 把后端错误响应或网络错误统一转换成可读的错误信息 */
function toErrorMessage(error: AxiosError<ApiResponse<unknown>>): string {
  const body = error.response?.data

  if (
    body !== null &&
    body !== undefined &&
    typeof body === 'object' &&
    typeof body.message === 'string' &&
    body.message
  ) {
    return body.message
  }

  return error.response ? `请求失败（HTTP ${error.response.status}）` : error.message
}

/** 需要注入当前操作人的写操作方法 */
const WRITE_METHODS = new Set(['post', 'put', 'patch', 'delete'])

request.interceptors.request.use((config) => {
  // 过滤空串 / null / undefined 查询参数：空值表示“不参与过滤”，
  // 否则后端日期/枚举参数会把空串当作非法值返回 422。
  if (config.params !== null && typeof config.params === 'object') {
    const cleaned: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(config.params as Record<string, unknown>)) {
      if (value !== '' && value !== null && value !== undefined) {
        cleaned[key] = value
      }
    }
    config.params = cleaned
  }

  // 写操作统一注入当前操作人 `operator_id`：后端各模块的写接口都接受可选的
  // operator_id（用于填充 created_by / updated_by 与操作日志），缺失时审计字段会是 NULL。
  // params 与 body 两边都注入 —— 有的接口把它声明为 Query 参数
  // （如 `PATCH /sales/orders/{id}/status?operator_id=xx`），有的声明在请求体里
  // （如 `OrderCreate.operator_id`），前端无法逐接口区分；Pydantic 默认忽略未声明的
  // 额外字段，因此合并进 body 是安全的。
  const method = (config.method ?? 'get').toLowerCase()
  if (WRITE_METHODS.has(method)) {
    const operatorId = getCurrentOperatorId()
    // 未选择操作人时保持请求原样
    if (operatorId !== null) {
      config.params = {
        ...(config.params as Record<string, unknown> | undefined),
        operator_id: operatorId,
      }
      const data = config.data
      if (
        data !== null &&
        typeof data === 'object' &&
        !Array.isArray(data) &&
        !(data instanceof FormData)
      ) {
        config.data = { ...(data as Record<string, unknown>), operator_id: operatorId }
      }
    }
  }

  return config
})

request.interceptors.response.use(undefined, (error: AxiosError<ApiResponse<unknown>>) => {
  // 登录态失效：清除本地登录信息并跳回登录页，避免旧登录态卡在错误页面
  if (error.response?.status === 401) {
    localStorage.removeItem('bh-erp-user')
    if (!window.location.pathname.startsWith('/login')) {
      window.location.replace('/login')
    }
  }
  return Promise.reject(new Error(toErrorMessage(error)))
})

/** 拆包统一响应结构，返回业务数据 */
async function unwrap<T>(promise: Promise<AxiosResponse<ApiResponse<T>>>): Promise<T> {
  const response = await promise
  const body = response.data

  // 兼容未按统一规范返回的响应
  if (body === null || typeof body !== 'object' || !('code' in body)) {
    return body as unknown as T
  }

  if (body.code !== SUCCESS_CODE) {
    throw new Error(body.message || '请求失败')
  }

  return body.data
}

export function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  return unwrap<T>(request.get(url, { params }))
}

export function post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return unwrap<T>(request.post(url, data, config))
}

export function put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return unwrap<T>(request.put(url, data, config))
}

export function patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return unwrap<T>(request.patch(url, data, config))
}

export function del<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return unwrap<T>(request.delete(url, config))
}

export default request
