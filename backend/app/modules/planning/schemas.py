"""planning 模块 Pydantic Schema。

命名约定：

- `XxxCreate` 新增入参、`XxxUpdate` 修改入参
- `XxxOut` 出参（单个）、`XxxListOut` 列表出参
- 所有接口统一用 `ApiResponse[...]` 包装（见 `app.common.response`）
- 分页统一使用 `PageData[...]`（见 `app.common.pagination`）

计划模块错误码区段：`3000~3999`。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.common.response import ApiResponse
from app.shared.types import HealthData

HealthResponse = ApiResponse[HealthData]


class _OrmBase(BaseModel):
    """允许从 ORM 对象直接构造的出参基类。"""

    model_config = ConfigDict(from_attributes=True)


class _IdOut(_OrmBase):
    id: int = Field(description="主键")


# ---------------- 统一需求 ----------------
class DemandCreate(BaseModel):
    """需求新增入参。"""

    source_type: str = Field(description="需求来源 SALES/FORECAST/STOCKFILL/MPS")
    material_id: int = Field(description="物料ID")
    quantity: Decimal = Field(gt=0, description="需求数量")
    due_date: date = Field(description="需求日期")
    source_reference_id: Optional[int] = Field(default=None, description="来源单据ID")
    source_no: Optional[str] = Field(default=None, description="来源单号")
    remark: Optional[str] = None


class DemandOut(_IdOut):
    demand_no: str
    source_type: str
    source_reference_id: Optional[int] = None
    source_no: Optional[str] = None
    material_id: int
    material_code: Optional[str] = Field(default=None, description="物料编码（列表展示）")
    material_name: Optional[str] = Field(default=None, description="物料名称（列表展示）")
    quantity: Decimal
    due_date: date
    status: str
    remark: Optional[str] = None


# ---------------- MPS ----------------
class MpsItemCreate(BaseModel):
    """MPS 行新增入参。"""

    material_id: int = Field(description="产成品物料ID")
    period_label: Optional[str] = Field(default=None, description="计划期间标签")
    planned_qty: Decimal = Field(gt=0, description="计划生产数量")
    start_date: date = Field(description="计划开始日期")
    end_date: date = Field(description="计划完成日期")
    remark: Optional[str] = None


class MpsCreate(BaseModel):
    """MPS 头新增入参（可含行明细）。"""

    mps_no: Optional[str] = Field(default=None, description="MPS编号，留空自动生成")
    mps_name: Optional[str] = Field(default=None, description="计划名称")
    program_no: Optional[str] = None
    plan_year: int = Field(description="计划年度")
    start_date: date = Field(description="计划开始日期")
    end_date: date = Field(description="计划结束日期")
    remark: Optional[str] = None
    items: List[MpsItemCreate] = Field(default_factory=list, description="MPS行明细")


class MpsItemOut(_IdOut):
    mps_id: int
    material_id: int
    material_code: Optional[str] = Field(default=None, description="物料编码（列表展示）")
    material_name: Optional[str] = Field(default=None, description="物料名称（列表展示）")
    period_label: Optional[str] = None
    planned_qty: Decimal
    finished_qty: Decimal
    start_date: date
    end_date: date
    status: str
    remark: Optional[str] = None
    source_demand_ids: Optional[str] = Field(
        default=None, description="来源需求ID（逗号分隔，由需求汇总生成时写入）"
    )
    source_demand_nos: Optional[str] = Field(
        default=None, description="来源需求单号（逗号分隔，列表展示）"
    )


class MpsFromDemandsRequest(BaseModel):
    """从统一需求汇总生成 MPS 的入参。"""

    start_date: date = Field(description="汇总期间开始日期（含）")
    end_date: date = Field(description="汇总期间结束日期（含）")
    mps_name: Optional[str] = Field(default=None, description="计划名称，留空自动生成")
    program_no: Optional[str] = None
    remark: Optional[str] = None


class MpsOut(_IdOut):
    mps_no: str
    mps_name: Optional[str] = None
    program_no: Optional[str] = None
    plan_year: int
    start_date: date
    end_date: date
    status: str
    remark: Optional[str] = None
    items: List[MpsItemOut] = Field(default_factory=list)


# ---------------- MRP ----------------
class MrpRunCreate(BaseModel):
    """MRP 运算发起入参：MRP 只由 MPS 触发，不再接受需求直算。"""

    mps_id: int = Field(description="要展开的 MPS 头ID")
    remark: Optional[str] = None


class MrpResultOut(_IdOut):
    run_id: int
    material_id: int
    material_code: Optional[str] = Field(default=None, description="物料编码（列表展示）")
    material_name: Optional[str] = Field(default=None, description="物料名称（列表展示）")
    parent_material_id: Optional[int] = None
    parent_material_code: Optional[str] = Field(default=None, description="父件物料编码（列表展示）")
    parent_material_name: Optional[str] = Field(default=None, description="父件物料名称（列表展示）")
    bom_level: int
    gross_requirement: Decimal
    on_hand: Decimal
    available_quantity: Decimal
    safety_stock: Decimal
    net_requirement: Decimal
    order_qty: Decimal
    supply_type: str
    lead_time_days: int
    requirement_date: date
    planned_release_date: Optional[date] = None
    status: str
    remark: Optional[str] = None


class MrpRunOut(_IdOut):
    run_no: str
    mps_id: Optional[int] = None
    mps_no: Optional[str] = Field(default=None, description="MPS 编号（列表展示）")
    run_at: datetime
    status: str
    material_count: int
    remark: Optional[str] = None
    results: List[MrpResultOut] = Field(default_factory=list)


class MrpResultStatusUpdate(BaseModel):
    """MRP 结果状态流转入参。"""

    status: str = Field(description="目标状态")


# ---------------- 生产作业计划 ----------------
class ProductionPlanCreate(BaseModel):
    plan_no: Optional[str] = Field(default=None, description="作业计划编号，留空自动生成")
    mrp_result_id: Optional[int] = None
    material_id: int = Field(description="自制件物料ID")
    planned_qty: Decimal = Field(gt=0, description="计划生产数量")
    plan_date: date = Field(description="计划日期")
    start_date: date = Field(description="计划开始日期")
    end_date: date = Field(description="计划完成日期")
    remark: Optional[str] = None


class ProductionPlanOut(_IdOut):
    plan_no: str
    mrp_result_id: Optional[int] = None
    source_type: str
    source_reference_id: Optional[int] = None
    material_id: int
    material_code: Optional[str] = Field(default=None, description="物料编码（列表展示）")
    material_name: Optional[str] = Field(default=None, description="物料名称（列表展示）")
    planned_qty: Decimal
    completed_qty: Decimal
    plan_date: date
    start_date: date
    end_date: date
    status: str
    remark: Optional[str] = None


class StatusUpdate(BaseModel):
    """通用状态流转入参。"""

    status: str = Field(description="目标状态")


# ---------------- 派工单 ----------------
class DispatchOrderCreate(BaseModel):
    dispatch_no: Optional[str] = Field(default=None, description="派工单号，留空自动生成")
    plan_id: Optional[int] = None
    operation: Optional[str] = None
    planned_qty: Decimal = Field(gt=0, description="派工数量")
    worker_id: Optional[int] = Field(default=None, description="作业人员（sys_personnel.id）")
    org_id: Optional[int] = Field(
        default=None, description="承接单位（sys_organization.id）；留空自动取智能加工中心"
    )
    planned_start: Optional[date] = Field(default=None, description="计划开始日期，草稿可留空")
    planned_end: Optional[date] = Field(default=None, description="计划结束日期，草稿可留空")
    remark: Optional[str] = None


class DispatchOrderOut(_IdOut):
    dispatch_no: str
    source_type: str
    source_reference_id: Optional[int] = None
    plan_id: Optional[int] = None
    plan_no: Optional[str] = Field(default=None, description="生产作业计划编号（列表展示）")
    operation: Optional[str] = None
    planned_qty: Decimal
    completed_qty: Decimal
    worker_id: Optional[int] = None
    worker_name: Optional[str] = Field(default=None, description="作业人员姓名（列表展示）")
    org_id: Optional[int] = None
    org_name: Optional[str] = Field(default=None, description="承接单位名称（列表展示）")
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    status: str
    remark: Optional[str] = None


class DispatchOrderUpdate(BaseModel):
    """派工单修改入参（人工审核调整，仅 DRAFT 可改；未传字段不改）。"""

    operation: Optional[str] = None
    planned_qty: Optional[Decimal] = Field(default=None, gt=0, description="派工数量")
    worker_id: Optional[int] = Field(default=None, description="作业人员（sys_personnel.id）")
    org_id: Optional[int] = Field(
        default=None, description="承接单位（sys_organization.id）"
    )
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    remark: Optional[str] = None


class DispatchOrderFromPlansRequest(BaseModel):
    """按生产作业计划生成派工单入参。"""

    plan_ids: List[int] = Field(min_length=1, description="生产作业计划ID集合")


# ---------------- 领料单 ----------------
class RequisitionItemCreate(BaseModel):
    material_id: int = Field(description="物料ID")
    required_qty: Decimal = Field(gt=0, description="需求数量")
    remark: Optional[str] = None


class RequisitionCreate(BaseModel):
    req_no: Optional[str] = Field(default=None, description="领料单号，留空自动生成")
    plan_id: Optional[int] = None
    warehouse_id: Optional[int] = Field(default=None, description="领料仓库ID")
    req_date: Optional[date] = Field(default=None, description="领料日期，草稿可留空")
    remark: Optional[str] = None
    items: List[RequisitionItemCreate] = Field(default_factory=list, description="领料行")


class RequisitionItemOut(_IdOut):
    requisition_id: int
    material_id: int
    material_code: Optional[str] = Field(default=None, description="物料编码（列表展示）")
    material_name: Optional[str] = Field(default=None, description="物料名称（列表展示）")
    required_qty: Decimal
    issued_qty: Decimal
    remark: Optional[str] = None


class RequisitionOut(_IdOut):
    req_no: str
    source_type: str
    source_reference_id: Optional[int] = None
    plan_id: Optional[int] = None
    plan_no: Optional[str] = Field(default=None, description="生产作业计划编号（列表展示）")
    warehouse_id: Optional[int] = None
    warehouse_code: Optional[str] = Field(default=None, description="领料仓库编码（列表展示）")
    warehouse_name: Optional[str] = Field(default=None, description="领料仓库名称（列表展示）")
    req_date: Optional[date] = None
    status: str
    remark: Optional[str] = None
    items: List[RequisitionItemOut] = Field(default_factory=list)


class RequisitionItemUpdate(BaseModel):
    material_id: int = Field(description="物料ID")
    required_qty: Decimal = Field(gt=0, description="需求数量")
    remark: Optional[str] = None


class RequisitionUpdate(BaseModel):
    """领料单修改入参（人工审核调整，仅 DRAFT 可改；未传字段不改，`items` 传则整表替换）。"""

    warehouse_id: Optional[int] = Field(default=None, description="领料仓库ID")
    req_date: Optional[date] = None
    remark: Optional[str] = None
    items: Optional[List[RequisitionItemUpdate]] = Field(
        default=None, description="领料行，传入则整表替换"
    )


class RequisitionFromPlansRequest(BaseModel):
    """按生产作业计划生成领料单入参。"""

    plan_ids: List[int] = Field(min_length=1, description="生产作业计划ID集合")
    warehouse_id: Optional[int] = Field(default=None, description="领料仓库ID，可留空后续补填")


# ---------------- 批量生成结果 ----------------
class GenerationErrorOut(BaseModel):
    """单条计划生成失败原因。"""

    plan_id: int
    plan_no: Optional[str] = None
    material_code: Optional[str] = None
    reason: str


class GenerationSkipOut(BaseModel):
    """单条计划被跳过的原因。"""

    plan_id: int
    plan_no: Optional[str] = None
    reason: str


class GenerationResultOut(BaseModel):
    """批量生成汇总：新建 / 跳过 / 失败明细。"""

    created_count: int
    skipped_count: int
    errors: List[GenerationErrorOut] = Field(default_factory=list)
    skipped: List[GenerationSkipOut] = Field(default_factory=list)
    ids: List[int] = Field(default_factory=list)


# ---------------- 批量删除 ----------------
class BatchDeleteRequest(BaseModel):
    """批量删除入参：待删除单据 ID 集合。"""

    ids: List[int] = Field(min_length=1, description="待删除单据ID集合")


class BatchDeleteSkipOut(BaseModel):
    """单条被跳过删除的原因。"""

    id: int = Field(description="单据ID")
    reason: str = Field(description="跳过原因")


class BatchDeleteResultOut(BaseModel):
    """批量删除汇总：成功条数 / 逐条跳过原因。"""

    deleted_count: int = Field(description="成功删除条数")
    skipped: List[BatchDeleteSkipOut] = Field(default_factory=list, description="逐条跳过原因")


# ---------------- 完工报告 ----------------
class CompletionReportCreate(BaseModel):
    report_no: Optional[str] = Field(default=None, description="完工报告单号，留空自动生成")
    plan_id: Optional[int] = None
    dispatch_id: Optional[int] = None
    material_id: int = Field(description="产出物料ID")
    completed_qty: Decimal = Field(gt=0, description="完工数量")
    qualified_qty: Decimal = Field(ge=0, description="合格数量（入库数量）")
    scrap_qty: Decimal = Field(default=Decimal("0"), ge=0, description="报废数量")
    warehouse_id: Optional[int] = Field(default=None, description="入库仓库ID，草稿可留空")
    report_date: Optional[date] = Field(default=None, description="报工日期，草稿可留空")
    remark: Optional[str] = None


class CompletionReportOut(_IdOut):
    report_no: str
    plan_id: Optional[int] = None
    plan_no: Optional[str] = Field(default=None, description="生产作业计划编号（列表展示）")
    dispatch_id: Optional[int] = None
    dispatch_no: Optional[str] = Field(default=None, description="派工单号（列表展示）")
    material_id: int
    material_code: Optional[str] = Field(default=None, description="物料编码（列表展示）")
    material_name: Optional[str] = Field(default=None, description="物料名称（列表展示）")
    completed_qty: Decimal
    qualified_qty: Decimal
    scrap_qty: Decimal
    warehouse_id: Optional[int] = None
    warehouse_code: Optional[str] = Field(default=None, description="入库仓库编码（列表展示）")
    warehouse_name: Optional[str] = Field(default=None, description="入库仓库名称（列表展示）")
    report_date: Optional[date] = None
    status: str
    remark: Optional[str] = None


class CompletionReportUpdate(BaseModel):
    """完工报告修改入参（人工补填，仅 DRAFT 可改；未传字段不改）。"""

    dispatch_id: Optional[int] = Field(default=None, description="派工单ID")
    completed_qty: Optional[Decimal] = Field(default=None, gt=0, description="完工数量")
    qualified_qty: Optional[Decimal] = Field(default=None, ge=0, description="合格数量（入库数量）")
    scrap_qty: Optional[Decimal] = Field(default=None, ge=0, description="报废数量")
    warehouse_id: Optional[int] = Field(default=None, description="入库仓库ID")
    report_date: Optional[date] = Field(default=None, description="报工日期")
    remark: Optional[str] = None


class CompletionReportFromPlansRequest(BaseModel):
    """按生产作业计划生成完工报告入参。"""

    plan_ids: List[int] = Field(min_length=1, description="生产作业计划ID集合")


# ---------------- 统计 ----------------
class PlanningStatsOut(BaseModel):
    """计划管理统计（供首页 / 综合查询使用）。"""

    current_period: str = Field(default="", description="本期期间（如 2026-10）")
    mps_planned_qty: Decimal = Field(
        default=Decimal("0"), description="本期已确认及以上 MPS 计划量合计"
    )
    mps_count: int = Field(description="MPS 数量")
    demand_count: int = Field(default=0, description="需求总量（已确认及以上，排除草稿/已取消）")
    mrp_run_count: int = Field(description="MRP 运算批次数量")
    mrp_result_count: int = Field(description="MRP 结果条数")
    make_count: int = Field(description="自制件需求条数")
    buy_count: int = Field(description="采购件需求条数")
    open_plan_count: int = Field(description="未完成作业计划数")
    open_dispatch_count: int = Field(description="未完成派工单数")
    open_requisition_count: int = Field(description="未完成领料单数")
    completion_report_count: int = Field(default=0, description="完工报告数量")


class StatsResponse(ApiResponse[PlanningStatsOut]):
    """计划模块统计响应。"""


# ---------------- 需求：扩展入参 ----------------
class DemandStatusUpdate(BaseModel):
    """需求状态流转入参。"""

    status: str = Field(description="目标状态 DRAFT/CONFIRMED/RELEASED/COMPLETED/CANCELLED")


class DemandFromReplenishmentRequest(BaseModel):
    """从库存补库需求生成计划需求入参。"""

    request_id: int = Field(description="库存补库需求ID（inv_replenishment_request.id）")


class DemandImportResult(BaseModel):
    """从销售订单导入需求的结果。"""

    created_count: int = Field(description="新建需求数")
    skipped_count: int = Field(description="已存在被跳过数")
    demand_ids: List[int] = Field(default_factory=list, description="新建需求ID列表")


# ---------------- MPS：扩展入参 ----------------
class MpsUpdate(BaseModel):
    """MPS 修改入参（仅 DRAFT 可改；items 为空表示不改明细）。"""

    mps_name: Optional[str] = None
    program_no: Optional[str] = None
    plan_year: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    remark: Optional[str] = None
    items: Optional[List[MpsItemCreate]] = Field(default=None, description="替换后的 MPS 行明细")


# ---------------- MPS 课程附录 1 导入 ----------------
class MpsImportRow(BaseModel):
    """显式传入的导入行。"""

    material_code: str = Field(description="物料编码，导入时解析为物料ID")
    period_label: Optional[str] = Field(default=None, description="计划期间标签")
    planned_qty: Decimal = Field(gt=0, description="计划生产数量")
    start_date: date = Field(description="计划开始日期")
    end_date: date = Field(description="计划完成日期")


class MpsImportRequest(BaseModel):
    """MPS 导入请求：`source` 与服务端内置案例二选一，或直接给 `rows`。"""

    source: Optional[str] = Field(default=None, description="内置数据源标识，如 course_chair_case")
    rows: List[MpsImportRow] = Field(default_factory=list, description="显式导入行")
    mps_no: Optional[str] = Field(default=None, description="MPS编号，留空自动生成")
    mps_name: Optional[str] = None
    program_no: Optional[str] = None
    plan_year: Optional[int] = None
    remark: Optional[str] = None


class MpsImportPreviewRow(BaseModel):
    """校验通过的一行。"""

    row_index: int
    material_code: str
    material_id: Optional[int] = None
    material_name: Optional[str] = None
    period_label: Optional[str] = None
    planned_qty: Decimal
    start_date: date
    end_date: date


class MpsImportError(BaseModel):
    """一行校验失败。"""

    row: int = Field(description="行号（从 0 开始）")
    message: str


class MpsImportSummary(BaseModel):
    """导入汇总。"""

    total_rows: int
    valid_count: int
    error_count: int
    plan_year: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class MpsImportPreviewOut(BaseModel):
    """导入预览（不落库）。"""

    valid_rows: List[MpsImportPreviewRow] = Field(default_factory=list)
    errors: List[MpsImportError] = Field(default_factory=list)
    summary: MpsImportSummary


# ---------------- MRP：扩展出参 ----------------
class MrpExplainOut(BaseModel):
    """MRP 计算明细：供前端展示毛需求 → 净需求的完整推导过程。"""

    mrp_result_id: int
    run_id: int
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    parent_material_id: Optional[int] = None
    parent_material_code: Optional[str] = None
    parent_material_name: Optional[str] = None
    bom_level: int
    gross_requirement: Decimal
    on_hand: Decimal
    available_quantity: Decimal
    safety_stock: Decimal
    net_requirement: Decimal
    order_qty: Decimal
    supply_type: str
    lead_time_days: int
    requirement_date: date
    planned_release_date: Optional[date] = None
    status: str
    formula: str = Field(description="净需求计算说明（中文）")


# ---------------- 生产作业计划：扩展入参 ----------------
class ProductionPlanUpdate(BaseModel):
    """生产作业计划修改入参（仅 DRAFT 可改）。"""

    planned_qty: Optional[Decimal] = Field(default=None, gt=0)
    plan_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    remark: Optional[str] = None


class ProductionPlanFromMrpRequest(BaseModel):
    """从 MRP 结果批量生成作业计划入参。"""

    mrp_result_ids: List[int] = Field(default_factory=list, description="MRP 结果ID列表")


# ---------------- 完工报告：取消入参 ----------------
class CompletionReportCancel(BaseModel):
    """完工报告取消入参。"""

    remark: Optional[str] = None