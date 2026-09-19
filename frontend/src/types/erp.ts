/**
 * BH-ERP 业务实体类型。
 *
 * 字段与后端各模块 `schemas.py` 的 `XxxOut` 一一对应。
 * 说明：后端 Decimal 序列化后可能是字符串，故金额 / 数量统一用 `Num`。
 */

/** 金额 / 数量：后端 Decimal 可能以字符串或数字返回 */
export type Num = number | string

/** 远程下拉选项 */
export interface RemoteOption {
  id: number
  label: string
}

/** 通用状态流转入参 */
export interface StatusPayload {
  status: string
  operator_id?: number
}

// ==================== system ====================

export interface Material {
  id: number
  material_code: string
  material_name: string
  material_type: string
  supply_type: string
  unit_code: string
  specification?: string | null
  material_group?: string | null
  lead_time_days: number
  safety_stock: Num
  standard_cost: Num
  status: string
  remark?: string | null
}

export interface MaterialPayload {
  material_code?: string
  material_name?: string
  material_type?: string
  supply_type?: string
  unit_code?: string
  specification?: string | null
  material_group?: string | null
  lead_time_days?: number
  safety_stock?: Num
  standard_cost?: Num
  status?: string
  remark?: string | null
}

export interface BomItem {
  id: number
  bom_id: number
  material_id: number
  quantity: Num
  lead_time_offset: number
  scrap_rate: Num
  sequence_no: number
  remark?: string | null
}

export interface Bom {
  id: number
  bom_code: string
  material_id: number
  bom_version: string
  effective_date?: string | null
  expiry_date?: string | null
  is_active: boolean
  status: string
  remark?: string | null
  items: BomItem[]
}

export interface BomTreeNode {
  material_id: number
  material_code?: string | null
  material_name?: string | null
  quantity: Num
  lead_time_offset: number
  scrap_rate: Num
  level: number
  children: BomTreeNode[]
}

export interface RoutingOperation {
  id: number
  routing_id: number
  sequence_no: number
  operation_code: string
  operation_name: string
  work_center?: string | null
  setup_time: Num
  run_time: Num
  remark?: string | null
}

export interface Routing {
  id: number
  routing_code: string
  material_id: number
  routing_version: string
  status: string
  remark?: string | null
  operations: RoutingOperation[]
}

export interface Organization {
  id: number
  org_code: string
  org_name: string
  parent_id?: number | null
  org_type: string
  manager_id?: number | null
  status: string
  remark?: string | null
  children?: Organization[]
}

export interface Personnel {
  id: number
  employee_no: string
  person_name: string
  org_id: number
  position?: string | null
  phone?: string | null
  email?: string | null
  hire_date?: string | null
  status: string
  remark?: string | null
}

export interface DictionaryItem {
  id: number
  dict_id: number
  item_code: string
  item_name: string
  item_value?: string | null
  sort_no: number
  status: string
}

export interface Dictionary {
  id: number
  dict_code: string
  dict_name: string
  status: string
  remark?: string | null
  items: DictionaryItem[]
}

export interface Permission {
  id: number
  perm_code: string
  perm_name: string
  perm_type: string
  parent_id?: number | null
  path?: string | null
  module?: string | null
  sort_no: number
  status: string
  children?: Permission[]
}

export interface Role {
  id: number
  role_code: string
  role_name: string
  description?: string | null
  status: string
  permissions: Permission[]
}

export interface User {
  id: number
  username: string
  display_name: string
  personnel_id?: number | null
  status: string
  last_login_at?: string | null
  remark?: string | null
  roles: Role[]
}

export interface OperationLog {
  id: number
  module: string
  action: string
  target_type: string
  target_id?: number | null
  operator_id?: number | null
  detail?: string | null
  created_at: string
}

export interface SystemStats {
  material_count: number
  active_material_count: number
  bom_count: number
  routing_count: number
  personnel_count: number
  user_count: number
  role_count: number
  dictionary_count: number
}

export interface LoginResult {
  user: User
  roles: Role[]
  permissions: Permission[]
}

// ==================== sales ====================

