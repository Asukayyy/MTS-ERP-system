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
CODE_LOCATION_IN_USE = 5007  # 库位已被库存引用，禁止删除

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


def _require_location(db: Session, location_id: int, warehouse_id: int) -> models.InvLocation:
    location = repository.get_location(db, location_id)
    if not location:
        raise BusinessException(CODE_NOT_FOUND, f"库位不存在：{location_id}")
    if location.warehouse_id != warehouse_id:
        raise BusinessException(CODE_PARAM_INVALID, "库位不属于指定仓库")
    return location


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


def _lock_or_create_balance(
    db: Session, warehouse_id: int, location_id: Optional[int], material_id: int
) -> models.InvBalance:
    """取或建结存桶，并对已存在的行加锁（`SELECT ... FOR UPDATE`）。"""
    balance = repository.get_balance_for_update(db, warehouse_id, location_id, material_id)
    if balance is None:
        balance = models.InvBalance(
            warehouse_id=warehouse_id,
            location_id=location_id,
            material_id=material_id,
            quantity=Decimal("0"),
            locked_quantity=Decimal("0"),
        )
        repository.add_balance(db, balance)
        balance = repository.get_balance_for_update(
            db, warehouse_id, location_id, material_id
        ) or balance
    return balance


def _append_transaction(
    db: Session,
    *,
    transaction_type: str,
    material_id: int,
    warehouse_id: int,
    location_id: Optional[int],
    quantity_change: Decimal,
    quantity_after: Decimal,
    unit_cost: Decimal,
    biz_date: date,
    source_module: str,
    source_type: str,
    source_reference_id: Optional[int],
    source_no: Optional[str],
    operator_id: Optional[int],
    remark: Optional[str],
) -> models.InvTransaction:
    """写入一条库存流水。单号冲突时重取单号重试一次（保存点回滚，不影响外层事务）。"""
    txn = models.InvTransaction(
        transaction_no=repository.next_txn_no(db, biz_date),
        transaction_type=transaction_type,
        material_id=material_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        quantity_change=quantity_change,
        quantity_after=quantity_after,
        unit_cost=unit_cost,
        biz_date=biz_date,
        source_module=source_module,
        source_type=source_type,
        source_reference_id=source_reference_id,
        source_no=source_no,
        operator_id=operator_id,
        remark=remark,
        created_by=operator_id,
    )
    try:
        with db.begin_nested():
            db.add(txn)
            db.flush()
    except IntegrityError:
        txn.transaction_no = repository.next_txn_no(db, biz_date)
        with db.begin_nested():
            db.add(txn)
            db.flush()
    return txn


