"""inventory 4 张表：删除流水表 + 订货点字段改为可选

数据变更：
- 删除 `inv_transaction` 库存流水表（库存变动由业务单据直接驱动结存）。
- `inv_balance.reorder_point` / `reorder_quantity` 改为 NULLABLE，
  默认 NULL（仅 A 类高价值关键物料配置订货点）。
- 现有数据中 reorder_point=0 的行改为 NULL，便于前端区分"未配置"。

Revision ID: c4d2e1f3a6b0
Revises: b7f3c2a91d04
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "c4d2e1f3a6b0"
down_revision: Union[str, None] = "b7f3c2a91d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table: str) -> bool:
    return bool(
        bind.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :t"),
            {"t": table},
        ).scalar()
    )


def _column_exists(bind, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    # 1. reorder_point / reorder_quantity 先改为 NULLABLE
    op.alter_column(
        "inv_balance",
        "reorder_point",
        existing_type=sa.Numeric(18, 4),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "inv_balance",
        "reorder_quantity",
        existing_type=sa.Numeric(18, 4),
        nullable=True,
        server_default=None,
    )

    # 2. 现有 reorder_point=0 / reorder_quantity=0 改为 NULL（区分"未配置"与"配置为0"）
    bind.execute(text("UPDATE inv_balance SET reorder_point = NULL WHERE reorder_point = 0"))
    bind.execute(text("UPDATE inv_balance SET reorder_quantity = NULL WHERE reorder_quantity = 0"))

    # 3. 旧的 reorder_point/reorder_quantity CHECK 约束不存在于当前库（MySQL 解析时忽略），
    #    且 NULL 值对 `>= 0` 约束天然放行，无需重建约束。

    # 4. 删除 inv_transaction 流水表
    if _table_exists(bind, "inv_transaction"):
        op.drop_table("inv_transaction")


def downgrade() -> None:
    # 不可逆：流水表数据已丢弃，无法恢复
    raise NotImplementedError("本迁移不可逆（流水表已删除）")
