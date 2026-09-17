/**
 * 与后端保持一致的基础类型。
 * 对应后端 `app/common/response.py` 与 `app/common/pagination.py`。
 */

/** 统一响应结构 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 统一分页结构 */
export interface PageData<T> {
  page: number
  page_size: number
  total: number
  items: T[]
}

/** 分页查询参数 */
export interface PageQuery {
  page?: number
  page_size?: number
}

/** 模块占位健康检查数据 */
export interface HealthData {
  module: string
  status: string
}

/** 成功状态码，与后端一致 */
export const SUCCESS_CODE = 0
