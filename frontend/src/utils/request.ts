import axios from 'axios'
import type { AxiosError, AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'

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

request.interceptors.response.use(undefined, (error: AxiosError<ApiResponse<unknown>>) =>
  Promise.reject(new Error(toErrorMessage(error))),
)

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

export function del<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return unwrap<T>(request.delete(url, config))
}

export default request
