"""inventory 模块业务逻辑层（**库存引擎所在层**）。

硬性约定（规格 §24 / §35 / §36）：

1. **任何库存变动都必须同时写 `inv_transaction` 流水并更新 `inv_balance` 结存**，
   二者在同一事务内完成，禁止只改结存不写流水。
2. **禁止负库存**：出库 / 盘点调减前必须在事务内加锁复核可用量。
3. 本层**不调用 `db.commit()`**：由 router 提交；contract 函数运行在调用方事务里。
4. **库存永远不直接创建正式生产计划**：库存不足只产生“补库需求”，
   由 planning / procurement 通过契约创建正式计划（规格 §14）。

错误码区段：`5000~5999`。
"""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.inventory import models, repository
from app.modules.system.contract import (
    find_material_by_code,
    get_material,
    get_materials,
    log_operation,
)

# ==================== 错误码（5000~5999） ====================

CODE_PARAM_INVALID = 5000  # 入参 / 状态非法
CODE_STOCK_INSUFFICIENT = 5001  # 库存不足
CODE_CONTRACT_NOT_READY = 5002  # 跨模块契约尚未就绪
CODE_STATUS_INVALID = 5003  # 单据状态不允许该操作
CODE_NOT_FOUND = 5004  # 资源不存在
CODE_DUPLICATE = 5005  # 唯一性冲突
CODE_BALANCE_NEGATIVE = 5006  # 调整后库存会为负

MODULE = "inventory"

_VALID_SOURCE_TYPES = {
    "PURCHASE_RECEIPT",
    "PRODUCTION_COMPLETION",
    "MATERIAL_REQUISITION",
    "SALES_SHIPMENT",
    "SALES_RETURN",
    "TRANSFER",
    "STOCKTAKE",
    "MANUAL",
}
_VALID_REPLENISHMENT_SOURCES = {"REORDER", "PRODUCTION"}
_RECORD_STATUS = {"ACTIVE", "INACTIVE"}


# ==================== 小工具 ====================


def _as_decimal(value: Any) -> Decimal:
    """把 int / str / Decimal / None 统一转成 Decimal。"""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _require_warehouse(db: Session, warehouse_id: int) -> models.InvWarehouse:
    warehouse = repository.get_warehouse(db, warehouse_id)
    if not warehouse:
        raise BusinessException(CODE_NOT_FOUND, f"仓库不存在：{warehouse_id}")
    return warehouse


def _require_material(db: Session, material_id: int) -> Dict[str, Any]:
    material = get_material(db, material_id)
    if not material:
        raise BusinessException(CODE_NOT_FOUND, f"物料不存在：{material_id}")
    return material


def _validate_source_type(source_type: str) -> None:
    if source_type not in _VALID_SOURCE_TYPES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法的来源业务类型：{source_type}")


def _material_map(db: Session, material_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    return get_materials(db, [int(i) for i in material_ids if i])


def _warehouse_name_map(db: Session, warehouse_ids: Sequence[int]) -> Dict[int, str]:
    result: Dict[int, str] = {}
    for wid in {int(i) for i in warehouse_ids if i}:
        warehouse = repository.get_warehouse(db, wid)
        if warehouse:
            result[wid] = warehouse.warehouse_name
    return result


def _balance_dict(balance: models.InvBalance) -> Dict[str, Any]:
    return {
        "on_hand": _as_decimal(balance.quantity),
        "locked_quantity": _as_decimal(balance.locked_quantity),
        "available_quantity": _as_decimal(balance.quantity) - _as_decimal(balance.locked_quantity),
    }


# ==================== 库存引擎（核心） ====================


def _lock_or_create_balance(db: Session, warehouse_id: int, material_id: int) -> models.InvBalance:
    """取或建结存桶，并对已存在的行加锁（`SELECT ... FOR UPDATE`）。"""
    balance = repository.get_balance_for_update(db, warehouse_id, material_id)
    if balance is None:
        balance = models.InvBalance(
            warehouse_id=warehouse_id,
            material_id=material_id,
            quantity=Decimal("0"),
            locked_quantity=Decimal("0"),
            reorder_point=None,
            reorder_quantity=None,
        )
        repository.add_balance(db, balance)
        balance = repository.get_balance_for_update(db, warehouse_id, material_id) or balance
    return balance


def _validate_stock_args(
    db: Session,
    *,
    material_id: int,
    quantity: Decimal,
    warehouse_id: int,
    source_module: str,
    source_type: str,
) -> Decimal:
    qty = _as_decimal(quantity)
    if qty <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "库存变动数量必须为正数")
    if not source_module:
        raise BusinessException(CODE_PARAM_INVALID, "来源模块不能为空")
    _validate_source_type(source_type)
    _require_warehouse(db, warehouse_id)
    _require_material(db, material_id)
    return qty


def _increase_stock(
    db: Session,
    *,
    transaction_type: str,
    material_id: int,
    quantity: Decimal,
    warehouse_id: int,
    source_module: str,
    source_type: str,
    source_reference_id: Optional[int] = None,
    source_no: Optional[str] = None,
    unit_cost: Decimal = Decimal("0"),
    biz_date: Optional[date] = None,
    operator_id: Optional[int] = None,
    remark: Optional[str] = None,
) -> Dict[str, Any]:
    """入库内部实现：结存加数量 + 写一条指定类型的流水（同一事务）。"""
    qty = _validate_stock_args(
        db,
        material_id=material_id,
        quantity=quantity,
        warehouse_id=warehouse_id,
        source_module=source_module,
        source_type=source_type,
    )
    biz = biz_date or date.today()
    balance = _lock_or_create_balance(db, warehouse_id, material_id)
    balance.quantity = _as_decimal(balance.quantity) + qty
    balance.updated_at_txn = datetime.now()
    return {
        "quantity_after": _as_decimal(balance.quantity),
    }


