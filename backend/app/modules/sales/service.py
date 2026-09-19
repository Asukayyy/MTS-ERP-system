"""sales 模块业务逻辑层。

硬性约定（规格 §7 / §24 / §35 / §42）：

1. **不直接改库存**：发货 / 退货确认必须调用 `inventory.contract` 的
   `decrease_stock` / `increase_stock`，由库存引擎写流水 + 结存；
   库存不足时由库存契约抛 5001，本层**不吞异常**，整单事务回滚。
2. **不写计划表**：销售只提供需求来源（订单 / 预测），由 Planning 通过契约读取。
3. **只有一个物料主数据 / 人员表**：物料、销售员分别经 `system.contract`
   的 `get_material` / `get_personnel_name` 读取，不另建销售产品表 / 销售员表。
4. 本层**不调用 `db.commit()`**：由 router 提交；`contract.py` 函数运行在调用方事务里。
5. 每个状态变更在同一事务内写操作日志（`system.contract.log_operation`）。

错误码区段：`2000~2999`。
"""

import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.inventory.contract import decrease_stock, increase_stock
from app.modules.sales import models, repository
from app.modules.system.contract import (
    get_finished_materials,
    get_material,
    get_materials,
    get_personnel_name,
    log_operation,
)
from app.shared.enums import MaterialType, RecordStatus

# ==================== 错误码（2000~2999） ====================

CODE_PARAM_INVALID = 2000  # 入参 / 状态非法
CODE_DUPLICATE = 2001  # 唯一性冲突（如客户编码重复）
CODE_IMMUTABLE = 2002  # 已完结 / 已取消单据不可修改
CODE_SHIP_QTY_EXCEED = 2003  # 发货数量超过未发数量
CODE_RETURN_MISMATCH = 2004  # 退货单与原订单客户不一致
CODE_NOT_FOUND = 2005  # 资源不存在
CODE_STATUS_INVALID = 2006  # 单据状态不允许该操作

MODULE = "sales"

