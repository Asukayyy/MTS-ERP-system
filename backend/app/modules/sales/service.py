"""sales 模块业务逻辑层。

硬性约定（规格 §7 / §24 / §35 / §42）：

1. **不直接改库存**：发货 / 退货确认不直接改结存，而是调用 `inventory.contract` 的
   `push_outbound_order` / `push_inbound_order` 向库存管理推送**待出库 / 待入库单**；
   由仓库管理人员在「库存管理 → 出库管理 / 入库管理」中指定仓库并确认后，
   结存才真正变动（仓库选择权收口到库存模块）。
2. **不写计划表**：销售只提供需求来源（订单 / 预测），由 Planning 通过契约读取。
3. **只有一个物料主数据 / 人员表**：物料、销售员分别经 `system.contract`
   的 `get_material` / `get_personnel_name` 读取，不另建销售产品表 / 销售员表。
4. 本层**不调用 `db.commit()`**：由 router 提交；`contract.py` 函数运行在调用方事务里。
5. 每个状态变更在同一事务内写操作日志（`system.contract.log_operation`）。

错误码区段：`2000~2999`。
"""

import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.inventory.contract import (
    cancel_pending_inout_orders,
    get_available_by_warehouse,
    push_inbound_order,
    push_outbound_order,
)
from app.modules.sales import models, repository
from app.modules.system.contract import (
    get_sellable_materials,
    get_material,
    get_materials,
    get_personnel_name,
    get_personnel_names,
    log_operation,
    search_materials,
)
from app.shared.enums import RecordStatus

# ==================== 错误码（2000~2999） ====================

CODE_PARAM_INVALID = 2000  # 入参 / 状态非法
CODE_DUPLICATE = 2001  # 唯一性冲突（如客户编码重复）
CODE_IMMUTABLE = 2002  # 已完结 / 已取消单据不可修改
CODE_SHIP_QTY_EXCEED = 2003  # 发货数量超过未发数量
CODE_RETURN_MISMATCH = 2004  # 退货单与原订单客户不一致
CODE_NOT_FOUND = 2005  # 资源不存在
CODE_STATUS_INVALID = 2006  # 单据状态不允许该操作
CODE_RETURN_QTY_EXCEED = 2007  # 退货数量超过可退数量（已发 - 已退）
CODE_REFERENCED = 2008  # 资源已被业务单据引用，不可删除
CODE_CONTRACT_NOT_READY = 2009  # 跨模块契约尚未就绪（库存 / 计划）

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
# 销售预测状态机：DRAFT → CONFIRMED → COMPLETED，另可从 DRAFT/CONFIRMED 取消。
# 特意不设 CONFIRMED → DRAFT 的回退：Planning 是按 CONFIRMED 拉取需求的，
# 回退会让已导入的需求与预测状态对不上。
_FORECAST_TRANSITIONS: Dict[str, set] = {
    "DRAFT": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}
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


def _current_month_range(today: Optional[date] = None) -> Tuple[date, date]:
    """返回本月的 `[首日, 次月首日)`，右开区间可直接与业务日期比较。

    加 32 天再取当月首日，是为了跨月跨年（如 12 月 → 次年 1 月）都不用特判。
    """
    first_day = (today or date.today()).replace(day=1)
    return first_day, (first_day + timedelta(days=32)).replace(day=1)


def _is_sellable_active(material: Dict[str, Any]) -> bool:
    """判定物料是否可对外销售：启用，且销售类别为整机（MACHINE）或可售备件（SPARE）。"""
    return (
        material.get("status") == RecordStatus.ACTIVE.value
        and material.get("sales_category") in ("MACHINE", "SPARE")
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
        "material_abc_class": material.get("abc_class"),
        "material_sales_category": material.get("sales_category"),
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
    order_items: Sequence[models.SalOrderItem],
    materials: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """把订单行转成出参（纯内存转换）。

    行数据由调用方传入：列表接口复用 `SalOrder.items`（`lazy="selectin"` 已在分页
    查询时批量加载），详情接口传本单的一次查询结果，避免逐单重复查行。
    """
    items = []
    for item in order_items:
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
    order: models.SalOrder,
    order_items: Sequence[models.SalOrderItem],
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
        "items": _order_items_dict(order_items, materials),
    }


