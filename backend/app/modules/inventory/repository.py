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


# ==================== 库位 ====================


def list_locations(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    warehouse_id: Optional[int] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
):
    """分页查询库位，支持仓库过滤与编码/名称关键字。"""
    stmt = select(models.InvLocation).order_by(models.InvLocation.id.desc())
    if warehouse_id:
        stmt = stmt.where(models.InvLocation.warehouse_id == warehouse_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                models.InvLocation.location_code.like(like),
                models.InvLocation.location_name.like(like),
            )
        )
    if status:
        stmt = stmt.where(models.InvLocation.status == status)
    return _paginate(db, stmt, page, page_size)


def get_location(db: Session, location_id: int) -> Optional[models.InvLocation]:
    return db.get(models.InvLocation, location_id)


def get_location_by_code(
    db: Session, warehouse_id: int, location_code: str
) -> Optional[models.InvLocation]:
    return db.scalar(
        select(models.InvLocation).where(
            models.InvLocation.warehouse_id == warehouse_id,
            models.InvLocation.location_code == location_code,
        )
    )


def add_location(db: Session, location: models.InvLocation) -> models.InvLocation:
    db.add(location)
    db.flush()
    return location


def delete_location(db: Session, location: models.InvLocation) -> None:
    db.delete(location)


def count_balances_by_location(db: Session, location_id: int) -> int:
    """统计某库位下的结存记录数（删除库位前的引用校验）。"""
    return count_where(db, models.InvBalance, models.InvBalance.location_id == location_id)


# ==================== 库存结存 ====================


def _balance_filter(warehouse_id: int, location_id: Optional[int], material_id: int):
    """构造结存桶的唯一键条件（location_id 为 NULL 时要用 IS NULL）。"""
    criteria = [
        models.InvBalance.warehouse_id == warehouse_id,
        models.InvBalance.material_id == material_id,
    ]
    if location_id is None:
        criteria.append(models.InvBalance.location_id.is_(None))
    else:
        criteria.append(models.InvBalance.location_id == location_id)
    return criteria


def get_balance(
    db: Session, warehouse_id: int, location_id: Optional[int], material_id: int
) -> Optional[models.InvBalance]:
    return db.scalar(select(models.InvBalance).where(*_balance_filter(warehouse_id, location_id, material_id)))