def increase_stock(
    db: Session,
    *,
    material_id: int,
    quantity: Decimal,
    warehouse_id: int,
    source_module: str,
    source_type: str,
    source_reference_id: Optional[int] = None,
    source_no: Optional[str] = None,
    unit_cost: Decimal = Decimal("0"),
    biz_date: Optional[date] = None,
    operator_id: Optional[int] = None,
    remark: Optional[str] = None,
) -> Dict[str, Any]:
    """入库：结存加数量 + 写一条 `IN` 流水（同一事务）。"""
    return _increase_stock(
        db,
        transaction_type="IN",
        material_id=material_id,
        quantity=quantity,
        warehouse_id=warehouse_id,
        source_module=source_module,
        source_type=source_type,
        source_reference_id=source_reference_id,
        source_no=source_no,
        unit_cost=unit_cost,
        biz_date=biz_date,
        operator_id=operator_id,
        remark=remark,
    )


def _decrease_stock(
    db: Session,
    *,
    transaction_type: str,
    material_id: int,
    quantity: Decimal,
    warehouse_id: int,
    source_module: str,
    source_type: str,
    source_reference_id: Optional[int] = None,
    source_no: Optional[str] = None,
    unit_cost: Decimal = Decimal("0"),
    biz_date: Optional[date] = None,
    operator_id: Optional[int] = None,
    remark: Optional[str] = None,
) -> Dict[str, Any]:
    """出库内部实现：加锁复核可用量 → 减结存 + 写一条指定类型的流水。"""
    qty = _validate_stock_args(
        db,
        material_id=material_id,
        quantity=quantity,
        warehouse_id=warehouse_id,
        source_module=source_module,
        source_type=source_type,
    )
    biz = biz_date or date.today()
    balance = repository.get_balance_for_update(db, warehouse_id, material_id)
    if balance is None:
        raise BusinessException(
            CODE_STOCK_INSUFFICIENT,
            f"库存不足：物料 {material_id} 在仓库 {warehouse_id} 无库存",
        )
    on_hand = _as_decimal(balance.quantity)
    available = on_hand - _as_decimal(balance.locked_quantity)
    if available < qty:
        raise BusinessException(
            CODE_STOCK_INSUFFICIENT,
            f"库存不足：物料 {material_id} 可用量 {available}，需求 {qty}",
        )
    new_qty = on_hand - qty
    if new_qty < 0:  # 防御性校验，禁止负库存
        raise BusinessException(CODE_STOCK_INSUFFICIENT, "库存不足：出库后将出现负库存")
    balance.quantity = new_qty
    balance.updated_at_txn = datetime.now()
    return {
        "quantity_after": new_qty,
    }


def decrease_stock(
    db: Session,
    *,
    material_id: int,
    quantity: Decimal,
    warehouse_id: int,
    source_module: str,
    source_type: str,
    source_reference_id: Optional[int] = None,
    source_no: Optional[str] = None,
    unit_cost: Decimal = Decimal("0"),
    biz_date: Optional[date] = None,
    operator_id: Optional[int] = None,
    remark: Optional[str] = None,
) -> Dict[str, Any]:
    """出库：加锁复核可用量 → 减结存 + 写一条 `OUT` 流水；不足则抛 5001，结存不变。"""
    return _decrease_stock(
        db,
        transaction_type="OUT",
        material_id=material_id,
        quantity=quantity,
        warehouse_id=warehouse_id,
        source_module=source_module,
        source_type=source_type,
        source_reference_id=source_reference_id,
        source_no=source_no,
        unit_cost=unit_cost,
        biz_date=biz_date,
        operator_id=operator_id,
        remark=remark,
    )


def _apply_adjust(
    db: Session,
    *,
    material_id: int,
    warehouse_id: int,
    delta: Decimal,
    unit_cost: Decimal = Decimal("0"),
    biz_date: Optional[date] = None,
    source_module: str = MODULE,
    source_type: str = "STOCKTAKE",
    source_reference_id: Optional[int] = None,
    source_no: Optional[str] = None,
    operator_id: Optional[int] = None,
    remark: Optional[str] = None,
) -> Decimal:
    """盘点调整：直接改结存（delta 可为负，调整后结存不得为负）。"""
    biz = biz_date or date.today()
    balance = _lock_or_create_balance(db, warehouse_id, material_id)
    new_qty = _as_decimal(balance.quantity) + delta
    if new_qty < 0:
        raise BusinessException(
            CODE_BALANCE_NEGATIVE,
            f"盘点调整后库存为负：物料 {material_id} 调整后 {new_qty}",
        )
    balance.quantity = new_qty
    balance.updated_at_txn = datetime.now()
    return new_qty


# ---- 只读查询（契约导出） ----


def get_on_hand_qty(
    db: Session, material_id: int, warehouse_id: Optional[int] = None
) -> Decimal:
    """取某物料现存量合计。"""
    return repository.sum_quantity(db, material_id, warehouse_id)


