"""销售产品价格：当前价格表 + 价格变动记录表

背景：
    「销售管理 → 产品价格」只覆盖可对外销售的物料（销售类别 MACHINE / SPARE）。
    当前价格用于销售订单自动带出单价；每次改价同时追加一条变动记录，
    供详细页以折线图展示价格走势。

数据初始化：
    按「标准成本 × 1.3」为每个可售物料写入初始价格，并把初始价记为
    第一条价格变动记录，使详细页立即有点位可展示。

Revision ID: d1f7a3c9b260
Revises: c9a5e2f71b64
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1f7a3c9b260"
down_revision: Union[str, None] = "c9a5e2f71b64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: 初始定价说明
INIT_REMARK = "初始定价（标准成本×1.3）"


def upgrade() -> None:
    op.create_table(
        "sal_product_price",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False, comment="物料ID"),
        sa.Column("price", sa.Numeric(precision=18, scale=2), nullable=False, comment="当前单价"),
        sa.Column("effective_date", sa.Date(), nullable=False, comment="当前价格生效日期"),
        sa.Column("remark", sa.String(length=200), nullable=True, comment="定价说明"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人ID（sys_user.id）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人ID（sys_user.id）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.CheckConstraint("price >= 0", name="ck_sal_product_price_price"),
        sa.ForeignKeyConstraint(["material_id"], ["sys_material.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id"),
    )
    op.create_table(
        "sal_product_price_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False, comment="物料ID"),
        sa.Column("price", sa.Numeric(precision=18, scale=2), nullable=False, comment="变动后的单价"),
        sa.Column("effective_date", sa.Date(), nullable=False, comment="生效日期"),
        sa.Column("remark", sa.String(length=200), nullable=True, comment="变动说明"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人ID（sys_user.id）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人ID（sys_user.id）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.CheckConstraint("price >= 0", name="ck_sal_product_price_history_price"),
        sa.ForeignKeyConstraint(["material_id"], ["sys_material.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sal_product_price_history_material_id"),
        "sal_product_price_history",
        ["material_id"],
        unique=False,
    )

    # 初始价格：仅可售物料（整机 / 可售备件），价格 = 标准成本 × 1.3
    op.execute(
        f"""
        INSERT INTO sal_product_price
            (material_id, price, effective_date, remark, created_at, updated_at)
        SELECT id, ROUND(standard_cost * 1.3, 2), CURDATE(), '{INIT_REMARK}', NOW(), NOW()
        FROM sys_material
        WHERE status = 'ACTIVE'
          AND sales_category IN ('MACHINE', 'SPARE')
          AND standard_cost > 0
        """
    )
    op.execute(
        f"""
        INSERT INTO sal_product_price_history
            (material_id, price, effective_date, remark, created_at, updated_at)
        SELECT material_id, price, effective_date, '{INIT_REMARK}', NOW(), NOW()
        FROM sal_product_price
        """
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_sal_product_price_history_material_id"),
        table_name="sal_product_price_history",
    )
    op.drop_table("sal_product_price_history")
    op.drop_table("sal_product_price")
