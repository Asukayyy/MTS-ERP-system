"""sales 模块 ORM 模型 —— 客户、预测、订单、发货、退货。

要点：

- 销售需求来源：`sal_forecast`（预测）与 `sal_order`（真实订单），
  由 Planning 通过 Service Contract 读取，`sales` **不主动写计划表**。
- 发货 `sal_shipment` → 调用 inventory 接口扣减库存（必须有库存流水）。
- 退货 `sal_return` → 调用 inventory 接口回增库存（规格 §42：不允许只有发货没有退货）。
- 客户、销售员的外键分别指向 `sys_*` 与 `sys_personnel`，不另建客户/人员表。
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
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
# 客户
# ====================================================================


class SalCustomer(Base, AuditMixin):
    """客户主数据。"""

    __tablename__ = "sal_customer"

    id: Mapped[BigIntPk]
    customer_code: Mapped[CodeStr] = mapped_column(unique=True, comment="客户编码")
    customer_name: Mapped[NameStr] = mapped_column(comment="客户名称")
    contact_person: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="联系人")
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, comment="联系电话")
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="邮箱")
    address: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="地址")
    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="信用额度"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_sal_customer_status"),
        CheckConstraint("credit_limit >= 0", name="ck_sal_customer_credit"),
    )


# ====================================================================
# 销售预测
# ====================================================================


class SalForecast(Base, AuditMixin):
    """销售预测：按月对某物料的预测量，是 Planning 的需求来源之一。"""

    __tablename__ = "sal_forecast"

    id: Mapped[BigIntPk]
    forecast_no: Mapped[CodeStr] = mapped_column(unique=True, comment="预测单号")
    customer_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sal_customer.id", ondelete="RESTRICT"), nullable=True, index=True, comment="客户ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    forecast_month: Mapped[str] = mapped_column(String(7), nullable=False, comment="预测月份（YYYY-MM）")
    forecast_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="预测数量"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint("forecast_qty >= 0", name="ck_sal_forecast_qty"),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')", name="ck_sal_forecast_status"
        ),
    )


# ====================================================================
# 销售订单
# ====================================================================


class SalOrder(Base, AuditMixin):
    """销售订单头。"""

    __tablename__ = "sal_order"

    id: Mapped[BigIntPk]
    order_no: Mapped[CodeStr] = mapped_column(unique=True, comment="销售订单号")
    customer_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sal_customer.id", ondelete="RESTRICT"), nullable=False, index=True, comment="客户ID"
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False, comment="订单日期")
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False, comment="要求交货日期")
    salesperson_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_personnel.id", ondelete="RESTRICT"), nullable=True, index=True, comment="销售员（sys_personnel.id）"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="订单总金额"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["SalOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')",
            name="ck_sal_order_status",
        ),
    )


class SalOrderItem(Base, AuditMixin):
    """销售订单行。`delivered_qty` 由发货流程回写。"""

    __tablename__ = "sal_order_item"

    id: Mapped[BigIntPk]
    order_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sal_order.id", ondelete="CASCADE"), nullable=False, index=True, comment="订单头ID"
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="行号")
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="订单数量")
    delivered_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="已发货数量"
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="单价"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="金额"
    )
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    order: Mapped[SalOrder] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("order_id", "line_no", name="uq_sal_order_item_line"),
        CheckConstraint("quantity > 0", name="ck_sal_order_item_qty"),
        CheckConstraint("delivered_qty >= 0", name="ck_sal_order_item_delivered"),
    )


# ====================================================================
# 销售发货
# ====================================================================


class SalShipment(Base, AuditMixin):
    """销售发货单头。确认发货时调用 inventory 接口出库。"""

    __tablename__ = "sal_shipment"

    id: Mapped[BigIntPk]
    shipment_no: Mapped[CodeStr] = mapped_column(unique=True, comment="发货单号")
    order_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sal_order.id", ondelete="RESTRICT"), nullable=False, index=True, comment="销售订单ID"
    )
    customer_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sal_customer.id", ondelete="RESTRICT"), nullable=False, index=True, comment="客户ID"
    )
    shipment_date: Mapped[date] = mapped_column(Date, nullable=False, comment="发货日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["SalShipmentItem"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')", name="ck_sal_shipment_status"
        ),
    )


class SalShipmentItem(Base, AuditMixin):
    """发货明细行。"""

    __tablename__ = "sal_shipment_item"

    id: Mapped[BigIntPk]
    shipment_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sal_shipment.id", ondelete="CASCADE"), nullable=False, index=True, comment="发货单头ID"
    )
    order_item_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sal_order_item.id", ondelete="RESTRICT"), nullable=False, index=True, comment="销售订单行ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, comment="发货仓库ID"
    )
    location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, comment="发货库位ID"
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="发货数量")
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    shipment: Mapped[SalShipment] = relationship(back_populates="items")

    __table_args__ = (CheckConstraint("quantity > 0", name="ck_sal_shipment_item_qty"),)


# ====================================================================
# 销售退货（规格 §42：不允许只有发货没有退货）
# ====================================================================


class SalReturn(Base, AuditMixin):
    """销售退货单头。确认退货时调用 inventory 接口入库。"""

    __tablename__ = "sal_return"

    id: Mapped[BigIntPk]
    return_no: Mapped[CodeStr] = mapped_column(unique=True, comment="退货单号")
    order_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sal_order.id", ondelete="RESTRICT"), nullable=True, index=True, comment="原销售订单ID"
    )
    customer_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sal_customer.id", ondelete="RESTRICT"), nullable=False, index=True, comment="客户ID"
    )
    return_date: Mapped[date] = mapped_column(Date, nullable=False, comment="退货日期")
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="退货原因")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["SalReturnItem"]] = relationship(
        back_populates="sales_return", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')", name="ck_sal_return_status"
        ),
    )


class SalReturnItem(Base, AuditMixin):
    """退货明细行。"""

    __tablename__ = "sal_return_item"

    id: Mapped[BigIntPk]
    return_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sal_return.id", ondelete="CASCADE"), nullable=False, index=True, comment="退货单头ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, comment="退回仓库ID"
    )
    location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, comment="退回库位ID"
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="退货数量")
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="行退货原因")
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    sales_return: Mapped[SalReturn] = relationship(back_populates="items")

    __table_args__ = (CheckConstraint("quantity > 0", name="ck_sal_return_item_qty"),)