def get_balance_for_update(
    db: Session, warehouse_id: int, location_id: Optional[int], material_id: int
) -> Optional[models.InvBalance]:
    """加行锁读取结存（`SELECT ... FOR UPDATE`），供出库/移库在事务内复核可用量。"""
    return db.scalar(
        select(models.InvBalance)
        .where(*_balance_filter(warehouse_id, location_id, material_id))
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


def next_txn_no(db: Session, biz_date: date) -> str:
    """生成流水单号：`INV` + yyyyMMdd + 4 位流水号。"""
    return _next_doc_no(
        db,
        models.InvTransaction,
        models.InvTransaction.transaction_no,
        f"INV{biz_date.strftime('%Y%m%d')}",
    )


def add_transaction(db: Session, txn: models.InvTransaction) -> models.InvTransaction:
    db.add(txn)
    return txn


def get_transaction(db: Session, txn_id: int) -> Optional[models.InvTransaction]:
    return db.get(models.InvTransaction, txn_id)


def list_transactions(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    transaction_type: Optional[str] = None,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    source_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    source_no: Optional[str] = None,
    material_ids: Optional[Sequence[int]] = None,
):
    """分页查询库存流水，支持按类型/物料/仓库/来源/日期/来源单号过滤。"""
    stmt = select(models.InvTransaction).order_by(models.InvTransaction.id.desc())
    if transaction_type:
        stmt = stmt.where(models.InvTransaction.transaction_type == transaction_type)
    if material_id:
        stmt = stmt.where(models.InvTransaction.material_id == material_id)
    if warehouse_id:
        stmt = stmt.where(models.InvTransaction.warehouse_id == warehouse_id)
    if source_type:
        stmt = stmt.where(models.InvTransaction.source_type == source_type)
    if date_from:
        stmt = stmt.where(models.InvTransaction.biz_date >= date_from)
    if date_to:
        stmt = stmt.where(models.InvTransaction.biz_date <= date_to)
    if source_no:
        stmt = stmt.where(models.InvTransaction.source_no.like(f"%{source_no}%"))
    if material_ids is not None:
        ids = [int(i) for i in material_ids]
        if not ids:
            return [], 0
        stmt = stmt.where(models.InvTransaction.material_id.in_(ids))
    return _paginate(db, stmt, page, page_size)


def aggregate_flow(
    db: Session, date_from: date, date_to: date
) -> List[Tuple[str, int, Decimal]]:
    """按流水类型 + 物料汇总出入库数量。"""
    stmt = (
        select(
            models.InvTransaction.transaction_type,
            models.InvTransaction.material_id,
            func.coalesce(func.sum(models.InvTransaction.quantity_change), 0),
        )
        .where(
            models.InvTransaction.biz_date >= date_from,
            models.InvTransaction.biz_date <= date_to,
        )
        .group_by(models.InvTransaction.transaction_type, models.InvTransaction.material_id)
        .order_by(models.InvTransaction.transaction_type, models.InvTransaction.material_id)
    )
    return [
        (str(txn_type), int(mid), Decimal(str(total or 0)))
        for txn_type, mid, total in db.execute(stmt)
    ]


# ==================== 移库 ====================


def next_transfer_no(db: Session, biz_date: date) -> str:
    return _next_doc_no(
        db,
        models.InvTransfer,
        models.InvTransfer.transfer_no,
        f"TRF{biz_date.strftime('%Y%m%d')}",
    )


def list_transfers(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    from_warehouse_id: Optional[int] = None,
):
    stmt = select(models.InvTransfer).order_by(models.InvTransfer.id.desc())
    if status:
        stmt = stmt.where(models.InvTransfer.status == status)
    if from_warehouse_id:
        stmt = stmt.where(models.InvTransfer.from_warehouse_id == from_warehouse_id)
    return _paginate(db, stmt, page, page_size)


def get_transfer(db: Session, transfer_id: int) -> Optional[models.InvTransfer]:
    return db.get(models.InvTransfer, transfer_id)


def get_transfer_by_no(db: Session, transfer_no: str) -> Optional[models.InvTransfer]:
    return db.scalar(
        select(models.InvTransfer).where(models.InvTransfer.transfer_no == transfer_no)
    )


def add_transfer(db: Session, transfer: models.InvTransfer) -> models.InvTransfer:
    db.add(transfer)
    db.flush()
    return transfer


def add_transfer_item(db: Session, item: models.InvTransferItem) -> models.InvTransferItem:
    db.add(item)
    return item


# ==================== 盘点 ====================


def next_stocktake_no(db: Session, biz_date: date) -> str:
    return _next_doc_no(
        db,
        models.InvStocktake,
        models.InvStocktake.stocktake_no,
        f"STK{biz_date.strftime('%Y%m%d')}",
    )


def list_stocktakes(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    warehouse_id: Optional[int] = None,
    status: Optional[str] = None,
):
    stmt = select(models.InvStocktake).order_by(models.InvStocktake.id.desc())
    if warehouse_id:
        stmt = stmt.where(models.InvStocktake.warehouse_id == warehouse_id)
    if status:
        stmt = stmt.where(models.InvStocktake.status == status)
    return _paginate(db, stmt, page, page_size)


def get_stocktake(db: Session, stocktake_id: int) -> Optional[models.InvStocktake]:
    return db.get(models.InvStocktake, stocktake_id)


def get_stocktake_by_no(db: Session, stocktake_no: str) -> Optional[models.InvStocktake]:
    return db.scalar(
        select(models.InvStocktake).where(models.InvStocktake.stocktake_no == stocktake_no)
    )


def add_stocktake(db: Session, stocktake: models.InvStocktake) -> models.InvStocktake:
    db.add(stocktake)
    db.flush()
    return stocktake


def add_stocktake_item(
    db: Session, item: models.InvStocktakeItem
) -> models.InvStocktakeItem:
    db.add(item)
    return item


# ==================== 订货点规则 ====================


def list_reorder_rules(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
):
    stmt = select(models.InvReorderRule).order_by(models.InvReorderRule.id.desc())
    if status:
        stmt = stmt.where(models.InvReorderRule.status == status)
    if material_id:
        stmt = stmt.where(models.InvReorderRule.material_id == material_id)
    if warehouse_id:
        stmt = stmt.where(models.InvReorderRule.warehouse_id == warehouse_id)
    return _paginate(db, stmt, page, page_size)


def list_active_reorder_rules(db: Session) -> List[models.InvReorderRule]:
    return list(
        db.scalars(
            select(models.InvReorderRule)
            .where(models.InvReorderRule.status == "ACTIVE")
            .order_by(models.InvReorderRule.id)
        )
    )


def get_reorder_rule(db: Session, rule_id: int) -> Optional[models.InvReorderRule]:
    return db.get(models.InvReorderRule, rule_id)


def get_reorder_rule_by_pair(
    db: Session, material_id: int, warehouse_id: int
) -> Optional[models.InvReorderRule]:
    return db.scalar(
        select(models.InvReorderRule).where(
            models.InvReorderRule.material_id == material_id,
            models.InvReorderRule.warehouse_id == warehouse_id,
        )
    )


def add_reorder_rule(db: Session, rule: models.InvReorderRule) -> models.InvReorderRule:
    db.add(rule)
    db.flush()
    return rule


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