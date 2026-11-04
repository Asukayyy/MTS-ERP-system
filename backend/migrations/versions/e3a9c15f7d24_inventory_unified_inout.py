"""库存集中出入库：库存单据支持 INBOUND / OUTBOUND + 来源字段 + 物料快照

背景（规格调整）：
    全系统出入库统一收口到库存管理模块。销售发货（出库）、销售退货（入库）、
    采购到货（入库）、生产领料（出库）、完工入库（入库）不再自行改结存、也不再
    指定仓库，改为向库存管理推送「待出入库单」，由仓库管理人员在
    库存管理 → 入库管理 / 出库管理 中决定仓库并确认后才真正变动结存。

数据变更：
1. `inv_stock_operation.op_type` 放开到 `TRANSFER / STOCKTAKE / INBOUND / OUTBOUND`；
2. `inv_stock_operation` 新增来源字段 `source_module / source_type /
   source_reference_id / source_no` 与 `confirmed_at`，并建来源索引；
3. `inv_stock_operation_item` 新增物料快照 `material_code / material_name /
   material_spec / unit`，保证仓库人员无需跳转即可看到完整物料信息；
4. `sal_shipment_item.warehouse_id`、`sal_return_item.warehouse_id`、
   `pur_receipt.warehouse_id` 改为可空：仓库由库存管理确认时决定，
   业务单据不再强制选择仓库。
5. 历史已完成单据的 `warehouse_id` 保持原值，不回填、不修改。

Revision ID: e3a9c15f7d24
Revises: f2b7c41d9e83
Create Date: 2026-10-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "e3a9c15f7d24"
down_revision: Union[str, None] = "f2b7c41d9e83"
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


def _constraint_exists(bind, table: str, name: str) -> bool:
    return bool(
        bind.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND CONSTRAINT_NAME = :n"
            ),
            {"t": table, "n": name},
        ).scalar()
    )


def _is_nullable(bind, table: str, column: str) -> bool:
    value = bind.execute(
        text(
            "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": column},
    ).scalar()
    return str(value).upper() == "YES"


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 放开单据类型
    if _constraint_exists(bind, "inv_stock_operation", "ck_inv_stock_op_type"):
        op.drop_constraint("ck_inv_stock_op_type", "inv_stock_operation", type_="check")
    op.create_check_constraint(
        "ck_inv_stock_op_type",
        "inv_stock_operation",
        "op_type IN ('TRANSFER','STOCKTAKE','INBOUND','OUTBOUND')",
    )

    # 2. 单据头来源字段
    if not _column_exists(bind, "inv_stock_operation", "source_module"):
        op.add_column(
            "inv_stock_operation",
            sa.Column("source_module", sa.String(32), nullable=True, comment="来源模块"),
        )
    if not _column_exists(bind, "inv_stock_operation", "source_type"):
        op.add_column(
            "inv_stock_operation",
            sa.Column("source_type", sa.String(64), nullable=True, comment="来源业务类型"),
        )
    if not _column_exists(bind, "inv_stock_operation", "source_reference_id"):
        op.add_column(
            "inv_stock_operation",
            sa.Column("source_reference_id", sa.BigInteger(), nullable=True, comment="来源单据ID"),
        )
    if not _column_exists(bind, "inv_stock_operation", "source_no"):
        op.add_column(
            "inv_stock_operation",
            sa.Column("source_no", sa.String(64), nullable=True, comment="来源单据号"),
        )
    if not _column_exists(bind, "inv_stock_operation", "confirmed_at"):
        op.add_column(
            "inv_stock_operation",
            sa.Column("confirmed_at", sa.DateTime(), nullable=True, comment="仓库确认出入库时间"),
        )
    if not _index_exists(bind, "inv_stock_operation", "idx_inv_stock_op_source"):
        op.create_index(
            "idx_inv_stock_op_source",
            "inv_stock_operation",
            ["source_module", "source_type", "source_reference_id"],
        )

    # 3. 明细物料快照
    for column, type_, comment in (
        ("material_code", sa.String(64), "物料编码快照"),
        ("material_name", sa.String(128), "物料名称快照"),
        ("material_spec", sa.String(200), "规格型号快照"),
        ("unit", sa.String(32), "计量单位快照"),
    ):
        if not _column_exists(bind, "inv_stock_operation_item", column):
            op.add_column(
                "inv_stock_operation_item",
                sa.Column(column, type_, nullable=True, comment=comment),
            )

    # 4. 业务单据不再强制选仓库
    for table in ("sal_shipment_item", "sal_return_item", "pur_receipt"):
        if _column_exists(bind, table, "warehouse_id") and not _is_nullable(
            bind, table, "warehouse_id"
        ):
            op.alter_column(
                table,
                "warehouse_id",
                existing_type=sa.BigInteger(),
                nullable=True,
                comment="仓库由库存管理确认出入库时指定（历史数据保留原值）",
            )


def downgrade() -> None:
    bind = op.get_bind()

    for column in ("material_code", "material_name", "material_spec", "unit"):
        if _column_exists(bind, "inv_stock_operation_item", column):
            op.drop_column("inv_stock_operation_item", column)

    if _index_exists(bind, "inv_stock_operation", "idx_inv_stock_op_source"):
        op.drop_index("idx_inv_stock_op_source", table_name="inv_stock_operation")
    for column in ("confirmed_at", "source_no", "source_reference_id", "source_type", "source_module"):
        if _column_exists(bind, "inv_stock_operation", column):
            op.drop_column("inv_stock_operation", column)

    # 回退前先把 INBOUND / OUTBOUND 单据标记为作废，避免约束回滚失败
    bind.execute(
        text(
            "UPDATE inv_stock_operation SET op_type = 'STOCKTAKE' "
            "WHERE op_type IN ('INBOUND','OUTBOUND')"
        )
    )
    if _constraint_exists(bind, "inv_stock_operation", "ck_inv_stock_op_type"):
        op.drop_constraint("ck_inv_stock_op_type", "inv_stock_operation", type_="check")
    op.create_check_constraint(
        "ck_inv_stock_op_type",
        "inv_stock_operation",
        "op_type IN ('TRANSFER','STOCKTAKE')",
    )

    # 仓库字段恢复非空前，先补齐历史空值（取任一可用仓库，避免回滚失败）
    fallback = bind.execute(text("SELECT id FROM inv_warehouse ORDER BY id LIMIT 1")).scalar()
    if fallback is not None:
        for table in ("sal_shipment_item", "sal_return_item", "pur_receipt"):
            if _column_exists(bind, table, "warehouse_id"):
                bind.execute(
                    text(
                        f"UPDATE {table} SET warehouse_id = :w WHERE warehouse_id IS NULL"
                    ),
                    {"w": fallback},
                )