export interface Customer {
  id: number
  customer_code: string
  customer_name: string
  contact_person?: string | null
  phone?: string | null
  email?: string | null
  address?: string | null
  credit_limit: Num
  status: string
  remark?: string | null
}

export interface Product {
  id: number
  material_code: string
  material_name: string
  material_type: string
  supply_type?: string | null
  unit_code?: string | null
  lead_time_days?: number | null
  safety_stock?: Num | null
  status: string
}

export interface Forecast {
  id: number
  forecast_no: string
  customer_id?: number | null
  customer_name?: string | null
  material_id: number
  material_code?: string | null
  material_name?: string | null
  forecast_month: string
  forecast_qty: Num
  status: string
  remark?: string | null
}

export interface OrderItem {
  id: number
  order_id: number
  line_no: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  quantity: Num
  delivered_qty: Num
  unit_price: Num
  amount: Num
  remark?: string | null
}

export interface Order {
  id: number
  order_no: string
  customer_id: number
  customer_name?: string | null
  order_date: string
  delivery_date: string
  salesperson_id?: number | null
  salesperson_name?: string | null
  total_amount: Num
  status: string
  remark?: string | null
  items: OrderItem[]
}

export interface ShipmentItem {
  id: number
  shipment_id: number
  order_item_id: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  warehouse_id: number
  location_id?: number | null
  quantity: Num
  remark?: string | null
}

export interface Shipment {
  id: number
  shipment_no: string
  order_id: number
  order_no?: string | null
  customer_id: number
  customer_name?: string | null
  shipment_date: string
  status: string
  remark?: string | null
  items: ShipmentItem[]
}

export interface ReturnItem {
  id: number
  return_id: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  warehouse_id: number
  location_id?: number | null
  quantity: Num
  quality_status: string
  reason?: string | null
  remark?: string | null
}

export interface SalesReturn {
  id: number
  return_no: string
  order_id?: number | null
  order_no?: string | null
  customer_id: number
  customer_name?: string | null
  return_date: string
  reason?: string | null
  status: string
  remark?: string | null
  items: ReturnItem[]
}

export interface OrderStatusReport {
  order_no: string
  customer_name?: string | null
  order_date: string
  status: string
  total_qty: Num
  delivered_qty: Num
  fulfillment_rate: Num
}

export interface SalesStats {
  customer_count: number
  order_count: number
  order_counts: Record<string, number>
  pending_shipment_order_count: number
  shipment_count: number
  return_count: number
}

// ==================== planning ====================

export interface Demand {
  id: number
  demand_no: string
  source_type: string
  source_reference_id?: number | null
  source_no?: string | null
  material_id: number
  quantity: Num
  due_date: string
  status: string
  remark?: string | null
}

export interface MpsItem {
  id: number
  mps_id: number
  material_id: number
  period_label?: string | null
  planned_qty: Num
  finished_qty: Num
  start_date: string
  end_date: string
  status: string
  remark?: string | null
}

export interface Mps {
  id: number
  mps_no: string
  mps_name?: string | null
  program_no?: string | null
  plan_year: number
  start_date: string
  end_date: string
  status: string
  remark?: string | null
  items: MpsItem[]
}

export interface MrpResult {
  id: number
  run_id: number
  material_id: number
  parent_material_id?: number | null
  bom_level: number
  gross_requirement: Num
  on_hand: Num
  available_quantity: Num
  safety_stock: Num
  net_requirement: Num
  order_qty: Num
  supply_type: string
  lead_time_days: number
  requirement_date: string
  planned_release_date?: string | null
  status: string
  remark?: string | null
}

export interface MrpRun {
  id: number
  run_no: string
  mps_id?: number | null
  run_at: string
  status: string
  material_count: number
  remark?: string | null
  results: MrpResult[]
}

export interface MrpExplain {
  mrp_result_id: number
  run_id: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  parent_material_id?: number | null
  parent_material_code?: string | null
  parent_material_name?: string | null
  bom_level: number
  gross_requirement: Num
  on_hand: Num
  available_quantity: Num
  safety_stock: Num
  net_requirement: Num
  order_qty: Num
  supply_type: string
  lead_time_days: number
  requirement_date: string
  planned_release_date?: string | null
  status: string
  formula: string
}

