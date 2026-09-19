import { del, get, patch, post, put } from '@/utils/request'
import type { HealthData, PageData } from '@/types/api'
import type {
  Balance,
  FlowSummaryRow,
  InitialStockConfirm,
  InitialStockPreview,
  InventoryStats,
  Location,
  LowStock,
  ReorderRule,
  ReorderSuggestion,
  ReplenishmentRequest,
  StockChangeResult,
  StockSummary,
  Stocktake,
  Transaction,
  Transfer,
  Warehouse,
} from '@/types/erp'

/** inventory 模块接口（库存管理），统一前缀 /api/v1/inventory */

export function getInventoryHealth(): Promise<HealthData> {
  return get<HealthData>('/inventory/health')
}

export function getInventoryStats(): Promise<InventoryStats> {
  return get<InventoryStats>('/inventory/stats')
}

// ---------------- 仓库 / 库位 ----------------

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

export function listLocations(params: Record<string, unknown> = {}): Promise<PageData<Location>> {
  return get<PageData<Location>>('/inventory/locations', params)
}

export function createLocation(payload: Record<string, unknown>): Promise<Location> {
  return post<Location>('/inventory/locations', payload)
}

export function updateLocation(id: number, payload: Record<string, unknown>): Promise<Location> {
  return put<Location>(`/inventory/locations/${id}`, payload)
}

export function deleteLocation(id: number): Promise<unknown> {
  return del(`/inventory/locations/${id}`)
}

export function setLocationStatus(id: number, status: string): Promise<Location> {
  return patch<Location>(`/inventory/locations/${id}/status`, { status })
}

// ---------------- 实时库存 / 流水 ----------------

export function listBalances(params: Record<string, unknown> = {}): Promise<PageData<Balance>> {
  return get<PageData<Balance>>('/inventory/balances', params)
}

export function listTransactions(params: Record<string, unknown> = {}): Promise<PageData<Transaction>> {
  return get<PageData<Transaction>>('/inventory/transactions', params)
}

// ---------------- 手工入 / 出库 ----------------

export function stockIncrease(payload: Record<string, unknown>): Promise<StockChangeResult> {
  return post<StockChangeResult>('/inventory/stock/increase', payload)
}

export function stockDecrease(payload: Record<string, unknown>): Promise<StockChangeResult> {
  return post<StockChangeResult>('/inventory/stock/decrease', payload)
}

// ---------------- 移库 ----------------

export function listTransfers(params: Record<string, unknown> = {}): Promise<PageData<Transfer>> {
  return get<PageData<Transfer>>('/inventory/transfers', params)
}

export function createTransfer(payload: Record<string, unknown>): Promise<Transfer> {
  return post<Transfer>('/inventory/transfers', payload)
}

export function confirmTransfer(id: number, operatorId?: number): Promise<Transfer> {
  return post<Transfer>(`/inventory/transfers/${id}/confirm`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

export function cancelTransfer(id: number, operatorId?: number): Promise<Transfer> {
  return post<Transfer>(`/inventory/transfers/${id}/cancel`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

// ---------------- 盘点 ----------------

export function listStocktakes(params: Record<string, unknown> = {}): Promise<PageData<Stocktake>> {
  return get<PageData<Stocktake>>('/inventory/stocktakes', params)
}

export function createStocktake(payload: Record<string, unknown>): Promise<Stocktake> {
  return post<Stocktake>('/inventory/stocktakes', payload)
}

export function confirmStocktake(id: number, operatorId?: number): Promise<Stocktake> {
  return post<Stocktake>(`/inventory/stocktakes/${id}/confirm`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

export function cancelStocktake(id: number, operatorId?: number): Promise<Stocktake> {
  return post<Stocktake>(`/inventory/stocktakes/${id}/cancel`, undefined, {
    params: operatorId ? { operator_id: operatorId } : undefined,
  })
}

// ---------------- 订货点 ----------------

export function listReorderRules(params: Record<string, unknown> = {}): Promise<PageData<ReorderRule>> {
  return get<PageData<ReorderRule>>('/inventory/reorder-rules', params)
}

export function listReorderSuggestions(): Promise<ReorderSuggestion[]> {
  return get<ReorderSuggestion[]>('/inventory/reorder-rules/suggestions')
}

export function createReorderRule(payload: Record<string, unknown>): Promise<ReorderRule> {
  return post<ReorderRule>('/inventory/reorder-rules', payload)
}

export function updateReorderRule(id: number, payload: Record<string, unknown>): Promise<ReorderRule> {
  return put<ReorderRule>(`/inventory/reorder-rules/${id}`, payload)
}

export function setReorderRuleStatus(id: number, status: string): Promise<ReorderRule> {
  return patch<ReorderRule>(`/inventory/reorder-rules/${id}/status`, { status })
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

export function getFlowSummary(params: {
  date_from: string
  date_to: string
}): Promise<FlowSummaryRow[]> {
  return get<FlowSummaryRow[]>('/inventory/reports/flow-summary', params)
}

// ---------------- 课程数据导入（规格 §37） ----------------

/** 期初库存导入入参：可显式给 rows，也可只给 source 由服务端读取课程数据文件 */
export interface InitialStockImportPayload {
  source?: string
  warehouse_id?: number
  warehouse_code?: string
  location_id?: number
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