"""planning 模块跨模块契约（**唯一对外入口**）。

规则（规格 §7 / §14 / §24 / §35）：

1. 其它模块**只允许** import 本文件，禁止 import planning 的 `models` / `repository` / `service`。
2. **本文件的函数永不 `db.commit()`**：它们运行在调用方的事务里，保证
   “上游业务单据 + planning 计划单据” 要么一起成功、要么一起回滚。
3. 只返回普通 `dict` / 标量，不返回 ORM 对象，避免会话与懒加载外泄。
4. 签名一经确定即视为公共接口，修改需同步其它模块。

主要调用方：

- Inventory：确认 `PRODUCTION` 生产补库需求时调用
  `create_production_plan_from_replenishment`，把补库需求转成正式生产作业计划。
- Procurement：从 MRP 的 BUY 结果生成采购计划时调用 `get_mrp_results`。
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.planning import repository, service
from app.modules.planning.service import CODE_CONTRACT_NOT_READY, CODE_NOT_FOUND
from app.modules.system.contract import get_materials, log_operation


def create_sales_demand_from_shortage(
    db: Session,
    *,
    order_id: int,
    order_no: str,
    material_id: int,
    quantity: Decimal,
    due_date: date,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """销售订单确认时库存不足，把缺口登记为 `source_type=SALES` 的计划需求。

    - 去重键 = 来源订单 + 物料：同一订单同一物料只保留一条缺口需求，重复受理幂等；
    - 需求直接置 `CONFIRMED`（订单已确认，缺口是确定需求），可立即进入 MPS 汇总；
    - **不提交事务**，由调用方（Sales）提交，保证订单状态与需求同时生效。
    """
    existing = repository.find_demand_by_source_material(
        db, "SALES", order_id, order_no, material_id
    )
    if existing:
        return {
            "demand_id": existing.id,
            "demand_no": existing.demand_no,
            "created": False,
        }
    demand = service.create_demand(
        db,
        source_type="SALES",
        material_id=material_id,
        quantity=quantity,
        due_date=due_date,
        source_reference_id=order_id,
        source_no=order_no,
        remark=remark or f"销售订单 {order_no} 库存不足缺口",
        operator_id=operator_id,
    )
    service.set_demand_status(db, demand.id, "CONFIRMED", operator_id)
    return {"demand_id": demand.id, "demand_no": demand.demand_no, "created": True}


def cancel_sales_demands_for_order(
    db: Session, order_id: int, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    """销售订单取消时回收其缺口需求。

    只取消尚未进入 MPS 的 `DRAFT` / `CONFIRMED` 需求；已 `RELEASED`
    （已被 MPS 汇总引用）的需求保留，避免破坏已下达的主生产计划。
    **不提交事务**，由 Sales 与订单状态变更一同提交。
    """
    demands = repository.list_open_sales_demands_by_order(db, order_id)
    cancelled: List[str] = []
    for demand in demands:
        service.set_demand_status(db, demand.id, "CANCELLED", operator_id)
        cancelled.append(demand.demand_no)
    return {"cancelled_count": len(cancelled), "demand_nos": cancelled}


def create_production_plan_from_replenishment(db: Session, request_id: int) -> Dict[str, Any]:
    """受理 Inventory 的生产补库需求：生成正式生产作业计划并返回其引用。

    - `source_type="REPLENISHMENT"`、`source_reference_id=request_id`；
    - 需求明细通过 `inventory.contract.get_replenishment_request(db, request_id)` 读取（惰性导入）；
    - 同一补库需求重复受理时返回已生成的计划（幂等，不重复建单）；
    - **不提交事务**，由调用方提交。
    """
    existing = repository.find_plan_by_source(db, "REPLENISHMENT", request_id)
    if existing:
        return {"plan_id": existing.id, "plan_no": existing.plan_no}

    try:
        from app.modules.inventory import contract as inventory_contract  # type: ignore

        getter = getattr(inventory_contract, "get_replenishment_request", None)
    except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
        raise BusinessException(CODE_CONTRACT_NOT_READY, "库存补库需求接口尚未就绪") from exc
    if getter is None:
        raise BusinessException(CODE_CONTRACT_NOT_READY, "库存补库需求接口尚未就绪")

    request = getter(db, request_id)

    def _field(name: str, default: Any = None) -> Any:
        if isinstance(request, dict):
            return request.get(name, default)
        return getattr(request, name, default)

    material_id = int(_field("material_id"))
    if not get_materials(db, [material_id]):
        raise BusinessException(CODE_NOT_FOUND, f"物料不存在：{material_id}")

    required_date = _field("required_date") or date.today()
    today = date.today()
    end_date = required_date if required_date >= today else today
    plan = service.create_production_plan(
        db,
        material_id=material_id,
        planned_qty=Decimal(str(_field("request_qty") or 0)),
        plan_date=today,
        start_date=today,
        end_date=end_date,
        source_type="REPLENISHMENT",
        source_reference_id=request_id,
        remark=f"受理库存补库需求 {_field('request_no')}",
    )
    return {"plan_id": plan.id, "plan_no": plan.plan_no}


def create_production_plan_from_mrp_result(db: Session, mrp_result_id: int) -> Dict[str, Any]:
    """由一条 MRP MAKE 结果生成生产作业计划并返回其引用（**不提交事务**）。"""
    result = repository.get_mrp_result(db, mrp_result_id)
    if not result:
        raise BusinessException(CODE_NOT_FOUND, f"MRP 结果不存在：{mrp_result_id}")
    existing = repository.find_plan_by_mrp_result(db, mrp_result_id)
    if existing:
        return {"plan_id": existing.id, "plan_no": existing.plan_no}
    plan = service._create_plan_from_mrp_result(db, result)
    log_operation(
        db,
        module="planning",
        action="CREATE",
        target_type="pln_production_plan",
        target_id=plan.id,
        detail=f"跨模块按 MRP 结果 {mrp_result_id} 生成作业计划 {plan.plan_no}",
    )
    return {"plan_id": plan.id, "plan_no": plan.plan_no}


def get_mrp_results(db: Session, result_ids: Sequence[int]) -> List[Dict[str, Any]]:
    """批量读取 MRP 结果（供 Procurement 从 BUY 结果生成采购计划）。"""
    rows = repository.get_mrp_results_by_ids(db, result_ids)
    materials = get_materials(db, [row.material_id for row in rows])
    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "material_id": row.material_id,
            "material_code": materials.get(row.material_id, {}).get("material_code"),
            "order_qty": Decimal(str(row.order_qty)),
            "requirement_date": row.requirement_date,
            "supply_type": row.supply_type,
            "status": row.status,
        }
        for row in rows
    ]


def get_open_production_qty(db: Session, material_id: int) -> Decimal:
    """某物料未完工的生产数量合计（终态单据不计），供需求净算参考。"""
    return repository.sum_open_production_qty(db, material_id)