export interface MpsImportPreviewRow {
  row_index: number
  material_code: string
  material_id?: number | null
  material_name?: string | null
  period_label?: string | null
  planned_qty: Num
  start_date: string
  end_date: string
}

export interface MpsImportError {
  row: number
  message: string
}

export interface MpsImportPreview {
  valid_rows: MpsImportPreviewRow[]
  errors: MpsImportError[]
  summary: {
    total_rows: number
    valid_count: number
    error_count: number
    plan_year: number
    start_date?: string | null
    end_date?: string | null
  }
}

export interface ProductionPlan {
  id: number
  plan_no: string
  mrp_result_id?: number | null
  source_type: string
  source_reference_id?: number | null
  material_id: number
  planned_qty: Num
  completed_qty: Num
  plan_date: string
  start_date: string
  end_date: string
  status: string
  remark?: string | null
}

export interface DispatchOrder {
  id: number
  dispatch_no: string
  plan_id?: number | null
  operation?: string | null
  planned_qty: Num
  completed_qty: Num
  worker_id?: number | null
  planned_start: string
  planned_end: string
  status: string
  remark?: string | null
}

export interface RequisitionItem {
  id: number
  requisition_id: number
  material_id: number
  required_qty: Num
  issued_qty: Num
  location_id?: number | null
  remark?: string | null
}

export interface Requisition {
  id: number
  req_no: string
  plan_id?: number | null
  warehouse_id?: number | null
  req_date: string
  status: string
  remark?: string | null
  items: RequisitionItem[]
}

export interface CompletionReport {
  id: number
  report_no: string
  plan_id?: number | null
  dispatch_id?: number | null
  material_id: number
  completed_qty: Num
  qualified_qty: Num
  scrap_qty: Num
  warehouse_id: number
  location_id?: number | null
  report_date: string
  status: string
  remark?: string | null
}

export interface PlanningStats {
  mps_count: number
  mrp_run_count: number
  mrp_result_count: number
  make_count: number
  buy_count: number
  open_plan_count: number
  open_dispatch_count: number
  open_requisition_count: number
  completion_report_count: number
}

// ==================== inventory ====================

export interface Location {
  id: number
  location_code: string
  location_name: string
  warehouse_id: number
  status: string
  remark?: string | null
}

export interface Warehouse {
  id: number
  warehouse_code: string
  warehouse_name: string
  org_id?: number | null
  manager_id?: number | null
  address?: string | null
  status: string
  remark?: string | null
  locations: Location[]
}

export interface Balance {
  id: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  warehouse_id: number
  warehouse_name?: string | null
  location_id?: number | null
  on_hand: Num
  locked_quantity: Num
  available_quantity: Num
}

export interface Transaction {
  id: number
  transaction_no: string
  transaction_type: string
  material_id: number
  material_code?: string | null
  material_name?: string | null
  warehouse_id: number
  location_id?: number | null
  quantity_change: Num
  quantity_after: Num
  unit_cost: Num
  biz_date: string
  source_module: string
  source_type: string
  source_reference_id?: number | null
  source_no?: string | null
  operator_id?: number | null
  remark?: string | null
  created_at: string
}

export interface StockChangeResult {
  transaction_id: number
  transaction_no: string
  quantity_after: Num
}

export interface TransferItem {
  id: number
  transfer_id: number
  material_id: number
  from_location_id?: number | null
  to_location_id?: number | null
  quantity: Num
  remark?: string | null
}

export interface Transfer {
  id: number
  transfer_no: string
  from_warehouse_id: number
  to_warehouse_id: number
  transfer_date: string
  status: string
  remark?: string | null
  items: TransferItem[]
}

export interface StocktakeItem {
  id: number
  stocktake_id: number
  material_id: number
  location_id?: number | null
  book_qty: Num
  actual_qty: Num
  difference: Num
  remark?: string | null
}

export interface Stocktake {
  id: number
  stocktake_no: string
  warehouse_id: number
  stocktake_date: string
  status: string
  remark?: string | null
  items: StocktakeItem[]
}

export interface ReorderRule {
  id: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  warehouse_id: number
  reorder_point: Num
  reorder_quantity: Num
  status: string
  remark?: string | null
}

