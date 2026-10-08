"""inventory 5 张概念表合并：库位并入仓库、订货点并入结存、移库+盘点合并为操作单

数据变更：
- `inv_warehouse` 增加 location_code / location_name 文本字段（原 inv_location 并入）。
- `inv_balance` 增加 reorder_point / reorder_quantity（原 inv_reorder_rule 回填），
  按 (warehouse_id, material_id) 合并多库位结存行，删除 location 维度。
- `inv_transfer` + `inv_transfer_item`、`inv_stocktake` + `inv_stocktake_item`
  数据迁入 `inv_stock_operation` + `inv_stock_operation_item`（op_type 区分）。
- 各模块明细表的 location_id 列（含外键）删除。
- 旧表 inv_location / inv_reorder_rule / inv_transfer(_item) / inv_stocktake(_item) 删除。

注意：MySQL DDL 非事务，本迁移做了幂等保护（列/表存在性检查、重跑前清空新表），
中断后可直接重新执行。

Revision ID: b7f3c2a91d04
Revises: f5e52ee720d6
Create Date: 2026-09-24
"""

from typing import List, Sequence, Tuple, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "b7f3c2a91d04"
down_revision: Union[str, None] = "f5e52ee720d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ------------------------------------------------------------------
# 辅助：MySQL 外键名是自动生成的（如 inv_balance_ibfk_2），
# 必须先查 information_schema 拿到真实约束名再删；DDL 幂等保护。
# ------------------------------------------------------------------


def _table_exists(bind, table: str) -> bool:
    return bool(
        bind.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
            ),
            {"t": table},
        ).scalar()
    )


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


def _fk_names_on_column(bind, table: str, column: str) -> List[str]:
    """某表某列上定义的外键约束名。"""
    rows = bind.execute(
        text(
            "SELECT kc.CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE kc "
            "WHERE kc.TABLE_SCHEMA = DATABASE() AND kc.TABLE_NAME = :t "
            "AND kc.COLUMN_NAME = :c AND kc.REFERENCED_TABLE_NAME IS NOT NULL"
        ),
        {"t": table, "c": column},
    )
    return [r[0] for r in rows]


def _fk_names_referencing(bind, ref_table: str) -> List[Tuple[str, str]]:
    """引用 ref_table 的（表名, 约束名）列表。"""
    rows = bind.execute(
        text(
            "SELECT DISTINCT kc.TABLE_NAME, kc.CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE kc "
            "WHERE kc.TABLE_SCHEMA = DATABASE() AND kc.REFERENCED_TABLE_NAME = :t"
        ),
        {"t": ref_table},
    )
    return [(r[0], r[1]) for r in rows]


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    if not _column_exists(bind, table, column.name):
        op.add_column(table, column)


