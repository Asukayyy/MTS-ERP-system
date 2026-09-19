"""inventory 模块 ORM 模型 —— 仓库、库位、库存结存与库存流水。

核心原则（规格 §24 / §35 / §36）：

1. **库存数量只由 inventory 模块维护**，其他模块看到的库存必须来自本模块接口。
2. **任何库存变动都必须产生一条 `inv_transaction` 流水**，不允许直接改余额。
3. 库存业务必须可追踪：流水带 `source_module / source_type / source_reference_id`，
   能追溯回具体的 PUR_RECEIPT / SAL_SHIPMENT / PLN_MATERIAL_REQUISITION 等来源单据。
4. **禁止负库存**（`inv_balance.quantity >= 0`）；
   但 `inv_transaction.quantity_change` 允许正负数（规格 §23）。
5. `inv_balance` 对 `(warehouse_id, location_id, material_id)` 唯一。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
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
# 仓库 / 库位
# ====================================================================


class InvWarehouse(Base, AuditMixin):
    """仓库。"""

    __tablename__ = "inv_warehouse"

    id: Mapped[BigIntPk]
    warehouse_code: Mapped[CodeStr] = mapped_column(unique=True, comment="仓库编码")
    warehouse_name: Mapped[NameStr] = mapped_column(comment="仓库名称")
    org_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_organization.id", ondelete="RESTRICT"), nullable=True, index=True, comment="所属组织ID"
    )
    manager_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_personnel.id", ondelete="RESTRICT"), nullable=True, comment="仓库负责人（sys_personnel.id）"
    )
    address: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="地址")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    locations: Mapped[List["InvLocation"]] = relationship(
        back_populates="warehouse", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_inv_warehouse_status"),
    )


class InvLocation(Base, AuditMixin):
    """库位（仓库下的具体存放位置）。"""

    __tablename__ = "inv_location"

    id: Mapped[BigIntPk]
    location_code: Mapped[CodeStr] = mapped_column(comment="库位编码")
    location_name: Mapped[NameStr] = mapped_column(comment="库位名称")
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="CASCADE"), nullable=False, index=True, comment="仓库ID"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    warehouse: Mapped[InvWarehouse] = relationship(back_populates="locations")

    __table_args__ = (
        UniqueConstraint("warehouse_id", "location_code", name="uq_inv_location"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_inv_location_status"),
    )


# ====================================================================
# 库存结存（实时库存）
# ====================================================================


class InvBalance(Base, AuditMixin):
    """库存结存：某仓库/库位下某物料的当前数量。

    只能通过库存流水 `inv_transaction` 变更，**禁止直接修改 quantity**（规格 §36）。
    """

    __tablename__ = "inv_balance"

    id: Mapped[BigIntPk]
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, index=True, comment="仓库ID"
    )
    location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, index=True, comment="库位ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="库存数量"
    )
    locked_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="锁定量（已分配未出库）"
    )
    updated_at_txn: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近一次变动时间")

    __table_args__ = (
        UniqueConstraint(
            "warehouse_id", "location_id", "material_id", name="uq_inv_balance_bucket"
        ),
        # 规格 §23 / §36：禁止负库存
        CheckConstraint("quantity >= 0", name="ck_inv_balance_qty"),
        CheckConstraint("locked_quantity >= 0", name="ck_inv_balance_locked"),
    )


class InvTransaction(Base, AuditMixin):
    """库存流水（出入库明细）—— 库存变动的唯一入口与审计凭证。

    `quantity_change` 允许正数（入库）与负数（出库），因此**不加 >= 0 约束**。
    """

    __tablename__ = "inv_transaction"

    id: Mapped[BigIntPk]
    transaction_no: Mapped[CodeStr] = mapped_column(unique=True, comment="流水单号")
    transaction_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="类型 IN/OUT/TRANSFER_IN/TRANSFER_OUT/ADJUST"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, index=True, comment="仓库ID"
    )
    location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, comment="库位ID"
    )
    quantity_change: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="变动数量（入库为正，出库为负）"
    )
    quantity_after: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="变动后结存"
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="单位成本"
    )
    biz_date: Mapped[date] = mapped_column(Date, nullable=False, comment="业务日期")
    # ---- 来源可追溯（规格 §24）：能追溯回具体来源单据 ----
    source_module: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="来源模块"
    )
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="来源业务类型（PURCHASE_RECEIPT 等）"
    )
    source_reference_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, index=True, comment="来源单据ID"
    )
    source_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="来源单号（冗余便于查询）")
    operator_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="操作人ID（sys_user.id）")
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('IN','OUT','TRANSFER_IN','TRANSFER_OUT','ADJUST')",
            name="ck_inv_transaction_type",
        ),
        CheckConstraint(
            "source_type IN ('PURCHASE_RECEIPT','PRODUCTION_COMPLETION','MATERIAL_REQUISITION',"
            "'SALES_SHIPMENT','SALES_RETURN','TRANSFER','STOCKTAKE','MANUAL')",
            name="ck_inv_transaction_source_type",
        ),
    )


# ====================================================================
# 订货点 / 补库需求（规格 §14：Inventory 可主动发起计划）
# ====================================================================


class InvReorderRule(Base, AuditMixin):
    """订货点规则：库存低于 `reorder_point` 时触发补库建议。"""

    __tablename__ = "inv_reorder_rule"

    id: Mapped[BigIntPk]
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, index=True, comment="仓库ID"
    )
    reorder_point: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="订货点"
    )
    reorder_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="建议订货量"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        UniqueConstraint("material_id", "warehouse_id", name="uq_inv_reorder_rule"),
        CheckConstraint("reorder_point >= 0", name="ck_inv_reorder_point"),
        CheckConstraint("reorder_quantity >= 0", name="ck_inv_reorder_qty"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_inv_reorder_rule_status"),
    )


class InvReplenishmentRequest(Base, AuditMixin):
    """补库需求单。

    规格 §14：Inventory **不直接创建正式生产计划**；库存不足时只产生补库需求，
    `REORDER` 交给 Procurement、`PRODUCTION` 交给 Planning 处理（走 Service 契约）。
    """

    __tablename__ = "inv_replenishment_request"

    id: Mapped[BigIntPk]
    request_no: Mapped[CodeStr] = mapped_column(unique=True, comment="补库需求单号")
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, comment="仓库ID"
    )
    request_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="补库数量"
    )
    current_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="触发时库存量"
    )
    required_date: Mapped[date] = mapped_column(Date, nullable=False, comment="需求日期")
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="来源 REORDER/PRODUCTION"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    # 处理结果引用（跨模块 ID 引用）：Planning 的生产计划ID 或 Procurement 的采购计划ID
    handled_module: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="受理模块")
    handled_ref_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="受理单据ID")
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint("source_type IN ('REORDER','PRODUCTION')", name="ck_inv_repl_source_type"),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')",
            name="ck_inv_repl_status",
        ),
        CheckConstraint("request_qty > 0", name="ck_inv_repl_qty"),
    )


# ====================================================================
# 移库
# ====================================================================


class InvTransfer(Base, AuditMixin):
    """移库单头：仓库/库位之间的库存移动。"""

    __tablename__ = "inv_transfer"

    id: Mapped[BigIntPk]
    transfer_no: Mapped[CodeStr] = mapped_column(unique=True, comment="移库单号")
    from_warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, comment="源仓库ID"
    )
    to_warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, comment="目标仓库ID"
    )
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False, comment="移库日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["InvTransferItem"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')", name="ck_inv_transfer_status"
        ),
    )


class InvTransferItem(Base, AuditMixin):
    """移库明细行。"""

    __tablename__ = "inv_transfer_item"

    id: Mapped[BigIntPk]
    transfer_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_transfer.id", ondelete="CASCADE"), nullable=False, index=True, comment="移库单头ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, comment="物料ID"
    )
    from_location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, comment="源库位ID"
    )
    to_location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, comment="目标库位ID"
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="移库数量")
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    transfer: Mapped[InvTransfer] = relationship(back_populates="items")

    __table_args__ = (CheckConstraint("quantity > 0", name="ck_inv_transfer_item_qty"),)


# ====================================================================
# 盘点
# ====================================================================


class InvStocktake(Base, AuditMixin):
    """库存盘点单头。"""

    __tablename__ = "inv_stocktake"

    id: Mapped[BigIntPk]
    stocktake_no: Mapped[CodeStr] = mapped_column(unique=True, comment="盘点单号")
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, comment="仓库ID"
    )
    stocktake_date: Mapped[date] = mapped_column(Date, nullable=False, comment="盘点日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["InvStocktakeItem"]] = relationship(
        back_populates="stocktake", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')", name="ck_inv_stocktake_status"
        ),
    )


class InvStocktakeItem(Base, AuditMixin):
    """盘点明细行：账面数 vs 实盘数，差异通过 `ADJUST` 流水调整。"""

    __tablename__ = "inv_stocktake_item"

    id: Mapped[BigIntPk]
    stocktake_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_stocktake.id", ondelete="CASCADE"), nullable=False, index=True, comment="盘点单头ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, comment="物料ID"
    )
    location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, comment="库位ID"
    )
    book_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0, comment="账面数量")
    actual_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0, comment="实盘数量")
    difference: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0, comment="差异数量")
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    stocktake: Mapped[InvStocktake] = relationship(back_populates="items")

    __table_args__ = (CheckConstraint("actual_qty >= 0", name="ck_inv_stocktake_actual"),)