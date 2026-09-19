"""system 模块跨模块契约（**唯一对外入口**）。

规则（规格 §7 / §24）：

1. 其它模块**只允许** import 本文件，禁止 import system 的 `models` / `repository` / `service`。
2. 本文件只返回普通 `dict` / 标量，**不返回 ORM 对象**，避免会话与懒加载外泄。
3. 本文件签名一经确定即视为公共接口，修改需同步其它模块。

本文件刻意只依赖 system 自己的 ORM 模型，不依赖 `service.py`，
保证其它模块在任何时刻都能安全调用。
"""

from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.system import models
from app.shared.enums import MaterialType, RecordStatus

# 物料字典的字段口径，供其它模块稳定读取
MATERIAL_FIELDS = (
    "id",
    "material_code",
    "material_name",
    "material_type",
    "supply_type",
    "unit_code",
    "lead_time_days",
    "safety_stock",
    "status",
)


def _material_dict(row: models.SysMaterial) -> Dict[str, Any]:
    """把 ORM 物料转成只读字典。"""
    return {
        "id": row.id,
        "material_code": row.material_code,
        "material_name": row.material_name,
        "material_type": row.material_type,
        "supply_type": row.supply_type,
        "unit_code": row.unit_code,
        "lead_time_days": row.lead_time_days,
        "safety_stock": row.safety_stock,
        "status": row.status,
    }


# ==================== 物料 ====================


def get_material(db: Session, material_id: int) -> Optional[Dict[str, Any]]:
    """按 ID 取单个物料，不存在返回 None。"""
    row = db.get(models.SysMaterial, material_id)
    return _material_dict(row) if row else None


def get_materials(
    db: Session, material_ids: Iterable[int]
) -> Dict[int, Dict[str, Any]]:
    """批量取物料，返回 `{material_id: material_dict}`，缺失的 ID 不出现在结果中。"""
    ids = [int(i) for i in material_ids]
    if not ids:
        return {}
    rows = db.scalars(select(models.SysMaterial).where(models.SysMaterial.id.in_(ids)))
    return {row.id: _material_dict(row) for row in rows}


def find_material_by_code(db: Session, material_code: str) -> Optional[Dict[str, Any]]:
    """按业务编码取物料（导入与校验用）。"""
    row = db.scalar(
        select(models.SysMaterial).where(models.SysMaterial.material_code == material_code)
    )
    return _material_dict(row) if row else None


def search_materials(
    db: Session,
    *,
    material_type: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """按条件查询物料（Sales 的“销售产品查询”、Procurement 的“采购材料”均走此处）。"""
    stmt = select(models.SysMaterial).order_by(models.SysMaterial.material_code)
    if material_type:
        stmt = stmt.where(models.SysMaterial.material_type == material_type)
    if status:
        stmt = stmt.where(models.SysMaterial.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                models.SysMaterial.material_code.like(like),
                models.SysMaterial.material_name.like(like),
            )
        )
    return [_material_dict(row) for row in db.scalars(stmt.limit(limit))]


