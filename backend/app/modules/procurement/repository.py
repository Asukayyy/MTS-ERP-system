"""procurement 模块数据访问层。

约定（规格 §24 / §35）：

- 只做数据库读写与查询拼装，**不写业务规则**。
- 只允许被本模块的 `service.py` / `contract.py` 调用；其它模块禁止直接 import 本文件。
- 跨模块数据（物料、人员、库存）通过对方 Contract 获取，本层**不跨模块 JOIN**，
  只 JOIN 本模块自己的表（`pur_*`）。

错误码区段：`4000~4999`（定义在 `service.py`）。
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.procurement import models

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
        db.scalar(select(func.count()).select_from(model).where(field.like(f"{prefix}%"))) or 0
    )
    return f"{prefix}{total + 1:04d}"


def status_counts(db: Session, model) -> Dict[str, int]:
    """按状态分组统计数量。"""
    stmt = select(model.status, func.count()).select_from(model).group_by(model.status)
    return {status: count for status, count in db.execute(stmt).all()}


# ==================== 供应商 ====================


def list_suppliers(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
):
    """分页查询供应商，支持编码/名称关键字与状态过滤。"""
    stmt = select(models.PurSupplier).order_by(models.PurSupplier.id.desc())
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                models.PurSupplier.supplier_code.like(like),
                models.PurSupplier.supplier_name.like(like),
            )
        )
    if status:
        stmt = stmt.where(models.PurSupplier.status == status)
    return _paginate(db, stmt, page, page_size)


def get_supplier(db: Session, supplier_id: int) -> Optional[models.PurSupplier]:
    return db.get(models.PurSupplier, supplier_id)


def get_supplier_by_code(db: Session, supplier_code: str) -> Optional[models.PurSupplier]:
    return db.scalar(
        select(models.PurSupplier).where(models.PurSupplier.supplier_code == supplier_code)
    )


def get_suppliers(db: Session, supplier_ids: Sequence[int]) -> Dict[int, models.PurSupplier]:
    """批量取供应商 `{supplier_id: PurSupplier}`，供列表 / 报表补名称。"""
    ids = [int(i) for i in supplier_ids if i]
    if not ids:
        return {}
    rows = db.scalars(select(models.PurSupplier).where(models.PurSupplier.id.in_(ids)))
    return {row.id: row for row in rows}


def add_supplier(db: Session, supplier: models.PurSupplier) -> models.PurSupplier:
    db.add(supplier)
    db.flush()
    return supplier


# ==================== 供应商-物料关系 ====================


def list_supplier_materials(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    supplier_id: Optional[int] = None,
    material_id: Optional[int] = None,
):
    stmt = select(models.PurSupplierMaterial).order_by(models.PurSupplierMaterial.id.desc())
    if supplier_id:
        stmt = stmt.where(models.PurSupplierMaterial.supplier_id == supplier_id)
    if material_id:
        stmt = stmt.where(models.PurSupplierMaterial.material_id == material_id)
    return _paginate(db, stmt, page, page_size)


def get_supplier_material(
    db: Session, link_id: int
) -> Optional[models.PurSupplierMaterial]:
    return db.get(models.PurSupplierMaterial, link_id)


def get_supplier_material_by_pair(
    db: Session, supplier_id: int, material_id: int
) -> Optional[models.PurSupplierMaterial]:
    return db.scalar(
        select(models.PurSupplierMaterial).where(
            models.PurSupplierMaterial.supplier_id == supplier_id,
            models.PurSupplierMaterial.material_id == material_id,
        )
    )


def add_supplier_material(
    db: Session, link: models.PurSupplierMaterial
) -> models.PurSupplierMaterial:
    db.add(link)
    db.flush()
    return link


def delete_supplier_material(db: Session, link: models.PurSupplierMaterial) -> None:
    db.delete(link)


def supplier_material_terms(
    db: Session, supplier_id: int, material_ids: Sequence[int]
) -> Dict[int, models.PurSupplierMaterial]:
    """取某供应商对一批物料的供货条款 `{material_id: PurSupplierMaterial}`。"""
    ids = [int(i) for i in material_ids if i]
    if not ids:
        return {}
    rows = db.scalars(
        select(models.PurSupplierMaterial).where(
            models.PurSupplierMaterial.supplier_id == supplier_id,
            models.PurSupplierMaterial.material_id.in_(ids),
        )
    )
    return {row.material_id: row for row in rows}


# ==================== 采购计划 ====================


def list_plans(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    keyword: Optional[str] = None,
):
    stmt = select(models.PurPurchasePlan).order_by(models.PurPurchasePlan.id.desc())
    if status:
        stmt = stmt.where(models.PurPurchasePlan.status == status)
    if date_from:
        stmt = stmt.where(models.PurPurchasePlan.plan_date >= date_from)
    if date_to:
        stmt = stmt.where(models.PurPurchasePlan.plan_date <= date_to)
    if keyword:
        stmt = stmt.where(models.PurPurchasePlan.plan_no.like(f"%{keyword}%"))
    return _paginate(db, stmt, page, page_size)


def get_plan(db: Session, plan_id: int) -> Optional[models.PurPurchasePlan]:
    return db.get(models.PurPurchasePlan, plan_id)


def get_plan_by_no(db: Session, plan_no: str) -> Optional[models.PurPurchasePlan]:
    return db.scalar(
        select(models.PurPurchasePlan).where(models.PurPurchasePlan.plan_no == plan_no)
    )


def add_plan(db: Session, plan: models.PurPurchasePlan) -> models.PurPurchasePlan:
    db.add(plan)
    db.flush()
    return plan


def add_plan_item(
    db: Session, item: models.PurPurchasePlanItem
) -> models.PurPurchasePlanItem:
    db.add(item)
    db.flush()
    return item


def get_plan_items(db: Session, plan_id: int) -> List[models.PurPurchasePlanItem]:
    return list(
        db.scalars(
            select(models.PurPurchasePlanItem)
            .where(models.PurPurchasePlanItem.plan_id == plan_id)
            .order_by(models.PurPurchasePlanItem.id)
        )
    )


def get_plan_item(db: Session, item_id: int) -> Optional[models.PurPurchasePlanItem]:
    return db.get(models.PurPurchasePlanItem, item_id)


def delete_plan_items(db: Session, plan_id: int) -> None:
    for item in get_plan_items(db, plan_id):
        db.delete(item)


def delete_plan(db: Session, plan: models.PurPurchasePlan) -> None:
    db.delete(plan)


def find_plan_items_by_source(
    db: Session, source_type: str, reference_ids: Sequence[int]
) -> List[models.PurPurchasePlanItem]:
    """按来源类型 + 来源单据ID批量查计划行，用于契约生成时的幂等判重。"""
    ids = [int(i) for i in reference_ids if i]
    if not ids:
        return []
    return list(
        db.scalars(
            select(models.PurPurchasePlanItem).where(
                models.PurPurchasePlanItem.source_type == source_type,
                models.PurPurchasePlanItem.source_reference_id.in_(ids),
            )
        )
    )


# ==================== 采购订单 ====================


def list_orders(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    keyword: Optional[str] = None,
):
    stmt = select(models.PurOrder).order_by(models.PurOrder.id.desc())
    if supplier_id:
        stmt = stmt.where(models.PurOrder.supplier_id == supplier_id)
    if status:
        stmt = stmt.where(models.PurOrder.status == status)
    if date_from:
        stmt = stmt.where(models.PurOrder.order_date >= date_from)
    if date_to:
        stmt = stmt.where(models.PurOrder.order_date <= date_to)
    if keyword:
        stmt = stmt.where(models.PurOrder.order_no.like(f"%{keyword}%"))
    return _paginate(db, stmt, page, page_size)


def get_order(db: Session, order_id: int) -> Optional[models.PurOrder]:
    return db.get(models.PurOrder, order_id)


def get_order_by_no(db: Session, order_no: str) -> Optional[models.PurOrder]:
    return db.scalar(select(models.PurOrder).where(models.PurOrder.order_no == order_no))


def get_orders(db: Session, order_ids: Sequence[int]) -> Dict[int, models.PurOrder]:
    """批量取订单 `{order_id: PurOrder}`。"""
    ids = [int(i) for i in order_ids if i]
    if not ids:
        return {}
    rows = db.scalars(select(models.PurOrder).where(models.PurOrder.id.in_(ids)))
    return {row.id: row for row in rows}


def add_order(db: Session, order: models.PurOrder) -> models.PurOrder:
    db.add(order)
    db.flush()
    return order


def add_order_item(db: Session, item: models.PurOrderItem) -> models.PurOrderItem:
    db.add(item)
    db.flush()
    return item


def get_order_item(db: Session, item_id: int) -> Optional[models.PurOrderItem]:
    return db.get(models.PurOrderItem, item_id)


def get_order_items(db: Session, order_id: int) -> List[models.PurOrderItem]:
    return list(
        db.scalars(
            select(models.PurOrderItem)
            .where(models.PurOrderItem.order_id == order_id)
            .order_by(models.PurOrderItem.line_no)
        )
    )


def delete_order_items(db: Session, order_id: int) -> None:
    for item in get_order_items(db, order_id):
        db.delete(item)


def delete_order(db: Session, order: models.PurOrder) -> None:
    db.delete(order)


def received_qty_sum(db: Session, order_id: int) -> Tuple[Decimal, Decimal]:
    """返回某订单的 (采购总量, 已到货总量)。"""
    row = db.execute(
        select(
            func.coalesce(func.sum(models.PurOrderItem.quantity), 0),
            func.coalesce(func.sum(models.PurOrderItem.received_qty), 0),
        )
        .select_from(models.PurOrderItem)
        .where(models.PurOrderItem.order_id == order_id)
    ).one()
    return Decimal(str(row[0])), Decimal(str(row[1]))


# ==================== 到货登记 ====================


def list_receipts(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    purchase_order_id: Optional[int] = None,
    status: Optional[str] = None,
):
    stmt = select(models.PurReceipt).order_by(models.PurReceipt.id.desc())
    if purchase_order_id:
        stmt = stmt.where(models.PurReceipt.purchase_order_id == purchase_order_id)
    if status:
        stmt = stmt.where(models.PurReceipt.status == status)
    return _paginate(db, stmt, page, page_size)


def get_receipt(db: Session, receipt_id: int) -> Optional[models.PurReceipt]:
    return db.get(models.PurReceipt, receipt_id)


def get_receipt_by_no(db: Session, receipt_no: str) -> Optional[models.PurReceipt]:
    return db.scalar(
        select(models.PurReceipt).where(models.PurReceipt.receipt_no == receipt_no)
    )


def add_receipt(db: Session, receipt: models.PurReceipt) -> models.PurReceipt:
    db.add(receipt)
    db.flush()
    return receipt


def add_receipt_item(db: Session, item: models.PurReceiptItem) -> models.PurReceiptItem:
    db.add(item)
    db.flush()
    return item


def get_receipt_items(db: Session, receipt_id: int) -> List[models.PurReceiptItem]:
    return list(
        db.scalars(
            select(models.PurReceiptItem)
            .where(models.PurReceiptItem.receipt_id == receipt_id)
            .order_by(models.PurReceiptItem.id)
        )
    )


# ==================== 供应商评价 ====================


def list_evaluations(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    supplier_id: Optional[int] = None,
):
    stmt = select(models.PurSupplierEvaluation).order_by(
        models.PurSupplierEvaluation.id.desc()
    )
    if supplier_id:
        stmt = stmt.where(models.PurSupplierEvaluation.supplier_id == supplier_id)
    return _paginate(db, stmt, page, page_size)


def get_evaluation(db: Session, evaluation_id: int) -> Optional[models.PurSupplierEvaluation]:
    return db.get(models.PurSupplierEvaluation, evaluation_id)


def get_evaluations_by_supplier(
    db: Session, supplier_id: int
) -> List[models.PurSupplierEvaluation]:
    return list(
        db.scalars(
            select(models.PurSupplierEvaluation)
            .where(models.PurSupplierEvaluation.supplier_id == supplier_id)
            .order_by(models.PurSupplierEvaluation.evaluate_date.desc())
        )
    )


def add_evaluation(
    db: Session, evaluation: models.PurSupplierEvaluation
) -> models.PurSupplierEvaluation:
    db.add(evaluation)
    db.flush()
    return evaluation


def delete_evaluation(db: Session, evaluation: models.PurSupplierEvaluation) -> None:
    db.delete(evaluation)


def evaluation_summary_rows(db: Session) -> List[Tuple]:
    """按供应商汇总评价：供应商ID、评价次数、平均综合分、平均质量/交期/价格分。"""
    stmt = (
        select(
            models.PurSupplierEvaluation.supplier_id,
            func.count(),
            func.avg(models.PurSupplierEvaluation.total_score),
            func.avg(models.PurSupplierEvaluation.quality_score),
            func.avg(models.PurSupplierEvaluation.delivery_score),
            func.avg(models.PurSupplierEvaluation.price_score),
        )
        .group_by(models.PurSupplierEvaluation.supplier_id)
        .order_by(models.PurSupplierEvaluation.supplier_id)
    )
    return list(db.execute(stmt).all())


# ==================== 报表 / 统计 ====================


def plan_report_rows(db: Session) -> List[Tuple]:
    """采购计划及其执行：计划行级，含需求数量与已下单数量。"""
    stmt = (
        select(
            models.PurPurchasePlan.id,
            models.PurPurchasePlan.plan_no,
            models.PurPurchasePlan.plan_date,
            models.PurPurchasePlan.status,
            models.PurPurchasePlanItem.material_id,
            models.PurPurchasePlanItem.required_qty,
            models.PurPurchasePlanItem.ordered_qty,
            models.PurPurchasePlanItem.required_date,
            models.PurPurchasePlanItem.source_type,
        )
        .join(
            models.PurPurchasePlanItem,
            models.PurPurchasePlanItem.plan_id == models.PurPurchasePlan.id,
        )
        .order_by(models.PurPurchasePlan.id.desc(), models.PurPurchasePlanItem.id)
    )
    return list(db.execute(stmt).all())


def order_report_rows(db: Session) -> List[Tuple]:
    """采购订单及到货进度：订单行级。"""
    stmt = (
        select(
            models.PurOrder.id,
            models.PurOrder.order_no,
            models.PurOrder.supplier_id,
            models.PurOrder.order_date,
            models.PurOrder.expected_date,
            models.PurOrder.status,
            models.PurOrderItem.material_id,
            models.PurOrderItem.quantity,
            models.PurOrderItem.received_qty,
            models.PurOrderItem.unit_price,
            models.PurOrderItem.amount,
        )
        .join(models.PurOrderItem, models.PurOrderItem.order_id == models.PurOrder.id)
        .order_by(models.PurOrder.id.desc(), models.PurOrderItem.line_no)
    )
    return list(db.execute(stmt).all())


def receipt_report_rows(db: Session, date_from: date, date_to: date) -> List[Tuple]:
    """到货记录（行级），按到货日期区间查询。"""
    stmt = (
        select(
            models.PurReceipt.id,
            models.PurReceipt.receipt_no,
            models.PurReceipt.receipt_date,
            models.PurReceipt.status,
            models.PurOrder.order_no,
            models.PurReceipt.supplier_id,
            models.PurReceiptItem.material_id,
            models.PurReceiptItem.warehouse_id,
            models.PurReceiptItem.location_id,
            models.PurReceiptItem.quantity,
            models.PurReceiptItem.qualified_qty,
        )
        .join(models.PurReceiptItem, models.PurReceiptItem.receipt_id == models.PurReceipt.id)
        .join(models.PurOrder, models.PurOrder.id == models.PurReceipt.purchase_order_id)
        .where(
            models.PurReceipt.receipt_date >= date_from,
            models.PurReceipt.receipt_date <= date_to,
        )
        .order_by(models.PurReceipt.id.desc(), models.PurReceiptItem.id)
    )
    return list(db.execute(stmt).all())


def pending_receipt_rows(db: Session) -> List[Tuple]:
    """未到货采购订单行：`received_qty < quantity` 且订单处于在途状态。"""
    stmt = (
        select(
            models.PurOrder.id,
            models.PurOrder.order_no,
            models.PurOrder.supplier_id,
            models.PurOrder.expected_date,
            models.PurOrder.status,
            models.PurOrderItem.id,
            models.PurOrderItem.material_id,
            models.PurOrderItem.quantity,
            models.PurOrderItem.received_qty,
        )
        .join(models.PurOrderItem, models.PurOrderItem.order_id == models.PurOrder.id)
        .where(
            models.PurOrder.status.in_(["CONFIRMED", "RELEASED", "IN_PROGRESS"]),
            models.PurOrderItem.received_qty < models.PurOrderItem.quantity,
        )
        .order_by(models.PurOrder.expected_date, models.PurOrder.id)
    )
    return list(db.execute(stmt).all())


def pending_receipt_qty(db: Session, material_id: int) -> Decimal:
    """某物料所有在途未到货采购订单行的剩余数量合计。"""
    value = db.scalar(
        select(
            func.coalesce(
                func.sum(models.PurOrderItem.quantity - models.PurOrderItem.received_qty), 0
            )
        )
        .select_from(models.PurOrderItem)
        .join(models.PurOrder, models.PurOrder.id == models.PurOrderItem.order_id)
        .where(
            models.PurOrderItem.material_id == material_id,
            models.PurOrder.status.in_(["CONFIRMED", "RELEASED", "IN_PROGRESS"]),
            models.PurOrderItem.received_qty < models.PurOrderItem.quantity,
        )
    )
    return Decimal(str(value)) if value is not None else Decimal("0")


def pending_receipt_line_count(db: Session) -> int:
    """未到货订单行数。"""
    return (
        db.scalar(
            select(func.count())
            .select_from(models.PurOrderItem)
            .join(models.PurOrder, models.PurOrder.id == models.PurOrderItem.order_id)
            .where(
                models.PurOrder.status.in_(["CONFIRMED", "RELEASED", "IN_PROGRESS"]),
                models.PurOrderItem.received_qty < models.PurOrderItem.quantity,
            )
        )
        or 0
    )