_ORDER_STATUSES = {"DRAFT", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
_ORDER_TERMINAL = {"COMPLETED", "CANCELLED"}
# 销售订单状态机：DRAFT → CONFIRMED → IN_PROGRESS → COMPLETED，另可从 DRAFT/CONFIRMED 取消
_ORDER_TRANSITIONS: Dict[str, set] = {
    "DRAFT": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}
_FORECAST_STATUSES = {"DRAFT", "CONFIRMED", "COMPLETED", "CANCELLED"}
_FORECAST_TERMINAL = {"COMPLETED", "CANCELLED"}
_CUSTOMER_STATUSES = {RecordStatus.ACTIVE.value, RecordStatus.INACTIVE.value}
_QUALITY_STATUSES = {"QUALIFIED", "DEFECTIVE", "SCRAP"}
_SHIPPABLE_ORDER_STATUSES = {"CONFIRMED", "IN_PROGRESS"}
_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CENT = Decimal("0.01")


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


def _is_finished_active(material: Dict[str, Any]) -> bool:
    """判定物料是否可销售的成品（FINISHED + ACTIVE）。"""
    return (
        material.get("material_type") == MaterialType.FINISHED.value
        and material.get("status") == RecordStatus.ACTIVE.value
    )


def _material_map(db: Session, material_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    return get_materials(db, [int(i) for i in material_ids if i])


def _require_customer(db: Session, customer_id: Optional[int]) -> models.SalCustomer:
    if not customer_id:
        raise BusinessException(CODE_PARAM_INVALID, "客户ID不能为空")
    customer = repository.get_customer(db, customer_id)
    if not customer:
        raise BusinessException(CODE_NOT_FOUND, f"客户不存在：{customer_id}")
    return customer


def _require_order(db: Session, order_id: int) -> models.SalOrder:
    order = repository.get_order(db, order_id)
    if not order:
        raise BusinessException(CODE_NOT_FOUND, f"销售订单不存在：{order_id}")
    return order


def _require_forecast(db: Session, forecast_id: int) -> models.SalForecast:
    forecast = repository.get_forecast(db, forecast_id)
    if not forecast:
        raise BusinessException(CODE_NOT_FOUND, f"销售预测不存在：{forecast_id}")
    return forecast


def _require_shipment(db: Session, shipment_id: int) -> models.SalShipment:
    shipment = repository.get_shipment(db, shipment_id)
    if not shipment:
        raise BusinessException(CODE_NOT_FOUND, f"发货单不存在：{shipment_id}")
    return shipment


def _require_return(db: Session, return_id: int) -> models.SalReturn:
    sales_return = repository.get_return(db, return_id)
    if not sales_return:
        raise BusinessException(CODE_NOT_FOUND, f"退货单不存在：{return_id}")
    return sales_return


def _require_material(db: Session, material_id: int) -> Dict[str, Any]:
    material = get_material(db, material_id)
    if not material:
        raise BusinessException(CODE_NOT_FOUND, f"物料不存在：{material_id}")
    return material


def _order_no(db: Session, order_no: Optional[str], on_date: date) -> str:
    if order_no:
        if repository.get_order_by_no(db, order_no):
            raise BusinessException(CODE_DUPLICATE, f"销售订单号已存在：{order_no}")
        return order_no
    return repository.next_no(
        db, models.SalOrder, models.SalOrder.order_no, f"SO{on_date:%Y%m%d}"
    )


def _shipment_no(db: Session, shipment_no: Optional[str], on_date: date) -> str:
    if shipment_no:
        if repository.get_shipment_by_no(db, shipment_no):
            raise BusinessException(CODE_DUPLICATE, f"发货单号已存在：{shipment_no}")
        return shipment_no
    return repository.next_no(
        db, models.SalShipment, models.SalShipment.shipment_no, f"SH{on_date:%Y%m%d}"
    )


def _return_no(db: Session, return_no: Optional[str], on_date: date) -> str:
    if return_no:
        if repository.get_return_by_no(db, return_no):
            raise BusinessException(CODE_DUPLICATE, f"退货单号已存在：{return_no}")
        return return_no
    return repository.next_no(
        db, models.SalReturn, models.SalReturn.return_no, f"RT{on_date:%Y%m%d}"
    )


# ==================== 出参拼装 ====================


def _customer_dict(row: models.SalCustomer) -> Dict[str, Any]:
    return {
        "id": row.id,
        "customer_code": row.customer_code,
        "customer_name": row.customer_name,
        "contact_person": row.contact_person,
        "phone": row.phone,
        "email": row.email,
        "address": row.address,
        "credit_limit": _as_decimal(row.credit_limit),
        "status": row.status,
        "remark": row.remark,
    }


def _material_fields(material: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    material = material or {}
    return {
        "material_code": material.get("material_code"),
        "material_name": material.get("material_name"),
    }


def _forecast_dict(
    row: models.SalForecast,
    materials: Dict[int, Dict[str, Any]],
    customer_name: Optional[str],
) -> Dict[str, Any]:
    return {
        "id": row.id,
        "forecast_no": row.forecast_no,
        "customer_id": row.customer_id,
        "customer_name": customer_name,
        "material_id": row.material_id,
        **_material_fields(materials.get(row.material_id)),
        "forecast_month": row.forecast_month,
        "forecast_qty": _as_decimal(row.forecast_qty),
        "status": row.status,
        "remark": row.remark,
    }


def _order_items_dict(
    db: Session, order_id: int, materials: Dict[int, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    items = []
    for item in repository.get_order_items(db, order_id):
        items.append(
            {
                "id": item.id,
                "order_id": item.order_id,
                "line_no": item.line_no,
                "material_id": item.material_id,
                **_material_fields(materials.get(item.material_id)),
                "quantity": _as_decimal(item.quantity),
                "delivered_qty": _as_decimal(item.delivered_qty),
                "unit_price": _as_decimal(item.unit_price),
                "amount": _as_decimal(item.amount),
                "remark": item.remark,
            }
        )
    return items


def _order_dict(
    db: Session,
    order: models.SalOrder,
    materials: Dict[int, Dict[str, Any]],
    customer_name: Optional[str],
    salesperson_name: Optional[str],
) -> Dict[str, Any]:
    return {
        "id": order.id,
        "order_no": order.order_no,
        "customer_id": order.customer_id,
        "customer_name": customer_name,
        "order_date": order.order_date,
        "delivery_date": order.delivery_date,
        "salesperson_id": order.salesperson_id,
        "salesperson_name": salesperson_name,
        "total_amount": _as_decimal(order.total_amount),
        "status": order.status,
        "remark": order.remark,
        "items": _order_items_dict(db, order.id, materials),
    }


def _shipment_dict(
    db: Session,
    shipment: models.SalShipment,
    materials: Dict[int, Dict[str, Any]],
    customer_name: Optional[str],
    order_no: Optional[str],
) -> Dict[str, Any]:
    items = []
    for item in repository.get_shipment_items(db, shipment.id):
        items.append(
            {
                "id": item.id,
                "shipment_id": item.shipment_id,
                "order_item_id": item.order_item_id,
                "material_id": item.material_id,
                **_material_fields(materials.get(item.material_id)),
                "warehouse_id": item.warehouse_id,
                "location_id": item.location_id,
                "quantity": _as_decimal(item.quantity),
                "remark": item.remark,
            }
        )
    return {
        "id": shipment.id,
        "shipment_no": shipment.shipment_no,
        "order_id": shipment.order_id,
        "order_no": order_no,
        "customer_id": shipment.customer_id,
        "customer_name": customer_name,
        "shipment_date": shipment.shipment_date,
        "status": shipment.status,
        "remark": shipment.remark,
        "items": items,
    }


def _return_dict(
    db: Session,
    sales_return: models.SalReturn,
    materials: Dict[int, Dict[str, Any]],
    customer_name: Optional[str],
    order_no: Optional[str],
) -> Dict[str, Any]:
    items = []
    for item in repository.get_return_items(db, sales_return.id):
        items.append(
            {
                "id": item.id,
                "return_id": item.return_id,
                "material_id": item.material_id,
                **_material_fields(materials.get(item.material_id)),
                "warehouse_id": item.warehouse_id,
                "location_id": item.location_id,
                "quantity": _as_decimal(item.quantity),
                "quality_status": item.quality_status,
                "reason": item.reason,
                "remark": item.remark,
            }
        )
    return {
        "id": sales_return.id,
        "return_no": sales_return.return_no,
        "order_id": sales_return.order_id,
        "order_no": order_no,
        "customer_id": sales_return.customer_id,
        "customer_name": customer_name,
        "return_date": sales_return.return_date,
        "reason": sales_return.reason,
        "status": sales_return.status,
        "remark": sales_return.remark,
        "items": items,
    }


# ==================== 客户 ====================


def list_customers(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_customers(db, page, page_size, keyword, status)
    return [_customer_dict(row) for row in rows], total


def get_customer(db: Session, customer_id: int) -> Dict[str, Any]:
    return _customer_dict(_require_customer(db, customer_id))


def create_customer(
    db: Session,
    *,
    customer_code: str,
    customer_name: str,
    contact_person: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    address: Optional[str] = None,
    credit_limit: Decimal = Decimal("0"),
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    if repository.get_customer_by_code(db, customer_code):
        raise BusinessException(CODE_DUPLICATE, f"客户编码已存在：{customer_code}")
    customer = models.SalCustomer(
        customer_code=customer_code,
        customer_name=customer_name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        address=address,
        credit_limit=_as_decimal(credit_limit),
        status=RecordStatus.ACTIVE.value,
        remark=remark,
        created_by=operator_id,
    )
    repository.add_customer(db, customer)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="sal_customer",
        target_id=customer.id,
        operator_id=operator_id,
        detail=f"新增客户 {customer_code}",
    )
    return _customer_dict(customer)


def update_customer(
    db: Session,
    customer_id: int,
    *,
    customer_name: Optional[str] = None,
    contact_person: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    address: Optional[str] = None,
    credit_limit: Optional[Decimal] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    customer = _require_customer(db, customer_id)
    if customer_name is not None:
        customer.customer_name = customer_name
    if contact_person is not None:
        customer.contact_person = contact_person
    if phone is not None:
        customer.phone = phone
    if email is not None:
        customer.email = email
    if address is not None:
        customer.address = address
    if credit_limit is not None:
        customer.credit_limit = _as_decimal(credit_limit)
    if remark is not None:
        customer.remark = remark
    customer.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="sal_customer",
        target_id=customer.id,
        operator_id=operator_id,
        detail=f"修改客户 {customer.customer_code}",
    )
    return _customer_dict(customer)


def set_customer_status(
    db: Session, customer_id: int, status: str, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    if status not in _CUSTOMER_STATUSES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法状态：{status}（客户不物理删除，仅停用）")
    customer = _require_customer(db, customer_id)
    customer.status = status
    customer.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="sal_customer",
        target_id=customer.id,
        operator_id=operator_id,
        detail=f"客户 {customer.customer_code} 状态改为 {status}",
    )
    return _customer_dict(customer)


# ==================== 销售产品查询（只读物料主数据） ====================


def list_products(db: Session, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    """可销售成品：直接读取 `system.contract`，不建销售产品表。"""
    return get_finished_materials(db, keyword)


# ==================== 销售预测 ====================


def list_forecasts(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    forecast_month: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_forecasts(
        db, page, page_size, material_id, status, forecast_month
    )
    materials = _material_map(db, [r.material_id for r in rows])
    customers = {
        c.id: c.customer_name
        for c in repository.get_customers(db, [r.customer_id for r in rows]).values()
    }
    items = [_forecast_dict(row, materials, customers.get(row.customer_id)) for row in rows]
    return items, total


def get_forecast(db: Session, forecast_id: int) -> Dict[str, Any]:
    forecast = _require_forecast(db, forecast_id)
    materials = _material_map(db, [forecast.material_id])
    customer_name = (
        repository.get_customer(db, forecast.customer_id).customer_name
        if forecast.customer_id and repository.get_customer(db, forecast.customer_id)
        else None
    )
    return _forecast_dict(forecast, materials, customer_name)


def create_forecast(
    db: Session,
    *,
    material_id: int,
    forecast_month: str,
    forecast_qty: Decimal,
    customer_id: Optional[int] = None,
    forecast_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    if not _MONTH_PATTERN.match(forecast_month or ""):
        raise BusinessException(CODE_PARAM_INVALID, "预测月份格式应为 YYYY-MM")
    qty = _as_decimal(forecast_qty)
    if qty <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "预测数量必须为正数")
    _require_material(db, material_id)
    if customer_id is not None:
        _require_customer(db, customer_id)
    if forecast_no:
        if repository.get_forecast_by_no(db, forecast_no):
            raise BusinessException(CODE_DUPLICATE, f"预测单号已存在：{forecast_no}")
    else:
        forecast_no = repository.next_no(
            db, models.SalForecast, models.SalForecast.forecast_no, f"FC{date.today():%Y%m%d}"
        )
    forecast = models.SalForecast(
        forecast_no=forecast_no,
        customer_id=customer_id,
        material_id=material_id,
        forecast_month=forecast_month,
        forecast_qty=qty,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_forecast(db, forecast)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="sal_forecast",
        target_id=forecast.id,
        operator_id=operator_id,
        detail=f"新增销售预测 {forecast_no}",
    )
    return get_forecast(db, forecast.id)


def update_forecast(
    db: Session,
    forecast_id: int,
    *,
    material_id: Optional[int] = None,
    forecast_month: Optional[str] = None,
    forecast_qty: Optional[Decimal] = None,
    customer_id: Optional[int] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    forecast = _require_forecast(db, forecast_id)
    if forecast.status in _FORECAST_TERMINAL:
        raise BusinessException(CODE_IMMUTABLE, f"预测单已 {forecast.status}，不可修改")
    if material_id is not None:
        _require_material(db, material_id)
        forecast.material_id = material_id
    if forecast_month is not None:
        if not _MONTH_PATTERN.match(forecast_month):
            raise BusinessException(CODE_PARAM_INVALID, "预测月份格式应为 YYYY-MM")
        forecast.forecast_month = forecast_month
    if forecast_qty is not None:
        qty = _as_decimal(forecast_qty)
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "预测数量必须为正数")
        forecast.forecast_qty = qty
    if customer_id is not None:
        _require_customer(db, customer_id)
        forecast.customer_id = customer_id
    if remark is not None:
        forecast.remark = remark
    forecast.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="sal_forecast",
        target_id=forecast.id,
        operator_id=operator_id,
        detail=f"修改销售预测 {forecast.forecast_no}",
    )
    return get_forecast(db, forecast.id)


def set_forecast_status(
    db: Session, forecast_id: int, status: str, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    if status not in _FORECAST_STATUSES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法预测状态：{status}")
    forecast = _require_forecast(db, forecast_id)
    if forecast.status in _FORECAST_TERMINAL:
        raise BusinessException(CODE_IMMUTABLE, f"预测单已 {forecast.status}，不可再流转")
    forecast.status = status
    forecast.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="sal_forecast",
        target_id=forecast.id,
        operator_id=operator_id,
        detail=f"销售预测 {forecast.forecast_no} 状态改为 {status}",
    )
    return get_forecast(db, forecast.id)


def delete_forecast(
    db: Session, forecast_id: int, operator_id: Optional[int] = None
) -> None:
    forecast = _require_forecast(db, forecast_id)
    if forecast.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, "仅 DRAFT 状态的预测单可删除")
    no = forecast.forecast_no
    repository.delete_forecast(db, forecast)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="sal_forecast",
        target_id=forecast_id,
        operator_id=operator_id,
        detail=f"删除销售预测 {no}",
    )


# ==================== 销售订单 ====================


def _build_order_items(
    db: Session, order_id: int, raw_items: Sequence[Dict[str, Any]]
) -> Decimal:
    """按入参写入订单行，返回订单总金额。仅校验物料存在与数量为正。"""
    total = Decimal("0")
    for index, raw in enumerate(raw_items, start=1):
        material_id = raw.get("material_id")
        _require_material(db, material_id)
        qty = _as_decimal(raw.get("quantity"))
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "订单数量必须为正数")
        unit_price = _as_decimal(raw.get("unit_price"))
        if unit_price < 0:
            raise BusinessException(CODE_PARAM_INVALID, "单价不能为负数")
        amount = _money(qty * unit_price)
        total += amount
        repository.add_order_item(
            db,
            models.SalOrderItem(
                order_id=order_id,
                line_no=index,
                material_id=material_id,
                quantity=qty,
                delivered_qty=Decimal("0"),
                unit_price=unit_price,
                amount=amount,
                remark=raw.get("remark"),
            ),
        )
    return _money(total)


def _order_view(db: Session, order: models.SalOrder) -> Dict[str, Any]:
    materials = _material_map(
        db, [item.material_id for item in repository.get_order_items(db, order.id)]
    )
    customer = repository.get_customer(db, order.customer_id)
    return _order_dict(
        db,
        order,
        materials,
        customer.customer_name if customer else None,
        get_personnel_name(db, order.salesperson_id),
    )


def list_orders(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    keyword: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_orders(
        db, page, page_size, customer_id, status, date_from, date_to, keyword
    )
    customers = {
        c.id: c.customer_name
        for c in repository.get_customers(db, [r.customer_id for r in rows]).values()
    }
    material_ids = [
        item.material_id
        for row in rows
        for item in repository.get_order_items(db, row.id)
    ]
    materials = _material_map(db, material_ids)
    items = [
        _order_dict(
            db,
            row,
            materials,
            customers.get(row.customer_id),
            get_personnel_name(db, row.salesperson_id),
        )
        for row in rows
    ]
    return items, total


def get_order(db: Session, order_id: int) -> Dict[str, Any]:
    return _order_view(db, _require_order(db, order_id))


def create_order(
    db: Session,
    *,
    customer_id: int,
    order_date: date,
    delivery_date: date,
    items: Sequence[Dict[str, Any]],
    salesperson_id: Optional[int] = None,
    order_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    _require_customer(db, customer_id)
    number = _order_no(db, order_no, order_date)
    order = models.SalOrder(
        order_no=number,
        customer_id=customer_id,
        order_date=order_date,
        delivery_date=delivery_date,
        salesperson_id=salesperson_id,
        total_amount=Decimal("0"),
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_order(db, order)
    total = _build_order_items(db, order.id, items)
    order.total_amount = total
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="sal_order",
        target_id=order.id,
        operator_id=operator_id,
        detail=f"新增销售订单 {number}，金额 {total}",
    )
    return _order_view(db, order)


def update_order(
    db: Session,
    order_id: int,
    *,
    customer_id: Optional[int] = None,
    order_date: Optional[date] = None,
    delivery_date: Optional[date] = None,
    salesperson_id: Optional[int] = None,
    items: Optional[Sequence[Dict[str, Any]]] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    order = _require_order(db, order_id)
    if order.status in _ORDER_TERMINAL:
        raise BusinessException(CODE_IMMUTABLE, f"订单已 {order.status}，不可修改")
    if order.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, "仅 DRAFT 状态的订单可修改")
    if customer_id is not None:
        _require_customer(db, customer_id)
        order.customer_id = customer_id
    if order_date is not None:
        order.order_date = order_date
    if delivery_date is not None:
        order.delivery_date = delivery_date
    if salesperson_id is not None:
        order.salesperson_id = salesperson_id
    if remark is not None:
        order.remark = remark
    if items is not None:
        repository.delete_order_items(db, order.id)
        db.flush()
        order.total_amount = _build_order_items(db, order.id, items)
    order.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="sal_order",
        target_id=order.id,
        operator_id=operator_id,
        detail=f"修改销售订单 {order.order_no}",
    )
    return _order_view(db, order)


def delete_order(db: Session, order_id: int, operator_id: Optional[int] = None) -> None:
    order = _require_order(db, order_id)
    if order.status in _ORDER_TERMINAL:
        raise BusinessException(CODE_IMMUTABLE, f"订单已 {order.status}，不可删除")
    if order.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, "仅 DRAFT 状态的订单可删除")
    no = order.order_no
    repository.delete_order(db, order)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="sal_order",
        target_id=order_id,
        operator_id=operator_id,
        detail=f"删除销售订单 {no}",
    )


def _validate_order_confirm(db: Session, order: models.SalOrder) -> None:
    """确认订单前的业务校验：≥1 行、客户启用、每行物料为启用成品且数量为正。"""
    items = repository.get_order_items(db, order.id)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "订单没有明细，不能确认")
    customer = repository.get_customer(db, order.customer_id)
    if not customer:
        raise BusinessException(CODE_PARAM_INVALID, f"客户不存在：{order.customer_id}")
    if customer.status != RecordStatus.ACTIVE.value:
        raise BusinessException(CODE_PARAM_INVALID, "客户已停用，不能确认订单")
    for item in items:
        material = get_material(db, item.material_id)
        if not material:
            raise BusinessException(CODE_PARAM_INVALID, f"订单行物料不存在：{item.material_id}")
        if not _is_finished_active(material):
            raise BusinessException(
                CODE_PARAM_INVALID,
                f"物料 {material.get('material_code')} 不是启用的成品，不能确认订单",
            )
        if _as_decimal(item.quantity) <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "订单行数量必须为正数")


def set_order_status(
    db: Session, order_id: int, status: str, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    if status not in _ORDER_STATUSES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法订单状态：{status}")
    order = _require_order(db, order_id)
    if order.status in _ORDER_TERMINAL:
        raise BusinessException(CODE_IMMUTABLE, f"订单已 {order.status}，不可再流转")
    if status not in _ORDER_TRANSITIONS.get(order.status, set()):
        raise BusinessException(
            CODE_STATUS_INVALID, f"订单状态不允许从 {order.status} 流转到 {status}"
        )
    if status == "CONFIRMED":
        _validate_order_confirm(db, order)
    order.status = status
    order.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="sal_order",
        target_id=order.id,
        operator_id=operator_id,
        detail=f"销售订单 {order.order_no} 状态改为 {status}",
    )
    return _order_view(db, order)


# ==================== 销售发货 ====================


def list_shipments(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    order_id: Optional[int] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_shipments(db, page, page_size, order_id, status)
    items = []
    for row in rows:
        materials = _material_map(
            db, [i.material_id for i in repository.get_shipment_items(db, row.id)]
        )
        customer = repository.get_customer(db, row.customer_id)
        order = repository.get_order(db, row.order_id)
        items.append(
            _shipment_dict(
                db,
                row,
                materials,
                customer.customer_name if customer else None,
                order.order_no if order else None,
            )
        )
    return items, total


def _shipment_view(db: Session, shipment: models.SalShipment) -> Dict[str, Any]:
    materials = _material_map(
        db, [i.material_id for i in repository.get_shipment_items(db, shipment.id)]
    )
    customer = repository.get_customer(db, shipment.customer_id)
    order = repository.get_order(db, shipment.order_id)
    return _shipment_dict(
        db,
        shipment,
        materials,
        customer.customer_name if customer else None,
        order.order_no if order else None,
    )


def get_shipment(db: Session, shipment_id: int) -> Dict[str, Any]:
    return _shipment_view(db, _require_shipment(db, shipment_id))


def create_shipment(
    db: Session,
    *,
    order_id: int,
    shipment_date: date,
    items: Sequence[Dict[str, Any]],
    shipment_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    order = _require_order(db, order_id)
    if order.status not in _SHIPPABLE_ORDER_STATUSES:
        raise BusinessException(
            CODE_STATUS_INVALID, f"订单当前状态为 {order.status}，不能发货"
        )
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "发货单至少需要一条明细")
    number = _shipment_no(db, shipment_no, shipment_date)
    shipment = models.SalShipment(
        shipment_no=number,
        order_id=order.id,
        customer_id=order.customer_id,
        shipment_date=shipment_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_shipment(db, shipment)
    for raw in items:
        order_item = repository.get_order_item(db, raw.get("order_item_id"))
        if not order_item or order_item.order_id != order.id:
            raise BusinessException(
                CODE_PARAM_INVALID, f"订单行不存在或不属于当前订单：{raw.get('order_item_id')}"
            )
        qty = _as_decimal(raw.get("quantity"))
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "发货数量必须为正数")
        remaining = _as_decimal(order_item.quantity) - _as_decimal(order_item.delivered_qty)
        if qty > remaining:
            raise BusinessException(
                CODE_SHIP_QTY_EXCEED,
                f"发货数量超过未发数量：物料 {order_item.material_id} 未发 {remaining}，本次 {qty}",
            )
        repository.add_shipment_item(
            db,
            models.SalShipmentItem(
                shipment_id=shipment.id,
                order_item_id=order_item.id,
                material_id=order_item.material_id,
                warehouse_id=raw.get("warehouse_id"),
                location_id=raw.get("location_id"),
                quantity=qty,
                remark=raw.get("remark"),
            ),
        )
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="sal_shipment",
        target_id=shipment.id,
        operator_id=operator_id,
        detail=f"新增发货单 {number}",
    )
    return _shipment_view(db, shipment)


def confirm_shipment(
    db: Session, shipment_id: int, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    """确认发货（原子）：调用库存出库 → 回写订单行已发数量 → 更新单据 / 订单状态。"""
    shipment = _require_shipment(db, shipment_id)
    if shipment.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"发货单当前状态为 {shipment.status}，不能确认"
        )
    order = _require_order(db, shipment.order_id)
    if order.status not in _SHIPPABLE_ORDER_STATUSES:
        raise BusinessException(
            CODE_STATUS_INVALID, f"订单当前状态为 {order.status}，不能发货"
        )
    items = repository.get_shipment_items(db, shipment.id)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "发货单没有明细，不能确认")
    for item in items:
        order_item = repository.get_order_item(db, item.order_item_id)
        if not order_item:
            raise BusinessException(CODE_PARAM_INVALID, f"订单行不存在：{item.order_item_id}")
        qty = _as_decimal(item.quantity)
        remaining = _as_decimal(order_item.quantity) - _as_decimal(order_item.delivered_qty)
        if qty > remaining:
            raise BusinessException(
                CODE_SHIP_QTY_EXCEED,
                f"发货数量超过未发数量：物料 {item.material_id} 未发 {remaining}，本次 {qty}",
            )
        # 库存不足时库存契约抛 5001，本层不吞，整单事务回滚
        decrease_stock(
            db,
            material_id=item.material_id,
            quantity=qty,
            warehouse_id=item.warehouse_id,
            location_id=item.location_id,
            source_module=MODULE,
            source_type="SALES_SHIPMENT",
            source_reference_id=shipment.id,
            source_no=shipment.shipment_no,
            biz_date=shipment.shipment_date,
            operator_id=operator_id,
            remark=f"销售发货 {shipment.shipment_no}",
        )
        order_item.delivered_qty = _as_decimal(order_item.delivered_qty) + qty

    shipment.status = "COMPLETED"
    shipment.updated_by = operator_id
    order_items = repository.get_order_items(db, order.id)
    if all(
        _as_decimal(it.delivered_qty) >= _as_decimal(it.quantity) for it in order_items
    ):
        order.status = "COMPLETED"
    else:
        order.status = "IN_PROGRESS"
    order.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="sal_shipment",
        target_id=shipment.id,
        operator_id=operator_id,
        detail=f"确认发货单 {shipment.shipment_no}，订单 {order.order_no} → {order.status}",
    )
    return _shipment_view(db, shipment)


