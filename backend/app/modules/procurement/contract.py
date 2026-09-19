"""procurement 模块跨模块契约（**唯一对外入口**）。

规则（规格 §7 / §14 / §24 / §35）：

1. 其它模块**只允许** import 本文件，禁止 import procurement 的
   `models` / `repository` / `service`。
2. **本文件的函数永不 `db.commit()`**：它们运行在调用方的事务里，保证
   “上游业务单据 + 采购计划单据” 要么一起成功、要么一起回滚。
3. 只返回普通 `dict` / 标量，不返回 ORM 对象。
4. 签名一经确定即视为公共接口，修改需同步其它模块。

主要调用方：

- Inventory：确认 `REORDER` 订货点补库需求时调用
  `create_purchase_plan_from_replenishment`，把补库需求转成正式采购计划。
- Planning：从 MRP 的 `BUY` 结果生成采购计划时调用 `create_purchase_plan_from_mrp`；
  净需求计算可调用 `get_pending_receipt_qty` 参考在途未到货数量。
"""

from decimal import Decimal
from typing import Any, Dict, Sequence

from sqlalchemy.orm import Session

from app.modules.procurement import service


def create_purchase_plan_from_mrp(
    db: Session, mrp_result_ids: Sequence[int]
) -> Dict[str, Any]:
    """从 Planning 的 MRP `BUY` 结果生成采购计划（头 + 行）。

    - 行 `source_type="MRP"`、`source_reference_id=mrp_result.id`，
      数量取 `order_qty`、需求日期取 `requirement_date`；
    - 明细通过 `planning.contract.get_mrp_results(db, mrp_result_ids)` 读取（惰性 import）；
    - **幂等**：同一 `source_reference_id` 已受理且计划未终结时复用该计划并只补新增行，
      已终结的计划不再扩展，改为新建计划；
    - 返回 `{"plan_id": int, "plan_no": str}`；**不提交事务**，由调用方提交。
    """
    return service.create_purchase_plan_from_mrp(db, mrp_result_ids)


def create_purchase_plan_from_replenishment(db: Session, request_id: int) -> Dict[str, Any]:
    """受理 Inventory 的订货点补库需求：生成采购计划并返回其引用。

    - 行 `source_type="REORDER"`、`source_reference_id=request_id`；
    - 需求明细通过 `inventory.contract.get_replenishment_request(db, request_id)` 读取
      （惰性 import，契约未就绪时抛 4007）；
    - **幂等**：同一 `request_id` 已受理且计划未终结时复用该计划，不重复建单；
    - 返回 `{"plan_id": int, "plan_no": str}`；**不提交事务**，由调用方提交。
    """
    return service.create_purchase_plan_from_replenishment(db, request_id)


def get_pending_receipt_qty(db: Session, material_id: int) -> Decimal:
    """该物料所有在途未到货采购订单行的剩余数量合计，供 Planning / 库存预警参考。"""
    return service.get_pending_receipt_qty(db, material_id)