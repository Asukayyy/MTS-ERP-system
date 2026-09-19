"""planning 模块数据访问层。

只负责数据库读写与查询拼装，**不写业务规则**。
只允许被本模块的 `service.py` 调用；其它模块禁止直接 import 本文件。
跨模块数据（销售需求、库存、BOM）通过模块 Contract 获取，本层**不跨模块 JOIN**。
"""

from typing import List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.planning import models


def count_all(db: Session, model) -> int:
    """统计某表总行数（供综合统计使用）。"""
    return db.scalar(select(func.count()).select_from(model)) or 0


def count_where(db: Session, model, *criteria) -> int:
    """按条件统计行数。"""
    return db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0


# ==================== 通用分页 ====================


def _paginate(db: Session, stmt, page: int, page_size: int):
    """对 select 语句做统一分页，返回 (items, total)。"""
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


# ==================== 需求 ====================


def list_demands(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    source_type: Optional[str] = None,
    status: Optional[str] = None,
):
    stmt = select(models.PlnDemand).order_by(models.PlnDemand.id.desc())
    if source_type:
        stmt = stmt.where(models.PlnDemand.source_type == source_type)
    if status:
        stmt = stmt.where(models.PlnDemand.status == status)
    return _paginate(db, stmt, page, page_size)


def get_demand(db: Session, demand_id: int) -> Optional[models.PlnDemand]:
    return db.get(models.PlnDemand, demand_id)


def add_demand(db: Session, demand: models.PlnDemand) -> models.PlnDemand:
    db.add(demand)
    db.flush()
    return demand


# ==================== MPS ====================


def list_mps(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
):
    stmt = select(models.PlnMps).order_by(models.PlnMps.id.desc())
    if status:
        stmt = stmt.where(models.PlnMps.status == status)
    return _paginate(db, stmt, page, page_size)


def get_mps(db: Session, mps_id: int) -> Optional[models.PlnMps]:
    return db.get(models.PlnMps, mps_id)


def get_mps_items(db: Session, mps_id: int) -> List[models.PlnMpsItem]:
    return list(
        db.scalars(
            select(models.PlnMpsItem)
            .where(models.PlnMpsItem.mps_id == mps_id)
            .order_by(models.PlnMpsItem.id)
        )
    )


def add_mps(db: Session, mps: models.PlnMps) -> models.PlnMps:
    db.add(mps)
    db.flush()
    return mps


def add_mps_item(db: Session, item: models.PlnMpsItem) -> models.PlnMpsItem:
    db.add(item)
    return item


def delete_mps_items(db: Session, mps_id: int) -> None:
    for item in get_mps_items(db, mps_id):
        db.delete(item)


def next_no(db: Session, model, field_name: str, prefix: str) -> str:
    """生成业务单号：`<prefix><6位序号>`。仅用于演示级单号，真实场景应走独立序列。"""
    total = count_all(db, model)
    return f"{prefix}{total + 1:06d}"


# ==================== MRP ====================


def list_mrp_runs(db: Session, page: int = 1, page_size: int = 20):
    stmt = select(models.PlnMrpRun).order_by(models.PlnMrpRun.id.desc())
    return _paginate(db, stmt, page, page_size)


def get_mrp_run(db: Session, run_id: int) -> Optional[models.PlnMrpRun]:
    return db.get(models.PlnMrpRun, run_id)


def add_mrp_run(db: Session, run: models.PlnMrpRun) -> models.PlnMrpRun:
    db.add(run)
    db.flush()
    return run


def add_mrp_results(
    db: Session, results: Sequence[models.PlnMrpResult]
) -> None:
    db.add_all(results)


def get_mrp_results(db: Session, run_id: int) -> List[models.PlnMrpResult]:
    return list(
        db.scalars(
            select(models.PlnMrpResult)
            .where(models.PlnMrpResult.run_id == run_id)
            .order_by(models.PlnMrpResult.bom_level, models.PlnMrpResult.id)
        )
    )


def list_mrp_results(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    run_id: Optional[int] = None,
    supply_type: Optional[str] = None,
    status: Optional[str] = None,
):
    stmt = select(models.PlnMrpResult).order_by(
        models.PlnMrpResult.bom_level, models.PlnMrpResult.id
    )
    if run_id:
        stmt = stmt.where(models.PlnMrpResult.run_id == run_id)
    if supply_type:
        stmt = stmt.where(models.PlnMrpResult.supply_type == supply_type)
    if status:
        stmt = stmt.where(models.PlnMrpResult.status == status)
    return _paginate(db, stmt, page, page_size)