def _validate_stock_args(
    db: Session,
    *,
    material_id: int,
    quantity: Decimal,
    warehouse_id: int,
    location_id: Optional[int],
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
    if location_id is not None:
        _require_location(db, location_id, warehouse_id)
    return qty


def _increase_stock(
    db: Session,
    *,
    transaction_type: str,
    material_id: int,
    quantity: Decimal,
    warehouse_id: int,
    location_id: Optional[int] = None,
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
        location_id=location_id,
        source_module=source_module,
        source_type=source_type,
    )
    biz = biz_date or date.today()
    balance = _lock_or_create_balance(db, warehouse_id, location_id, material_id)
    balance.quantity = _as_decimal(balance.quantity) + qty
    balance.updated_at_txn = datetime.now()
    txn = _append_transaction(
        db,
        transaction_type=transaction_type,
        material_id=material_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        quantity_change=qty,
        quantity_after=balance.quantity,
        unit_cost=_as_decimal(unit_cost),
        biz_date=biz,
        source_module=source_module,
        source_type=source_type,
        source_reference_id=source_reference_id,
        source_no=source_no,
        operator_id=operator_id,
        remark=remark,
    )
    return {
        "transaction_id": txn.id,
        "transaction_no": txn.transaction_no,
        "quantity_after": _as_decimal(balance.quantity),
    }


def increase_stock(
    db: Session,
    *,
    material_id: int,
    quantity: Decimal,
    warehouse_id: int,
    location_id: Optional[int] = None,
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
        location_id=location_id,
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
    location_id: Optional[int] = None,
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
        location_id=location_id,
        source_module=source_module,
        source_type=source_type,
    )
    biz = biz_date or date.today()
    balance = repository.get_balance_for_update(db, warehouse_id, location_id, material_id)
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
    txn = _append_transaction(
        db,
        transaction_type=transaction_type,
        material_id=material_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        quantity_change=-qty,
        quantity_after=new_qty,
        unit_cost=_as_decimal(unit_cost),
        biz_date=biz,
        source_module=source_module,
        source_type=source_type,
        source_reference_id=source_reference_id,
        source_no=source_no,
        operator_id=operator_id,
        remark=remark,
    )
    return {
        "transaction_id": txn.id,
        "transaction_no": txn.transaction_no,
        "quantity_after": new_qty,
    }


def decrease_stock(
    db: Session,
    *,
    material_id: int,
    quantity: Decimal,
    warehouse_id: int,
    location_id: Optional[int] = None,
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
        location_id=location_id,
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
    location_id: Optional[int],
    delta: Decimal,
    unit_cost: Decimal = Decimal("0"),
    biz_date: Optional[date] = None,
    source_module: str = MODULE,
    source_type: str = "STOCKTAKE",
    source_reference_id: Optional[int] = None,
    source_no: Optional[str] = None,
    operator_id: Optional[int] = None,
    remark: Optional[str] = None,
) -> models.InvTransaction:
    """盘点调整：写 `ADJUST` 流水（delta 可为负，调整后结存不得为负）。"""
    biz = biz_date or date.today()
    balance = _lock_or_create_balance(db, warehouse_id, location_id, material_id)
    new_qty = _as_decimal(balance.quantity) + delta
    if new_qty < 0:
        raise BusinessException(
            CODE_BALANCE_NEGATIVE,
            f"盘点调整后库存为负：物料 {material_id} 调整后 {new_qty}",
        )
    balance.quantity = new_qty
    balance.updated_at_txn = datetime.now()
    return _append_transaction(
        db,
        transaction_type="ADJUST",
        material_id=material_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        quantity_change=delta,
        quantity_after=new_qty,
        unit_cost=_as_decimal(unit_cost),
        biz_date=biz,
        source_module=source_module,
        source_type=source_type,
        source_reference_id=source_reference_id,
        source_no=source_no,
        operator_id=operator_id,
        remark=remark,
    )


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


# ==================== 库位 ====================


def list_locations(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    warehouse_id: Optional[int] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
):
    return repository.list_locations(db, page, page_size, warehouse_id, keyword, status)


def get_location(db: Session, location_id: int) -> models.InvLocation:
    location = repository.get_location(db, location_id)
    if not location:
        raise BusinessException(CODE_NOT_FOUND, f"库位不存在：{location_id}")
    return location


def create_location(
    db: Session,
    *,
    location_code: str,
    location_name: str,
    warehouse_id: int,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.InvLocation:
    _require_warehouse(db, warehouse_id)
    if repository.get_location_by_code(db, warehouse_id, location_code):
        raise BusinessException(
            CODE_DUPLICATE, f"该仓库下库位编码已存在：{location_code}"
        )
    location = models.InvLocation(
        location_code=location_code,
        location_name=location_name,
        warehouse_id=warehouse_id,
        status="ACTIVE",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_location(db, location)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="inv_location",
        target_id=location.id,
        operator_id=operator_id,
        detail=f"新增库位 {location_code}",
    )
    return location


def update_location(
    db: Session,
    location_id: int,
    *,
    location_name: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.InvLocation:
    location = get_location(db, location_id)
    if location_name is not None:
        location.location_name = location_name
    if remark is not None:
        location.remark = remark
    location.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="inv_location",
        target_id=location.id,
        operator_id=operator_id,
        detail=f"修改库位 {location.location_code}",
    )
    return location


def set_location_status(
    db: Session, location_id: int, status: str, operator_id: Optional[int] = None
) -> models.InvLocation:
    if status not in _RECORD_STATUS:
        raise BusinessException(CODE_PARAM_INVALID, f"非法状态：{status}")
    location = get_location(db, location_id)
    location.status = status
    location.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="inv_location",
        target_id=location.id,
        operator_id=operator_id,
        detail=f"库位 {location.location_code} 状态改为 {status}",
    )
    return location


def delete_location(db: Session, location_id: int, operator_id: Optional[int] = None) -> None:
    location = get_location(db, location_id)
    if repository.count_balances_by_location(db, location_id) > 0:
        raise BusinessException(CODE_LOCATION_IN_USE, "库位已被库存引用，禁止删除")
    code = location.location_code
    repository.delete_location(db, location)
    log_operation(
        db,
        module=MODULE,
        action="DELETE",
        target_type="inv_location",
        target_id=location_id,
        operator_id=operator_id,
        detail=f"删除库位 {code}",
    )


# ==================== 实时库存查询 ====================


def list_balances(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    keyword: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """分页查询实时库存，附带物料编码/名称与可用量。"""
    material_ids: Optional[List[int]] = None
    if keyword:
        from app.modules.system.contract import search_materials

        material_ids = [m["id"] for m in search_materials(db, keyword=keyword, limit=500)]
    rows, total = repository.list_balances(
        db, page, page_size, material_id, warehouse_id, material_ids
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
                "location_id": row.location_id,
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


# ==================== 库存流水查询 ====================


def list_transactions(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    transaction_type: Optional[str] = None,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    source_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    source_no: Optional[str] = None,
    keyword: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    material_ids: Optional[List[int]] = None
    if keyword:
        from app.modules.system.contract import search_materials

        material_ids = [m["id"] for m in search_materials(db, keyword=keyword, limit=500)]
    rows, total = repository.list_transactions(
        db,
        page,
        page_size,
        transaction_type,
        material_id,
        warehouse_id,
        source_type,
        date_from,
        date_to,
        source_no,
        material_ids,
    )
    materials = _material_map(db, [r.material_id for r in rows])
    items = [_transaction_dict(row, materials) for row in rows]
    return items, total


def _transaction_dict(
    row: models.InvTransaction, materials: Dict[int, Dict[str, Any]]
) -> Dict[str, Any]:
    material = materials.get(row.material_id, {})
    return {
        "id": row.id,
        "transaction_no": row.transaction_no,
        "transaction_type": row.transaction_type,
        "material_id": row.material_id,
        "material_code": material.get("material_code"),
        "material_name": material.get("material_name"),
        "warehouse_id": row.warehouse_id,
        "location_id": row.location_id,
        "quantity_change": _as_decimal(row.quantity_change),
        "quantity_after": _as_decimal(row.quantity_after),
        "unit_cost": _as_decimal(row.unit_cost),
        "biz_date": row.biz_date,
        "source_module": row.source_module,
        "source_type": row.source_type,
        "source_reference_id": row.source_reference_id,
        "source_no": row.source_no,
        "operator_id": row.operator_id,
        "remark": row.remark,
        "created_at": row.created_at,
    }


def get_transaction(db: Session, transaction_id: int) -> Dict[str, Any]:
    row = repository.get_transaction(db, transaction_id)
    if not row:
        raise BusinessException(CODE_NOT_FOUND, f"库存流水不存在：{transaction_id}")
    return _transaction_dict(row, _material_map(db, [row.material_id]))


# ==================== 移库 ====================


def list_transfers(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    from_warehouse_id: Optional[int] = None,
):
    return repository.list_transfers(db, page, page_size, status, from_warehouse_id)


def get_transfer(db: Session, transfer_id: int) -> models.InvTransfer:
    transfer = repository.get_transfer(db, transfer_id)
    if not transfer:
        raise BusinessException(CODE_NOT_FOUND, f"移库单不存在：{transfer_id}")
    return transfer


def create_transfer(
    db: Session,
    *,
    from_warehouse_id: int,
    to_warehouse_id: int,
    transfer_date: date,
    items: Sequence[Mapping[str, Any]],
    transfer_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.InvTransfer:
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "移库单至少需要一条明细")
    _require_warehouse(db, from_warehouse_id)
    _require_warehouse(db, to_warehouse_id)
    if transfer_no and repository.get_transfer_by_no(db, transfer_no):
        raise BusinessException(CODE_DUPLICATE, f"移库单号已存在：{transfer_no}")
    number = transfer_no or repository.next_transfer_no(db, transfer_date)
    transfer = models.InvTransfer(
        transfer_no=number,
        from_warehouse_id=from_warehouse_id,
        to_warehouse_id=to_warehouse_id,
        transfer_date=transfer_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_transfer(db, transfer)
    for raw in items:
        qty = _as_decimal(raw.get("quantity"))
        if qty <= 0:
            raise BusinessException(CODE_PARAM_INVALID, "移库数量必须为正数")
        _require_material(db, raw["material_id"])
        from_loc = raw.get("from_location_id")
        to_loc = raw.get("to_location_id")
        if from_loc is not None:
            _require_location(db, from_loc, from_warehouse_id)
        if to_loc is not None:
            _require_location(db, to_loc, to_warehouse_id)
        if from_warehouse_id == to_warehouse_id and from_loc == to_loc:
            raise BusinessException(CODE_PARAM_INVALID, "移库源与目标不能相同")
        repository.add_transfer_item(
            db,
            models.InvTransferItem(
                transfer_id=transfer.id,
                material_id=raw["material_id"],
                from_location_id=from_loc,
                to_location_id=to_loc,
                quantity=qty,
                remark=raw.get("remark"),
            ),
        )
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="inv_transfer",
        target_id=transfer.id,
        operator_id=operator_id,
        detail=f"新增移库单 {number}",
    )
    return transfer


def confirm_transfer(
    db: Session, transfer_id: int, operator_id: Optional[int] = None
) -> models.InvTransfer:
    """确认移库：对每条明细写 TRANSFER_OUT + TRANSFER_IN 两条流水（同一事务）。"""
    transfer = get_transfer(db, transfer_id)
    if transfer.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, f"移库单当前状态为 {transfer.status}，不能确认")
    items = list(transfer.items)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "移库单没有明细，不能确认")
    for item in items:
        _decrease_stock(
            db,
            transaction_type="TRANSFER_OUT",
            material_id=item.material_id,
            quantity=_as_decimal(item.quantity),
            warehouse_id=transfer.from_warehouse_id,
            location_id=item.from_location_id,
            source_module=MODULE,
            source_type="TRANSFER",
            source_reference_id=transfer.id,
            source_no=transfer.transfer_no,
            biz_date=transfer.transfer_date,
            operator_id=operator_id,
            remark=f"移库出库 {transfer.transfer_no}",
        )
        _increase_stock(
            db,
            transaction_type="TRANSFER_IN",
            material_id=item.material_id,
            quantity=_as_decimal(item.quantity),
            warehouse_id=transfer.to_warehouse_id,
            location_id=item.to_location_id,
            source_module=MODULE,
            source_type="TRANSFER",
            source_reference_id=transfer.id,
            source_no=transfer.transfer_no,
            biz_date=transfer.transfer_date,
            operator_id=operator_id,
            remark=f"移库入库 {transfer.transfer_no}",
        )
    transfer.status = "COMPLETED"
    transfer.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="inv_transfer",
        target_id=transfer.id,
        operator_id=operator_id,
        detail=f"确认移库单 {transfer.transfer_no}",
    )
    return transfer


def cancel_transfer(
    db: Session, transfer_id: int, operator_id: Optional[int] = None
) -> models.InvTransfer:
    transfer = get_transfer(db, transfer_id)
    if transfer.status != "DRAFT":
        raise BusinessException(CODE_STATUS_INVALID, f"移库单当前状态为 {transfer.status}，不能取消")
    transfer.status = "CANCELLED"
    transfer.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="inv_transfer",
        target_id=transfer.id,
        operator_id=operator_id,
        detail=f"取消移库单 {transfer.transfer_no}",
    )
    return transfer


