"""system 模块 RBAC 初始化数据（种子数据）。

为注册页 / 管理界面提供 **九种人员身份**（角色）、覆盖五个模块功能的权限资源树，
以及角色与权限的绑定关系。由 `app/main.py` 启动时调用 `seed_roles_and_permissions(db)`。

设计约定：

- 权限编码统一为 `模块:功能[:操作]` 形式，如 `system:user:approve`；
- 质检、财务没有独立业务模块，权限按业务域挂靠：
  - QC（质检人员）：`procurement:qc`（到货质检）、`planning:qc`（完工质检）；
  - FINANCE（财务）：各业务模块单据、计划结果与库存流水**只读查看**，不授予系统管理能力；
- 种子函数幂等：按 `role_code` / `perm_code` 唯一编码判断是否已存在，存在即跳过，
  只补缺失的绑定关系，不会覆盖运营期的人工调整。
"""

from typing import Any

from sqlalchemy.orm import Session

from app.modules.system import models

# --------------------------------------------------------------------------- #
# 一、九种人员身份（角色）
# --------------------------------------------------------------------------- #
# 团队版 SysRole 无 data_scope / sort_order 列，数据范围约定并入 description 供注册页展示。
ROLE_SEEDS: list[dict[str, Any]] = [
    {
        "role_code": "ADMIN",
        "role_name": "管理人员",
        "status": "ACTIVE",
        "description": "拥有系统全部功能权限，可管理账号、角色与权限（数据范围：全部）",
    },
    {
        "role_code": "DESIGN",
        "role_name": "设计人员",
        "status": "ACTIVE",
        "description": "维护物料、BOM、工艺路线，查看基础字典（数据范围：全部）",
    },
    {
        "role_code": "MAKE",
        "role_name": "制造人员",
        "status": "ACTIVE",
        "description": "查看物料/BOM/工艺，执行生产作业、领料与完工入库（数据范围：仅本人）",
    },
    {
        "role_code": "PURCHASE",
        "role_name": "采购人员",
        "status": "ACTIVE",
        "description": "处理采购计划、采购需求、采购订单与到货（数据范围：本组织）",
    },
    {
        "role_code": "SALES",
        "role_name": "销售人员",
        "status": "ACTIVE",
        "description": "处理销售需求、销售订单与发货指令，查看可发货量（数据范围：本组织及下级）",
    },
    {
        "role_code": "INVENTORY",
        "role_name": "库存人员",
        "status": "ACTIVE",
        "description": "管理出入库与实时库存，查看发货指令、领料单与到货信息（数据范围：全部）",
    },
    {
        "role_code": "PLAN",
        "role_name": "计划管理人员",
        "status": "ACTIVE",
        "description": "编制 MPS/MRP/作业计划并派工，查看 BOM/物料/库存/销售需求（数据范围：全部）",
    },
    {
        "role_code": "QC",
        "role_name": "质检人员",
        "status": "ACTIVE",
        "description": "负责到货质检与完工质检，无独立业务模块（数据范围：全部）",
    },
    {
        "role_code": "FINANCE",
        "role_name": "财务",
        "status": "ACTIVE",
        "description": "只读查看各业务单据、计划结果与库存流水，用于核算监督（数据范围：全部）",
    },
]

