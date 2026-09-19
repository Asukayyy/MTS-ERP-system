"""add lead time offset, return quality status and replenishment target qty

Revision ID: f5e52ee720d6
Revises: 9e6fa0de8416
Create Date: 2026-09-19 19:27:45.172400

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5e52ee720d6'
down_revision: Union[str, None] = '9e6fa0de8416'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'inv_replenishment_request',
        sa.Column('target_qty', sa.Numeric(precision=18, scale=4), nullable=False, comment='目标库存量'),
    )
    op.add_column(
        'sal_return_item',
        sa.Column('quality_status', sa.String(length=20), nullable=False, comment='质量状态 QUALIFIED/DEFECTIVE/SCRAP'),
    )
    op.add_column(
        'sys_bom_item',
        sa.Column('lead_time_offset', sa.Integer(), nullable=False, comment='提前期偏置（天，相对父件需求时间的提前量）'),
    )
    # MySQL 的 CHECK 约束不会被 autogenerate 检测，需显式补齐（规格 §22 约束）
    op.create_check_constraint(
        'ck_sys_bom_item_lead_offset', 'sys_bom_item', 'lead_time_offset >= 0'
    )
    op.create_check_constraint(
        'ck_sal_return_item_quality',
        'sal_return_item',
        "quality_status IN ('QUALIFIED','DEFECTIVE','SCRAP')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_sal_return_item_quality', 'sal_return_item', type_='check')
    op.drop_constraint('ck_sys_bom_item_lead_offset', 'sys_bom_item', type_='check')
    op.drop_column('sys_bom_item', 'lead_time_offset')
    op.drop_column('sal_return_item', 'quality_status')
    op.drop_column('inv_replenishment_request', 'target_qty')