export interface ReorderSuggestion {
  material_id: number
  warehouse_id: number
  reorder_point: Num
  current_qty: Num
  suggested_qty: Num
  target_qty: Num
}

export interface ReplenishmentRequest {
  id: number
  request_no: string
  material_id: number
  material_code?: string | null
  material_name?: string | null
  warehouse_id: number
  request_qty: Num
  current_qty: Num
  target_qty: Num
  required_date: string
  source_type: string
  status: string
  handled_module?: string | null
  handled_ref_id?: number | null
  remark?: string | null
}

export interface StockSummary {
  material_id: number
  material_code?: string | null
  material_name?: string | null
  on_hand: Num
  available_quantity: Num
  safety_stock: Num
  below_safety: boolean
}

export interface LowStock {
  material_id: number
  material_code?: string | null
  material_name?: string | null
  available_quantity: Num
  safety_stock: Num
  shortage_qty: Num
}

export interface FlowSummaryRow {
  transaction_type: string
  material_id: number
  material_code?: string | null
  material_name?: string | null
  total_quantity: Num
}

export interface InventoryStats {
  warehouse_count: number
  location_count: number
  balance_count: number
  transaction_count: number
  transfer_count: number
  stocktake_count: number
  reorder_rule_count: number
  replenishment_request_count: number
  low_stock_count: number
}

// ==================== procurement（表结构已在后端 models.py 定义） ====================

export interface Supplier {
  id: number
  supplier_code: string
  supplier_name: string
  contact_person?: string | null
  phone?: string | null
  email?: string | null
  address?: string | null
  status: string
  remark?: string | null
}

/** 供应商-物料供货关系（含供货价与提前期） */
export interface SupplierMaterial {
  id: number
  supplier_id: number
  supplier_name?: string | null
  material_id: number
  material_code?: string | null
  material_name?: string | null
  is_primary: boolean
  supply_price: Num
  lead_time_days: number
  min_order_qty: Num
  status: string
}

/** 可采购物料（只读 system 物料主数据，supply_type = BUY） */
export interface PurchaseMaterial {
  id: number
  material_code: string
  material_name: string
  material_type: string
  supply_type?: string | null
  unit_code?: string | null
  lead_time_days?: number | null
  safety_stock?: Num | null
  status: string
}

export interface PurchasePlanItem {
  id: number
  plan_id: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  required_qty: Num
  ordered_qty: Num
  required_date: string
  source_type: string
  source_reference_id?: number | null
  supplier_id?: number | null
  supplier_name?: string | null
  status: string
  remark?: string | null
}

export interface PurchasePlan {
  id: number
  plan_no: string
  plan_date: string
  status: string
  remark?: string | null
  items: PurchasePlanItem[]
}

export interface PurchaseOrderItem {
  id: number
  order_id: number
  line_no: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  quantity: Num
  received_qty: Num
  unit_price: Num
  amount: Num
  remark?: string | null
}

export interface PurchaseOrder {
  id: number
  order_no: string
  supplier_id: number
  supplier_name?: string | null
  order_date: string
  expected_date: string
  buyer_id?: number | null
  buyer_name?: string | null
  total_amount: Num
  status: string
  remark?: string | null
  items: PurchaseOrderItem[]
}

export interface ReceiptItem {
  id: number
  receipt_id: number
  order_item_id: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  location_id?: number | null
  quantity: Num
  qualified_qty: Num
  remark?: string | null
}

export interface Receipt {
  id: number
  receipt_no: string
  purchase_order_id: number
  order_no?: string | null
  supplier_id: number
  supplier_name?: string | null
  warehouse_id: number
  receipt_date: string
  status: string
  remark?: string | null
  items: ReceiptItem[]
}

export interface SupplierEvaluation {
  id: number
  supplier_id: number
  supplier_name?: string | null
  evaluate_date: string
  quality_score: Num
  delivery_score: Num
  price_score: Num
  /** 综合得分由后端按三项评分计算，前端不提交 */
  total_score: Num
  evaluator_id?: number | null
  evaluator_name?: string | null
  remark?: string | null
}

