import { del, get, patch, post, put } from '@/utils/request'
import type { HealthData, PageData } from '@/types/api'
import type {
  OrderReportRow,
  PendingReceiptRow,
  PlanReportRow,
  ProcurementStats,
  PurchaseMaterial,
  PurchaseOrder,
  PurchasePlan,
  Receipt,
  ReceiptReportRow,
  Supplier,
  SupplierEvaluation,
  SupplierEvaluationSummary,
  SupplierMaterial,
} from '@/types/erp'

/**
 * procurement 模块接口（采购管理），统一前缀 /api/v1/procurement。
 *
 * 路径与后端 `app/modules/procurement/router.py` 一一对应，不使用任何本地假数据。
 */

export function getProcurementHealth(): Promise<HealthData> {
  return get<HealthData>('/procurement/health')
}

export function getProcurementStats(): Promise<ProcurementStats> {
  return get<ProcurementStats>('/procurement/stats')
}

// ---------------- 供应商 ----------------

export function listSuppliers(params: Record<string, unknown> = {}): Promise<PageData<Supplier>> {
  return get<PageData<Supplier>>('/procurement/suppliers', params)
}

export function createSupplier(payload: Record<string, unknown>): Promise<Supplier> {
  return post<Supplier>('/procurement/suppliers', payload)
}

export function getSupplier(id: number): Promise<Supplier> {
  return get<Supplier>(`/procurement/suppliers/${id}`)
}

export function updateSupplier(id: number, payload: Record<string, unknown>): Promise<Supplier> {
  return put<Supplier>(`/procurement/suppliers/${id}`, payload)
}

export function setSupplierStatus(id: number, status: string): Promise<Supplier> {
  return patch<Supplier>(`/procurement/suppliers/${id}/status`, { status })
}

// ---------------- 供应商-物料关系 ----------------

export function listSupplierMaterials(
  params: Record<string, unknown> = {},
): Promise<PageData<SupplierMaterial>> {
  return get<PageData<SupplierMaterial>>('/procurement/supplier-materials', params)
}

export function createSupplierMaterial(payload: Record<string, unknown>): Promise<SupplierMaterial> {
  return post<SupplierMaterial>('/procurement/supplier-materials', payload)
}

export function updateSupplierMaterial(
  id: number,
  payload: Record<string, unknown>,
): Promise<SupplierMaterial> {
  return put<SupplierMaterial>(`/procurement/supplier-materials/${id}`, payload)
}

export function deleteSupplierMaterial(id: number): Promise<unknown> {
  return del(`/procurement/supplier-materials/${id}`)
}

// ---------------- 可采购物料（只读 system 物料主数据） ----------------

export function listPurchaseMaterials(keyword?: string): Promise<PurchaseMaterial[]> {
  return get<PurchaseMaterial[]>('/procurement/materials', keyword ? { keyword } : undefined)
}

// ---------------- 采购计划 ----------------

export function listPurchasePlans(params: Record<string, unknown> = {}): Promise<PageData<PurchasePlan>> {
  return get<PageData<PurchasePlan>>('/procurement/purchase-plans', params)
}

export function createPurchasePlan(payload: Record<string, unknown>): Promise<PurchasePlan> {
  return post<PurchasePlan>('/procurement/purchase-plans', payload)
}

export function getPurchasePlan(id: number): Promise<PurchasePlan> {
  return get<PurchasePlan>(`/procurement/purchase-plans/${id}`)
}

export function updatePurchasePlan(id: number, payload: Record<string, unknown>): Promise<PurchasePlan> {
  return put<PurchasePlan>(`/procurement/purchase-plans/${id}`, payload)
}

export function deletePurchasePlan(id: number): Promise<unknown> {
  return del(`/procurement/purchase-plans/${id}`)
}

export function setPurchasePlanStatus(id: number, status: string): Promise<PurchasePlan> {
  return patch<PurchasePlan>(`/procurement/purchase-plans/${id}/status`, { status })
}

// ---------------- 采购订单 ----------------