def cancel_shipment(
    db: Session, shipment_id: int, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    shipment = _require_shipment(db, shipment_id)
    if shipment.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"发货单当前状态为 {shipment.status}，不能取消"
        )
    shipment.status = "CANCELLED"
    shipment.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="sal_shipment",
        target_id=shipment.id,
        operator_id=operator_id,
        detail=f"取消发货单 {shipment.shipment_no}",
    )
    return _shipment_view(db, shipment)


# ==================== 销售退货 ====================


def list_returns(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    order_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_returns(db, page, page_size, order_id, customer_id, status)
    items = []
    for row in rows:
        materials = _material_map(
            db, [i.material_id for i in repository.get_return_items(db, row.id)]
        )
        customer = repository.get_customer(db, row.customer_id)
        order = repository.get_order(db, row.order_id) if row.order_id else None
        items.append(
            _return_dict(
                db,
                row,
                materials,
                customer.customer_name if customer else None,
                order.order_no if order else None,
            )
        )
    return items, total


def _return_view(db: Session, sales_return: models.SalReturn) -> Dict[str, Any]:
    materials = _material_map(
        db, [i.material_id for i in repository.get_return_items(db, sales_return.id)]
    )
    customer = repository.get_customer(db, sales_return.customer_id)
    order = (
        repository.get_order(db, sales_return.order_id) if sales_return.order_id else None
    )
    return _return_dict(
        db,
        sales_return,
        materials,
        customer.customer_name if customer else None,
        order.order_no if order else None,
    )


def get_return(db: Session, return_id: int) -> Dict[str, Any]:
    return _return_view(db, _require_return(db, return_id))


def create_return(
    db: Session,
    *,
    customer_id: int,
    return_date: date,
    items: Sequence[Dict[str, Any]],
    order_id: Optional[int] = None,
    return_no: Optional[str] = None,
    reason: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    _require_customer(db, customer_id)
    if order_id is not None:
        order = _require_order(db, order_id)
        if order.customer_id != customer_id:
            raise BusinessException(
                CODE_RETURN_MISMATCH, "退货单客户与原销售订单客户不一致"
            )
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "退货单至少需要一条明细")
    number = _return_no(db, return_no, return_date)
    sales_return = models.SalReturn(
        return_no=number,
        order_id=order_id,
        customer_id=customer_id,
        return_date=return_date,
        reason=reason,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_return(db, sales_return)
    for raw in items:
        _require_material(db, raw.get("material_id"))
        qty = _as_decimal(raw.get("quantity"))
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "退货数量必须为正数")
        quality_status = raw.get("quality_status") or "QUALIFIED"
        if quality_status not in _QUALITY_STATUSES:
            raise BusinessException(CODE_PARAM_INVALID, f"非法质量状态：{quality_status}")
        repository.add_return_item(
            db,
            models.SalReturnItem(
                return_id=sales_return.id,
                material_id=raw.get("material_id"),
                warehouse_id=raw.get("warehouse_id"),
                location_id=raw.get("location_id"),
                quantity=qty,
                quality_status=quality_status,
                reason=raw.get("reason"),
                remark=raw.get("remark"),
            ),
        )
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="sal_return",
        target_id=sales_return.id,
        operator_id=operator_id,
        detail=f"新增退货单 {number}",
    )
    return _return_view(db, sales_return)


