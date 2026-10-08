"""inventory 旧表 / 旧列残留清理（b7f3c2a91d04 清理段的幂等补跑）

背景：
- b7f3c2a91d04（5 表合并）的 upgrade 末尾应删除
  inv_location / inv_reorder_rule / inv_transfer(_item) / inv_stocktake(_item)
  及各表 location_id 列，但共享库上版本号已 stamp 到 c4d2e1f3a6b0，
  上述 DDL 实际未生效（疑似当时迁移中断后手工 stamp 版本）。
- 2026-10-08 实测共享库：6 张旧表全部 0 行；inv_balance 与其他 5 个模块
  明细表残留的 location_id 列全部为 NULL，无数据损失风险。

本迁移幂等执行：
1. 动态查找并删除所有指向 6 张旧表的外键（含 inv_balance 与跨模块明细表）。
2. 删除残留的 location_id 列（存在才删）。
3. 先子表后父表删除 6 张旧空表（存在才删）。

注意：MySQL DDL 非事务，每步均带存在性检查，中断后可直接重新执行。

Revision ID: e7a1b9c4d208
Revises: c4d2e1f3a6b0
Create Date: 2026-10-08
"""

from typing import List, Sequence, Tuple, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "e7a1b9c4d208"
down_revision: Union[str, None] = "c4d2e1f3a6b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_TABLES = (
    "inv_location",
    "inv_reorder_rule",
    "inv_transfer",
    "inv_transfer_item",
    "inv_stocktake",
    "inv_stocktake_item",
)

# 残留 location_id 列的表（2026-10-08 实测；执行时仍以列存在性检查为准）
LOCATION_ID_TABLES = (
    "inv_balance",
    "pln_completion_report",
    "pln_material_requisition_item",
    "pur_receipt_item",
    "sal_return_item",
    "sal_shipment_item",
)


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


def _fk_constraints_referencing(bind, tables) -> List[Tuple[str, str]]:
    """返回 (表名, 外键约束名)：所有引用给定表集合的外键。"""
    if not tables:
        return []
    params = {f"t{i}": name for i, name in enumerate(tables)}
    placeholders = ", ".join(f":t{i}" for i in range(len(tables)))
    rows = bind.execute(
        text(
            f"""
            SELECT TABLE_NAME, CONSTRAINT_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND REFERENCED_TABLE_NAME IN ({placeholders})
            """
        ),
        params,
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


def upgrade() -> None:
    bind = op.get_bind()

    # 0. 安全断言：6 张旧表必须为空表才允许删除（非空则中止，避免误删数据）
    for table in LEGACY_TABLES:
        if _table_exists(bind, table):
            count = bind.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar()
            if count:
                raise RuntimeError(
                    f"旧表 {table} 仍有 {count} 行数据，已中止清理；"
                    "请人工核对数据是否已迁入 inv_stock_operation 后再执行。"
                )

    # 1. 删除所有指向旧表的外键（动态取名，兼容 fk_* 显式命名与 *_ibfk_* 自动命名）
    for table, constraint in _fk_constraints_referencing(bind, LEGACY_TABLES):
        op.drop_constraint(constraint, table, type_="foreignkey")

    # 2. 删除各表残留的 location_id 列（外键已在上一步移除）
    for table in LOCATION_ID_TABLES:
        if _table_exists(bind, table) and _column_exists(bind, table, "location_id"):
            op.drop_column(table, "location_id")

    # 3. 删除旧表：先子表后父表
    drop_order = (
        "inv_transfer_item",
        "inv_stocktake_item",
        "inv_transfer",
        "inv_stocktake",
        "inv_reorder_rule",
        "inv_location",
    )
    for table in drop_order:
        if _table_exists(bind, table):
            op.drop_table(table)


def downgrade() -> None:
    # 不可逆：旧表为空壳、数据早已在 5 表合并时迁移，无法也无需恢复
    raise NotImplementedError("本迁移不可逆（旧表为 5 表合并前的废弃结构）")