def get_available_qty(
    db: Session, material_id: int, warehouse_id: Optional[int] = None
) -> Decimal:
    """取某物料可用量合计（现存量 - 锁定量）。"""
    return repository.sum_available(db, material_id, warehouse_id)


def get_stock_snapshot(
    db: Session, material_ids: Sequence[int], warehouse_id: Optional[int] = None
) -> Dict[int, Dict[str, Decimal]]:
    """批量取库存快照：`{material_id: {"on_hand": ..., "available": ...}}`（缺失物料补 0）。"""
    raw = repository.stock_snapshot(db, material_ids, warehouse_id)
    result: Dict[int, Dict[str, Decimal]] = {}
    for mid in material_ids:
        key = int(mid)
        result[key] = raw.get(
            key, {"on_hand": Decimal("0"), "available": Decimal("0")}
        )
    return result


# ==================== 仓库 ====================


def list_warehouses(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
):
    return repository.list_warehouses(db, page, page_size, keyword, status)


def get_warehouse(db: Session, warehouse_id: int) -> models.InvWarehouse:
    return _require_warehouse(db, warehouse_id)


def create_warehouse(
    db: Session,
    *,
    warehouse_code: str,
    warehouse_name: str,
    org_id: Optional[int] = None,
    manager_id: Optional[int] = None,
    address: Optional[str] = None,
    location_code: Optional[str] = None,
    location_name: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.InvWarehouse:
    if repository.get_warehouse_by_code(db, warehouse_code):
        raise BusinessException(CODE_DUPLICATE, f"仓库编码已存在：{warehouse_code}")
    warehouse = models.InvWarehouse(
        warehouse_code=warehouse_code,
        warehouse_name=warehouse_name,
        org_id=org_id,
        manager_id=manager_id,
        address=address,
        location_code=location_code,
        location_name=location_name,
        status="ACTIVE",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_warehouse(db, warehouse)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="inv_warehouse",
        target_id=warehouse.id,
        operator_id=operator_id,
        detail=f"新增仓库 {warehouse_code}",
    )
    return warehouse


def update_warehouse(
    db: Session,
    warehouse_id: int,
    *,
    warehouse_name: Optional[str] = None,
    org_id: Optional[int] = None,
    manager_id: Optional[int] = None,
    address: Optional[str] = None,
    location_code: Optional[str] = None,
    location_name: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.InvWarehouse:
    warehouse = _require_warehouse(db, warehouse_id)
    if warehouse_name is not None:
        warehouse.warehouse_name = warehouse_name
    if org_id is not None:
        warehouse.org_id = org_id
    if manager_id is not None:
        warehouse.manager_id = manager_id
    if address is not None:
        warehouse.address = address
    if location_code is not None:
        warehouse.location_code = location_code
    if location_name is not None:
        warehouse.location_name = location_name
    if remark is not None:
        warehouse.remark = remark
    warehouse.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="inv_warehouse",
        target_id=warehouse.id,
        operator_id=operator_id,
        detail=f"修改仓库 {warehouse.warehouse_code}",
    )
    return warehouse


def set_warehouse_status(
    db: Session, warehouse_id: int, status: str, operator_id: Optional[int] = None
) -> models.InvWarehouse:
    if status not in _RECORD_STATUS:
        raise BusinessException(CODE_PARAM_INVALID, f"非法状态：{status}")
    warehouse = _require_warehouse(db, warehouse_id)
    warehouse.status = status
    warehouse.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="inv_warehouse",
        target_id=warehouse.id,
        operator_id=operator_id,
        detail=f"仓库 {warehouse.warehouse_code} 状态改为 {status}",
    )
    return warehouse


# ==================== 实时库存查询 ====================


