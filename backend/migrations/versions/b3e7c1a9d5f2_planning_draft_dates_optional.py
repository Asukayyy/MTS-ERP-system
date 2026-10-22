"""planning 派工单 / 领料单：计划日期改为可选（预填草稿留空待人工填写）

数据变更：
- `pln_dispatch_order.planned_start` / `planned_end` 改为 NULLABLE：
  按计划自动生成的派工单只预填工序与派工数量，计划起止日期由人工指定。
- `pln_material_requisition.req_date` 改为 NULLABLE：领料日期由人工指定。
- 这些字段在业务上仍是必填项，由服务层在"确认（进入非 DRAFT 状态）"时校验，
  因此本次迁移只放宽数据库约束，不改变已有数据的取值。

Revision ID: b3e7c1a9d5f2
Revises: a1c8f4d2e9b7
Create Date: 2026-10-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "b3e7c1a9d5f2"
down_revision: Union[str, None] = "a1c8f4d2e9b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OPTIONAL_DATE_COLUMNS = (
    ("pln_dispatch_order", "planned_start", "计划开始日期（草稿可留空，确认前必填）"),
    ("pln_dispatch_order", "planned_end", "计划结束日期（草稿可留空，确认前必填）"),
    ("pln_material_requisition", "req_date", "领料日期（草稿可留空，确认前必填）"),
)


def upgrade() -> None:
    for table, column, comment in OPTIONAL_DATE_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Date(),
            nullable=True,
            comment=comment,
        )


def downgrade() -> None:
    # 回退前先补齐空值：派工单沿用所属作业计划区间，领料单取当天
    bind = op.get_bind()
    bind.execute(
        text(
            "UPDATE pln_dispatch_order d "
            "JOIN pln_production_plan p ON p.id = d.plan_id "
            "SET d.planned_start = COALESCE(d.planned_start, p.start_date), "
            "    d.planned_end = COALESCE(d.planned_end, p.end_date) "
            "WHERE d.planned_start IS NULL OR d.planned_end IS NULL"
        )
    )
    bind.execute(
        text(
            "UPDATE pln_dispatch_order SET planned_start = CURDATE() WHERE planned_start IS NULL"
        )
    )
    bind.execute(
        text(
            "UPDATE pln_dispatch_order SET planned_end = planned_start WHERE planned_end IS NULL"
        )
    )
    bind.execute(
        text("UPDATE pln_material_requisition SET req_date = CURDATE() WHERE req_date IS NULL")
    )

    for table, column, comment in reversed(OPTIONAL_DATE_COLUMNS):
        reversed_comment = comment.rsplit("（", 1)[0]
        op.alter_column(
            table,
            column,
            existing_type=sa.Date(),
            nullable=False,
            comment=reversed_comment,
        )