def confirm_return(
    db: Session, return_id: int, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    """确认退货（原子）：调用库存入库，状态置 COMPLETED。

    简化说明（规格 §42）：`quality_status` 为 SCRAP 的退货行**仍然入仓**，
    仅通过质量状态标签区分，系统不设独立隔离仓。
    """
    sales_return = _require_return(db, return_id)
    if sales_return.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"退货单当前状态为 {sales_return.status}，不能确认"
        )
    items = repository.get_return_items(db, sales_return.id)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "退货单没有明细，不能确认")
    for item in items:
        increase_stock(
            db,
            material_id=item.material_id,
            quantity=_as_decimal(item.quantity),
            warehouse_id=item.warehouse_id,
            location_id=item.location_id,
            source_module=MODULE,
            source_type="SALES_RETURN",
            source_reference_id=sales_return.id,
            source_no=sales_return.return_no,
            biz_date=sales_return.return_date,
            operator_id=operator_id,
            remark=f"销售退货 {sales_return.return_no}（{item.quality_status}）",
        )
    sales_return.status = "COMPLETED"
    sales_return.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="sal_return",
        target_id=sales_return.id,
        operator_id=operator_id,
        detail=f"确认退货单 {sales_return.return_no}",
    )
    return _return_view(db, sales_return)


