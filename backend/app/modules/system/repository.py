"""system 模块数据访问层。

只负责数据库读写与查询拼装，**不写业务规则**。
只允许被本模块的 `service.py` 调用；其它模块禁止直接 import 本文件。

说明：本模块是全系统基础数据 Owner，因此本层只访问自己的 `sys_*` 表，
不跨模块 JOIN；跨模块读取由其它模块调用 `contract.py` 完成。
"""

from typing import List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.system import models


# ==================== 通用 ====================


def count_all(db: Session, model) -> int:
    """统计某表总行数。"""
    return db.scalar(select(func.count()).select_from(model)) or 0


def count_where(db: Session, model, *criteria) -> int:
    """按条件统计行数。"""
    return db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0


def _paginate(db: Session, stmt, page: int, page_size: int):
    """对 select 语句做统一分页，返回 (items, total)。"""
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def next_no(db: Session, model, prefix: str) -> str:
    """生成业务编码：`<prefix><6位序号>`。仅用于演示级编码，真实场景应走独立序列。"""
    return f"{prefix}{count_all(db, model) + 1:06d}"


# ==================== 物料 ====================


def list_materials(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    material_type: Optional[str] = None,
    supply_type: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
):
    stmt = select(models.SysMaterial).order_by(models.SysMaterial.id.desc())
    if material_type:
        stmt = stmt.where(models.SysMaterial.material_type == material_type)
    if supply_type:
        stmt = stmt.where(models.SysMaterial.supply_type == supply_type)
    if status:
        stmt = stmt.where(models.SysMaterial.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            models.SysMaterial.material_code.like(like)
            | models.SysMaterial.material_name.like(like)
        )
    return _paginate(db, stmt, page, page_size)


def get_material(db: Session, material_id: int) -> Optional[models.SysMaterial]:
    return db.get(models.SysMaterial, material_id)


def get_material_by_code(db: Session, material_code: str) -> Optional[models.SysMaterial]:
    return db.scalar(
        select(models.SysMaterial).where(models.SysMaterial.material_code == material_code)
    )


def add_material(db: Session, material: models.SysMaterial) -> models.SysMaterial:
    db.add(material)
    db.flush()
    return material


# ==================== BOM ====================


