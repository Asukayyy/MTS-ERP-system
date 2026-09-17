import type { HealthData } from '@/types/api'
import { get } from '@/utils/request'

/**
 * system 模块接口（系统与基础信息管理）。
 *
 * 当前只有占位健康检查，业务接口由本模块负责人在本文件内继续添加。
 * 每个业务实体建议单独一个文件，例如 `api/system/product.ts`。
 */

/** 占位健康检查，用于验证前后端连通性 */
export function getSystemHealth(): Promise<HealthData> {
  return get<HealthData>('/system/health')
}