# --------------------------------------------------------------------------- #
# 二、权限资源树（五个模块的功能划分）
# --------------------------------------------------------------------------- #
# 每条记录：code 权限编码 / name 权限名称 / perm_type 类型 / parent 上级权限编码 /
#           path 前端路由 / module 所属模块 / sort_no 排序。父节点必须先于子节点声明。
# 团队版 perm_type 合法值：MENU / PAGE / ACTION（旧版 BUTTON 一律映射为 ACTION）。
PERMISSION_SEEDS: list[dict[str, Any]] = [
    # ---- 模块根节点 ----
    {"code": "system", "name": "系统与基础信息管理", "perm_type": "MENU",
     "parent": None, "path": "/system", "module": "system", "sort_no": 10},
    {"code": "sales", "name": "销售管理", "perm_type": "MENU",
     "parent": None, "path": "/sales", "module": "sales", "sort_no": 20},
    {"code": "planning", "name": "计划管理", "perm_type": "MENU",
     "parent": None, "path": "/planning", "module": "planning", "sort_no": 30},
    {"code": "procurement", "name": "采购管理", "perm_type": "MENU",
     "parent": None, "path": "/procurement", "module": "procurement", "sort_no": 40},
    {"code": "inventory", "name": "库存管理", "perm_type": "MENU",
     "parent": None, "path": "/inventory", "module": "inventory", "sort_no": 50},
    # ---- system：物料 / BOM / 工艺 / 组织人员 / 字典 / 账号 / 角色 / 权限 / 日志 ----
    {"code": "system:material", "name": "物料管理", "perm_type": "MENU",
     "parent": "system", "path": "/system/material", "module": "system", "sort_no": 10},
    {"code": "system:bom", "name": "BOM 管理", "perm_type": "MENU",
     "parent": "system", "path": "/system/bom", "module": "system", "sort_no": 20},
    {"code": "system:routing", "name": "工艺路线管理", "perm_type": "MENU",
     "parent": "system", "path": "/system/routing", "module": "system", "sort_no": 30},
    {"code": "system:org", "name": "组织与人员", "perm_type": "MENU",
     "parent": "system", "path": "/system/org", "module": "system", "sort_no": 40},
    {"code": "system:dictionary", "name": "基础字典", "perm_type": "MENU",
     "parent": "system", "path": "/system/dictionary", "module": "system", "sort_no": 50},
    {"code": "system:user", "name": "账号管理", "perm_type": "MENU",
     "parent": "system", "path": "/system/user", "module": "system", "sort_no": 60},
    {"code": "system:role", "name": "角色管理", "perm_type": "MENU",
     "parent": "system", "path": "/system/role", "module": "system", "sort_no": 70},
    {"code": "system:permission", "name": "权限管理", "perm_type": "MENU",
     "parent": "system", "path": "/system/permission", "module": "system", "sort_no": 80},
    {"code": "system:log", "name": "操作日志", "perm_type": "MENU",
     "parent": "system", "path": "/system/log", "module": "system", "sort_no": 90},
    # system 常规写操作（功能码 = 查看；`:manage` = 新增 / 修改 / 删除等写操作）
    {"code": "system:material:manage", "name": "维护物料", "perm_type": "ACTION",
     "parent": "system:material", "path": "/system/material", "module": "system", "sort_no": 10},
    {"code": "system:bom:manage", "name": "维护 BOM", "perm_type": "ACTION",
     "parent": "system:bom", "path": "/system/bom", "module": "system", "sort_no": 10},
    {"code": "system:routing:manage", "name": "维护工艺路线", "perm_type": "ACTION",
     "parent": "system:routing", "path": "/system/routing", "module": "system", "sort_no": 10},
    {"code": "system:org:manage", "name": "维护组织与人员", "perm_type": "ACTION",
     "parent": "system:org", "path": "/system/org", "module": "system", "sort_no": 10},
    {"code": "system:dictionary:manage", "name": "维护基础字典", "perm_type": "ACTION",
     "parent": "system:dictionary", "path": "/system/dictionary", "module": "system", "sort_no": 10},
    {"code": "system:user:manage", "name": "维护账号", "perm_type": "ACTION",
     "parent": "system:user", "path": "/system/user", "module": "system", "sort_no": 10},
    {"code": "system:role:manage", "name": "维护角色", "perm_type": "ACTION",
     "parent": "system:role", "path": "/system/role", "module": "system", "sort_no": 10},
    {"code": "system:permission:manage", "name": "维护权限", "perm_type": "ACTION",
     "parent": "system:permission", "path": "/system/permission", "module": "system", "sort_no": 10},
    {"code": "system:log:manage", "name": "维护操作日志", "perm_type": "ACTION",
     "parent": "system:log", "path": "/system/log", "module": "system", "sort_no": 10},
    # system 高危操作（仅管理人员持有）
    {"code": "system:user:approve", "name": "注册审批", "perm_type": "ACTION",
     "parent": "system:user", "path": "/system/users/{id}/approve", "module": "system", "sort_no": 10},
    {"code": "system:user:assign", "name": "分配用户角色", "perm_type": "ACTION",
     "parent": "system:user", "path": "/system/users/{id}/roles", "module": "system", "sort_no": 20},
    {"code": "system:user:reset", "name": "重置密码", "perm_type": "ACTION",
     "parent": "system:user", "path": "/system/users/{id}/password", "module": "system", "sort_no": 30},
    {"code": "system:role:assign", "name": "分配角色权限", "perm_type": "ACTION",
     "parent": "system:role", "path": "/system/roles/{id}/permissions", "module": "system", "sort_no": 10},
    {"code": "system:log:clear", "name": "清理操作日志", "perm_type": "ACTION",
     "parent": "system:log", "path": "/system/operation-logs", "module": "system", "sort_no": 10},
    # ---- sales：订单 / 需求与预测 / 发货指令 / 可发货量 ----
    {"code": "sales:order", "name": "销售订单", "perm_type": "MENU",
     "parent": "sales", "path": "/sales/order", "module": "sales", "sort_no": 10},
    {"code": "sales:demand", "name": "销售需求与预测", "perm_type": "MENU",
     "parent": "sales", "path": "/sales/demand", "module": "sales", "sort_no": 20},
    {"code": "sales:shipping", "name": "发货指令", "perm_type": "MENU",
     "parent": "sales", "path": "/sales/shipping", "module": "sales", "sort_no": 30},
    {"code": "sales:stock", "name": "可发货量查询", "perm_type": "MENU",
     "parent": "sales", "path": "/sales/stock", "module": "sales", "sort_no": 40},
    # ---- planning：MPS / MRP / 作业计划 / 派工 / 领料 / 完工入库 / 完工质检 ----
    {"code": "planning:mps", "name": "主生产计划 MPS", "perm_type": "MENU",
     "parent": "planning", "path": "/planning/mps", "module": "planning", "sort_no": 10},
    {"code": "planning:mrp", "name": "物料需求计划 MRP", "perm_type": "MENU",
     "parent": "planning", "path": "/planning/mrp", "module": "planning", "sort_no": 20},
    {"code": "planning:schedule", "name": "生产作业计划", "perm_type": "MENU",
     "parent": "planning", "path": "/planning/schedule", "module": "planning", "sort_no": 30},
    {"code": "planning:dispatch", "name": "派工单", "perm_type": "MENU",
     "parent": "planning", "path": "/planning/dispatch", "module": "planning", "sort_no": 40},
    {"code": "planning:picking", "name": "领料单", "perm_type": "MENU",
     "parent": "planning", "path": "/planning/picking", "module": "planning", "sort_no": 50},
    {"code": "planning:finish", "name": "完工入库", "perm_type": "MENU",
     "parent": "planning", "path": "/planning/finish", "module": "planning", "sort_no": 60},
    {"code": "planning:qc", "name": "完工质检", "perm_type": "MENU",
     "parent": "planning", "path": "/planning/qc", "module": "planning", "sort_no": 70},
    # ---- procurement：采购计划 / 采购需求 / 采购订单 / 到货 / 到货质检 ----
    {"code": "procurement:plan", "name": "采购计划", "perm_type": "MENU",
     "parent": "procurement", "path": "/procurement/plan", "module": "procurement", "sort_no": 10},
    {"code": "procurement:demand", "name": "采购需求", "perm_type": "MENU",
     "parent": "procurement", "path": "/procurement/demand", "module": "procurement", "sort_no": 20},
    {"code": "procurement:order", "name": "采购订单", "perm_type": "MENU",
     "parent": "procurement", "path": "/procurement/order", "module": "procurement", "sort_no": 30},
    {"code": "procurement:arrival", "name": "到货管理", "perm_type": "MENU",
     "parent": "procurement", "path": "/procurement/arrival", "module": "procurement", "sort_no": 40},
    {"code": "procurement:qc", "name": "到货质检", "perm_type": "MENU",
     "parent": "procurement", "path": "/procurement/qc", "module": "procurement", "sort_no": 50},
    # ---- inventory：库存状态 / 入库 / 出库 / 流水与结存 ----
    {"code": "inventory:stock", "name": "库存状态查询", "perm_type": "MENU",
     "parent": "inventory", "path": "/inventory/stock", "module": "inventory", "sort_no": 10},
    {"code": "inventory:inbound", "name": "入库管理", "perm_type": "MENU",
     "parent": "inventory", "path": "/inventory/inbound", "module": "inventory", "sort_no": 20},
    {"code": "inventory:outbound", "name": "出库管理", "perm_type": "MENU",
     "parent": "inventory", "path": "/inventory/outbound", "module": "inventory", "sort_no": 30},
    {"code": "inventory:ledger", "name": "库存流水与结存", "perm_type": "MENU",
     "parent": "inventory", "path": "/inventory/ledger", "module": "inventory", "sort_no": 40},
]