# ==================== 盘点 ====================


def list_stocktakes(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    warehouse_id: Optional[int] = None,
    status: Optional[str] = None,
):
    return repository.list_stocktakes(db, page, page_size, warehouse_id, status)


def get_stocktake(db: Session, stocktake_id: int) -> models.InvStocktake:
    stocktake = repository.get_stocktake(db, stocktake_id)
    if not stocktake:
        raise BusinessException(CODE_NOT_FOUND, f"盘点单不存在：{stocktake_id}")
    return stocktake


def create_stocktake(
    db: Session,
    *,
    warehouse_id: int,
    stocktake_date: date,
    items: Sequence[Mapping[str, Any]],
    stocktake_no: Optional[str] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.InvStocktake:
    """新增盘点单；`book_qty` 缺省时按当前结存自动带出。"""
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "盘点单至少需要一条明细")
    _require_warehouse(db, warehouse_id)
    if stocktake_no and repository.get_stocktake_by_no(db, stocktake_no):
        raise BusinessException(CODE_DUPLICATE, f"盘点单号已存在：{stocktake_no}")
    number = stocktake_no or repository.next_stocktake_no(db, stocktake_date)
    stocktake = models.InvStocktake(
        stocktake_no=number,
        warehouse_id=warehouse_id,
        stocktake_date=stocktake_date,
        status="DRAFT",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_stocktake(db, stocktake)
    for raw in items:
        _require_material(db, raw["material_id"])
        location_id = raw.get("location_id")
        if location_id is not None:
            _require_location(db, location_id, warehouse_id)
        actual = _as_decimal(raw.get("actual_qty"))
        book_value = raw.get("book_qty")
        if book_value is None:
            balance = repository.get_balance(db, warehouse_id, location_id, raw["material_id"])
            book_value = _as_decimal(balance.quantity) if balance else Decimal("0")
        book = _as_decimal(book_value)
        repository.add_stocktake_item(
            db,
            models.InvStocktakeItem(
                stocktake_id=stocktake.id,
                material_id=raw["material_id"],
                location_id=location_id,
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
        target_type="inv_stocktake",
        target_id=stocktake.id,
        operator_id=operator_id,
        detail=f"新增盘点单 {number}",
    )
    return stocktake


def confirm_stocktake(
    db: Session, stocktake_id: int, operator_id: Optional[int] = None
) -> models.InvStocktake:
    """确认盘点：按差异写 `ADJUST` 流水（差异为 0 的行不写流水）。"""
    stocktake = get_stocktake(db, stocktake_id)
    if stocktake.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"盘点单当前状态为 {stocktake.status}，不能确认"
        )
    items = list(stocktake.items)
    if not items:
        raise BusinessException(CODE_PARAM_INVALID, "盘点单没有明细，不能确认")
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
            warehouse_id=stocktake.warehouse_id,
            location_id=item.location_id,
            delta=difference,
            biz_date=stocktake.stocktake_date,
            source_module=MODULE,
            source_type="STOCKTAKE",
            source_reference_id=stocktake.id,
            source_no=stocktake.stocktake_no,
            operator_id=operator_id,
            remark=f"盘点调整 {stocktake.stocktake_no}",
        )
    stocktake.status = "COMPLETED"
    stocktake.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CONFIRM",
        target_type="inv_stocktake",
        target_id=stocktake.id,
        operator_id=operator_id,
        detail=f"确认盘点单 {stocktake.stocktake_no}",
    )
    return stocktake


