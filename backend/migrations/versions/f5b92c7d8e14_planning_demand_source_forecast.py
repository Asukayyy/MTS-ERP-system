"""planning 需求来源新增 FORECAST：销售订单与销售预测分离

背景：
    `pln_demand.source_type` 原先把销售订单与销售预测都记为 `SALES`，
    导致「销售订单 + 补库申请 → MPS」汇总时无法排除预测需求。
    本次新增 `FORECAST` 取值，预测需求独立标识，MPS 汇总只取
    `SALES`（销售订单）与 `STOCKFILL`（补库申请）。

数据变更：
    - 重建检查约束 `ck_pln_demand_source`，允许 SALES/FORECAST/STOCKFILL/MPS；
    - 历史预测需求（remark 以「销售预测 」开头且原为 SALES）改写为 FORECAST。

Revision ID: f5b92c7d8e14
Revises: c8a4f2d61b73
Create Date: 2026-10-22
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5b92c7d8e14"
down_revision: Union[str, None] = "c8a4f2d61b73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE pln_demand DROP CHECK ck_pln_demand_source")
    op.execute(
        "ALTER TABLE pln_demand ADD CONSTRAINT ck_pln_demand_source "
        "CHECK (source_type IN ('SALES','FORECAST','STOCKFILL','MPS'))"
    )
    op.execute(
        "UPDATE pln_demand SET source_type = 'FORECAST' "
        "WHERE source_type = 'SALES' AND remark LIKE '销售预测 %'"
    )


def downgrade() -> None:
    op.execute("UPDATE pln_demand SET source_type = 'SALES' WHERE source_type = 'FORECAST'")
    op.execute("ALTER TABLE pln_demand DROP CHECK ck_pln_demand_source")
    op.execute(
        "ALTER TABLE pln_demand ADD CONSTRAINT ck_pln_demand_source "
        "CHECK (source_type IN ('SALES','STOCKFILL','MPS'))"
    )