def get_finished_materials(db: Session, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    """取可销售的成品（FINISHED + ACTIVE），规格 §12.2。"""
    return search_materials(
        db,
        material_type=MaterialType.FINISHED.value,
        status=RecordStatus.ACTIVE.value,
        keyword=keyword,
    )


# ==================== 人员 / 组织 ====================


def get_personnel(db: Session, personnel_id: int) -> Optional[Dict[str, Any]]:
    """按 ID 取员工，返回 `{id, employee_no, person_name, org_id, status}`。"""
    row = db.get(models.SysPersonnel, personnel_id)
    if not row:
        return None
    return {
        "id": row.id,
        "employee_no": row.employee_no,
        "person_name": row.person_name,
        "org_id": row.org_id,
        "position": row.position,
        "status": row.status,
    }


def get_personnel_name(db: Session, personnel_id: Optional[int]) -> Optional[str]:
    """取员工姓名，用于列表展示（人员缺失时返回 None，不抛异常）。"""
    if not personnel_id:
        return None
    row = db.get(models.SysPersonnel, personnel_id)
    return row.person_name if row else None


def get_personnel_names(
    db: Session, personnel_ids: Sequence[int]
) -> Dict[int, str]:
    """批量取员工姓名，返回 `{personnel_id: person_name}`。"""
    ids = [int(i) for i in personnel_ids if i]
    if not ids:
        return {}
    rows = db.scalars(select(models.SysPersonnel).where(models.SysPersonnel.id.in_(ids)))
    return {row.id: row.person_name for row in rows}


# ==================== BOM ====================


def get_active_bom(
    db: Session, material_id: int, on_date: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """取某物料当前生效的 BOM 头（含明细）。

    生效判定：`status = ACTIVE` 且 `is_active = TRUE`，
    并在给定日期落在 `[effective_date, expiry_date]` 区间内（空值视为不限）。
    """
    stmt = (
        select(models.SysBom)
        .where(
            models.SysBom.material_id == material_id,
            models.SysBom.status == RecordStatus.ACTIVE.value,
            models.SysBom.is_active.is_(True),
        )
        .order_by(models.SysBom.id.desc())
    )
    for bom in db.scalars(stmt):
        if on_date is not None:
            if bom.effective_date and bom.effective_date > on_date:
                continue
            if bom.expiry_date and bom.expiry_date < on_date:
                continue
        return get_bom(db, bom.id)
    return None


def get_bom(db: Session, bom_id: int) -> Optional[Dict[str, Any]]:
    """取 BOM 头 + 明细（纯字典结构）。"""
    bom = db.get(models.SysBom, bom_id)
    if not bom:
        return None
    items = db.scalars(
        select(models.SysBomItem)
        .where(models.SysBomItem.bom_id == bom_id)
        .order_by(models.SysBomItem.sequence_no, models.SysBomItem.id)
    )
    return {
        "id": bom.id,
        "bom_code": bom.bom_code,
        "material_id": bom.material_id,
        "bom_version": bom.bom_version,
        "effective_date": bom.effective_date,
        "expiry_date": bom.expiry_date,
        "is_active": bom.is_active,
        "status": bom.status,
        "items": [
            {
                "id": it.id,
                "material_id": it.material_id,
                "quantity": it.quantity,
                "lead_time_offset": it.lead_time_offset,
                "scrap_rate": it.scrap_rate,
                "sequence_no": it.sequence_no,
            }
            for it in items
        ],
    }


def get_active_bom_children(
    db: Session, material_id: int, on_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """取某物料当前生效 BOM 的直接子件，供 MRP 逐层展开使用。

    返回 `[{child_material_id, quantity, lead_time_offset, scrap_rate, sequence_no}]`。
    未维护 BOM 时返回空列表（调用方据此判定为采购件/叶子）。
    """
    bom = get_active_bom(db, material_id, on_date)
    if not bom:
        return []
    return [
        {
            "child_material_id": it["material_id"],
            "quantity": it["quantity"],
            "lead_time_offset": it["lead_time_offset"],
            "scrap_rate": it["scrap_rate"],
            "sequence_no": it["sequence_no"],
        }
        for it in bom["items"]
    ]


def has_bom(db: Session, material_id: int) -> bool:
    """判断物料是否维护了生效 BOM（MRP 用 MAKE/BUY 兜底判定）。"""
    return get_active_bom(db, material_id) is not None


# ==================== 操作日志（规格 §24） ====================


def log_operation(
    db: Session,
    *,
    module: str,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    operator_id: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    """写入操作日志。

    **不提交事务**：由调用方在自己的事务里一并提交，
    保证“业务单据 + 日志”要么同时成功，要么同时回滚（规格 §35）。
    """
    db.add(
        models.SysOperationLog(
            module=module,
            action=action,
            target_type=target_type,
            target_id=target_id,
            operator_id=operator_id,
            detail=detail,
        )
    )