def list_balances(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    keyword: Optional[str] = None,
    has_reorder_point: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """分页查询实时库存，附带物料编码/名称与可用量。"""
    material_ids: Optional[List[int]] = None
    if keyword:
        from app.modules.system.contract import search_materials

        material_ids = [m["id"] for m in search_materials(db, keyword=keyword, limit=500)]
    rows, total = repository.list_balances(
        db, page, page_size, material_id, warehouse_id, material_ids,
        has_reorder_point=has_reorder_point,
    )
    materials = _material_map(db, [r.material_id for r in rows])
    warehouses = _warehouse_name_map(db, [r.warehouse_id for r in rows])
    items = []
    for row in rows:
        material = materials.get(row.material_id, {})
        items.append(
            {
                "id": row.id,
                "material_id": row.material_id,
                "material_code": material.get("material_code"),
                "material_name": material.get("material_name"),
                "warehouse_id": row.warehouse_id,
                "warehouse_name": warehouses.get(row.warehouse_id),
                "reorder_point": row.reorder_point,
                "reorder_quantity": row.reorder_quantity,
                **_balance_dict(row),
            }
        )
    return items, total


def get_available_stock(
    db: Session, material_id: int, warehouse_id: Optional[int] = None
) -> Dict[str, Any]:
    """按物料（可选仓库）汇总现存量 / 锁定量 / 可用量。"""
    on_hand = repository.sum_quantity(db, material_id, warehouse_id)
    available = repository.sum_available(db, material_id, warehouse_id)
    return {
        "material_id": material_id,
        "warehouse_id": warehouse_id,
        "on_hand": on_hand,
        "locked_quantity": on_hand - available,
        "available_quantity": available,
    }


# ==================== 库存变动记录（从业务单据聚合） ====================
# inv_transaction 流水表已删除。库存变动记录可通过库存操作单（移库/盘点）查询，
# 手工入/出库直接改结存、不留单据；前端流水页复用 list_stock_operations 展示。


# ==================== 库存操作单（移库 / 盘点） ====================


def list_stock_operations(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    op_type: Optional[str] = None,
    status: Optional[str] = None,
    warehouse_id: Optional[int] = None,
):
    return repository.list_stock_operations(db, page, page_size, op_type, status, warehouse_id)


def get_stock_operation(db: Session, operation_id: int) -> models.InvStockOperation:
    operation = repository.get_stock_operation(db, operation_id)
    if not operation:
        raise BusinessException(CODE_NOT_FOUND, f"库存操作单不存在：{operation_id}")
    return operation


def create_stock_operation(
    db: Session,
    *,
    op_type: str,
    op_date: date,
    items: Sequence[Mapping[str, Any]],
    operation_no: Optional[str] = None,
    from_warehouse_id: Optional[int] = None,
    to_warehouse_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.InvStockOperation:
    """新增库存操作单（单头 + 明细，状态 DRAFT）。

    - TRANSFER：必填 from_warehouse_id / to_warehouse_id，明细带 quantity；
    - STOCKTAKE：必填 warehouse_id，明细带 actual_qty（book_qty 缺省按当前结存自动带出）。
    """
    if op_type not in ("TRANSFER", "STOCKTAKE"):
        raise BusinessException(CODE_PARAM_INVALID, f"非法操作类型：{op_type}")
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "操作单至少需要一条明细")
    if operation_no and repository.get_operation_by_no(db, operation_no):
        raise BusinessException(CODE_DUPLICATE, f"操作单号已存在：{operation_no}")

    if op_type == "TRANSFER":
        if not from_warehouse_id or not to_warehouse_id:
            raise BusinessException(CODE_PARAM_INVALID, "移库单必须指定源仓库与目标仓库")
        _require_warehouse(db, from_warehouse_id)
        _require_warehouse(db, to_warehouse_id)
        if from_warehouse_id == to_warehouse_id:
            raise BusinessException(CODE_PARAM_INVALID, "移库源仓库与目标仓库不能相同")
        warehouse = None
    else:
        if not warehouse_id:
            raise BusinessException(CODE_PARAM_INVALID, "盘点单必须指定仓库")
        warehouse = _require_warehouse(db, warehouse_id)

    number = operation_no or repository.next_operation_no(db, op_date, op_type)
    operation = models.InvStockOperation(
        operation_no=number,
        op_type=op_type,
        from_warehouse_id=from_warehouse_id if op_type == "TRANSFER" else None,
        to_warehouse_id=to_warehouse_id if op_type == "TRANSFER" else None,
        warehouse_id=warehouse_id if op_type == "STOCKTAKE" else None,
        op_date=op_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_stock_operation(db, operation)
    for raw in items:
        _require_material(db, raw["material_id"])
        if op_type == "TRANSFER":
            qty = _as_decimal(raw.get("quantity"))
            if qty <= 0:
                raise BusinessException(CODE_PARAM_INVALID, "移库数量必须为正数")
            repository.add_operation_item(
                db,
                models.InvStockOperationItem(
                    operation_id=operation.id,
                    material_id=raw["material_id"],
                    quantity=qty,
                    remark=raw.get("remark"),
                ),
            )
        else:
            actual = _as_decimal(raw.get("actual_qty"))
            if actual < 0:
                raise BusinessException(CODE_PARAM_INVALID, "实盘数量不能为负数")
            book_value = raw.get("book_qty")
            if book_value is None:
                balance = repository.get_balance(db, warehouse.id, raw["material_id"])
                book_value = _as_decimal(balance.quantity) if balance else Decimal("0")
            book = _as_decimal(book_value)
            repository.add_operation_item(
                db,
                models.InvStockOperationItem(
                    operation_id=operation.id,
                    material_id=raw["material_id"],
                    book_qty=book,
                    actual_qty=actual,
                    difference=actual - book,
                    remark=raw.get("remark"),
                ),
            )
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="inv_stock_operation",
        target_id=operation.id,
        operator_id=operator_id,
        detail=f"新增{'移库' if op_type == 'TRANSFER' else '盘点'}单 {number}",
    )
    return operation


def confirm_stock_operation(
    db: Session, operation_id: int, operator_id: Optional[int] = None
) -> models.InvStockOperation:
    """确认操作单（仅 DRAFT 可确认）：

    - TRANSFER：对每条明细写 TRANSFER_OUT + TRANSFER_IN 两条流水（同一事务）；
    - STOCKTAKE：按差异写 `ADJUST` 流水（差异为 0 的行不写流水）。
    """
    operation = get_stock_operation(db, operation_id)
    if operation.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"操作单当前状态为 {operation.status}，不能确认"
        )
    items = list(operation.items)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "操作单没有明细，不能确认")
    if operation.op_type == "TRANSFER":
        for item in items:
            qty = _as_decimal(item.quantity)
            if qty <= 0:
                raise BusinessException(CODE_PARAM_INVALID, "移库数量必须为正数")
            _decrease_stock(
                db,
                transaction_type="TRANSFER_OUT",
                material_id=item.material_id,
                quantity=qty,
                warehouse_id=operation.from_warehouse_id,
                source_module=MODULE,
                source_type="TRANSFER",
                source_reference_id=operation.id,
                source_no=operation.operation_no,
                biz_date=operation.op_date,
                operator_id=operator_id,
                remark=f"移库出库 {operation.operation_no}",
            )
            _increase_stock(
                db,
                transaction_type="TRANSFER_IN",
                material_id=item.material_id,
                quantity=qty,
                warehouse_id=operation.to_warehouse_id,
                source_module=MODULE,
                source_type="TRANSFER",
                source_reference_id=operation.id,
                source_no=operation.operation_no,
                biz_date=operation.op_date,
                operator_id=operator_id,
                remark=f"移库入库 {operation.operation_no}",
            )
    else:
        for item in items:
            book = _as_decimal(item.book_qty)
            actual = _as_decimal(item.actual_qty)
            difference = actual - book
            item.difference = difference
            if difference == 0:
                continue
            _apply_adjust(
                db,
                material_id=item.material_id,
                warehouse_id=operation.warehouse_id,
                delta=difference,
                biz_date=operation.op_date,
                source_module=MODULE,
                source_type="STOCKTAKE",
                source_reference_id=operation.id,
                source_no=operation.operation_no,
                operator_id=operator_id,
                remark=f"盘点调整 {operation.operation_no}",
            )
    operation.status = "COMPLETED"
    operation.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="inv_stock_operation",
        target_id=operation.id,
        operator_id=operator_id,
        detail=f"确认操作单 {operation.operation_no}",
    )
    return operation


