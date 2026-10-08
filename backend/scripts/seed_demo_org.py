# -*- coding: utf-8 -*-
"""组织/人员/账号演示数据种子脚本（幂等，可重复执行）。

功能：
1. 清理垃圾角色（仅保留 13 个正式身份）、
   全部旧账号、旧员工、旧组织；
2. 重建组织架构：1 个公司根 + 8 个部门 + 智能加工中心（FACTORY，下辖下料/数控/车工/铣工/钳工/磨工/粉末冶金/总装/包装 9 个车间，覆盖全部工艺路线工序）；
   设计部**不配人**，设计人员由用户自行创建；
3. 重建人员与账号（初始密码统一 123456）：
   - 管理员 3：徐黔晨 / 陈自鹏 / 牛晕针（ADMIN）
   - 销售 5（SALES）、采购 5（PURCHASE）、仓储 5（INVENTORY）
   - 计划 2（PLAN）、生产 10（MAKE，经理挂中心、9 车间各 1 人）、质检 2（QC）、财务 2（FINANCE）
   共 34 人，每人完成「员工档案 → 登录账号 → 角色绑定」全链路。

执行方式（cwd = backend）：
    .venv/Scripts/python.exe scripts/seed_demo_org.py
"""

import hashlib
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.modules.system import models

# ============================ 常量 ============================

SEED_ROLE_CODES = ("ADMIN", "DESIGN", "MAKE", "PURCHASE", "SALES", "INVENTORY", "PLAN", "QC", "FINANCE", "DEPT_HEAD", "WORKER", "GROUP_LEADER", "DIRECTOR")
DEFAULT_PASSWORD = "123456"

# (组织编码, 名称, 上级编码, 类型)
ORGS = [
    ("CO-001", "大众自动钳制造有限公司", None, "COMPANY"),
    ("DEP-ADMIN", "总经办", "CO-001", "DEPARTMENT"),
    ("DEP-DESIGN", "设计部", "CO-001", "DEPARTMENT"),
    ("DEP-PLAN", "计划部", "CO-001", "DEPARTMENT"),
    ("DEP-PURCHASE", "采购部", "CO-001", "DEPARTMENT"),
    ("DEP-SALES", "销售部", "CO-001", "DEPARTMENT"),
    ("DEP-WAREHOUSE", "仓储部", "CO-001", "DEPARTMENT"),
    ("DEP-QC", "质检部", "CO-001", "DEPARTMENT"),
    ("DEP-FINANCE", "财务部", "CO-001", "DEPARTMENT"),
    # 生产工厂：统一归入智能加工中心，下按工艺流程设 9 个车间（覆盖全部 42 道工序）
    ("MFG-CTR", "智能加工中心", "CO-001", "FACTORY"),
    ("MFG-CUT", "下料车间", "MFG-CTR", "WORKSHOP"),
    ("MFG-CNC", "数控加工车间", "MFG-CTR", "WORKSHOP"),
    ("MFG-TURN", "车工车间", "MFG-CTR", "WORKSHOP"),
    ("MFG-MILL", "铣工车间", "MFG-CTR", "WORKSHOP"),
    ("MFG-FIT", "钳工车间", "MFG-CTR", "WORKSHOP"),
    ("MFG-GRIND", "磨工车间", "MFG-CTR", "WORKSHOP"),
    ("MFG-PM", "粉末冶金车间", "MFG-CTR", "WORKSHOP"),
    ("MFG-ASSY", "总装车间", "MFG-CTR", "WORKSHOP"),
    ("MFG-PACK", "包装车间", "MFG-CTR", "WORKSHOP"),
]