def cancel_stocktake(
    db: Session, stocktake_id: int, operator_id: Optional[int] = None
) -> models.InvStocktake:
    stocktake = get_stocktake(db, stocktake_id)
    if stocktake.status != "DRAFT":
        raise BusinessException(
            CODE_STATUS_INVALID, f"盘点单当前状态为 {stocktake.status}，不能取消"
        )
    stocktake.status = "CANCELLED"
    stocktake.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="CANCEL",
        target_type="inv_stocktake",
        target_id=stocktake.id,
        operator_id=operator_id,
        detail=f"取消盘点单 {stocktake.stocktake_no}",
    )
    return stocktake


# ==================== 订货点规则 ====================


def list_reorder_rules(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    rows, total = repository.list_reorder_rules(
        db, page, page_size, status, material_id, warehouse_id
    )
    materials = _material_map(db, [r.material_id for r in rows])
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
                "reorder_point": _as_decimal(row.reorder_point),
                "reorder_quantity": _as_decimal(row.reorder_quantity),
                "status": row.status,
                "remark": row.remark,
            }
        )
    return items, total


def get_reorder_rule(db: Session, rule_id: int) -> models.InvReorderRule:
    rule = repository.get_reorder_rule(db, rule_id)
    if not rule:
        raise BusinessException(CODE_NOT_FOUND, f"订货点规则不存在：{rule_id}")
    return rule