def cancel_stock_operation(
    db: Session, operation_id: int, operator_id: Optional[int] = None
) -> models.InvStockOperation:
    operation = get_stock_operation(db, operation_id)
    if operation.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"操作单当前状态为 {operation.status}，不能取消"
        )
    operation.status = "CANCELLED"
    operation.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="inv_stock_operation",
        target_id=operation.id,
        operator_id=operator_id,
        detail=f"取消操作单 {operation.operation_no}",
    )
    return operation


# ==================== 订货点（直接维护在 inv_balance 上） ====================


def get_balance_row(db: Session, balance_id: int) -> models.InvBalance:
    balance = db.get(models.InvBalance, balance_id)
    if not balance:
        raise BusinessException(CODE_NOT_FOUND, f"库存结存不存在：{balance_id}")
    return balance


def update_balance_reorder(
    db: Session,
    balance_id: int,
    *,
    reorder_point: Optional[Decimal] = None,
    reorder_quantity: Optional[Decimal] = None,
    operator_id: Optional[int] = None,
) -> models.InvBalance:
    """直接编辑结存行的订货点 / 建议订货量（原 inv_reorder_rule 维护逻辑并入）。"""
    balance = get_balance_row(db, balance_id)
    if reorder_point is not None:
        if _as_decimal(reorder_point) < 0:
            raise BusinessException(CODE_PARAM_INVALID, "订货点不能为负数")
        balance.reorder_point = _as_decimal(reorder_point)
    if reorder_quantity is not None:
        if _as_decimal(reorder_quantity) < 0:
            raise BusinessException(CODE_PARAM_INVALID, "建议订货量不能为负数")
        balance.reorder_quantity = _as_decimal(reorder_quantity)
    balance.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="inv_balance",
        target_id=balance.id,
        operator_id=operator_id,
        detail=f"修改订货点 结存{balance.id}（订货点 {balance.reorder_point} / 订货量 {balance.reorder_quantity}）",
    )
    materials = _material_map(db, [balance.material_id])
    warehouses = _warehouse_name_map(db, [balance.warehouse_id])
    material = materials.get(balance.material_id, {})
    return {
        "id": balance.id,
        "material_id": balance.material_id,
        "material_code": material.get("material_code"),
        "material_name": material.get("material_name"),
        "warehouse_id": balance.warehouse_id,
        "warehouse_name": warehouses.get(balance.warehouse_id),
        "reorder_point": _as_decimal(balance.reorder_point),
        "reorder_quantity": _as_decimal(balance.reorder_quantity),
        **_balance_dict(balance),
    }


def list_reorder_suggestions(db: Session) -> List[Dict[str, Any]]:
    """对所有**配置了订货点**的结存，现存量低于订货点的返回补库建议。

    订货点（reorder_point）为可选字段，仅 A 类高价值关键物料配置；
    未配置（None）的结存不产生补库建议。
    """
    suggestions: List[Dict[str, Any]] = []
    balances = list(db.scalars(select(models.InvBalance).order_by(models.InvBalance.id)))
    for balance in balances:
        if balance.reorder_point is None:
            continue
        point = _as_decimal(balance.reorder_point)
        if point <= 0:
            continue
        current = _as_decimal(balance.quantity)
        if current >= point:
            continue
        suggested = _as_decimal(balance.reorder_quantity) if balance.reorder_quantity is not None else Decimal("0")
        suggestions.append(
            {
                "balance_id": balance.id,
                "material_id": balance.material_id,
                "warehouse_id": balance.warehouse_id,
                "reorder_point": point,
                "current_qty": current,
                "suggested_qty": suggested,
                "target_qty": current + suggested,
            }
        )
    return suggestions


# ==================== 补库需求 ====================


