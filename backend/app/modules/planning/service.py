"""planning 模块业务逻辑层（MPS 录入 + 多层 MRP 展开 + 车间计划执行）。

职责边界（规格 §1 / §7 / §13 / §14）：

- Planning **负责计划**：需求归集、MPS 录入、MRP 多层 BOM 展开、净需求计算、MAKE/BUY 分流。
- 生产业务（生产作业计划 / 派工 / 领料 / 完工）**统一归 Planning**，不建独立 Production 模块。
- Planning **不直接改库存**：领料 / 完工一律通过 `inventory.contract`，由库存引擎写真实流水。
- 本层**不调用 `db.commit()`**：由 router 提交；contract 函数运行在调用方事务里。

错误码区段：`3000~3999`。
"""

import calendar
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.inventory.contract import (
    decrease_stock,
    get_stock_snapshot,
    increase_stock,
)
from app.modules.planning import models, repository
from app.modules.system.contract import (
    find_material_by_code,
    get_active_bom_children,
    get_material,
    get_materials,
    get_personnel,
    log_operation,
)

# ==================== 错误码（3000~3999） ====================

CODE_PARAM_INVALID = 3000  # 入参 / 状态非法
CODE_BOM_CYCLE = 3001  # BOM 存在循环引用
CODE_MPS_LOCKED = 3002  # 已确认/已下达的 MPS 只读
CODE_NOT_FOUND = 3003  # 资源不存在
CODE_DUPLICATE = 3004  # 唯一性冲突
CODE_CONTRACT_NOT_READY = 3005  # 跨模块契约尚未就绪
CODE_STATUS_INVALID = 3006  # 状态机不允许该流转
CODE_IMPORT_INVALID = 3007  # 导入数据校验失败

MODULE = "planning"

#: 服务端内置的课程附录 1 案例数据源标识
COURSE_CASE_SOURCE = "course_chair_case"

