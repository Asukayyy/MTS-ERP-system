"""system 模块 ORM 模型 —— 企业基础主数据与平台管理。

本模块是**全系统唯一的基础数据 Owner**（规格 §7 / §8 / §10）：

- 唯一物料主表 `sys_material`（用 `material_type` 区分 RAW/PURCHASED/SEMI/FINISHED，
  不做独立的 product / material 多套表）。其他模块**只读**，禁止另建物料表。
- 唯一员工表 `sys_personnel`（禁止 sal_salesperson / pur_buyer / inv_staff / pln_worker）。
- BOM / 工艺路线 / 组织 / 字典 / RBAC / 操作日志。

建模约定：

1. 表名 `snake_case` + `sys_` 前缀；主键统一 `BIGINT`（`BigIntPk`）。
2. 模块**内部**关系使用真实外键；跨模块引用也统一指向对方 `id`
   并使用 `ON DELETE RESTRICT`（规格 §20），避免基础数据被删除导致历史业务丢失。
3. 业务状态使用明确枚举 + `CHECK` 约束（规格 §23 / §25）。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from app.core.mixins import AuditMixin, BigIntFk, BigIntPk, CodeStr, Money, NameStr
from app.shared.enums import MaterialType, RecordStatus, SupplyType

# ====================================================================
# 组织 / 人员 / 账号（规格 §10：员工统一由 System 平台管理）
# ====================================================================


class SysOrganization(Base, AuditMixin):
    """组织 / 部门（树形，`parent_id` 自引用）。"""

    __tablename__ = "sys_organization"

    id: Mapped[BigIntPk]
    org_code: Mapped[CodeStr] = mapped_column(unique=True, comment="组织编码")
    org_name: Mapped[NameStr] = mapped_column(comment="组织名称")
    parent_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_organization.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="上级组织ID",
    )
    org_type: Mapped[str] = mapped_column(String(20), nullable=False, default="DEPARTMENT", comment="组织类型")
    manager_id: Mapped[Optional[BigIntFk]] = mapped_column(
        BigInteger, nullable=True, comment="负责人ID（sys_personnel.id，延迟引用避免建表循环）"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name="ck_sys_organization_status"
        ),
        CheckConstraint(
            "org_type IN ('COMPANY','FACTORY','DEPARTMENT','WORKSHOP','WAREHOUSE')",
            name="ck_sys_organization_type",
        ),
    )


class SysPersonnel(Base, AuditMixin):
    """企业员工（全系统唯一人员表）。"""

    __tablename__ = "sys_personnel"

    id: Mapped[BigIntPk]
    employee_no: Mapped[CodeStr] = mapped_column(unique=True, comment="员工工号")
    person_name: Mapped[NameStr] = mapped_column(comment="姓名")
    org_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_organization.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属组织ID"
    )
    position: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="岗位")
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, comment="联系电话")
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="邮箱")
    hire_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="入职日期")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name="ck_sys_personnel_status"
        ),
    )


class SysUser(Base, AuditMixin):
    """软件登录账号（与 Personnel 分离：一个 Personnel 可有 0 或 1 个 User）。"""

    __tablename__ = "sys_user"

    id: Mapped[BigIntPk]
    username: Mapped[CodeStr] = mapped_column(unique=True, comment="登录名")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    display_name: Mapped[NameStr] = mapped_column(comment="显示名")
    personnel_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_personnel.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
        comment="关联员工ID（1:1，可为空）",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近登录时间")
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    roles: Mapped[List["SysRole"]] = relationship(
        secondary="sys_user_role", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_sys_user_status"),
    )


class SysRole(Base, AuditMixin):
    """角色（规格 §30：System Administrator / Sales User / Planner / Buyer / Warehouse User）。"""

    __tablename__ = "sys_role"

    id: Mapped[BigIntPk]
    role_code: Mapped[CodeStr] = mapped_column(unique=True, comment="角色编码")
    role_name: Mapped[NameStr] = mapped_column(comment="角色名称")
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="描述")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )

    permissions: Mapped[List["SysPermission"]] = relationship(
        secondary="sys_role_permission", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_sys_role_status"),
    )


class SysPermission(Base, AuditMixin):
    """权限点：菜单 / 页面 / 关键操作（树形）。"""

    __tablename__ = "sys_permission"

    id: Mapped[BigIntPk]
    perm_code: Mapped[CodeStr] = mapped_column(unique=True, comment="权限编码")
    perm_name: Mapped[NameStr] = mapped_column(comment="权限名称")
    perm_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="权限类型")
    parent_id: Mapped[Optional[BigIntFk]] = mapped_column(
        ForeignKey("sys_permission.id", ondelete="RESTRICT"), nullable=True, index=True, comment="上级权限ID"
    )
    path: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="前端路由/接口路径")
    module: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="所属模块")
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序号")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )

    __table_args__ = (
        CheckConstraint("perm_type IN ('MENU','PAGE','ACTION')", name="ck_sys_permission_type"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_sys_permission_status"),
    )


class SysUserRole(Base):
    """用户 N:M 角色 关联表（规格 §21，禁止把多个 ID 塞进 VARCHAR）。"""

    __tablename__ = "sys_user_role"

    id: Mapped[BigIntPk]
    user_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID"
    )
    role_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_role.id", ondelete="CASCADE"), nullable=False, index=True, comment="角色ID"
    )

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_sys_user_role"),)


class SysRolePermission(Base):
    """角色 N:M 权限 关联表。"""

    __tablename__ = "sys_role_permission"

    id: Mapped[BigIntPk]
    role_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_role.id", ondelete="CASCADE"), nullable=False, index=True, comment="角色ID"
    )
    permission_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_permission.id", ondelete="CASCADE"), nullable=False, index=True, comment="权限ID"
    )

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_sys_role_permission"),
    )


# ====================================================================
# 字典
# ====================================================================


class SysDictionary(Base, AuditMixin):
    """数据字典（计量单位、物料分类等基础枚举的可维护来源）。"""

    __tablename__ = "sys_dictionary"

    id: Mapped[BigIntPk]
    dict_code: Mapped[CodeStr] = mapped_column(unique=True, comment="字典编码")
    dict_name: Mapped[NameStr] = mapped_column(comment="字典名称")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["SysDictionaryItem"]] = relationship(
        back_populates="dictionary", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_sys_dictionary_status"),
    )


class SysDictionaryItem(Base, AuditMixin):
    """字典项。"""

    __tablename__ = "sys_dictionary_item"

    id: Mapped[BigIntPk]
    dict_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_dictionary.id", ondelete="CASCADE"), nullable=False, index=True, comment="字典ID"
    )
    item_code: Mapped[CodeStr] = mapped_column(comment="字典项编码")
    item_name: Mapped[NameStr] = mapped_column(comment="字典项名称")
    item_value: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="字典项值")
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序号")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )

    dictionary: Mapped[SysDictionary] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("dict_id", "item_code", name="uq_sys_dictionary_item"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_sys_dictionary_item_status"),
    )


# ====================================================================
# 统一 Material Master（规格 §8）
# ====================================================================


class SysMaterial(Base, AuditMixin):
    """**全系统唯一物料主表**。

    - `material_type`: RAW / PURCHASED / SEMI / FINISHED
    - `supply_type`: MAKE（自制）/ BUY（采购）—— 决定 MRP 结果分流方向
    - `lead_time_days` / `safety_stock` 为 BOM 与 MRP 的必需字段（规格 §9）
    """

    __tablename__ = "sys_material"

    id: Mapped[BigIntPk]
    material_code: Mapped[CodeStr] = mapped_column(unique=True, comment="物料编码")
    material_name: Mapped[NameStr] = mapped_column(comment="物料名称")
    material_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="物料类型 RAW/PURCHASED/SEMI/FINISHED"
    )
    supply_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="供应类型 MAKE/BUY"
    )
    unit_code: Mapped[str] = mapped_column(String(20), nullable=False, default="PCS", comment="计量单位")
    specification: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="规格型号")
    material_group: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="物料分组")
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="提前期（天）")
    safety_stock: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="安全库存"
    )
    standard_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0, comment="标准成本"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    __table_args__ = (
        CheckConstraint(
            "material_type IN ('RAW','PURCHASED','SEMI','FINISHED')", name="ck_sys_material_type"
        ),
        CheckConstraint("supply_type IN ('MAKE','BUY')", name="ck_sys_material_supply_type"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_sys_material_status"),
        CheckConstraint("safety_stock >= 0", name="ck_sys_material_safety_stock"),
        CheckConstraint("lead_time_days >= 0", name="ck_sys_material_lead_time"),
    )


# ====================================================================
# BOM（规格 §9：必须正式支持提前期与版本，必须支持多层）
# ====================================================================


class SysBom(Base, AuditMixin):
    """BOM 头：某物料在某个版本下的组成关系。`(material_id, bom_version)` 唯一。"""

    __tablename__ = "sys_bom"

    id: Mapped[BigIntPk]
    bom_code: Mapped[CodeStr] = mapped_column(comment="BOM编码")
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="母件物料ID（sys_material.id）",
    )
    bom_version: Mapped[str] = mapped_column(String(20), nullable=False, default="V1.0", comment="BOM版本")
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="生效日期")
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="失效日期")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否当前激活版本"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    items: Mapped[List["SysBomItem"]] = relationship(
        back_populates="bom", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("material_id", "bom_version", name="uq_sys_bom_material_version"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_sys_bom_status"),
    )


class SysBomItem(Base, AuditMixin):
    """BOM 子项：母件 → 子件，含数量与损耗率（支持多层展开）。"""

    __tablename__ = "sys_bom_item"

    id: Mapped[BigIntPk]
    bom_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_bom.id", ondelete="CASCADE"), nullable=False, index=True, comment="BOM头ID"
    )
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="子件物料ID（sys_material.id）",
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=1, comment="单位用量"
    )
    lead_time_offset: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="提前期偏置（天，相对父件需求时间的提前量）"
    )
    scrap_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0, comment="损耗率（0~1）"
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="序号")
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    bom: Mapped[SysBom] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("bom_id", "material_id", name="uq_sys_bom_item"),
        CheckConstraint("quantity > 0", name="ck_sys_bom_item_qty"),
        CheckConstraint("lead_time_offset >= 0", name="ck_sys_bom_item_lead_offset"),
        CheckConstraint("scrap_rate >= 0 AND scrap_rate < 1", name="ck_sys_bom_item_scrap"),
    )


# ====================================================================
# 工艺路线（Routing）
# ====================================================================


class SysRouting(Base, AuditMixin):
    """工艺路线头：某自制件的加工工序集合。"""

    __tablename__ = "sys_routing"

    id: Mapped[BigIntPk]
    routing_code: Mapped[CodeStr] = mapped_column(comment="工艺路线编码")
    material_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_material.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="自制件物料ID（sys_material.id）",
    )
    routing_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="V1.0", comment="工艺版本"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecordStatus.ACTIVE.value, comment="状态"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")

    operations: Mapped[List["SysRoutingOperation"]] = relationship(
        back_populates="routing", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("material_id", "routing_version", name="uq_sys_routing_material_version"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_sys_routing_status"),
    )


class SysRoutingOperation(Base, AuditMixin):
    """工艺路线工序行。"""

    __tablename__ = "sys_routing_operation"

    id: Mapped[BigIntPk]
    routing_id: Mapped[BigIntFk] = mapped_column(
        ForeignKey("sys_routing.id", ondelete="CASCADE"), nullable=False, index=True, comment="工艺路线ID"
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="工序顺序号")
    operation_code: Mapped[CodeStr] = mapped_column(comment="工序编码")
    operation_name: Mapped[NameStr] = mapped_column(comment="工序名称")
    work_center: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="工作中心")
    setup_time: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="准备工时（分钟）"
    )
    run_time: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, comment="单件加工工时（分钟）"
    )
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="备注")

    routing: Mapped[SysRouting] = relationship(back_populates="operations")

    __table_args__ = (
        UniqueConstraint("routing_id", "sequence_no", name="uq_sys_routing_operation_seq"),
        CheckConstraint("setup_time >= 0", name="ck_sys_routing_op_setup"),
        CheckConstraint("run_time >= 0", name="ck_sys_routing_op_run"),
    )


# ====================================================================
# 操作日志（规格 §24：重要业务动作写 sys_operation_log）
# ====================================================================


class SysOperationLog(Base):
    """操作日志：记录关键业务动作，便于审计追踪。"""

    __tablename__ = "sys_operation_log"

    id: Mapped[BigIntPk]
    module: Mapped[str] = mapped_column(String(20), nullable=False, index=True, comment="模块标识")
    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="动作（CREATE/CONFIRM/...）")
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="目标对象类型（表名）")
    target_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="目标对象ID")
    operator_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="操作人ID（sys_user.id）")
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="详情")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, comment="发生时间"
    )