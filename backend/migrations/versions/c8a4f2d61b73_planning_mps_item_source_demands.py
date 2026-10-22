"""planning MPS 行：记录来源需求，打通「统一需求 → MPS」链路

数据变更：
- `pln_mps_item.source_demand_ids`（VARCHAR(500)，NULLABLE）：
  由统一需求汇总生成 MPS 时写入被聚合的需求 ID（逗号分隔），
  用于从 MPS 行回查来源需求；手工录入 / 课程案例导入的 MPS 行保持 NULL。

Revision ID: c8a4f2d61b73
Revises: d4b8e2f6a1c3
Create Date: 2026-10-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8a4f2d61b73"
down_revision: Union[str, None] = "d4b8e2f6a1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pln_mps_item",
        sa.Column(
            "source_demand_ids",
            sa.String(length=500),
            nullable=True,
            comment="来源需求ID（逗号分隔，由需求汇总生成时写入）",
        ),
    )


def downgrade() -> None:
    op.drop_column("pln_mps_item", "source_demand_ids")
