"""物料新增 ABC 分类与销售类别

背景：
    1. BOM 表需要展示/维护经典 ABC 分类（A 高价值、B 中等、C 低值）；
    2. 销售预测与实时库存需要区分「整机售卖」与「可单独售卖备件」（如转椅轮子），
       以便两类业务分开统计，不互相混算。

字段：
    - `sys_material.abc_class`：A/B/C，可空（未分类）；
    - `sys_material.sales_category`：MACHINE 整机 / SPARE 可售备件 / INTERNAL 内部件。

数据回填：
    - 成品（FINISHED）默认 MACHINE；
    - 其余物料默认 INTERNAL，需要单独售卖的零件（如轮子）由业务在物料/BOM 中改为 SPARE。

Revision ID: b3e7a9c52d18
Revises: b2d6f8a41c07
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3e7a9c52d18"
down_revision: Union[str, None] = "b2d6f8a41c07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sys_material",
        sa.Column(
            "abc_class",
            sa.String(1),
            nullable=True,
            comment="ABC 分类（经典 ABC：A 高价值/B 中等/C 低值）",
        ),
    )
    op.add_column(
        "sys_material",
        sa.Column(
            "sales_category",
            sa.String(20),
            nullable=False,
            server_default="INTERNAL",
            comment="销售类别 MACHINE 整机 / SPARE 可单独售卖备件 / INTERNAL 内部件",
        ),
    )
    op.create_index("ix_sys_material_sales_category", "sys_material", ["sales_category"])
    op.create_check_constraint(
        "ck_sys_material_abc_class",
        "sys_material",
        "abc_class IS NULL OR abc_class IN ('A','B','C')",
    )
    op.create_check_constraint(
        "ck_sys_material_sales_category",
        "sys_material",
        "sales_category IN ('MACHINE','SPARE','INTERNAL')",
    )
    op.execute(
        "UPDATE sys_material SET sales_category = 'MACHINE' WHERE material_type = 'FINISHED'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_sys_material_sales_category", "sys_material", type_="check")
    op.drop_constraint("ck_sys_material_abc_class", "sys_material", type_="check")
    op.drop_index("ix_sys_material_sales_category", table_name="sys_material")
    op.drop_column("sys_material", "sales_category")
    op.drop_column("sys_material", "abc_class")
