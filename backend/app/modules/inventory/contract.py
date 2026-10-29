"""inventory 模块跨模块契约（**唯一对外入口**）。

规则（规格 §7 / §14 / §24 / §35）：

1. 其它模块**只允许** import 本文件，禁止 import inventory 的 `models` / `repository` / `service`。
2. **本文件的函数永不 `db.commit()`**：它们运行在调用方的事务里，保证
   “结存变动 + 调用方业务单据” 要么一起成功、要么一起回滚（规格 §35）。
3. 只返回普通 `dict` / 标量，不返回 ORM 对象，避免会话与懒加载外泄。
4. 签名一经确定即视为公共接口，修改需同步其它模块。

库存变动唯一入口：
- `increase_stock` / `decrease_stock`：**仅供库存管理模块内部（仓库确认）调用**。
  业务模块（销售 / 采购 / 计划）**不再直接改库存**，一律改用下面的
  `push_inbound_order` / `push_outbound_order` 推送待办单据。
- `push_inbound_order` / `push_outbound_order`：把业务单据（发货 / 退货 / 到货 /
  领料 / 完工）登记为库存管理的入库单 / 出库单（状态 DRAFT，**不改结存**），
  由仓库管理人员在「库存管理 → 入库管理 / 出库管理」里指定仓库并确认。
- `cancel_pending_inout_orders`：业务单据取消 / 作废时撤销尚未确认的出入库单。
- `create_replenishment_request`：库存不足时**只产生补库需求**，
  不直接创建正式生产/采购计划（规格 §14），由 planning / procurement 受理。
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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


def get_available_by_warehouse(db: Session, material_id: int) -> List[Dict[str, Any]]:
    """某物料各仓库可用量明细（可用量 > 0），按可用量倒序。

    返回 `[{"warehouse_id", "on_hand", "available"}]`；供 Sales 在订单确认时
    把可用库存分配到具体仓库并生成发货草稿。
    """
    return service.get_available_by_warehouse(db, material_id)


def get_warehouse_names(
    db: Session, warehouse_ids: Sequence[int]
) -> Dict[int, Dict[str, str]]:
    """批量取仓库编码 / 名称，用于其它模块列表展示。

    返回 `{warehouse_id: {"warehouse_code", "warehouse_name"}}`。
    """
    return service.get_warehouse_names(db, warehouse_ids)


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
    source_module: str,
    source_type: str,
    source_reference_id: Optional[int] = None,
    source_no: Optional[str] = None,
    unit_cost: Decimal = Decimal("0"),
    biz_date: Optional[date] = None,
    operator_id: Optional[int] = None,
    remark: Optional[str] = None,
) -> Dict[str, Any]:
    """入库：直接加结存。返回 `{"quantity_after"}`。"""
    return service.increase_stock(
        db,
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
    """出库：事务内加锁复核可用量，不足抛 `BusinessException(5001)`；直接减结存。"""
    return service.decrease_stock(
        db,
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


def push_inout_order(
    db: Session,
    *,
    op_type: str,
    op_date: date,
    items: Sequence[Dict[str, Any]],
    source_module: str,
    source_type: str,
    source_reference_id: int,
    source_no: str,
    remark: Optional[str] = None,
    operator_id: Optional[int] = None,
) -> Dict[str, Any]:
    """业务单据推送入库 / 出库单（**只登记待办，不改结存**）。

    参数：
    - `op_type`：`INBOUND` 入库 / `OUTBOUND` 出库；
    - `items`：`[{"material_id", "quantity", "remark"}]`，数量必须为正整数；
    - `source_module` / `source_type` / `source_reference_id` / `source_no`：来源单据信息，
      会写进单据头并展示在库存管理列表中（source_type 见 `SOURCE_TYPE_NAMES`）；
    - 同一来源单据已存在待处理单时直接返回原单，重复推送幂等。

    返回 `{"operation_id", "operation_no", "created"}`；**不指定仓库**，
    仓库由仓库管理人员在确认时选择。
    """
    operation = service.push_inout_order(
        db,
        op_type=op_type,
        op_date=op_date,
        items=items,
        source_module=source_module,
        source_type=source_type,
        source_reference_id=source_reference_id,
        source_no=source_no,
        remark=remark,
        operator_id=operator_id,
    )
    return {
        "operation_id": operation.id,
        "operation_no": operation.operation_no,
        "created": operation.status == "DRAFT",
    }


def push_inbound_order(db: Session, **kwargs: Any) -> Dict[str, Any]:
    """推送入库单（采购到货 / 销售退货 / 完工入库）。"""
    return push_inout_order(db, op_type="INBOUND", **kwargs)


def push_outbound_order(db: Session, **kwargs: Any) -> Dict[str, Any]:
    """推送出库单（销售发货 / 生产领料）。"""
    return push_inout_order(db, op_type="OUTBOUND", **kwargs)


def cancel_pending_inout_orders(
    db: Session,
    *,
    source_module: str,
    source_type: str,
    source_reference_id: int,
    operator_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> int:
    """撤销某来源单据尚未被仓库确认的出入库单，返回撤销数量。"""
    return service.cancel_pending_inout_orders(
        db,
        source_module=source_module,
        source_type=source_type,
        source_reference_id=source_reference_id,
        operator_id=operator_id,
        reason=reason,
    )


def get_inout_status_map(
    db: Session, sources: Iterable[Tuple[str, str, int]]
) -> Dict[Tuple[str, str, int], Dict[str, Any]]:
    """批量查来源单据对应的库存单据状态。

    返回 `{(module, source_type, reference_id): {"operation_no", "status", ...}}`，
    供业务列表展示「库存单号 / 库存单状态」（DRAFT 待仓库处理 / COMPLETED 已出入库）。
    """
    return service.get_inout_status_map(db, list(sources))


def get_source_type_names() -> Dict[str, str]:
    """来源业务类型中文名映射（前端 / 列表展示用）。"""
    return dict(service.SOURCE_TYPE_NAMES)


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


def list_replenishment_requests(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 100,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    material_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """按条件分页读取补库需求单（只读，不提交事务）。返回 `(items, total)`。"""
    return service.list_replenishment_requests(
        db,
        page=page,
        page_size=page_size,
        status=status,
        source_type=source_type,
        material_id=material_id,
    )