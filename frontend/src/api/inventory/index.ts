import type { HealthData } from '@/types/api'
import { get } from '@/utils/request'

/**
 * inventory 模块接口（库存管理）。
 *
 * 当前只有占位健康检查，业务接口由本模块负责人在本文件内继续添加。
 */

/** 占位健康检查，用于验证前后端连通性 */
export function getInventoryHealth(): Promise<HealthData> {
  return get<HealthData>('/inventory/health')
}
