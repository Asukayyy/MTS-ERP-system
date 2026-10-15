"""planning 派工单 / 领料单：新增来源字段（支持按生产作业计划自动生成）

数据变更：
- `pln_dispatch_order` / `pln_material_requisition` 新增
  `source_type`（MANUAL/PLAN）与 `source_reference_id`，用于记录生成来源
  生产作业计划（`pln_production_plan.id`）并实现"按来源幂等判重"。
- 既有数据回填为 MANUAL。
- `pln_dispatch_order.operation` 由 VARCHAR(60) 放宽到 VARCHAR(100)，
  以容纳工艺路线工序名称（`sys_routing_operation.operation_name` 为 VARCHAR(100)）。
- 新增来源复合索引与 `source_type` CHECK 约束。

Revision ID: a1c8f4d2e9b7
Revises: e7a1b9c4d208
Create Date: 2026-10-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "a1c8f4d2e9b7"
down_revision: Union[str, None] = "e7a1b9c4d208"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_TABLES = ("pln_dispatch_order", "pln_material_requisition")


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


def _constraint_exists(bind, table: str, name: str) -> bool:
    return bool(
        bind.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = :t AND CONSTRAINT_NAME = :c"
            ),
            {"t": table, "c": name},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 来源字段：先带 server_default 新增（回填既有行），再撤掉默认值以对齐模型定义
    for table in SOURCE_TABLES:
        if not _column_exists(bind, table, "source_type"):
            op.add_column(
                table,
                sa.Column(
                    "source_type",
                    sa.String(20),
                    nullable=False,
                    server_default="MANUAL",
                    comment="来源 MANUAL/PLAN",
                ),
            )
            op.alter_column(table, "source_type", server_default=None)
        if not _column_exists(bind, table, "source_reference_id"):
            op.add_column(
                table,
                sa.Column(
                    "source_reference_id",
                    sa.Integer(),
                    nullable=True,
                    comment="来源单据ID（source_type=PLAN 时为 pln_production_plan.id）",
                ),
            )

    # 2. 派工单工序名放宽到 100（工艺路线工序名称口径）
    op.alter_column(
        "pln_dispatch_order",
        "operation",
        existing_type=sa.String(60),
        type_=sa.String(100),
        existing_nullable=True,
        existing_comment="工序",
        comment="工序（工艺路线工序名称，最长 100）",
    )

    # 3. 来源复合索引
    if not _index_exists(bind, "pln_dispatch_order", "ix_pln_dispatch_order_source"):
        op.create_index(
            "ix_pln_dispatch_order_source",
            "pln_dispatch_order",
            ["source_type", "source_reference_id"],
        )
    if not _index_exists(bind, "pln_material_requisition", "ix_pln_material_requisition_source"):
        op.create_index(
            "ix_pln_material_requisition_source",
            "pln_material_requisition",
            ["source_type", "source_reference_id"],
        )

    # 4. 来源枚举 CHECK 约束（MySQL 不会自动生成，需显式补齐）
    if not _constraint_exists(bind, "pln_dispatch_order", "ck_pln_dispatch_source"):
        op.create_check_constraint(
            "ck_pln_dispatch_source", "pln_dispatch_order", "source_type IN ('MANUAL','PLAN')"
        )
    if not _constraint_exists(bind, "pln_material_requisition", "ck_pln_requisition_source"):
        op.create_check_constraint(
            "ck_pln_requisition_source", "pln_material_requisition", "source_type IN ('MANUAL','PLAN')"
        )


def downgrade() -> None:
    bind = op.get_bind()

    # 严格逆序：约束 → 索引 → operation 回 VARCHAR(60) → 列
    if _constraint_exists(bind, "pln_material_requisition", "ck_pln_requisition_source"):
        op.drop_constraint("ck_pln_requisition_source", "pln_material_requisition", type_="check")
    if _constraint_exists(bind, "pln_dispatch_order", "ck_pln_dispatch_source"):
        op.drop_constraint("ck_pln_dispatch_source", "pln_dispatch_order", type_="check")

    if _index_exists(bind, "pln_material_requisition", "ix_pln_material_requisition_source"):
        op.drop_index("ix_pln_material_requisition_source", table_name="pln_material_requisition")
    if _index_exists(bind, "pln_dispatch_order", "ix_pln_dispatch_order_source"):
        op.drop_index("ix_pln_dispatch_order_source", table_name="pln_dispatch_order")

    op.alter_column(
        "pln_dispatch_order",
        "operation",
        existing_type=sa.String(100),
        type_=sa.String(60),
        existing_nullable=True,
        existing_comment="工序（工艺路线工序名称，最长 100）",
        comment="工序",
    )

    for table in SOURCE_TABLES:
        if _column_exists(bind, table, "source_reference_id"):
            op.drop_column(table, "source_reference_id")
        if _column_exists(bind, table, "source_type"):
            op.drop_column(table, "source_type")