def _shipment_dict(
    shipment: models.SalShipment,
    shipment_items: Sequence[models.SalShipmentItem],
    materials: Dict[int, Dict[str, Any]],
    customer_name: Optional[str],
    order_no: Optional[str],
) -> Dict[str, Any]:
    items = []
    for item in shipment_items:
        items.append(
            {
                "id": item.id,
                "shipment_id": item.shipment_id,
                "order_item_id": item.order_item_id,
                "material_id": item.material_id,
                **_material_fields(materials.get(item.material_id)),
                "warehouse_id": item.warehouse_id,
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
    sales_return: models.SalReturn,
    return_items: Sequence[models.SalReturnItem],
    materials: Dict[int, Dict[str, Any]],
    customer_name: Optional[str],
    order_no: Optional[str],
) -> Dict[str, Any]:
    items = []
    for item in return_items:
        items.append(
            {
                "id": item.id,
                "return_id": item.return_id,
                "material_id": item.material_id,
                **_material_fields(materials.get(item.material_id)),
                "warehouse_id": item.warehouse_id,
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


def delete_customer(
    db: Session, customer_id: int, operator_id: Optional[int] = None
) -> None:
    """物理删除客户；已被销售单据引用时拒绝，避免破坏外键与历史数据。"""
    customer = _require_customer(db, customer_id)
    references = repository.count_customer_references(db, customer_id)
    if references:
        raise BusinessException(
            CODE_REFERENCED,
            f"客户 {customer.customer_code} 已被 {references} 条销售单据引用，无法删除（可改为停用）",
        )
    code = customer.customer_code
    repository.delete_customer(db, customer)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="sal_customer",
        target_id=customer_id,
        operator_id=operator_id,
        detail=f"删除客户 {code}",
    )


# ==================== 销售产品查询（只读物料主数据） ====================


def list_products(db: Session, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    """可销售物料：整机（MACHINE）与可单独售卖备件（SPARE），不建销售产品表。"""
    return get_sellable_materials(db, keyword)


# ==================== 产品价格（仅可售物料） ====================


def _product_price_dict(
    material: Dict[str, Any],
    price: Optional[models.SalProductPrice],
    history_count: int = 0,
) -> Dict[str, Any]:
    return {
        "material_id": material["id"],
        "material_code": material.get("material_code") or "",
        "material_name": material.get("material_name") or "",
        "sales_category": material.get("sales_category"),
        "unit_code": material.get("unit_code"),
        "standard_cost": _as_decimal(material.get("standard_cost")),
        "current_price": _as_decimal(price.price) if price else None,
        "effective_date": price.effective_date if price else None,
        "remark": price.remark if price else None,
        "history_count": history_count,
    }


def list_product_prices(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """分页查询产品价格：可售物料（含未定价）+ 已定价的其他仓库物料。"""
    materials = list(get_sellable_materials(db, keyword))
    sellable_ids = {int(item["id"]) for item in materials}
    # 新增价格时允许从全部仓库物料中选取，这些物料也要在列表中可见
    extra_ids = [
        row.material_id for row in repository.list_prices(db) if row.material_id not in sellable_ids
    ]
    if extra_ids:
        extra_map = get_materials(db, extra_ids)
        needle = (keyword or "").strip().lower()
        for material_id in extra_ids:
            material = extra_map.get(int(material_id))
            if not material:
                continue
            haystack = f"{material.get('material_code') or ''} {material.get('material_name') or ''}".lower()
            if needle and needle not in haystack:
                continue
            materials.append(material)
    materials.sort(key=lambda item: str(item.get("material_code") or ""))
    material_ids = [int(item["id"]) for item in materials]
    prices = repository.get_prices(db, material_ids)
    counts = repository.price_history_counts(db, material_ids)
    total = len(materials)
    start = (page - 1) * page_size
    page_materials = materials[start:start + page_size]
    items = [
        _product_price_dict(
            material,
            prices.get(int(material["id"])),
            counts.get(int(material["id"]), 0),
        )
        for material in page_materials
    ]
    return items, total


def get_product_price(db: Session, material_id: int) -> Dict[str, Any]:
    """查询单个可售物料的当前价格。"""
    material = _require_material(db, material_id)
    price = repository.get_price(db, material_id)
    count = len(repository.list_price_history(db, material_id))
    return _product_price_dict(material, price, count)


def set_product_price(
    db: Session,
    material_id: int,
    *,
    price: Decimal,
    effective_date: Optional[date] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """调整产品价格：更新当前价并追加一条价格变动记录。

    价格未变化时只更新备注 / 生效日期，不写变动记录（避免详细页被重复
    提交的同价记录刷屏）。
    """
    material = _require_material(db, material_id)
    if material.get("status") != RecordStatus.ACTIVE.value:
        raise BusinessException(
            CODE_PARAM_INVALID,
            f"物料 {material.get('material_code')} 已停用，不能定价",
        )
    new_price = _money(price)
    if new_price < 0:
        raise BusinessException(CODE_PARAM_INVALID, "产品价格不能为负数")
    effective = effective_date or date.today()
    row = repository.get_price(db, material_id)
    changed = row is None or _as_decimal(row.price) != new_price
    if row is None:
        row = models.SalProductPrice(
            material_id=material_id,
            price=new_price,
            effective_date=effective,
            remark=remark,
            created_by=operator_id,
            updated_by=operator_id,
        )
        repository.add_price(db, row)
    else:
        row.price = new_price
        row.effective_date = effective
        row.remark = remark
        row.updated_by = operator_id
    if changed:
        repository.add_price_history(
            db,
            models.SalProductPriceHistory(
                material_id=material_id,
                price=new_price,
                effective_date=effective,
                remark=remark,
                created_by=operator_id,
                updated_by=operator_id,
            ),
        )
        log_operation(
            db,
            module=MODULE,
            action="UPDATE",
            target_type="sal_product_price",
            target_id=material_id,
            operator_id=operator_id,
            detail=f"调整产品价格 {material.get('material_code')} → {new_price}",
        )
    count = len(repository.list_price_history(db, material_id))
    return _product_price_dict(material, row, count)


def product_price_history(db: Session, material_id: int) -> List[Dict[str, Any]]:
    """某物料的产品价格变动记录（按生效日期升序）。"""
    _require_material(db, material_id)
    return [
        {
            "id": row.id,
            "material_id": row.material_id,
            "price": _as_decimal(row.price),
            "effective_date": row.effective_date,
            "remark": row.remark,
        }
        for row in repository.list_price_history(db, material_id)
    ]


def delete_product_price(
    db: Session, material_id: int, operator_id: Optional[int] = None
) -> None:
    """删除产品价格及其全部价格变动记录，物料回到「未定价」。"""
    material = _require_material(db, material_id)
    price = repository.get_price(db, material_id)
    if price is None:
        raise BusinessException(CODE_NOT_FOUND, "该物料尚未维护产品价格")
    repository.delete_price_history(db, material_id)
    repository.delete_price(db, price)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="sal_product_price",
        target_id=material_id,
        operator_id=operator_id,
        detail=f"删除产品价格 {material.get('material_code')}",
    )


# ==================== 销售预测 ====================


def list_forecasts(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    forecast_month: Optional[str] = None,
    sales_category: Optional[str] = None,
    abc_class: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    material_ids = _filter_material_ids(db, sales_category, abc_class)
    rows, total = repository.list_forecasts(
        db, page, page_size, material_id, status, forecast_month, material_ids
    )
    materials = _material_map(db, [r.material_id for r in rows])
    customers = {
        c.id: c.customer_name
        for c in repository.get_customers(db, [r.customer_id for r in rows]).values()
    }
    items = [_forecast_dict(row, materials, customers.get(row.customer_id)) for row in rows]
    return items, total


def _filter_material_ids(
    db: Session, sales_category: Optional[str], abc_class: Optional[str]
) -> Optional[List[int]]:
    """按销售类别 / ABC 分类收敛物料范围；两个条件都为空时返回 None（不过滤）。"""
    if not sales_category and not abc_class:
        return None
    rows = search_materials(
        db,
        abc_class=abc_class,
        sales_category=sales_category,
        limit=5000,
    )
    return [int(row["id"]) for row in rows]


def forecast_summary(
    db: Session,
    *,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    forecast_month: Optional[str] = None,
    sales_category: Optional[str] = None,
    abc_class: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """按销售类别汇总预测数量：整机与可售备件分开统计，互不混算。"""
    material_ids = _filter_material_ids(db, sales_category, abc_class)
    rows = repository.forecast_rows(
        db,
        material_id=material_id,
        status=status,
        forecast_month=forecast_month,
        material_ids=material_ids,
    )
    materials = _material_map(db, [row.material_id for row in rows])
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        category = materials.get(row.material_id, {}).get("sales_category") or "INTERNAL"
        bucket = buckets.setdefault(
            category, {"sales_category": category, "forecast_qty": Decimal("0"), "count": 0}
        )
        bucket["forecast_qty"] += _as_decimal(row.forecast_qty)
        bucket["count"] += 1
    return list(buckets.values())


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
    if forecast.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID,
            f"预测单当前状态为 {forecast.status}，仅 DRAFT 状态可修改",
        )
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
    allowed = _FORECAST_TRANSITIONS.get(forecast.status, set())
    if status not in allowed:
        raise BusinessException(
            CODE_STATUS_INVALID,
            f"预测单状态不允许从 {forecast.status} 流转到 {status}",
        )
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
        if unit_price == 0:
            # 未传单价时按产品当前价格兜底，保证下单价格与「产品价格」一致
            price_row = repository.get_price(db, material_id)
            if price_row is not None:
                unit_price = _money(price_row.price)
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
    order_items = repository.get_order_items(db, order.id)
    materials = _material_map(db, [item.material_id for item in order_items])
    customer = repository.get_customer(db, order.customer_id)
    return _order_dict(
        order,
        order_items,
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
    # 订单行靠 SalOrder.items 的 selectin 一次性加载，销售员姓名也批量取。
    # 这些都必须在循环外准备好：逐行单查时 20 行列表会打出 40+ 条 SQL。
    salespersons = get_personnel_names(db, [r.salesperson_id for r in rows])
    materials = _material_map(
        db, [item.material_id for row in rows for item in row.items]
    )
    items = [
        _order_dict(
            row,
            row.items,
            materials,
            customers.get(row.customer_id),
            salespersons.get(row.salesperson_id),
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
        if not _is_sellable_active(material):
            raise BusinessException(
                CODE_PARAM_INVALID,
                f"物料 {material.get('material_code')} 不是可销售的整机或备件，不能确认订单",
            )
        if _as_decimal(item.quantity) <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "订单行数量必须为正数")


def _settle_order_from_stock(
    db: Session, order: models.SalOrder, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    """订单确认后按可用库存分流：够的部分生成发货草稿，缺口登记为计划需求。

    - 可用量口径：`现存量 - 锁定量`；安全库存**不参与扣减**，只作为补货触发线；
    - 跨仓库按可用量从大到小分配，同一订单行可拆成多条仓库发货明细；
    - 缺口按物料汇总，经 `planning.contract` 登记为 `SALES` 需求（直接 CONFIRMED）；
    - **不提交事务**，与订单状态变更同一事务，任一步失败整单回滚。
    """
    try:
        from app.modules.planning import contract as planning_contract  # type: ignore
    except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
        raise BusinessException(CODE_CONTRACT_NOT_READY, "计划接口尚未就绪") from exc

    items = repository.get_order_items(db, order.id)
    # 其他草稿发货单已占用的库存要先扣掉（发货确认前不会真正扣减结存）。
    # 草稿可能没指定仓库（由仓库管理在出库单里定仓），这种占用只能按物料整体抵扣。
    reserved = repository.draft_shipment_allocations(db)
    reserved_by_material: Dict[int, Decimal] = {}
    for (reserved_warehouse_id, reserved_material_id), reserved_qty in reserved.items():
        if reserved_warehouse_id is None:
            reserved_by_material[reserved_material_id] = (
                reserved_by_material.get(reserved_material_id, Decimal("0")) + reserved_qty
            )
    # 同一物料可能出现在多行，库存池必须按物料共享，否则会重复分配同一批库存
    pools: Dict[int, List[Dict[str, Any]]] = {}
    shipment_lines: List[Dict[str, Any]] = []
    required: Dict[int, Decimal] = {}
    allocated: Dict[int, Decimal] = {}
    for item in items:
        remaining = _as_decimal(item.quantity) - _as_decimal(item.delivered_qty)
        if remaining <= 0:
            continue
        material_id = item.material_id
        required[material_id] = required.get(material_id, Decimal("0")) + remaining
        pool = pools.get(material_id)
        if pool is None:
            pool = []
            for row in get_available_by_warehouse(db, material_id):
                warehouse_id = int(row["warehouse_id"])
                free = _as_decimal(row["available"]) - reserved.get(
                    (warehouse_id, material_id), Decimal("0")
                )
                if free > 0:
                    pool.append({"warehouse_id": warehouse_id, "available": free})
            # 未指定仓库的草稿占用：按可用量从大到小依次抵扣，与后续分配顺序一致
            outstanding = reserved_by_material.get(material_id, Decimal("0"))
            for bucket in pool:
                if outstanding <= 0:
                    break
                take = min(bucket["available"], outstanding)
                bucket["available"] -= take
                outstanding -= take
            pool = [bucket for bucket in pool if bucket["available"] > 0]
            pools[material_id] = pool
        need = remaining
        for bucket in pool:
            if need <= 0:
                break
            take = min(bucket["available"], need)
            if take <= 0:
                continue
            bucket["available"] -= take
            need -= take
            shipment_lines.append(
                {
                    "order_item_id": item.id,
                    "warehouse_id": bucket["warehouse_id"],
                    "quantity": take,
                    "remark": "订单确认时按可用库存自动分配",
                }
            )
            allocated[material_id] = allocated.get(material_id, Decimal("0")) + take

    shipment_id: Optional[int] = None
    shipment_no: Optional[str] = None
    if shipment_lines:
        shipment = create_shipment(
            db,
            order_id=order.id,
            shipment_date=order.delivery_date,
            items=shipment_lines,
            remark=f"订单 {order.order_no} 确认时按可用库存自动生成",
            operator_id=operator_id,
        )
        shipment_id = shipment.get("id")
        shipment_no = shipment.get("shipment_no")

    materials = _material_map(db, list(required.keys()))
    summary_items: List[Dict[str, Any]] = []
    demand_nos: List[str] = []
    stock_total = Decimal("0")
    shortage_total = Decimal("0")
    for material_id, need_qty in required.items():
        got = allocated.get(material_id, Decimal("0"))
        shortage = need_qty - got
        material = materials.get(material_id, {})
        summary_items.append(
            {
                "material_id": material_id,
                "material_code": material.get("material_code"),
                "material_name": material.get("material_name"),
                "required_qty": need_qty,
                "stock_qty": got,
                "shortage_qty": shortage if shortage > 0 else Decimal("0"),
            }
        )
        stock_total += got
        if shortage > 0:
            # 需求数量登记**订单未交付总量**（而非缺口）：库存已分配的部分由
            # MRP 用可用库存净算抵扣，需求侧若只记缺口，会被库存重复抵扣一次。
            result = planning_contract.create_sales_demand_from_order(
                db,
                order_id=order.id,
                order_no=order.order_no,
                material_id=material_id,
                quantity=need_qty,
                due_date=order.delivery_date,
                remark=(
                    f"销售订单 {order.order_no} 客户需求 {need_qty}"
                    f"（库存已分配 {got}，缺口 {shortage}）"
                ),
                operator_id=operator_id,
            )
            demand_nos.append(result["demand_no"])
            shortage_total += shortage

    log_operation(
        db,
        module=MODULE,
        action="STOCK_ALLOCATE",
        target_type="sal_order",
        target_id=order.id,
        operator_id=operator_id,
        detail=(
            f"销售订单 {order.order_no} 确认后库存分流：库存发货 {stock_total}"
            f"（发货单 {shipment_no or '无'}），缺口 {shortage_total} 触发计划需求"
            f"（需求 {'、'.join(demand_nos) or '无'}，按订单未交付总量登记）"
        ),
    )
    return {
        "shipment_id": shipment_id,
        "shipment_no": shipment_no,
        "stock_qty": stock_total,
        "shortage_qty": shortage_total,
        "demand_nos": demand_nos,
        "items": summary_items,
    }


def _release_order_allocation(
    db: Session, order: models.SalOrder, operator_id: Optional[int] = None
) -> None:
    """订单取消时回收库存分流结果：取消自动发货草稿 + 取消未进入 MPS 的缺口需求。

    已确认（出货完成）的发货单不回收，已 `RELEASED` 的需求留在计划侧。
    **不提交事务**。
    """
    shipments, _ = repository.list_shipments(db, page=1, page_size=200, order_id=order.id)
    for shipment in shipments:
        if shipment.status == "DRAFT":
            cancel_shipment(db, shipment.id, operator_id)
    try:
        from app.modules.planning import contract as planning_contract  # type: ignore
    except Exception:  # noqa: BLE001 - 计划模块未就绪时跳过需求回收
        return
    planning_contract.cancel_sales_demands_for_order(db, order.id, operator_id)


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
    db.flush()
    # 订单确认后立即按可用库存分流：够的生成发货草稿，缺口转计划需求
    allocation = _settle_order_from_stock(db, order, operator_id) if status == "CONFIRMED" else None
    if status == "CANCELLED":
        _release_order_allocation(db, order, operator_id)
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="sal_order",
        target_id=order.id,
        operator_id=operator_id,
        detail=f"销售订单 {order.order_no} 状态改为 {status}",
    )
    view = _order_view(db, order)
    if allocation is not None:
        view["allocation"] = allocation
    return view


# ==================== 销售发货 ====================


def list_shipments(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    order_id: Optional[int] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_shipments(db, page, page_size, order_id, status)
    # 客户名、订单号、物料都批量预取（一行一次单查时 20 行会打出 120+ 条 SQL）；
    # 发货明细来自 SalShipment.items 的 selectin 预加载。
    customers = {
        c.id: c.customer_name
        for c in repository.get_customers(db, [r.customer_id for r in rows]).values()
    }
    orders = repository.get_orders(db, [r.order_id for r in rows])
    materials = _material_map(
        db, [item.material_id for row in rows for item in row.items]
    )
    items = [
        _shipment_dict(
            row,
            row.items,
            materials,
            customers.get(row.customer_id),
            orders[row.order_id].order_no if orders.get(row.order_id) else None,
        )
        for row in rows
    ]
    return items, total


def _shipment_view(db: Session, shipment: models.SalShipment) -> Dict[str, Any]:
    shipment_items = repository.get_shipment_items(db, shipment.id)
    materials = _material_map(db, [i.material_id for i in shipment_items])
    customer = repository.get_customer(db, shipment.customer_id)
    order = repository.get_order(db, shipment.order_id)
    return _shipment_dict(
        shipment,
        shipment_items,
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
    # 同一订单行允许在一张发货单里出现多行，未发额度必须**累计**判断：
    # 否则两行各自都不超未发数量、合计却超了，要到确认时才报错。
    reserved: Dict[int, Decimal] = {}
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
        available = remaining - reserved.get(order_item.id, Decimal("0"))
        if qty > available:
            raise BusinessException(
                CODE_SHIP_QTY_EXCEED,
                f"发货数量超过未发数量：物料 {order_item.material_id} 可发 {available}，本次 {qty}",
            )
        reserved[order_item.id] = reserved.get(order_item.id, Decimal("0")) + qty
        repository.add_shipment_item(
            db,
            models.SalShipmentItem(
                shipment_id=shipment.id,
                order_item_id=order_item.id,
                material_id=order_item.material_id,
                warehouse_id=raw.get("warehouse_id"),
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
    """确认发货（原子）：推送库存待出库单 → 回写订单行已发数量 → 更新单据 / 订单状态。

    **不再直接扣减结存、也不再指定仓库**：库存管理会生成一张「待出库单」，
    由仓库管理人员选择仓库并确认后，库存才真正减少。
    """
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
    push_items: List[Dict[str, Any]] = []
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
        push_items.append({"material_id": item.material_id, "quantity": qty})
        order_item.delivered_qty = _as_decimal(order_item.delivered_qty) + qty

    # 推送到库存管理 → 出库管理（待仓库指定仓库并确认）
    customer = repository.get_customers(db, [order.customer_id]).get(order.customer_id)
    customer_label = customer.customer_name if customer else ""
    pushed = push_outbound_order(
        db,
        op_date=shipment.shipment_date,
        items=push_items,
        source_module=MODULE,
        source_type="SALES_SHIPMENT",
        source_reference_id=shipment.id,
        source_no=shipment.shipment_no,
        remark=(
            f"订单 {order.order_no}"
            + (f"，客户 {customer_label}" if customer_label else "")
            + f"，共 {len(push_items)} 项"
        ),
        operator_id=operator_id,
    )

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
        detail=(
            f"确认发货单 {shipment.shipment_no}，订单 {order.order_no} → {order.status}；"
            f"已推送库存待出库单 {pushed.get('operation_no')}"
        ),
    )
    view = _shipment_view(db, shipment)
    view["inventory_operation_no"] = pushed.get("operation_no")
    view["inventory_operation_id"] = pushed.get("operation_id")
    return view


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
    # 尚未被仓库确认的待出库单一并撤销
    cancelled = cancel_pending_inout_orders(
        db,
        source_module=MODULE,
        source_type="SALES_SHIPMENT",
        source_reference_id=shipment.id,
        operator_id=operator_id,
        reason=f"发货单 {shipment.shipment_no} 已取消",
    )
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="sal_shipment",
        target_id=shipment.id,
        operator_id=operator_id,
        detail=(
            f"取消发货单 {shipment.shipment_no}"
            + (f"，同时撤销待出库单 {cancelled} 张" if cancelled else "")
        ),
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
    # 同 list_shipments：客户名 / 订单号 / 物料批量预取，明细用 selectin 预加载。
    customers = {
        c.id: c.customer_name
        for c in repository.get_customers(db, [r.customer_id for r in rows]).values()
    }
    orders = repository.get_orders(db, [r.order_id for r in rows if r.order_id])
    materials = _material_map(
        db, [item.material_id for row in rows for item in row.items]
    )
    items = [
        _return_dict(
            row,
            row.items,
            materials,
            customers.get(row.customer_id),
            orders[row.order_id].order_no if orders.get(row.order_id) else None,
        )
        for row in rows
    ]
    return items, total


def _return_view(db: Session, sales_return: models.SalReturn) -> Dict[str, Any]:
    return_items = repository.get_return_items(db, sales_return.id)
    materials = _material_map(db, [i.material_id for i in return_items])
    customer = repository.get_customer(db, sales_return.customer_id)
    order = (
        repository.get_order(db, sales_return.order_id) if sales_return.order_id else None
    )
    return _return_dict(
        sales_return,
        return_items,
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
    shipped: Dict[int, Decimal] = {}
    returned: Dict[int, Decimal] = {}
    if order_id is not None:
        order = _require_order(db, order_id)
        if order.customer_id != customer_id:
            raise BusinessException(
                CODE_RETURN_MISMATCH, "退货单客户与原销售订单客户不一致"
            )
        # 可退额度 = 该订单该物料的已发数量 - 已占用退货数量（未取消的退货单）
        shipped = repository.delivered_qty_by_material(db, order_id)
        returned = repository.returned_qty_by_material(db, order_id)
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
        material_id = raw.get("material_id")
        _require_material(db, material_id)
        qty = _as_decimal(raw.get("quantity"))
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "退货数量必须为正数")
        if order_id is not None:
            used = returned.get(material_id, Decimal("0"))
            available = shipped.get(material_id, Decimal("0")) - used
            if qty > available:
                raise BusinessException(
                    CODE_RETURN_QTY_EXCEED,
                    f"退货数量超过可退数量：物料 {material_id} 可退 {available}，本次 {qty}",
                )
            # 同一张退货单内多行同物料时，后面几行要按已占用额度继续扣
            returned[material_id] = used + qty
        quality_status = raw.get("quality_status") or "QUALIFIED"
        if quality_status not in _QUALITY_STATUSES:
            raise BusinessException(CODE_PARAM_INVALID, f"非法质量状态：{quality_status}")
        repository.add_return_item(
            db,
            models.SalReturnItem(
                return_id=sales_return.id,
                material_id=material_id,
                warehouse_id=raw.get("warehouse_id"),
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
    """确认退货（原子）：推送库存待入库单，状态置 COMPLETED。

    **不再直接增加结存、也不再指定仓库**：库存管理生成「待入库单」，
    由仓库管理人员选择仓库并确认后，库存才真正增加。

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
    # 确认前再核一次可退额度：本单是草稿期间可能有别的退货单先确认了。
    # 用 exclude_return_id 排除本单，否则会把自己的明细当成已占用。
    if sales_return.order_id is not None:
        shipped = repository.delivered_qty_by_material(db, sales_return.order_id)
        returned = repository.returned_qty_by_material(
            db, sales_return.order_id, exclude_return_id=sales_return.id
        )
        for item in items:
            qty = _as_decimal(item.quantity)
            used = returned.get(item.material_id, Decimal("0"))
            available = shipped.get(item.material_id, Decimal("0")) - used
            if qty > available:
                raise BusinessException(
                    CODE_RETURN_QTY_EXCEED,
                    f"退货数量超过可退数量：物料 {item.material_id} 可退 {available}，本次 {qty}",
                )
            returned[item.material_id] = used + qty
    push_items = [
        {
            "material_id": item.material_id,
            "quantity": _as_decimal(item.quantity),
            "remark": f"质量状态 {item.quality_status}",
        }
        for item in items
    ]
    customer = repository.get_customers(
        db, [sales_return.customer_id] if sales_return.customer_id else []
    ).get(sales_return.customer_id)
    customer_label = customer.customer_name if customer else ""
    pushed = push_inbound_order(
        db,
        op_date=sales_return.return_date,
        items=push_items,
        source_module=MODULE,
        source_type="SALES_RETURN",
        source_reference_id=sales_return.id,
        source_no=sales_return.return_no,
        remark=(
            (f"客户 {customer_label}，" if customer_label else "")
            + f"共 {len(push_items)} 项"
        ),
        operator_id=operator_id,
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
        detail=(
            f"确认退货单 {sales_return.return_no}；"
            f"已推送库存待入库单 {pushed.get('operation_no')}"
        ),
    )
    view = _return_view(db, sales_return)
    view["inventory_operation_no"] = pushed.get("operation_no")
    view["inventory_operation_id"] = pushed.get("operation_id")
    return view


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
    cancelled = cancel_pending_inout_orders(
        db,
        source_module=MODULE,
        source_type="SALES_RETURN",
        source_reference_id=sales_return.id,
        operator_id=operator_id,
        reason=f"退货单 {sales_return.return_no} 已取消",
    )
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="sal_return",
        target_id=sales_return.id,
        operator_id=operator_id,
        detail=(
            f"取消退货单 {sales_return.return_no}"
            + (f"，同时撤销待入库单 {cancelled} 张" if cancelled else "")
        ),
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
    db: Session, date_from: Optional[date] = None, date_to: Optional[date] = None
) -> List[Dict[str, Any]]:
    """发货记录（行级），按发货日期区间；两个日期都可省，省则不过滤。"""
    if date_from and date_to and date_from > date_to:
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


def returns_report(
    db: Session, date_from: Optional[date] = None, date_to: Optional[date] = None
) -> List[Dict[str, Any]]:
    """退货记录（行级），按退货日期区间；两个日期都可省，省则不过滤。"""
    if date_from and date_to and date_from > date_to:
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
    db: Session, date_from: Optional[date] = None, date_to: Optional[date] = None
) -> List[Dict[str, Any]]:
    """销售量汇总：已确认发货单按物料汇总发货数量，日期区间可选。"""
    if date_from and date_to and date_from > date_to:
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
    """销售模块统计（供 dashboard 使用）。

    订单 / 未发完订单 / 发货 / 退货四项都按**本月**统计：它们是期间业务量，
    直接用 `COUNT(*)` 会随历史数据越积越大，工作台上看到的就不再是本期经营
    情况了。`customer_count` 是主数据总量，不参与期间过滤。
    """
    month_start, next_month_start = _current_month_range()
    return {
        "customer_count": repository.count_all(db, models.SalCustomer),
        "order_count": repository.count_by_date_range(
            db, models.SalOrder, models.SalOrder.order_date, month_start, next_month_start
        ),
        "order_counts": repository.order_status_counts(db, month_start, next_month_start),
        "pending_shipment_order_count": repository.pending_shipment_order_count(
            db, month_start, next_month_start
        ),
        "shipment_count": repository.count_by_date_range(
            db, models.SalShipment, models.SalShipment.shipment_date, month_start, next_month_start
        ),
        "return_count": repository.count_by_date_range(
            db, models.SalReturn, models.SalReturn.return_date, month_start, next_month_start
        ),
    }

def get_material_delivered_values(db: Session, since: date) -> Dict[int, Decimal]:
    """按物料汇总指定日期之后的销售出库金额（供 ABC 自动分类使用）。"""
    return dict(repository.material_delivered_value_rows(db, since))