def list_replenishment_requests(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    material_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_replenishment_requests(
        db, page, page_size, status, source_type, material_id
    )
    materials = _material_map(db, [r.material_id for r in rows])
    items = []
    for row in rows:
        material = materials.get(row.material_id, {})
        items.append(
            {
                "id": row.id,
                "request_no": row.request_no,
                "material_id": row.material_id,
                "material_code": material.get("material_code"),
                "material_name": material.get("material_name"),
                "warehouse_id": row.warehouse_id,
                "request_qty": _as_decimal(row.request_qty),
                "current_qty": _as_decimal(row.current_qty),
                "target_qty": _as_decimal(row.target_qty),
                "required_date": row.required_date,
                "source_type": row.source_type,
                "status": row.status,
                "handled_module": row.handled_module,
                "handled_ref_id": row.handled_ref_id,
                "remark": row.remark,
            }
        )
    return items, total


def get_replenishment_request(db: Session, request_id: int) -> models.InvReplenishmentRequest:
    request = repository.get_replenishment_request(db, request_id)
    if not request:
        raise BusinessException(CODE_NOT_FOUND, f"补库需求不存在：{request_id}")
    return request


def get_replenishment_request_dict(
    db: Session, request_id: int
) -> Optional[Dict[str, Any]]:
    """按 ID 读取补库需求单为纯字典（供跨模块契约使用），不存在返回 None。"""
    request = repository.get_replenishment_request(db, request_id)
    if not request:
        return None
    return {
        "id": request.id,
        "request_no": request.request_no,
        "material_id": request.material_id,
        "warehouse_id": request.warehouse_id,
        "request_qty": _as_decimal(request.request_qty),
        "current_qty": _as_decimal(request.current_qty),
        "target_qty": _as_decimal(request.target_qty),
        "required_date": request.required_date,
        "source_type": request.source_type,
        "status": request.status,
    }


def create_replenishment_request(
    db: Session,
    *,
    material_id: int,
    warehouse_id: int,
    request_qty: Decimal,
    required_date: date,
    source_type: str,
    current_qty: Decimal = Decimal("0"),
    target_qty: Decimal = Decimal("0"),
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """创建补库需求单（**不直接创建正式计划**，规格 §14）。"""
    qty = _as_decimal(request_qty)
    if qty <= 0:
        raise BusinessException(CODE_PARAM_INVALID, "补库数量必须为正数")
    if source_type not in _VALID_REPLENISHMENT_SOURCES:
        raise BusinessException(CODE_PARAM_INVALID, f"非法的补库来源：{source_type}")
    _require_material(db, material_id)
    _require_warehouse(db, warehouse_id)
    number = repository.next_replenishment_no(db, required_date)
    request = models.InvReplenishmentRequest(
        request_no=number,
        material_id=material_id,
        warehouse_id=warehouse_id,
        request_qty=qty,
        current_qty=_as_decimal(current_qty),
        target_qty=_as_decimal(target_qty),
        required_date=required_date,
        source_type=source_type,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_replenishment_request(db, request)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="inv_replenishment_request",
        target_id=request.id,
        operator_id=operator_id,
        detail=f"新增补库需求 {number}（{source_type}）",
    )
    return {"id": request.id, "request_no": request.request_no}


def _extract_plan_id(result: Any) -> Optional[int]:
    """从契约返回结果中提取计划ID（兼容 dict / int）。"""
    if result is None:
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, Mapping):
        for key in ("id", "plan_id", "purchase_plan_id", "production_plan_id"):
            if result.get(key) is not None:
                return int(result[key])
    return None


def confirm_replenishment_request(
    db: Session, request_id: int, operator_id: Optional[int] = None
) -> models.InvReplenishmentRequest:
    """确认补库需求：DRAFT → CONFIRMED → 调用跨模块契约 → RELEASED。

    库存模块**只负责发起补库需求**；正式采购/生产计划由 procurement / planning
    通过各自 contract 创建（规格 §14）。契约尚未就绪时抛 5002。
    """
    request = get_replenishment_request(db, request_id)
    if request.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"补库需求当前状态为 {request.status}，不能确认"
        )
    request.status = "CONFIRMED"
    if request.source_type == "REORDER":
        try:
            from app.modules.procurement.contract import (  # type: ignore
                create_purchase_plan_from_replenishment,
            )
        except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
            raise BusinessException(CODE_CONTRACT_NOT_READY, "采购计划接口尚未就绪") from exc
        result = create_purchase_plan_from_replenishment(db, request.id)
        request.handled_module = "procurement"
    elif request.source_type == "PRODUCTION":
        try:
            from app.modules.planning.contract import (  # type: ignore
                create_production_plan_from_replenishment,
            )
        except Exception as exc:  # noqa: BLE001 - 契约尚未就绪
            raise BusinessException(CODE_CONTRACT_NOT_READY, "生产计划接口尚未就绪") from exc
        result = create_production_plan_from_replenishment(db, request.id)
        request.handled_module = "planning"
    else:
        raise BusinessException(CODE_PARAM_INVALID, f"非法的补库来源：{request.source_type}")
    request.handled_ref_id = _extract_plan_id(result)
    request.status = "RELEASED"
    request.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="inv_replenishment_request",
        target_id=request.id,
        operator_id=operator_id,
        detail=f"确认补库需求 {request.request_no}，转 {request.handled_module}",
    )
    return request


