"""sys_personnel 新增性别与身份证号

背景：
    人事建档需要性别、身份证号等基础身份信息，原员工表只有工号、姓名、
    岗位、联系方式与入职日期。本次补充 `gender`（MALE/FEMALE）与
    `id_card`（18 位，唯一），身份证号可为空以兼容历史数据。

Revision ID: b2d6f8a41c07
Revises: f5b92c7d8e14
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d6f8a41c07"
down_revision: Union[str, None] = "f5b92c7d8e14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sys_personnel",
        sa.Column("gender", sa.String(10), nullable=True, comment="性别 MALE/FEMALE"),
    )
    op.add_column(
        "sys_personnel",
        sa.Column("id_card", sa.String(18), nullable=True, comment="身份证号"),
    )
    op.create_unique_constraint(
        "uq_sys_personnel_id_card", "sys_personnel", ["id_card"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_sys_personnel_id_card", "sys_personnel", type_="unique")
    op.drop_column("sys_personnel", "id_card")
    op.drop_column("sys_personnel", "gender")
