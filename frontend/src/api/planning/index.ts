import { del, get, patch, post, put } from '@/utils/request'
import type { PageData } from '@/types/api'
import type {
  BatchDeleteResult,
  CompletionReport,
  Demand,
  DispatchOrder,
  GenerationResult,
  Mps,
  MpsImportPreview,
  MrpExplain,
  MrpResult,
  MrpRun,
  PlanningStats,
  ProductionPlan,
  Requisition,
} from '@/types/erp'

/** planning 模块接口（计划管理），统一前缀 /api/v1/planning */

export function getPlanningStats(): Promise<PlanningStats> {
  return get<PlanningStats>('/planning/stats')
}

// ---------------- 需求 ----------------

export function listDemands(params: Record<string, unknown> = {}): Promise<PageData<Demand>> {
  return get<PageData<Demand>>('/planning/demands', params)
}

export function createDemand(payload: Record<string, unknown>): Promise<Demand> {
  return post<Demand>('/planning/demands', payload)
}

export function setDemandStatus(id: number, status: string): Promise<Demand> {
  return patch<Demand>(`/planning/demands/${id}/status`, { status })
}

/** 从已确认销售订单导入计划需求 */
export function importDemandsFromSales(): Promise<{
  created_count: number
  skipped_count: number
  demand_ids: number[]
}> {
  return post<{ created_count: number; skipped_count: number; demand_ids: number[] }>(
    '/planning/demands/from-sales',
  )
}

/** 由库存补库需求生成计划需求 */
export function createDemandFromReplenishment(requestId: number): Promise<Demand> {
  return post<Demand>('/planning/demands/from-replenishment', { request_id: requestId })
}

/** 从库存补库需求批量导入计划需求 */
export function importDemandsFromReplenishment(): Promise<{
  created_count: number
  skipped_count: number
  demand_ids: number[]
}> {
  return post<{ created_count: number; skipped_count: number; demand_ids: number[] }>(
    '/planning/demands/from-replenishment/import',
  )
}

// ---------------- MPS ----------------

export function listMps(params: Record<string, unknown> = {}): Promise<PageData<Mps>> {
  return get<PageData<Mps>>('/planning/mps', params)
}

export function getMps(id: number): Promise<Mps> {
  return get<Mps>(`/planning/mps/${id}`)
}

export function createMps(payload: Record<string, unknown>): Promise<Mps> {
  return post<Mps>('/planning/mps', payload)
}

export function updateMps(id: number, payload: Record<string, unknown>): Promise<Mps> {
  return put<Mps>(`/planning/mps/${id}`, payload)
}

export function deleteMps(id: number): Promise<unknown> {
  return del(`/planning/mps/${id}`)
}

export function setMpsStatus(id: number, status: string): Promise<Mps> {
  return patch<Mps>(`/planning/mps/${id}/status`, { status })
}

/** 课程附录 1：MPS 导入预览（不落库） */
export function previewMpsImport(payload: Record<string, unknown>): Promise<MpsImportPreview> {
  return post<MpsImportPreview>('/planning/mps/import/preview', payload)
}

/** 课程附录 1：MPS 导入确认（写入 MPS 头 + 行） */
export function confirmMpsImport(payload: Record<string, unknown>): Promise<Mps> {
  return post<Mps>('/planning/mps/import/confirm', payload)
}

// ---------------- MRP ----------------

export function runMrp(payload: Record<string, unknown>): Promise<MrpRun> {
  return post<MrpRun>('/planning/mrp/run', payload)
}

export function listMrpRuns(params: Record<string, unknown> = {}): Promise<PageData<MrpRun>> {
  return get<PageData<MrpRun>>('/planning/mrp/runs', params)
}

export function getMrpRun(runId: number): Promise<MrpRun> {
  return get<MrpRun>(`/planning/mrp/runs/${runId}`)
}

export function listMrpResults(params: Record<string, unknown> = {}): Promise<PageData<MrpResult>> {
  return get<PageData<MrpResult>>('/planning/mrp/results', params)
}

export function explainMrpResult(runId: number, materialId: number): Promise<MrpExplain> {
  return get<MrpExplain>(`/planning/mrp/runs/${runId}/explain`, { material_id: materialId })
}

export function setMrpResultStatus(id: number, status: string): Promise<MrpResult> {
  return patch<MrpResult>(`/planning/mrp/results/${id}/status`, { status })
}

/** 由 MRP 批次生成采购计划（BUY 结果） */
export function createPurchasePlanFromRun(runId: number): Promise<Record<string, unknown>> {
  return post<Record<string, unknown>>(`/planning/mrp/runs/${runId}/create-purchase-plan`)
}

/** 由 MRP 批次生成生产作业计划（MAKE 结果） */
export function createProductionPlansFromRun(runId: number): Promise<ProductionPlan[]> {
  return post<ProductionPlan[]>(`/planning/mrp/runs/${runId}/create-production-plans`)
}

// ---------------- 生产作业计划 ----------------

export function listProductionPlans(params: Record<string, unknown> = {}): Promise<PageData<ProductionPlan>> {
  return get<PageData<ProductionPlan>>('/planning/production-plans', params)
}

export function createProductionPlan(payload: Record<string, unknown>): Promise<ProductionPlan> {
  return post<ProductionPlan>('/planning/production-plans', payload)
}

export function createProductionPlansFromMrp(mrpResultIds: number[]): Promise<ProductionPlan[]> {
  return post<ProductionPlan[]>('/planning/production-plans/from-mrp', { mrp_result_ids: mrpResultIds })
}