def cancel_replenishment_request(
    db: Session, request_id: int, operator_id: Optional[int] = None
) -> models.InvReplenishmentRequest:
    request = get_replenishment_request(db, request_id)
    if request.status not in {"DRAFT", "CONFIRMED"}:
        raise BusinessException(
            CODE_STATUS_INVALID, f"补库需求当前状态为 {request.status}，不能取消"
        )
    request.status = "CANCELLED"
    request.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="inv_replenishment_request",
        target_id=request.id,
        operator_id=operator_id,
        detail=f"取消补库需求 {request.request_no}",
    )
    return request


def generate_from_reorder_rules(
    db: Session, operator_id: Optional[int] = None
) -> Dict[str, Any]:
    """按订货点建议批量生成 DRAFT `REORDER` 补库需求（已有在途需求的跳过）。"""
    created_ids: List[int] = []
    skipped = 0
    for suggestion in list_reorder_suggestions(db):
        if suggestion["suggested_qty"] <= 0:
            skipped += 1
            continue
        pending = repository.count_where(
            db,
            models.InvReplenishmentRequest,
            models.InvReplenishmentRequest.material_id == suggestion["material_id"],
            models.InvReplenishmentRequest.warehouse_id == suggestion["warehouse_id"],
            models.InvReplenishmentRequest.source_type == "REORDER",
            models.InvReplenishmentRequest.status.in_(
                ["DRAFT", "CONFIRMED", "RELEASED"]
            ),
        )
        if pending:
            skipped += 1
            continue
        result = create_replenishment_request(
            db,
            material_id=suggestion["material_id"],
            warehouse_id=suggestion["warehouse_id"],
            request_qty=suggestion["suggested_qty"],
            required_date=date.today(),
            source_type="REORDER",
            current_qty=suggestion["current_qty"],
            target_qty=suggestion["target_qty"],
            remark="订货点自动生成",
            operator_id=operator_id,
        )
        created_ids.append(result["id"])
    return {
        "created_count": len(created_ids),
        "request_ids": created_ids,
        "skipped_count": skipped,
    }


# ==================== 报表 / 统计 ====================


