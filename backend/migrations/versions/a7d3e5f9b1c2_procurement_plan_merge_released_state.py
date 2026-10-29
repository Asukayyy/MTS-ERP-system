"""procurement: 采购计划状态机收敛 — 合并 RELEASED → CONFIRMED，删已下达状态

把 DRAFT → CONFIRMED → RELEASED → COMPLETED 简化为 DRAFT → CONFIRMED → COMPLETED，
RELEASED 状态的计划视为已确认（可下单），不再有单独的「下达」环节。

Revision ID: a7d3e5f9b1c2
Revises: b3e7a9c52d18
Create Date: 2026-10-29 10:00:00.000000

注意：共享库上 system 组员已执行未合并的迁移 c9a5e2f71b64，
     本迁移合入 develop 后需把 down_revision 改为 c9a5e2f71b64。
"""

from alembic import op
import sqlalchemy as sa

revision = "a7d3e5f9b1c2"
down_revision = "b3e7a9c52d18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # 1) 把 PURCHASE_PLAN / PUR_PURCHASE_PLAN 里残留的 RELEASED 全部并到 CONFIRMED
    #    （pur_purchase_plan.status + pur_purchase_plan_item.status 同时处理）
    conn.execute(sa.text(
        "UPDATE pur_purchase_plan SET status='CONFIRMED' WHERE status='RELEASED'"
    ))
    conn.execute(sa.text(
        "UPDATE pur_purchase_plan_item SET status='CONFIRMED' WHERE status='RELEASED'"
    ))

    # 2) 重建 status CHECK 约束（去掉 RELEASED，只留 DRAFT/CONFIRMED/COMPLETED/CANCELLED）
    op.drop_constraint("ck_pur_purchase_plan_status", "pur_purchase_plan", type_="check")
    op.create_check_constraint(
        "ck_pur_purchase_plan_status",
        "pur_purchase_plan",
        "status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')",
    )


def downgrade() -> None:
    # 回滚：把 CONFIRMED 再拆回 RELEASED/CONFIRMED，无法精确还原，直接恢复 CHECK
    # （实际几乎不会执行，因为状态机收敛是业务确定方向）
    op.drop_constraint("ck_pur_purchase_plan_status", "pur_purchase_plan", type_="check")
    op.create_check_constraint(
        "ck_pur_purchase_plan_status",
        "pur_purchase_plan",
        "status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')",
    )
