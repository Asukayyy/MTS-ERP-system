"""sales 模块跨模块契约（**唯一对外入口**）。

规则（规格 §7 / §24 / §35）：

1. 其它模块（Planning 等）**只允许** import 本文件，
   禁止 import sales 的 `models` / `repository` / `service`。
2. **本文件的函数永不 `db.commit()`**：它们可能运行在调用方（如 Planning）
   的事务里，保证“销售需求读取 + 调用方单据”要么一起成功、要么一起回滚。
3. 只返回普通 `dict` / `标量`，不返回 ORM 对象，避免会话与懒加载外泄。
4. 签名一经确定即视为公共接口，修改需同步其它模块：

   - `get_open_order_demand(db, on_date=None)` 未交付需求行
   - `get_confirmed_forecast_demand(db, month_from=None, month_to=None)` 已确认预测
   - `get_open_order_qty(db, material_id)` 某物料未交付订单数量
   - `get_customer_name(db, customer_id)` 客户名（缺失返回 None）
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.modules.sales import repository


def get_open_order_demand(db: Session, on_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """未交付需求行（供 MRP / 计划展开）。

    只统计状态 ∈ CONFIRMED/IN_PROGRESS 的订单，且 `quantity = quantity - delivered_qty > 0`。
    传入 `on_date` 时只返回要求交货日期不晚于该日的需求。

    返回 `[{"order_id", "order_no", "customer_id", "material_id", "quantity", "due_date"}]`。
    """
    rows = repository.open_order_demand_rows(db, on_date)
    return [
        {
            "order_id": row[0],
            "order_no": row[1],
            "customer_id": row[2],
            "material_id": row[3],
            "quantity": Decimal(str(row[4])),
            "due_date": row[5],
        }
        for row in rows
    ]


def get_confirmed_forecast_demand(
    db: Session,
    month_from: Optional[str] = None,
    month_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """已确认销售预测需求（只统计 CONFIRMED），可按月份区间过滤。

    返回 `[{"forecast_id", "forecast_no", "material_id", "quantity", "month"}]`。
    """
    rows = repository.confirmed_forecast_rows(db, month_from, month_to)
    return [
        {
            "forecast_id": row[0],
            "forecast_no": row[1],
            "material_id": row[2],
            "quantity": Decimal(str(row[3])),
            "month": row[4],
        }
        for row in rows
    ]


def get_open_order_qty(db: Session, material_id: int) -> Decimal:
    """某物料的未交付订单数量合计（CONFIRMED/IN_PROGRESS）。"""
    return repository.open_order_qty(db, material_id)


def get_customer_name(db: Session, customer_id: Optional[int]) -> Optional[str]:
    """取客户名称，用于其它模块展示（客户缺失返回 None，不抛异常）。"""
    if not customer_id:
        return None
    customer = repository.get_customer(db, int(customer_id))
    return customer.customer_name if customer else None