def list_boms(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    stmt = select(models.SysBom).order_by(models.SysBom.id.desc())
    if material_id:
        stmt = stmt.where(models.SysBom.material_id == material_id)
    if status:
        stmt = stmt.where(models.SysBom.status == status)
    if is_active is not None:
        stmt = stmt.where(models.SysBom.is_active.is_(is_active))
    return _paginate(db, stmt, page, page_size)


def get_bom(db: Session, bom_id: int) -> Optional[models.SysBom]:
    return db.get(models.SysBom, bom_id)


def get_bom_by_material_version(
    db: Session, material_id: int, bom_version: str
) -> Optional[models.SysBom]:
    return db.scalar(
        select(models.SysBom).where(
            models.SysBom.material_id == material_id,
            models.SysBom.bom_version == bom_version,
        )
    )


def get_active_bom_for_material(
    db: Session, material_id: int
) -> Optional[models.SysBom]:
    """取某物料当前激活且启用的 BOM 头（用于多层展开）。"""
    stmt = (
        select(models.SysBom)
        .where(
            models.SysBom.material_id == material_id,
            models.SysBom.status == "ACTIVE",
            models.SysBom.is_active.is_(True),
        )
        .order_by(models.SysBom.id.desc())
    )
    return db.scalar(stmt)


def list_active_boms_of_material(db: Session, material_id: int) -> List[models.SysBom]:
    return list(
        db.scalars(select(models.SysBom).where(models.SysBom.material_id == material_id))
    )


def add_bom(db: Session, bom: models.SysBom) -> models.SysBom:
    db.add(bom)
    db.flush()
    return bom


def delete_bom(db: Session, bom: models.SysBom) -> None:
    db.delete(bom)


def deactivate_other_boms(db: Session, material_id: int, keep_bom_id: int) -> None:
    """把同一物料的其它 BOM 版本置为非激活。"""
    for bom in list_active_boms_of_material(db, material_id):
        if bom.id != keep_bom_id and bom.is_active:
            bom.is_active = False


def list_bom_items(db: Session, bom_id: int) -> List[models.SysBomItem]:
    return list(
        db.scalars(
            select(models.SysBomItem)
            .where(models.SysBomItem.bom_id == bom_id)
            .order_by(models.SysBomItem.sequence_no, models.SysBomItem.id)
        )
    )


def get_bom_item(db: Session, item_id: int) -> Optional[models.SysBomItem]:
    return db.get(models.SysBomItem, item_id)


def get_bom_item_by_material(
    db: Session, bom_id: int, material_id: int
) -> Optional[models.SysBomItem]:
    return db.scalar(
        select(models.SysBomItem).where(
            models.SysBomItem.bom_id == bom_id,
            models.SysBomItem.material_id == material_id,
        )
    )


def add_bom_item(db: Session, item: models.SysBomItem) -> models.SysBomItem:
    db.add(item)
    db.flush()
    return item


def delete_bom_item(db: Session, item: models.SysBomItem) -> None:
    db.delete(item)


# ==================== 工艺路线 ====================


def list_routings(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
):
    stmt = select(models.SysRouting).order_by(models.SysRouting.id.desc())
    if material_id:
        stmt = stmt.where(models.SysRouting.material_id == material_id)
    if status:
        stmt = stmt.where(models.SysRouting.status == status)
    return _paginate(db, stmt, page, page_size)


def get_routing(db: Session, routing_id: int) -> Optional[models.SysRouting]:
    return db.get(models.SysRouting, routing_id)


def get_routing_by_material_version(
    db: Session, material_id: int, routing_version: str
) -> Optional[models.SysRouting]:
    return db.scalar(
        select(models.SysRouting).where(
            models.SysRouting.material_id == material_id,
            models.SysRouting.routing_version == routing_version,
        )
    )


def add_routing(db: Session, routing: models.SysRouting) -> models.SysRouting:
    db.add(routing)
    db.flush()
    return routing


def get_routing_operation(
    db: Session, operation_id: int
) -> Optional[models.SysRoutingOperation]:
    return db.get(models.SysRoutingOperation, operation_id)


def get_routing_operation_by_seq(
    db: Session, routing_id: int, sequence_no: int
) -> Optional[models.SysRoutingOperation]:
    return db.scalar(
        select(models.SysRoutingOperation).where(
            models.SysRoutingOperation.routing_id == routing_id,
            models.SysRoutingOperation.sequence_no == sequence_no,
        )
    )


def add_routing_operation(
    db: Session, operation: models.SysRoutingOperation
) -> models.SysRoutingOperation:
    db.add(operation)
    db.flush()
    return operation


def delete_routing_operation(
    db: Session, operation: models.SysRoutingOperation
) -> None:
    db.delete(operation)


# ==================== 组织 ====================


def list_organizations(db: Session) -> List[models.SysOrganization]:
    return list(
        db.scalars(
            select(models.SysOrganization).order_by(
                models.SysOrganization.id
            )
        )
    )


def get_organization(db: Session, org_id: int) -> Optional[models.SysOrganization]:
    return db.get(models.SysOrganization, org_id)


def get_organization_by_code(
    db: Session, org_code: str
) -> Optional[models.SysOrganization]:
    return db.scalar(
        select(models.SysOrganization).where(models.SysOrganization.org_code == org_code)
    )


def list_organization_children(db: Session, parent_id: int) -> List[models.SysOrganization]:
    return list(
        db.scalars(
            select(models.SysOrganization).where(
                models.SysOrganization.parent_id == parent_id
            )
        )
    )


def add_organization(db: Session, org: models.SysOrganization) -> models.SysOrganization:
    db.add(org)
    db.flush()
    return org


# ==================== 人员 ====================


def list_personnel(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    org_id: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
):
    stmt = select(models.SysPersonnel).order_by(models.SysPersonnel.id.desc())
    if org_id:
        stmt = stmt.where(models.SysPersonnel.org_id == org_id)
    if status:
        stmt = stmt.where(models.SysPersonnel.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            models.SysPersonnel.employee_no.like(like)
            | models.SysPersonnel.person_name.like(like)
        )
    return _paginate(db, stmt, page, page_size)


def get_personnel(db: Session, personnel_id: int) -> Optional[models.SysPersonnel]:
    return db.get(models.SysPersonnel, personnel_id)


def get_personnel_by_no(db: Session, employee_no: str) -> Optional[models.SysPersonnel]:
    return db.scalar(
        select(models.SysPersonnel).where(models.SysPersonnel.employee_no == employee_no)
    )


def next_employee_no(db: Session) -> str:
    """自动生成工号：EMP + 表内最大 id+1 补 5 位。

    基于 id 递增（删除工号后 id 不回用），并循环探测唯一键避免与手工工号撞号。
    """
    max_id = db.scalar(select(func.max(models.SysPersonnel.id))) or 0
    for offset in range(1, 101):
        candidate = f"EMP{int(max_id) + offset:05d}"
        if not get_personnel_by_no(db, candidate):
            return candidate
    raise RuntimeError("无法生成唯一员工工号")


def add_personnel(db: Session, personnel: models.SysPersonnel) -> models.SysPersonnel:
    db.add(personnel)
    db.flush()
    return personnel


# ==================== 字典 ====================


def list_dictionaries(db: Session) -> List[models.SysDictionary]:
    return list(
        db.scalars(select(models.SysDictionary).order_by(models.SysDictionary.id))
    )


def get_dictionary(db: Session, dict_id: int) -> Optional[models.SysDictionary]:
    return db.get(models.SysDictionary, dict_id)


def get_dictionary_by_code(db: Session, dict_code: str) -> Optional[models.SysDictionary]:
    return db.scalar(
        select(models.SysDictionary).where(models.SysDictionary.dict_code == dict_code)
    )


def add_dictionary(db: Session, dictionary: models.SysDictionary) -> models.SysDictionary:
    db.add(dictionary)
    db.flush()
    return dictionary


def get_dictionary_item(
    db: Session, item_id: int
) -> Optional[models.SysDictionaryItem]:
    return db.get(models.SysDictionaryItem, item_id)


def get_dictionary_item_by_code(
    db: Session, dict_id: int, item_code: str
) -> Optional[models.SysDictionaryItem]:
    return db.scalar(
        select(models.SysDictionaryItem).where(
            models.SysDictionaryItem.dict_id == dict_id,
            models.SysDictionaryItem.item_code == item_code,
        )
    )


def add_dictionary_item(
    db: Session, item: models.SysDictionaryItem
) -> models.SysDictionaryItem:
    db.add(item)
    db.flush()
    return item


def delete_dictionary_item(db: Session, item: models.SysDictionaryItem) -> None:
    db.delete(item)


# ==================== RBAC ====================


def list_users(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
):
    stmt = select(models.SysUser).order_by(models.SysUser.id.desc())
    if status:
        stmt = stmt.where(models.SysUser.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            models.SysUser.username.like(like)
            | models.SysUser.display_name.like(like)
        )
    return _paginate(db, stmt, page, page_size)


def get_user(db: Session, user_id: int) -> Optional[models.SysUser]:
    return db.get(models.SysUser, user_id)


def get_user_by_username(db: Session, username: str) -> Optional[models.SysUser]:
    return db.scalar(select(models.SysUser).where(models.SysUser.username == username))


def get_user_by_personnel(
    db: Session, personnel_id: int
) -> Optional[models.SysUser]:
    return db.scalar(
        select(models.SysUser).where(models.SysUser.personnel_id == personnel_id)
    )


def add_user(db: Session, user: models.SysUser) -> models.SysUser:
    db.add(user)
    db.flush()
    return user


def replace_user_roles(db: Session, user_id: int, role_ids: Sequence[int]) -> None:
    """全量替换用户角色集合。"""
    for link in db.scalars(
        select(models.SysUserRole).where(models.SysUserRole.user_id == user_id)
    ):
        db.delete(link)
    db.flush()
    for role_id in role_ids:
        db.add(models.SysUserRole(user_id=user_id, role_id=role_id))


def list_roles(
    db: Session, status: Optional[str] = None
) -> List[models.SysRole]:
    stmt = select(models.SysRole).order_by(models.SysRole.id)
    if status:
        stmt = stmt.where(models.SysRole.status == status)
    return list(db.scalars(stmt))


def get_role(db: Session, role_id: int) -> Optional[models.SysRole]:
    return db.get(models.SysRole, role_id)


def get_role_by_code(db: Session, role_code: str) -> Optional[models.SysRole]:
    return db.scalar(select(models.SysRole).where(models.SysRole.role_code == role_code))


def list_roles_by_codes(db: Session, role_codes: Sequence[str]) -> List[models.SysRole]:
    """按编码集合取角色（保持传入顺序去重，不存在的不报错）。"""
    rows = {
        role.role_code: role
        for role in db.scalars(
            select(models.SysRole).where(models.SysRole.role_code.in_(list(role_codes)))
        )
    }
    return [rows[code] for code in role_codes if code in rows]


def add_role(db: Session, role: models.SysRole) -> models.SysRole:
    db.add(role)
    db.flush()
    return role


def replace_role_permissions(
    db: Session, role_id: int, permission_ids: Sequence[int]
) -> None:
    """全量替换角色权限集合。"""
    for link in db.scalars(
        select(models.SysRolePermission).where(
            models.SysRolePermission.role_id == role_id
        )
    ):
        db.delete(link)
    db.flush()
    for permission_id in permission_ids:
        db.add(models.SysRolePermission(role_id=role_id, permission_id=permission_id))


def list_permissions(
    db: Session, status: Optional[str] = None
) -> List[models.SysPermission]:
    stmt = select(models.SysPermission).order_by(
        models.SysPermission.sort_no, models.SysPermission.id
    )
    if status:
        stmt = stmt.where(models.SysPermission.status == status)
    return list(db.scalars(stmt))


def get_permission(db: Session, permission_id: int) -> Optional[models.SysPermission]:
    return db.get(models.SysPermission, permission_id)


def get_permission_by_code(
    db: Session, perm_code: str
) -> Optional[models.SysPermission]:
    return db.scalar(
        select(models.SysPermission).where(models.SysPermission.perm_code == perm_code)
    )


def list_role_permissions(
    db: Session, role_ids: Sequence[int]
) -> List[models.SysPermission]:
    """取给定角色集合下的全部权限点（去重）。"""
    ids = [int(i) for i in role_ids]
    if not ids:
        return []
    stmt = (
        select(models.SysPermission)
        .join(
            models.SysRolePermission,
            models.SysRolePermission.permission_id == models.SysPermission.id,
        )
        .where(models.SysRolePermission.role_id.in_(ids))
        .distinct()
        .order_by(models.SysPermission.sort_no, models.SysPermission.id)
    )
    return list(db.scalars(stmt))


def add_permission(db: Session, permission: models.SysPermission) -> models.SysPermission:
    db.add(permission)
    db.flush()
    return permission


# ==================== 操作日志 ====================


def list_operation_logs(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    module: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
):
    stmt = select(models.SysOperationLog).order_by(models.SysOperationLog.id.desc())
    if module:
        stmt = stmt.where(models.SysOperationLog.module == module)
    if action:
        stmt = stmt.where(models.SysOperationLog.action == action)
    if target_type:
        stmt = stmt.where(models.SysOperationLog.target_type == target_type)
    if target_id:
        stmt = stmt.where(models.SysOperationLog.target_id == target_id)
    return _paginate(db, stmt, page, page_size)


# ==================== 事务辅助 ====================


def refresh(db: Session, obj) -> None:
    """刷新 ORM 对象（含 selectin 关系）。"""
    db.refresh(obj)