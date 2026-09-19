"""planning 模块 ORM 模型 —— 需求、MPS、MRP、生产作业计划、派工、领料、完工。

职责边界（规格 §7 / §13 / §14）：

- Planning **负责计划**：MPS 录入、MRP 多层 BOM 展开、净需求计算、MAKE/BUY 分流。
- 生产相关业务（生产作业计划 / 派工 / 领料 / 生产完工）**统一归 Planning**，
  不建独立的 Production 模块（规格 §1）。
- Planning **不直接改库存**：领料 / 完工通过 inventory 的 Service Contract 产生库存流水。
- Planning 不替 Inventory 创建正式生产计划：库存补库需求由 Inventory 发起，
  Planning 负责受理并形成正式生产作业计划（规格 §14）。

建模约定：主键 `BIGINT`、数量 `DECIMAL(18,4)`、状态明确枚举 + `CHECK`、统一审计列。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin, BigIntFk, BigIntPk, CodeStr

# ====================================================================
# 统一需求入口
# ====================================================================


class PlnDemand(Base, AuditMixin):
    """统一需求入口：合并销售需求 / 库存补库需求 / MPS 需求。

    `source_type` 取值见 `app.shared.enums.MrpSourceType`（SALES/STOCKFILL/MPS）。
    `source_reference_id` 为跨模块多态引用（指向 sal_order / inv_replenishment_request 等），
    只做索引不做物理外键。
    """

    __tablename__ = "pln_demand"

    id: Mapped[BigIntPk]
    demand_no: Mapped[CodeStr] = mapped_column(unique=True, comment="需求单号")
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="需求来源 SALES/STOCKFILL/MPS"
    )
    source_reference_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True, comment="来源单据ID（跨模块多态引用）"
    )
    source_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="来源单号")
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, comment="需求数量")
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True, comment="需求日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint("source_type IN ('SALES','STOCKFILL','MPS')", name="ck_pln_demand_source"),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')",
            name="ck_pln_demand_status",
        ),
        CheckConstraint("quantity > 0", name="ck_pln_demand_qty"),
    )


# ====================================================================
# 主生产计划 MPS（附录 1 数据录入于此）
# ====================================================================


class PlnMps(Base, AuditMixin):
    """主生产计划头。"""

    __tablename__ = "pln_mps"

    id: Mapped[BigIntPk]
    mps_no: Mapped[CodeStr] = mapped_column(unique=True, comment="MPS编号")
    mps_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="计划名称")
    program_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="计划编号/产线")
    plan_year: Mapped[int] = mapped_column(Integer, nullable=False, comment="计划年度")
    start_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划开始日期")
    end_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划结束日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["PlnMpsItem"]] = relationship(
        back_populates="mps", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')",
            name="ck_pln_mps_status",
        ),
    )


class PlnMpsItem(Base, AuditMixin):
    """主生产计划行：某成品在某期间的计划生产量。"""

    __tablename__ = "pln_mps_item"

    id: Mapped[BigIntPk]
    mps_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pln_mps.id", ondelete="CASCADE"), nullable=False, index=True, comment="MPS头ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="产成品物料ID"
    )
    period_label: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="计划期间标签（如 2026-01）")
    planned_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="计划生产数量"
    )
    finished_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="已完成数量"
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划开始日期")
    end_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划完成日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    mps: Mapped[PlnMps] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("planned_qty > 0", name="ck_pln_mps_item_qty"),
        CheckConstraint("finished_qty >= 0", name="ck_pln_mps_item_finished"),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')",
            name="ck_pln_mps_item_status",
        ),
    )


# ====================================================================
# MRP 运算
# ====================================================================


class PlnMrpRun(Base, AuditMixin):
    """MRP 运算批次：一次运算的上下文与结果归属。"""

    __tablename__ = "pln_mrp_run"

    id: Mapped[BigIntPk]
    run_no: Mapped[CodeStr] = mapped_column(unique=True, comment="运算批次号")
    mps_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("pln_mps.id", ondelete="RESTRICT"), nullable=True, index=True, comment="MPS头ID"
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, comment="运算时间"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    material_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="涉及物料数")
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    results: Mapped[List["PlnMrpResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','IN_PROGRESS','COMPLETED','CANCELLED')", name="ck_pln_mrp_run_status"
        ),
    )


class PlnMrpResult(Base, AuditMixin):
    """MRP 运算结果：BOM 逐层展开后的毛需求 / 可用库存 / 净需求 / 建议下达。

    规格 §17 要求真实计算：
    `净需求 = max(毛需求 + 安全库存 - 可用库存, 0)`，并按 `supply_type` 分流 MAKE / BUY。
    """

    __tablename__ = "pln_mrp_result"

    id: Mapped[BigIntPk]
    run_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pln_mrp_run.id", ondelete="CASCADE"), nullable=False, index=True, comment="运算批次ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    parent_material_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="父件物料ID（BOM 展开时记录来源母件）",
    )
    bom_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="BOM层级（成品=0）")
    gross_requirement: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="毛需求"
    )
    on_hand: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="库存量（来自 inventory 快照）"
    )
    available_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="可用库存（库存 - 锁定量）"
    )
    safety_stock: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="安全库存"
    )
    net_requirement: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="净需求 = max(毛需求+安全库存-可用库存, 0)"
    )
    order_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="建议下达数量"
    )
    supply_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="供应类型 MAKE/BUY"
    )
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="提前期（天）")
    requirement_date: Mapped[date] = mapped_column(Date, nullable=False, comment="需求日期")
    planned_release_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, comment="建议下达日期（需求日期 - 提前期）"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    run: Mapped[PlnMrpRun] = relationship(back_populates="results")

    __table_args__ = (
        CheckConstraint("supply_type IN ('MAKE','BUY')", name="ck_pln_mrp_result_supply"),
        CheckConstraint("bom_level >= 0", name="ck_pln_mrp_result_level"),
        CheckConstraint("gross_requirement >= 0", name="ck_pln_mrp_result_gross"),
        CheckConstraint("net_requirement >= 0", name="ck_pln_mrp_result_net"),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')",
            name="ck_pln_mrp_result_status",
        ),
    )


# ====================================================================
# 生产作业计划 / 派工 / 领料 / 完工
# ====================================================================


class PlnProductionPlan(Base, AuditMixin):
    """车间生产作业计划：承接 MRP 自制（MAKE）需求。"""

    __tablename__ = "pln_production_plan"

    id: Mapped[BigIntPk]
    plan_no: Mapped[CodeStr] = mapped_column(unique=True, comment="作业计划编号")
    mrp_result_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("pln_mrp_result.id", ondelete="RESTRICT"), nullable=True, index=True, comment="MRP结果ID"
    )
    # 来源：MRP / 库存生产补库需求（规格 §14）
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MRP", comment="来源 MRP/REPLENISHMENT/MANUAL"
    )
    source_reference_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="来源单据ID（多态引用）"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="自制件物料ID"
    )
    planned_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="计划生产数量"
    )
    completed_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="已完工数量"
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划日期")
    start_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划开始日期")
    end_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划完成日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint("planned_qty > 0", name="ck_pln_production_plan_qty"),
        CheckConstraint("completed_qty >= 0", name="ck_pln_production_plan_completed"),
        CheckConstraint(
            "source_type IN ('MRP','REPLENISHMENT','MANUAL')", name="ck_pln_production_plan_source"
        ),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')",
            name="ck_pln_production_plan_status",
        ),
    )


class PlnDispatchOrder(Base, AuditMixin):
    """派工单：把作业计划下达到具体工序 / 作业人员。"""

    __tablename__ = "pln_dispatch_order"

    id: Mapped[BigIntPk]
    dispatch_no: Mapped[CodeStr] = mapped_column(unique=True, comment="派工单号")
    plan_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("pln_production_plan.id", ondelete="RESTRICT"), nullable=True, index=True, comment="生产作业计划ID"
    )
    operation: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, comment="工序")
    planned_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="派工数量"
    )
    completed_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="完成数量"
    )
    worker_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_personnel.id", ondelete="RESTRICT"), nullable=True, index=True, comment="作业人员（sys_personnel.id）"
    )
    planned_start: Mapped[date] = mapped_column(Date, nullable=False, comment="计划开始日期")
    planned_end: Mapped[date] = mapped_column(Date, nullable=False, comment="计划结束日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint("planned_qty > 0", name="ck_pln_dispatch_qty"),
        CheckConstraint("completed_qty >= 0", name="ck_pln_dispatch_completed"),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')",
            name="ck_pln_dispatch_status",
        ),
    )


class PlnMaterialRequisition(Base, AuditMixin):
    """领料单头：生产领料的申请与执行（执行时走 inventory 出库）。"""

    __tablename__ = "pln_material_requisition"

    id: Mapped[BigIntPk]
    req_no: Mapped[CodeStr] = mapped_column(unique=True, comment="领料单号")
    plan_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("pln_production_plan.id", ondelete="RESTRICT"), nullable=True, index=True, comment="生产作业计划ID"
    )
    warehouse_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=True, comment="领料仓库ID"
    )
    req_date: Mapped[date] = mapped_column(Date, nullable=False, comment="领料日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["PlnMaterialRequisitionItem"]] = relationship(
        back_populates="requisition", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')",
            name="ck_pln_requisition_status",
        ),
    )


class PlnMaterialRequisitionItem(Base, AuditMixin):
    """领料单行。`issued_qty` 由实际出库回写。"""

    __tablename__ = "pln_material_requisition_item"

    id: Mapped[BigIntPk]
    requisition_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("pln_material_requisition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="领料单头ID",
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="物料ID"
    )
    required_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="需求数量"
    )
    issued_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="已领数量"
    )
    location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, comment="领料库位ID"
    )
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    requisition: Mapped[PlnMaterialRequisition] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("required_qty > 0", name="ck_pln_req_item_required"),
        CheckConstraint("issued_qty >= 0", name="ck_pln_req_item_issued"),
    )


class PlnCompletionReport(Base, AuditMixin):
    """完工报告：生产完工报工（确认后走 inventory 入库，增加半成品/成品库存）。"""

    __tablename__ = "pln_completion_report"

    id: Mapped[BigIntPk]
    report_no: Mapped[CodeStr] = mapped_column(unique=True, comment="完工报告单号")
    plan_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("pln_production_plan.id", ondelete="RESTRICT"), nullable=True, index=True, comment="生产作业计划ID"
    )
    dispatch_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("pln_dispatch_order.id", ondelete="RESTRICT"), nullable=True, comment="派工单ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"), nullable=False, index=True, comment="产出物料ID"
    )
    completed_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="完工数量"
    )
    qualified_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="合格数量（入库数量）"
    )
    scrap_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="报废数量"
    )
    warehouse_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("inv_warehouse.id", ondelete="RESTRICT"), nullable=False, comment="入库仓库ID"
    )
    location_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("inv_location.id", ondelete="RESTRICT"), nullable=True, comment="入库库位ID"
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False, comment="报工日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", index=True, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint("completed_qty > 0", name="ck_pln_completion_qty"),
        CheckConstraint("qualified_qty >= 0", name="ck_pln_completion_qualified"),
        CheckConstraint("scrap_qty >= 0", name="ck_pln_completion_scrap"),
        CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')", name="ck_pln_completion_status"
        ),
    )