# 所有权限编码（供 ADMIN 全量授权使用）
ALL_PERMISSION_CODES: list[str] = [item["code"] for item in PERMISSION_SEEDS]

#: 注册页可选身份的角色编码（按展示顺序）
REGISTER_ROLE_CODES: list[str] = [item["role_code"] for item in ROLE_SEEDS]

# --------------------------------------------------------------------------- #
# 三、角色-权限绑定（按五个模块的功能划分）
# --------------------------------------------------------------------------- #
ROLE_PERMISSION_BINDINGS: dict[str, list[str]] = {
    "ADMIN": ALL_PERMISSION_CODES,
    "DESIGN": [
        "system", "system:material", "system:bom", "system:routing", "system:dictionary",
        "system:material:manage", "system:bom:manage", "system:routing:manage",
    ],
    "MAKE": [
        "system", "system:material", "system:bom", "system:routing",
        "planning", "planning:schedule", "planning:dispatch", "planning:picking", "planning:finish",
    ],
    "PURCHASE": [
        "procurement", "procurement:plan", "procurement:demand",
        "procurement:order", "procurement:arrival",
        "system:material", "system:dictionary",
    ],
    "SALES": [
        "sales", "sales:order", "sales:demand", "sales:shipping", "sales:stock",
        "system:material",
    ],
    "INVENTORY": [
        "inventory", "inventory:stock", "inventory:inbound",
        "inventory:outbound", "inventory:ledger",
        "sales", "sales:shipping",
        "planning", "planning:picking",
        "procurement", "procurement:arrival",
        "system:material",
    ],
    "PLAN": [
        "planning", "planning:mps", "planning:mrp", "planning:schedule",
        "planning:dispatch", "planning:picking", "planning:finish",
        "system:bom", "system:material",
        "inventory:stock",
        "sales:demand",
    ],
    "QC": [
        "procurement:qc", "procurement:arrival",
        "planning:qc", "planning:finish",
        "system:material", "system:routing",
    ],
    "FINANCE": [
        "sales:order", "sales:demand", "sales:shipping",
        "procurement:plan", "procurement:order", "procurement:arrival",
        "planning:mps", "planning:mrp", "planning:schedule", "planning:finish",
        "inventory:stock", "inventory:inbound", "inventory:outbound", "inventory:ledger",
        "system:material",
    ],
}