def _drop_column_with_fks(table: str, column: str) -> None:
    bind = op.get_bind()
    if not _column_exists(bind, table, column):
        return
    for name in _fk_names_on_column(bind, table, column):
        op.drop_constraint(name, table, type_="foreignkey")
    op.drop_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------- 1. 新列 ----------------
    _add_column_if_missing(
        "inv_warehouse",
        sa.Column("location_code", sa.String(length=50), nullable=True, comment="库位编码（文本，原 inv_location 并入）"),
    )
    _add_column_if_missing(
        "inv_warehouse",
        sa.Column("location_name", sa.String(length=100), nullable=True, comment="库位名称（文本，原 inv_location 并入）"),
    )
    _add_column_if_missing(
        "inv_balance",
        sa.Column("reorder_point", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0", comment="订货点"),
    )
    _add_column_if_missing(
        "inv_balance",
        sa.Column("reorder_quantity", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0", comment="建议订货量"),
    )

    # ---------------- 2. 新表：库存操作单（移库 + 盘点合并） ----------------
    if not _table_exists(bind, "inv_stock_operation"):
        op.create_table(
            "inv_stock_operation",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("operation_no", sa.String(length=50), nullable=False, comment="操作单号（TRF/STK 前缀）"),
            sa.Column("op_type", sa.String(length=20), nullable=False, comment="操作类型 TRANSFER/STOCKTAKE"),
            sa.Column("from_warehouse_id", sa.BigInteger(), nullable=True, comment="源仓库ID（TRANSFER 用）"),
            sa.Column("to_warehouse_id", sa.BigInteger(), nullable=True, comment="目标仓库ID（TRANSFER 用）"),
            sa.Column("warehouse_id", sa.BigInteger(), nullable=True, comment="仓库ID（STOCKTAKE 用）"),
            sa.Column("op_date", sa.Date(), nullable=False, comment="业务日期（移库/盘点日期）"),
            sa.Column("status", sa.String(length=20), nullable=False, comment="状态"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
            sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人ID（sys_user.id）"),
            sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人ID（sys_user.id）"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.CheckConstraint("op_type IN ('TRANSFER','STOCKTAKE')", name="ck_inv_stock_op_type"),
            sa.CheckConstraint("status IN ('DRAFT','COMPLETED','CANCELLED')", name="ck_inv_stock_op_status"),
            sa.ForeignKeyConstraint(["from_warehouse_id"], ["inv_warehouse.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["to_warehouse_id"], ["inv_warehouse.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["inv_warehouse.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("operation_no"),
        )
        op.create_index(op.f("ix_inv_stock_operation_op_type"), "inv_stock_operation", ["op_type"], unique=False)
        op.create_index(op.f("ix_inv_stock_operation_status"), "inv_stock_operation", ["status"], unique=False)
    if not _table_exists(bind, "inv_stock_operation_item"):
        op.create_table(
            "inv_stock_operation_item",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("operation_id", sa.BigInteger(), nullable=False, comment="操作单头ID"),
            sa.Column("material_id", sa.BigInteger(), nullable=False, comment="物料ID"),
            sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=True, comment="移库数量（TRANSFER 用）"),
            sa.Column("book_qty", sa.Numeric(precision=18, scale=4), nullable=True, comment="账面数量（STOCKTAKE 用）"),
            sa.Column("actual_qty", sa.Numeric(precision=18, scale=4), nullable=True, comment="实盘数量（STOCKTAKE 用）"),
            sa.Column("difference", sa.Numeric(precision=18, scale=4), nullable=True, comment="差异数量（STOCKTAKE 用）"),
            sa.Column("remark", sa.String(length=200), nullable=True, comment="备注"),
            sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人ID（sys_user.id）"),
            sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人ID（sys_user.id）"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.ForeignKeyConstraint(["material_id"], ["sys_material.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["operation_id"], ["inv_stock_operation.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_inv_stock_operation_item_operation_id"),
            "inv_stock_operation_item",
            ["operation_id"],
            unique=False,
        )

    # ---------------- 3. 数据迁移（重跑安全：先清空新表再全量写入） ----------------
    op.execute("DELETE FROM inv_stock_operation_item")
    op.execute("DELETE FROM inv_stock_operation")

    # 3.1 结存合并：同 (warehouse_id, material_id) 多行 → 保留 MIN(id) 行并汇总数量
    op.execute(
        """
        UPDATE inv_balance b
        JOIN (
            SELECT warehouse_id, material_id, MIN(id) AS keep_id,
                   SUM(quantity) AS total_qty, SUM(locked_quantity) AS total_locked
            FROM inv_balance
            GROUP BY warehouse_id, material_id
        ) agg ON agg.keep_id = b.id
        SET b.quantity = agg.total_qty, b.locked_quantity = agg.total_locked
        """
    )
    op.execute(
        """
        DELETE b FROM inv_balance b
        JOIN (
            SELECT warehouse_id, material_id, MIN(id) AS keep_id
            FROM inv_balance
            GROUP BY warehouse_id, material_id
        ) k ON b.warehouse_id = k.warehouse_id AND b.material_id = k.material_id
        WHERE b.id <> k.keep_id
        """
    )
    # 3.2 回填订货点：inv_reorder_rule（每物料+仓库唯一）→ 保留的结存行
    if _table_exists(bind, "inv_reorder_rule"):
        op.execute(
            """
            UPDATE inv_balance b
            JOIN inv_reorder_rule r
              ON r.material_id = b.material_id AND r.warehouse_id = b.warehouse_id
            SET b.reorder_point = r.reorder_point, b.reorder_quantity = r.reorder_quantity
            """
        )

    # 3.3 移库单 → inv_stock_operation（op_type=TRANSFER；旧 CONFIRMED 视为未完成 → DRAFT）
    op.execute(
        """
        INSERT INTO inv_stock_operation
            (operation_no, op_type, from_warehouse_id, to_warehouse_id, warehouse_id,
             op_date, status, remark, created_by, updated_by, created_at, updated_at)
        SELECT t.transfer_no, 'TRANSFER', t.from_warehouse_id, t.to_warehouse_id, NULL,
               t.transfer_date, CASE t.status WHEN 'CONFIRMED' THEN 'DRAFT' ELSE t.status END,
               t.remark, t.created_by, t.updated_by, t.created_at, t.updated_at
        FROM inv_transfer t
        """
    )
    op.execute(
        """
        INSERT INTO inv_stock_operation_item
            (operation_id, material_id, quantity, remark,
             created_by, updated_by, created_at, updated_at)
        SELECT s.id, ti.material_id, ti.quantity, ti.remark,
               ti.created_by, ti.updated_by, ti.created_at, ti.updated_at
        FROM inv_transfer_item ti
        JOIN inv_transfer t ON ti.transfer_id = t.id
        JOIN inv_stock_operation s ON s.operation_no = t.transfer_no AND s.op_type = 'TRANSFER'
        """
    )

    # 3.4 盘点单 → inv_stock_operation（op_type=STOCKTAKE）
    op.execute(
        """
        INSERT INTO inv_stock_operation
            (operation_no, op_type, from_warehouse_id, to_warehouse_id, warehouse_id,
             op_date, status, remark, created_by, updated_by, created_at, updated_at)
        SELECT k.stocktake_no, 'STOCKTAKE', NULL, NULL, k.warehouse_id,
               k.stocktake_date, CASE k.status WHEN 'CONFIRMED' THEN 'DRAFT' ELSE k.status END,
               k.remark, k.created_by, k.updated_by, k.created_at, k.updated_at
        FROM inv_stocktake k
        """
    )
    op.execute(
        """
        INSERT INTO inv_stock_operation_item
            (operation_id, material_id, quantity, book_qty, actual_qty, difference, remark,
             created_by, updated_by, created_at, updated_at)
        SELECT s.id, ki.material_id, NULL, ki.book_qty, ki.actual_qty, ki.difference, ki.remark,
               ki.created_by, ki.updated_by, ki.created_at, ki.updated_at
        FROM inv_stocktake_item ki
        JOIN inv_stocktake k ON ki.stocktake_id = k.id
        JOIN inv_stock_operation s ON s.operation_no = k.stocktake_no AND s.op_type = 'STOCKTAKE'
        """
    )

    # ---------------- 4. 各模块明细表删除 location_id（先删外键再删列） ----------------
    for table in (
        "inv_balance",
        "inv_transaction",
        "sal_shipment_item",
        "sal_return_item",
        "pur_receipt_item",
        "pln_material_requisition_item",
        "pln_completion_report",
    ):
        _drop_column_with_fks(table, "location_id")

    # inv_balance：唯一约束 (warehouse, location, material) → (warehouse, material)
    if _index_exists(bind, "inv_balance", "ix_inv_balance_location_id"):
        op.drop_index("ix_inv_balance_location_id", table_name="inv_balance")
    if _index_exists(bind, "inv_balance", "uq_inv_balance_bucket"):
        op.drop_index("uq_inv_balance_bucket", table_name="inv_balance")
        op.create_index(
            "uq_inv_balance_bucket", "inv_balance", ["warehouse_id", "material_id"], unique=True
        )

    # ---------------- 5. 删除旧表（先子表后父表） ----------------
    for table in ("inv_transfer_item", "inv_transfer", "inv_stocktake_item", "inv_stocktake", "inv_reorder_rule"):
        if _table_exists(bind, table):
            op.drop_table(table)
    # 安全网：清理仍指向 inv_location 的外键后再删表
    for tbl, constraint in _fk_names_referencing(bind, "inv_location"):
        op.drop_constraint(constraint, tbl, type_="foreignkey")
    if _table_exists(bind, "inv_location"):
        op.drop_table("inv_location")


def downgrade() -> None:
    """不提供自动回滚：数据已合并/删除，降级不可逆。如需回滚请从备份恢复。"""
    raise NotImplementedError("5 表合并涉及数据删除，无法自动降级；请从数据库备份恢复。")