/** 采购计划执行报表行 */
export interface PlanReportRow {
  plan_id: number
  plan_no: string
  plan_date: string
  status: string
  material_id: number
  material_code?: string | null
  material_name?: string | null
  required_qty: Num
  ordered_qty: Num
  remaining_qty: Num
  required_date: string
  source_type: string
}

/** 采购订单到货进度报表行 */
export interface OrderReportRow {
  order_id: number
  order_no: string
  supplier_id: number
  supplier_name?: string | null
  order_date: string
  expected_date: string
  status: string
  material_id: number
  material_code?: string | null
  material_name?: string | null
  quantity: Num
  received_qty: Num
  remaining_qty: Num
  receipt_rate: Num
  unit_price: Num
  amount: Num
}

/** 到货记录报表行 */
export interface ReceiptReportRow {
  receipt_no: string
  receipt_date: string
  status: string
  order_no?: string | null
  supplier_id: number
  supplier_name?: string | null
  material_id: number
  material_code?: string | null
  material_name?: string | null
  warehouse_id: number
  location_id?: number | null
  quantity: Num
  qualified_qty: Num
}

/** 未到货报表行（received_qty < quantity 的订单行） */
export interface PendingReceiptRow {
  order_id: number
  order_no: string
  supplier_id: number
  supplier_name?: string | null
  expected_date: string
  status: string
  order_item_id: number
  material_id: number
  material_code?: string | null
  material_name?: string | null
  quantity: Num
  received_qty: Num
  remaining_qty: Num
}

/** 供应商评分汇总报表行 */
export interface SupplierEvaluationSummary {
  supplier_id: number
  supplier_name?: string | null
  evaluation_count: number
  avg_total_score: Num
  avg_quality_score: Num
  avg_delivery_score: Num
  avg_price_score: Num
}

/** 采购模块统计（工作台使用） */
export interface ProcurementStats {
  supplier_count: number
  supplier_material_count: number
  plan_count: number
  plan_counts: Record<string, number>
  order_count: number
  order_counts: Record<string, number>
  pending_receipt_line_count: number
  receipt_count: number
  evaluation_count: number
}

// ==================== 课程数据导入（规格 §37） ====================

/** 单条导入错误 */
export interface ImportErrorRow {
  material_code?: string | null
  message: string
}

/** 物料导入预览行 */
export interface MaterialPreviewItem {
  material_code: string
  material_name: string
  material_type?: string | null
  supply_type?: string | null
  /** TO_CREATE / EXISTING / INVALID */
  status: string
}

export interface MaterialImportSummary {
  total: number
  to_create: number
  existing: number
  invalid: number
  max_level: number
  source_counts: Record<string, number>
}

export interface MaterialImportPreview {
  source: string
  materials: MaterialPreviewItem[]
  errors: ImportErrorRow[]
  summary: MaterialImportSummary
}

export interface MaterialImportConfirm {
  source: string
  created: number
  skipped: number
  errors: ImportErrorRow[]
}

/** BOM 子项导入预览行 */
export interface BomItemPreview {
  parent_material_code: string
  child_material_code: string
  quantity: Num
  lead_time_offset: number
  scrap_rate: Num
  level: number
}

export interface BomImportSummary {
  total_nodes: number
  levels: number
  bom_headers: number
  bom_items: number
  lead_time_offset_default: number
  scrap_rate_default: Num
  resolution_rule: string
  source_counts: Record<string, number>
}

export interface BomImportPreview {
  source: string
  materials: MaterialPreviewItem[]
  bom_items: BomItemPreview[]
  errors: ImportErrorRow[]
  summary: BomImportSummary
}

export interface BomImportConfirm {
  source: string
  bom_headers_created: number
  bom_items_created: number
  skipped: number
  errors: ImportErrorRow[]
}

/** 期初库存导入预览行（VALID / INVALID） */
export interface InitialStockPreviewRow {
  material_code: string
  material_name?: string | null
  quantity: Num
  status: string
}

export interface InitialStockErrorRow {
  material_code: string
  message: string
}

export interface InitialStockPreview {
  rows: InitialStockPreviewRow[]
  errors: InitialStockErrorRow[]
  summary: { total: number; valid: number; invalid: number }
}

export interface InitialStockConfirm {
  imported: number
  errors: InitialStockErrorRow[]
}