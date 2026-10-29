"""procurement: 到货职责分离 — pur_receipt 删 warehouse_id，状态机改 WAIT_INBOUND

采购人员只登记到货数量、合格数量、关联订单与供应商，不再选择仓库。
到货单状态机从 DRAFT→CONFIRMED→COMPLETED 改为 DRAFT→WAIT_INBOUND→INBOUND_CONFIRMED，
采购员确认到货后置 WAIT_INBOUND，库存模块上架后回调置 INBOUND_CONFIRMED。

Revision ID: b3d8f1a2c4e5
Revises: a7d3e5f9b1c2
Create Date: 2026-10-29 10:10:00.000000

注意：共享库上 system 组员已执行未合并的迁移 c9a5e2f71b64，
     本迁移合入 develop 后需把 down_revision 改为 c9a5e2f71b64。
"""

from alembic import op
import sqlalchemy as sa

revision = "b3d8f1a2c4e5"
down_revision = "a7d3e5f9b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 状态映射：CONFIRMED → WAIT_INBOUND（采购员已确认到货但未入库），
    #    COMPLETED → INBOUND_CONFIRMED（库存已完成上架入库）
    conn.execute(sa.text(
        "UPDATE pur_receipt SET status='WAIT_INBOUND' WHERE status='CONFIRMED'"
    ))
    conn.execute(sa.text(
        "UPDATE pur_receipt SET status='INBOUND_CONFIRMED' WHERE status='COMPLETED'"
    ))

    # 2) 重建 status CHECK 约束
    op.drop_constraint("ck_pur_receipt_status", "pur_receipt", type_="check")
    op.create_check_constraint(
        "ck_pur_receipt_status",
        "pur_receipt",
        "status IN ('DRAFT','WAIT_INBOUND','INBOUND_CONFIRMED','CANCELLED')",
    )

    # 3) 删 warehouse_id 列 + 对应外键（外键名通过数据库 inspect 确认）
    #    先尝试 pur_receipt_ibfk_3（开发机实测名），回退尝试 pur_receipt_ibfk_warehouse
    fk_name = None
    try:
        op.drop_constraint("pur_receipt_ibfk_3", "pur_receipt", type_="foreignkey")
        fk_name = "pur_receipt_ibfk_3"
    except Exception:
        try:
            op.drop_constraint("pur_receipt_ibfk_warehouse", "pur_receipt", type_="foreignkey")
            fk_name = "pur_receipt_ibfk_warehouse"
        except Exception:
            # 兜底：让 SQLAlchemy inspect 查真实外键名
            insp = sa.inspect(conn)
            for fk in insp.get_foreign_keys("pur_receipt"):
                if "warehouse" in ",".join(fk["constrained_columns"]).lower() or \
                   "inv_warehouse" in ",".join(fk["referred_columns"]).lower():
                    fk_name = fk["name"]
                    if fk_name:
                        op.drop_constraint(fk_name, "pur_receipt", type_="foreignkey")
                    break

    op.drop_column("pur_receipt", "warehouse_id")


def downgrade() -> None:
    # 回滚风险较高：已入库的单据 warehouse_id 已丢失，只能恢复结构 + 回填默认
    op.add_column(
        "pur_receipt",
        sa.Column("warehouse_id", sa.BigInteger(), nullable=True, comment="收货仓库ID"),
    )
    # 尝试补外键（inv_warehouse 可能仍存在）
    try:
        op.create_foreign_key(
            "pur_receipt_ibfk_3",
            "pur_receipt",
            "inv_warehouse",
            ["warehouse_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    except Exception:
        pass

    # 恢复 CHECK + 状态
    op.drop_constraint("ck_pur_receipt_status", "pur_receipt", type_="check")
    op.create_check_constraint(
        "ck_pur_receipt_status",
        "pur_receipt",
        "status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')",
    )
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE pur_receipt SET status='CONFIRMED' WHERE status='WAIT_INBOUND'"
    ))
    conn.execute(sa.text(
        "UPDATE pur_receipt SET status='COMPLETED' WHERE status='INBOUND_CONFIRMED'"
    ))