def cancel_return(
    db: Session, return_id: int, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    sales_return = _require_return(db, return_id)
    if sales_return.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"退货单当前状态为 {sales_return.status}，不能取消"
        )
    sales_return.status = "CANCELLED"
    sales_return.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="sal_return",
        target_id=sales_return.id,
        operator_id=operator_id,
        detail=f"取消退货单 {sales_return.return_no}",
    )
    return _return_view(db, sales_return)


# ==================== 报表 / 统计 ====================


def order_status_report(db: Session) -> List[Dict[str, Any]]:
    """订单执行状态：订单号、客户、日期、状态、总数量、已发数量、交付完成率。"""
    rows = repository.order_status_rows(db)
    customers = {
        c.id: c.customer_name
        for c in repository.get_customers(db, [row[2] for row in rows]).values()
    }
    report = []
    for order_id, order_no, customer_id, order_date, status, total_qty, delivered_qty in rows:
        total = _as_decimal(total_qty)
        delivered = _as_decimal(delivered_qty)
        rate = (
            (delivered / total).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            if total > 0
            else Decimal("0")
        )
        report.append(
            {
                "order_no": order_no,
                "customer_name": customers.get(customer_id),
                "order_date": order_date,
                "status": status,
                "total_qty": total,
                "delivered_qty": delivered,
                "fulfillment_rate": rate,
            }
        )
    return report


