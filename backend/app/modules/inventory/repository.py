"""inventory 模块数据访问层。

只负责数据库读写与查询拼装，**不写业务规则**。
只允许被本模块的 `service.py` / `contract.py` 调用；其它模块禁止直接 import 本文件。
跨模块数据（物料、安全库存）通过 `system.contract` 获取，本层**不跨模块 JOIN**。
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.inventory import models


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


def _next_doc_no(db: Session, model, field, prefix: str) -> str:
    """按前缀生成流水号：`<prefix><4位序号>`（prefix 已含日期，故按前缀内计数）。"""
    total = (
        db.scalar(
            select(func.count()).select_from(model).where(field.like(f"{prefix}%"))
        )
        or 0
    )
    return f"{prefix}{total + 1:04d}"


# ==================== 仓库 ====================


def list_warehouses(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
):
    """分页查询仓库，支持编码/名称关键字与状态过滤。"""
    stmt = select(models.InvWarehouse).order_by(models.InvWarehouse.id.desc())
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                models.InvWarehouse.warehouse_code.like(like),
                models.InvWarehouse.warehouse_name.like(like),
            )
        )
    if status:
        stmt = stmt.where(models.InvWarehouse.status == status)
    return _paginate(db, stmt, page, page_size)


def get_warehouse(db: Session, warehouse_id: int) -> Optional[models.InvWarehouse]:
    return db.get(models.InvWarehouse, warehouse_id)


def get_warehouse_by_code(db: Session, warehouse_code: str) -> Optional[models.InvWarehouse]:
    return db.scalar(
        select(models.InvWarehouse).where(models.InvWarehouse.warehouse_code == warehouse_code)
    )


def add_warehouse(db: Session, warehouse: models.InvWarehouse) -> models.InvWarehouse:
    db.add(warehouse)
    db.flush()
    return warehouse


# ==================== 库存结存 ====================


def _balance_filter(warehouse_id: int, material_id: int):
    """构造结存桶的唯一键条件 `(warehouse_id, material_id)`。"""
    return [
        models.InvBalance.warehouse_id == warehouse_id,
        models.InvBalance.material_id == material_id,
    ]


def get_balance(db: Session, warehouse_id: int, material_id: int) -> Optional[models.InvBalance]:
    return db.scalar(select(models.InvBalance).where(*_balance_filter(warehouse_id, material_id)))


def get_balance_for_update(
    db: Session, warehouse_id: int, material_id: int
) -> Optional[models.InvBalance]:
    """加行锁读取结存（`SELECT ... FOR UPDATE`），供出库/移库在事务内复核可用量。"""
    return db.scalar(
        select(models.InvBalance)
        .where(*_balance_filter(warehouse_id, material_id))
        .with_for_update()
    )


def add_balance(db: Session, balance: models.InvBalance) -> models.InvBalance:
    db.add(balance)
    db.flush()
    return balance


def list_balances(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    material_ids: Optional[Sequence[int]] = None,
):
    """分页查询结存。`material_ids` 用于把跨模块的关键字检索结果收敛到本模块 SQL。"""
    stmt = select(models.InvBalance).order_by(models.InvBalance.id.desc())
    if material_id:
        stmt = stmt.where(models.InvBalance.material_id == material_id)
    if warehouse_id:
        stmt = stmt.where(models.InvBalance.warehouse_id == warehouse_id)
    if material_ids is not None:
        ids = [int(i) for i in material_ids]
        if not ids:
            return [], 0
        stmt = stmt.where(models.InvBalance.material_id.in_(ids))
    return _paginate(db, stmt, page, page_size)


def sum_quantity(
    db: Session, material_id: int, warehouse_id: Optional[int] = None
) -> Decimal:
    """某物料的现存数量合计（可选限制仓库）。"""
    stmt = select(func.coalesce(func.sum(models.InvBalance.quantity), 0)).where(
        models.InvBalance.material_id == material_id
    )
    if warehouse_id is not None:
        stmt = stmt.where(models.InvBalance.warehouse_id == warehouse_id)
    return Decimal(str(db.scalar(stmt) or 0))


def sum_available(
    db: Session, material_id: int, warehouse_id: Optional[int] = None
) -> Decimal:
    """某物料的可用量合计（现存量 - 锁定量，可选限制仓库）。"""
    expr = models.InvBalance.quantity - models.InvBalance.locked_quantity
    stmt = select(func.coalesce(func.sum(expr), 0)).where(
        models.InvBalance.material_id == material_id
    )
    if warehouse_id is not None:
        stmt = stmt.where(models.InvBalance.warehouse_id == warehouse_id)
    return Decimal(str(db.scalar(stmt) or 0))


def stock_snapshot(
    db: Session, material_ids: Sequence[int], warehouse_id: Optional[int] = None
) -> dict:
    """批量取现存量/可用量快照：`{material_id: {"on_hand": Decimal, "available": Decimal}}`。"""
    ids = [int(i) for i in material_ids]
    if not ids:
        return {}
    available_expr = models.InvBalance.quantity - models.InvBalance.locked_quantity
    stmt = (
        select(
            models.InvBalance.material_id,
            func.coalesce(func.sum(models.InvBalance.quantity), 0),
            func.coalesce(func.sum(available_expr), 0),
        )
        .where(models.InvBalance.material_id.in_(ids))
        .group_by(models.InvBalance.material_id)
    )
    if warehouse_id is not None:
        stmt = stmt.where(models.InvBalance.warehouse_id == warehouse_id)
    result: dict = {}
    for mid, on_hand, available in db.execute(stmt):
        result[int(mid)] = {
            "on_hand": Decimal(str(on_hand or 0)),
            "available": Decimal(str(available or 0)),
        }
    return result


def aggregate_by_material(
    db: Session, warehouse_id: Optional[int] = None
) -> List[Tuple[int, Decimal, Decimal]]:
    """按物料汇总现存量/可用量，供库存报表使用。"""
    available_expr = models.InvBalance.quantity - models.InvBalance.locked_quantity
    stmt = (
        select(
            models.InvBalance.material_id,
            func.coalesce(func.sum(models.InvBalance.quantity), 0),
            func.coalesce(func.sum(available_expr), 0),
        )
        .group_by(models.InvBalance.material_id)
        .order_by(models.InvBalance.material_id)
    )
    if warehouse_id is not None:
        stmt = stmt.where(models.InvBalance.warehouse_id == warehouse_id)
    return [
        (int(mid), Decimal(str(on_hand or 0)), Decimal(str(available or 0)))
        for mid, on_hand, available in db.execute(stmt)
    ]


# ==================== 库存流水 ====================


# ==================== 库存操作单（移库 / 盘点） ====================


def next_operation_no(db: Session, biz_date: date, op_type: str) -> str:
    """生成操作单号：移库 `TRF` + 日期 + 序号，盘点 `STK` + 日期 + 序号。"""
    prefix = f"{'TRF' if op_type == 'TRANSFER' else 'STK'}{biz_date.strftime('%Y%m%d')}"
    return _next_doc_no(db, models.InvStockOperation, models.InvStockOperation.operation_no, prefix)


def list_stock_operations(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    op_type: Optional[str] = None,
    status: Optional[str] = None,
    warehouse_id: Optional[int] = None,
):
    """分页查询库存操作单，可按类型 / 状态 / 仓库过滤。"""
    stmt = select(models.InvStockOperation).order_by(models.InvStockOperation.id.desc())
    if op_type:
        stmt = stmt.where(models.InvStockOperation.op_type == op_type)
    if status:
        stmt = stmt.where(models.InvStockOperation.status == status)
    if warehouse_id:
        stmt = stmt.where(
            or_(
                models.InvStockOperation.from_warehouse_id == warehouse_id,
                models.InvStockOperation.to_warehouse_id == warehouse_id,
                models.InvStockOperation.warehouse_id == warehouse_id,
            )
        )
    return _paginate(db, stmt, page, page_size)


def get_stock_operation(db: Session, operation_id: int) -> Optional[models.InvStockOperation]:
    return db.get(models.InvStockOperation, operation_id)


def get_operation_by_no(db: Session, operation_no: str) -> Optional[models.InvStockOperation]:
    return db.scalar(
        select(models.InvStockOperation).where(models.InvStockOperation.operation_no == operation_no)
    )


def add_stock_operation(
    db: Session, operation: models.InvStockOperation
) -> models.InvStockOperation:
    db.add(operation)
    db.flush()
    return operation


def add_operation_item(
    db: Session, item: models.InvStockOperationItem
) -> models.InvStockOperationItem:
    db.add(item)
    return item


def count_operations_by_type(db: Session, op_type: str) -> int:
    return count_where(db, models.InvStockOperation, models.InvStockOperation.op_type == op_type)


def aggregate_flow(
    db: Session, date_from: date, date_to: date
) -> List[Tuple[str, int, Decimal]]:
    """按操作类型 + 物料汇总库存变动数量（基于库存操作单）。

    移库按明细 quantity 汇总；盘点按明细 (actual_qty - book_qty) 差异汇总。
    """
    op = models.InvStockOperation
    item = models.InvStockOperationItem
    stmt = (
        select(
            op.op_type,
            item.material_id,
            func.coalesce(
                func.sum(
                    func.coalesce(item.quantity, 0)
                    + func.coalesce(item.actual_qty, 0)
                    - func.coalesce(item.book_qty, 0)
                ),
                0,
            ),
        )
        .select_from(item)
        .join(op, op.id == item.operation_id)
        .where(
            op.status == "COMPLETED",
            op.op_date >= date_from,
            op.op_date <= date_to,
        )
        .group_by(op.op_type, item.material_id)
        .order_by(op.op_type, item.material_id)
    )
    return [
        (str(op_type), int(mid), Decimal(str(total or 0)))
        for op_type, mid, total in db.execute(stmt)
    ]


# ==================== 补库需求 ====================


def next_replenishment_no(db: Session, biz_date: date) -> str:
    return _next_doc_no(
        db,
        models.InvReplenishmentRequest,
        models.InvReplenishmentRequest.request_no,
        f"RPL{biz_date.strftime('%Y%m%d')}",
    )


def list_replenishment_requests(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    material_id: Optional[int] = None,
):
    stmt = select(models.InvReplenishmentRequest).order_by(
        models.InvReplenishmentRequest.id.desc()
    )
    if status:
        stmt = stmt.where(models.InvReplenishmentRequest.status == status)
    if source_type:
        stmt = stmt.where(models.InvReplenishmentRequest.source_type == source_type)
    if material_id:
        stmt = stmt.where(models.InvReplenishmentRequest.material_id == material_id)
    return _paginate(db, stmt, page, page_size)


def get_replenishment_request(
    db: Session, request_id: int
) -> Optional[models.InvReplenishmentRequest]:
    return db.get(models.InvReplenishmentRequest, request_id)


def add_replenishment_request(
    db: Session, request: models.InvReplenishmentRequest
) -> models.InvReplenishmentRequest:
    db.add(request)
    db.flush()
    return request