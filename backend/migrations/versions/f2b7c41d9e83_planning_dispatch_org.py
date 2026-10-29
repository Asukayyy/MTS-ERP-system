"""planning 派工单：新增承接单位 `org_id`（整单派给智能加工中心）

背景（规格调整）：
    车间不再按工艺路线逐工序生成派工单（一张计划会膨胀成 4~6 张），
    改为「一张生产作业计划 → 一张派工单」，整单派给承接单位
    （`sys_organization` 中的智能加工中心），再由加工中心自行把任务
    分派给具体作业人员。

数据变更：
- `pln_dispatch_order` 新增 `org_id`（`sys_organization.id`，可空）与索引。
- 既有数据不回填：历史派工单保留原工序与作业人员信息，仅新单据使用承接单位。

Revision ID: f2b7c41d9e83
Revises: d1f7a3c9b260
Create Date: 2026-10-29

说明：`d1f7a3c9b260`（销售产品价格）已先合入 develop，本迁移顺延挂在其后，
保持单 head，避免 `alembic upgrade head` 因分叉失败。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "f2b7c41d9e83"
down_revision: Union[str, None] = "d1f7a3c9b260"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def _index_exists(bind, table: str, index: str) -> bool:
    return bool(
        bind.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i"
            ),
            {"t": table, "i": index},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _column_exists(bind, "pln_dispatch_order", "org_id"):
        op.add_column(
            "pln_dispatch_order",
            sa.Column(
                "org_id",
                sa.BigInteger(),
                nullable=True,
                comment="承接单位（sys_organization.id，加工中心 / 车间）",
            ),
        )
        op.create_foreign_key(
            "fk_pln_dispatch_order_org",
            "pln_dispatch_order",
            "sys_organization",
            ["org_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    if not _index_exists(bind, "pln_dispatch_order", "ix_pln_dispatch_order_org_id"):
        op.create_index("ix_pln_dispatch_order_org_id", "pln_dispatch_order", ["org_id"])


def downgrade() -> None:
    bind = op.get_bind()

    if _index_exists(bind, "pln_dispatch_order", "ix_pln_dispatch_order_org_id"):
        op.drop_index("ix_pln_dispatch_order_org_id", table_name="pln_dispatch_order")
    if _column_exists(bind, "pln_dispatch_order", "org_id"):
        op.drop_constraint(
            "fk_pln_dispatch_order_org", "pln_dispatch_order", type_="foreignkey"
        )
        op.drop_column("pln_dispatch_order", "org_id")