_DEMAND_STATUSES = {"DRAFT", "CONFIRMED", "RELEASED", "COMPLETED", "CANCELLED"}
_MPS_STATUSES = {"DRAFT", "CONFIRMED", "RELEASED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
_MRP_RESULT_STATUSES = {"DRAFT", "CONFIRMED", "RELEASED", "COMPLETED", "CANCELLED"}
_PLAN_STATUSES = {"DRAFT", "CONFIRMED", "RELEASED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
_DISPATCH_STATUSES = {"DRAFT", "CONFIRMED", "RELEASED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
_REQUISITION_STATUSES = {"DRAFT", "CONFIRMED", "RELEASED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
_COMPLETION_STATUSES = {"DRAFT", "CONFIRMED", "COMPLETED", "CANCELLED"}

#: 主单据状态机 DRAFT → CONFIRMED → RELEASED → IN_PROGRESS → COMPLETED（+ CANCELLED）
_MAIN_TRANSITIONS: Dict[str, set] = {
    "DRAFT": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"RELEASED", "CANCELLED"},
    "RELEASED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}

#: 需求状态机（DRAFT → CONFIRMED → RELEASED → COMPLETED）
_DEMAND_TRANSITIONS: Dict[str, set] = {
    "DRAFT": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"RELEASED", "COMPLETED", "CANCELLED"},
    "RELEASED": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}

_TERMINAL_STATUSES = ("COMPLETED", "CANCELLED")


# ==================== 小工具 ====================


def _as_decimal(value: Any) -> Decimal:
    """把 int / str / Decimal / None 统一转成 Decimal。"""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_date(value: Any, default: Optional[date] = None) -> Optional[date]:
    """把 date / datetime / ISO 字符串统一转成 date。"""
    if value is None:
        return default
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return default


def _days_before(value: date, days: int) -> date:
    """需求日期回推提前期天数，得到建议下达日期。"""
    return value - timedelta(days=int(days or 0))


def _month_end(year: int, month: int) -> date:
    """某年某月的最后一天。"""
    return date(year, month, calendar.monthrange(year, month)[1])


def _validate_status(value: str, allowed: set, label: str = "状态") -> None:
    if value not in allowed:
        raise BusinessException(CODE_PARAM_INVALID, f"非法{label}：{value}")


def _validate_transition(current: str, target: str, transitions: Dict[str, set], label: str) -> None:
    if target not in transitions.get(current, set()):
        raise BusinessException(
            CODE_STATUS_INVALID, f"{label}当前状态 {current} 不能流转到 {target}"
        )


def _require_material(db: Session, material_id: int) -> Dict[str, Any]:
    material = get_material(db, material_id)
    if not material:
        raise BusinessException(CODE_NOT_FOUND, f"物料不存在：{material_id}")
    return material


def _require_mps(db: Session, mps_id: int) -> models.PlnMps:
    mps = repository.get_mps(db, mps_id)
    if not mps:
        raise BusinessException(CODE_NOT_FOUND, f"MPS 不存在：{mps_id}")
    return mps


def _require_demand(db: Session, demand_id: int) -> models.PlnDemand:
    demand = repository.get_demand(db, demand_id)
    if not demand:
        raise BusinessException(CODE_NOT_FOUND, f"需求不存在：{demand_id}")
    return demand


def _require_run(db: Session, run_id: int) -> models.PlnMrpRun:
    run = repository.get_mrp_run(db, run_id)
    if not run:
        raise BusinessException(CODE_NOT_FOUND, f"MRP 运算批次不存在：{run_id}")
    return run


def _require_mrp_result(db: Session, result_id: int) -> models.PlnMrpResult:
    result = repository.get_mrp_result(db, result_id)
    if not result:
        raise BusinessException(CODE_NOT_FOUND, f"MRP 结果不存在：{result_id}")
    return result


def _require_plan(db: Session, plan_id: int) -> models.PlnProductionPlan:
    plan = repository.get_production_plan(db, plan_id)
    if not plan:
        raise BusinessException(CODE_NOT_FOUND, f"生产作业计划不存在：{plan_id}")
    return plan


def _require_dispatch(db: Session, dispatch_id: int) -> models.PlnDispatchOrder:
    dispatch = repository.get_dispatch_order(db, dispatch_id)
    if not dispatch:
        raise BusinessException(CODE_NOT_FOUND, f"派工单不存在：{dispatch_id}")
    return dispatch


def _require_requisition(db: Session, req_id: int) -> models.PlnMaterialRequisition:
    req = repository.get_requisition(db, req_id)
    if not req:
        raise BusinessException(CODE_NOT_FOUND, f"领料单不存在：{req_id}")
    return req


def _require_completion(db: Session, report_id: int) -> models.PlnCompletionReport:
    report = repository.get_completion_report(db, report_id)
    if not report:
        raise BusinessException(CODE_NOT_FOUND, f"完工报告不存在：{report_id}")
    return report


def _unique_no(
    db: Session, model, field_name: str, provided: Optional[str], prefix: str
) -> str:
    """确定业务单号：外部提供则校验唯一，否则按前缀自动生成。"""
    if provided:
        if repository.exists_by_field(db, model, field_name, provided):
            raise BusinessException(CODE_DUPLICATE, f"单号已存在：{provided}")
        return provided
    return repository.next_no(db, model, field_name, prefix)


# ==================== 统一需求 ====================


def list_demands(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    source_type: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[List[models.PlnDemand], int]:
    """分页查询需求。"""
    return repository.list_demands(db, page, page_size, source_type, status)


def get_demand(db: Session, demand_id: int) -> models.PlnDemand:
    return _require_demand(db, demand_id)


def create_demand(
    db: Session,
    *,
    source_type: str,
    material_id: int,
    quantity: Decimal,
    due_date: date,
    source_reference_id: Optional[int] = None,
    source_no: Optional[str] = None,
    demand_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnDemand:
    """新增需求（默认 DRAFT）。`source_type` 限定 SALES/STOCKFILL/MPS。"""
    _validate_status(source_type, {"SALES", "STOCKFILL", "MPS"}, "需求来源")
    qty = _as_decimal(quantity)
    if qty <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "需求数量必须为正数")
    _require_material(db, material_id)
    number = _unique_no(db, models.PlnDemand, "demand_no", demand_no, "DEM")
    demand = models.PlnDemand(
        demand_no=number,
        source_type=source_type,
        source_reference_id=source_reference_id,
        source_no=source_no,
        material_id=material_id,
        quantity=qty,
        due_date=due_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_demand(db, demand)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pln_demand",
        target_id=demand.id,
        operator_id=operator_id,
        detail=f"新增需求 {number}（{source_type}）",
    )
    return demand


def set_demand_status(
    db: Session, demand_id: int, status: str, operator_id: Optional[int] = None
) -> models.PlnDemand:
    """需求状态流转（DRAFT → CONFIRMED → RELEASED → COMPLETED，可 CANCELLED）。"""
    _validate_status(status, _DEMAND_STATUSES)
    demand = _require_demand(db, demand_id)
    _validate_transition(demand.status, status, _DEMAND_TRANSITIONS, "需求")
    demand.status = status
    demand.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="pln_demand",
        target_id=demand.id,
        operator_id=operator_id,
        detail=f"需求 {demand.demand_no} 状态改为 {status}",
    )
    return demand


def import_demands_from_sales(db: Session, operator_id: Optional[int] = None) -> Dict[str, Any]:
    """把已确认销售订单需求拉取为 `source_type=SALES` 的计划需求（已导入的跳过）。

    销售契约（`sales.contract.get_open_order_demand`）**惰性导入**，
    以便该模块尚未就绪时 planning 仍可正常导入。
    """
    try:
        from app.modules.sales.contract import get_open_order_demand  # type: ignore
    except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
        raise BusinessException(CODE_CONTRACT_NOT_READY, "销售需求接口尚未就绪") from exc

    rows = get_open_order_demand(db) or []
    created_ids: List[int] = []
    skipped = 0
    for row in rows:
        material_id = int(row["material_id"])
        source_reference_id = row.get("order_id") or row.get("id") or row.get("source_reference_id")
        due = _to_date(
            row.get("due_date")
            or row.get("required_date")
            or row.get("delivery_date")
            or row.get("order_date"),
            date.today(),
        )
        if repository.find_demand_by_source(db, "SALES", source_reference_id):
            skipped += 1
            continue
        demand = create_demand(
            db,
            source_type="SALES",
            material_id=material_id,
            quantity=_as_decimal(row.get("quantity") or row.get("order_qty")),
            due_date=due,
            source_reference_id=source_reference_id,
            source_no=row.get("order_no") or row.get("source_no"),
            remark=row.get("remark"),
            operator_id=operator_id,
        )
        created_ids.append(demand.id)
    return {"created_count": len(created_ids), "skipped_count": skipped, "demand_ids": created_ids}


def create_demand_from_replenishment(
    db: Session, request_id: int, operator_id: Optional[int] = None
) -> models.PlnDemand:
    """由库存补库需求生成 `source_type=STOCKFILL` 的计划需求。

    补库需求通过 `inventory.contract` 读取（惰性导入）。
    """
    try:
        from app.modules.inventory import contract as inventory_contract  # type: ignore

        getter = getattr(inventory_contract, "get_replenishment_request", None)
    except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
        raise BusinessException(CODE_CONTRACT_NOT_READY, "库存补库需求接口尚未就绪") from exc
    if getter is None:
        raise BusinessException(CODE_CONTRACT_NOT_READY, "库存补库需求接口尚未就绪")

    request = getter(db, request_id)

    def _field(name: str, default: Any = None) -> Any:
        if isinstance(request, Mapping):
            return request.get(name, default)
        return getattr(request, name, default)

    return create_demand(
        db,
        source_type="STOCKFILL",
        material_id=int(_field("material_id")),
        quantity=_as_decimal(_field("request_qty")),
        due_date=_to_date(_field("required_date"), date.today()),
        source_reference_id=request_id,
        source_no=_field("request_no"),
        remark=_field("remark"),
        operator_id=operator_id,
    )


# ==================== MPS ====================


def list_mps(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    year: Optional[int] = None,
) -> Tuple[List[models.PlnMps], int]:
    return repository.list_mps(db, page, page_size, status, year)


def get_mps(db: Session, mps_id: int) -> models.PlnMps:
    return _require_mps(db, mps_id)


def _create_mps_record(
    db: Session,
    *,
    mps_no: Optional[str],
    mps_name: Optional[str],
    program_no: Optional[str],
    plan_year: int,
    start_date: date,
    end_date: date,
    remark: Optional[str],
    items: Sequence[Mapping[str, Any]],
    operator_id: Optional[int],
) -> models.PlnMps:
    """写入 MPS 头 + 明细（内部复用，不写日志）。"""
    if start_date > end_date:
        raise BusinessException(CODE_PARAM_INVALID, "计划开始日期不能晚于结束日期")
    number = _unique_no(db, models.PlnMps, "mps_no", mps_no, "MPS")
    mps = models.PlnMps(
        mps_no=number,
        mps_name=mps_name,
        program_no=program_no,
        plan_year=plan_year,
        start_date=start_date,
        end_date=end_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_mps(db, mps)
    for raw in items:
        material_id = int(raw["material_id"])
        _require_material(db, material_id)
        qty = _as_decimal(raw.get("planned_qty"))
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "MPS 计划数量必须为正数")
        item_start = _to_date(raw.get("start_date"), start_date)
        item_end = _to_date(raw.get("end_date"), end_date)
        if item_start > item_end:
            raise BusinessException(CODE_PARAM_INVALID, f"物料 {material_id} 计划起止日期非法")
        repository.add_mps_item(
            db,
            models.PlnMpsItem(
                mps_id=mps.id,
                material_id=material_id,
                period_label=raw.get("period_label"),
                planned_qty=qty,
                finished_qty=Decimal("0"),
                start_date=item_start,
                end_date=item_end,
                status="DRAFT",
                remark=raw.get("remark"),
            ),
        )
    return mps


def create_mps(db: Session, payload: Any, operator_id: Optional[int] = None) -> models.PlnMps:
    """新增 MPS（头 + 行）。"""
    items = [item.model_dump() for item in payload.items]
    mps = _create_mps_record(
        db,
        mps_no=payload.mps_no,
        mps_name=payload.mps_name,
        program_no=payload.program_no,
        plan_year=payload.plan_year,
        start_date=payload.start_date,
        end_date=payload.end_date,
        remark=payload.remark,
        items=items,
        operator_id=operator_id,
    )
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pln_mps",
        target_id=mps.id,
        operator_id=operator_id,
        detail=f"新增 MPS {mps.mps_no}（{len(items)} 行）",
    )
    return mps


def update_mps(
    db: Session, mps_id: int, payload: Any, operator_id: Optional[int] = None
) -> models.PlnMps:
    """修改 MPS：仅 DRAFT 可改，已确认/已下达只读（报 3002）。"""
    mps = _require_mps(db, mps_id)
    if mps.status != "DRAFT":
        raise BusinessException(CODE_MPS_LOCKED, f"MPS 已处于 {mps.status}，不允许修改")
    if payload.mps_name is not None:
        mps.mps_name = payload.mps_name
    if payload.program_no is not None:
        mps.program_no = payload.program_no
    if payload.plan_year is not None:
        mps.plan_year = payload.plan_year
    if payload.start_date is not None:
        mps.start_date = payload.start_date
    if payload.end_date is not None:
        mps.end_date = payload.end_date
    if payload.remark is not None:
        mps.remark = payload.remark
    if mps.start_date > mps.end_date:
        raise BusinessException(CODE_PARAM_INVALID, "计划开始日期不能晚于结束日期")
    if payload.items is not None:
        repository.delete_mps_items(db, mps_id)
        for item in payload.items:
            raw = item.model_dump()
            _require_material(db, raw["material_id"])
            repository.add_mps_item(
                db,
                models.PlnMpsItem(
                    mps_id=mps.id,
                    material_id=raw["material_id"],
                    period_label=raw.get("period_label"),
                    planned_qty=_as_decimal(raw["planned_qty"]),
                    finished_qty=Decimal("0"),
                    start_date=raw["start_date"],
                    end_date=raw["end_date"],
                    status="DRAFT",
                    remark=raw.get("remark"),
                ),
            )
    mps.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="pln_mps",
        target_id=mps.id,
        operator_id=operator_id,
        detail=f"修改 MPS {mps.mps_no}",
    )
    return mps


def delete_mps(db: Session, mps_id: int, operator_id: Optional[int] = None) -> None:
    """删除 MPS：仅 DRAFT 可删。"""
    mps = _require_mps(db, mps_id)
    if mps.status != "DRAFT":
        raise BusinessException(CODE_MPS_LOCKED, f"MPS 已处于 {mps.status}，不允许删除")
    number = mps.mps_no
    repository.delete_mps_items(db, mps_id)
    db.delete(mps)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="pln_mps",
        target_id=mps_id,
        operator_id=operator_id,
        detail=f"删除 MPS {number}",
    )


