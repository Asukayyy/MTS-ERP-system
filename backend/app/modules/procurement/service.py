"""procurement 模块业务逻辑层。

硬性约定（规格 §7 / §14 / §16.5 / §24 / §35 / §42）：

1. **采购模块永不直接改库存**：到货确认必须调用 `inventory.contract.increase_stock`，
   由库存引擎写 `PURCHASE_RECEIPT` 流水并更新结存，禁止绕过库存流水改结存。
2. **只有一个物料主数据 / 人员表**：物料、采购员、评价人分别经 `system.contract`
   的 `get_material` / `get_materials` / `get_personnel` 读取，不另建采购物料表 / 采购员表。
3. **采购计划来源跨模块**：MRP `BUY` 结果经 `planning.contract.get_mrp_results` 读取，
   库存订货点补库需求经 `inventory.contract.get_replenishment_request` 读取
   （均**函数内惰性 import**，契约尚未就绪时抛 4007）。
4. 本层**不调用 `db.commit()`**：由 router 提交；`contract.py` 函数运行在调用方事务里。
5. 每个状态变更在同一事务内写操作日志（`system.contract.log_operation`）。

错误码区段：`4000~4999`。
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.inventory.contract import increase_stock
from app.modules.procurement import models, repository
from app.modules.system.contract import (
    get_material,
    get_materials,
    get_personnel,
    get_personnel_name,
    log_operation,
    search_materials,
)
from app.shared.enums import RecordStatus, SupplyType

# ==================== 错误码（4000~4999） ====================

CODE_PARAM_INVALID = 4000  # 入参 / 状态非法
CODE_DUPLICATE = 4001  # 供应商编码重复
CODE_SUPPLIER_MATERIAL_DUPLICATE = 4002  # 供应商-物料关系重复
CODE_IMMUTABLE = 4003  # 已确认 / 已下达 / 已完结单据不可修改
CODE_RECEIPT_QTY_EXCEED = 4004  # 到货数量超过未到货数量
CODE_NOT_FOUND = 4005  # 资源不存在
CODE_STATUS_INVALID = 4006  # 单据状态不允许该流转
CODE_CONTRACT_NOT_READY = 4007  # 跨模块契约尚未就绪

MODULE = "procurement"

_SUPPLIER_STATUSES = {RecordStatus.ACTIVE.value, RecordStatus.INACTIVE.value}
_PLAN_SOURCE_TYPES = {"MRP", "REORDER", "MANUAL"}
_PLAN_STATUSES = {"DRAFT", "CONFIRMED", "RELEASED", "COMPLETED", "CANCELLED"}
_PLAN_TERMINAL = {"COMPLETED", "CANCELLED"}
# 采购计划状态机：DRAFT → CONFIRMED → RELEASED → COMPLETED，另可从非终态取消
_PLAN_TRANSITIONS: Dict[str, set] = {
    "DRAFT": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"RELEASED", "CANCELLED"},
    "RELEASED": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}
_ORDER_STATUSES = {
    "DRAFT",
    "CONFIRMED",
    "RELEASED",
    "IN_PROGRESS",
    "COMPLETED",
    "CANCELLED",
}
_ORDER_TERMINAL = {"COMPLETED", "CANCELLED"}
# 采购订单状态机：DRAFT → CONFIRMED → RELEASED → IN_PROGRESS → COMPLETED
_ORDER_TRANSITIONS: Dict[str, set] = {
    "DRAFT": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"RELEASED", "CANCELLED"},
    "RELEASED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}
_RECEIPT_STATUSES = {"DRAFT", "CONFIRMED", "COMPLETED", "CANCELLED"}
# 允许到货 / 收货的订单状态（规格：CONFIRMED / RELEASED / IN_PROGRESS）
_RECEIVABLE_ORDER_STATUSES = {"CONFIRMED", "RELEASED", "IN_PROGRESS"}
_CENT = Decimal("0.01")
_SCORE_STEP = Decimal("0.0001")


# ==================== 小工具 ====================


def _as_decimal(value: Any) -> Decimal:
    """把 int / str / Decimal / None 统一转成 Decimal。"""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    """金额统一四舍五入到分。"""
    return _as_decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def _material_fields(material: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    material = material or {}
    return {
        "material_code": material.get("material_code"),
        "material_name": material.get("material_name"),
    }


def _material_map(db: Session, material_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    return get_materials(db, [int(i) for i in material_ids if i])


def _supplier_name_map(db: Session, supplier_ids: Sequence[int]) -> Dict[int, str]:
    return {
        sid: row.supplier_name
        for sid, row in repository.get_suppliers(db, supplier_ids).items()
    }


def _require_supplier(db: Session, supplier_id: Optional[int]) -> models.PurSupplier:
    if not supplier_id:
        raise BusinessException(CODE_PARAM_INVALID, "供应商ID不能为空")
    supplier = repository.get_supplier(db, supplier_id)
    if not supplier:
        raise BusinessException(CODE_NOT_FOUND, f"供应商不存在：{supplier_id}")
    return supplier


def _require_material(db: Session, material_id: Optional[int]) -> Dict[str, Any]:
    if not material_id:
        raise BusinessException(CODE_PARAM_INVALID, "物料ID不能为空")
    material = get_material(db, material_id)
    if not material:
        raise BusinessException(CODE_NOT_FOUND, f"物料不存在：{material_id}")
    return material


def _require_personnel(db: Session, personnel_id: Optional[int]) -> Dict[str, Any]:
    person = get_personnel(db, personnel_id) if personnel_id else None
    if not person:
        raise BusinessException(CODE_NOT_FOUND, f"员工不存在：{personnel_id}")
    return person


def _require_plan(db: Session, plan_id: int) -> models.PurPurchasePlan:
    plan = repository.get_plan(db, plan_id)
    if not plan:
        raise BusinessException(CODE_NOT_FOUND, f"采购计划不存在：{plan_id}")
    return plan


def _require_order(db: Session, order_id: int) -> models.PurOrder:
    order = repository.get_order(db, order_id)
    if not order:
        raise BusinessException(CODE_NOT_FOUND, f"采购订单不存在：{order_id}")
    return order


def _require_receipt(db: Session, receipt_id: int) -> models.PurReceipt:
    receipt = repository.get_receipt(db, receipt_id)
    if not receipt:
        raise BusinessException(CODE_NOT_FOUND, f"到货单不存在：{receipt_id}")
    return receipt


def _require_evaluation(db: Session, evaluation_id: int) -> models.PurSupplierEvaluation:
    evaluation = repository.get_evaluation(db, evaluation_id)
    if not evaluation:
        raise BusinessException(CODE_NOT_FOUND, f"供应商评价不存在：{evaluation_id}")
    return evaluation


# ==================== 出参拼装 ====================


def _supplier_dict(row: models.PurSupplier) -> Dict[str, Any]:
    return {
        "id": row.id,
        "supplier_code": row.supplier_code,
        "supplier_name": row.supplier_name,
        "contact_person": row.contact_person,
        "phone": row.phone,
        "email": row.email,
        "address": row.address,
        "status": row.status,
        "remark": row.remark,
    }


def _supplier_material_dict(
    db: Session,
    row: models.PurSupplierMaterial,
    materials: Dict[int, Dict[str, Any]],
    supplier_name: Optional[str],
) -> Dict[str, Any]:
    return {
        "id": row.id,
        "supplier_id": row.supplier_id,
        "supplier_name": supplier_name,
        "material_id": row.material_id,
        **_material_fields(materials.get(row.material_id)),
        "is_primary": row.is_primary,
        "supply_price": _as_decimal(row.supply_price),
        "lead_time_days": row.lead_time_days,
        "min_order_qty": _as_decimal(row.min_order_qty),
        "status": row.status,
    }


def _plan_item_dict(
    item: models.PurPurchasePlanItem,
    materials: Dict[int, Dict[str, Any]],
    suppliers: Dict[int, str],
) -> Dict[str, Any]:
    return {
        "id": item.id,
        "plan_id": item.plan_id,
        "material_id": item.material_id,
        **_material_fields(materials.get(item.material_id)),
        "required_qty": _as_decimal(item.required_qty),
        "ordered_qty": _as_decimal(item.ordered_qty),
        "required_date": item.required_date,
        "source_type": item.source_type,
        "source_reference_id": item.source_reference_id,
        "supplier_id": item.supplier_id,
        "supplier_name": suppliers.get(item.supplier_id) if item.supplier_id else None,
        "status": item.status,
        "remark": item.remark,
    }


def _plan_dict(
    db: Session, plan: models.PurPurchasePlan
) -> Dict[str, Any]:
    items = repository.get_plan_items(db, plan.id)
    materials = _material_map(db, [i.material_id for i in items])
    suppliers = _supplier_name_map(db, [i.supplier_id for i in items if i.supplier_id])
    return {
        "id": plan.id,
        "plan_no": plan.plan_no,
        "plan_date": plan.plan_date,
        "status": plan.status,
        "remark": plan.remark,
        "items": [_plan_item_dict(i, materials, suppliers) for i in items],
    }


def _order_item_dict(
    item: models.PurOrderItem, materials: Dict[int, Dict[str, Any]]
) -> Dict[str, Any]:
    return {
        "id": item.id,
        "order_id": item.order_id,
        "line_no": item.line_no,
        "material_id": item.material_id,
        **_material_fields(materials.get(item.material_id)),
        "quantity": _as_decimal(item.quantity),
        "received_qty": _as_decimal(item.received_qty),
        "unit_price": _as_decimal(item.unit_price),
        "amount": _as_decimal(item.amount),
        "remark": item.remark,
    }


def _order_dict(
    db: Session,
    order: models.PurOrder,
    supplier_name: Optional[str],
    buyer_name: Optional[str],
) -> Dict[str, Any]:
    items = repository.get_order_items(db, order.id)
    materials = _material_map(db, [i.material_id for i in items])
    return {
        "id": order.id,
        "order_no": order.order_no,
        "supplier_id": order.supplier_id,
        "supplier_name": supplier_name,
        "order_date": order.order_date,
        "expected_date": order.expected_date,
        "buyer_id": order.buyer_id,
        "buyer_name": buyer_name,
        "total_amount": _as_decimal(order.total_amount),
        "status": order.status,
        "remark": order.remark,
        "items": [_order_item_dict(i, materials) for i in items],
    }


def _order_view(db: Session, order: models.PurOrder) -> Dict[str, Any]:
    supplier = repository.get_supplier(db, order.supplier_id)
    return _order_dict(
        db,
        order,
        supplier.supplier_name if supplier else None,
        get_personnel_name(db, order.buyer_id),
    )


def _receipt_dict(
    db: Session,
    receipt: models.PurReceipt,
    supplier_name: Optional[str],
    order_no: Optional[str],
) -> Dict[str, Any]:
    items = repository.get_receipt_items(db, receipt.id)
    materials = _material_map(db, [i.material_id for i in items])
    return {
        "id": receipt.id,
        "receipt_no": receipt.receipt_no,
        "purchase_order_id": receipt.purchase_order_id,
        "order_no": order_no,
        "supplier_id": receipt.supplier_id,
        "supplier_name": supplier_name,
        "warehouse_id": receipt.warehouse_id,
        "receipt_date": receipt.receipt_date,
        "status": receipt.status,
        "remark": receipt.remark,
        "items": [
            {
                "id": item.id,
                "receipt_id": item.receipt_id,
                "order_item_id": item.order_item_id,
                "material_id": item.material_id,
                **_material_fields(materials.get(item.material_id)),
                "location_id": item.location_id,
                "quantity": _as_decimal(item.quantity),
                "qualified_qty": _as_decimal(item.qualified_qty),
                "remark": item.remark,
            }
            for item in items
        ],
    }


def _receipt_view(db: Session, receipt: models.PurReceipt) -> Dict[str, Any]:
    supplier = repository.get_supplier(db, receipt.supplier_id)
    order = repository.get_order(db, receipt.purchase_order_id)
    return _receipt_dict(
        db,
        receipt,
        supplier.supplier_name if supplier else None,
        order.order_no if order else None,
    )


def _evaluation_dict(
    row: models.PurSupplierEvaluation,
    supplier_name: Optional[str],
    evaluator_name: Optional[str],
) -> Dict[str, Any]:
    return {
        "id": row.id,
        "supplier_id": row.supplier_id,
        "supplier_name": supplier_name,
        "evaluate_date": row.evaluate_date,
        "quality_score": _as_decimal(row.quality_score),
        "delivery_score": _as_decimal(row.delivery_score),
        "price_score": _as_decimal(row.price_score),
        "total_score": _as_decimal(row.total_score),
        "evaluator_id": row.evaluator_id,
        "evaluator_name": evaluator_name,
        "remark": row.remark,
    }


# ==================== 供应商 ====================


def list_suppliers(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_suppliers(db, page, page_size, keyword, status)
    return [_supplier_dict(row) for row in rows], total


def get_supplier(db: Session, supplier_id: int) -> Dict[str, Any]:
    return _supplier_dict(_require_supplier(db, supplier_id))


def create_supplier(
    db: Session,
    *,
    supplier_code: str,
    supplier_name: str,
    contact_person: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    address: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    if repository.get_supplier_by_code(db, supplier_code):
        raise BusinessException(CODE_DUPLICATE, f"供应商编码已存在：{supplier_code}")
    supplier = models.PurSupplier(
        supplier_code=supplier_code,
        supplier_name=supplier_name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        address=address,
        status=RecordStatus.ACTIVE.value,
        remark=remark,
        created_by=operator_id,
    )
    repository.add_supplier(db, supplier)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pur_supplier",
        target_id=supplier.id,
        operator_id=operator_id,
        detail=f"新增供应商 {supplier_code}",
    )
    return _supplier_dict(supplier)


def update_supplier(
    db: Session,
    supplier_id: int,
    *,
    supplier_name: Optional[str] = None,
    contact_person: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    address: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    supplier = _require_supplier(db, supplier_id)
    if supplier_name is not None:
        supplier.supplier_name = supplier_name
    if contact_person is not None:
        supplier.contact_person = contact_person
    if phone is not None:
        supplier.phone = phone
    if email is not None:
        supplier.email = email
    if address is not None:
        supplier.address = address
    if remark is not None:
        supplier.remark = remark
    supplier.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="pur_supplier",
        target_id=supplier.id,
        operator_id=operator_id,
        detail=f"修改供应商 {supplier.supplier_code}",
    )
    return _supplier_dict(supplier)


def set_supplier_status(
    db: Session, supplier_id: int, status: str, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    """供应商停用 = 置 INACTIVE，从不物理删除（规格 §20）。"""
    if status not in _SUPPLIER_STATUSES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法状态：{status}（供应商不物理删除，仅停用）")
    supplier = _require_supplier(db, supplier_id)
    supplier.status = status
    supplier.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="pur_supplier",
        target_id=supplier.id,
        operator_id=operator_id,
        detail=f"供应商 {supplier.supplier_code} 状态改为 {status}",
    )
    return _supplier_dict(supplier)


# ==================== 供应商-物料关系 ====================


def list_supplier_materials(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    supplier_id: Optional[int] = None,
    material_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_supplier_materials(
        db, page, page_size, supplier_id, material_id
    )
    materials = _material_map(db, [r.material_id for r in rows])
    suppliers = _supplier_name_map(db, [r.supplier_id for r in rows])
    items = [
        _supplier_material_dict(db, row, materials, suppliers.get(row.supplier_id))
        for row in rows
    ]
    return items, total


def create_supplier_material(
    db: Session,
    *,
    supplier_id: int,
    material_id: int,
    is_primary: bool = False,
    supply_price: Decimal = Decimal("0"),
    lead_time_days: int = 0,
    min_order_qty: Decimal = Decimal("0"),
    status: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    _require_supplier(db, supplier_id)
    _require_material(db, material_id)
    if repository.get_supplier_material_by_pair(db, supplier_id, material_id):
        raise BusinessException(
            CODE_SUPPLIER_MATERIAL_DUPLICATE,
            f"该供应商与物料的供货关系已存在：供应商 {supplier_id} / 物料 {material_id}",
        )
    link_status = status or RecordStatus.ACTIVE.value
    if link_status not in _SUPPLIER_STATUSES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法状态：{link_status}")
    link = models.PurSupplierMaterial(
        supplier_id=supplier_id,
        material_id=material_id,
        is_primary=is_primary,
        supply_price=_as_decimal(supply_price),
        lead_time_days=int(lead_time_days or 0),
        min_order_qty=_as_decimal(min_order_qty),
        status=link_status,
        created_by=operator_id,
    )
    repository.add_supplier_material(db, link)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pur_supplier_material",
        target_id=link.id,
        operator_id=operator_id,
        detail=f"新增供应商-物料关系 供应商{supplier_id}/物料{material_id}",
    )
    return _supplier_material_dict(db, link, _material_map(db, [material_id]), None)


def update_supplier_material(
    db: Session,
    link_id: int,
    *,
    is_primary: Optional[bool] = None,
    supply_price: Optional[Decimal] = None,
    lead_time_days: Optional[int] = None,
    min_order_qty: Optional[Decimal] = None,
    status: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    link = repository.get_supplier_material(db, link_id)
    if not link:
        raise BusinessException(CODE_NOT_FOUND, f"供应商-物料关系不存在：{link_id}")
    if is_primary is not None:
        link.is_primary = is_primary
    if supply_price is not None:
        link.supply_price = _as_decimal(supply_price)
    if lead_time_days is not None:
        link.lead_time_days = int(lead_time_days)
    if min_order_qty is not None:
        link.min_order_qty = _as_decimal(min_order_qty)
    if status is not None:
        if status not in _SUPPLIER_STATUSES:
            raise BusinessException(CODE_PARAM_INVALID, f"非法状态：{status}")
        link.status = status
    link.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="pur_supplier_material",
        target_id=link.id,
        operator_id=operator_id,
        detail=f"修改供应商-物料关系 {link.id}",
    )
    return _supplier_material_dict(
        db, link, _material_map(db, [link.material_id]), None
    )


def delete_supplier_material(
    db: Session, link_id: int, operator_id: Optional[int] = None
) -> None:
    link = repository.get_supplier_material(db, link_id)
    if not link:
        raise BusinessException(CODE_NOT_FOUND, f"供应商-物料关系不存在：{link_id}")
    repository.delete_supplier_material(db, link)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="pur_supplier_material",
        target_id=link_id,
        operator_id=operator_id,
        detail=f"删除供应商-物料关系 {link_id}",
    )


# ==================== 采购材料查询（只读物料主数据） ====================


def list_purchase_materials(
    db: Session, keyword: Optional[str] = None
) -> List[Dict[str, Any]]:
    """可采购物料：直接读取 `system.contract`，仅保留 `supply_type == BUY`，不建采购物料表。"""
    return [
        material
        for material in search_materials(db, keyword=keyword)
        if material.get("supply_type") == SupplyType.BUY.value
    ]


# ==================== 采购计划 ====================


def _add_plan_item(
    db: Session, plan_id: int, raw: Dict[str, Any]
) -> models.PurPurchasePlanItem:
    """校验并写入一条采购计划行。"""
    source_type = raw.get("source_type") or "MANUAL"
    if source_type not in _PLAN_SOURCE_TYPES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法计划来源类型：{source_type}")
    _require_material(db, raw.get("material_id"))
    qty = _as_decimal(raw.get("required_qty"))
    if qty <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "计划需求数量必须为正数")
    required_date = raw.get("required_date")
    if required_date is None:
        raise BusinessException(CODE_PARAM_INVALID, "计划行需求日期不能为空")
    supplier_id = raw.get("supplier_id")
    if supplier_id:
        _require_supplier(db, supplier_id)
    item = models.PurPurchasePlanItem(
        plan_id=plan_id,
        material_id=raw["material_id"],
        required_qty=qty,
        ordered_qty=Decimal("0"),
        required_date=required_date,
        source_type=source_type,
        source_reference_id=raw.get("source_reference_id"),
        supplier_id=supplier_id,
        status="DRAFT",
        remark=raw.get("remark"),
    )
    return repository.add_plan_item(db, item)


def _create_plan_header(
    db: Session,
    *,
    plan_date: date,
    remark: Optional[str],
    plan_no: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.PurPurchasePlan:
    if plan_no:
        if repository.get_plan_by_no(db, plan_no):
            raise BusinessException(CODE_DUPLICATE, f"采购计划编号已存在：{plan_no}")
    else:
        plan_no = repository.next_no(
            db, models.PurPurchasePlan, models.PurPurchasePlan.plan_no, f"PP{plan_date:%Y%m%d}"
        )
    plan = models.PurPurchasePlan(
        plan_no=plan_no,
        plan_date=plan_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    return repository.add_plan(db, plan)


def _resolve_reusable_plan(
    db: Session, source_type: str, reference_ids: Sequence[int]
) -> Optional[models.PurPurchasePlan]:
    """幂等：按来源找到尚未终结的采购计划，可复用扩展；否则返回 None。"""
    for item in repository.find_plan_items_by_source(db, source_type, reference_ids):
        plan = repository.get_plan(db, item.plan_id)
        if plan and plan.status not in _PLAN_TERMINAL:
            return plan
    return None


def create_plan(
    db: Session,
    *,
    items: Sequence[Dict[str, Any]],
    plan_date: Optional[date] = None,
    plan_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "采购计划至少需要一条明细")
    plan = _create_plan_header(
        db,
        plan_date=plan_date or date.today(),
        plan_no=plan_no,
        remark=remark,
        operator_id=operator_id,
    )
    for raw in items:
        _add_plan_item(db, plan.id, raw)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pur_purchase_plan",
        target_id=plan.id,
        operator_id=operator_id,
        detail=f"新增采购计划 {plan.plan_no}",
    )
    return _plan_dict(db, plan)


def list_plans(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    keyword: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_plans(
        db, page, page_size, status, date_from, date_to, keyword
    )
    return [_plan_dict(db, row) for row in rows], total


def get_plan(db: Session, plan_id: int) -> Dict[str, Any]:
    return _plan_dict(db, _require_plan(db, plan_id))


def update_plan(
    db: Session,
    plan_id: int,
    *,
    plan_date: Optional[date] = None,
    remark: Optional[str] = None,
    items: Optional[Sequence[Dict[str, Any]]] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    plan = _require_plan(db, plan_id)
    if plan.status != "DRAFT":
        raise BusinessException(
            CODE_IMMUTABLE, f"采购计划 {plan.plan_no} 已 {plan.status}，不可修改"
        )
    if plan_date is not None:
        plan.plan_date = plan_date
    if remark is not None:
        plan.remark = remark
    if items is not None:
        if not items:
            raise BusinessException(CODE_PARAM_INVALID, "采购计划至少需要一条明细")
        repository.delete_plan_items(db, plan.id)
        db.flush()
        for raw in items:
            _add_plan_item(db, plan.id, raw)
    plan.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="pur_purchase_plan",
        target_id=plan.id,
        operator_id=operator_id,
        detail=f"修改采购计划 {plan.plan_no}",
    )
    return _plan_dict(db, plan)


def delete_plan(db: Session, plan_id: int, operator_id: Optional[int] = None) -> None:
    plan = _require_plan(db, plan_id)
    if plan.status != "DRAFT":
        raise BusinessException(
            CODE_IMMUTABLE, f"采购计划 {plan.plan_no} 已 {plan.status}，不可删除"
        )
    no = plan.plan_no
    repository.delete_plan(db, plan)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="pur_purchase_plan",
        target_id=plan_id,
        operator_id=operator_id,
        detail=f"删除采购计划 {no}",
    )


def set_plan_status(
    db: Session, plan_id: int, status: str, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    if status not in _PLAN_STATUSES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法计划状态：{status}")
    plan = _require_plan(db, plan_id)
    if plan.status in _PLAN_TERMINAL:
        raise BusinessException(
            CODE_IMMUTABLE, f"采购计划已 {plan.status}，不可再流转"
        )
    if status not in _PLAN_TRANSITIONS.get(plan.status, set()):
        raise BusinessException(
            CODE_STATUS_INVALID, f"计划状态不允许从 {plan.status} 流转到 {status}"
        )
    plan.status = status
    for item in repository.get_plan_items(db, plan.id):
        item.status = status
    plan.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="pur_purchase_plan",
        target_id=plan.id,
        operator_id=operator_id,
        detail=f"采购计划 {plan.plan_no} 状态改为 {status}",
    )
    return _plan_dict(db, plan)


# ==================== 采购订单 ====================


def _build_order_items(
    db: Session, order_id: int, raw_items: Sequence[Dict[str, Any]]
) -> Decimal:
    """按入参写入订单行，返回订单总金额（`amount = quantity × unit_price`）。"""
    total = Decimal("0")
    for index, raw in enumerate(raw_items, start=1):
        material_id = raw.get("material_id")
        _require_material(db, material_id)
        qty = _as_decimal(raw.get("quantity"))
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "采购数量必须为正数")
        unit_price = _as_decimal(raw.get("unit_price"))
        if unit_price < 0:
            raise BusinessException(CODE_PARAM_INVALID, "单价不能为负数")
        amount = _money(qty * unit_price)
        total += amount
        repository.add_order_item(
            db,
            models.PurOrderItem(
                order_id=order_id,
                line_no=index,
                material_id=material_id,
                quantity=qty,
                received_qty=Decimal("0"),
                unit_price=unit_price,
                amount=amount,
                remark=raw.get("remark"),
            ),
        )
    return _money(total)


def create_order(
    db: Session,
    *,
    supplier_id: int,
    order_date: date,
    expected_date: date,
    items: Sequence[Dict[str, Any]],
    buyer_id: Optional[int] = None,
    order_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    _require_supplier(db, supplier_id)
    if buyer_id:
        _require_personnel(db, buyer_id)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "采购订单至少需要一条明细")
    if order_no:
        if repository.get_order_by_no(db, order_no):
            raise BusinessException(CODE_DUPLICATE, f"采购订单号已存在：{order_no}")
    else:
        order_no = repository.next_no(
            db, models.PurOrder, models.PurOrder.order_no, f"PO{order_date:%Y%m%d}"
        )
    order = models.PurOrder(
        order_no=order_no,
        supplier_id=supplier_id,
        order_date=order_date,
        expected_date=expected_date,
        buyer_id=buyer_id,
        total_amount=Decimal("0"),
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_order(db, order)
    order.total_amount = _build_order_items(db, order.id, items)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pur_order",
        target_id=order.id,
        operator_id=operator_id,
        detail=f"新增采购订单 {order.order_no}，金额 {order.total_amount}",
    )
    return _order_view(db, order)


def list_orders(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    keyword: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_orders(
        db, page, page_size, supplier_id, status, date_from, date_to, keyword
    )
    suppliers = _supplier_name_map(db, [r.supplier_id for r in rows])
    items = [
        _order_dict(
            db,
            row,
            suppliers.get(row.supplier_id),
            get_personnel_name(db, row.buyer_id),
        )
        for row in rows
    ]
    return items, total


def get_order(db: Session, order_id: int) -> Dict[str, Any]:
    return _order_view(db, _require_order(db, order_id))


def update_order(
    db: Session,
    order_id: int,
    *,
    supplier_id: Optional[int] = None,
    order_date: Optional[date] = None,
    expected_date: Optional[date] = None,
    buyer_id: Optional[int] = None,
    items: Optional[Sequence[Dict[str, Any]]] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    order = _require_order(db, order_id)
    if order.status in _ORDER_TERMINAL:
        raise BusinessException(CODE_IMMUTABLE, f"采购订单已 {order.status}，不可修改")
    if order.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, "仅 DRAFT 状态的采购订单可修改")
    if supplier_id is not None:
        _require_supplier(db, supplier_id)
        order.supplier_id = supplier_id
    if order_date is not None:
        order.order_date = order_date
    if expected_date is not None:
        order.expected_date = expected_date
    if buyer_id is not None:
        if buyer_id:
            _require_personnel(db, buyer_id)
        order.buyer_id = buyer_id
    if remark is not None:
        order.remark = remark
    if items is not None:
        if not items:
            raise BusinessException(CODE_PARAM_INVALID, "采购订单至少需要一条明细")
        repository.delete_order_items(db, order.id)
        db.flush()
        order.total_amount = _build_order_items(db, order.id, items)
    order.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="pur_order",
        target_id=order.id,
        operator_id=operator_id,
        detail=f"修改采购订单 {order.order_no}",
    )
    return _order_view(db, order)


def delete_order(db: Session, order_id: int, operator_id: Optional[int] = None) -> None:
    order = _require_order(db, order_id)
    if order.status in _ORDER_TERMINAL:
        raise BusinessException(CODE_IMMUTABLE, f"采购订单已 {order.status}，不可删除")
    if order.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, "仅 DRAFT 状态的采购订单可删除")
    no = order.order_no
    repository.delete_order(db, order)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="pur_order",
        target_id=order_id,
        operator_id=operator_id,
        detail=f"删除采购订单 {no}",
    )


def set_order_status(
    db: Session, order_id: int, status: str, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    if status not in _ORDER_STATUSES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法订单状态：{status}")
    order = _require_order(db, order_id)
    if order.status in _ORDER_TERMINAL:
        raise BusinessException(CODE_IMMUTABLE, f"采购订单已 {order.status}，不可再流转")
    if status not in _ORDER_TRANSITIONS.get(order.status, set()):
        raise BusinessException(
            CODE_STATUS_INVALID, f"订单状态不允许从 {order.status} 流转到 {status}"
        )
    order.status = status
    order.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="pur_order",
        target_id=order.id,
        operator_id=operator_id,
        detail=f"采购订单 {order.order_no} 状态改为 {status}",
    )
    return _order_view(db, order)


def create_order_from_plan(
    db: Session,
    *,
    plan_id: int,
    supplier_id: int,
    order_date: Optional[date] = None,
    expected_date: Optional[date] = None,
    buyer_id: Optional[int] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """按采购计划生成 DRAFT 采购订单，并回写计划行已下单数量。

    - 单价优先取供应商-物料关系的 `supply_price`，缺失时取 0；
    - 预计到货日期未指定时 = 下单日期 + 供应商对该批物料的最大供货提前期；
    - 仅取「未下单数量 = required_qty − ordered_qty > 0」的计划行。
    """
    plan = _require_plan(db, plan_id)
    if plan.status in _PLAN_TERMINAL:
        raise BusinessException(CODE_IMMUTABLE, f"采购计划已 {plan.status}，不可生成订单")
    _require_supplier(db, supplier_id)
    if buyer_id:
        _require_personnel(db, buyer_id)
    plan_items = repository.get_plan_items(db, plan.id)
    terms = repository.supplier_material_terms(
        db, supplier_id, [item.material_id for item in plan_items]
    )
    order_date = order_date or date.today()
    lead_time_days = max(
        (int(term.lead_time_days) for term in terms.values()), default=0
    )
    if expected_date is None:
        expected_date = order_date + timedelta(days=lead_time_days)

    pending: List[Tuple[models.PurPurchasePlanItem, Decimal]] = []
    for item in plan_items:
        remaining = _as_decimal(item.required_qty) - _as_decimal(item.ordered_qty)
        if remaining > 0:
            pending.append((item, remaining))
    if not pending:
        raise BusinessException(CODE_PARAM_INVALID, "采购计划没有可下单的行")

    order_no = repository.next_no(
        db, models.PurOrder, models.PurOrder.order_no, f"PO{order_date:%Y%m%d}"
    )
    order = models.PurOrder(
        order_no=order_no,
        supplier_id=supplier_id,
        order_date=order_date,
        expected_date=expected_date,
        buyer_id=buyer_id,
        total_amount=Decimal("0"),
        status="DRAFT",
        remark=remark or f"由采购计划 {plan.plan_no} 生成",
        created_by=operator_id,
    )
    repository.add_order(db, order)

    total = Decimal("0")
    for index, (plan_item, qty) in enumerate(pending, start=1):
        term = terms.get(plan_item.material_id)
        unit_price = _as_decimal(term.supply_price) if term else Decimal("0")
        amount = _money(qty * unit_price)
        total += amount
        repository.add_order_item(
            db,
            models.PurOrderItem(
                order_id=order.id,
                line_no=index,
                material_id=plan_item.material_id,
                quantity=qty,
                received_qty=Decimal("0"),
                unit_price=unit_price,
                amount=amount,
            ),
        )
        plan_item.ordered_qty = _as_decimal(plan_item.ordered_qty) + qty
    order.total_amount = _money(total)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pur_order",
        target_id=order.id,
        operator_id=operator_id,
        detail=f"由采购计划 {plan.plan_no} 生成采购订单 {order.order_no}",
    )
    return _order_view(db, order)


# ==================== 到货登记 ====================


def create_receipt(
    db: Session,
    *,
    purchase_order_id: int,
    warehouse_id: int,
    receipt_date: date,
    items: Sequence[Dict[str, Any]],
    receipt_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    order = _require_order(db, purchase_order_id)
    if order.status not in _RECEIVABLE_ORDER_STATUSES:
        raise BusinessException(
            CODE_STATUS_INVALID, f"采购订单当前状态为 {order.status}，不能登记到货"
        )
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "到货单至少需要一条明细")
    if receipt_no:
        if repository.get_receipt_by_no(db, receipt_no):
            raise BusinessException(CODE_DUPLICATE, f"到货单号已存在：{receipt_no}")
    else:
        receipt_no = repository.next_no(
            db, models.PurReceipt, models.PurReceipt.receipt_no, f"PR{receipt_date:%Y%m%d}"
        )
    receipt = models.PurReceipt(
        receipt_no=receipt_no,
        purchase_order_id=order.id,
        supplier_id=order.supplier_id,
        warehouse_id=warehouse_id,
        receipt_date=receipt_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_receipt(db, receipt)
    for raw in items:
        order_item = repository.get_order_item(db, raw.get("order_item_id"))
        if not order_item or order_item.order_id != order.id:
            raise BusinessException(
                CODE_PARAM_INVALID, f"订单行不存在或不属于当前订单：{raw.get('order_item_id')}"
            )
        qty = _as_decimal(raw.get("quantity"))
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "到货数量必须为正数")
        remaining = _as_decimal(order_item.quantity) - _as_decimal(order_item.received_qty)
        if qty > remaining:
            raise BusinessException(
                CODE_RECEIPT_QTY_EXCEED,
                f"到货数量超过未到货数量：物料 {order_item.material_id} 未到货 {remaining}，本次 {qty}",
            )
        qualified_raw = raw.get("qualified_qty")
        qualified = qty if qualified_raw is None else _as_decimal(qualified_raw)
        if qualified < 0 or qualified > qty:
            raise BusinessException(
                CODE_PARAM_INVALID, "合格数量不能为负且不能超过到货数量"
            )
        repository.add_receipt_item(
            db,
            models.PurReceiptItem(
                receipt_id=receipt.id,
                order_item_id=order_item.id,
                material_id=order_item.material_id,
                location_id=raw.get("location_id"),
                quantity=qty,
                qualified_qty=qualified,
                remark=raw.get("remark"),
            ),
        )
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pur_receipt",
        target_id=receipt.id,
        operator_id=operator_id,
        detail=f"新增到货单 {receipt.receipt_no}",
    )
    return _receipt_view(db, receipt)


def list_receipts(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    purchase_order_id: Optional[int] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_receipts(db, page, page_size, purchase_order_id, status)
    suppliers = _supplier_name_map(db, [r.supplier_id for r in rows])
    orders = repository.get_orders(db, [r.purchase_order_id for r in rows])
    items = [
        _receipt_dict(
            db,
            row,
            suppliers.get(row.supplier_id),
            orders[row.purchase_order_id].order_no if row.purchase_order_id in orders else None,
        )
        for row in rows
    ]
    return items, total


def get_receipt(db: Session, receipt_id: int) -> Dict[str, Any]:
    return _receipt_view(db, _require_receipt(db, receipt_id))


def confirm_receipt(
    db: Session, receipt_id: int, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    """确认到货（原子，单事务）：

    1. 校验到货数量不超过订单行未到货数量；
    2. 逐行调用 `inventory.contract.increase_stock`（`PURCHASE_RECEIPT` 流水 + 结存）；
    3. 回写订单行已到货数量 → 单据 COMPLETED → 订单 IN_PROGRESS / COMPLETED。
    """
    receipt = _require_receipt(db, receipt_id)
    if receipt.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"到货单当前状态为 {receipt.status}，不能确认"
        )
    order = _require_order(db, receipt.purchase_order_id)
    if order.status not in _RECEIVABLE_ORDER_STATUSES:
        raise BusinessException(
            CODE_STATUS_INVALID, f"采购订单当前状态为 {order.status}，不能确认到货"
        )
    items = repository.get_receipt_items(db, receipt.id)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "到货单没有明细，不能确认")
    for item in items:
        order_item = repository.get_order_item(db, item.order_item_id)
        if not order_item:
            raise BusinessException(CODE_PARAM_INVALID, f"订单行不存在：{item.order_item_id}")
        qty = _as_decimal(item.quantity)
        remaining = _as_decimal(order_item.quantity) - _as_decimal(order_item.received_qty)
        if qty > remaining:
            raise BusinessException(
                CODE_RECEIPT_QTY_EXCEED,
                f"到货数量超过未到货数量：物料 {item.material_id} 未到货 {remaining}，本次 {qty}",
            )
        # 库存契约写 PURCHASE_RECEIPT 流水 + 加结存；本层不吞异常，整单事务回滚
        increase_stock(
            db,
            material_id=item.material_id,
            quantity=_as_decimal(item.qualified_qty),
            warehouse_id=receipt.warehouse_id,
            location_id=item.location_id,
            source_module=MODULE,
            source_type="PURCHASE_RECEIPT",
            source_reference_id=receipt.id,
            source_no=receipt.receipt_no,
            unit_cost=_as_decimal(order_item.unit_price),
            biz_date=receipt.receipt_date,
            operator_id=operator_id,
            remark=f"采购到货 {receipt.receipt_no}",
        )
        order_item.received_qty = _as_decimal(order_item.received_qty) + qty
    receipt.status = "COMPLETED"
    receipt.updated_by = operator_id
    order_items = repository.get_order_items(db, order.id)
    if all(
        _as_decimal(it.received_qty) >= _as_decimal(it.quantity) for it in order_items
    ):
        order.status = "COMPLETED"
    else:
        order.status = "IN_PROGRESS"
    order.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="pur_receipt",
        target_id=receipt.id,
        operator_id=operator_id,
        detail=f"确认到货单 {receipt.receipt_no}，订单 {order.order_no} → {order.status}",
    )
    return _receipt_view(db, receipt)


def cancel_receipt(
    db: Session, receipt_id: int, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    receipt = _require_receipt(db, receipt_id)
    if receipt.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"到货单当前状态为 {receipt.status}，不能取消"
        )
    receipt.status = "CANCELLED"
    receipt.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="pur_receipt",
        target_id=receipt.id,
        operator_id=operator_id,
        detail=f"取消到货单 {receipt.receipt_no}",
    )
    return _receipt_view(db, receipt)


# ==================== 供应商评价 ====================


def _validate_score(value: Decimal, label: str) -> Decimal:
    score = _as_decimal(value)
    if score < 0 or score > 100:
        raise BusinessException(CODE_PARAM_INVALID, f"{label}必须在 0~100 之间")
    return score.quantize(_SCORE_STEP, rounding=ROUND_HALF_UP)


def create_evaluation(
    db: Session,
    *,
    supplier_id: int,
    quality_score: Decimal,
    delivery_score: Decimal,
    price_score: Decimal,
    evaluate_date: Optional[date] = None,
    evaluator_id: Optional[int] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """新增供应商评价。

    综合评分公式：`total_score = (quality_score + delivery_score + price_score) / 3`，
    结果四舍五入保留 4 位小数（ROUND_HALF_UP）。
    """
    _require_supplier(db, supplier_id)
    if evaluator_id:
        _require_personnel(db, evaluator_id)
    quality = _validate_score(quality_score, "质量评分")
    delivery = _validate_score(delivery_score, "交期评分")
    price = _validate_score(price_score, "价格评分")
    total = ((quality + delivery + price) / 3).quantize(
        _SCORE_STEP, rounding=ROUND_HALF_UP
    )
    evaluation = models.PurSupplierEvaluation(
        supplier_id=supplier_id,
        evaluate_date=evaluate_date or date.today(),
        quality_score=quality,
        delivery_score=delivery,
        price_score=price,
        total_score=total,
        evaluator_id=evaluator_id,
        remark=remark,
        created_by=operator_id,
    )
    repository.add_evaluation(db, evaluation)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pur_supplier_evaluation",
        target_id=evaluation.id,
        operator_id=operator_id,
        detail=f"新增供应商评价 供应商{supplier_id}，综合 {total}",
    )
    supplier = repository.get_supplier(db, supplier_id)
    return _evaluation_dict(
        evaluation,
        supplier.supplier_name if supplier else None,
        get_personnel_name(db, evaluator_id),
    )


def list_evaluations(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    supplier_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_evaluations(db, page, page_size, supplier_id)
    suppliers = _supplier_name_map(db, [r.supplier_id for r in rows])
    items = [
        _evaluation_dict(
            row,
            suppliers.get(row.supplier_id),
            get_personnel_name(db, row.evaluator_id),
        )
        for row in rows
    ]
    return items, total


def list_evaluations_by_supplier(
    db: Session, supplier_id: int
) -> List[Dict[str, Any]]:
    _require_supplier(db, supplier_id)
    rows = repository.get_evaluations_by_supplier(db, supplier_id)
    supplier = repository.get_supplier(db, supplier_id)
    return [
        _evaluation_dict(
            row,
            supplier.supplier_name if supplier else None,
            get_personnel_name(db, row.evaluator_id),
        )
        for row in rows
    ]


def delete_evaluation(
    db: Session, evaluation_id: int, operator_id: Optional[int] = None
) -> None:
    evaluation = _require_evaluation(db, evaluation_id)
    repository.delete_evaluation(db, evaluation)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="pur_supplier_evaluation",
        target_id=evaluation_id,
        operator_id=operator_id,
        detail=f"删除供应商评价 {evaluation_id}",
    )


# ==================== 报表 / 统计 ====================


def plan_report(db: Session) -> List[Dict[str, Any]]:
    """采购计划及其执行：行级 required_qty vs ordered_qty。"""
    rows = repository.plan_report_rows(db)
    materials = _material_map(db, [row[4] for row in rows])
    report = []
    for (
        plan_id,
        plan_no,
        plan_date,
        status,
        material_id,
        required_qty,
        ordered_qty,
        required_date,
        source_type,
    ) in rows:
        required = _as_decimal(required_qty)
        ordered = _as_decimal(ordered_qty)
        report.append(
            {
                "plan_id": plan_id,
                "plan_no": plan_no,
                "plan_date": plan_date,
                "status": status,
                "material_id": material_id,
                **_material_fields(materials.get(material_id)),
                "required_qty": required,
                "ordered_qty": ordered,
                "remaining_qty": required - ordered,
                "required_date": required_date,
                "source_type": source_type,
            }
        )
    return report


def order_report(db: Session) -> List[Dict[str, Any]]:
    """采购订单及到货进度：行级。"""
    rows = repository.order_report_rows(db)
    materials = _material_map(db, [row[6] for row in rows])
    suppliers = _supplier_name_map(db, [row[2] for row in rows])
    report = []
    for (
        order_id,
        order_no,
        supplier_id,
        order_date,
        expected_date,
        status,
        material_id,
        quantity,
        received_qty,
        unit_price,
        amount,
    ) in rows:
        qty = _as_decimal(quantity)
        received = _as_decimal(received_qty)
        rate = (
            (received / qty).quantize(_SCORE_STEP, rounding=ROUND_HALF_UP)
            if qty > 0
            else Decimal("0")
        )
        report.append(
            {
                "order_id": order_id,
                "order_no": order_no,
                "supplier_id": supplier_id,
                "supplier_name": suppliers.get(supplier_id),
                "order_date": order_date,
                "expected_date": expected_date,
                "status": status,
                "material_id": material_id,
                **_material_fields(materials.get(material_id)),
                "quantity": qty,
                "received_qty": received,
                "remaining_qty": qty - received,
                "receipt_rate": rate,
                "unit_price": _as_decimal(unit_price),
                "amount": _as_decimal(amount),
            }
        )
    return report


def receipt_report(
    db: Session, date_from: date, date_to: date
) -> List[Dict[str, Any]]:
    """到货记录（行级），按到货日期区间。"""
    if date_from > date_to:
        raise BusinessException(CODE_PARAM_INVALID, "开始日期不能晚于结束日期")
    rows = repository.receipt_report_rows(db, date_from, date_to)
    materials = _material_map(db, [row[6] for row in rows])
    suppliers = _supplier_name_map(db, [row[5] for row in rows])
    report = []
    for (
        _rid,
        receipt_no,
        receipt_date,
        status,
        order_no,
        supplier_id,
        material_id,
        warehouse_id,
        location_id,
        quantity,
        qualified_qty,
    ) in rows:
        report.append(
            {
                "receipt_no": receipt_no,
                "receipt_date": receipt_date,
                "status": status,
                "order_no": order_no,
                "supplier_id": supplier_id,
                "supplier_name": suppliers.get(supplier_id),
                "material_id": material_id,
                **_material_fields(materials.get(material_id)),
                "warehouse_id": warehouse_id,
                "location_id": location_id,
                "quantity": _as_decimal(quantity),
                "qualified_qty": _as_decimal(qualified_qty),
            }
        )
    return report


def pending_receipt_report(db: Session) -> List[Dict[str, Any]]:
    """未到货报表：`received_qty < quantity` 的采购订单行。"""
    rows = repository.pending_receipt_rows(db)
    materials = _material_map(db, [row[6] for row in rows])
    suppliers = _supplier_name_map(db, [row[2] for row in rows])
    report = []
    for (
        order_id,
        order_no,
        supplier_id,
        expected_date,
        status,
        order_item_id,
        material_id,
        quantity,
        received_qty,
    ) in rows:
        qty = _as_decimal(quantity)
        received = _as_decimal(received_qty)
        report.append(
            {
                "order_id": order_id,
                "order_no": order_no,
                "supplier_id": supplier_id,
                "supplier_name": suppliers.get(supplier_id),
                "expected_date": expected_date,
                "status": status,
                "order_item_id": order_item_id,
                "material_id": material_id,
                **_material_fields(materials.get(material_id)),
                "quantity": qty,
                "received_qty": received,
                "remaining_qty": qty - received,
            }
        )
    return report


def supplier_evaluation_report(db: Session) -> List[Dict[str, Any]]:
    """供应商评分汇总：评价次数与平均质量 / 交期 / 价格 / 综合分。"""
    rows = repository.evaluation_summary_rows(db)
    suppliers = _supplier_name_map(db, [row[0] for row in rows])
    report = []
    for (
        supplier_id,
        evaluation_count,
        avg_total,
        avg_quality,
        avg_delivery,
        avg_price,
    ) in rows:
        report.append(
            {
                "supplier_id": supplier_id,
                "supplier_name": suppliers.get(supplier_id),
                "evaluation_count": int(evaluation_count),
                "avg_total_score": _as_decimal(avg_total).quantize(
                    _SCORE_STEP, rounding=ROUND_HALF_UP
                ),
                "avg_quality_score": _as_decimal(avg_quality).quantize(
                    _SCORE_STEP, rounding=ROUND_HALF_UP
                ),
                "avg_delivery_score": _as_decimal(avg_delivery).quantize(
                    _SCORE_STEP, rounding=ROUND_HALF_UP
                ),
                "avg_price_score": _as_decimal(avg_price).quantize(
                    _SCORE_STEP, rounding=ROUND_HALF_UP
                ),
            }
        )
    return report


def stats(db: Session) -> Dict[str, Any]:
    """采购模块统计（供 dashboard 使用）。"""
    return {
        "supplier_count": repository.count_all(db, models.PurSupplier),
        "supplier_material_count": repository.count_all(db, models.PurSupplierMaterial),
        "plan_count": repository.count_all(db, models.PurPurchasePlan),
        "plan_counts": repository.status_counts(db, models.PurPurchasePlan),
        "order_count": repository.count_all(db, models.PurOrder),
        "order_counts": repository.status_counts(db, models.PurOrder),
        "pending_receipt_line_count": repository.pending_receipt_line_count(db),
        "receipt_count": repository.count_all(db, models.PurReceipt),
        "evaluation_count": repository.count_all(db, models.PurSupplierEvaluation),
    }


# ==================== 跨模块契约核心逻辑（不提交事务） ====================


def create_purchase_plan_from_mrp(
    db: Session, mrp_result_ids: Sequence[int]
) -> Dict[str, Any]:
    """从 Planning 的 MRP `BUY` 结果生成采购计划（头 + 行）。

    - 行 `source_type="MRP"`、`source_reference_id=mrp_result.id`，
      数量取 `order_qty`、需求日期取 `requirement_date`；
    - **幂等**：同一 `source_reference_id` 已存在且计划未终结时复用该计划并只补新增行，
      已终结计划则新建计划（保证历史可追溯）；
    - **不提交事务**，由调用方提交。
    """
    from app.modules.planning.contract import get_mrp_results  # 惰性 import（契约）

    ids = [int(i) for i in mrp_result_ids if i]
    if not ids:
        raise BusinessException(CODE_PARAM_INVALID, "MRP 结果ID不能为空")
    results = get_mrp_results(db, ids)
    buy_results = [row for row in results if row.get("supply_type") == SupplyType.BUY.value]
    if not buy_results:
        raise BusinessException(CODE_PARAM_INVALID, "未找到 BUY 类型的 MRP 结果")

    reference_ids = [int(row["id"]) for row in buy_results]
    plan = _resolve_reusable_plan(db, "MRP", reference_ids)
    if plan is None:
        plan = _create_plan_header(
            db,
            plan_date=date.today(),
            remark=f"由 MRP BUY 结果生成（{len(buy_results)} 条）",
        )
    existing = {
        item.source_reference_id
        for item in repository.get_plan_items(db, plan.id)
        if item.source_type == "MRP"
    }
    for row in buy_results:
        reference_id = int(row["id"])
        if reference_id in existing:
            continue
        _add_plan_item(
            db,
            plan.id,
            {
                "material_id": row["material_id"],
                "required_qty": _as_decimal(row.get("order_qty")),
                "required_date": row.get("requirement_date") or date.today(),
                "source_type": "MRP",
                "source_reference_id": reference_id,
                "remark": f"MRP 结果 {reference_id}",
            },
        )
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pur_purchase_plan",
        target_id=plan.id,
        detail=f"按 MRP BUY 结果生成采购计划 {plan.plan_no}",
    )
    return {"plan_id": plan.id, "plan_no": plan.plan_no}


def create_purchase_plan_from_replenishment(
    db: Session, request_id: int
) -> Dict[str, Any]:
    """受理 Inventory 的订货点补库需求：生成采购计划（行 `source_type="REORDER"`）。

    - 需求明细通过 `inventory.contract.get_replenishment_request(db, request_id)` 读取
      （**函数内惰性 import**，契约尚未就绪时抛 4007）；
    - **幂等**：同一 `request_id` 已受理且计划未终结时复用该计划，不重复建单；
    - **不提交事务**，由调用方提交。
    """
    try:
        from app.modules.inventory import contract as inventory_contract  # 惰性 import

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
    _require_material(db, material_id)
    request_no = _field("request_no")
    required_date = _field("required_date") or date.today()
    request_qty = _as_decimal(_field("request_qty"))

    plan = _resolve_reusable_plan(db, "REORDER", [request_id])
    if plan is None:
        plan = _create_plan_header(
            db,
            plan_date=date.today(),
            remark=f"受理库存补库需求 {request_no}",
        )
    existing = {
        item.source_reference_id
        for item in repository.get_plan_items(db, plan.id)
        if item.source_type == "REORDER"
    }
    if request_id not in existing:
        _add_plan_item(
            db,
            plan.id,
            {
                "material_id": material_id,
                "required_qty": request_qty,
                "required_date": required_date,
                "source_type": "REORDER",
                "source_reference_id": request_id,
                "remark": f"补库需求 {request_no}",
            },
        )
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="pur_purchase_plan",
        target_id=plan.id,
        detail=f"受理库存补库需求 {request_no}，生成采购计划 {plan.plan_no}",
    )
    return {"plan_id": plan.id, "plan_no": plan.plan_no}


def get_pending_receipt_qty(db: Session, material_id: int) -> Decimal:
    """该物料所有在途未到货采购订单行的剩余数量合计（供 Planning / 库存预警参考）。"""
    return repository.pending_receipt_qty(db, material_id)