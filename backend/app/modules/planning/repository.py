"""planning 模块数据访问层。

只负责数据库读写与查询拼装，**不写业务规则**。
只允许被本模块的 `service.py` 调用；其它模块禁止直接 import 本文件。
跨模块数据（销售需求、库存、BOM）通过模块 Contract 获取，本层**不跨模块 JOIN**。
"""

from decimal import Decimal
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


def get_demands_by_ids(db: Session, demand_ids: Sequence[int]) -> List[models.PlnDemand]:
    if not demand_ids:
        return []
    return list(
        db.scalars(select(models.PlnDemand).where(models.PlnDemand.id.in_(list(demand_ids))))
    )


def find_demand_by_source(
    db: Session, source_type: str, source_reference_id: Optional[int]
):
    """按来源类型 + 来源单据ID 查找已有需求（导入去重用）。"""
    if source_reference_id is None:
        return None
    return db.scalar(
        select(models.PlnDemand).where(
            models.PlnDemand.source_type == source_type,
            models.PlnDemand.source_reference_id == source_reference_id,
        )
    )


# ==================== MPS ====================


def list_mps(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    year: Optional[int] = None,
):
    stmt = select(models.PlnMps).order_by(models.PlnMps.id.desc())
    if status:
        stmt = stmt.where(models.PlnMps.status == status)
    if year:
        stmt = stmt.where(models.PlnMps.plan_year == year)
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


def exists_by_field(db: Session, model, field_name: str, value) -> bool:
    """判断某列取值是否已存在（业务编码唯一性校验）。"""
    column = getattr(model, field_name)
    return (db.scalar(select(func.count()).select_from(model).where(column == value)) or 0) > 0


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


def get_mrp_result(db: Session, result_id: int) -> Optional[models.PlnMrpResult]:
    return db.get(models.PlnMrpResult, result_id)


def find_run_result(
    db: Session, run_id: int, material_id: int
) -> Optional[models.PlnMrpResult]:
    """取某批次内某物料的计算结果（计算明细展示用）。"""
    return db.scalar(
        select(models.PlnMrpResult)
        .where(
            models.PlnMrpResult.run_id == run_id,
            models.PlnMrpResult.material_id == material_id,
        )
        .order_by(models.PlnMrpResult.id)
    )


def count_mrp_results_by_supply(db: Session, supply_type: str) -> int:
    return count_where(db, models.PlnMrpResult, models.PlnMrpResult.supply_type == supply_type)


def count_open(db: Session, model, open_statuses: Sequence[str]) -> int:
    """统计未结束（不处于给定终态）的单据数。"""
    return count_where(db, model, model.status.notin_(list(open_statuses)))


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


def find_plan_by_mrp_result(
    db: Session, mrp_result_id: int
) -> Optional[models.PlnProductionPlan]:
    """按 MRP 结果ID 查已生成的作业计划（防止重复下达）。"""
    return db.scalar(
        select(models.PlnProductionPlan).where(
            models.PlnProductionPlan.mrp_result_id == mrp_result_id
        )
    )


def find_plan_by_source(
    db: Session, source_type: str, source_reference_id: int
) -> Optional[models.PlnProductionPlan]:
    """按来源类型 + 来源单据ID 查作业计划（补库受理去重用）。"""
    return db.scalar(
        select(models.PlnProductionPlan).where(
            models.PlnProductionPlan.source_type == source_type,
            models.PlnProductionPlan.source_reference_id == source_reference_id,
        )
    )


def sum_open_production_qty(db: Session, material_id: int) -> Decimal:
    """某物料未完工的生产数量合计 = Σ(计划数量 - 已完工数量)，终态单据不计。"""
    total = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    models.PlnProductionPlan.planned_qty
                    - models.PlnProductionPlan.completed_qty
                ),
                0,
            )
        ).where(
            models.PlnProductionPlan.material_id == material_id,
            models.PlnProductionPlan.status.notin_(["COMPLETED", "CANCELLED"]),
        )
    )
    return Decimal(str(total or 0))


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