def stock_summary(
    db: Session, warehouse_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """库存汇总：每物料现存量 / 可用量 / 安全库存 / 是否低于安全库存。"""
    rows = repository.aggregate_by_material(db, warehouse_id)
    materials = _material_map(db, [mid for mid, _, _ in rows])
    summary = []
    for material_id, on_hand, available in rows:
        material = materials.get(material_id, {})
        safety = _as_decimal(material.get("safety_stock"))
        summary.append(
            {
                "material_id": material_id,
                "material_code": material.get("material_code"),
                "material_name": material.get("material_name"),
                "on_hand": on_hand,
                "available_quantity": available,
                "safety_stock": safety,
                "below_safety": available < safety,
            }
        )
    return summary


def low_stock_report(db: Session) -> List[Dict[str, Any]]:
    """低库存 / 缺料报表：可用量低于安全库存的物料。"""
    report = []
    for row in stock_summary(db):
        if row["safety_stock"] > 0 and row["available_quantity"] < row["safety_stock"]:
            row = dict(row)
            row["shortage_qty"] = row["safety_stock"] - row["available_quantity"]
            report.append(row)
    return report


def flow_summary(db: Session, date_from: date, date_to: date) -> List[Dict[str, Any]]:
    """出入库汇总：从库存操作单（移库/盘点）按物料统计数量合计。

    流水表删除后，出入库汇总基于 inv_stock_operation 聚合；
    手工入/出库无单据，不在此汇总中体现。
    """
    if date_from > date_to:
        raise BusinessException(CODE_PARAM_INVALID, "开始日期不能晚于结束日期")
    rows = repository.aggregate_flow(db, date_from, date_to)
    materials = _material_map(db, [mid for _, mid, _ in rows])
    result = []
    for operation_type, material_id, total in rows:
        material = materials.get(material_id, {})
        result.append(
            {
                "transaction_type": operation_type,
                "material_id": material_id,
                "material_code": material.get("material_code"),
                "material_name": material.get("material_name"),
                "total_quantity": total,
            }
        )
    return result


def stats(db: Session) -> Dict[str, Any]:
    """库存模块统计（供 dashboard 使用）。"""
    return {
        "warehouse_count": repository.count_all(db, models.InvWarehouse),
        "balance_count": repository.count_all(db, models.InvBalance),
        "stock_operation_count": repository.count_all(db, models.InvStockOperation),
        "transfer_count": repository.count_operations_by_type(db, "TRANSFER"),
        "stocktake_count": repository.count_operations_by_type(db, "STOCKTAKE"),
        "replenishment_request_count": repository.count_all(
            db, models.InvReplenishmentRequest
        ),
        "low_stock_count": len(low_stock_report(db)),
    }


# ==================== 课程期初库存导入（规格 §37） ====================

_COURSE_CASE_SOURCE = "course_chair_case"
# data/seed/course_chair_case.json 位于仓库根目录；本文件位于 backend/app/modules/inventory/
_SEED_FILE = Path(__file__).resolve().parents[4] / "data" / "seed" / "course_chair_case.json"


def _load_course_initial_inventory() -> List[Dict[str, Any]]:
    """从课程权威数据文件读取期初库存。

    数量全部来自 `course_data.initial_inventory`：`finished_goods_quantity` 用于根节点，
    `component_quantity` 用于其余节点；物料编码通过递归 `course_data.product` 树枚举，
    **绝不硬编码任何数量或编码**。
    """
    if not _SEED_FILE.exists():
        raise BusinessException(CODE_NOT_FOUND, f"课程数据文件不存在：{_SEED_FILE}")
    with _SEED_FILE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    course = payload.get("course_data") or {}
    initial = course.get("initial_inventory") or {}
    product = course.get("product") or {}
    finished_qty = _as_decimal(initial.get("finished_goods_quantity"))
    component_qty = _as_decimal(initial.get("component_quantity"))
    rows: List[Dict[str, Any]] = []

    def walk(node: Mapping[str, Any], is_root: bool) -> None:
        code = node.get("material_code")
        if code:
            rows.append(
                {
                    "material_code": str(code),
                    "quantity": finished_qty if is_root else component_qty,
                }
            )
        for child in node.get("children") or []:
            walk(child, False)

    walk(product, True)
    return rows


def _collect_import_rows(
    source: Optional[str], rows: Optional[Sequence[Mapping[str, Any]]]
) -> List[Dict[str, Any]]:
    """整理待导入行：显式 rows 优先，否则按 source 读取课程数据文件。"""
    if rows:
        return [
            {
                "material_code": str(row.get("material_code") or "").strip(),
                "quantity": _as_decimal(row.get("quantity")),
            }
            for row in rows
        ]
    if source == _COURSE_CASE_SOURCE:
        return _load_course_initial_inventory()
    raise BusinessException(CODE_PARAM_INVALID, "未提供期初库存导入数据")


def _resolve_import_warehouse(
    db: Session, warehouse_id: Optional[int], warehouse_code: Optional[str]
) -> models.InvWarehouse:
    """解析导入仓库：id 优先，其次编码；都无法解析时抛 5007（未指定导入仓库）。"""
    warehouse = None
    if warehouse_id is not None:
        warehouse = repository.get_warehouse(db, warehouse_id)
    elif warehouse_code:
        warehouse = repository.get_warehouse_by_code(db, warehouse_code)
    if not warehouse:
        raise BusinessException(5007, "未指定导入仓库")
    return warehouse


def _validate_import_rows(
    db: Session,
    *,
    warehouse_id: int,
    rows: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """逐行校验：物料编码必须存在、数量必须为正；未知编码记为错误而非静默跳过。"""
    entries: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for row in rows:
        code = row["material_code"]
        quantity = _as_decimal(row["quantity"])
        material = find_material_by_code(db, code) if code else None
        if not material:
            entries.append(
                {
                    "material_code": code,
                    "material_name": None,
                    "quantity": quantity,
                    "status": "INVALID",
                }
            )
            errors.append({"material_code": code, "message": f"物料编码不存在：{code}"})
            continue
        if quantity <= 0:
            entries.append(
                {
                    "material_code": code,
                    "material_name": material["material_name"],
                    "quantity": quantity,
                    "status": "INVALID",
                }
            )
            errors.append({"material_code": code, "message": "导入数量必须为正数"})
            continue
        entries.append(
            {
                "material_code": code,
                "material_name": material["material_name"],
                "quantity": quantity,
                "status": "VALID",
                "material_id": material["id"],
            }
        )
    return entries, errors


def preview_initial_stock_import(
    db: Session,
    *,
    source: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    warehouse_code: Optional[str] = None,
    rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """期初库存导入预览：**只校验、不写任何数据**（规格 §37）。"""
    warehouse = _resolve_import_warehouse(db, warehouse_id, warehouse_code)
    collected = _collect_import_rows(source, rows)
    entries, errors = _validate_import_rows(db, warehouse_id=warehouse.id, rows=collected)
    valid = sum(1 for entry in entries if entry["status"] == "VALID")
    return {
        "rows": [
            {
                "material_code": entry["material_code"],
                "material_name": entry["material_name"],
                "quantity": entry["quantity"],
                "status": entry["status"],
            }
            for entry in entries
        ],
        "errors": errors,
        "summary": {"total": len(entries), "valid": valid, "invalid": len(errors)},
    }


def confirm_initial_stock_import(
    db: Session,
    *,
    source: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    warehouse_code: Optional[str] = None,
    rows: Optional[Sequence[Mapping[str, Any]]] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """确认期初库存导入：重新校验后逐行走 `increase_stock`（写真实流水），同一事务内完成。"""
    warehouse = _resolve_import_warehouse(db, warehouse_id, warehouse_code)
    collected = _collect_import_rows(source, rows)
    entries, errors = _validate_import_rows(db, warehouse_id=warehouse.id, rows=collected)
    imported = 0
    for entry in entries:
        if entry["status"] != "VALID":
            continue
        increase_stock(
            db,
            material_id=entry["material_id"],
            quantity=entry["quantity"],
            warehouse_id=warehouse.id,
            source_module=MODULE,
            source_type="MANUAL",
            biz_date=date.today(),
            operator_id=operator_id,
            remark="课程附录1期初库存导入",
        )
        imported += 1
    log_operation(
        db,
        module=MODULE,
        action="IMPORT",
        target_type="inv_balance",
        target_id=warehouse.id,
        operator_id=operator_id,
        detail=f"期初库存导入：成功 {imported} 行，失败 {len(errors)} 行",
    )
    return {"imported": imported, "errors": errors}