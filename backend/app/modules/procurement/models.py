"""procurement 模块 ORM 模型 —— 供应商、采购计划、采购订单、到货、供应商评价。

要点：

- 采购计划来源于 Planning 的 MRP `BUY` 结果或 Inventory 的订货点补库需求，
  通过 `source_type` + `source_reference_id` 记录来源（规格 §24 / §43 Phase 7）。
- 到货登记 `pur_receipt` 确认时必须调用 inventory 接口入库并产生库存流水，
  **不允许绕过库存流水直接改库存**（规格 §42）。
- 供应商与物料是 N:M 关系，使用关联表 `pur_supplier_material`（规格 §21）。
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin, BigIntFk, BigIntPk, CodeStr, NameStr
from app.shared.enums import RecordStatus

# ====================================================================
# 供应商
# ====================================================================


class PurSupplier(Base, AuditMixin):
    """供应商主数据。"""

    __tablename__ = "pur_supplier"

    id: Mapped[BigIntPk]
    supplier_code: Mapped[CodeStr] = mapped_column(unique=True, comment="供应商编码")
    supplier_name: Mapped[NameStr] = mapped_column(comment="供应商名称")
    contact_person: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="联系人")
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, comment="联系电话")
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="邮箱")
    address: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="地址")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_pur_supplier_status"),
    )


class PurSupplierMaterial(Base, AuditMixin):
    """供应商 N:M 物料 关联表（含供货价与供货提前期）。"""

    __tablename__ = "pur_supplier_material"

    id: Mapped[BigIntPk]
    supplier_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pur_supplier.id", ondelete="CASCADE"), nullable=False, index=True, comment="供应商ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否主供应商"
    )
    supply_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="供货单价"
    )
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="供货提前期（天）")
    min_order_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="最小起订量"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )

    __table_args__ = (
        UniqueConstraint("supplier_id", "material_id", name="uq_pur_supplier_material"),
        CheckConstraint("supply_price >= 0", name="ck_pur_supplier_material_price"),
        CheckConstraint("lead_time_days >= 0", name="ck_pur_supplier_material_lead"),
    )


# ====================================================================
# 采购计划（承接 MRP BUY / 库存补库）
# ====================================================================


class PurPurchasePlan(Base, AuditMixin):
    """采购计划头：集中承载待采购需求的建议。"""

    __tablename__ = "pur_purchase_plan"

    id: Mapped[BigIntPk]
    plan_no: Mapped[CodeStr] = mapped_column(unique=True, comment="采购计划编号")
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["PurPurchasePlanItem"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')",
            name="ck_pur_purchase_plan_status",
        ),
    )


class PurPurchasePlanItem(Base, AuditMixin):
    """采购计划行：来源可以是 MRP 结果或库存补库需求。

    规格 §20 要求跨模块历史业务外键用 RESTRICT，但 `source_reference_id` 是
    **多态引用**（可能指向 `pln_mrp_result` 或 `inv_replenishment_request`），
    因此只做索引不做物理外键。
    """

    __tablename__ = "pur_purchase_plan_item"

    id: Mapped[BigIntPk]
    plan_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pur_purchase_plan.id", ondelete="CASCADE"), nullable=False, index=True, comment="采购计划头ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    required_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="需求数量"
    )
    ordered_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="已下单数量"
    )
    required_date: Mapped[date] = mapped_column(Date, nullable=False, comment="需求日期")
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="MRP", index=True, comment="来源类型 MRP/REORDER/MANUAL"
    )
    source_reference_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True, comment="来源单据ID（多态引用）"
    )
    supplier_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("pur_supplier.id", ondelete="RESTRICT"), nullable=True, comment="建议供应商ID"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    plan: Mapped[PurPurchasePlan] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("required_qty > 0", name="ck_pur_plan_item_qty"),
        CheckConstraint("ordered_qty >= 0", name="ck_pur_plan_item_ordered"),
        CheckConstraint(
            "source_type IN ('MRP','REORDER','MANUAL')", name="ck_pur_plan_item_source"
        ),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')",
            name="ck_pur_plan_item_status",
        ),
    )


# ====================================================================
# 采购订单
# ====================================================================


class PurOrder(Base, AuditMixin):
    """采购订单头。"""

    __tablename__ = "pur_order"

    id: Mapped[BigIntPk]
    order_no: Mapped[CodeStr] = mapped_column(unique=True, comment="采购订单号")
    supplier_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pur_supplier.id", ondelete="RESTRICT"), nullable=False, index=True, comment="供应商ID"
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False, comment="下单日期")
    expected_date: Mapped[date] = mapped_column(Date, nullable=False, comment="预计到货日期")
    buyer_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_personnel.id", ondelete="RESTRICT"), nullable=True, index=True, comment="采购员（sys_personnel.id）"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="订单总金额"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["PurOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')",
            name="ck_pur_order_status",
        ),
    )


class PurOrderItem(Base, AuditMixin):
    """采购订单行。`received_qty` 由到货流程回写。"""

    __tablename__ = "pur_order_item"

    id: Mapped[BigIntPk]
    order_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pur_order.id", ondelete="CASCADE"), nullable=False, index=True, comment="订单头ID"
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="行号")
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="采购数量")
    received_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="已到货数量"
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="单价"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="金额"
    )
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    order: Mapped[PurOrder] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("order_id", "line_no", name="uq_pur_order_item_line"),
        CheckConstraint("quantity > 0", name="ck_pur_order_item_qty"),
        CheckConstraint("received_qty >= 0", name="ck_pur_order_item_received"),
    )


# ====================================================================
# 到货登记（→ Inventory 入库）
# ====================================================================


class PurReceipt(Base, AuditMixin):
    """到货登记单头。确认后必须调用 inventory 入库并生成库存流水。"""

    __tablename__ = "pur_receipt"

    id: Mapped[BigIntPk]
    receipt_no: Mapped[CodeStr] = mapped_column(unique=True, comment="到货单号")
    purchase_order_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pur_order.id", ondelete="RESTRICT"), nullable=False, index=True, comment="采购订单ID"
    )
    supplier_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pur_supplier.id", ondelete="RESTRICT"), nullable=False, index=True, comment="供应商ID"
    )
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, comment="收货仓库ID"
    )
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False, comment="到货日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["PurReceiptItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')", name="ck_pur_receipt_status"
        ),
    )


class PurReceiptItem(Base, AuditMixin):
    """到货明细行。"""

    __tablename__ = "pur_receipt_item"

    id: Mapped[BigIntPk]
    receipt_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pur_receipt.id", ondelete="CASCADE"), nullable=False, index=True, comment="到货单头ID"
    )
    order_item_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pur_order_item.id", ondelete="RESTRICT"), nullable=False, index=True, comment="采购订单行ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, comment="收货库位ID"
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="到货数量")
    qualified_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="合格数量"
    )
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    receipt: Mapped[PurReceipt] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_pur_receipt_item_qty"),
        CheckConstraint("qualified_qty >= 0", name="ck_pur_receipt_item_qualified"),
    )


# ====================================================================
# 供应商评价
# ====================================================================


class PurSupplierEvaluation(Base, AuditMixin):
    """供应商评价：质量 / 交期 / 价格 三类评分。"""

    __tablename__ = "pur_supplier_evaluation"

    id: Mapped[BigIntPk]
    supplier_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pur_supplier.id", ondelete="CASCADE"), nullable=False, index=True, comment="供应商ID"
    )
    evaluate_date: Mapped[date] = mapped_column(Date, nullable=False, comment="评价日期")
    quality_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0, comment="质量评分（0~100）"
    )
    delivery_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0, comment="交期评分（0~100）"
    )
    price_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0, comment="价格评分（0~100）"
    )
    total_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0, comment="综合评分"
    )
    evaluator_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_personnel.id", ondelete="RESTRICT"), nullable=True, comment="评价人（sys_personnel.id）"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint(
            "quality_score >= 0 AND quality_score <= 100", name="ck_pur_eval_quality"
        ),
        CheckConstraint(
            "delivery_score >= 0 AND delivery_score <= 100", name="ck_pur_eval_delivery"
        ),
        CheckConstraint("price_score >= 0 AND price_score <= 100", name="ck_pur_eval_price"),
    )