def seed_roles_and_permissions(db: Session) -> None:
    """幂等写入九种身份角色、权限资源树与角色-权限绑定。

    按 `role_code` / `perm_code` 存在即跳过，只补缺失的绑定，
    不会覆盖运营期的人工调整。由应用启动时调用。
    """
    # 1. 角色：按编码存在即跳过，不覆盖人工调整
    role_map: dict[str, models.SysRole] = {}
    for spec in ROLE_SEEDS:
        code = spec["role_code"]
        role = db.query(models.SysRole).filter(models.SysRole.role_code == code).first()
        if role is None:
            role = models.SysRole(**spec)
            db.add(role)
            db.flush()
        role_map[code] = role

    # 2. 权限：父节点必须先于子节点写入，子节点拿父节点 ID 挂树
    perm_map: dict[str, models.SysPermission] = {}
    for spec in PERMISSION_SEEDS:
        code = spec["code"]
        existing = (
            db.query(models.SysPermission)
            .filter(models.SysPermission.perm_code == code)
            .first()
        )
        if existing is not None:
            perm_map[code] = existing
            continue
        parent_code = spec.get("parent")
        if parent_code is not None and parent_code not in perm_map:
            raise ValueError(f"权限种子定义错误：{code} 的上级权限 {parent_code} 尚未声明")
        perm = models.SysPermission(
            perm_code=code,
            perm_name=spec["name"],
            perm_type=spec["perm_type"],
            parent_id=perm_map[parent_code].id if parent_code else None,
            path=spec.get("path"),
            module=spec.get("module"),
            sort_no=int(spec.get("sort_no", 0)),
            status="ACTIVE",
        )
        db.add(perm)
        db.flush()
        perm_map[code] = perm

    # 3. 绑定：只补缺失的关联，不删除已存在的人工调整
    existing_pairs = {
        (row.role_id, row.permission_id)
        for row in db.query(models.SysRolePermission).all()
    }
    for role_code, perm_codes in ROLE_PERMISSION_BINDINGS.items():
        role = role_map[role_code]
        for perm_code in perm_codes:
            if perm_code not in perm_map:
                raise ValueError(f"角色 {role_code} 引用了未定义的权限编码：{perm_code}")
            perm = perm_map[perm_code]
            if (role.id, perm.id) not in existing_pairs:
                db.add(models.SysRolePermission(role_id=role.id, permission_id=perm.id))

    db.commit()