export function updateProductionPlan(id: number, payload: Record<string, unknown>): Promise<ProductionPlan> {
  return put<ProductionPlan>(`/planning/production-plans/${id}`, payload)
}

export function setProductionPlanStatus(id: number, status: string): Promise<ProductionPlan> {
  return patch<ProductionPlan>(`/planning/production-plans/${id}/status`, { status })
}

/** 删除生产作业计划（仅草稿 / 已取消，且须先删除其下游单据） */
export function deleteProductionPlan(id: number): Promise<unknown> {
  return del(`/planning/production-plans/${id}`)
}

/** 批量删除生产作业计划 */
export function batchDeleteProductionPlans(ids: number[]): Promise<BatchDeleteResult> {
  return post<BatchDeleteResult>('/planning/production-plans/batch-delete', { ids })
}

// ---------------- 派工单 ----------------

export function listDispatchOrders(params: Record<string, unknown> = {}): Promise<PageData<DispatchOrder>> {
  return get<PageData<DispatchOrder>>('/planning/dispatch-orders', params)
}

export function createDispatchOrder(payload: Record<string, unknown>): Promise<DispatchOrder> {
  return post<DispatchOrder>('/planning/dispatch-orders', payload)
}

export function setDispatchOrderStatus(id: number, status: string): Promise<DispatchOrder> {
  return patch<DispatchOrder>(`/planning/dispatch-orders/${id}/status`, { status })
}

/** 人工审核调整派工单（仅 DRAFT 可改） */
export function updateDispatchOrder(id: number, payload: Record<string, unknown>): Promise<DispatchOrder> {
  return patch<DispatchOrder>(`/planning/dispatch-orders/${id}`, payload)
}

/** 按选中的生产作业计划逐工序生成派工单 */
export function generateDispatchOrdersFromPlans(
  planIds: number[],
): Promise<GenerationResult> {
  return post<GenerationResult>('/planning/dispatch-orders/from-plans', { plan_ids: planIds })
}

/** 删除派工单（仅草稿 / 已取消，且须先删除引用它的完工报告） */
export function deleteDispatchOrder(id: number): Promise<unknown> {
  return del(`/planning/dispatch-orders/${id}`)
}

/** 批量删除派工单 */
export function batchDeleteDispatchOrders(ids: number[]): Promise<BatchDeleteResult> {
  return post<BatchDeleteResult>('/planning/dispatch-orders/batch-delete', { ids })
}

// ---------------- 领料单 ----------------

export function listRequisitions(params: Record<string, unknown> = {}): Promise<PageData<Requisition>> {
  return get<PageData<Requisition>>('/planning/requisitions', params)
}

export function createRequisition(payload: Record<string, unknown>): Promise<Requisition> {
  return post<Requisition>('/planning/requisitions', payload)
}

export function confirmRequisition(id: number): Promise<Requisition> {
  return post<Requisition>(`/planning/requisitions/${id}/confirm`)
}

export function cancelRequisition(id: number): Promise<Requisition> {
  return post<Requisition>(`/planning/requisitions/${id}/cancel`)
}

/** 人工审核调整领料单（仅 DRAFT 可改，items 传入则整表替换） */
export function updateRequisition(id: number, payload: Record<string, unknown>): Promise<Requisition> {
  return patch<Requisition>(`/planning/requisitions/${id}`, payload)
}

/** 按选中的生产作业计划的 BOM 子件生成领料单 */
export function generateRequisitionsFromPlans(
  planIds: number[],
  warehouseId?: number | null,
): Promise<GenerationResult> {
  return post<GenerationResult>('/planning/requisitions/from-plans', {
    plan_ids: planIds,
    warehouse_id: warehouseId ?? null,
  })
}

/** 删除领料单（仅草稿 / 已取消，明细一并删除） */
export function deleteRequisition(id: number): Promise<unknown> {
  return del(`/planning/requisitions/${id}`)
}

/** 批量删除领料单 */
export function batchDeleteRequisitions(ids: number[]): Promise<BatchDeleteResult> {
  return post<BatchDeleteResult>('/planning/requisitions/batch-delete', { ids })
}

// ---------------- 完工报告 ----------------

export function listCompletionReports(params: Record<string, unknown> = {}): Promise<PageData<CompletionReport>> {
  return get<PageData<CompletionReport>>('/planning/completion-reports', params)
}

export function createCompletionReport(payload: Record<string, unknown>): Promise<CompletionReport> {
  return post<CompletionReport>('/planning/completion-reports', payload)
}

export function confirmCompletionReport(id: number): Promise<CompletionReport> {
  return post<CompletionReport>(`/planning/completion-reports/${id}/confirm`)
}

export function cancelCompletionReport(id: number): Promise<CompletionReport> {
  return post<CompletionReport>(`/planning/completion-reports/${id}/cancel`)
}

/** 人工补填完工报告（仅 DRAFT 可改） */
export function updateCompletionReport(id: number, payload: Record<string, unknown>): Promise<CompletionReport> {
  return patch<CompletionReport>(`/planning/completion-reports/${id}`, payload)
}

/** 按选中的生产作业计划生成完工报告 */
export function generateCompletionReportsFromPlans(
  planIds: number[],
): Promise<GenerationResult> {
  return post<GenerationResult>('/planning/completion-reports/from-plans', { plan_ids: planIds })
}

/** 删除完工报告（仅草稿 / 已取消） */
export function deleteCompletionReport(id: number): Promise<unknown> {
  return del(`/planning/completion-reports/${id}`)
}

/** 批量删除完工报告 */
export function batchDeleteCompletionReports(ids: number[]): Promise<BatchDeleteResult> {
  return post<BatchDeleteResult>('/planning/completion-reports/batch-delete', { ids })
}