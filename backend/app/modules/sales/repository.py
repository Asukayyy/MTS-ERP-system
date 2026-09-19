"""sales 模块数据访问层。

约定（规格 §24 / §35）：

- 只做数据库读写与查询拼装，**不写业务规则**。
- 只允许被本模块的 `service.py` / `contract.py` 调用；其它模块禁止直接 import 本文件。
- 跨模块数据（物料、人员、库存）通过对方 Contract 获取，本层**不跨模块 JOIN**，
  只 JOIN 本模块自己的表（`sal_*`）。

错误码区段：`2000~2999`（定义在 `service.py`）。
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.sales import models

# ==================== 通用工具 ====================


def count_all(db: Session, model) -> int:
    """统计某表总行数。"""
    return db.scalar(select(func.count()).select_from(model)) or 0


def count_where(db: Session, model, *criteria) -> int:
    """按条件统计行数。"""
    return db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0


def _paginate(db: Session, stmt, page: int, page_size: int) -> Tuple[List, int]:
    """对 select 语句做统一分页，返回 (items, total)。"""
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def next_no(db: Session, model, field, prefix: str) -> str:
    """生成业务单号：`<prefix><4位序号>`（按前缀内计数，保证同日多次调用递增）。"""
    total = (
        db.scalar(
            select(func.count()).select_from(model).where(field.like(f"{prefix}%"))
        )
        or 0
    )
    return f"{prefix}{total + 1:04d}"


# ==================== 客户 ====================


def list_customers(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
):
    """分页查询客户，支持编码/名称关键字与状态过滤。"""
    stmt = select(models.SalCustomer).order_by(models.SalCustomer.id.desc())
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                models.SalCustomer.customer_code.like(like),
                models.SalCustomer.customer_name.like(like),
            )
        )
    if status:
        stmt = stmt.where(models.SalCustomer.status == status)
    return _paginate(db, stmt, page, page_size)


def get_customer(db: Session, customer_id: int) -> Optional[models.SalCustomer]:
    return db.get(models.SalCustomer, customer_id)


def get_customer_by_code(db: Session, customer_code: str) -> Optional[models.SalCustomer]:
    return db.scalar(
        select(models.SalCustomer).where(models.SalCustomer.customer_code == customer_code)
    )


def get_customers(db: Session, customer_ids: Sequence[int]) -> dict:
    """批量取客户 `{customer_id: SalCustomer}`，供列表补名称。"""
    ids = [int(i) for i in customer_ids if i]
    if not ids:
        return {}
    rows = db.scalars(select(models.SalCustomer).where(models.SalCustomer.id.in_(ids)))
    return {row.id: row for row in rows}


def add_customer(db: Session, customer: models.SalCustomer) -> models.SalCustomer:
    db.add(customer)
    db.flush()
    return customer


# ==================== 销售预测 ====================


def list_forecasts(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    forecast_month: Optional[str] = None,
):
    stmt = select(models.SalForecast).order_by(models.SalForecast.id.desc())
    if material_id:
        stmt = stmt.where(models.SalForecast.material_id == material_id)
    if status:
        stmt = stmt.where(models.SalForecast.status == status)
    if forecast_month:
        stmt = stmt.where(models.SalForecast.forecast_month == forecast_month)
    return _paginate(db, stmt, page, page_size)


def get_forecast(db: Session, forecast_id: int) -> Optional[models.SalForecast]:
    return db.get(models.SalForecast, forecast_id)


def get_forecast_by_no(db: Session, forecast_no: str) -> Optional[models.SalForecast]:
    return db.scalar(
        select(models.SalForecast).where(models.SalForecast.forecast_no == forecast_no)
    )


def add_forecast(db: Session, forecast: models.SalForecast) -> models.SalForecast:
    db.add(forecast)
    db.flush()
    return forecast


def delete_forecast(db: Session, forecast: models.SalForecast) -> None:
    db.delete(forecast)


# ==================== 销售订单 ====================


def list_orders(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    keyword: Optional[str] = None,
):
    stmt = select(models.SalOrder).order_by(models.SalOrder.id.desc())
    if customer_id:
        stmt = stmt.where(models.SalOrder.customer_id == customer_id)
    if status:
        stmt = stmt.where(models.SalOrder.status == status)
    if date_from:
        stmt = stmt.where(models.SalOrder.order_date >= date_from)
    if date_to:
        stmt = stmt.where(models.SalOrder.order_date <= date_to)
    if keyword:
        stmt = stmt.where(models.SalOrder.order_no.like(f"%{keyword}%"))
    return _paginate(db, stmt, page, page_size)


def get_order(db: Session, order_id: int) -> Optional[models.SalOrder]:
    return db.get(models.SalOrder, order_id)


def get_order_by_no(db: Session, order_no: str) -> Optional[models.SalOrder]:
    return db.scalar(select(models.SalOrder).where(models.SalOrder.order_no == order_no))


def add_order(db: Session, order: models.SalOrder) -> models.SalOrder:
    db.add(order)
    db.flush()
    return order


def add_order_item(db: Session, item: models.SalOrderItem) -> models.SalOrderItem:
    db.add(item)
    db.flush()
    return item


def get_order_item(db: Session, order_item_id: int) -> Optional[models.SalOrderItem]:
    return db.get(models.SalOrderItem, order_item_id)


def get_orders(db: Session, order_ids: Sequence[int]) -> dict:
    """批量取订单 `{order_id: SalOrder}`，供列表 / 报表补订单号。"""
    ids = [int(i) for i in order_ids if i]
    if not ids:
        return {}
    rows = db.scalars(select(models.SalOrder).where(models.SalOrder.id.in_(ids)))
    return {row.id: row for row in rows}


def get_order_items(db: Session, order_id: int) -> List[models.SalOrderItem]:
    return list(
        db.scalars(
            select(models.SalOrderItem)
            .where(models.SalOrderItem.order_id == order_id)
            .order_by(models.SalOrderItem.line_no)
        )
    )


def add_order_item_flush(db: Session, item: models.SalOrderItem) -> models.SalOrderItem:
    db.add(item)
    db.flush()
    return item


def delete_order_items(db: Session, order_id: int) -> None:
    for item in get_order_items(db, order_id):
        db.delete(item)


def delete_order(db: Session, order: models.SalOrder) -> None:
    db.delete(order)


# ==================== 销售发货 ====================


def list_shipments(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    order_id: Optional[int] = None,
    status: Optional[str] = None,
):
    stmt = select(models.SalShipment).order_by(models.SalShipment.id.desc())
    if order_id:
        stmt = stmt.where(models.SalShipment.order_id == order_id)
    if status:
        stmt = stmt.where(models.SalShipment.status == status)
    return _paginate(db, stmt, page, page_size)


def get_shipment(db: Session, shipment_id: int) -> Optional[models.SalShipment]:
    return db.get(models.SalShipment, shipment_id)


def get_shipment_by_no(db: Session, shipment_no: str) -> Optional[models.SalShipment]:
    return db.scalar(
        select(models.SalShipment).where(models.SalShipment.shipment_no == shipment_no)
    )


def add_shipment(db: Session, shipment: models.SalShipment) -> models.SalShipment:
    db.add(shipment)
    db.flush()
    return shipment


def add_shipment_item(
    db: Session, item: models.SalShipmentItem
) -> models.SalShipmentItem:
    db.add(item)
    db.flush()
    return item


def get_shipment_items(db: Session, shipment_id: int) -> List[models.SalShipmentItem]:
    return list(
        db.scalars(
            select(models.SalShipmentItem)
            .where(models.SalShipmentItem.shipment_id == shipment_id)
            .order_by(models.SalShipmentItem.id)
        )
    )


# ==================== 销售退货 ====================


def list_returns(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    order_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
):
    stmt = select(models.SalReturn).order_by(models.SalReturn.id.desc())
    if order_id:
        stmt = stmt.where(models.SalReturn.order_id == order_id)
    if customer_id:
        stmt = stmt.where(models.SalReturn.customer_id == customer_id)
    if status:
        stmt = stmt.where(models.SalReturn.status == status)
    return _paginate(db, stmt, page, page_size)


def get_return(db: Session, return_id: int) -> Optional[models.SalReturn]:
    return db.get(models.SalReturn, return_id)


def get_return_by_no(db: Session, return_no: str) -> Optional[models.SalReturn]:
    return db.scalar(select(models.SalReturn).where(models.SalReturn.return_no == return_no))


def add_return(db: Session, sales_return: models.SalReturn) -> models.SalReturn:
    db.add(sales_return)
    db.flush()
    return sales_return


def add_return_item(db: Session, item: models.SalReturnItem) -> models.SalReturnItem:
    db.add(item)
    db.flush()
    return item


def get_return_items(db: Session, return_id: int) -> List[models.SalReturnItem]:
    return list(
        db.scalars(
            select(models.SalReturnItem)
            .where(models.SalReturnItem.return_id == return_id)
            .order_by(models.SalReturnItem.id)
        )
    )


# ==================== 报表 / 统计 ====================


def order_status_rows(db: Session) -> List[Tuple]:
    """订单执行状态：按订单汇总订单数量与已发数量。"""
    stmt = (
        select(
            models.SalOrder.id,
            models.SalOrder.order_no,
            models.SalOrder.customer_id,
            models.SalOrder.order_date,
            models.SalOrder.status,
            func.coalesce(func.sum(models.SalOrderItem.quantity), 0),
            func.coalesce(func.sum(models.SalOrderItem.delivered_qty), 0),
        )
        .join(models.SalOrderItem, models.SalOrderItem.order_id == models.SalOrder.id)
        .group_by(
            models.SalOrder.id,
            models.SalOrder.order_no,
            models.SalOrder.customer_id,
            models.SalOrder.order_date,
            models.SalOrder.status,
        )
        .order_by(models.SalOrder.id.desc())
    )
    return list(db.execute(stmt).all())


def shipment_report_rows(
    db: Session, date_from: date, date_to: date
) -> List[Tuple]:
    """发货记录（行级）：按发货日期区间查询。"""
    stmt = (
        select(
            models.SalShipment.id,
            models.SalShipment.shipment_no,
            models.SalShipment.order_id,
            models.SalOrder.order_no,
            models.SalShipment.customer_id,
            models.SalShipment.shipment_date,
            models.SalShipment.status,
            models.SalShipmentItem.material_id,
            models.SalShipmentItem.warehouse_id,
            models.SalShipmentItem.quantity,
        )
        .join(models.SalShipmentItem, models.SalShipmentItem.shipment_id == models.SalShipment.id)
        .join(models.SalOrder, models.SalOrder.id == models.SalShipment.order_id)
        .where(
            models.SalShipment.shipment_date >= date_from,
            models.SalShipment.shipment_date <= date_to,
        )
        .order_by(models.SalShipment.id.desc(), models.SalShipmentItem.id)
    )
    return list(db.execute(stmt).all())


def return_report_rows(
    db: Session, date_from: date, date_to: date
) -> List[Tuple]:
    """退货记录（行级）：按退货日期区间查询。"""
    stmt = (
        select(
            models.SalReturn.id,
            models.SalReturn.return_no,
            models.SalReturn.order_id,
            models.SalReturn.customer_id,
            models.SalReturn.return_date,
            models.SalReturn.status,
            models.SalReturnItem.material_id,
            models.SalReturnItem.warehouse_id,
            models.SalReturnItem.quantity,
            models.SalReturnItem.quality_status,
        )
        .join(models.SalReturnItem, models.SalReturnItem.return_id == models.SalReturn.id)
        .where(
            models.SalReturn.return_date >= date_from,
            models.SalReturn.return_date <= date_to,
        )
        .order_by(models.SalReturn.id.desc(), models.SalReturnItem.id)
    )
    return list(db.execute(stmt).all())


def sales_volume_rows(db: Session, date_from: date, date_to: date) -> List[Tuple]:
    """销售量汇总：已确认发货单按物料汇总发货数量。"""
    stmt = (
        select(
            models.SalShipmentItem.material_id,
            func.coalesce(func.sum(models.SalShipmentItem.quantity), 0),
        )
        .join(models.SalShipment, models.SalShipment.id == models.SalShipmentItem.shipment_id)
        .where(
            models.SalShipment.status == "COMPLETED",
            models.SalShipment.shipment_date >= date_from,
            models.SalShipment.shipment_date <= date_to,
        )
        .group_by(models.SalShipmentItem.material_id)
        .order_by(models.SalShipmentItem.material_id)
    )
    return list(db.execute(stmt).all())


def order_status_counts(db: Session) -> dict:
    """按状态统计销售订单数量。"""
    stmt = (
        select(models.SalOrder.status, func.count())
        .select_from(models.SalOrder)
        .group_by(models.SalOrder.status)
    )
    return {status: count for status, count in db.execute(stmt).all()}


def pending_shipment_order_count(db: Session) -> int:
    """未发完的订单数：状态 CONFIRMED/IN_PROGRESS 且存在未交付行。"""
    stmt = (
        select(func.count(func.distinct(models.SalOrder.id)))
        .select_from(models.SalOrder)
        .join(models.SalOrderItem, models.SalOrderItem.order_id == models.SalOrder.id)
        .where(
            models.SalOrder.status.in_(["CONFIRMED", "IN_PROGRESS"]),
            models.SalOrderItem.quantity > models.SalOrderItem.delivered_qty,
        )
    )
    return db.scalar(stmt) or 0


# ==================== 跨模块契约专用查询（不提交事务） ====================


def open_order_demand_rows(db: Session, on_date: Optional[date] = None) -> List[Tuple]:
    """未交付需求行：状态 CONFIRMED/IN_PROGRESS 且未交付数量 > 0。"""
    stmt = (
        select(
            models.SalOrder.id,
            models.SalOrder.order_no,
            models.SalOrder.customer_id,
            models.SalOrderItem.material_id,
            models.SalOrderItem.quantity - models.SalOrderItem.delivered_qty,
            models.SalOrder.delivery_date,
        )
        .join(models.SalOrderItem, models.SalOrderItem.order_id == models.SalOrder.id)
        .where(
            models.SalOrder.status.in_(["CONFIRMED", "IN_PROGRESS"]),
            models.SalOrderItem.quantity - models.SalOrderItem.delivered_qty > 0,
        )
        .order_by(models.SalOrder.delivery_date, models.SalOrder.id)
    )
    if on_date is not None:
        stmt = stmt.where(models.SalOrder.delivery_date <= on_date)
    return list(db.execute(stmt).all())


def confirmed_forecast_rows(
    db: Session,
    month_from: Optional[str] = None,
    month_to: Optional[str] = None,
) -> List[Tuple]:
    """已确认预测行：状态 CONFIRMED，可按预测月份区间过滤（YYYY-MM 字符串比较）。"""
    stmt = select(
        models.SalForecast.id,
        models.SalForecast.forecast_no,
        models.SalForecast.material_id,
        models.SalForecast.forecast_qty,
        models.SalForecast.forecast_month,
    ).where(models.SalForecast.status == "CONFIRMED")
    if month_from:
        stmt = stmt.where(models.SalForecast.forecast_month >= month_from)
    if month_to:
        stmt = stmt.where(models.SalForecast.forecast_month <= month_to)
    stmt = stmt.order_by(models.SalForecast.forecast_month, models.SalForecast.id)
    return list(db.execute(stmt).all())


def open_order_qty(db: Session, material_id: int) -> Decimal:
    """某物料的未交付订单数量合计。"""
    stmt = (
        select(
            func.coalesce(
                func.sum(models.SalOrderItem.quantity - models.SalOrderItem.delivered_qty),
                0,
            )
        )
        .select_from(models.SalOrderItem)
        .join(models.SalOrder, models.SalOrder.id == models.SalOrderItem.order_id)
        .where(
            models.SalOrder.status.in_(["CONFIRMED", "IN_PROGRESS"]),
            models.SalOrderItem.material_id == material_id,
        )
    )
    value = db.scalar(stmt)
    return Decimal(str(value)) if value is not None else Decimal("0")