def set_mps_status(
    db: Session, mps_id: int, status: str, operator_id: Optional[int] = None
) -> models.PlnMps:
    """MPS 状态机：DRAFT → CONFIRMED → RELEASED → IN_PROGRESS → COMPLETED（+ CANCELLED）。"""
    _validate_status(status, _MPS_STATUSES)
    mps = _require_mps(db, mps_id)
    _validate_transition(mps.status, status, _MAIN_TRANSITIONS, "MPS")
    mps.status = status
    mps.updated_by = operator_id
    for item in repository.get_mps_items(db, mps_id):
        item.status = status
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="pln_mps",
        target_id=mps.id,
        operator_id=operator_id,
        detail=f"MPS {mps.mps_no} 状态改为 {status}",
    )
    return mps


# ---------------- MPS 课程附录 1 导入 ----------------


def _course_case_rows(plan_year: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """读取 `data/seed/course_chair_case.json`，按月份展开为导入行。

    **所有数量均来自 JSON 载荷**（每月计划产量、月份数、成品物料编码），
    服务端不做任何数字硬编码；计划日期由年度 + 月份推导。
    """
    path = Path(__file__).resolve().parents[4] / "data" / "seed" / "course_chair_case.json"
    if not path.exists():
        raise BusinessException(CODE_NOT_FOUND, f"内置案例文件不存在：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    course = payload.get("course_data", {})
    product = course.get("product", {})
    mps = course.get("mps", {})
    material_code = product.get("material_code")
    monthly_qty = _as_decimal(mps.get("monthly_plan_quantity"))
    month_count = int(mps.get("month_count") or 0)
    if not material_code or monthly_qty <= 0 or month_count <= 0:
        raise BusinessException(CODE_IMPORT_INVALID, "内置案例缺少成品编码/月产量/月份数")
    rows: List[Dict[str, Any]] = []
    for idx in range(month_count):
        month = idx + 1
        rows.append(
            {
                "row_index": idx,
                "material_code": material_code,
                "period_label": f"{plan_year}-{month:02d}",
                "planned_qty": monthly_qty,
                "start_date": date(plan_year, month, 1),
                "end_date": _month_end(plan_year, month),
            }
        )
    return rows, product


def _resolve_import_rows(db: Session, request: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, Dict[str, Any]]:
    """把导入请求解析成带物料ID的规范行，并做逐行校验。

    返回 `(valid_rows, errors, plan_year, product_info)`；**不写库**。
    """
    plan_year = int(request.plan_year or date.today().year)
    product: Dict[str, Any] = {}
    raw_rows: List[Dict[str, Any]] = []
    if request.rows:
        for idx, row in enumerate(request.rows):
            item = row.model_dump()
            item["row_index"] = idx
            raw_rows.append(item)
    elif request.source == COURSE_CASE_SOURCE:
        raw_rows, product = _course_case_rows(plan_year)
    elif request.source:
        raise BusinessException(CODE_PARAM_INVALID, f"未知的内置数据源：{request.source}")
    else:
        raise BusinessException(CODE_PARAM_INVALID, "必须提供 source 或 rows")

    valid_rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for row in raw_rows:
        row_index = int(row["row_index"])
        code = str(row.get("material_code") or "").strip()
        material = find_material_by_code(db, code) if code else None
        if not code:
            errors.append({"row": row_index, "message": "物料编码不能为空"})
            continue
        if not material:
            errors.append({"row": row_index, "message": f"物料编码不存在：{code}"})
            continue
        qty = _as_decimal(row.get("planned_qty"))
        if qty <= 0:
            errors.append({"row": row_index, "message": "计划数量必须为正数"})
            continue
        start = _to_date(row.get("start_date"))
        end = _to_date(row.get("end_date"))
        if not start or not end:
            errors.append({"row": row_index, "message": "计划起止日期缺失或格式非法"})
            continue
        if start > end:
            errors.append({"row": row_index, "message": "计划开始日期不能晚于结束日期"})
            continue
        valid_rows.append(
            {
                "row_index": row_index,
                "material_code": code,
                "material_id": material["id"],
                "material_name": material["material_name"],
                "period_label": row.get("period_label"),
                "planned_qty": qty,
                "start_date": start,
                "end_date": end,
            }
        )
    return valid_rows, errors, plan_year, product


def preview_mps_import(db: Session, request: Any) -> Dict[str, Any]:
    """MPS 导入预览：只校验、只读、**不落库**。"""
    valid_rows, errors, plan_year, _ = _resolve_import_rows(db, request)
    summary = {
        "total_rows": len(valid_rows) + len(errors),
        "valid_count": len(valid_rows),
        "error_count": len(errors),
        "plan_year": plan_year,
        "start_date": min((row["start_date"] for row in valid_rows), default=None),
        "end_date": max((row["end_date"] for row in valid_rows), default=None),
    }
    return {"valid_rows": valid_rows, "errors": errors, "summary": summary}


def confirm_mps_import(
    db: Session, request: Any, operator_id: Optional[int] = None
) -> models.PlnMps:
    """MPS 导入确认：校验通过后写入 MPS 头 + 行。"""
    valid_rows, errors, plan_year, product = _resolve_import_rows(db, request)
    if errors:
        raise BusinessException(CODE_IMPORT_INVALID, f"存在 {len(errors)} 行校验失败，已中止导入")
    if not valid_rows:
        raise BusinessException(CODE_IMPORT_INVALID, "没有可导入的有效行")
    material_names = {row["material_name"] for row in valid_rows}
    default_name = (
        f"{next(iter(material_names))}主生产计划" if len(material_names) == 1 else "MPS 导入"
    )
    if product.get("material_name") and len(material_names) == 1:
        default_name = f"{product['material_name']}主生产计划"
    mps = _create_mps_record(
        db,
        mps_no=request.mps_no,
        mps_name=request.mps_name or default_name,
        program_no=request.program_no,
        plan_year=plan_year,
        start_date=min(row["start_date"] for row in valid_rows),
        end_date=max(row["end_date"] for row in valid_rows),
        remark=request.remark,
        items=valid_rows,
        operator_id=operator_id,
    )
    log_operation(
        db,
        module=MODULE,
        action="IMPORT",
        target_type="pln_mps",
        target_id=mps.id,
        operator_id=operator_id,
        detail=f"导入 MPS {mps.mps_no}（{len(valid_rows)} 行）",
    )
    return mps


# ==================== MRP 运算 ====================


def _accumulate(
    target: Dict[int, Dict[str, Any]],
    material_id: int,
    gross: Decimal,
    level: int,
    parent_material_id: Optional[int],
    requirement_date: date,
    ancestors: set,
) -> None:
    """把一条需求累加进展开映射。

    聚合规则（规格 §13，同一层内）：
    - **毛需求求和**；
    - **需求日期取最早**（对净需求与下达日期更保守）；
    - **父件取首次出现的父件**，用于结果回溯展示；
    - `ancestors` 为该分支的祖先物料集合，用于循环检测（首次出现的路径为准）。
    """
    entry = target.get(material_id)
    if entry is None:
        target[material_id] = {
            "gross": gross,
            "level": level,
            "parent_material_id": parent_material_id,
            "requirement_date": requirement_date,
            "ancestors": set(ancestors),
        }
        return
    entry["gross"] += gross
    if requirement_date < entry["requirement_date"]:
        entry["requirement_date"] = requirement_date


def _explode_level(
    db: Session,
    level_map: Dict[int, Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """用**父件的净需求（建议下达量）**展开下一层直接子件。

    子件毛需求 = 父件净需求 × 单位用量 × (1 + 损耗率)；
    子件需求日期 = 父件需求日期 − 提前期偏置（`lead_time_offset`）。
    """
    next_map: Dict[int, Dict[str, Any]] = {}
    for material_id, entry in level_map.items():
        order_qty = entry["order_qty"]
        # 无净需求则不下达计划，也无需产生子件需求（标准 MRP 净算逻辑）
        if order_qty <= 0:
            continue
        parent_date = entry["requirement_date"]
        for child in get_active_bom_children(db, material_id, on_date=parent_date):
            child_id = int(child["child_material_id"])
            if child_id == material_id or child_id in entry["ancestors"]:
                raise BusinessException(CODE_BOM_CYCLE, "BOM 存在循环引用，无法展开")
            qty = _as_decimal(child["quantity"])
            scrap = _as_decimal(child["scrap_rate"])
            offset = int(child["lead_time_offset"] or 0)
            child_gross = order_qty * qty * (Decimal("1") + scrap)
            child_date = _days_before(parent_date, offset)
            _accumulate(
                next_map,
                child_id,
                child_gross,
                entry["level"] + 1,
                material_id,
                child_date,
                entry["ancestors"] | {material_id},
            )
    return next_map


def _collect_level0(
    db: Session,
    mps_id: Optional[int],
    demand_ids: Sequence[int],
    include_sales_demand: bool,
) -> Dict[int, Dict[str, Any]]:
    """归集第 0 层毛需求：MPS + 计划需求 + （可选）销售订单需求。"""
    level0: Dict[int, Dict[str, Any]] = {}

    if mps_id is not None:
        mps = _require_mps(db, mps_id)
        for item in repository.get_mps_items(db, mps.id):
            qty = _as_decimal(item.planned_qty)
            if qty <= 0:
                continue
            _accumulate(
                level0, item.material_id, qty, 0, None, item.end_date, set()
            )

    if demand_ids:
        demands = repository.get_demands_by_ids(db, demand_ids)
        found = {d.id for d in demands}
        missing = [i for i in demand_ids if i not in found]
        if missing:
            raise BusinessException(CODE_NOT_FOUND, f"需求不存在：{missing}")
        for demand in demands:
            if demand.status not in {"CONFIRMED", "RELEASED"}:
                continue
            _accumulate(
                level0,
                demand.material_id,
                _as_decimal(demand.quantity),
                0,
                None,
                demand.due_date,
                set(),
            )

    if include_sales_demand:
        try:
            from app.modules.sales.contract import get_open_order_demand  # type: ignore
        except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
            raise BusinessException(CODE_CONTRACT_NOT_READY, "销售需求接口尚未就绪") from exc
        for row in get_open_order_demand(db) or []:
            material_id = int(row["material_id"])
            qty = _as_decimal(row.get("quantity") or row.get("order_qty"))
            if qty <= 0:
                continue
            due = _to_date(
                row.get("due_date")
                or row.get("required_date")
                or row.get("delivery_date")
                or row.get("order_date"),
                date.today(),
            )
            _accumulate(level0, material_id, qty, 0, None, due, set())

    return level0


def run_mrp(
    db: Session,
    *,
    mps_id: Optional[int] = None,
    demand_ids: Optional[Sequence[int]] = None,
    include_sales_demand: bool = False,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnMrpRun:
    """执行一次 MRP 运算（真实计算，**每次运算独立批次，绝不覆盖历史结果**）。

    算法（规格 §13 / §17）：

    1. **第 0 层毛需求**来自 MPS 行（`planned_qty` / `end_date`）、
       指定 `pln_demand`（状态 CONFIRMED/RELEASED）与（可选）销售订单需求。
    2. **逐层展开（广度优先）**：对每层物料先做净算，再用**父件的净需求**
       （而非毛需求）展开下一层：`子件毛需求 = 父件净需求 × 用量 × (1 + 损耗率)`，
       `子件需求日期 = 父件需求日期 − lead_time_offset`。无生效 BOM 的物料为叶子，停止展开。
       同一层内若某物料有多个父件，则**毛需求求和、需求日期取最早、父件取首次出现者**。
       分支祖先路径上重现物料即判定 **BOM 循环**，抛 3001。
    3. **净算**：`可用库存` 来自 `inventory.contract.get_stock_snapshot`，
       `安全库存 / 提前期` 来自 `system.contract.get_materials`：
       `净需求 = max(毛需求 + 安全库存 − 可用库存, 0)`，`建议下达量 = 净需求`，
       `建议下达日期 = 需求日期 − 提前期天数`，`供应类型` 取物料 `supply_type`。
    4. **可用库存只在本批次内消耗一次**：维护 `remaining_available[material_id]`，
       某物料每次净算消耗 `min(剩余可用, 毛需求 + 安全库存)`，剩余量再供后续出现使用，
       因此同一物料出现两次不会被重复抵扣库存。
    5. 落库：写入一个 `pln_mrp_run`（IN_PROGRESS → COMPLETED）与其全部结果行。
    """
    demand_ids = list(demand_ids or [])
    if mps_id is None and not demand_ids and not include_sales_demand:
        raise BusinessException(
            CODE_PARAM_INVALID, "MRP 运算至少需要提供 mps_id / demand_ids / include_sales_demand"
        )

    level_map = _collect_level0(db, mps_id, demand_ids, include_sales_demand)

    run = models.PlnMrpRun(
        run_no=_unique_no(db, models.PlnMrpRun, "run_no", None, "MRP"),
        mps_id=mps_id,
        run_at=datetime.now(),
        status="IN_PROGRESS",
        material_count=0,
        remark=remark,
        created_by=operator_id,
    )
    repository.add_mrp_run(db, run)

    results: List[models.PlnMrpResult] = []
    remaining_available: Dict[int, Decimal] = {}
    touched: set = set()

    while level_map:
        material_ids = list(level_map.keys())
        materials = get_materials(db, material_ids)
        snapshot = get_stock_snapshot(db, material_ids)
        for material_id, entry in level_map.items():
            material = materials.get(material_id)
            if not material:
                raise BusinessException(CODE_NOT_FOUND, f"物料不存在：{material_id}")
            touch = snapshot.get(material_id, {})
            on_hand = _as_decimal(touch.get("on_hand"))
            if material_id not in remaining_available:
                remaining_available[material_id] = _as_decimal(touch.get("available"))
            usable = remaining_available[material_id]

            gross = _as_decimal(entry["gross"])
            safety = _as_decimal(material.get("safety_stock"))
            lead_time = int(material.get("lead_time_days") or 0)
            net = gross + safety - usable
            if net < 0:
                net = Decimal("0")
            # 本行消耗的可用库存；剩余额度保留给本批次后续出现的同一物料
            consumed = usable if usable < gross + safety else gross + safety
            remaining_available[material_id] = usable - consumed

            requirement_date = entry["requirement_date"]
            results.append(
                models.PlnMrpResult(
                    run_id=run.id,
                    material_id=material_id,
                    parent_material_id=entry["parent_material_id"],
                    bom_level=entry["level"],
                    gross_requirement=gross,
                    on_hand=on_hand,
                    available_quantity=usable,
                    safety_stock=safety,
                    net_requirement=net,
                    order_qty=net,
                    supply_type=material.get("supply_type") or "BUY",
                    lead_time_days=lead_time,
                    requirement_date=requirement_date,
                    planned_release_date=_days_before(requirement_date, lead_time),
                    status="DRAFT",
                    created_by=operator_id,
                )
            )
            # 记录净需求，供下一层展开使用（子件毛需求来源于父件净需求）
            entry["order_qty"] = net
            touched.add(material_id)
        level_map = _explode_level(db, level_map)

    repository.add_mrp_results(db, results)
    run.material_count = len(touched)
    run.status = "COMPLETED"
    run.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="RUN",
        target_type="pln_mrp_run",
        target_id=run.id,
        operator_id=operator_id,
        detail=f"MRP 运算 {run.run_no}，涉及 {len(touched)} 个物料，{len(results)} 条结果",
    )
    return run


def list_mrp_runs(
    db: Session, page: int = 1, page_size: int = 20
) -> Tuple[List[models.PlnMrpRun], int]:
    return repository.list_mrp_runs(db, page, page_size)


def get_mrp_run(db: Session, run_id: int) -> models.PlnMrpRun:
    return _require_run(db, run_id)


def list_mrp_results(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    run_id: Optional[int] = None,
    supply_type: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[List[models.PlnMrpResult], int]:
    return repository.list_mrp_results(db, page, page_size, run_id, supply_type, status)


def explain_mrp_result(db: Session, run_id: int, material_id: int) -> Dict[str, Any]:
    """MRP 计算明细：展示某物料在某批次内的完整推导（毛需求 → 净需求）。"""
    _require_run(db, run_id)
    result = repository.find_run_result(db, run_id, material_id)
    if not result:
        raise BusinessException(CODE_NOT_FOUND, f"该批次中不存在物料 {material_id} 的计算结果")
    materials = get_materials(
        db, [result.material_id, result.parent_material_id or result.material_id]
    )
    material = materials.get(result.material_id, {})
    parent = materials.get(result.parent_material_id or -1, {})
    return {
        "mrp_result_id": result.id,
        "run_id": result.run_id,
        "material_id": result.material_id,
        "material_code": material.get("material_code"),
        "material_name": material.get("material_name"),
        "parent_material_id": result.parent_material_id,
        "parent_material_code": parent.get("material_code"),
        "parent_material_name": parent.get("material_name"),
        "bom_level": result.bom_level,
        "gross_requirement": _as_decimal(result.gross_requirement),
        "on_hand": _as_decimal(result.on_hand),
        "available_quantity": _as_decimal(result.available_quantity),
        "safety_stock": _as_decimal(result.safety_stock),
        "net_requirement": _as_decimal(result.net_requirement),
        "order_qty": _as_decimal(result.order_qty),
        "supply_type": result.supply_type,
        "lead_time_days": result.lead_time_days,
        "requirement_date": result.requirement_date,
        "planned_release_date": result.planned_release_date,
        "status": result.status,
        "formula": (
            f"净需求 = max(毛需求 {_as_decimal(result.gross_requirement)} "
            f"+ 安全库存 {_as_decimal(result.safety_stock)} "
            f"− 可用库存 {_as_decimal(result.available_quantity)}, 0) "
            f"= {_as_decimal(result.net_requirement)}"
        ),
    }


def set_mrp_result_status(
    db: Session, result_id: int, status: str, operator_id: Optional[int] = None
) -> models.PlnMrpResult:
    """MRP 结果状态流转（默认 DRAFT；下达后置 RELEASED）。"""
    _validate_status(status, _MRP_RESULT_STATUSES)
    result = _require_mrp_result(db, result_id)
    result.status = status
    result.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="pln_mrp_result",
        target_id=result.id,
        operator_id=operator_id,
        detail=f"MRP 结果 {result.id} 状态改为 {status}",
    )
    return result


def create_purchase_plan_from_run(
    db: Session, run_id: int, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    """把某批次的 BUY 结果交给 Procurement 生成采购计划，并把这些结果置 RELEASED。"""
    run = _require_run(db, run_id)
    results = repository.get_mrp_results(db, run.id)
    buy_results = [
        r
        for r in results
        if r.supply_type == "BUY" and _as_decimal(r.order_qty) > 0 and r.status not in {"RELEASED", "CANCELLED"}
    ]
    if not buy_results:
        raise BusinessException(CODE_PARAM_INVALID, "该批次没有可下达的采购件需求")
    try:
        from app.modules.procurement.contract import (  # type: ignore
            create_purchase_plan_from_mrp,
        )
    except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
        raise BusinessException(CODE_CONTRACT_NOT_READY, "采购计划接口尚未就绪") from exc
    result = create_purchase_plan_from_mrp(db, [r.id for r in buy_results])
    for row in buy_results:
        row.status = "RELEASED"
        row.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="RELEASE",
        target_type="pln_mrp_run",
        target_id=run.id,
        operator_id=operator_id,
        detail=f"批次 {run.run_no} 下达采购计划，{len(buy_results)} 条 BUY 结果",
    )
    return {"mrp_run_id": run.id, "released_count": len(buy_results), "purchase_plan": result}


def create_production_plans_from_run(
    db: Session, run_id: int, operator_id: Optional[int] = None
) -> List[models.PlnProductionPlan]:
    """把某批次的 MAKE 结果生成生产作业计划，并把结果置 RELEASED。"""
    run = _require_run(db, run_id)
    plans: List[models.PlnProductionPlan] = []
    for result in repository.get_mrp_results(db, run.id):
        if result.supply_type != "MAKE" or _as_decimal(result.net_requirement) <= 0:
            continue
        if result.status in {"RELEASED", "CANCELLED"}:
            continue
        plans.append(_create_plan_from_mrp_result(db, result, operator_id=operator_id))
        result.status = "RELEASED"
        result.updated_by = operator_id
    if not plans:
        raise BusinessException(CODE_PARAM_INVALID, "该批次没有可下达的自制件需求")
    log_operation(
        db,
        module=MODULE,
        action="RELEASE",
        target_type="pln_mrp_run",
        target_id=run.id,
        operator_id=operator_id,
        detail=f"批次 {run.run_no} 下达生产作业计划 {len(plans)} 条",
    )
    return plans


# ==================== 生产作业计划 ====================


def list_production_plans(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    material_id: Optional[int] = None,
) -> Tuple[List[models.PlnProductionPlan], int]:
    return repository.list_production_plans(db, page, page_size, status, material_id)


def get_production_plan(db: Session, plan_id: int) -> models.PlnProductionPlan:
    return _require_plan(db, plan_id)


def _create_plan_from_mrp_result(
    db: Session, result: models.PlnMrpResult, operator_id: Optional[int] = None
) -> models.PlnProductionPlan:
    """由 MRP MAKE 结果生成作业计划（供 service 与 contract 共用，内部不提交）。"""
    release_date = result.planned_release_date or result.requirement_date
    plan = models.PlnProductionPlan(
        plan_no=_unique_no(db, models.PlnProductionPlan, "plan_no", None, "PLN"),
        mrp_result_id=result.id,
        source_type="MRP",
        source_reference_id=result.run_id,
        material_id=result.material_id,
        planned_qty=_as_decimal(result.order_qty),
        completed_qty=Decimal("0"),
        plan_date=release_date,
        start_date=release_date,
        end_date=result.requirement_date,
        status="DRAFT",
        remark=f"由 MRP 结果 {result.id} 生成",
        created_by=operator_id,
    )
    repository.add_production_plan(db, plan)
    return plan


def create_production_plan(
    db: Session,
    *,
    material_id: int,
    planned_qty: Decimal,
    plan_date: date,
    start_date: date,
    end_date: date,
    mrp_result_id: Optional[int] = None,
    source_type: str = "MANUAL",
    source_reference_id: Optional[int] = None,
    plan_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnProductionPlan:
    """手工新增生产作业计划。"""
    material = _require_material(db, material_id)
    if material["supply_type"] != "MAKE":
        raise BusinessException(CODE_PARAM_INVALID, f"物料 {material_id} 不是自制件，不能建作业计划")
    qty = _as_decimal(planned_qty)
    if qty <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "计划数量必须为正数")
    if start_date > end_date:
        raise BusinessException(CODE_PARAM_INVALID, "计划开始日期不能晚于结束日期")
    plan = models.PlnProductionPlan(
        plan_no=_unique_no(db, models.PlnProductionPlan, "plan_no", plan_no, "PLN"),
        mrp_result_id=mrp_result_id,
        source_type=source_type,
        source_reference_id=source_reference_id,
        material_id=material_id,
        planned_qty=qty,
        completed_qty=Decimal("0"),
        plan_date=plan_date,
        start_date=start_date,
        end_date=end_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_production_plan(db, plan)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pln_production_plan",
        target_id=plan.id,
        operator_id=operator_id,
        detail=f"新增生产作业计划 {plan.plan_no}",
    )
    return plan


def update_production_plan(
    db: Session, plan_id: int, payload: Any, operator_id: Optional[int] = None
) -> models.PlnProductionPlan:
    """修改作业计划：仅 DRAFT 可改。"""
    plan = _require_plan(db, plan_id)
    if plan.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, f"作业计划已处于 {plan.status}，不允许修改")
    if payload.planned_qty is not None:
        plan.planned_qty = _as_decimal(payload.planned_qty)
    if payload.plan_date is not None:
        plan.plan_date = payload.plan_date
    if payload.start_date is not None:
        plan.start_date = payload.start_date
    if payload.end_date is not None:
        plan.end_date = payload.end_date
    if payload.remark is not None:
        plan.remark = payload.remark
    if plan.start_date > plan.end_date:
        raise BusinessException(CODE_PARAM_INVALID, "计划开始日期不能晚于结束日期")
    plan.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="pln_production_plan",
        target_id=plan.id,
        operator_id=operator_id,
        detail=f"修改生产作业计划 {plan.plan_no}",
    )
    return plan


def set_production_plan_status(
    db: Session, plan_id: int, status: str, operator_id: Optional[int] = None
) -> models.PlnProductionPlan:
    """作业计划状态机。"""
    _validate_status(status, _PLAN_STATUSES)
    plan = _require_plan(db, plan_id)
    _validate_transition(plan.status, status, _MAIN_TRANSITIONS, "生产作业计划")
    plan.status = status
    plan.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="pln_production_plan",
        target_id=plan.id,
        operator_id=operator_id,
        detail=f"作业计划 {plan.plan_no} 状态改为 {status}",
    )
    return plan


def create_production_plans_from_mrp(
    db: Session, mrp_result_ids: Sequence[int], operator_id: Optional[int] = None
) -> List[models.PlnProductionPlan]:
    """按 MRP 结果ID 批量生成作业计划（供 `/production-plans/from-mrp`）。"""
    ids = [int(i) for i in mrp_result_ids]
    if not ids:
        raise BusinessException(CODE_PARAM_INVALID, "mrp_result_ids 不能为空")
    results = repository.get_mrp_results_by_ids(db, ids)
    found = {r.id for r in results}
    missing = [i for i in ids if i not in found]
    if missing:
        raise BusinessException(CODE_NOT_FOUND, f"MRP 结果不存在：{missing}")
    plans: List[models.PlnProductionPlan] = []
    for result in results:
        if result.supply_type != "MAKE":
            raise BusinessException(CODE_PARAM_INVALID, f"MRP 结果 {result.id} 不是自制件")
        if _as_decimal(result.order_qty) <= 0:
            raise BusinessException(CODE_PARAM_INVALID, f"MRP 结果 {result.id} 净需求为 0，无需下达")
        if repository.find_plan_by_mrp_result(db, result.id):
            raise BusinessException(CODE_DUPLICATE, f"MRP 结果 {result.id} 已生成作业计划")
        plans.append(_create_plan_from_mrp_result(db, result, operator_id=operator_id))
        result.status = "RELEASED"
        result.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pln_production_plan",
        target_id=plans[0].id if plans else None,
        operator_id=operator_id,
        detail=f"由 MRP 结果生成作业计划 {len(plans)} 条",
    )
    return plans