def get_mrp_results_by_ids(db: Session, ids: Sequence[int]) -> List[models.PlnMrpResult]:
    if not ids:
        return []
    return list(
        db.scalars(select(models.PlnMrpResult).where(models.PlnMrpResult.id.in_(list(ids))))
    )


# ==================== 生产作业计划 ====================


def list_production_plans(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    material_id: Optional[int] = None,
):
    stmt = select(models.PlnProductionPlan).order_by(models.PlnProductionPlan.id.desc())
    if status:
        stmt = stmt.where(models.PlnProductionPlan.status == status)
    if material_id:
        stmt = stmt.where(models.PlnProductionPlan.material_id == material_id)
    return _paginate(db, stmt, page, page_size)


def get_production_plan(db: Session, plan_id: int) -> Optional[models.PlnProductionPlan]:
    return db.get(models.PlnProductionPlan, plan_id)


def add_production_plan(
    db: Session, plan: models.PlnProductionPlan
) -> models.PlnProductionPlan:
    db.add(plan)
    db.flush()
    return plan


# ==================== 派工单 ====================


def list_dispatch_orders(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
):
    stmt = select(models.PlnDispatchOrder).order_by(models.PlnDispatchOrder.id.desc())
    if status:
        stmt = stmt.where(models.PlnDispatchOrder.status == status)
    if plan_id:
        stmt = stmt.where(models.PlnDispatchOrder.plan_id == plan_id)
    return _paginate(db, stmt, page, page_size)


def get_dispatch_order(db: Session, dispatch_id: int) -> Optional[models.PlnDispatchOrder]:
    return db.get(models.PlnDispatchOrder, dispatch_id)


def add_dispatch_order(
    db: Session, dispatch: models.PlnDispatchOrder
) -> models.PlnDispatchOrder:
    db.add(dispatch)
    db.flush()
    return dispatch


# ==================== 领料单 ====================


def list_requisitions(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
):
    stmt = select(models.PlnMaterialRequisition).order_by(
        models.PlnMaterialRequisition.id.desc()
    )
    if status:
        stmt = stmt.where(models.PlnMaterialRequisition.status == status)
    if plan_id:
        stmt = stmt.where(models.PlnMaterialRequisition.plan_id == plan_id)
    return _paginate(db, stmt, page, page_size)


def get_requisition(db: Session, req_id: int) -> Optional[models.PlnMaterialRequisition]:
    return db.get(models.PlnMaterialRequisition, req_id)


def get_requisition_items(
    db: Session, req_id: int
) -> List[models.PlnMaterialRequisitionItem]:
    return list(
        db.scalars(
            select(models.PlnMaterialRequisitionItem)
            .where(models.PlnMaterialRequisitionItem.requisition_id == req_id)
            .order_by(models.PlnMaterialRequisitionItem.id)
        )
    )


def add_requisition(
    db: Session, req: models.PlnMaterialRequisition
) -> models.PlnMaterialRequisition:
    db.add(req)
    db.flush()
    return req


def add_requisition_item(
    db: Session, item: models.PlnMaterialRequisitionItem
) -> models.PlnMaterialRequisitionItem:
    db.add(item)
    return item


# ==================== 完工报告 ====================


def list_completion_reports(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
):
    stmt = select(models.PlnCompletionReport).order_by(models.PlnCompletionReport.id.desc())
    if status:
        stmt = stmt.where(models.PlnCompletionReport.status == status)
    if plan_id:
        stmt = stmt.where(models.PlnCompletionReport.plan_id == plan_id)
    return _paginate(db, stmt, page, page_size)


def get_completion_report(db: Session, report_id: int) -> Optional[models.PlnCompletionReport]:
    return db.get(models.PlnCompletionReport, report_id)


def add_completion_report(
    db: Session, report: models.PlnCompletionReport
) -> models.PlnCompletionReport:
    db.add(report)
    db.flush()
    return report


# ==================== 事务 ====================


def commit(db: Session) -> None:
    db.commit()


def rollback(db: Session) -> None:
    db.rollback()


def refresh(db: Session, obj) -> None:
    db.refresh(obj)