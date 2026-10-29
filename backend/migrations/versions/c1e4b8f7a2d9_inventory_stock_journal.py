"""inventory：补建库存变动流水表 inv_stock_journal

背景：
    `inv_stock_journal` 由 cf32f81 新增（每次改 `inv_balance` 时在同一事务追加一条流水），
    但当时漏了 Alembic 迁移。数据库里没有这张表时：
      - `GET /api/v1/inventory/stock-journal` 直接 500（表不存在），前端「库存流水」页看起来永远是空的；
      - 任何改结存的动作（入库/出库/移库/盘点确认）都会因为写流水失败而整笔回滚。
    本迁移补齐建表，保证「库存流水」页和出入库确认链路可用。

数据变更：
1. 新建 `inv_stock_journal`（幂等：表/列/索引/约束存在性检查，
   若已由人工 SQL 建过表则只补缺失的列与索引）。
2. **不回填历史**：建表前发生的库存变动没有流水记录，只能从建表后新发生的出入库开始追溯。

Revision ID: c1e4b8f7a2d9
Revises: e3a9c15f7d24
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "c1e4b8f7a2d9"
down_revision: Union[str, None] = "e3a9c15f7d24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "inv_stock_journal"


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


# 人工建表时可能缺失的列：名字 → 列定义（可空，避免已有数据插入失败）
_MISSING_COLUMNS = {
    "material_code": sa.Column("material_code", sa.String(length=64), nullable=True, comment="物料编码快照"),
    "material_name": sa.Column("material_name", sa.String(length=128), nullable=True, comment="物料名称快照"),
    "warehouse_code": sa.Column("warehouse_code", sa.String(length=32), nullable=True, comment="仓库编码快照"),
    "warehouse_name": sa.Column("warehouse_name", sa.String(length=64), nullable=True, comment="仓库名称快照"),
    "source_module": sa.Column("source_module", sa.String(length=32), nullable=True, comment="来源模块"),
    "source_type": sa.Column("source_type", sa.String(length=64), nullable=True, comment="来源类型"),
    "source_reference_id": sa.Column("source_reference_id", sa.BigInteger(), nullable=True, comment="来源单据ID"),
    "source_no": sa.Column("source_no", sa.String(length=64), nullable=True, comment="来源单据号"),
    "remark": sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
    "operator_id": sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="操作人ID"),
}


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("op_date", sa.Date(), nullable=False, comment="业务日期"),
            sa.Column("material_id", sa.BigInteger(), nullable=False, comment="物料ID"),
            sa.Column("material_code", sa.String(length=64), nullable=True, comment="物料编码快照"),
            sa.Column("material_name", sa.String(length=128), nullable=True, comment="物料名称快照"),
            sa.Column("warehouse_id", sa.BigInteger(), nullable=False, comment="仓库ID"),
            sa.Column("warehouse_code", sa.String(length=32), nullable=True, comment="仓库编码快照"),
            sa.Column("warehouse_name", sa.String(length=64), nullable=True, comment="仓库名称快照"),
            sa.Column(
                "direction",
                sa.String(length=16),
                nullable=False,
                comment="IN/OUT/ADJUST/TRANSFER",
            ),
            sa.Column("delta_qty", sa.Numeric(precision=18, scale=4), nullable=False, comment="数量变化"),
            sa.Column("qty_before", sa.Numeric(precision=18, scale=4), nullable=False, comment="变动前结存"),
            sa.Column("qty_after", sa.Numeric(precision=18, scale=4), nullable=False, comment="变动后结存"),
            sa.Column("source_module", sa.String(length=32), nullable=True, comment="来源模块"),
            sa.Column("source_type", sa.String(length=64), nullable=True, comment="来源类型"),
            sa.Column("source_reference_id", sa.BigInteger(), nullable=True, comment="来源单据ID"),
            sa.Column("source_no", sa.String(length=64), nullable=True, comment="来源单据号"),
            sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
            sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="操作人ID"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.CheckConstraint(
                "direction IN ('IN','OUT','ADJUST','TRANSFER')",
                name="ck_inv_journal_direction",
            ),
            sa.ForeignKeyConstraint(
                ["material_id"], ["sys_material.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["warehouse_id"], ["inv_warehouse.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        # 已有人工建表：只补缺失列，不动已有数据
        for name, column in _MISSING_COLUMNS.items():
            if not _column_exists(bind, TABLE, name):
                op.add_column(TABLE, column)

    _ensure_index(bind, "ix_inv_stock_journal_material_id", ["material_id"])
    _ensure_index(bind, "ix_inv_stock_journal_warehouse_id", ["warehouse_id"])
    _ensure_index(bind, "ix_inv_stock_journal_direction", ["direction"])
    _ensure_index(bind, "idx_journal_op_date", ["op_date"])
    _ensure_index(bind, "idx_journal_source", ["source_module", "source_type"])

    if not _constraint_exists(bind, TABLE, "ck_inv_journal_direction"):
        op.create_check_constraint(
            "ck_inv_journal_direction",
            TABLE,
            "direction IN ('IN','OUT','ADJUST','TRANSFER')",
        )


def _ensure_index(bind, name: str, columns: list[str]) -> None:
    if not _index_exists(bind, TABLE, name):
        op.create_index(name, TABLE, columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, TABLE):
        op.drop_table(TABLE)
