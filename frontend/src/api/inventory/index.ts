import { get, patch, post, put } from '@/utils/request'
import type { PageData } from '@/types/api'
import type {
  Balance,
  BalanceSummary,
  InitialStockConfirm,
  InitialStockPreview,
  InventoryStats,
  LowStock,
  ReorderSuggestion,
  ReplenishmentRequest,
  SafetyStockSuggestion,
  StockChangeResult,
  StockJournal,
  StockOperation,
  StockSummary,
  StocktakeSummary,
  Warehouse,
} from '@/types/erp'

/** inventory 模块接口（库存管理），统一前缀 /api/v1/inventory */

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

/** 实时库存按销售类别（整机 / 可售备件 / 内部件）汇总 */
export function getBalanceSummary(
  params: Record<string, unknown> = {},
): Promise<BalanceSummary[]> {
  return get<BalanceSummary[]>('/inventory/balances/summary', params)
}

// ---------------- 实时库存 ----------------

export function stockIncrease(payload: Record<string, unknown>): Promise<StockChangeResult> {
  return post<StockChangeResult>('/inventory/stock/increase', payload)
}

export function stockDecrease(payload: Record<string, unknown>): Promise<StockChangeResult> {
  return post<StockChangeResult>('/inventory/stock/decrease', payload)
}

// ---------------- 库存操作单（移库 / 盘点共用） ----------------

/** op_type：TRANSFER 移库 / STOCKTAKE 盘点 / INBOUND 入库 / OUTBOUND 出库 */
export function listStockOperations(
  params: Record<string, unknown> = {},
): Promise<PageData<StockOperation>> {
  return get<PageData<StockOperation>>('/inventory/stock-operations', params)
}

export function createStockOperation(payload: Record<string, unknown>): Promise<StockOperation> {
  return post<StockOperation>('/inventory/stock-operations', payload)
}

/** 确认库存单据：INBOUND / OUTBOUND 由仓库管理人员在此指定仓库 */
export function confirmStockOperation(
  id: number,
  options: { operator_id?: number; warehouse_id?: number } = {},
): Promise<StockOperation> {
  const { operator_id: operatorId, warehouse_id: warehouseId } = options
  return post<StockOperation>(
    `/inventory/stock-operations/${id}/confirm`,
    { warehouse_id: warehouseId ?? null },
    { params: operatorId ? { operator_id: operatorId } : undefined },
  )
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

/** 按安全库存批量生成补库需求（BUY→采购补库，MAKE→生产补库） */
export function generateFromSafetyStock(): Promise<{
  created_count: number
  request_ids: number[]
  skipped_count: number
}> {
  return post<{ created_count: number; request_ids: number[]; skipped_count: number }>(
    '/inventory/replenishment-requests/generate-from-safety-stock',
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

/** 安全库存补库建议（可用量低于安全库存的物料） */
export function getSafetyStockSuggestions(): Promise<SafetyStockSuggestion[]> {
  return get<SafetyStockSuggestion[]>('/inventory/reports/safety-stock-suggestions')
}

/** 盘点汇总（盘盈盘亏），只统计已确认盘点单 */
export function getStocktakeSummary(params: Record<string, unknown> = {}): Promise<StocktakeSummary> {
  return get<StocktakeSummary>('/inventory/reports/stocktake-summary', params)
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

/** 库存变动流水列表 */
export function listStockJournal(
  params: Record<string, unknown> = {},
): Promise<PageData<StockJournal>> {
  return get<PageData<StockJournal>>('/inventory/stock-journal', params)
}