# ==================== 派工单 ====================


def list_dispatch_orders(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
) -> Tuple[List[models.PlnDispatchOrder], int]:
    return repository.list_dispatch_orders(db, page, page_size, status, plan_id)


def get_dispatch_order(db: Session, dispatch_id: int) -> models.PlnDispatchOrder:
    return _require_dispatch(db, dispatch_id)


def create_dispatch_order(
    db: Session,
    *,
    planned_qty: Decimal,
    planned_start: date,
    planned_end: date,
    plan_id: Optional[int] = None,
    operation: Optional[str] = None,
    worker_id: Optional[int] = None,
    dispatch_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnDispatchOrder:
    """新增派工单；`worker_id` 指向 `sys_personnel.id` 并通过 system 契约校验。"""
    qty = _as_decimal(planned_qty)
    if qty <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "派工数量必须为正数")
    if planned_start > planned_end:
        raise BusinessException(CODE_PARAM_INVALID, "计划开始日期不能晚于结束日期")
    if plan_id is not None:
        _require_plan(db, plan_id)
    if worker_id is not None and not get_personnel(db, worker_id):
        raise BusinessException(CODE_NOT_FOUND, f"作业人员不存在：{worker_id}")
    dispatch = models.PlnDispatchOrder(
        dispatch_no=_unique_no(db, models.PlnDispatchOrder, "dispatch_no", dispatch_no, "DSP"),
        plan_id=plan_id,
        operation=operation,
        planned_qty=qty,
        completed_qty=Decimal("0"),
        worker_id=worker_id,
        planned_start=planned_start,
        planned_end=planned_end,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_dispatch_order(db, dispatch)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pln_dispatch_order",
        target_id=dispatch.id,
        operator_id=operator_id,
        detail=f"新增派工单 {dispatch.dispatch_no}",
    )
    return dispatch