# (姓名, 部门编码, 岗位, 工号前缀, 工号序号, 账号, 角色编码)
STAFF = [
    # 管理员 3
    ("徐黔晨", "DEP-ADMIN", "系统管理员", "ADM", 1, "xuqianchen", "ADMIN"),
    ("陈自鹏", "DEP-ADMIN", "系统管理员", "ADM", 2, "chenzipeng", "ADMIN"),
    ("牛晕针", "DEP-ADMIN", "系统管理员", "ADM", 3, "niuyunzhen", "ADMIN"),
    # 计划 2
    ("王志远", "DEP-PLAN", "计划经理", "PLN", 1, "planner01", "PLAN"),
    ("李思敏", "DEP-PLAN", "计划员", "PLN", 2, "planner02", "PLAN"),
    # 生产 10（智能加工中心：经理挂中心，9 个车间各 1 名操作员）
    ("张伟强", "MFG-CTR", "加工中心经理", "MFG", 1, "maker01", "MAKE"),
    ("刘建国", "MFG-CUT", "下料车间操作员", "MFG", 2, "maker02", "MAKE"),
    ("周海涛", "MFG-CNC", "数控车间操作员", "MFG", 3, "maker03", "MAKE"),
    ("钱德明", "MFG-TURN", "车工车间操作员", "MFG", 4, "maker04", "MAKE"),
    ("孙大勇", "MFG-MILL", "铣工车间操作员", "MFG", 5, "maker05", "MAKE"),
    ("李明华", "MFG-FIT", "钳工车间操作员", "MFG", 6, "maker06", "MAKE"),
    ("王守成", "MFG-GRIND", "磨工车间操作员", "MFG", 7, "maker07", "MAKE"),
    ("赵铁生", "MFG-PM", "粉末冶金车间操作员", "MFG", 8, "maker08", "MAKE"),
    ("吴刚", "MFG-ASSY", "总装车间操作员", "MFG", 9, "maker09", "MAKE"),
    ("郑维国", "MFG-PACK", "包装车间操作员", "MFG", 10, "maker10", "MAKE"),
    # 采购 5
    ("孙立国", "DEP-PURCHASE", "采购经理", "PUR", 1, "purchase01", "PURCHASE"),
    ("钱进", "DEP-PURCHASE", "采购员", "PUR", 2, "purchase02", "PURCHASE"),
    ("吴敏", "DEP-PURCHASE", "采购员", "PUR", 3, "purchase03", "PURCHASE"),
    ("郑凯", "DEP-PURCHASE", "采购员", "PUR", 4, "purchase04", "PURCHASE"),
    ("冯雪", "DEP-PURCHASE", "采购员", "PUR", 5, "purchase05", "PURCHASE"),
    # 销售 5
    ("周晓东", "DEP-SALES", "销售经理", "SAL", 1, "sales01", "SALES"),
    ("吴婷", "DEP-SALES", "销售员", "SAL", 2, "sales02", "SALES"),
    ("郑浩然", "DEP-SALES", "销售员", "SAL", 3, "sales03", "SALES"),
    ("王丽", "DEP-SALES", "销售员", "SAL", 4, "sales04", "SALES"),
    ("陈静", "DEP-SALES", "销售员", "SAL", 5, "sales05", "SALES"),
    # 仓储 5
    ("许强", "DEP-WAREHOUSE", "仓储经理", "WH", 1, "warehouse01", "INVENTORY"),
    ("蒋海峰", "DEP-WAREHOUSE", "仓管员", "WH", 2, "warehouse02", "INVENTORY"),
    ("沈斌", "DEP-WAREHOUSE", "仓管员", "WH", 3, "warehouse03", "INVENTORY"),
    ("韩梅", "DEP-WAREHOUSE", "仓管员", "WH", 4, "warehouse04", "INVENTORY"),
    ("杨军", "DEP-WAREHOUSE", "仓管员", "WH", 5, "warehouse05", "INVENTORY"),
    # 质检 2
    ("秦刚", "DEP-QC", "质检经理", "QC", 1, "qc01", "QC"),
    ("朱琳", "DEP-QC", "质检员", "QC", 2, "qc02", "QC"),
    # 财务 2
    ("方华", "DEP-FINANCE", "财务经理", "FIN", 1, "finance01", "FINANCE"),
    ("袁晓敏", "DEP-FINANCE", "财务专员", "FIN", 2, "finance02", "FINANCE"),
]


def _hash(pwd: str) -> str:
    """与 system.service._hash_password 保持一致的 sha256 哈希。"""
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


def clear_rbac() -> None:
    """清空旧账号/员工/组织与垃圾角色（只删重建范围内的数据）。"""
    placeholders = ",".join(":c%d" % i for i in range(len(SEED_ROLE_CODES)))
    sql = f"DELETE FROM sys_role WHERE role_code NOT IN ({placeholders})"
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        conn.execute(text("TRUNCATE TABLE sys_user_role"))
        conn.execute(text("TRUNCATE TABLE sys_user"))
        conn.execute(text("TRUNCATE TABLE sys_personnel"))
        conn.execute(text("TRUNCATE TABLE sys_organization"))
        # 垃圾角色（ROLE-xxx 等），sys_role_permission 由 FK CASCADE 联动清理
        conn.execute(text(sql), {f"c{i}": code for i, code in enumerate(SEED_ROLE_CODES)})
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def seed() -> None:
    clear_rbac()
    print("[1/3] 已清空旧组织/员工/账号及垃圾角色（保留 13 个正式身份）")

    db = SessionLocal()
    try:
        # 组织树
        org_ids: dict[str, int] = {}
        for code, name, parent_code, otype in ORGS:
            org = models.SysOrganization(
                org_code=code,
                org_name=name,
                parent_id=org_ids.get(parent_code) if parent_code else None,
                org_type=otype,
                status="ACTIVE",
            )
            db.add(org)
            db.flush()
            org_ids[code] = org.id

        # 员工档案 + 登录账号 + 角色绑定
        role_ids = {
            r.role_code: r.id
            for r in db.query(models.SysRole).filter(models.SysRole.role_code.in_(SEED_ROLE_CODES)).all()
        }
        person_ids: dict[str, int] = {}
        managers: dict[str, int] = {}
        for name, org_code, position, prefix, seq, username, role_code in STAFF:
            emp_no = f"{prefix}{seq:03d}"
            person = models.SysPersonnel(
                employee_no=emp_no,
                person_name=name,
                org_id=org_ids[org_code],
                position=position,
                hire_date=date.today(),
                status="ACTIVE",
            )
            db.add(person)
            db.flush()
            person_ids[username] = person.id
            if "经理" in position or "管理员" in position:
                managers.setdefault(org_code, person.id)

            user = models.SysUser(
                username=username,
                password_hash=_hash(DEFAULT_PASSWORD),
                display_name=name,
                personnel_id=person.id,
                status="ACTIVE",
            )
            db.add(user)
            db.flush()
            db.add(models.SysUserRole(user_id=user.id, role_id=role_ids[role_code]))
        print(f"[2/3] 已创建组织节点 {len(ORGS) - 1} 个（部门 8 / 智能加工中心 1 / 车间 9）、员工账号 {len(STAFF)} 个（管理员 3 / 销售 5 / 采购 5 / 仓储 5 / 计划 2 / 生产 10 / 质检 2 / 财务 2）")

        # 部门经理回填
        for org_code, person_id in managers.items():
            db.query(models.SysOrganization).filter(
                models.SysOrganization.org_code == org_code
            ).update({models.SysOrganization.manager_id: person_id})

        db.commit()
        print("[3/3] 部门负责人回填完成，种子执行结束（初始密码统一 123456）")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()