export function listPurchaseOrders(params: Record<string, unknown> = {}): Promise<PageData<PurchaseOrder>> {
  return get<PageData<PurchaseOrder>>('/procurement/orders', params)
}

export function createPurchaseOrder(payload: Record<string, unknown>): Promise<PurchaseOrder> {
  return post<PurchaseOrder>('/procurement/orders', payload)
}

/** 由采购计划生成采购订单（单价取供应商供货价，并回写计划行已下单数量） */
export function createOrderFromPlan(payload: Record<string, unknown>): Promise<PurchaseOrder> {
  return post<PurchaseOrder>('/procurement/orders/from-plan', payload)
}

export function getPurchaseOrder(id: number): Promise<PurchaseOrder> {
  return get<PurchaseOrder>(`/procurement/orders/${id}`)
}

export function updatePurchaseOrder(id: number, payload: Record<string, unknown>): Promise<PurchaseOrder> {
  return put<PurchaseOrder>(`/procurement/orders/${id}`, payload)
}

export function deletePurchaseOrder(id: number): Promise<unknown> {
  return del(`/procurement/orders/${id}`)
}

export function setPurchaseOrderStatus(id: number, status: string): Promise<PurchaseOrder> {
  return patch<PurchaseOrder>(`/procurement/orders/${id}/status`, { status })
}

// ---------------- 到货管理 ----------------

export function listReceipts(params: Record<string, unknown> = {}): Promise<PageData<Receipt>> {
  return get<PageData<Receipt>>('/procurement/receipts', params)
}

export function createReceipt(payload: Record<string, unknown>): Promise<Receipt> {
  return post<Receipt>('/procurement/receipts', payload)
}

export function getReceipt(id: number): Promise<Receipt> {
  return get<Receipt>(`/procurement/receipts/${id}`)
}

export function confirmReceipt(id: number): Promise<Receipt> {
  return post<Receipt>(`/procurement/receipts/${id}/confirm`)
}

export function cancelReceipt(id: number): Promise<Receipt> {
  return post<Receipt>(`/procurement/receipts/${id}/cancel`)
}

// ---------------- 供应商评价 ----------------

export function listEvaluations(
  params: Record<string, unknown> = {},
): Promise<PageData<SupplierEvaluation>> {
  return get<PageData<SupplierEvaluation>>('/procurement/evaluations', params)
}

export function createEvaluation(payload: Record<string, unknown>): Promise<SupplierEvaluation> {
  return post<SupplierEvaluation>('/procurement/evaluations', payload)
}

/** 某供应商的全部评价记录 */
export function listEvaluationsBySupplier(supplierId: number): Promise<SupplierEvaluation[]> {
  return get<SupplierEvaluation[]>(`/procurement/evaluations/supplier/${supplierId}`)
}

export function deleteEvaluation(id: number): Promise<unknown> {
  return del(`/procurement/evaluations/${id}`)
}

// ---------------- 报表 ----------------

/** 采购计划执行报表 */
export function getPlanReport(): Promise<PlanReportRow[]> {
  return get<PlanReportRow[]>('/procurement/reports/plans')
}

/** 采购订单到货进度报表 */
export function getOrderReport(): Promise<OrderReportRow[]> {
  return get<OrderReportRow[]>('/procurement/reports/orders')
}

/** 到货记录报表（按到货日期区间） */
export function getReceiptReport(dateFrom: string, dateTo: string): Promise<ReceiptReportRow[]> {
  return get<ReceiptReportRow[]>('/procurement/reports/receipts', {
    date_from: dateFrom,
    date_to: dateTo,
  })
}

/** 未到货报表 */
export function getPendingReceiptReport(): Promise<PendingReceiptRow[]> {
  return get<PendingReceiptRow[]>('/procurement/reports/pending')
}

/** 供应商评分汇总报表 */
export function getSupplierEvaluationReport(): Promise<SupplierEvaluationSummary[]> {
  return get<SupplierEvaluationSummary[]>('/procurement/reports/supplier-evaluation')
}