def set_dispatch_order_status(
    db: Session, dispatch_id: int, status: str, operator_id: Optional[int] = None
) -> models.PlnDispatchOrder:
    """派工单状态机。"""
    _validate_status(status, _DISPATCH_STATUSES)
    dispatch = _require_dispatch(db, dispatch_id)
    _validate_transition(dispatch.status, status, _MAIN_TRANSITIONS, "派工单")
    dispatch.status = status
    dispatch.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="pln_dispatch_order",
        target_id=dispatch.id,
        operator_id=operator_id,
        detail=f"派工单 {dispatch.dispatch_no} 状态改为 {status}",
    )
    return dispatch


# ==================== 领料单 ====================


def list_requisitions(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
) -> Tuple[List[models.PlnMaterialRequisition], int]:
    return repository.list_requisitions(db, page, page_size, status, plan_id)


def get_requisition(db: Session, req_id: int) -> models.PlnMaterialRequisition:
    return _require_requisition(db, req_id)


def create_requisition(
    db: Session,
    *,
    req_date: date,
    items: Sequence[Mapping[str, Any]],
    plan_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    req_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnMaterialRequisition:
    """新增领料单（头 + 行），默认 DRAFT。"""
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "领料单至少需要一条明细")
    if plan_id is not None:
        _require_plan(db, plan_id)
    req = models.PlnMaterialRequisition(
        req_no=_unique_no(db, models.PlnMaterialRequisition, "req_no", req_no, "REQ"),
        plan_id=plan_id,
        warehouse_id=warehouse_id,
        req_date=req_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_requisition(db, req)
    for raw in items:
        material_id = int(raw["material_id"])
        _require_material(db, material_id)
        qty = _as_decimal(raw.get("required_qty"))
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "领料需求数量必须为正数")
        repository.add_requisition_item(
            db,
            models.PlnMaterialRequisitionItem(
                requisition_id=req.id,
                material_id=material_id,
                required_qty=qty,
                issued_qty=Decimal("0"),
                location_id=raw.get("location_id"),
                remark=raw.get("remark"),
            ),
        )
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pln_material_requisition",
        target_id=req.id,
        operator_id=operator_id,
        detail=f"新增领料单 {req.req_no}",
    )
    return req


