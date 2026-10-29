"""inventory 模块 ORM 模型 —— 仓库、库存结存、补库需求与库存操作单。

核心原则（规格 §24 / §35 / §36，PPT 精简版 5 表设计）：

1. **库存数量只由 inventory 模块维护**，其他模块看到的库存必须来自本模块接口。
2. **任何库存变动都在同一事务内直接更新 `inv_balance` 结存**（不再维护独立流水表），
   不允许绕过契约直接改余额。
3. 库存业务必须可追踪：跨模块入/出库由来源单据（PUR_RECEIPT / SAL_SHIPMENT /
   PLN_MATERIAL_REQUISITION 等）直接驱动结存；移库 / 盘点以库存操作单留痕。
4. **禁止负库存**（`inv_balance.quantity >= 0`，规格 §23）。
5. `inv_balance` 对 `(warehouse_id, material_id)` 唯一；订货点/建议订货量
   直接落在结存行上（原 inv_reorder_rule 并入，仅 A 类物料配置，默认 NULL）。
6. 仓库表带冗余库位文本字段（原 inv_location 并入，仅作展示不再建库位维度）。
7. 移库与盘点统一为 `inv_stock_operation`（`op_type` 区分 TRANSFER / STOCKTAKE），
   明细行统一放 `inv_stock_operation_item`。
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
    Index,
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
# 仓库（原 inv_location 的库位编码/名称并入为本表文本字段）
# ====================================================================


class InvWarehouse(Base, AuditMixin):
    """仓库（含冗余库位文本字段）。"""

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
    location_code: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="库位编码（文本，原 inv_location 并入）"
    )
    location_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="库位名称（文本，原 inv_location 并入）"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_inv_warehouse_status"),
    )


# ====================================================================
# 库存结存（实时库存；原 inv_reorder_rule 的订货点字段并入）
# ====================================================================


class InvBalance(Base, AuditMixin):
    """库存结存：某仓库下某物料的当前数量 + 订货点参数。

    库存变动由业务单据（入库/出库/移库/盘点）直接驱动，**不再维护独立流水表**。
    `reorder_point / reorder_quantity` 为可选项，仅 A 类高价值关键物料配置。
    """

    __tablename__ = "inv_balance"

    id: Mapped[BigIntPk]
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, index=True, comment="仓库ID"
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
    reorder_point: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 4), nullable=True, default=None, comment="订货点（仅 A 类物料配置）"
    )
    reorder_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 4), nullable=True, default=None, comment="建议订货量（仅 A 类物料配置）"
    )
    updated_at_txn: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近一次变动时间")

    __table_args__ = (
        UniqueConstraint("warehouse_id", "material_id", name="uq_inv_balance_bucket"),
        # 规格 §23：禁止负库存
        CheckConstraint("quantity >= 0", name="ck_inv_balance_qty"),
        CheckConstraint("locked_quantity >= 0", name="ck_inv_balance_locked"),
        CheckConstraint("reorder_point IS NULL OR reorder_point >= 0", name="ck_inv_reorder_point"),
        CheckConstraint("reorder_quantity IS NULL OR reorder_quantity >= 0", name="ck_inv_reorder_qty"),
    )


# inv_transaction 流水表已删除：库存变动由各业务单据直接驱动 inv_balance，流水信息
# 可从入库/出库/移库/盘点单据聚合查询，不再单独维护。

# 2026-10-29 新增：inv_stock_journal 库存变动流水。
# 每次 increase_stock / decrease_stock / _apply_adjust / 移库确认 / 盘点确认 时，
# 在同一事务内追加一条 journal，记录：谁/什么物料/哪个仓库/哪一天/入或出/变动多少/前后结存/来源单据。
# 目的：让用户可以完整追溯任何一笔库存变动的原因。


class InvStockJournal(Base):
    """库存变动流水：每次改 inv_balance 时追加一条。"""

    __tablename__ = "inv_stock_journal"

    id: Mapped[BigIntPk]
    op_date: Mapped[date] = mapped_column(Date, nullable=False, comment="业务日期")
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    material_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="物料编码快照")
    material_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="物料名称快照")
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    warehouse_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="仓库编码快照")
    warehouse_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="仓库名称快照")
    direction: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True, comment="IN/OUT/ADJUST/TRANSFER"
    )
    delta_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="数量变化")
    qty_before: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="变动前结存")
    qty_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="变动后结存")
    source_module: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="来源模块")
    source_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="来源类型")
    source_reference_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="来源单据ID")
    source_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="来源单据号")
    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="备注")
    operator_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="操作人ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")

    __table_args__ = (
        Index("idx_journal_op_date", "op_date"),
        Index("idx_journal_source", "source_module", "source_type"),
        CheckConstraint(
            "direction IN ('IN','OUT','ADJUST','TRANSFER')",
            name="ck_inv_journal_direction",
        ),
    )


# ====================================================================
# 补库需求（规格 §14：Inventory 可主动发起计划）
# ====================================================================


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
    target_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="目标库存量"
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
# 库存操作单（原 inv_transfer + inv_stocktake 合并，op_type 区分）
# ====================================================================


class InvStockOperation(Base, AuditMixin):
    """库存单据头：移库（TRANSFER）、盘点（STOCKTAKE）、入库（INBOUND）、出库（OUTBOUND）共用。

    - TRANSFER：`from_warehouse_id → to_warehouse_id`，明细带移库数量；
      确认时对调出/调入两个仓库的结存各更新一次。
    - STOCKTAKE：`warehouse_id`，明细带账面数/实盘数/差异；
      确认时按盘盈/盘亏差异直接调整结存。
    - INBOUND / OUTBOUND：**由业务单据（采购到货、销售发货/退货、生产领料/完工）或
      仓库手工建单产生，只登记「待入库 / 待出库」，不直接改结存**；
      仓库管理人员确认时才指定 `warehouse_id` 并真正更新结存 + 写流水。
      单头通过 `source_module / source_type / source_reference_id / source_no`
      记录来源，备注写清来源单据信息。
    """

    __tablename__ = "inv_stock_operation"

    id: Mapped[BigIntPk]
    operation_no: Mapped[CodeStr] = mapped_column(unique=True, comment="单据号（TRF/STK/INB/OUT 前缀）")
    op_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="单据类型 TRANSFER 移库 / STOCKTAKE 盘点 / INBOUND 入库 / OUTBOUND 出库",
    )
    from_warehouse_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=True, comment="源仓库ID（TRANSFER 用）"
    )
    to_warehouse_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=True, comment="目标仓库ID（TRANSFER 用）"
    )
    warehouse_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"),
        nullable=True,
        comment="仓库ID（STOCKTAKE 用；入/出库在仓库确认时写入）",
    )
    op_date: Mapped[date] = mapped_column(Date, nullable=False, comment="业务日期（移库/盘点/出入库日期）")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT",
        index=True,
        comment="状态：DRAFT 待处理 / COMPLETED 已完成 / CANCELLED 已作废",
    )
    source_module: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="来源模块（sales / procurement / planning / inventory）"
    )
    source_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="来源业务类型（SALES_SHIPMENT 等）"
    )
    source_reference_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="来源单据ID"
    )
    source_no: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="来源单据号"
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="仓库确认出入库时间"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注（写明来源单据）")

    items: Mapped[List["InvStockOperationItem"]] = relationship(
        back_populates="operation", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "op_type IN ('TRANSFER','STOCKTAKE','INBOUND','OUTBOUND')",
            name="ck_inv_stock_op_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT','COMPLETED','CANCELLED')", name="ck_inv_stock_op_status"
        ),
        Index("idx_inv_stock_op_source", "source_module", "source_type", "source_reference_id"),
    )


class InvStockOperationItem(Base, AuditMixin):
    """库存单据明细行：移库明细（quantity）、盘点明细（book/actual/difference）、
    入/出库明细（quantity）共用。

    `material_code / material_name / material_spec / unit` 为建单时的物料快照，
    保证仓库人员在出入库单里能直接看到完整信息（不依赖实时主数据）。
    """

    __tablename__ = "inv_stock_operation_item"

    id: Mapped[BigIntPk]
    operation_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_stock_operation.id", ondelete="CASCADE"), nullable=False, index=True, comment="单据头ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, comment="物料ID"
    )
    material_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="物料编码快照"
    )
    material_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="物料名称快照"
    )
    material_spec: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="规格型号快照"
    )
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="计量单位快照")
    quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 4), nullable=True, comment="数量（移库 / 入库 / 出库用）"
    )
    book_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 4), nullable=True, comment="账面数量（STOCKTAKE 用）"
    )
    actual_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 4), nullable=True, comment="实盘数量（STOCKTAKE 用）"
    )
    difference: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 4), nullable=True, comment="差异数量（STOCKTAKE 用）"
    )
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    operation: Mapped[InvStockOperation] = relationship(back_populates="items")

    # 数量合法性（quantity>0 / actual_qty>=0）依赖 op_type，跨表 CHECK 无法表达，由 service 层校验
