"""planning 模块业务逻辑层（MPS 录入 + 多层 MRP 展开 + 车间计划执行）。

职责边界（规格 §1 / §7 / §13 / §14）：

- Planning **负责计划**：需求归集、MPS 录入、MRP 多层 BOM 展开、净需求计算、MAKE/BUY 分流。
- 生产业务（生产作业计划 / 派工 / 领料 / 完工）**统一归 Planning**，不建独立 Production 模块。
- Planning **不直接改库存**：领料 / 完工只向库存管理推送**待出库 / 待入库单**，
  由仓库管理人员在「库存管理 → 出库管理 / 入库管理」中指定仓库并确认后，结存才真正变动。
- 本层**不调用 `db.commit()`**：由 router 提交；contract 函数运行在调用方事务里。

错误码区段：`3000~3999`。
"""

import calendar
import json
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.inventory.contract import (
    cancel_pending_inout_orders,
    get_stock_snapshot,
    push_inbound_order,
    push_outbound_order,
)
from app.modules.planning import models, repository
from app.modules.system.contract import (
    find_material_by_code,
    get_active_bom_children,
    get_default_factory,
    get_material,
    get_materials,
    get_organization,
    get_organization_names,
    get_personnel,
    get_personnel_names,
    log_operation,
)

# ==================== 列表明细展示信息（编码 / 名称） ====================


