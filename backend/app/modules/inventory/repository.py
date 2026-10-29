"""inventory 模块数据访问层。

只负责数据库读写与查询拼装，**不写业务规则**。
只允许被本模块的 `service.py` / `contract.py` 调用；其它模块禁止直接 import 本文件。
跨模块数据（物料、安全库存）通过 `system.contract` 获取，本层**不跨模块 JOIN**，
仅在需要按物料/仓库字段排序时才临时 JOIN system.models.SysMaterial。
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.modules.inventory import models
from app.modules.system.models import SysMaterial  # 仅用于排序时跨模块 JOIN

# 不计入可用量的仓库编码：废品仓内的物资已报废，仅作资产登记，
# 不参与可用量、安全库存判断与补库建议（现存量仍然照实记录）。
NON_AVAILABLE_WAREHOUSE_CODES: Tuple[str, ...] = ("WH-SCRAP-01",)


def _non_available_warehouse_ids():
    """废品仓等不计入可用量的仓库 ID 子查询。"""
    return select(models.InvWarehouse.id).where(
        models.InvWarehouse.warehouse_code.in_(NON_AVAILABLE_WAREHOUSE_CODES)
    )


def _available_expr():
    """可用量表达式：废品仓一律记 0（物资已报废，不能用于生产/销售）。"""
    return case(
        (models.InvBalance.warehouse_id.in_(_non_available_warehouse_ids()), 0),
        else_=models.InvBalance.quantity - models.InvBalance.locked_quantity,
    )


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


def warehouse_names(db: Session, warehouse_ids: Sequence[int]) -> Dict[int, Dict[str, str]]:
    """批量取仓库编码与名称，返回 `{warehouse_id: {"warehouse_code", "warehouse_name"}}`。"""
    ids = [int(i) for i in warehouse_ids if i]
    if not ids:
        return {}
    rows = db.scalars(
        select(models.InvWarehouse).where(models.InvWarehouse.id.in_(ids))
    )
    return {
        row.id: {"warehouse_code": row.warehouse_code, "warehouse_name": row.warehouse_name}
        for row in rows
    }


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
    has_reorder_point: bool = False,
    quantity_gt: Optional[Decimal] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
):
    """分页查询结存。`material_ids` 用于把跨模块的关键字检索结果收敛到本模块 SQL。

    sort_by 可选值：
      id / quantity / locked_qty / safety_stock / reorder_point /
      material_code / material_name / material_abc_class / material_sales_category /
      warehouse_name / warehouse_code /
      available_quantity（= quantity - locked_qty，后端计算字段）
    默认按 id desc（最新建的结存在前）。
    """
    stmt = select(models.InvBalance)
    if material_id:
        stmt = stmt.where(models.InvBalance.material_id == material_id)
    if warehouse_id:
        stmt = stmt.where(models.InvBalance.warehouse_id == warehouse_id)
    if has_reorder_point:
        stmt = stmt.where(models.InvBalance.reorder_point.is_not(None))
    if quantity_gt is not None:
        stmt = stmt.where(models.InvBalance.quantity > quantity_gt)
    if material_ids is not None:
        ids = [int(i) for i in material_ids]
        if not ids:
            return [], 0
        stmt = stmt.where(models.InvBalance.material_id.in_(ids))

    # --- 排序 ---
    asc = sort_order.lower() == "asc"
    B = models.InvBalance     # inv_balance
    W = models.InvWarehouse   # inv_warehouse（本模块）
    SM = SysMaterial          # sys_material（跨模块）
    direction = lambda col: col if asc else col.desc()

    # 需要联表的排序列
    _need_material_join = sort_by in (
        "material_code", "material_name", "material_abc_class",
        "material_sales_category", "safety_stock",
    )
    _need_warehouse_join = sort_by in ("warehouse_name", "warehouse_code")

    if sort_by is None:
        stmt = stmt.order_by(B.id.desc())
    elif _need_material_join or _need_warehouse_join:
        if _need_material_join:
            stmt = stmt.join(SM, SM.id == B.material_id)
        if _need_warehouse_join:
            stmt = stmt.join(W, W.id == B.warehouse_id)
        _ORDER_MAP = {
            "material_code": SM.material_code,
            "material_name": SM.material_name,
            "material_abc_class": SM.abc_class,
            "material_sales_category": SM.sales_category,
            "safety_stock": SM.safety_stock,
            "warehouse_name": W.warehouse_name,
            "warehouse_code": W.warehouse_code,
        }
        col = _ORDER_MAP.get(sort_by)
        if col is not None:
            stmt = stmt.order_by(direction(col), B.id)
        else:
            stmt = stmt.order_by(B.id.desc())
    elif sort_by == "available_quantity":
        available = (B.quantity - B.locked_quantity).label("available_quantity")
        stmt = stmt.order_by(direction(available), B.id)
    else:
        # InvBalance 自身字段
        _DIRECT_MAP = {
            "id": B.id,
            "quantity": B.quantity,
            "locked_quantity": B.locked_quantity,
            "reorder_point": B.reorder_point,
            "reorder_quantity": B.reorder_quantity,
        }
        col = _DIRECT_MAP.get(sort_by)
        if col is not None:
            stmt = stmt.order_by(direction(col), B.id)
        else:
            stmt = stmt.order_by(B.id.desc())

    return _paginate(db, stmt, page, page_size)


def balance_rows(
    db: Session,
    *,
    warehouse_id: Optional[int] = None,
    material_ids: Optional[Sequence[int]] = None,
) -> List[models.InvBalance]:
    """查询符合条件的全部结存行（不分页），用于按销售类别汇总。"""
    stmt = select(models.InvBalance)
    if warehouse_id:
        stmt = stmt.where(models.InvBalance.warehouse_id == warehouse_id)
    if material_ids is not None:
        ids = [int(i) for i in material_ids]
        if not ids:
            return []
        stmt = stmt.where(models.InvBalance.material_id.in_(ids))
    return list(db.scalars(stmt))


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
        models.InvBalance.material_id == material_id,
        models.InvBalance.warehouse_id.notin_(_non_available_warehouse_ids()),
    )
    if warehouse_id is not None:
        stmt = stmt.where(models.InvBalance.warehouse_id == warehouse_id)
    return Decimal(str(db.scalar(stmt) or 0))


def list_available_by_warehouse(db: Session, material_id: int) -> List[Tuple]:
    """某物料各仓库的可用量（现存量 - 锁定量 > 0），按可用量倒序、仓库ID升序。

    返回 `[(warehouse_id, quantity, available)]`，供销售订单确认时按仓库分配库存。
    """
    available_expr = models.InvBalance.quantity - models.InvBalance.locked_quantity
    stmt = (
        select(
            models.InvBalance.warehouse_id,
            models.InvBalance.quantity,
            available_expr,
        )
        .where(
            models.InvBalance.material_id == material_id,
            available_expr > 0,
            models.InvBalance.warehouse_id.notin_(_non_available_warehouse_ids()),
        )
        .order_by(available_expr.desc(), models.InvBalance.warehouse_id)
    )
    return list(db.execute(stmt).all())


def stock_snapshot(
    db: Session, material_ids: Sequence[int], warehouse_id: Optional[int] = None
) -> dict:
    """批量取现存量/可用量快照：`{material_id: {"on_hand": Decimal, "available": Decimal}}`。"""
    ids = [int(i) for i in material_ids]
    if not ids:
        return {}
    available_expr = _available_expr()
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
    """按物料汇总现存量/可用量，供库存报表使用（废品仓计入现存量、不计入可用量）。"""
    available_expr = _available_expr()
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


# ==================== 库存操作单（移库 / 盘点 / 入库 / 出库） ====================

#: 各单据类型对应的单号前缀
_OP_NO_PREFIX = {
    "TRANSFER": "TRF",
    "STOCKTAKE": "STK",
    "INBOUND": "INB",
    "OUTBOUND": "OUT",
}


def next_operation_no(db: Session, biz_date: date, op_type: str) -> str:
    """生成单据号：`前缀 + 日期 + 序号`（TRF 移库 / STK 盘点 / INB 入库 / OUT 出库）。"""
    prefix = f"{_OP_NO_PREFIX.get(op_type, 'OPS')}{biz_date.strftime('%Y%m%d')}"
    return _next_doc_no(db, models.InvStockOperation, models.InvStockOperation.operation_no, prefix)


def list_stock_operations(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    op_type: Optional[str] = None,
    status: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    source_module: Optional[str] = None,
    source_type: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """分页查询库存单据，可按类型 / 状态 / 仓库 / 来源过滤，`keyword` 匹配单号或来源单号。"""
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
    if source_module:
        stmt = stmt.where(models.InvStockOperation.source_module == source_module)
    if source_type:
        stmt = stmt.where(models.InvStockOperation.source_type == source_type)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                models.InvStockOperation.operation_no.like(like),
                models.InvStockOperation.source_no.like(like),
                models.InvStockOperation.remark.like(like),
            )
        )
    return _paginate(db, stmt, page, page_size)


def find_pending_by_source(
    db: Session, source_module: str, source_type: str, source_reference_id: int
) -> Optional[models.InvStockOperation]:
    """按来源单据查仍在待处理（DRAFT）的出入库单，用于重复推送去重。"""
    return db.scalar(
        select(models.InvStockOperation).where(
            models.InvStockOperation.source_module == source_module,
            models.InvStockOperation.source_type == source_type,
            models.InvStockOperation.source_reference_id == source_reference_id,
            models.InvStockOperation.status == "DRAFT",
        )
    )


def list_pending_by_source(
    db: Session, source_module: str, source_type: str, source_reference_id: int
) -> List[models.InvStockOperation]:
    """列出某来源单据下所有待处理的出入库单（取消 / 作废时批量撤销）。"""
    return list(
        db.scalars(
            select(models.InvStockOperation).where(
                models.InvStockOperation.source_module == source_module,
                models.InvStockOperation.source_type == source_type,
                models.InvStockOperation.source_reference_id == source_reference_id,
                models.InvStockOperation.status == "DRAFT",
            )
        ).all()
    )


def list_operations_by_sources(
    db: Session, sources: Sequence[Tuple[str, str, int]]
) -> List[models.InvStockOperation]:
    """按 `(module, type, reference_id)` 批量取单据（业务列表回填「库存单状态」用）。"""
    if not sources:
        return []
    conditions = [
        and_(
            models.InvStockOperation.source_module == module,
            models.InvStockOperation.source_type == source_type,
            models.InvStockOperation.source_reference_id == ref_id,
        )
        for module, source_type, ref_id in sources
    ]
    return list(db.scalars(select(models.InvStockOperation).where(or_(*conditions))).all())


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


# ==================== 库存流水（inv_stock_journal） ====================


def list_stock_journal(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    direction: Optional[str] = None,
    source_module: Optional[str] = None,
    source_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Tuple[List[models.InvStockJournal], int]:
    """分页查询库存变动流水。按 created_at / id 倒序。"""
    stmt = select(models.InvStockJournal).order_by(
        models.InvStockJournal.id.desc()
    )
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            (models.InvStockJournal.material_code.like(like))
            | (models.InvStockJournal.material_name.like(like))
            | (models.InvStockJournal.source_no.like(like))
        )
    if material_id:
        stmt = stmt.where(models.InvStockJournal.material_id == material_id)
    if warehouse_id:
        stmt = stmt.where(models.InvStockJournal.warehouse_id == warehouse_id)
    if direction:
        stmt = stmt.where(models.InvStockJournal.direction == direction)
    if source_module:
        stmt = stmt.where(models.InvStockJournal.source_module == source_module)
    if source_type:
        stmt = stmt.where(models.InvStockJournal.source_type == source_type)
    if date_from:
        stmt = stmt.where(models.InvStockJournal.op_date >= date_from)
    if date_to:
        stmt = stmt.where(models.InvStockJournal.op_date <= date_to)
    return _paginate(db, stmt, page, page_size)


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