def confirm_requisition(
    db: Session, req_id: int, operator_id: Optional[int] = None
) -> models.PlnMaterialRequisition:
    """确认领料（原子）：逐行走 `inventory.contract.decrease_stock` 写真实出库流水。

    任一物料库存不足（inventory 抛 5001）则整体回滚，领料单状态与库存均不变。
    """
    req = _require_requisition(db, req_id)
    if req.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, f"领料单当前状态为 {req.status}，不能确认")
    if req.warehouse_id is None:
        raise BusinessException(CODE_PARAM_INVALID, "领料单未指定领料仓库，不能确认")
    items = repository.get_requisition_items(db, req_id)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "领料单没有明细，不能确认")
    for item in items:
        outstanding = _as_decimal(item.required_qty) - _as_decimal(item.issued_qty)
        if outstanding <= 0:
            continue
        decrease_stock(
            db,
            material_id=item.material_id,
            quantity=outstanding,
            warehouse_id=req.warehouse_id,
            location_id=item.location_id,
            source_module=MODULE,
            source_type="MATERIAL_REQUISITION",
            source_reference_id=req.id,
            source_no=req.req_no,
            biz_date=req.req_date,
            operator_id=operator_id,
            remark=f"生产领料 {req.req_no}",
        )
        item.issued_qty = _as_decimal(item.required_qty)
    req.status = "COMPLETED"
    req.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="pln_material_requisition",
        target_id=req.id,
        operator_id=operator_id,
        detail=f"确认领料单 {req.req_no}",
    )
    return req