def create_reorder_rule(
    db: Session,
    *,
    material_id: int,
    warehouse_id: int,
    reorder_point: Decimal,
    reorder_quantity: Decimal,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.InvReorderRule:
    _require_material(db, material_id)
    _require_warehouse(db, warehouse_id)
    if repository.get_reorder_rule_by_pair(db, material_id, warehouse_id):
        raise BusinessException(CODE_DUPLICATE, "该物料在此仓库的订货点规则已存在")
    rule = models.InvReorderRule(
        material_id=material_id,
        warehouse_id=warehouse_id,
        reorder_point=_as_decimal(reorder_point),
        reorder_quantity=_as_decimal(reorder_quantity),
        status="ACTIVE",
        remark=remark,
        created_by=operator_id,
    )
    repository.add_reorder_rule(db, rule)
    log_operation(
        db,
        module=MODULE,
        action="CREATE",
        target_type="inv_reorder_rule",
        target_id=rule.id,
        operator_id=operator_id,
        detail=f"新增订货点规则 物料{material_id}/仓库{warehouse_id}",
    )
    return rule


def update_reorder_rule(
    db: Session,
    rule_id: int,
    *,
    reorder_point: Optional[Decimal] = None,
    reorder_quantity: Optional[Decimal] = None,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> models.InvReorderRule:
    rule = get_reorder_rule(db, rule_id)
    if reorder_point is not None:
        rule.reorder_point = _as_decimal(reorder_point)
    if reorder_quantity is not None:
        rule.reorder_quantity = _as_decimal(reorder_quantity)
    if remark is not None:
        rule.remark = remark
    rule.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="UPDATE",
        target_type="inv_reorder_rule",
        target_id=rule.id,
        operator_id=operator_id,
        detail=f"修改订货点规则 {rule.id}",
    )
    return rule


def set_reorder_rule_status(
    db: Session, rule_id: int, status: str, operator_id: Optional[int] = None
) -> models.InvReorderRule:
    if status not in _RECORD_STATUS:
        raise BusinessException(CODE_PARAM_INVALID, f"非法状态：{status}")
    rule = get_reorder_rule(db, rule_id)
    rule.status = status
    rule.updated_by = operator_id
    log_operation(
        db,
        module=MODULE,
        action="STATUS",
        target_type="inv_reorder_rule",
        target_id=rule.id,
        operator_id=operator_id,
        detail=f"订货点规则 {rule.id} 状态改为 {status}",
    )
    return rule


def list_reorder_suggestions(db: Session) -> List[Dict[str, Any]]:
    """对所有 ACTIVE 规则，现存量低于订货点的返回补库建议。"""
    suggestions: List[Dict[str, Any]] = []
    for rule in repository.list_active_reorder_rules(db):
        current = repository.sum_quantity(db, rule.material_id, rule.warehouse_id)
        point = _as_decimal(rule.reorder_point)
        if current >= point:
            continue
        suggested = _as_decimal(rule.reorder_quantity)
        suggestions.append(
            {
                "material_id": rule.material_id,
                "warehouse_id": rule.warehouse_id,
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
    """出入库汇总：按流水类型 + 物料统计数量合计（出库为负）。"""
    if date_from > date_to:
        raise BusinessException(CODE_PARAM_INVALID, "开始日期不能晚于结束日期")
    rows = repository.aggregate_flow(db, date_from, date_to)
    materials = _material_map(db, [mid for _, mid, _ in rows])
    result = []
    for transaction_type, material_id, total in rows:
        material = materials.get(material_id, {})
        result.append(
            {
                "transaction_type": transaction_type,
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
        "location_count": repository.count_all(db, models.InvLocation),
        "balance_count": repository.count_all(db, models.InvBalance),
        "transaction_count": repository.count_all(db, models.InvTransaction),
        "transfer_count": repository.count_all(db, models.InvTransfer),
        "stocktake_count": repository.count_all(db, models.InvStocktake),
        "reorder_rule_count": repository.count_all(db, models.InvReorderRule),
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
    location_id: Optional[int],
    rows: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """逐行校验：物料编码必须存在、数量必须为正；未知编码记为错误而非静默跳过。"""
    if location_id is not None:
        _require_location(db, location_id, warehouse_id)
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
    location_id: Optional[int] = None,
    rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """期初库存导入预览：**只校验、不写任何数据**（规格 §37）。"""
    warehouse = _resolve_import_warehouse(db, warehouse_id, warehouse_code)
    collected = _collect_import_rows(source, rows)
    entries, errors = _validate_import_rows(
        db, warehouse_id=warehouse.id, location_id=location_id, rows=collected
    )
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
    location_id: Optional[int] = None,
    rows: Optional[Sequence[Mapping[str, Any]]] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """确认期初库存导入：重新校验后逐行走 `increase_stock`（写真实流水），同一事务内完成。"""
    warehouse = _resolve_import_warehouse(db, warehouse_id, warehouse_code)
    collected = _collect_import_rows(source, rows)
    entries, errors = _validate_import_rows(
        db, warehouse_id=warehouse.id, location_id=location_id, rows=collected
    )
    imported = 0
    for entry in entries:
        if entry["status"] != "VALID":
            continue
        increase_stock(
            db,
            material_id=entry["material_id"],
            quantity=entry["quantity"],
            warehouse_id=warehouse.id,
            location_id=location_id,
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