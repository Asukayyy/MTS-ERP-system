"""inventory 模块跨模块契约（**唯一对外入口**）。

规则（规格 §7 / §14 / §24 / §35）：

1. 其它模块**只允许** import 本文件，禁止 import inventory 的 `models` / `repository` / `service`。
2. **本文件的函数永不 `db.commit()`**：它们运行在调用方的事务里，保证
   “库存流水 + 结存 + 调用方业务单据” 要么一起成功、要么一起回滚（规格 §35）。
3. 只返回普通 `dict` / 标量，不返回 ORM 对象，避免会话与懒加载外泄。
4. 签名一经确定即视为公共接口，修改需同步其它模块。

库存变动唯一入口：
- `increase_stock` / `decrease_stock`：任何模块改库存都必须走这里，
  内部会同时写 `inv_transaction` 流水并更新 `inv_balance` 结存，且禁止负库存。
- `create_replenishment_request`：库存不足时**只产生补库需求**，
  不直接创建正式生产/采购计划（规格 §14），由 planning / procurement 受理。
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional, Sequence

from sqlalchemy.orm import Session

from app.modules.inventory import service


def get_on_hand_qty(
    db: Session, material_id: int, warehouse_id: Optional[int] = None
) -> Decimal:
    """取某物料现存量合计（可选限制仓库）。"""
    return service.get_on_hand_qty(db, material_id, warehouse_id)


def get_available_qty(
    db: Session, material_id: int, warehouse_id: Optional[int] = None
) -> Decimal:
    """取某物料可用量合计 = 现存量 - 锁定量（可选限制仓库）。"""
    return service.get_available_qty(db, material_id, warehouse_id)


def get_stock_snapshot(
    db: Session, material_ids: Sequence[int], warehouse_id: Optional[int] = None
) -> Dict[int, Dict[str, Decimal]]:
    """批量取库存快照 `{material_id: {"on_hand": Decimal, "available": Decimal}}`。"""
    return service.get_stock_snapshot(db, material_ids, warehouse_id)


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
    """入库：写 `IN` 流水 + 加结存。返回 `{"transaction_id", "transaction_no", "quantity_after"}`。"""
    return service.increase_stock(
        db,
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
    """出库：事务内加锁复核可用量，不足抛 `BusinessException(5001)`；写 `OUT` 流水 + 减结存。"""
    return service.decrease_stock(
        db,
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
    """创建补库需求单（DRAFT）。返回 `{"id", "request_no"}`；不直接创建正式计划。"""
    return service.create_replenishment_request(
        db,
        material_id=material_id,
        warehouse_id=warehouse_id,
        request_qty=request_qty,
        required_date=required_date,
        source_type=source_type,
        current_qty=current_qty,
        target_qty=target_qty,
        remark=remark,
        operator_id=operator_id,
    )


def get_replenishment_request(db: Session, request_id: int) -> Optional[Dict[str, Any]]:
    """按 ID 读取补库需求单（只读，不提交事务）。不存在返回 None。"""
    return service.get_replenishment_request_dict(db, request_id)