def cancel_requisition(
    db: Session, req_id: int, operator_id: Optional[int] = None
) -> models.PlnMaterialRequisition:
    """取消领料单（DRAFT / CONFIRMED 可取消）。"""
    req = _require_requisition(db, req_id)
    if req.status not in {"DRAFT", "CONFIRMED"}:
        raise BusinessException(CODE_STATUS_INVALID, f"领料单当前状态为 {req.status}，不能取消")
    req.status = "CANCELLED"
    req.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="pln_material_requisition",
        target_id=req.id,
        operator_id=operator_id,
        detail=f"取消领料单 {req.req_no}",
    )
    return req


# ==================== 完工报告 ====================


def list_completion_reports(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
) -> Tuple[List[models.PlnCompletionReport], int]:
    return repository.list_completion_reports(db, page, page_size, status, plan_id)


def get_completion_report(db: Session, report_id: int) -> models.PlnCompletionReport:
    return _require_completion(db, report_id)


def create_completion_report(
    db: Session,
    *,
    material_id: int,
    completed_qty: Decimal,
    qualified_qty: Decimal,
    warehouse_id: int,
    report_date: date,
    plan_id: Optional[int] = None,
    dispatch_id: Optional[int] = None,
    location_id: Optional[int] = None,
    scrap_qty: Decimal = Decimal("0"),
    report_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnCompletionReport:
    """新增完工报告（默认 DRAFT），确认后才入库。"""
    _require_material(db, material_id)
    if plan_id is not None:
        _require_plan(db, plan_id)
    if dispatch_id is not None:
        _require_dispatch(db, dispatch_id)
    completed = _as_decimal(completed_qty)
    qualified = _as_decimal(qualified_qty)
    scrap = _as_decimal(scrap_qty)
    if completed <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "完工数量必须为正数")
    if qualified < 0 or scrap < 0:
        raise BusinessException(CODE_PARAM_INVALID, "合格数量与报废数量不能为负")
    if qualified > completed:
        raise BusinessException(CODE_PARAM_INVALID, "合格数量不能大于完工数量")
    report = models.PlnCompletionReport(
        report_no=_unique_no(db, models.PlnCompletionReport, "report_no", report_no, "CRP"),
        plan_id=plan_id,
        dispatch_id=dispatch_id,
        material_id=material_id,
        completed_qty=completed,
        qualified_qty=qualified,
        scrap_qty=scrap,
        warehouse_id=warehouse_id,
        location_id=location_id,
        report_date=report_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_completion_report(db, report)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pln_completion_report",
        target_id=report.id,
        operator_id=operator_id,
        detail=f"新增完工报告 {report.report_no}",
    )
    return report


