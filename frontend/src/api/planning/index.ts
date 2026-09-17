import type { HealthData } from '@/types/api'
import { get } from '@/utils/request'

/**
 * planning 模块接口（计划管理，含 MPS / MRP / 生产作业计划）。
 *
 * 当前只有占位健康检查，业务接口由本模块负责人在本文件内继续添加。
 */

/** 占位健康检查，用于验证前后端连通性 */
export function getPlanningHealth(): Promise<HealthData> {
  return get<HealthData>('/planning/health')
}
