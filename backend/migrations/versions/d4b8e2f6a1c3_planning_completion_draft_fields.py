"""planning 完工报告：报工日期 / 入库仓库改为可选（预填草稿留空待人工填写）

数据变更：
- `pln_completion_report.report_date` 改为 NULLABLE：按计划自动生成的完工报告只预填
  产出物料与完工数量，报工日期由人工指定。
- `pln_completion_report.warehouse_id` 改为 NULLABLE：入库仓库由人工指定。
- 这两个字段在业务上仍是必填项，由服务层在"确认入库"时校验，因此本次迁移只放宽
  数据库约束，不改变已有数据的取值。

Revision ID: d4b8e2f6a1c3
Revises: b3e7c1a9d5f2
Create Date: 2026-10-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "d4b8e2f6a1c3"
down_revision: Union[str, None] = "b3e7c1a9d5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OPTIONAL_COLUMNS = (
    (
        "report_date",
        sa.Date(),
        "报工日期（草稿可留空，确认前必填）",
        "报工日期",
    ),
    (
        "warehouse_id",
        sa.BigInteger(),
        "入库仓库ID（草稿可留空，确认前必填）",
        "入库仓库ID",
    ),
)


def upgrade() -> None:
    for column, column_type, comment, _original_comment in OPTIONAL_COLUMNS:
        op.alter_column(
            "pln_completion_report",
            column,
            existing_type=column_type,
            nullable=True,
            comment=comment,
        )


def downgrade() -> None:
    # 回退前先补齐空值：报工日期取当天，入库仓库取第一个仓库（无仓库时才留空，仍会报错提示）
    bind = op.get_bind()
    bind.execute(
        text(
            "UPDATE pln_completion_report SET report_date = CURDATE() WHERE report_date IS NULL"
        )
    )
    bind.execute(
        text(
            "UPDATE pln_completion_report SET warehouse_id = "
            "(SELECT MIN(id) FROM inv_warehouse) WHERE warehouse_id IS NULL"
        )
    )

    for column, column_type, _comment, original_comment in reversed(OPTIONAL_COLUMNS):
        op.alter_column(
            "pln_completion_report",
            column,
            existing_type=column_type,
            nullable=False,
            comment=original_comment,
        )