def confirm_completion_report(
    db: Session, report_id: int, operator_id: Optional[int] = None
) -> models.PlnCompletionReport:
    """确认完工（原子）：走 `inventory.contract.increase_stock` 写真实入库流水，
    并回写作业计划 / 派工单的已完工数量。"""
    report = _require_completion(db, report_id)
    if report.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, f"完工报告当前状态为 {report.status}，不能确认")
    qualified = _as_decimal(report.qualified_qty)
    if qualified <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "合格数量为 0，无需入库")
    increase_stock(
        db,
        material_id=report.material_id,
        quantity=qualified,
        warehouse_id=report.warehouse_id,
        location_id=report.location_id,
        source_module=MODULE,
        source_type="PRODUCTION_COMPLETION",
        source_reference_id=report.id,
        source_no=report.report_no,
        biz_date=report.report_date,
        operator_id=operator_id,
        remark=f"生产完工入库 {report.report_no}",
    )
    if report.plan_id is not None:
        plan = repository.get_production_plan(db, report.plan_id)
        if plan:
            plan.completed_qty = _as_decimal(plan.completed_qty) + qualified
            plan.updated_by = operator_id
    if report.dispatch_id is not None:
        dispatch = repository.get_dispatch_order(db, report.dispatch_id)
        if dispatch:
            dispatch.completed_qty = _as_decimal(dispatch.completed_qty) + qualified
            dispatch.updated_by = operator_id
    report.status = "COMPLETED"
    report.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="pln_completion_report",
        target_id=report.id,
        operator_id=operator_id,
        detail=f"确认完工报告 {report.report_no}，入库 {qualified}",
    )
    return report


def cancel_completion_report(
    db: Session, report_id: int, operator_id: Optional[int] = None
) -> models.PlnCompletionReport:
    """取消完工报告（仅 DRAFT）。"""
    report = _require_completion(db, report_id)
    if report.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, f"完工报告当前状态为 {report.status}，不能取消")
    report.status = "CANCELLED"
    report.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="pln_completion_report",
        target_id=report.id,
        operator_id=operator_id,
        detail=f"取消完工报告 {report.report_no}",
    )
    return report


# ==================== 统计 ====================


def stats(db: Session) -> Dict[str, int]:
    """计划模块统计（供首页 / 综合查询使用）。"""
    return {
        "mps_count": repository.count_all(db, models.PlnMps),
        "mrp_run_count": repository.count_all(db, models.PlnMrpRun),
        "mrp_result_count": repository.count_all(db, models.PlnMrpResult),
        "make_count": repository.count_mrp_results_by_supply(db, "MAKE"),
        "buy_count": repository.count_mrp_results_by_supply(db, "BUY"),
        "open_plan_count": repository.count_open(db, models.PlnProductionPlan, _TERMINAL_STATUSES),
        "open_dispatch_count": repository.count_open(db, models.PlnDispatchOrder, _TERMINAL_STATUSES),
        "open_requisition_count": repository.count_open(
            db, models.PlnMaterialRequisition, _TERMINAL_STATUSES
        ),
        "completion_report_count": repository.count_all(db, models.PlnCompletionReport),
    }