def _material_fields(db: Session, material_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    """批量取物料，供列表展示编码与名称。"""
    return get_materials(db, [m for m in material_ids if m])


def _warehouse_fields(
    db: Session, warehouse_ids: Sequence[Optional[int]]
) -> Dict[int, Dict[str, str]]:
    """批量取仓库编码与名称（`inventory.contract`，惰性导入避免循环依赖）。"""
    try:
        from app.modules.inventory.contract import get_warehouse_names  # type: ignore
    except Exception:  # noqa: BLE001 - 库存模块未就绪时不阻断列表
        return {}
    return get_warehouse_names(db, [w for w in warehouse_ids if w])


def _attach_material(
    rows: Iterable[Any], materials: Dict[int, Dict[str, Any]], field: str = "material"
) -> None:
    """把 `material_code` / `material_name` 挂到 ORM 行上，供 Pydantic 直接读取。"""
    for row in rows:
        material_id = getattr(row, f"{field}_id", None)
        info = materials.get(int(material_id)) if material_id else None
        setattr(row, f"{field}_code", info["material_code"] if info else None)
        setattr(row, f"{field}_name", info["material_name"] if info else None)


def _attach_warehouse(rows: Iterable[Any], warehouses: Dict[int, Dict[str, str]]) -> None:
    for row in rows:
        warehouse_id = getattr(row, "warehouse_id", None)
        info = warehouses.get(int(warehouse_id)) if warehouse_id else None
        row.warehouse_code = info["warehouse_code"] if info else None
        row.warehouse_name = info["warehouse_name"] if info else None

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

#: 可物理删除的状态：仅草稿与已取消。
#: 已确认/已发布/进行中/已完成不可删（只能取消）；已写库存流水的单据更不可删。
_DELETABLE_STATUSES = {"DRAFT", "CANCELLED"}

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

#: 计入「本期计划量」的有效状态：排除 DRAFT 草稿与 CANCELLED 已取消
_ACTIVE_PLAN_STATUSES = ("CONFIRMED", "RELEASED", "IN_PROGRESS", "COMPLETED")

#: 计入「需求总量」的有效状态：排除 DRAFT 草稿与 CANCELLED 已取消
_ACTIVE_DEMAND_STATUSES = ("CONFIRMED", "RELEASED", "COMPLETED")


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


def _forecast_due_date(month: Any) -> Optional[date]:
    """预测期间（`YYYY-MM`）→ 需求日期：取该月最后一天，非法期间返回 None。

    预测按月汇总、没有逐日需求日期，取期末作为需求日期（最晚必须交付的时点），
    这样 MRP 的需求日期不会早于预测期本身。
    """
    parts = str(month or "").strip().split("-")
    if len(parts) < 2:
        return None
    try:
        return _month_end(int(parts[0]), int(parts[1]))
    except ValueError:
        return None


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


def _ensure_deletable(status: str, label: str) -> None:
    """删除前置校验：仅 DRAFT / CANCELLED 可物理删除，其余状态报状态机错误。"""
    if status not in _DELETABLE_STATUSES:
        raise BusinessException(
            CODE_STATUS_INVALID,
            f"{label}当前状态为 {status}，只有草稿或已取消的记录可以删除",
        )


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
    """分页查询需求（附带物料编码 / 名称）。"""
    rows, total = repository.list_demands(db, page, page_size, source_type, status)
    _attach_material(rows, _material_fields(db, [r.material_id for r in rows]))
    return rows, total


def get_demand(db: Session, demand_id: int) -> models.PlnDemand:
    demand = _require_demand(db, demand_id)
    _attach_material([demand], _material_fields(db, [demand.material_id]))
    return demand


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
    """新增需求（默认 DRAFT）。`source_type` 限定 SALES/FORECAST/STOCKFILL/MPS。"""
    _validate_status(source_type, {"SALES", "FORECAST", "STOCKFILL", "MPS"}, "需求来源")
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
    # 同一订单同一物料可能有多行，导入前先按「订单 + 物料」汇总，
    # 去重键也随之带 material_id（与订单确认时的缺口需求保持一致）。
    aggregated: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for row in rows:
        material_id = int(row["material_id"])
        source_reference_id = row.get("order_id") or row.get("id") or row.get("source_reference_id")
        if source_reference_id is None:
            continue
        key = (int(source_reference_id), material_id)
        bucket = aggregated.get(key)
        if bucket is None:
            aggregated[key] = {
                "source_reference_id": source_reference_id,
                "material_id": material_id,
                "quantity": _as_decimal(row.get("quantity") or row.get("order_qty")),
                "due": _to_date(
                    row.get("due_date")
                    or row.get("required_date")
                    or row.get("delivery_date")
                    or row.get("order_date"),
                    date.today(),
                ),
                "source_no": row.get("order_no") or row.get("source_no"),
                "remark": row.get("remark"),
            }
        else:
            bucket["quantity"] += _as_decimal(row.get("quantity") or row.get("order_qty"))

    created_ids: List[int] = []
    skipped = 0
    for item in aggregated.values():
        if repository.find_demand_by_source_material(
            db,
            "SALES",
            item["source_reference_id"],
            item["source_no"],
            item["material_id"],
        ):
            skipped += 1
            continue
        demand = create_demand(
            db,
            source_type="SALES",
            material_id=item["material_id"],
            quantity=item["quantity"],
            due_date=item["due"],
            source_reference_id=item["source_reference_id"],
            source_no=item["source_no"],
            remark=item["remark"],
            operator_id=operator_id,
        )
        created_ids.append(demand.id)
    return {"created_count": len(created_ids), "skipped_count": skipped, "demand_ids": created_ids}


def import_demands_from_forecast(
    db: Session,
    month_from: Optional[str] = None,
    month_to: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """把已确认销售预测拉取为 `source_type=FORECAST` 的计划需求（已导入的跳过）。

    预测与订单分属不同来源类型：MPS 汇总只取销售订单（`SALES`）与补库申请
    （`STOCKFILL`），因此预测需求不会进入 MPS。

    - 预测契约（`sales.contract.get_confirmed_forecast_demand`，只含 CONFIRMED）
      **惰性导入**，可用 `month_from` / `month_to`（`YYYY-MM`，含端点）限定期间；
    - 需求日期取预测月份的最后一天（见 `_forecast_due_date`）；
    - **不把预测与订单合并**：同一物料同一期间既有订单又有预测时，两条需求
      各自保留，净算由 MRP 按物料汇总，避免在需求侧做归属判断；
    - 去重键带来源单号：预测行 id 与订单 id 会重号（详见
      `repository.find_demand_by_source`），重复调用幂等。
    """
    try:
        from app.modules.sales.contract import get_confirmed_forecast_demand  # type: ignore
    except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
        raise BusinessException(CODE_CONTRACT_NOT_READY, "销售预测接口尚未就绪") from exc

    rows = get_confirmed_forecast_demand(db, month_from, month_to) or []
    created_ids: List[int] = []
    skipped = 0
    for row in rows:
        forecast_id = row.get("forecast_id") or row.get("id")
        forecast_no = row.get("forecast_no")
        month = row.get("month") or row.get("forecast_month")
        due = _forecast_due_date(month)
        if due is None:
            raise BusinessException(CODE_PARAM_INVALID, f"预测期间非法：{month}")
        if repository.find_demand_by_source(db, "FORECAST", forecast_id, forecast_no):
            skipped += 1
            continue
        demand = create_demand(
            db,
            source_type="FORECAST",
            material_id=int(row["material_id"]),
            quantity=_as_decimal(row.get("quantity") or row.get("forecast_qty")),
            due_date=due,
            source_reference_id=forecast_id,
            source_no=forecast_no,
            remark=f"销售预测 {forecast_no}（{month}）",
            operator_id=operator_id,
        )
        created_ids.append(demand.id)
    return {"created_count": len(created_ids), "skipped_count": skipped, "demand_ids": created_ids}


def create_demand_from_replenishment(
    db: Session, request_id: int, operator_id: Optional[int] = None
) -> models.PlnDemand:
    """由库存补库需求生成 `source_type=STOCKFILL` 的计划需求。

    仅受理**转计划**（`source_type=PRODUCTION`）的补库需求；`REORDER` 属于转采购，
    归 Procurement 受理。补库需求通过 `inventory.contract` 读取（惰性导入）。
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

    if _field("source_type") != "PRODUCTION":
        raise BusinessException(
            CODE_PARAM_INVALID,
            "该补库需求来源为转采购（REORDER），应由采购模块受理，计划模块只受理转计划需求",
        )

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


def import_demands_from_replenishment(
    db: Session, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    """把库存补库需求批量拉取为 `source_type=STOCKFILL` 的计划需求（已导入的跳过）。

    补库需求通过 `inventory.contract.list_replenishment_requests`（惰性导入）批量读取，
    只拉取**转计划**（`source_type=PRODUCTION`）且已确认 / 已下达（CONFIRMED / RELEASED）
    的需求：`REORDER` 属于转采购，归 Procurement 受理，不由计划模块导入；
    同时跳过未确认的草稿，避免把未定稿的需求提前纳入计划。
    """
    try:
        from app.modules.inventory import contract as inventory_contract  # type: ignore

        getter = getattr(inventory_contract, "list_replenishment_requests", None)
    except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
        raise BusinessException(CODE_CONTRACT_NOT_READY, "库存补库需求接口尚未就绪") from exc
    if getter is None:
        raise BusinessException(CODE_CONTRACT_NOT_READY, "库存补库需求接口尚未就绪")

    rows, _total = getter(
        db,
        page=1,
        page_size=200,
        status=None,
        source_type="PRODUCTION",
        material_id=None,
    )
    created_ids: List[int] = []
    skipped = 0
    for row in rows:
        if row.get("status") not in ("CONFIRMED", "RELEASED"):
            skipped += 1
            continue
        request_id = int(row["id"])
        if repository.find_demand_by_source(db, "STOCKFILL", request_id):
            skipped += 1
            continue
        demand = create_demand(
            db,
            source_type="STOCKFILL",
            material_id=int(row["material_id"]),
            quantity=_as_decimal(row.get("request_qty")),
            due_date=_to_date(row.get("required_date"), date.today()),
            source_reference_id=request_id,
            source_no=row.get("request_no"),
            remark=row.get("remark"),
            operator_id=operator_id,
        )
        created_ids.append(demand.id)
    return {"created_count": len(created_ids), "skipped_count": skipped, "demand_ids": created_ids}


# ==================== MPS ====================


def list_mps(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    year: Optional[int] = None,
) -> Tuple[List[models.PlnMps], int]:
    rows, total = repository.list_mps(db, page, page_size, status, year)
    _attach_mps_items_material(db, rows)
    return rows, total


def get_mps(db: Session, mps_id: int) -> models.PlnMps:
    mps = _require_mps(db, mps_id)
    _attach_mps_items_material(db, [mps])
    return mps


def _attach_mps_items_material(db: Session, rows: Sequence[models.PlnMps]) -> None:
    """MPS 行明细附带物料编码 / 名称与来源需求单号。"""
    items = [item for mps in rows for item in mps.items]
    if not items:
        return
    _attach_material(items, _material_fields(db, [i.material_id for i in items]))
    demand_ids = [
        int(demand_id)
        for item in items
        if item.source_demand_ids
        for demand_id in str(item.source_demand_ids).split(",")
        if demand_id.strip().isdigit()
    ]
    demand_map = repository.nos_by_ids(db, models.PlnDemand, demand_ids, "demand_no")
    for item in items:
        if not item.source_demand_ids:
            item.source_demand_nos = None
            continue
        nos = [
            demand_map.get(int(demand_id))
            for demand_id in str(item.source_demand_ids).split(",")
            if demand_id.strip().isdigit()
        ]
        item.source_demand_nos = ",".join(no for no in nos if no) or None


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
                source_demand_ids=raw.get("source_demand_ids"),
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


def create_mps_from_demands(
    db: Session, payload: Any, operator_id: Optional[int] = None
) -> models.PlnMps:
    """把统一需求（**销售订单 + 补库申请**）按「物料 + 需求月份」汇总生成 MPS。

    只有状态为 `CONFIRMED` 的 `SALES`（销售订单）/ `STOCKFILL`（补库申请）需求
    参与汇总，销售预测（`FORECAST`）按业务口径不进入 MPS；生成后这些
    需求统一置为 `RELEASED`，避免同一需求被重复纳入多张 MPS，同时在 MPS 行上
    记录来源需求 ID 便于追溯。MPS 本体仍为 `DRAFT`，需人工确认后才可触发 MRP。
    """
    start_date: date = payload.start_date
    end_date: date = payload.end_date
    if start_date > end_date:
        raise BusinessException(CODE_PARAM_INVALID, "汇总期间开始日期不能晚于结束日期")

    demands = repository.list_confirmed_demands_in_period(db, start_date, end_date)
    if not demands:
        raise BusinessException(
            CODE_PARAM_INVALID, "所选期间没有已确认的销售订单 / 补库需求，无法生成 MPS"
        )

    buckets: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for demand in demands:
        period_label = demand.due_date.strftime("%Y-%m")
        key = (demand.material_id, period_label)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "material_id": demand.material_id,
                "period_label": period_label,
                "planned_qty": Decimal("0"),
                "start_date": demand.due_date.replace(day=1),
                "end_date": _month_end(demand.due_date.year, demand.due_date.month),
                "source_ids": [],
            }
            buckets[key] = bucket
        bucket["planned_qty"] += _as_decimal(demand.quantity)
        bucket["source_ids"].append(str(demand.id))

    items = [
        {
            "material_id": bucket["material_id"],
            "period_label": bucket["period_label"],
            "planned_qty": bucket["planned_qty"],
            "start_date": bucket["start_date"],
            "end_date": bucket["end_date"],
            "source_demand_ids": ",".join(bucket["source_ids"]),
        }
        for bucket in buckets.values()
    ]
    mps = _create_mps_record(
        db,
        mps_no=None,
        mps_name=payload.mps_name or f"需求汇总 MPS {start_date}~{end_date}",
        program_no=payload.program_no,
        plan_year=start_date.year,
        start_date=start_date,
        end_date=end_date,
        remark=payload.remark,
        items=items,
        operator_id=operator_id,
    )
    for demand in demands:
        demand.status = "RELEASED"
        demand.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pln_mps",
        target_id=mps.id,
        operator_id=operator_id,
        detail=f"由 {len(demands)} 条需求汇总生成 MPS {mps.mps_no}（{len(items)} 行）",
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
    # 手工把 MPS 置为完工时，其行上记录的来源需求同步置为已完成
    if status == "COMPLETED":
        _advance_demands_from_mps(db, mps, operator_id=operator_id)
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


def _ceil_units(value: Decimal) -> Decimal:
    """把生产数量向上取整为整数件（离散制造不生产 0.02 件）。

    安全库存会带来小数，向下取整会缺料，因此一律向上取整。
    """
    return Decimal(value).to_integral_value(rounding=ROUND_CEILING)


def _explode_level(
    db: Session,
    level_map: Dict[int, Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """用**父件的净需求（建议下达量）**展开下一层直接子件。

    子件毛需求 = 父件净需求 × 单位用量；
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
            offset = int(child["lead_time_offset"] or 0)
            child_gross = order_qty * qty
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


def _collect_level0(db: Session, mps_id: int) -> Dict[int, Dict[str, Any]]:
    """归集第 0 层毛需求：只取 MPS 行。

    MPS 由统一需求（销售订单 / 销售预测 / 库存补库）汇总生成，因此 MRP 不再
    直接读取需求或销售订单，保证「需求 → MPS → MRP」链路唯一。
    """
    level0: Dict[int, Dict[str, Any]] = {}

    mps = _require_mps(db, mps_id)
    for item in repository.get_mps_items(db, mps.id):
        qty = _as_decimal(item.planned_qty)
        if qty <= 0:
            continue
        _accumulate(level0, item.material_id, qty, 0, None, item.end_date, set())

    return level0


def _qty_text(value: Decimal) -> str:
    """数量转紧凑文本（去掉多余的小数零）。"""
    return format(value.normalize(), "f")


def run_mrp(
    db: Session,
    *,
    mps_id: int,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnMrpRun:
    """执行一次 MRP 运算（真实计算，**每次运算独立批次，绝不覆盖历史结果**）。

    算法（规格 §13 / §17）：

    1. **第 0 层毛需求**只来自指定 MPS 的行（`planned_qty` / `end_date`）。
       需求必须先汇总为 MPS，MRP 不接受需求 ID 或销售订单直算。
    2. **逐层展开（广度优先）**：对每层物料先做净算，再用**父件的净需求**
       （而非毛需求）展开下一层：`子件毛需求 = 父件净需求 × 用量`，
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
    level_map = _collect_level0(db, mps_id)

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
            supply_type = material.get("supply_type") or "BUY"
            # 自制件要下达生产作业计划，数量必须是整数件（安全库存净算会带小数）
            order_qty = _ceil_units(net) if supply_type == "MAKE" else net
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
                    order_qty=order_qty,
                    supply_type=supply_type,
                    lead_time_days=lead_time,
                    requirement_date=requirement_date,
                    planned_release_date=_days_before(requirement_date, lead_time),
                    status="DRAFT",
                    created_by=operator_id,
                )
            )
            # 记录取整后的下达量，供下一层展开使用（子件毛需求来源于父件下达量）
            entry["order_qty"] = order_qty
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
    rows, total = repository.list_mrp_runs(db, page, page_size)
    _attach_mrp_run_refs(db, rows)
    return rows, total


def get_mrp_run(db: Session, run_id: int) -> models.PlnMrpRun:
    run = _require_run(db, run_id)
    _attach_mrp_run_refs(db, [run])
    _attach_mrp_results_material(db, list(run.results))
    return run


def _attach_mrp_run_refs(db: Session, rows: Sequence[models.PlnMrpRun]) -> None:
    """MRP 批次附带 MPS 编号。"""
    mps_ids = [run.mps_id for run in rows if run.mps_id]
    mps_map = repository.nos_by_ids(db, models.PlnMps, mps_ids, "mps_no")
    for run in rows:
        run.mps_no = mps_map.get(run.mps_id) if run.mps_id else None


def _attach_mrp_results_material(
    db: Session, rows: Sequence[models.PlnMrpResult]
) -> None:
    """MRP 结果附带物料与父件物料的编码 / 名称。"""
    if not rows:
        return
    materials = _material_fields(
        db,
        [r.material_id for r in rows]
        + [r.parent_material_id for r in rows if r.parent_material_id],
    )
    _attach_material(rows, materials)
    _attach_material(rows, materials, field="parent_material")


def list_mrp_results(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    run_id: Optional[int] = None,
    supply_type: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[List[models.PlnMrpResult], int]:
    rows, total = repository.list_mrp_results(db, page, page_size, run_id, supply_type, status)
    _attach_mrp_results_material(db, rows)
    return rows, total


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
    generable_only: bool = False,
) -> Tuple[List[models.PlnProductionPlan], int]:
    rows, total = repository.list_production_plans(
        db, page, page_size, status, material_id, generable_only
    )
    _attach_material(rows, _material_fields(db, [r.material_id for r in rows]))
    return rows, total


def get_production_plan(db: Session, plan_id: int) -> models.PlnProductionPlan:
    plan = _require_plan(db, plan_id)
    _attach_material([plan], _material_fields(db, [plan.material_id]))
    return plan


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
        planned_qty=_ceil_units(_as_decimal(result.order_qty)),
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
    # 手工把计划置为完工时，同样向上补齐 MRP 结果 / MPS 行完成量 / MPS / 来源需求
    if status == "COMPLETED":
        _advance_mps_from_plan(db, plan, operator_id=operator_id)
    return plan


def delete_production_plan(
    db: Session, plan_id: int, operator_id: Optional[int] = None
) -> None:
    """删除生产作业计划：仅 DRAFT / CANCELLED 可删，且须先清空下游引用。

    `pln_dispatch_order` / `pln_material_requisition` / `pln_completion_report`
    均以 `plan_id` 外键（RESTRICT）引用本计划，存在下游单据时拒绝删除并提示
    按「完工报告 → 派工单/领料单 → 作业计划」的顺序先行清理。
    """
    plan = _require_plan(db, plan_id)
    _ensure_deletable(plan.status, "生产作业计划")
    if repository.count_dispatch_orders_by_plan(db, plan_id):
        raise BusinessException(CODE_PARAM_INVALID, "该作业计划已生成派工单，请先删除相关派工单")
    if repository.count_requisitions_by_plan(db, plan_id):
        raise BusinessException(CODE_PARAM_INVALID, "该作业计划已生成领料单，请先删除相关领料单")
    if repository.count_completion_reports_by_plan(db, plan_id):
        raise BusinessException(CODE_PARAM_INVALID, "该作业计划已生成完工报告，请先删除相关完工报告")
    number = plan.plan_no
    db.delete(plan)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="pln_production_plan",
        target_id=plan_id,
        operator_id=operator_id,
        detail=f"删除生产作业计划 {number}",
    )


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
    rows, total = repository.list_dispatch_orders(db, page, page_size, status, plan_id)
    _attach_dispatch_refs(db, rows)
    return rows, total


def get_dispatch_order(db: Session, dispatch_id: int) -> models.PlnDispatchOrder:
    dispatch = _require_dispatch(db, dispatch_id)
    _attach_dispatch_refs(db, [dispatch])
    return dispatch


def _attach_dispatch_refs(db: Session, rows: Sequence[models.PlnDispatchOrder]) -> None:
    """派工单附带作业计划编号、承接单位与作业人员姓名。"""
    if not rows:
        return
    plan_map = repository.nos_by_ids(
        db, models.PlnProductionPlan, [r.plan_id for r in rows if r.plan_id], "plan_no"
    )
    workers = get_personnel_names(db, [r.worker_id for r in rows if r.worker_id])
    orgs = get_organization_names(db, [r.org_id for r in rows if r.org_id])
    for row in rows:
        row.plan_no = plan_map.get(row.plan_id) if row.plan_id else None
        row.worker_name = workers.get(row.worker_id) if row.worker_id else None
        row.org_name = orgs.get(row.org_id) if row.org_id else None


def create_dispatch_order(
    db: Session,
    *,
    planned_qty: Decimal,
    planned_start: Optional[date] = None,
    planned_end: Optional[date] = None,
    plan_id: Optional[int] = None,
    operation: Optional[str] = None,
    worker_id: Optional[int] = None,
    org_id: Optional[int] = None,
    dispatch_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnDispatchOrder:
    """新增派工单；`worker_id` 指向 `sys_personnel.id` 并通过 system 契约校验。

    日期允许留空：派工单以 DRAFT 预填草稿形态存在，日期与作业人员由人工指定，
    确认（进入非 DRAFT 状态）前必须补齐。
    `org_id` 为承接单位（加工中心 / 车间），留空时自动取智能加工中心。
    """
    qty = _as_decimal(planned_qty)
    if qty <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "派工数量必须为正数")
    if planned_start is not None and planned_end is not None and planned_start > planned_end:
        raise BusinessException(CODE_PARAM_INVALID, "计划开始日期不能晚于结束日期")
    if plan_id is not None:
        _require_plan(db, plan_id)
    if worker_id is not None and not get_personnel(db, worker_id):
        raise BusinessException(CODE_NOT_FOUND, f"作业人员不存在：{worker_id}")
    if org_id is None:
        factory = get_default_factory(db)
        org_id = factory["id"] if factory else None
    elif not get_organization(db, org_id):
        raise BusinessException(CODE_NOT_FOUND, f"承接单位不存在：{org_id}")
    dispatch = models.PlnDispatchOrder(
        dispatch_no=_unique_no(db, models.PlnDispatchOrder, "dispatch_no", dispatch_no, "DSP"),
        plan_id=plan_id,
        operation=operation,
        planned_qty=qty,
        completed_qty=Decimal("0"),
        worker_id=worker_id,
        org_id=org_id,
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


def update_dispatch_order(
    db: Session, dispatch_id: int, payload: Any, operator_id: Optional[int] = None
) -> models.PlnDispatchOrder:
    """修改派工单（人工审核调整）：仅 DRAFT 可改。"""
    dispatch = _require_dispatch(db, dispatch_id)
    if dispatch.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"派工单已处于 {dispatch.status}，不允许修改"
        )
    data = payload.model_dump(exclude_unset=True)
    if "planned_qty" in data:
        qty = _as_decimal(data["planned_qty"])
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "派工数量必须为正数")
        dispatch.planned_qty = qty
    if "operation" in data:
        dispatch.operation = data["operation"]
    if "worker_id" in data:
        worker_id = data["worker_id"]
        if worker_id is not None and not get_personnel(db, worker_id):
            raise BusinessException(CODE_NOT_FOUND, f"作业人员不存在：{worker_id}")
        dispatch.worker_id = worker_id
    if "org_id" in data:
        org_id = data["org_id"]
        if org_id is not None and not get_organization(db, org_id):
            raise BusinessException(CODE_NOT_FOUND, f"承接单位不存在：{org_id}")
        dispatch.org_id = org_id
    if "planned_start" in data:
        dispatch.planned_start = data["planned_start"]
    if "planned_end" in data:
        dispatch.planned_end = data["planned_end"]
    if "remark" in data:
        dispatch.remark = data["remark"]
    if (
        dispatch.planned_start is not None
        and dispatch.planned_end is not None
        and dispatch.planned_start > dispatch.planned_end
    ):
        raise BusinessException(CODE_PARAM_INVALID, "计划开始日期不能晚于结束日期")
    dispatch.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="pln_dispatch_order",
        target_id=dispatch.id,
        operator_id=operator_id,
        detail=f"修改派工单 {dispatch.dispatch_no}",
    )
    return dispatch


def create_dispatch_orders_from_plans(
    db: Session,
    plan_ids: Sequence[int],
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """按选定的生产作业计划生成 DRAFT 派工单：**一张计划一张派工单**。

    生成口径（规格调整：车间不再逐工序派工）：
    - 不再按工艺路线拆工序，也不再要求物料必须维护工艺路线；
    - `org_id` 统一指派给智能加工中心（主数据缺失时留空），由加工中心再自行
      把任务分派给具体作业人员，因此 `worker_id`、`operation` 均留空；
    - `planned_qty` 取"计划量 − 已完工量"，计划起止日期沿用计划行，
      便于加工中心直接确认开工。
    幂等口径：以 `(source_type='PLAN', source_reference_id=plan.id)` 为来源键，
    已存在派工单的计划整体跳过，不会重复生成。
    单条失败不中断批量：缺失计划 / 终态计划 / 已完工计划均计入 `errors`。
    """
    ids = list(dict.fromkeys(int(i) for i in plan_ids))
    if not ids:
        raise BusinessException(CODE_PARAM_INVALID, "plan_ids 不能为空")
    plan_map = {p.id: p for p in repository.get_production_plans_by_ids(db, ids)}

    factory = get_default_factory(db)
    default_org_id = factory["id"] if factory else None
    default_org_name = factory["org_name"] if factory else None

    errors: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    created_ids: List[int] = []

    for plan_id in ids:
        plan = plan_map.get(plan_id)
        if plan is None:
            errors.append(
                {
                    "plan_id": plan_id,
                    "plan_no": None,
                    "material_code": None,
                    "reason": "作业计划不存在",
                }
            )
            continue
        material = get_material(db, plan.material_id)
        material_code = material["material_code"] if material else None
        if plan.status in {"COMPLETED", "CANCELLED"}:
            errors.append(
                {
                    "plan_id": plan.id,
                    "plan_no": plan.plan_no,
                    "material_code": material_code,
                    "reason": f"作业计划状态为 {plan.status}，不能生成派工单",
                }
            )
            continue

        remaining_qty = _as_decimal(plan.planned_qty) - _as_decimal(plan.completed_qty)
        if remaining_qty <= 0:
            errors.append(
                {
                    "plan_id": plan.id,
                    "plan_no": plan.plan_no,
                    "material_code": material_code,
                    "reason": "该计划已无未完工数量，无需派工",
                }
            )
            continue

        existing = repository.list_dispatch_orders_by_source(db, "PLAN", plan.id)
        if existing:
            skipped.append(
                {
                    "plan_id": plan.id,
                    "plan_no": plan.plan_no,
                    "reason": f"该计划已生成派工单（{existing[0].dispatch_no}），不重复生成",
                }
            )
            continue

        dispatch = models.PlnDispatchOrder(
            dispatch_no=_unique_no(
                db, models.PlnDispatchOrder, "dispatch_no", None, "DSP"
            ),
            source_type="PLAN",
            source_reference_id=plan.id,
            plan_id=plan.id,
            operation=None,
            planned_qty=remaining_qty,
            completed_qty=Decimal("0"),
            worker_id=None,
            org_id=default_org_id,
            planned_start=plan.start_date,
            planned_end=plan.end_date,
            status="DRAFT",
            remark=(
                f"按计划 {plan.plan_no} 整单派工，承接单位：{default_org_name or '未指定'}，"
                "作业人员由加工中心指派"
            ),
            created_by=operator_id,
        )
        repository.add_dispatch_order(db, dispatch)
        created_ids.append(dispatch.id)

    if created_ids:
        log_operation(
            db,
            module=MODULE,
            action="GENERATE",
            target_type="pln_dispatch_order",
            target_id=created_ids[0],
            operator_id=operator_id,
            detail=(
                f"按生产作业计划生成派工单 {len(created_ids)} 张"
                f"（整单派给 {default_org_name or '加工中心'}）"
            ),
        )
    return {
        "created_count": len(created_ids),
        "skipped_count": len(skipped),
        "errors": errors,
        "skipped": skipped,
        "ids": created_ids,
    }


def set_dispatch_order_status(
    db: Session, dispatch_id: int, status: str, operator_id: Optional[int] = None
) -> models.PlnDispatchOrder:
    """派工单状态机：进入非 DRAFT 状态前必须补齐计划开始/结束日期。"""
    _validate_status(status, _DISPATCH_STATUSES)
    dispatch = _require_dispatch(db, dispatch_id)
    _validate_transition(dispatch.status, status, _MAIN_TRANSITIONS, "派工单")
    if status != "DRAFT" and (
        dispatch.planned_start is None or dispatch.planned_end is None
    ):
        raise BusinessException(
            CODE_STATUS_INVALID, "派工单尚未填写计划开始/结束日期，不能确认"
        )
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
    # 派工单一旦已下达车间（确认/发布/开工），上游作业计划即视为开工；
    # 取消（CANCELLED）不算开工，避免错误推进计划状态
    if status in {"CONFIRMED", "RELEASED", "IN_PROGRESS"} and dispatch.plan_id is not None:
        plan = repository.get_production_plan(db, dispatch.plan_id)
        if plan is not None:
            _advance_plan_started(
                db, plan, trigger=f"派工单 {dispatch.dispatch_no} {status}", operator_id=operator_id
            )
    return dispatch


def delete_dispatch_order(
    db: Session, dispatch_id: int, operator_id: Optional[int] = None
) -> None:
    """删除派工单：仅 DRAFT / CANCELLED 可删，且须先清空被完工报告引用。

    完工报告以 `dispatch_id` 外键（RESTRICT）引用本派工单，存在引用时拒绝删除。
    """
    dispatch = _require_dispatch(db, dispatch_id)
    _ensure_deletable(dispatch.status, "派工单")
    if repository.count_completion_reports_by_dispatch(db, dispatch_id):
        raise BusinessException(CODE_PARAM_INVALID, "该派工单已被完工报告引用，请先删除相关完工报告")
    number = dispatch.dispatch_no
    db.delete(dispatch)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="pln_dispatch_order",
        target_id=dispatch_id,
        operator_id=operator_id,
        detail=f"删除派工单 {number}",
    )


# ==================== 领料单 ====================


def list_requisitions(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
) -> Tuple[List[models.PlnMaterialRequisition], int]:
    rows, total = repository.list_requisitions(db, page, page_size, status, plan_id)
    _attach_requisition_refs(db, rows)
    return rows, total


def get_requisition(db: Session, req_id: int) -> models.PlnMaterialRequisition:
    requisition = _require_requisition(db, req_id)
    _attach_requisition_refs(db, [requisition])
    return requisition


def _attach_requisition_refs(
    db: Session, rows: Sequence[models.PlnMaterialRequisition]
) -> None:
    """领料单附带作业计划编号、仓库编码 / 名称与行物料编码 / 名称。"""
    if not rows:
        return
    plan_map = repository.nos_by_ids(
        db, models.PlnProductionPlan, [r.plan_id for r in rows if r.plan_id], "plan_no"
    )
    warehouses = _warehouse_fields(db, [r.warehouse_id for r in rows])
    items = [item for row in rows for item in row.items]
    materials = _material_fields(db, [i.material_id for i in items])
    for row in rows:
        row.plan_no = plan_map.get(row.plan_id) if row.plan_id else None
    _attach_warehouse(rows, warehouses)
    _attach_material(items, materials)


def create_requisition(
    db: Session,
    *,
    items: Sequence[Mapping[str, Any]],
    req_date: Optional[date] = None,
    plan_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    req_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnMaterialRequisition:
    """新增领料单（头 + 行），默认 DRAFT。

    领料日期可留空（确认前需补齐）；**领料仓库不再由计划模块指定**，
    出库仓库由仓库管理人员在「库存管理 → 出库管理」确认时选择，
    因此 `warehouse_id` 仅作历史字段保留，不参与库存变动。
    """
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


def update_requisition(
    db: Session, req_id: int, payload: Any, operator_id: Optional[int] = None
) -> models.PlnMaterialRequisition:
    """修改领料单（人工审核调整）：仅 DRAFT 可改；`items` 给定时整表替换。"""
    req = _require_requisition(db, req_id)
    if req.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"领料单已处于 {req.status}，不允许修改"
        )
    data = payload.model_dump(exclude_unset=True)
    if "warehouse_id" in data:
        req.warehouse_id = data["warehouse_id"]
    if "req_date" in data:
        req.req_date = data["req_date"]
    if "remark" in data:
        req.remark = data["remark"]
    if "items" in data:
        rows = data["items"] or []
        if not rows:
            raise BusinessException(CODE_PARAM_INVALID, "领料单至少需要一条明细")
        for item in repository.get_requisition_items(db, req_id):
            db.delete(item)
        db.flush()
        for raw in rows:
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
                    remark=raw.get("remark"),
                ),
            )
        db.flush()
        repository.refresh(db, req)
    req.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="pln_material_requisition",
        target_id=req.id,
        operator_id=operator_id,
        detail=f"修改领料单 {req.req_no}",
    )
    return req


def create_requisitions_from_plans(
    db: Session,
    plan_ids: Sequence[int],
    operator_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
) -> Dict[str, Any]:
    """按选定的生产作业计划，取物料生效 BOM 直接子件生成 DRAFT 领料单。

    数量口径：`需求量 = Σ(子件单位用量 × 计划量)`，按物料聚合后
    4 位小数 HALF_UP 舍入（**不乘损耗率**）。**领料日期留空**（由人工指定）、仓库取调用方传入值（可空），
    明细按 BOM 预填，均可再修改。
    幂等口径：一张计划只生成一张领料单（按 `(source_type='PLAN', source_reference_id)`
    判重）；无生效 BOM / 终态计划 / 计划缺失计入 `errors`，不中断批量。
    """
    ids = list(dict.fromkeys(int(i) for i in plan_ids))
    if not ids:
        raise BusinessException(CODE_PARAM_INVALID, "plan_ids 不能为空")
    plan_map = {p.id: p for p in repository.get_production_plans_by_ids(db, ids)}

    errors: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    created_ids: List[int] = []

    for plan_id in ids:
        plan = plan_map.get(plan_id)
        if plan is None:
            errors.append(
                {
                    "plan_id": plan_id,
                    "plan_no": None,
                    "material_code": None,
                    "reason": "作业计划不存在",
                }
            )
            continue
        material = get_material(db, plan.material_id)
        material_code = material["material_code"] if material else None
        if plan.status in {"COMPLETED", "CANCELLED"}:
            errors.append(
                {
                    "plan_id": plan.id,
                    "plan_no": plan.plan_no,
                    "material_code": material_code,
                    "reason": f"作业计划状态为 {plan.status}，不能生成领料单",
                }
            )
            continue
        if repository.find_requisition_by_source(db, "PLAN", plan.id):
            skipped.append(
                {
                    "plan_id": plan.id,
                    "plan_no": plan.plan_no,
                    "reason": "该计划已生成领料单",
                }
            )
            continue

        children = get_active_bom_children(
            db, plan.material_id, on_date=plan.start_date
        )
        if not children:
            errors.append(
                {
                    "plan_id": plan.id,
                    "plan_no": plan.plan_no,
                    "material_code": material_code,
                    "reason": "物料未维护生效 BOM",
                }
            )
            continue

        planned_qty = _as_decimal(plan.planned_qty)
        totals: Dict[int, Decimal] = {}
        for child in children:
            child_id = int(child["child_material_id"])
            amount = _as_decimal(child["quantity"]) * planned_qty
            totals[child_id] = totals.get(child_id, Decimal("0")) + amount

        req = models.PlnMaterialRequisition(
            req_no=_unique_no(
                db, models.PlnMaterialRequisition, "req_no", None, "REQ"
            ),
            source_type="PLAN",
            source_reference_id=plan.id,
            plan_id=plan.id,
            warehouse_id=warehouse_id,
            req_date=None,
            status="DRAFT",
            remark=f"按计划 {plan.plan_no} 生成",
            created_by=operator_id,
        )
        repository.add_requisition(db, req)
        for child_id, amount in totals.items():
            qty = amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            if qty <= 0:
                qty = Decimal("0.0001")
            repository.add_requisition_item(
                db,
                models.PlnMaterialRequisitionItem(
                    requisition_id=req.id,
                    material_id=child_id,
                    required_qty=qty,
                    issued_qty=Decimal("0"),
                ),
            )
        created_ids.append(req.id)

    if created_ids:
        log_operation(
            db,
            module=MODULE,
            action="GENERATE",
            target_type="pln_material_requisition",
            target_id=created_ids[0],
            operator_id=operator_id,
            detail=f"按生产作业计划生成领料单 {len(created_ids)} 张",
        )
    return {
        "created_count": len(created_ids),
        "skipped_count": len(skipped),
        "errors": errors,
        "skipped": skipped,
        "ids": created_ids,
    }


def confirm_requisition(
    db: Session, req_id: int, operator_id: Optional[int] = None
) -> models.PlnMaterialRequisition:
    """确认领料（业务审核完成）：向库存管理推送**待出库单**，不改结存。

    - **不再由计划模块指定领料仓库**：单据进入「库存管理 → 出库管理」待办列表，
      由仓库管理人员选择仓库并确认后，结存才真正减少（禁止负库存仍由库存引擎复核）；
    - 推送数量口径：`需求数量 − 已领数量`，推送后回写已领数量，重复确认幂等；
    - 领料确认即代表车间已开始生产，上游作业计划自动转「进行中」（业务口径不变）。
    """
    req = _require_requisition(db, req_id)
    if req.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, f"领料单当前状态为 {req.status}，不能确认")
    if req.req_date is None:
        raise BusinessException(CODE_PARAM_INVALID, "领料单未指定领料日期，不能确认")
    items = repository.get_requisition_items(db, req_id)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "领料单没有明细，不能确认")
    push_items: List[Dict[str, Any]] = []
    for item in items:
        outstanding = _as_decimal(item.required_qty) - _as_decimal(item.issued_qty)
        if outstanding <= 0:
            continue
        push_items.append(
            {
                "material_id": item.material_id,
                "quantity": outstanding,
                "remark": item.remark,
            }
        )
        item.issued_qty = _as_decimal(item.required_qty)
    if not push_items:
        raise BusinessException(CODE_PARAM_INVALID, "领料单没有待领数量，不能确认")
    pushed = push_outbound_order(
        db,
        op_date=req.req_date,
        items=push_items,
        source_module=MODULE,
        source_type="MATERIAL_REQUISITION",
        source_reference_id=req.id,
        source_no=req.req_no,
        remark=(
            (f"领料日期 {req.req_date}，" if req.req_date else "")
            + f"共 {len(push_items)} 项，请仓库指定仓库后出库"
        ),
        operator_id=operator_id,
    )
    req.status = "COMPLETED"
    req.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="pln_material_requisition",
        target_id=req.id,
        operator_id=operator_id,
        detail=f"确认领料单 {req.req_no}，推送库存出库单 {pushed['operation_no']}",
    )
    # 领料确认即代表车间已开始生产，上游作业计划自动转「进行中」
    if req.plan_id is not None:
        plan = repository.get_production_plan(db, req.plan_id)
        if plan is not None:
            _advance_plan_started(
                db, plan, trigger=f"领料单 {req.req_no} 确认出库", operator_id=operator_id
            )
    return req


def cancel_requisition(
    db: Session, req_id: int, operator_id: Optional[int] = None
) -> models.PlnMaterialRequisition:
    """取消领料单（DRAFT / CONFIRMED 可取消），并撤销尚未确认的库存出库单。"""
    req = _require_requisition(db, req_id)
    if req.status not in {"DRAFT", "CONFIRMED"}:
        raise BusinessException(CODE_STATUS_INVALID, f"领料单当前状态为 {req.status}，不能取消")
    cancel_pending_inout_orders(
        db,
        source_module=MODULE,
        source_type="MATERIAL_REQUISITION",
        source_reference_id=req.id,
        operator_id=operator_id,
        reason=f"领料单 {req.req_no} 取消",
    )
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


def delete_requisition(db: Session, req_id: int, operator_id: Optional[int] = None) -> None:
    """删除领料单：仅 DRAFT / CANCELLED 可删，明细行一并显式清理。

    已确认（COMPLETED）的领料单已写库存出库流水，不可删除。
    """
    req = _require_requisition(db, req_id)
    _ensure_deletable(req.status, "领料单")
    number = req.req_no
    repository.delete_requisition_items(db, req_id)
    db.delete(req)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="pln_material_requisition",
        target_id=req_id,
        operator_id=operator_id,
        detail=f"删除领料单 {number}",
    )


# ==================== 状态联动（自动汇总） ====================


#: 自动推进使用的审计动作，便于与人工操作区分
_AUTO_ACTION = "AUTO_STATUS"


def _auto_set_status(
    db: Session,
    record,
    status: str,
    *,
    target_type: str,
    number: str,
    label: str,
    trigger: str,
    operator_id: Optional[int] = None,
) -> bool:
    """自动推进单据状态（内部专用，不提交）。

    设计约束：

    1. **只前进不回退**：只写入 `IN_PROGRESS` / `COMPLETED`，绝不把单据改回前序状态。
    2. **终态保护**：`CANCELLED`、已 `COMPLETED` 一律不动，避免重复触发时抖动。
    3. **幂等**：状态与目标一致时不写审计日志，重复确认完工不会产生重复记录。
    4. **可追溯**：审计动作固定为 `AUTO_STATUS`，明细里写明触发单据，能与人工流转区分开。
    """
    current = record.status
    if current in {"CANCELLED", status}:
        return False
    record.status = status
    record.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action=_AUTO_ACTION,
        target_type=target_type,
        target_id=record.id,
        operator_id=operator_id,
        detail=f"{label} {number} 由 {current} 自动推进为 {status}（触发：{trigger}）",
    )
    return True


def _advance_plan_started(
    db: Session, plan: models.PlnProductionPlan, trigger: str, operator_id: Optional[int] = None
) -> bool:
    """领料/派工开工后，把上游作业计划推进到「进行中」。

    只推进已确认及以后的计划：草稿计划仍要求人工确认，避免绕过确认环节。
    """
    if plan.status not in {"CONFIRMED", "RELEASED"}:
        return False
    return _auto_set_status(
        db,
        plan,
        "IN_PROGRESS",
        target_type="pln_production_plan",
        number=plan.plan_no,
        label="生产作业计划",
        trigger=trigger,
        operator_id=operator_id,
    )


def _mps_item_is_done(db: Session, mps: models.PlnMps, item: models.PlnMpsItem) -> bool:
    """判断 MPS 行是否已完成。

    两种情况：

    1. 该行有作业计划 → 要求关联计划**全部**完工（取消的计划已排除）。
    2. 该行没有作业计划 → 只有当该 MPS 跑过 MRP 且该物料净需求为 0 时，
       视为「库存已满足、无需生产」，才判定完成；否则视为还没排产。
    """
    plans = repository.plans_of_mps_item(db, mps.id, item.material_id)
    if plans:
        return all(plan.status == "COMPLETED" for plan in plans)
    order_qty = repository.latest_order_qty_of_material(db, mps.id, item.material_id)
    return order_qty is not None and order_qty <= 0


def _advance_demands_from_mps(
    db: Session, mps: models.PlnMps, operator_id: Optional[int] = None
) -> int:
    """MPS 完成后，把其行上记录的来源需求一并置为「已完成」。"""
    demand_ids: List[int] = []
    for item in repository.get_mps_items(db, mps.id):
        if not item.source_demand_ids:
            continue
        for token in str(item.source_demand_ids).split(","):
            token = token.strip()
            if token.isdigit():
                demand_ids.append(int(token))
    completed = 0
    for demand in repository.get_demands_by_ids(db, demand_ids):
        if demand.status not in {"CONFIRMED", "RELEASED"}:
            continue
        if _auto_set_status(
            db,
            demand,
            "COMPLETED",
            target_type="pln_demand",
            number=demand.demand_no,
            label="需求",
            trigger=f"主生产计划 {mps.mps_no} 完工",
            operator_id=operator_id,
        ):
            completed += 1
    return completed


def _advance_mps_from_plan(
    db: Session, plan: models.PlnProductionPlan, operator_id: Optional[int] = None
) -> bool:
    """作业计划完工后向上汇总：MRP 结果 → MPS 行完成量 → MPS → 来源需求。"""
    if plan.mrp_result_id is None:
        return False
    result = repository.get_mrp_result(db, plan.mrp_result_id)
    if result is None:
        return False
    trigger = f"生产作业计划 {plan.plan_no} 完工"
    _auto_set_status(
        db,
        result,
        "COMPLETED",
        target_type="pln_mrp_result",
        number=f"#{result.id}",
        label="MRP 结果",
        trigger=trigger,
        operator_id=operator_id,
    )
    run = repository.get_mrp_run(db, result.run_id)
    if run is None or run.mps_id is None:
        return False
    mps = repository.get_mps(db, run.mps_id)
    if mps is None or mps.status in {"CANCELLED", "COMPLETED"}:
        return False

    items = repository.get_mps_items(db, mps.id)
    # 完成量按关联计划重算（而非累加），保证重复触发、计划取消后回算都正确
    for item in items:
        plans = repository.plans_of_mps_item(db, mps.id, item.material_id)
        produced = sum((_as_decimal(p.completed_qty) for p in plans), Decimal("0"))
        item.finished_qty = min(produced, _as_decimal(item.planned_qty))
    if not items or not all(_mps_item_is_done(db, mps, item) for item in items):
        return False
    if not _auto_set_status(
        db,
        mps,
        "COMPLETED",
        target_type="pln_mps",
        number=mps.mps_no,
        label="主生产计划",
        trigger=trigger,
        operator_id=operator_id,
    ):
        return False
    for item in items:
        item.status = "COMPLETED"
    _advance_demands_from_mps(db, mps, operator_id=operator_id)
    return True


def _advance_after_completion(
    db: Session,
    report: models.PlnCompletionReport,
    plan: Optional[models.PlnProductionPlan],
    dispatch: Optional[models.PlnDispatchOrder],
    qualified: Decimal,
    operator_id: Optional[int] = None,
) -> None:
    """完工入库后的整链自动汇总：完工报告 → 派工单 → 作业计划 → MPS → 需求。"""
    trigger = f"完工报告 {report.report_no} 入库 {_qty_text(qualified)}"
    if dispatch is not None and _as_decimal(dispatch.completed_qty) >= _as_decimal(
        dispatch.planned_qty
    ):
        _auto_set_status(
            db,
            dispatch,
            "COMPLETED",
            target_type="pln_dispatch_order",
            number=dispatch.dispatch_no,
            label="派工单",
            trigger=trigger,
            operator_id=operator_id,
        )
    if plan is None:
        return
    if _as_decimal(plan.completed_qty) < _as_decimal(plan.planned_qty):
        return
    # 一张计划可能挂多张派工单（历史按工序拆分），必须全部完工才算计划完工
    if any(
        order.status != "COMPLETED"
        for order in repository.list_dispatch_orders_by_plan(db, plan.id)
    ):
        return
    changed = _auto_set_status(
        db,
        plan,
        "COMPLETED",
        target_type="pln_production_plan",
        number=plan.plan_no,
        label="生产作业计划",
        trigger=trigger,
        operator_id=operator_id,
    )
    # 计划已完工时也再次向上汇总，保证「计划手工置完工」后 MPS/需求能被补齐
    if changed or plan.status == "COMPLETED":
        _advance_mps_from_plan(db, plan, operator_id=operator_id)


# ==================== 完工报告 ====================


def list_completion_reports(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
) -> Tuple[List[models.PlnCompletionReport], int]:
    rows, total = repository.list_completion_reports(db, page, page_size, status, plan_id)
    _attach_completion_refs(db, rows)
    return rows, total


def get_completion_report(db: Session, report_id: int) -> models.PlnCompletionReport:
    report = _require_completion(db, report_id)
    _attach_completion_refs(db, [report])
    return report


def _attach_completion_refs(
    db: Session, rows: Sequence[models.PlnCompletionReport]
) -> None:
    """完工报告附带作业计划编号、派工单号、物料与入库仓库编码 / 名称。"""
    if not rows:
        return
    plan_map = repository.nos_by_ids(
        db, models.PlnProductionPlan, [r.plan_id for r in rows if r.plan_id], "plan_no"
    )
    dispatch_map = repository.nos_by_ids(
        db, models.PlnDispatchOrder, [r.dispatch_id for r in rows if r.dispatch_id], "dispatch_no"
    )
    warehouses = _warehouse_fields(db, [r.warehouse_id for r in rows])
    materials = _material_fields(db, [r.material_id for r in rows])
    for row in rows:
        row.plan_no = plan_map.get(row.plan_id) if row.plan_id else None
        row.dispatch_no = dispatch_map.get(row.dispatch_id) if row.dispatch_id else None
    _attach_warehouse(rows, warehouses)
    _attach_material(rows, materials)


def create_completion_report(
    db: Session,
    *,
    material_id: int,
    completed_qty: Decimal,
    qualified_qty: Decimal,
    warehouse_id: Optional[int] = None,
    report_date: Optional[date] = None,
    plan_id: Optional[int] = None,
    dispatch_id: Optional[int] = None,
    scrap_qty: Decimal = Decimal("0"),
    report_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PlnCompletionReport:
    """新增完工报告（默认 DRAFT），确认后推送库存待入库单。

    报工日期可留空（确认前需补齐）；**入库仓库不再由计划模块指定**，
    由仓库管理人员在「库存管理 → 入库管理」确认时选择，
    因此 `warehouse_id` 仅作历史字段保留，不参与库存变动。
    """
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


def update_completion_report(
    db: Session, report_id: int, payload: Any, operator_id: Optional[int] = None
) -> models.PlnCompletionReport:
    """修改完工报告（人工补填）：仅 DRAFT 可改，未传字段不改。"""
    report = _require_completion(db, report_id)
    if report.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"完工报告已处于 {report.status}，不允许修改"
        )
    data = payload.model_dump(exclude_unset=True)
    if "dispatch_id" in data:
        dispatch_id = data["dispatch_id"]
        if dispatch_id is not None:
            _require_dispatch(db, dispatch_id)
        report.dispatch_id = dispatch_id
    if "completed_qty" in data:
        report.completed_qty = _as_decimal(data["completed_qty"])
    if "qualified_qty" in data:
        report.qualified_qty = _as_decimal(data["qualified_qty"])
    if "scrap_qty" in data:
        report.scrap_qty = _as_decimal(data["scrap_qty"])
    if "warehouse_id" in data:
        report.warehouse_id = data["warehouse_id"]
    if "report_date" in data:
        report.report_date = data["report_date"]
    if "remark" in data:
        report.remark = data["remark"]
    completed = _as_decimal(report.completed_qty)
    qualified = _as_decimal(report.qualified_qty)
    scrap = _as_decimal(report.scrap_qty)
    if completed <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "完工数量必须为正数")
    if qualified < 0 or scrap < 0:
        raise BusinessException(CODE_PARAM_INVALID, "合格数量与报废数量不能为负")
    if qualified > completed:
        raise BusinessException(CODE_PARAM_INVALID, "合格数量不能大于完工数量")
    report.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="pln_completion_report",
        target_id=report.id,
        operator_id=operator_id,
        detail=f"修改完工报告 {report.report_no}",
    )
    return report


def create_completion_reports_from_plans(
    db: Session,
    plan_ids: Sequence[int],
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """按选定的生产作业计划生成 DRAFT 完工报告（预填草稿）。

    预填口径：产出物料取计划的产出物料、`completed_qty` 取「计划数量 − 已完工数量」
    （剩余数量），`qualified_qty` 预填同值、`scrap_qty` 预填 0（均为假设值，可再修改）；
    **报工日期与入库仓库留空**由人工指定，派工单关联一并留空（一张计划对应多道工序，
    无法推导）。一张计划只生成一张完工报告（按 `plan_id` 取未取消报告判重）；
    计划缺失 / 已取消计入 `errors`，已生成过 / 无剩余数量计入 `skipped`，不中断批量。
    """
    ids = list(dict.fromkeys(int(i) for i in plan_ids))
    if not ids:
        raise BusinessException(CODE_PARAM_INVALID, "plan_ids 不能为空")
    plan_map = {p.id: p for p in repository.get_production_plans_by_ids(db, ids)}

    errors: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    created_ids: List[int] = []

    for plan_id in ids:
        plan = plan_map.get(plan_id)
        if plan is None:
            errors.append(
                {
                    "plan_id": plan_id,
                    "plan_no": None,
                    "material_code": None,
                    "reason": "作业计划不存在",
                }
            )
            continue
        material = get_material(db, plan.material_id)
        material_code = material["material_code"] if material else None
        if plan.status == "CANCELLED":
            errors.append(
                {
                    "plan_id": plan.id,
                    "plan_no": plan.plan_no,
                    "material_code": material_code,
                    "reason": "作业计划已取消，不能生成完工报告",
                }
            )
            continue
        if repository.find_completion_report_by_plan(db, plan.id):
            skipped.append(
                {
                    "plan_id": plan.id,
                    "plan_no": plan.plan_no,
                    "reason": "该计划已生成完工报告",
                }
            )
            continue

        remaining = _as_decimal(plan.planned_qty) - _as_decimal(plan.completed_qty)
        if remaining <= 0:
            skipped.append(
                {
                    "plan_id": plan.id,
                    "plan_no": plan.plan_no,
                    "reason": "该计划已完工，无剩余数量",
                }
            )
            continue

        report = models.PlnCompletionReport(
            report_no=_unique_no(
                db, models.PlnCompletionReport, "report_no", None, "CRP"
            ),
            plan_id=plan.id,
            dispatch_id=None,
            material_id=plan.material_id,
            completed_qty=remaining,
            qualified_qty=remaining,
            scrap_qty=Decimal("0"),
            warehouse_id=None,
            report_date=None,
            status="DRAFT",
            remark=f"按计划 {plan.plan_no} 生成",
            created_by=operator_id,
        )
        repository.add_completion_report(db, report)
        created_ids.append(report.id)

    if created_ids:
        log_operation(
            db,
            module=MODULE,
            action="GENERATE",
            target_type="pln_completion_report",
            target_id=created_ids[0],
            operator_id=operator_id,
            detail=f"按生产作业计划生成完工报告 {len(created_ids)} 张",
        )
    return {
        "created_count": len(created_ids),
        "skipped_count": len(skipped),
        "errors": errors,
        "skipped": skipped,
        "ids": created_ids,
    }


def confirm_completion_report(
    db: Session, report_id: int, operator_id: Optional[int] = None
) -> models.PlnCompletionReport:
    """确认完工（业务审核完成）：向库存管理推送**待入库单**，并回写计划 / 派工的已完工数量。

    - **不再由计划模块指定入库仓库**：单据进入「库存管理 → 入库管理」待办列表，
      由仓库管理人员选择仓库并确认后，结存才真正增加；
    - 推送数量口径：合格数量（报废 / 不合格不入库），备注写清完工 / 合格 / 报废数量与来源；
    - 作业计划 / 派工单的已完工数量与状态推进保持原有业务口径不变。
    """
    report = _require_completion(db, report_id)
    if report.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, f"完工报告当前状态为 {report.status}，不能确认")
    if report.report_date is None:
        raise BusinessException(CODE_PARAM_INVALID, "完工报告未指定报工日期，不能确认")
    qualified = _as_decimal(report.qualified_qty)
    if qualified <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "合格数量为 0，无需入库")

    plan: Optional[models.PlnProductionPlan] = None
    dispatch: Optional[models.PlnDispatchOrder] = None
    if report.plan_id is not None:
        plan = repository.get_production_plan(db, report.plan_id)
    if report.dispatch_id is not None:
        dispatch = repository.get_dispatch_order(db, report.dispatch_id)
        # 报告只填了派工单时，作业计划从派工单反查，保证状态照样能向上汇总
        if plan is None and dispatch is not None and dispatch.plan_id is not None:
            plan = repository.get_production_plan(db, dispatch.plan_id)

    remark_parts: List[str] = []
    if plan is not None:
        remark_parts.append(f"作业计划 {plan.plan_no}")
    if dispatch is not None:
        remark_parts.append(f"派工单 {dispatch.dispatch_no}")
    remark_parts.append(
        f"完工 {_as_decimal(report.completed_qty)}，合格 {qualified}，"
        f"报废 {_as_decimal(report.scrap_qty)}，请仓库指定仓库后入库"
    )
    pushed = push_inbound_order(
        db,
        op_date=report.report_date,
        items=[
            {
                "material_id": report.material_id,
                "quantity": qualified,
                "remark": f"合格数量 {qualified}",
            }
        ],
        source_module=MODULE,
        source_type="PRODUCTION_COMPLETION",
        source_reference_id=report.id,
        source_no=report.report_no,
        remark="，".join(remark_parts),
        operator_id=operator_id,
    )

    if report.plan_id is not None and plan is not None:
        plan.completed_qty = _as_decimal(plan.completed_qty) + qualified
        plan.updated_by = operator_id
    if dispatch is not None:
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
        detail=(
            f"确认完工报告 {report.report_no}，推送库存入库单 {pushed['operation_no']}"
            f"（合格 {qualified}）"
        ),
    )
    _advance_after_completion(
        db, report, plan, dispatch, qualified, operator_id=operator_id
    )
    return report


def cancel_completion_report(
    db: Session, report_id: int, operator_id: Optional[int] = None
) -> models.PlnCompletionReport:
    """取消完工报告（仅 DRAFT），并撤销尚未确认的库存入库单。"""
    report = _require_completion(db, report_id)
    if report.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, f"完工报告当前状态为 {report.status}，不能取消")
    cancel_pending_inout_orders(
        db,
        source_module=MODULE,
        source_type="PRODUCTION_COMPLETION",
        source_reference_id=report.id,
        operator_id=operator_id,
        reason=f"完工报告 {report.report_no} 取消",
    )
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


def delete_completion_report(
    db: Session, report_id: int, operator_id: Optional[int] = None
) -> None:
    """删除完工报告：仅 DRAFT / CANCELLED 可删。

    已确认（COMPLETED）的完工报告已写库存入库流水并回写计划/派工已完工数量，不可删除。
    """
    report = _require_completion(db, report_id)
    _ensure_deletable(report.status, "完工报告")
    number = report.report_no
    db.delete(report)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="pln_completion_report",
        target_id=report_id,
        operator_id=operator_id,
        detail=f"删除完工报告 {number}",
    )


# ---------------- 批量删除 ----------------


def batch_delete(
    db: Session,
    ids: Sequence[int],
    deleter,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """通用批量删除：对每个 ID 调用单删函数，单条失败不中断并收集原因。

    `deleter` 为对应资源的单删函数（签名 `(db, id, operator_id)`）。
    失败原因来自 `BusinessException`（状态不允许 / 存在下游引用 / 不存在），
    返回 `{deleted_count, skipped:[{id, reason}]}`；批内重复 ID 已去重。
    """
    unique_ids = list(dict.fromkeys(int(i) for i in ids))
    if not unique_ids:
        raise BusinessException(CODE_PARAM_INVALID, "ids 不能为空")
    skipped: List[Dict[str, Any]] = []
    deleted_count = 0
    for record_id in unique_ids:
        try:
            deleter(db, record_id, operator_id)
        except BusinessException as exc:
            skipped.append({"id": record_id, "reason": exc.message})
            continue
        deleted_count += 1
    return {"deleted_count": deleted_count, "skipped": skipped}


# ==================== 统计 ====================


def stats(db: Session) -> Dict[str, Any]:
    """计划模块统计（供首页 / 综合查询使用）。

    「本期」= 当前年月（如 `2026-10`），按 MPS **行明细**的 `period_label` 月度时段统计，
    且仅计入已确认及以上状态（`_ACTIVE_PLAN_STATUSES`），排除 DRAFT 草稿与 CANCELLED。
    `buy_count` / `make_count` 只统计**最新一次 MRP 批次**的供需分流结果，
    避免随每次运算无限累加。`demand_count`（需求总量）同样排除 DRAFT 草稿与
    CANCELLED，与 `mps_planned_qty` 口径保持一致。
    """
    current_period = date.today().strftime("%Y-%m")
    latest_run_id = repository.latest_mrp_run_id(db)
    return {
        "current_period": current_period,
        "mps_planned_qty": repository.sum_mps_planned_qty(
            db, current_period, _ACTIVE_PLAN_STATUSES
        ),
        "mps_count": repository.count_all(db, models.PlnMps),
        "demand_count": repository.count_demands_by_statuses(db, _ACTIVE_DEMAND_STATUSES),
        "mrp_run_count": repository.count_all(db, models.PlnMrpRun),
        "mrp_result_count": repository.count_all(db, models.PlnMrpResult),
        "make_count": repository.count_mrp_results_by_supply(db, "MAKE", latest_run_id),
        "buy_count": repository.count_mrp_results_by_supply(db, "BUY", latest_run_id),
        "open_plan_count": repository.count_open(db, models.PlnProductionPlan, _TERMINAL_STATUSES),
        "open_dispatch_count": repository.count_open(db, models.PlnDispatchOrder, _TERMINAL_STATUSES),
        "open_requisition_count": repository.count_open(
            db, models.PlnMaterialRequisition, _TERMINAL_STATUSES
        ),
        "completion_report_count": repository.count_all(db, models.PlnCompletionReport),
    }