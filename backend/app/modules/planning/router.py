"""planning 模块路由（统一前缀 `/api/v1/planning`，由 `app/main.py` 注入）。

约定：
- 路由层只做参数绑定、调用 service、提交事务，不写业务规则。
- service 内写操作日志，二者同一事务；**本层成功后才 `db.commit()`**。
- 领料 / 完工确认涉及库存变动，异常时显式 `rollback()` 保证原子回滚。
- 出参统一 `ApiResponse[...]`，分页统一 `PageData[...]`。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.pagination import PageData, PageParams
from app.common.response import ApiResponse, success
from app.core.database import get_db
from app.modules.planning import schemas, service
from app.shared.enums import ModuleName, ModuleStatus
from app.shared.types import HealthData

router = APIRouter(tags=["planning"])


# ==================== 健康检查（占位） ====================


@router.get("/health", response_model=schemas.HealthResponse, summary="planning 模块健康检查（占位）")
def health() -> schemas.HealthResponse:
    """占位接口：只返回模块标识与状态，不含任何业务逻辑。"""
    return schemas.HealthResponse(
        data=HealthData(module=ModuleName.PLANNING.value, status=ModuleStatus.UP.value)
    )


# ==================== 统一需求 ====================


@router.get(
    "/demands",
    response_model=ApiResponse[PageData[schemas.DemandOut]],
    summary="需求列表",
)
def list_demands(
    params: PageParams = Depends(PageParams.as_dependency),
    source_type: Optional[str] = Query(default=None, description="需求来源 SALES/STOCKFILL/MPS"),
    status: Optional[str] = Query(default=None, description="状态"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.DemandOut]]:
    """分页查询计划需求。"""
    rows, total = service.list_demands(db, params.page, params.page_size, source_type, status)
    return success(
        PageData[schemas.DemandOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/demands", response_model=ApiResponse[schemas.DemandOut], summary="新增需求")
def create_demand(
    payload: schemas.DemandCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.DemandOut]:
    """新增计划需求（默认 DRAFT）。"""
    demand = service.create_demand(
        db,
        source_type=payload.source_type,
        material_id=payload.material_id,
        quantity=payload.quantity,
        due_date=payload.due_date,
        source_reference_id=payload.source_reference_id,
        source_no=payload.source_no,
        remark=payload.remark,
    )
    db.commit()
    return success(demand)


@router.get(
    "/demands/{demand_id}",
    response_model=ApiResponse[schemas.DemandOut],
    summary="需求详情",
)
def get_demand(
    demand_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.DemandOut]:
    """按 ID 查询需求。"""
    return success(service.get_demand(db, demand_id))


@router.patch(
    "/demands/{demand_id}/status",
    response_model=ApiResponse[schemas.DemandOut],
    summary="需求状态流转",
)
def set_demand_status(
    demand_id: int, payload: schemas.DemandStatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.DemandOut]:
    """需求状态流转（DRAFT → CONFIRMED → RELEASED → COMPLETED，可 CANCELLED）。"""
    demand = service.set_demand_status(db, demand_id, payload.status)
    db.commit()
    return success(demand)


@router.post(
    "/demands/from-sales",
    response_model=ApiResponse[schemas.DemandImportResult],
    summary="从销售订单导入需求",
)
def import_demands_from_sales(
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.DemandImportResult]:
    """把已确认销售订单需求拉取为 `source_type=SALES` 的计划需求（已导入的跳过）。"""
    result = service.import_demands_from_sales(db)
    db.commit()
    return success(result)


@router.post(
    "/demands/from-replenishment",
    response_model=ApiResponse[schemas.DemandOut],
    summary="从库存补库需求生成需求",
)
def create_demand_from_replenishment(
    payload: schemas.DemandFromReplenishmentRequest, db: Session = Depends(get_db)
) -> ApiResponse[schemas.DemandOut]:
    """由库存补库需求生成 `source_type=STOCKFILL` 的计划需求。"""
    demand = service.create_demand_from_replenishment(db, payload.request_id)
    db.commit()
    return success(demand)


# ==================== MPS ====================


@router.get("/mps", response_model=ApiResponse[PageData[schemas.MpsOut]], summary="MPS 列表")
def list_mps(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = Query(default=None, description="状态"),
    year: Optional[int] = Query(default=None, description="计划年度"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.MpsOut]]:
    """分页查询主生产计划。"""
    rows, total = service.list_mps(db, params.page, params.page_size, status, year)
    return success(
        PageData[schemas.MpsOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/mps", response_model=ApiResponse[schemas.MpsOut], summary="新增 MPS")
def create_mps(
    payload: schemas.MpsCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.MpsOut]:
    """新增 MPS（头 + 行明细，默认 DRAFT）。"""
    mps = service.create_mps(db, payload)
    db.commit()
    return success(mps)


@router.post(
    "/mps/import/preview",
    response_model=ApiResponse[schemas.MpsImportPreviewOut],
    summary="MPS 导入预览（不落库）",
)
def preview_mps_import(
    payload: schemas.MpsImportRequest, db: Session = Depends(get_db)
) -> ApiResponse[schemas.MpsImportPreviewOut]:
    """课程附录 1 MPS 导入预览：校验并返回有效行 / 错误行 / 汇总，**不写库**。"""
    return success(service.preview_mps_import(db, payload))


@router.post(
    "/mps/import/confirm",
    response_model=ApiResponse[schemas.MpsOut],
    summary="MPS 导入确认",
)
def confirm_mps_import(
    payload: schemas.MpsImportRequest, db: Session = Depends(get_db)
) -> ApiResponse[schemas.MpsOut]:
    """课程附录 1 MPS 导入确认：校验通过后写入 MPS 头 + 行。"""
    mps = service.confirm_mps_import(db, payload)
    db.commit()
    return success(mps)


@router.get("/mps/{mps_id}", response_model=ApiResponse[schemas.MpsOut], summary="MPS 详情")
def get_mps(mps_id: int, db: Session = Depends(get_db)) -> ApiResponse[schemas.MpsOut]:
    """按 ID 查询 MPS（含行明细）。"""
    return success(service.get_mps(db, mps_id))


@router.put("/mps/{mps_id}", response_model=ApiResponse[schemas.MpsOut], summary="修改 MPS")
def update_mps(
    mps_id: int, payload: schemas.MpsUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.MpsOut]:
    """修改 MPS：仅 DRAFT 可改（已确认/已下达只读，报 3002）。"""
    mps = service.update_mps(db, mps_id, payload)
    db.commit()
    return success(mps)


@router.delete("/mps/{mps_id}", response_model=ApiResponse[dict], summary="删除 MPS")
def delete_mps(mps_id: int, db: Session = Depends(get_db)) -> ApiResponse[dict]:
    """删除 MPS：仅 DRAFT 可删。"""
    service.delete_mps(db, mps_id)
    db.commit()
    return success({"deleted": True})


@router.patch(
    "/mps/{mps_id}/status",
    response_model=ApiResponse[schemas.MpsOut],
    summary="MPS 状态流转",
)
def set_mps_status(
    mps_id: int, payload: schemas.StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.MpsOut]:
    """MPS 状态机：DRAFT → CONFIRMED → RELEASED → IN_PROGRESS → COMPLETED（+ CANCELLED）。"""
    mps = service.set_mps_status(db, mps_id, payload.status)
    db.commit()
    return success(mps)


# ==================== MRP 运算 ====================


@router.post("/mrp/run", response_model=ApiResponse[schemas.MrpRunOut], summary="执行 MRP 运算")
def run_mrp(
    payload: schemas.MrpRunCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.MrpRunOut]:
    """执行一次真实的 MRP 多层 BOM 展开（每次运算独立批次，不覆盖历史结果）。"""
    run = service.run_mrp(
        db,
        mps_id=payload.mps_id,
        demand_ids=payload.demand_ids,
        include_sales_demand=payload.include_sales_demand,
        remark=payload.remark,
    )
    db.commit()
    return success(run)


@router.get(
    "/mrp/runs", response_model=ApiResponse[PageData[schemas.MrpRunOut]], summary="MRP 批次列表"
)
def list_mrp_runs(
    params: PageParams = Depends(PageParams.as_dependency), db: Session = Depends(get_db)
) -> ApiResponse[PageData[schemas.MrpRunOut]]:
    """分页查询 MRP 运算批次。"""
    rows, total = service.list_mrp_runs(db, params.page, params.page_size)
    return success(
        PageData[schemas.MrpRunOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.get(
    "/mrp/runs/{run_id}",
    response_model=ApiResponse[schemas.MrpRunOut],
    summary="MRP 批次详情（含结果）",
)
def get_mrp_run(run_id: int, db: Session = Depends(get_db)) -> ApiResponse[schemas.MrpRunOut]:
    """按 ID 查询批次及全部结果行。"""
    return success(service.get_mrp_run(db, run_id))


@router.get(
    "/mrp/runs/{run_id}/results",
    response_model=ApiResponse[PageData[schemas.MrpResultOut]],
    summary="MRP 批次结果（分页）",
)
def list_run_results(
    run_id: int,
    params: PageParams = Depends(PageParams.as_dependency),
    supply_type: Optional[str] = Query(default=None, description="MAKE/BUY"),
    status: Optional[str] = Query(default=None, description="状态"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.MrpResultOut]]:
    """分页查询某批次的结果，可按供应类型 / 状态过滤。"""
    rows, total = service.list_mrp_results(
        db, params.page, params.page_size, run_id, supply_type, status
    )
    return success(
        PageData[schemas.MrpResultOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.get(
    "/mrp/runs/{run_id}/explain",
    response_model=ApiResponse[schemas.MrpExplainOut],
    summary="MRP 计算明细",
)
def explain_mrp_result(
    run_id: int,
    material_id: int = Query(description="物料ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.MrpExplainOut]:
    """展示某物料在某批次的完整推导：毛需求 / 库存 / 安全库存 / 净需求 / 建议下达。"""
    return success(service.explain_mrp_result(db, run_id, material_id))


@router.get(
    "/mrp/results",
    response_model=ApiResponse[PageData[schemas.MrpResultOut]],
    summary="MRP 结果（跨批次分页）",
)
def list_mrp_results(
    params: PageParams = Depends(PageParams.as_dependency),
    run_id: Optional[int] = Query(default=None, description="批次ID"),
    supply_type: Optional[str] = Query(default=None, description="MAKE/BUY"),
    status: Optional[str] = Query(default=None, description="状态"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.MrpResultOut]]:
    """跨批次分页查询 MRP 结果。"""
    rows, total = service.list_mrp_results(
        db, params.page, params.page_size, run_id, supply_type, status
    )
    return success(
        PageData[schemas.MrpResultOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.patch(
    "/mrp/results/{result_id}/status",
    response_model=ApiResponse[schemas.MrpResultOut],
    summary="MRP 结果状态流转",
)
def set_mrp_result_status(
    result_id: int, payload: schemas.MrpResultStatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.MrpResultOut]:
    """MRP 结果状态流转（下达后置 RELEASED）。"""
    result = service.set_mrp_result_status(db, result_id, payload.status)
    db.commit()
    return success(result)


@router.post(
    "/mrp/runs/{run_id}/create-purchase-plan",
    response_model=ApiResponse[dict],
    summary="由 MRP 批次生成采购计划",
)
def create_purchase_plan_from_run(
    run_id: int, db: Session = Depends(get_db)
) -> ApiResponse[dict]:
    """把该批次的 BUY 结果交给 Procurement 生成采购计划，并置结果 RELEASED。"""
    result = service.create_purchase_plan_from_run(db, run_id)
    db.commit()
    return success(result)


@router.post(
    "/mrp/runs/{run_id}/create-production-plans",
    response_model=ApiResponse[List[schemas.ProductionPlanOut]],
    summary="由 MRP 批次生成生产作业计划",
)
def create_production_plans_from_run(
    run_id: int, db: Session = Depends(get_db)
) -> ApiResponse[List[schemas.ProductionPlanOut]]:
    """把该批次的 MAKE 结果生成生产作业计划，并置结果 RELEASED。"""
    plans = service.create_production_plans_from_run(db, run_id)
    db.commit()
    return success(plans)


# ==================== 生产作业计划 ====================


@router.get(
    "/production-plans",
    response_model=ApiResponse[PageData[schemas.ProductionPlanOut]],
    summary="生产作业计划列表",
)
def list_production_plans(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = Query(default=None, description="状态"),
    material_id: Optional[int] = Query(default=None, description="物料ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.ProductionPlanOut]]:
    """分页查询生产作业计划。"""
    rows, total = service.list_production_plans(db, params.page, params.page_size, status, material_id)
    return success(
        PageData[schemas.ProductionPlanOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/production-plans",
    response_model=ApiResponse[schemas.ProductionPlanOut],
    summary="新增生产作业计划",
)
def create_production_plan(
    payload: schemas.ProductionPlanCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ProductionPlanOut]:
    """手工新增生产作业计划（物料须为自制件）。"""
    plan = service.create_production_plan(
        db,
        material_id=payload.material_id,
        planned_qty=payload.planned_qty,
        plan_date=payload.plan_date,
        start_date=payload.start_date,
        end_date=payload.end_date,
        mrp_result_id=payload.mrp_result_id,
        plan_no=payload.plan_no,
        remark=payload.remark,
    )
    db.commit()
    return success(plan)


@router.post(
    "/production-plans/from-mrp",
    response_model=ApiResponse[List[schemas.ProductionPlanOut]],
    summary="由 MRP 结果生成生产作业计划",
)
def create_production_plans_from_mrp(
    payload: schemas.ProductionPlanFromMrpRequest, db: Session = Depends(get_db)
) -> ApiResponse[List[schemas.ProductionPlanOut]]:
    """按 MRP 结果ID 批量生成作业计划。"""
    plans = service.create_production_plans_from_mrp(db, payload.mrp_result_ids)
    db.commit()
    return success(plans)


@router.get(
    "/production-plans/{plan_id}",
    response_model=ApiResponse[schemas.ProductionPlanOut],
    summary="生产作业计划详情",
)
def get_production_plan(
    plan_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ProductionPlanOut]:
    """按 ID 查询生产作业计划。"""
    return success(service.get_production_plan(db, plan_id))


@router.put(
    "/production-plans/{plan_id}",
    response_model=ApiResponse[schemas.ProductionPlanOut],
    summary="修改生产作业计划",
)
def update_production_plan(
    plan_id: int, payload: schemas.ProductionPlanUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ProductionPlanOut]:
    """修改作业计划：仅 DRAFT 可改。"""
    plan = service.update_production_plan(db, plan_id, payload)
    db.commit()
    return success(plan)


@router.patch(
    "/production-plans/{plan_id}/status",
    response_model=ApiResponse[schemas.ProductionPlanOut],
    summary="生产作业计划状态流转",
)
def set_production_plan_status(
    plan_id: int, payload: schemas.StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ProductionPlanOut]:
    """作业计划状态机。"""
    plan = service.set_production_plan_status(db, plan_id, payload.status)
    db.commit()
    return success(plan)


# ==================== 派工单 ====================


@router.get(
    "/dispatch-orders",
    response_model=ApiResponse[PageData[schemas.DispatchOrderOut]],
    summary="派工单列表",
)
def list_dispatch_orders(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = Query(default=None, description="状态"),
    plan_id: Optional[int] = Query(default=None, description="作业计划ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.DispatchOrderOut]]:
    """分页查询派工单。"""
    rows, total = service.list_dispatch_orders(db, params.page, params.page_size, status, plan_id)
    return success(
        PageData[schemas.DispatchOrderOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/dispatch-orders",
    response_model=ApiResponse[schemas.DispatchOrderOut],
    summary="新增派工单",
)
def create_dispatch_order(
    payload: schemas.DispatchOrderCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.DispatchOrderOut]:
    """新增派工单；作业人员须存在于 `sys_personnel`。"""
    dispatch = service.create_dispatch_order(
        db,
        planned_qty=payload.planned_qty,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        plan_id=payload.plan_id,
        operation=payload.operation,
        worker_id=payload.worker_id,
        dispatch_no=payload.dispatch_no,
        remark=payload.remark,
    )
    db.commit()
    return success(dispatch)


@router.get(
    "/dispatch-orders/{dispatch_id}",
    response_model=ApiResponse[schemas.DispatchOrderOut],
    summary="派工单详情",
)
def get_dispatch_order(
    dispatch_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.DispatchOrderOut]:
    """按 ID 查询派工单。"""
    return success(service.get_dispatch_order(db, dispatch_id))


@router.patch(
    "/dispatch-orders/{dispatch_id}/status",
    response_model=ApiResponse[schemas.DispatchOrderOut],
    summary="派工单状态流转",
)
def set_dispatch_order_status(
    dispatch_id: int, payload: schemas.StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.DispatchOrderOut]:
    """派工单状态机。"""
    dispatch = service.set_dispatch_order_status(db, dispatch_id, payload.status)
    db.commit()
    return success(dispatch)


# ==================== 领料单 ====================


@router.get(
    "/requisitions",
    response_model=ApiResponse[PageData[schemas.RequisitionOut]],
    summary="领料单列表",
)
def list_requisitions(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = Query(default=None, description="状态"),
    plan_id: Optional[int] = Query(default=None, description="作业计划ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.RequisitionOut]]:
    """分页查询领料单。"""
    rows, total = service.list_requisitions(db, params.page, params.page_size, status, plan_id)
    return success(
        PageData[schemas.RequisitionOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/requisitions",
    response_model=ApiResponse[schemas.RequisitionOut],
    summary="新增领料单",
)
def create_requisition(
    payload: schemas.RequisitionCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.RequisitionOut]:
    """新增领料单（头 + 行，默认 DRAFT）。"""
    req = service.create_requisition(
        db,
        req_date=payload.req_date,
        items=[item.model_dump() for item in payload.items],
        plan_id=payload.plan_id,
        warehouse_id=payload.warehouse_id,
        req_no=payload.req_no,
        remark=payload.remark,
    )
    db.commit()
    return success(req)


@router.get(
    "/requisitions/{req_id}",
    response_model=ApiResponse[schemas.RequisitionOut],
    summary="领料单详情",
)
def get_requisition(
    req_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.RequisitionOut]:
    """按 ID 查询领料单（含行明细）。"""
    return success(service.get_requisition(db, req_id))


@router.post(
    "/requisitions/{req_id}/confirm",
    response_model=ApiResponse[schemas.RequisitionOut],
    summary="确认领料（出库）",
)
def confirm_requisition(
    req_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.RequisitionOut]:
    """确认领料：逐行走库存出库契约；库存不足（5001）整体回滚。"""
    try:
        req = service.confirm_requisition(db, req_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return success(req)


@router.post(
    "/requisitions/{req_id}/cancel",
    response_model=ApiResponse[schemas.RequisitionOut],
    summary="取消领料单",
)
def cancel_requisition(
    req_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.RequisitionOut]:
    """取消领料单（DRAFT / CONFIRMED 可取消）。"""
    req = service.cancel_requisition(db, req_id)
    db.commit()
    return success(req)


# ==================== 完工报告 ====================


@router.get(
    "/completion-reports",
    response_model=ApiResponse[PageData[schemas.CompletionReportOut]],
    summary="完工报告列表",
)
def list_completion_reports(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = Query(default=None, description="状态"),
    plan_id: Optional[int] = Query(default=None, description="作业计划ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.CompletionReportOut]]:
    """分页查询完工报告。"""
    rows, total = service.list_completion_reports(db, params.page, params.page_size, status, plan_id)
    return success(
        PageData[schemas.CompletionReportOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/completion-reports",
    response_model=ApiResponse[schemas.CompletionReportOut],
    summary="新增完工报告",
)
def create_completion_report(
    payload: schemas.CompletionReportCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.CompletionReportOut]:
    """新增完工报告（默认 DRAFT，确认后才入库）。"""
    report = service.create_completion_report(
        db,
        material_id=payload.material_id,
        completed_qty=payload.completed_qty,
        qualified_qty=payload.qualified_qty,
        warehouse_id=payload.warehouse_id,
        report_date=payload.report_date,
        plan_id=payload.plan_id,
        dispatch_id=payload.dispatch_id,
        location_id=payload.location_id,
        scrap_qty=payload.scrap_qty,
        report_no=payload.report_no,
        remark=payload.remark,
    )
    db.commit()
    return success(report)


@router.get(
    "/completion-reports/{report_id}",
    response_model=ApiResponse[schemas.CompletionReportOut],
    summary="完工报告详情",
)
def get_completion_report(
    report_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.CompletionReportOut]:
    """按 ID 查询完工报告。"""
    return success(service.get_completion_report(db, report_id))


@router.post(
    "/completion-reports/{report_id}/confirm",
    response_model=ApiResponse[schemas.CompletionReportOut],
    summary="确认完工（入库）",
)
def confirm_completion_report(
    report_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.CompletionReportOut]:
    """确认完工：走库存入库契约，并回写作业计划 / 派工单已完工数量。"""
    try:
        report = service.confirm_completion_report(db, report_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return success(report)


@router.post(
    "/completion-reports/{report_id}/cancel",
    response_model=ApiResponse[schemas.CompletionReportOut],
    summary="取消完工报告",
)
def cancel_completion_report(
    report_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.CompletionReportOut]:
    """取消完工报告（仅 DRAFT）。"""
    report = service.cancel_completion_report(db, report_id)
    db.commit()
    return success(report)


# ==================== 统计 ====================


@router.get(
    "/stats",
    response_model=ApiResponse[schemas.PlanningStatsOut],
    summary="计划模块统计",
)
def stats(db: Session = Depends(get_db)) -> ApiResponse[schemas.PlanningStatsOut]:
    """计划管理统计（MPS / MRP / MAKE-BUY / 未完成单据 / 完工报告）。"""
    return success(service.stats(db))