def shipments_report(
    db: Session, date_from: date, date_to: date
) -> List[Dict[str, Any]]:
    """发货记录（行级），按发货日期区间。"""
    if date_from > date_to:
        raise BusinessException(CODE_PARAM_INVALID, "开始日期不能晚于结束日期")
    rows = repository.shipment_report_rows(db, date_from, date_to)
    materials = _material_map(db, [row[7] for row in rows])
    customers = {
        c.id: c.customer_name
        for c in repository.get_customers(db, [row[4] for row in rows]).values()
    }
    report = []
    for (
        _sid,
        shipment_no,
        _order_id,
        order_no,
        customer_id,
        shipment_date,
        status,
        material_id,
        warehouse_id,
        quantity,
    ) in rows:
        report.append(
            {
                "shipment_no": shipment_no,
                "order_no": order_no,
                "customer_name": customers.get(customer_id),
                "shipment_date": shipment_date,
                "status": status,
                "material_id": material_id,
                **_material_fields(materials.get(material_id)),
                "warehouse_id": warehouse_id,
                "quantity": _as_decimal(quantity),
            }
        )
    return report


def returns_report(db: Session, date_from: date, date_to: date) -> List[Dict[str, Any]]:
    """退货记录（行级），按退货日期区间。"""
    if date_from > date_to:
        raise BusinessException(CODE_PARAM_INVALID, "开始日期不能晚于结束日期")
    rows = repository.return_report_rows(db, date_from, date_to)
    materials = _material_map(db, [row[6] for row in rows])
    customers = {
        c.id: c.customer_name
        for c in repository.get_customers(db, [row[3] for row in rows]).values()
    }
    order_ids = [row[2] for row in rows if row[2]]
    orders = {o.id: o.order_no for o in repository.get_orders(db, order_ids).values()}
    report = []
    for (
        _rid,
        return_no,
        order_id,
        customer_id,
        return_date,
        status,
        material_id,
        warehouse_id,
        quantity,
        quality_status,
    ) in rows:
        report.append(
            {
                "return_no": return_no,
                "order_no": orders.get(order_id),
                "customer_name": customers.get(customer_id),
                "return_date": return_date,
                "status": status,
                "material_id": material_id,
                **_material_fields(materials.get(material_id)),
                "warehouse_id": warehouse_id,
                "quantity": _as_decimal(quantity),
                "quality_status": quality_status,
            }
        )
    return report


def sales_volume_report(
    db: Session, date_from: date, date_to: date
) -> List[Dict[str, Any]]:
    """销售量汇总：已确认发货单按物料汇总发货数量。"""
    if date_from > date_to:
        raise BusinessException(CODE_PARAM_INVALID, "开始日期不能晚于结束日期")
    rows = repository.sales_volume_rows(db, date_from, date_to)
    materials = _material_map(db, [row[0] for row in rows])
    return [
        {
            "material_id": material_id,
            **_material_fields(materials.get(material_id)),
            "total_quantity": _as_decimal(total),
        }
        for material_id, total in rows
    ]


def stats(db: Session) -> Dict[str, Any]:
    """销售模块统计（供 dashboard 使用）。"""
    order_counts = repository.order_status_counts(db)
    return {
        "customer_count": repository.count_all(db, models.SalCustomer),
        "order_count": repository.count_all(db, models.SalOrder),
        "order_counts": order_counts,
        "pending_shipment_order_count": repository.pending_shipment_order_count(db),
        "shipment_count": repository.count_all(db, models.SalShipment),
        "return_count": repository.count_all(db, models.SalReturn),
    }