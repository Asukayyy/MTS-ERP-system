import { get, patch, post, put } from '@/utils/request'
import type { HealthData, PageData } from '@/types/api'
import type {
  Balance,
  InitialStockConfirm,
  InitialStockPreview,
  InventoryStats,
  LowStock,
  ReorderSuggestion,
  ReplenishmentRequest,
  StockChangeResult,
  StockOperation,
  StockSummary,
  Warehouse,
} from '@/types/erp'

/** inventory 模块接口（库存管理），统一前缀 /api/v1/inventory */

export function getInventoryHealth(): Promise<HealthData> {
  return get<HealthData>('/inventory/health')
}

export function getInventoryStats(): Promise<InventoryStats> {
  return get<InventoryStats>('/inventory/stats')
}

// ---------------- 仓库（库位字段并入仓库表） ----------------

export function listWarehouses(params: Record<string, unknown> = {}): Promise<PageData<Warehouse>> {
  return get<PageData<Warehouse>>('/inventory/warehouses', params)
}

export function createWarehouse(payload: Record<string, unknown>): Promise<Warehouse> {
  return post<Warehouse>('/inventory/warehouses', payload)
}

export function updateWarehouse(id: number, payload: Record<string, unknown>): Promise<Warehouse> {
  return put<Warehouse>(`/inventory/warehouses/${id}`, payload)
}

export function setWarehouseStatus(id: number, status: string): Promise<Warehouse> {
  return patch<Warehouse>(`/inventory/warehouses/${id}/status`, { status })
}

// ---------------- 实时库存 / 流水 ----------------

export function listBalances(params: Record<string, unknown> = {}): Promise<PageData<Balance>> {
  return get<PageData<Balance>>('/inventory/balances', params)
}

// ---------------- 实时库存 ----------------

export function stockIncrease(payload: Record<string, unknown>): Promise<StockChangeResult> {
  return post<StockChangeResult>('/inventory/stock/increase', payload)
}

export function stockDecrease(payload: Record<string, unknown>): Promise<StockChangeResult> {
  return post<StockChangeResult>('/inventory/stock/decrease', payload)
}

// ---------------- 库存操作单（移库 / 盘点共用） ----------------

/** op_type：TRANSFER 移库 / STOCKTAKE 盘点 */
export function listStockOperations(
  params: Record<string, unknown> = {},
): Promise<PageData<StockOperation>> {
  return get<PageData<StockOperation>>('/inventory/stock-operations', params)
}

export function createStockOperation(payload: Record<string, unknown>): Promise<StockOperation> {
  return post<StockOperation>('/inventory/stock-operations', payload)
}

export function confirmStockOperation(id: number, operatorId?: number): Promise<StockOperation> {
  return post<StockOperation>(`/inventory/stock-operations/${id}/confirm`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

export function cancelStockOperation(id: number, operatorId?: number): Promise<StockOperation> {
  return post<StockOperation>(`/inventory/stock-operations/${id}/cancel`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

// ---------------- 订货点（直接维护在结存行上） ----------------

/** 更新结存的订货点 / 建议订货量 */
export function updateBalanceReorder(
  balanceId: number,
  payload: { reorder_point: number | string; reorder_quantity: number | string; operator_id?: number },
): Promise<Balance> {
  return patch<Balance>(`/inventory/balances/${balanceId}/reorder`, payload)
}

/** 补库建议：现存量低于订货点的结存行 */
export function listReorderSuggestions(): Promise<ReorderSuggestion[]> {
  return get<ReorderSuggestion[]>('/inventory/balances/reorder-suggestions')
}

// ---------------- 补库需求 ----------------

export function listReplenishmentRequests(
  params: Record<string, unknown> = {},
): Promise<PageData<ReplenishmentRequest>> {
  return get<PageData<ReplenishmentRequest>>('/inventory/replenishment-requests', params)
}

export function createReplenishmentRequest(
  payload: Record<string, unknown>,
): Promise<ReplenishmentRequest> {
  return post<ReplenishmentRequest>('/inventory/replenishment-requests', payload)
}

export function generateFromReorderRules(): Promise<{
  created_count: number
  request_ids: number[]
  skipped_count: number
}> {
  return post<{ created_count: number; request_ids: number[]; skipped_count: number }>(
    '/inventory/replenishment-requests/generate-from-reorder-rules',
  )
}

export function confirmReplenishmentRequest(
  id: number,
  operatorId?: number,
): Promise<ReplenishmentRequest> {
  return post<ReplenishmentRequest>(`/inventory/replenishment-requests/${id}/confirm`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

export function cancelReplenishmentRequest(
  id: number,
  operatorId?: number,
): Promise<ReplenishmentRequest> {
  return post<ReplenishmentRequest>(`/inventory/replenishment-requests/${id}/cancel`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

// ---------------- 报表 ----------------

export function getStockSummary(params: Record<string, unknown> = {}): Promise<StockSummary[]> {
  return get<StockSummary[]>('/inventory/reports/stock-summary', params)
}

export function getLowStockReport(): Promise<LowStock[]> {
  return get<LowStock[]>('/inventory/reports/low-stock')
}

// ---------------- 课程数据导入（规格 §37） ----------------

/** 期初库存导入入参：可显式给 rows，也可只给 source 由服务端读取课程数据文件 */
export interface InitialStockImportPayload {
  source?: string
  warehouse_id?: number
  warehouse_code?: string
  rows?: Array<{ material_code: string; quantity: number | string }>
  operator_id?: number
}

/** 期初库存导入预览：只校验不写库 */
export function previewInitialStockImport(
  payload: InitialStockImportPayload,
): Promise<InitialStockPreview> {
  return post<InitialStockPreview>('/inventory/import/initial-stock/preview', payload)
}

/** 期初库存导入确认：逐行走入库并写真实流水 */
export function confirmInitialStockImport(
  payload: InitialStockImportPayload,
): Promise<InitialStockConfirm> {
  return post<InitialStockConfirm>('/inventory/import/initial-stock/confirm', payload)
}
