"""system 模块业务逻辑层。

职责与约定：

- 只有本模块的 `router.py` 可以调用本模块 service。
- 业务规则 / 校验写在 service，SQL 写在 `repository.py`。
- **不调用 `db.commit()`**：由 router 在 service 成功后统一提交，
  保证“业务数据 + 操作日志”处于同一事务（规格 §35）。
- 其它模块**禁止直接 import 本文件**，跨模块只能走 `contract.py`。

错误码区段：`1000~1999`。
"""

import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.system import models, repository as repo
from app.modules.system.contract import log_operation
from app.modules.system.schemas import (
    BomConfirmOut,
    BomCreate,
    BomImportSummaryOut,
    BomItemCreate,
    BomItemPreviewOut,
    BomItemUpdate,
    BomPreviewOut,
    BomTreeNode,
    BomUpdate,
    DictionaryCreate,
    DictionaryItemCreate,
    DictionaryItemUpdate,
    DictionaryUpdate,
    ImportErrorOut,
    MaterialConfirmOut,
    MaterialCreate,
    MaterialImportSummaryOut,
    MaterialPreviewItemOut,
    MaterialPreviewOut,
    MaterialUpdate,
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationTreeNode,
    PermissionCreate,
    PermissionTreeNode,
    PermissionUpdate,
    PersonnelCreate,
    PersonnelUpdate,
    RoutingCreate,
    RoutingOperationCreate,
    RoutingOperationUpdate,
    RoutingUpdate,
    RoleCreate,
    RoleUpdate,
    UserCreate,
    UserUpdate,
)
from app.shared.enums import MaterialType, RecordStatus, SupplyType

# ==================== 错误码 ====================

CODE_MATERIAL_CODE_EXISTS = 1001
CODE_BOM_VERSION_EXISTS = 1002
CODE_BOM_CYCLE = 1003
CODE_EMPLOYEE_NO_EXISTS = 1004
CODE_NOT_FOUND = 1005
CODE_INVALID_PARAM = 1006
CODE_CODE_EXISTS = 1007
CODE_INVALID_STATUS = 1008
CODE_DATA_REFERENCED = 1009
CODE_LOGIN_FAILED = 1010
CODE_UNSUPPORTED_SOURCE = 1011
CODE_MATERIAL_MISSING_FOR_BOM = 1012

#: 允许的状态集合（规格 §20：不物理删除，只置 INACTIVE）
_ALLOWED_STATUS = {RecordStatus.ACTIVE.value, RecordStatus.INACTIVE.value}

#: 物料类型 / 供应类型合法值
_MATERIAL_TYPES = {item.value for item in MaterialType}
_SUPPLY_TYPES = {item.value for item in SupplyType}

#: 组织类型合法值
_ORG_TYPES = {"COMPANY", "FACTORY", "DEPARTMENT", "WORKSHOP", "WAREHOUSE"}

#: 权限类型合法值
_PERM_TYPES = {"MENU", "PAGE", "ACTION"}

#: 多层 BOM 展开默认最大层数
_DEFAULT_MAX_LEVEL = 10


# ==================== 通用辅助 ====================


def _validate_status(status: str) -> str:
    """校验状态是否为 ACTIVE / INACTIVE。"""
    if status not in _ALLOWED_STATUS:
        raise BusinessException(CODE_INVALID_STATUS, f"状态不合法：{status}")
    return status


def _hash_password(password: str) -> str:
    """密码哈希（简化版：sha256，详见模块说明）。"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _require(condition: bool, code: int, message: str) -> None:
    """通用断言，不满足即抛业务异常。"""
    if not condition:
        raise BusinessException(code, message)


# ==================== 物料 ====================


def list_materials(
    db: Session,
    *,
    page: int,
    page_size: int,
    material_type: Optional[str] = None,
    supply_type: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """分页查询物料。"""
    return repo.list_materials(
        db,
        page=page,
        page_size=page_size,
        material_type=material_type,
        supply_type=supply_type,
        status=status,
        keyword=keyword,
    )


def get_material(db: Session, material_id: int) -> models.SysMaterial:
    """按 ID 取物料，不存在抛 1005。"""
    material = repo.get_material(db, material_id)
    if not material:
        raise BusinessException(CODE_NOT_FOUND, "物料不存在")
    return material


def _validate_material_fields(
    *,
    material_type: str,
    supply_type: str,
    lead_time_days: int,
    safety_stock: Decimal,
) -> None:
    """校验物料类型 / 供应类型 / 提前期 / 安全库存。"""
    _require(material_type in _MATERIAL_TYPES, CODE_INVALID_PARAM, f"物料类型不合法：{material_type}")
    _require(supply_type in _SUPPLY_TYPES, CODE_INVALID_PARAM, f"供应类型不合法：{supply_type}")
    _require(lead_time_days >= 0, CODE_INVALID_PARAM, "提前期不能为负数")
    _require(Decimal(safety_stock) >= 0, CODE_INVALID_PARAM, "安全库存不能为负数")


def create_material(db: Session, payload: MaterialCreate) -> models.SysMaterial:
    """新增物料：编码唯一。"""
    if repo.get_material_by_code(db, payload.material_code):
        raise BusinessException(CODE_MATERIAL_CODE_EXISTS, "物料编码已存在")
    _validate_material_fields(
        material_type=payload.material_type,
        supply_type=payload.supply_type,
        lead_time_days=payload.lead_time_days,
        safety_stock=payload.safety_stock,
    )
    _validate_status(payload.status)
    material = models.SysMaterial(
        material_code=payload.material_code,
        material_name=payload.material_name,
        material_type=payload.material_type,
        supply_type=payload.supply_type,
        unit_code=payload.unit_code,
        specification=payload.specification,
        material_group=payload.material_group,
        lead_time_days=payload.lead_time_days,
        safety_stock=payload.safety_stock,
        standard_cost=payload.standard_cost,
        status=payload.status,
        remark=payload.remark,
    )
    repo.add_material(db, material)
    log_operation(
        db,
        module="system",
        action="CREATE",
        target_type="sys_material",
        target_id=material.id,
        detail=f"新增物料 {material.material_code}",
    )
    return material


def update_material(
    db: Session, material_id: int, payload: MaterialUpdate
) -> models.SysMaterial:
    """修改物料（编码不可改）。"""
    material = get_material(db, material_id)
    data = payload.model_dump(exclude_unset=True)

    material_type = data.get("material_type", material.material_type)
    supply_type = data.get("supply_type", material.supply_type)
    lead_time_days = data.get("lead_time_days", material.lead_time_days)
    safety_stock = data.get("safety_stock", material.safety_stock)
    _validate_material_fields(
        material_type=material_type,
        supply_type=supply_type,
        lead_time_days=lead_time_days,
        safety_stock=safety_stock,
    )
    if "status" in data:
        _validate_status(data["status"])

    for field, value in data.items():
        setattr(material, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE",
        target_type="sys_material",
        target_id=material.id,
        detail=f"修改物料 {material.material_code}",
    )
    return material


def change_material_status(
    db: Session, material_id: int, status: str
) -> models.SysMaterial:
    """物料状态流转（停用只置 INACTIVE，不物理删除）。"""
    _validate_status(status)
    material = get_material(db, material_id)
    material.status = status
    log_operation(
        db,
        module="system",
        action="STATUS",
        target_type="sys_material",
        target_id=material.id,
        detail=f"物料 {material.material_code} 状态改为 {status}",
    )
    return material


# ==================== BOM ====================


def list_boms(
    db: Session,
    *,
    page: int,
    page_size: int,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """分页查询 BOM 头。"""
    return repo.list_boms(
        db,
        page=page,
        page_size=page_size,
        material_id=material_id,
        status=status,
        is_active=is_active,
    )


def get_bom(db: Session, bom_id: int) -> models.SysBom:
    """按 ID 取 BOM（含子项），不存在抛 1005。"""
    bom = repo.get_bom(db, bom_id)
    if not bom:
        raise BusinessException(CODE_NOT_FOUND, "BOM 不存在")
    return bom


def _descendants_contain(
    db: Session, start_material_id: int, target_material_id: int
) -> bool:
    """判断从 `start_material_id` 出发的多层 BOM 子树是否包含 `target_material_id`。

    沿“当前激活 BOM”逐层向下遍历，用于新增 BOM 子项时的循环引用校验。
    """
    visited: set = set()
    stack = [start_material_id]
    while stack:
        current = stack.pop()
        if current == target_material_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        bom = repo.get_active_bom_for_material(db, current)
        if not bom:
            continue
        for item in repo.list_bom_items(db, bom.id):
            stack.append(item.material_id)
    return False


def _validate_bom_item(
    db: Session, parent_material_id: int, item: BomItemCreate
) -> None:
    """校验 BOM 子项：数量 / 损耗率 / 提前期 / 是否循环引用。"""
    if item.material_id == parent_material_id:
        raise BusinessException(CODE_INVALID_PARAM, "子件不能与母件相同")
    if not repo.get_material(db, item.material_id):
        raise BusinessException(CODE_NOT_FOUND, "子件物料不存在")
    _require(Decimal(item.quantity) > 0, CODE_INVALID_PARAM, "用量必须大于 0")
    _require(
        Decimal(item.scrap_rate) >= 0 and Decimal(item.scrap_rate) < 1,
        CODE_INVALID_PARAM,
        "损耗率必须位于 [0,1) 区间",
    )
    _require(item.lead_time_offset >= 0, CODE_INVALID_PARAM, "提前期偏置不能为负数")
    if _descendants_contain(db, item.material_id, parent_material_id):
        raise BusinessException(CODE_BOM_CYCLE, "BOM 存在循环引用")


def create_bom(db: Session, payload: BomCreate) -> models.SysBom:
    """新增 BOM 头（可含子项）：`(material_id, bom_version)` 唯一。"""
    if not repo.get_material(db, payload.material_id):
        raise BusinessException(CODE_NOT_FOUND, "母件物料不存在")
    if repo.get_bom_by_material_version(db, payload.material_id, payload.bom_version):
        raise BusinessException(CODE_BOM_VERSION_EXISTS, "BOM 版本已存在")
    _validate_status(payload.status)

    bom = models.SysBom(
        bom_code=payload.bom_code or repo.next_no(db, models.SysBom, "BOM"),
        material_id=payload.material_id,
        bom_version=payload.bom_version,
        effective_date=payload.effective_date,
        expiry_date=payload.expiry_date,
        is_active=payload.is_active,
        status=payload.status,
        remark=payload.remark,
    )
    repo.add_bom(db, bom)

    seen: set = set()
    for item in payload.items:
        if item.material_id in seen:
            raise BusinessException(CODE_INVALID_PARAM, "同一 BOM 内子件重复")
        seen.add(item.material_id)
        _validate_bom_item(db, bom.material_id, item)
        repo.add_bom_item(
            db,
            models.SysBomItem(
                bom_id=bom.id,
                material_id=item.material_id,
                quantity=item.quantity,
                lead_time_offset=item.lead_time_offset,
                scrap_rate=item.scrap_rate,
                sequence_no=item.sequence_no,
                remark=item.remark,
            ),
        )

    log_operation(
        db,
        module="system",
        action="CREATE",
        target_type="sys_bom",
        target_id=bom.id,
        detail=f"新增 BOM {bom.bom_code}（母件 {bom.material_id}，版本 {bom.bom_version}）",
    )
    return bom


def update_bom(db: Session, bom_id: int, payload: BomUpdate) -> models.SysBom:
    """修改 BOM 头。"""
    bom = get_bom(db, bom_id)
    data = payload.model_dump(exclude_unset=True)
    if "bom_version" in data and data["bom_version"] != bom.bom_version:
        if repo.get_bom_by_material_version(db, bom.material_id, data["bom_version"]):
            raise BusinessException(CODE_BOM_VERSION_EXISTS, "BOM 版本已存在")
    if "status" in data:
        _validate_status(data["status"])
    for field, value in data.items():
        setattr(bom, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE",
        target_type="sys_bom",
        target_id=bom.id,
        detail=f"修改 BOM {bom.bom_code}",
    )
    return bom


def delete_bom(db: Session, bom_id: int) -> None:
    """删除 BOM 头（子项级联删除）。"""
    bom = get_bom(db, bom_id)
    log_operation(
        db,
        module="system",
        action="DELETE",
        target_type="sys_bom",
        target_id=bom.id,
        detail=f"删除 BOM {bom.bom_code}",
    )
    repo.delete_bom(db, bom)


def activate_bom(db: Session, bom_id: int) -> models.SysBom:
    """激活指定 BOM 版本，同物料其它版本全部置为非激活。"""
    bom = get_bom(db, bom_id)
    if bom.status != RecordStatus.ACTIVE.value:
        raise BusinessException(CODE_INVALID_STATUS, "仅启用状态的 BOM 可被激活")
    repo.deactivate_other_boms(db, bom.material_id, bom.id)
    bom.is_active = True
    log_operation(
        db,
        module="system",
        action="ACTIVATE",
        target_type="sys_bom",
        target_id=bom.id,
        detail=f"激活 BOM {bom.bom_code}（版本 {bom.bom_version}）",
    )
    return bom


def change_bom_status(db: Session, bom_id: int, status: str) -> models.SysBom:
    """BOM 状态流转。"""
    _validate_status(status)
    bom = get_bom(db, bom_id)
    bom.status = status
    if status == RecordStatus.INACTIVE.value:
        bom.is_active = False
    log_operation(
        db,
        module="system",
        action="STATUS",
        target_type="sys_bom",
        target_id=bom.id,
        detail=f"BOM {bom.bom_code} 状态改为 {status}",
    )
    return bom


def add_bom_item(db: Session, bom_id: int, payload: BomItemCreate) -> models.SysBomItem:
    """新增 BOM 子项（含循环引用校验）。"""
    bom = get_bom(db, bom_id)
    if repo.get_bom_item_by_material(db, bom.id, payload.material_id):
        raise BusinessException(CODE_INVALID_PARAM, "该子件已存在于当前 BOM")
    _validate_bom_item(db, bom.material_id, payload)
    item = models.SysBomItem(
        bom_id=bom.id,
        material_id=payload.material_id,
        quantity=payload.quantity,
        lead_time_offset=payload.lead_time_offset,
        scrap_rate=payload.scrap_rate,
        sequence_no=payload.sequence_no,
        remark=payload.remark,
    )
    repo.add_bom_item(db, item)
    log_operation(
        db,
        module="system",
        action="ADD_ITEM",
        target_type="sys_bom_item",
        target_id=item.id,
        detail=f"BOM {bom.bom_code} 新增子件 {payload.material_id}",
    )
    return item


def update_bom_item(
    db: Session, item_id: int, payload: BomItemUpdate
) -> models.SysBomItem:
    """修改 BOM 子项。"""
    item = repo.get_bom_item(db, item_id)
    if not item:
        raise BusinessException(CODE_NOT_FOUND, "BOM 子项不存在")
    parent_material_id = item.bom.material_id
    data = payload.model_dump(exclude_unset=True)

    # 合并后统一校验
    merged = BomItemCreate(
        material_id=data.get("material_id", item.material_id),
        quantity=data.get("quantity", item.quantity),
        lead_time_offset=data.get("lead_time_offset", item.lead_time_offset),
        scrap_rate=data.get("scrap_rate", item.scrap_rate),
        sequence_no=data.get("sequence_no", item.sequence_no),
        remark=data.get("remark", item.remark),
    )
    if merged.material_id != item.material_id:
        if repo.get_bom_item_by_material(db, item.bom_id, merged.material_id):
            raise BusinessException(CODE_INVALID_PARAM, "该子件已存在于当前 BOM")
    _validate_bom_item(db, parent_material_id, merged)

    for field, value in data.items():
        setattr(item, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE_ITEM",
        target_type="sys_bom_item",
        target_id=item.id,
        detail=f"修改 BOM 子项 {item.id}",
    )
    return item


def delete_bom_item(db: Session, item_id: int) -> None:
    """删除 BOM 子项。"""
    item = repo.get_bom_item(db, item_id)
    if not item:
        raise BusinessException(CODE_NOT_FOUND, "BOM 子项不存在")
    log_operation(
        db,
        module="system",
        action="DELETE_ITEM",
        target_type="sys_bom_item",
        target_id=item.id,
        detail=f"删除 BOM 子项 {item.id}",
    )
    repo.delete_bom_item(db, item)


def get_bom_tree(
    db: Session, material_id: int, max_level: int = _DEFAULT_MAX_LEVEL
) -> BomTreeNode:
    """多层 BOM 展开：对 `sys_bom_item` 做真实递归，返回嵌套树。

    每一层使用该物料“当前激活 + 启用”的 BOM；`max_level` 控制最大展开层数，
    并用访问集合防御数据层面的环，避免无限递归。
    """
    root_material = get_material(db, material_id)
    _require(max_level >= 1, CODE_INVALID_PARAM, "max_level 必须大于等于 1")

    def build(
        current_material_id: int,
        quantity: Decimal,
        lead_time_offset: int,
        scrap_rate: Decimal,
        level: int,
        visited: frozenset,
    ) -> BomTreeNode:
        material = repo.get_material(db, current_material_id)
        node = BomTreeNode(
            material_id=current_material_id,
            material_code=material.material_code if material else None,
            material_name=material.material_name if material else None,
            quantity=quantity,
            lead_time_offset=lead_time_offset,
            scrap_rate=scrap_rate,
            level=level,
            children=[],
        )
        if level >= max_level or current_material_id in visited:
            return node
        bom = repo.get_active_bom_for_material(db, current_material_id)
        if not bom:
            return node
        next_visited = visited | {current_material_id}
        for item in repo.list_bom_items(db, bom.id):
            node.children.append(
                build(
                    item.material_id,
                    item.quantity,
                    item.lead_time_offset,
                    item.scrap_rate,
                    level + 1,
                    next_visited,
                )
            )
        return node

    return build(
        root_material.id,
        Decimal("1"),
        0,
        Decimal("0"),
        1,
        frozenset(),
    )


# ==================== 工艺路线 ====================


def list_routings(
    db: Session,
    *,
    page: int,
    page_size: int,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
):
    """分页查询工艺路线。"""
    return repo.list_routings(
        db, page=page, page_size=page_size, material_id=material_id, status=status
    )


def get_routing(db: Session, routing_id: int) -> models.SysRouting:
    """按 ID 取工艺路线（含工序），不存在抛 1005。"""
    routing = repo.get_routing(db, routing_id)
    if not routing:
        raise BusinessException(CODE_NOT_FOUND, "工艺路线不存在")
    return routing


def _validate_operation(payload: RoutingOperationCreate) -> None:
    """校验工序工时非负。"""
    _require(payload.sequence_no >= 0, CODE_INVALID_PARAM, "工序顺序号不能为负数")
    _require(Decimal(payload.setup_time) >= 0, CODE_INVALID_PARAM, "准备工时不能为负数")
    _require(Decimal(payload.run_time) >= 0, CODE_INVALID_PARAM, "加工工时不能为负数")


def create_routing(db: Session, payload: RoutingCreate) -> models.SysRouting:
    """新增工艺路线（可含工序）：`(material_id, routing_version)` 唯一。"""
    if not repo.get_material(db, payload.material_id):
        raise BusinessException(CODE_NOT_FOUND, "物料不存在")
    if repo.get_routing_by_material_version(db, payload.material_id, payload.routing_version):
        raise BusinessException(CODE_CODE_EXISTS, "工艺版本已存在")
    _validate_status(payload.status)

    routing = models.SysRouting(
        routing_code=payload.routing_code or repo.next_no(db, models.SysRouting, "RT"),
        material_id=payload.material_id,
        routing_version=payload.routing_version,
        status=payload.status,
        remark=payload.remark,
    )
    repo.add_routing(db, routing)

    seen: set = set()
    for op in payload.operations:
        if op.sequence_no in seen:
            raise BusinessException(CODE_INVALID_PARAM, "工序顺序号重复")
        seen.add(op.sequence_no)
        _validate_operation(op)
        repo.add_routing_operation(
            db,
            models.SysRoutingOperation(
                routing_id=routing.id,
                sequence_no=op.sequence_no,
                operation_code=op.operation_code,
                operation_name=op.operation_name,
                work_center=op.work_center,
                setup_time=op.setup_time,
                run_time=op.run_time,
                remark=op.remark,
            ),
        )

    log_operation(
        db,
        module="system",
        action="CREATE",
        target_type="sys_routing",
        target_id=routing.id,
        detail=f"新增工艺路线 {routing.routing_code}（物料 {routing.material_id}）",
    )
    return routing


def update_routing(
    db: Session, routing_id: int, payload: RoutingUpdate
) -> models.SysRouting:
    """修改工艺路线头。"""
    routing = get_routing(db, routing_id)
    data = payload.model_dump(exclude_unset=True)
    if "routing_version" in data and data["routing_version"] != routing.routing_version:
        if repo.get_routing_by_material_version(
            db, routing.material_id, data["routing_version"]
        ):
            raise BusinessException(CODE_CODE_EXISTS, "工艺版本已存在")
    if "status" in data:
        _validate_status(data["status"])
    for field, value in data.items():
        setattr(routing, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE",
        target_type="sys_routing",
        target_id=routing.id,
        detail=f"修改工艺路线 {routing.routing_code}",
    )
    return routing


def change_routing_status(
    db: Session, routing_id: int, status: str
) -> models.SysRouting:
    """工艺路线状态流转。"""
    _validate_status(status)
    routing = get_routing(db, routing_id)
    routing.status = status
    log_operation(
        db,
        module="system",
        action="STATUS",
        target_type="sys_routing",
        target_id=routing.id,
        detail=f"工艺路线 {routing.routing_code} 状态改为 {status}",
    )
    return routing


def add_routing_operation(
    db: Session, routing_id: int, payload: RoutingOperationCreate
) -> models.SysRoutingOperation:
    """新增工序行：`(routing_id, sequence_no)` 唯一。"""
    routing = get_routing(db, routing_id)
    if repo.get_routing_operation_by_seq(db, routing.id, payload.sequence_no):
        raise BusinessException(CODE_INVALID_PARAM, "工序顺序号已存在")
    _validate_operation(payload)
    operation = models.SysRoutingOperation(
        routing_id=routing.id,
        sequence_no=payload.sequence_no,
        operation_code=payload.operation_code,
        operation_name=payload.operation_name,
        work_center=payload.work_center,
        setup_time=payload.setup_time,
        run_time=payload.run_time,
        remark=payload.remark,
    )
    repo.add_routing_operation(db, operation)
    log_operation(
        db,
        module="system",
        action="ADD_OPERATION",
        target_type="sys_routing_operation",
        target_id=operation.id,
        detail=f"工艺路线 {routing.routing_code} 新增工序 {payload.operation_code}",
    )
    return operation


def update_routing_operation(
    db: Session, operation_id: int, payload: RoutingOperationUpdate
) -> models.SysRoutingOperation:
    """修改工序行。"""
    operation = repo.get_routing_operation(db, operation_id)
    if not operation:
        raise BusinessException(CODE_NOT_FOUND, "工序不存在")
    data = payload.model_dump(exclude_unset=True)
    if "sequence_no" in data and data["sequence_no"] != operation.sequence_no:
        if repo.get_routing_operation_by_seq(
            db, operation.routing_id, data["sequence_no"]
        ):
            raise BusinessException(CODE_INVALID_PARAM, "工序顺序号已存在")
    if "setup_time" in data:
        _require(Decimal(data["setup_time"]) >= 0, CODE_INVALID_PARAM, "准备工时不能为负数")
    if "run_time" in data:
        _require(Decimal(data["run_time"]) >= 0, CODE_INVALID_PARAM, "加工工时不能为负数")
    for field, value in data.items():
        setattr(operation, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE_OPERATION",
        target_type="sys_routing_operation",
        target_id=operation.id,
        detail=f"修改工序 {operation.id}",
    )
    return operation


def delete_routing_operation(db: Session, operation_id: int) -> None:
    """删除工序行。"""
    operation = repo.get_routing_operation(db, operation_id)
    if not operation:
        raise BusinessException(CODE_NOT_FOUND, "工序不存在")
    log_operation(
        db,
        module="system",
        action="DELETE_OPERATION",
        target_type="sys_routing_operation",
        target_id=operation.id,
        detail=f"删除工序 {operation.id}",
    )
    repo.delete_routing_operation(db, operation)


# ==================== 组织 ====================


def _to_org_node(org: models.SysOrganization) -> dict:
    """把组织 ORM 转成树节点字典。"""
    return {
        "id": org.id,
        "org_code": org.org_code,
        "org_name": org.org_name,
        "parent_id": org.parent_id,
        "org_type": org.org_type,
        "manager_id": org.manager_id,
        "status": org.status,
        "remark": org.remark,
        "children": [],
    }


def get_organization_tree(db: Session) -> List[OrganizationTreeNode]:
    """返回组织树（真实依据 `parent_id` 递归组装；孤立节点按根处理）。"""
    rows = repo.list_organizations(db)
    nodes: Dict[int, OrganizationTreeNode] = {
        row.id: OrganizationTreeNode(**_to_org_node(row)) for row in rows
    }
    roots: List[OrganizationTreeNode] = []
    for row in rows:
        node = nodes[row.id]
        parent = nodes.get(row.parent_id) if row.parent_id else None
        if parent is not None:
            parent.children.append(node)
        else:
            roots.append(node)
    return roots


def list_organizations_flat(db: Session) -> List[models.SysOrganization]:
    """返回组织平铺列表。"""
    return repo.list_organizations(db)


def get_organization(db: Session, org_id: int) -> models.SysOrganization:
    """按 ID 取组织，不存在抛 1005。"""
    org = repo.get_organization(db, org_id)
    if not org:
        raise BusinessException(CODE_NOT_FOUND, "组织不存在")
    return org


def _validate_org_type(org_type: str) -> None:
    _require(org_type in _ORG_TYPES, CODE_INVALID_PARAM, f"组织类型不合法：{org_type}")


def _would_create_org_cycle(db: Session, org_id: int, new_parent_id: int) -> bool:
    """判断把 `org_id` 的父级改为 `new_parent_id` 是否形成环。"""
    current: Optional[int] = new_parent_id
    seen: set = set()
    while current is not None and current not in seen:
        if current == org_id:
            return True
        seen.add(current)
        parent = repo.get_organization(db, current)
        current = parent.parent_id if parent else None
    return False


def create_organization(
    db: Session, payload: OrganizationCreate
) -> models.SysOrganization:
    """新增组织：编码唯一、父级存在。"""
    if repo.get_organization_by_code(db, payload.org_code):
        raise BusinessException(CODE_CODE_EXISTS, "组织编码已存在")
    _validate_org_type(payload.org_type)
    _validate_status(payload.status)
    if payload.parent_id is not None and not repo.get_organization(db, payload.parent_id):
        raise BusinessException(CODE_NOT_FOUND, "上级组织不存在")

    org = models.SysOrganization(
        org_code=payload.org_code,
        org_name=payload.org_name,
        parent_id=payload.parent_id,
        org_type=payload.org_type,
        manager_id=payload.manager_id,
        status=payload.status,
        remark=payload.remark,
    )
    repo.add_organization(db, org)
    log_operation(
        db,
        module="system",
        action="CREATE",
        target_type="sys_organization",
        target_id=org.id,
        detail=f"新增组织 {org.org_code}",
    )
    return org


def update_organization(
    db: Session, org_id: int, payload: OrganizationUpdate
) -> models.SysOrganization:
    """修改组织：父级存在且不形成环。"""
    org = get_organization(db, org_id)
    data = payload.model_dump(exclude_unset=True)
    if "org_type" in data:
        _validate_org_type(data["org_type"])
    if "status" in data:
        _validate_status(data["status"])
    if "parent_id" in data:
        new_parent_id = data["parent_id"]
        if new_parent_id is not None:
            if not repo.get_organization(db, new_parent_id):
                raise BusinessException(CODE_NOT_FOUND, "上级组织不存在")
            if new_parent_id == org.id or _would_create_org_cycle(db, org.id, new_parent_id):
                raise BusinessException(CODE_INVALID_PARAM, "上级组织不能形成循环引用")
    for field, value in data.items():
        setattr(org, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE",
        target_type="sys_organization",
        target_id=org.id,
        detail=f"修改组织 {org.org_code}",
    )
    return org


def change_organization_status(
    db: Session, org_id: int, status: str
) -> models.SysOrganization:
    """组织状态流转。"""
    _validate_status(status)
    org = get_organization(db, org_id)
    org.status = status
    log_operation(
        db,
        module="system",
        action="STATUS",
        target_type="sys_organization",
        target_id=org.id,
        detail=f"组织 {org.org_code} 状态改为 {status}",
    )
    return org


# ==================== 人员 ====================


def list_personnel(
    db: Session,
    *,
    page: int,
    page_size: int,
    org_id: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """分页查询员工。"""
    return repo.list_personnel(
        db,
        page=page,
        page_size=page_size,
        org_id=org_id,
        status=status,
        keyword=keyword,
    )


def get_personnel(db: Session, personnel_id: int) -> models.SysPersonnel:
    """按 ID 取员工，不存在抛 1005。"""
    personnel = repo.get_personnel(db, personnel_id)
    if not personnel:
        raise BusinessException(CODE_NOT_FOUND, "员工不存在")
    return personnel


def create_personnel(db: Session, payload: PersonnelCreate) -> models.SysPersonnel:
    """新增员工：工号唯一、组织存在。"""
    if repo.get_personnel_by_no(db, payload.employee_no):
        raise BusinessException(CODE_EMPLOYEE_NO_EXISTS, "员工工号已存在")
    if not repo.get_organization(db, payload.org_id):
        raise BusinessException(CODE_NOT_FOUND, "所属组织不存在")
    _validate_status(payload.status)

    personnel = models.SysPersonnel(
        employee_no=payload.employee_no,
        person_name=payload.person_name,
        org_id=payload.org_id,
        position=payload.position,
        phone=payload.phone,
        email=payload.email,
        hire_date=payload.hire_date,
        status=payload.status,
        remark=payload.remark,
    )
    repo.add_personnel(db, personnel)
    log_operation(
        db,
        module="system",
        action="CREATE",
        target_type="sys_personnel",
        target_id=personnel.id,
        detail=f"新增员工 {personnel.employee_no}",
    )
    return personnel


def update_personnel(
    db: Session, personnel_id: int, payload: PersonnelUpdate
) -> models.SysPersonnel:
    """修改员工。"""
    personnel = get_personnel(db, personnel_id)
    data = payload.model_dump(exclude_unset=True)
    if "org_id" in data and not repo.get_organization(db, data["org_id"]):
        raise BusinessException(CODE_NOT_FOUND, "所属组织不存在")
    if "status" in data:
        _validate_status(data["status"])
    for field, value in data.items():
        setattr(personnel, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE",
        target_type="sys_personnel",
        target_id=personnel.id,
        detail=f"修改员工 {personnel.employee_no}",
    )
    return personnel


def change_personnel_status(
    db: Session, personnel_id: int, status: str
) -> models.SysPersonnel:
    """员工状态流转。"""
    _validate_status(status)
    personnel = get_personnel(db, personnel_id)
    personnel.status = status
    log_operation(
        db,
        module="system",
        action="STATUS",
        target_type="sys_personnel",
        target_id=personnel.id,
        detail=f"员工 {personnel.employee_no} 状态改为 {status}",
    )
    return personnel


# ==================== 字典 ====================


def list_dictionaries(db: Session) -> List[models.SysDictionary]:
    """返回全部字典（含字典项）。"""
    return repo.list_dictionaries(db)


def get_dictionary(db: Session, dict_id: int) -> models.SysDictionary:
    """按 ID 取字典，不存在抛 1005。"""
    dictionary = repo.get_dictionary(db, dict_id)
    if not dictionary:
        raise BusinessException(CODE_NOT_FOUND, "字典不存在")
    return dictionary


def create_dictionary(db: Session, payload: DictionaryCreate) -> models.SysDictionary:
    """新增字典：编码唯一。"""
    if repo.get_dictionary_by_code(db, payload.dict_code):
        raise BusinessException(CODE_CODE_EXISTS, "字典编码已存在")
    _validate_status(payload.status)
    dictionary = models.SysDictionary(
        dict_code=payload.dict_code,
        dict_name=payload.dict_name,
        status=payload.status,
        remark=payload.remark,
    )
    repo.add_dictionary(db, dictionary)
    log_operation(
        db,
        module="system",
        action="CREATE",
        target_type="sys_dictionary",
        target_id=dictionary.id,
        detail=f"新增字典 {dictionary.dict_code}",
    )
    return dictionary


def update_dictionary(
    db: Session, dict_id: int, payload: DictionaryUpdate
) -> models.SysDictionary:
    """修改字典。"""
    dictionary = get_dictionary(db, dict_id)
    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        _validate_status(data["status"])
    for field, value in data.items():
        setattr(dictionary, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE",
        target_type="sys_dictionary",
        target_id=dictionary.id,
        detail=f"修改字典 {dictionary.dict_code}",
    )
    return dictionary


def add_dictionary_item(
    db: Session, dict_id: int, payload: DictionaryItemCreate
) -> models.SysDictionaryItem:
    """新增字典项：`(dict_id, item_code)` 唯一。"""
    dictionary = get_dictionary(db, dict_id)
    if repo.get_dictionary_item_by_code(db, dictionary.id, payload.item_code):
        raise BusinessException(CODE_INVALID_PARAM, "字典项编码已存在")
    _validate_status(payload.status)
    item = models.SysDictionaryItem(
        dict_id=dictionary.id,
        item_code=payload.item_code,
        item_name=payload.item_name,
        item_value=payload.item_value,
        sort_no=payload.sort_no,
        status=payload.status,
    )
    repo.add_dictionary_item(db, item)
    log_operation(
        db,
        module="system",
        action="ADD_ITEM",
        target_type="sys_dictionary_item",
        target_id=item.id,
        detail=f"字典 {dictionary.dict_code} 新增项 {payload.item_code}",
    )
    return item


def update_dictionary_item(
    db: Session, item_id: int, payload: DictionaryItemUpdate
) -> models.SysDictionaryItem:
    """修改字典项。"""
    item = repo.get_dictionary_item(db, item_id)
    if not item:
        raise BusinessException(CODE_NOT_FOUND, "字典项不存在")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        _validate_status(data["status"])
    for field, value in data.items():
        setattr(item, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE_ITEM",
        target_type="sys_dictionary_item",
        target_id=item.id,
        detail=f"修改字典项 {item.id}",
    )
    return item


def delete_dictionary_item(db: Session, item_id: int) -> None:
    """删除字典项。"""
    item = repo.get_dictionary_item(db, item_id)
    if not item:
        raise BusinessException(CODE_NOT_FOUND, "字典项不存在")
    log_operation(
        db,
        module="system",
        action="DELETE_ITEM",
        target_type="sys_dictionary_item",
        target_id=item.id,
        detail=f"删除字典项 {item.id}",
    )
    repo.delete_dictionary_item(db, item)


# ==================== RBAC ====================


def list_users(
    db: Session,
    *,
    page: int,
    page_size: int,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """分页查询用户账号。"""
    return repo.list_users(
        db, page=page, page_size=page_size, status=status, keyword=keyword
    )


def get_user(db: Session, user_id: int) -> models.SysUser:
    """按 ID 取用户，不存在抛 1005。"""
    user = repo.get_user(db, user_id)
    if not user:
        raise BusinessException(CODE_NOT_FOUND, "用户不存在")
    return user


def create_user(db: Session, payload: UserCreate) -> models.SysUser:
    """新增用户账号：登录名唯一、关联员工 1:1。"""
    if repo.get_user_by_username(db, payload.username):
        raise BusinessException(CODE_CODE_EXISTS, "登录名已存在")
    _validate_status(payload.status)
    if payload.personnel_id is not None:
        if not repo.get_personnel(db, payload.personnel_id):
            raise BusinessException(CODE_NOT_FOUND, "关联员工不存在")
        if repo.get_user_by_personnel(db, payload.personnel_id):
            raise BusinessException(CODE_INVALID_PARAM, "该员工已关联其它账号")

    user = models.SysUser(
        username=payload.username,
        password_hash=_hash_password(payload.password),
        display_name=payload.display_name,
        personnel_id=payload.personnel_id,
        status=payload.status,
        remark=payload.remark,
    )
    repo.add_user(db, user)
    log_operation(
        db,
        module="system",
        action="CREATE",
        target_type="sys_user",
        target_id=user.id,
        detail=f"新增用户 {user.username}",
    )
    return user


def update_user(db: Session, user_id: int, payload: UserUpdate) -> models.SysUser:
    """修改用户账号（密码留空则不改）。"""
    user = get_user(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        _validate_status(data["status"])
    if "personnel_id" in data and data["personnel_id"] is not None:
        if not repo.get_personnel(db, data["personnel_id"]):
            raise BusinessException(CODE_NOT_FOUND, "关联员工不存在")
        existing = repo.get_user_by_personnel(db, data["personnel_id"])
        if existing and existing.id != user.id:
            raise BusinessException(CODE_INVALID_PARAM, "该员工已关联其它账号")
    password = data.pop("password", None)
    for field, value in data.items():
        setattr(user, field, value)
    if password:
        user.password_hash = _hash_password(password)
    log_operation(
        db,
        module="system",
        action="UPDATE",
        target_type="sys_user",
        target_id=user.id,
        detail=f"修改用户 {user.username}",
    )
    return user


def change_user_status(db: Session, user_id: int, status: str) -> models.SysUser:
    """用户账号状态流转。"""
    _validate_status(status)
    user = get_user(db, user_id)
    user.status = status
    log_operation(
        db,
        module="system",
        action="STATUS",
        target_type="sys_user",
        target_id=user.id,
        detail=f"用户 {user.username} 状态改为 {status}",
    )
    return user


def set_user_roles(
    db: Session, user_id: int, role_ids: Sequence[int]
) -> models.SysUser:
    """全量替换用户角色集合。"""
    user = get_user(db, user_id)
    unique_ids = list(dict.fromkeys(int(i) for i in role_ids))
    for role_id in unique_ids:
        if not repo.get_role(db, role_id):
            raise BusinessException(CODE_NOT_FOUND, f"角色不存在：{role_id}")
    repo.replace_user_roles(db, user.id, unique_ids)
    db.flush()
    repo.refresh(db, user)
    log_operation(
        db,
        module="system",
        action="SET_ROLES",
        target_type="sys_user",
        target_id=user.id,
        detail=f"设置用户 {user.username} 角色 {unique_ids}",
    )
    return user


def list_roles(db: Session, status: Optional[str] = None) -> List[models.SysRole]:
    """返回角色列表。"""
    return repo.list_roles(db, status=status)


def create_role(db: Session, payload: RoleCreate) -> models.SysRole:
    """新增角色：编码唯一。"""
    if repo.get_role_by_code(db, payload.role_code):
        raise BusinessException(CODE_CODE_EXISTS, "角色编码已存在")
    _validate_status(payload.status)
    role = models.SysRole(
        role_code=payload.role_code,
        role_name=payload.role_name,
        description=payload.description,
        status=payload.status,
    )
    repo.add_role(db, role)
    log_operation(
        db,
        module="system",
        action="CREATE",
        target_type="sys_role",
        target_id=role.id,
        detail=f"新增角色 {role.role_code}",
    )
    return role


def update_role(db: Session, role_id: int, payload: RoleUpdate) -> models.SysRole:
    """修改角色。"""
    role = repo.get_role(db, role_id)
    if not role:
        raise BusinessException(CODE_NOT_FOUND, "角色不存在")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        _validate_status(data["status"])
    for field, value in data.items():
        setattr(role, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE",
        target_type="sys_role",
        target_id=role.id,
        detail=f"修改角色 {role.role_code}",
    )
    return role


def set_role_permissions(
    db: Session, role_id: int, permission_ids: Sequence[int]
) -> models.SysRole:
    """全量替换角色权限集合。"""
    role = repo.get_role(db, role_id)
    if not role:
        raise BusinessException(CODE_NOT_FOUND, "角色不存在")
    unique_ids = list(dict.fromkeys(int(i) for i in permission_ids))
    for permission_id in unique_ids:
        if not repo.get_permission(db, permission_id):
            raise BusinessException(CODE_NOT_FOUND, f"权限不存在：{permission_id}")
    repo.replace_role_permissions(db, role.id, unique_ids)
    db.flush()
    repo.refresh(db, role)
    log_operation(
        db,
        module="system",
        action="SET_PERMISSIONS",
        target_type="sys_role",
        target_id=role.id,
        detail=f"设置角色 {role.role_code} 权限 {unique_ids}",
    )
    return role


def get_permission_tree(db: Session) -> List[PermissionTreeNode]:
    """返回权限树（真实依据 `parent_id` 递归组装）。"""
    rows = repo.list_permissions(db)
    nodes: Dict[int, PermissionTreeNode] = {
        row.id: PermissionTreeNode(
            id=row.id,
            perm_code=row.perm_code,
            perm_name=row.perm_name,
            perm_type=row.perm_type,
            parent_id=row.parent_id,
            path=row.path,
            module=row.module,
            sort_no=row.sort_no,
            status=row.status,
            children=[],
        )
        for row in rows
    }
    roots: List[PermissionTreeNode] = []
    for row in rows:
        node = nodes[row.id]
        parent = nodes.get(row.parent_id) if row.parent_id else None
        if parent is not None:
            parent.children.append(node)
        else:
            roots.append(node)
    return roots


def create_permission(
    db: Session, payload: PermissionCreate
) -> models.SysPermission:
    """新增权限点：编码唯一、类型合法、父级存在。"""
    if repo.get_permission_by_code(db, payload.perm_code):
        raise BusinessException(CODE_CODE_EXISTS, "权限编码已存在")
    _require(payload.perm_type in _PERM_TYPES, CODE_INVALID_PARAM, f"权限类型不合法：{payload.perm_type}")
    _validate_status(payload.status)
    if payload.parent_id is not None and not repo.get_permission(db, payload.parent_id):
        raise BusinessException(CODE_NOT_FOUND, "上级权限不存在")
    permission = models.SysPermission(
        perm_code=payload.perm_code,
        perm_name=payload.perm_name,
        perm_type=payload.perm_type,
        parent_id=payload.parent_id,
        path=payload.path,
        module=payload.module,
        sort_no=payload.sort_no,
        status=payload.status,
    )
    repo.add_permission(db, permission)
    log_operation(
        db,
        module="system",
        action="CREATE",
        target_type="sys_permission",
        target_id=permission.id,
        detail=f"新增权限 {permission.perm_code}",
    )
    return permission


def update_permission(
    db: Session, permission_id: int, payload: PermissionUpdate
) -> models.SysPermission:
    """修改权限点。"""
    permission = repo.get_permission(db, permission_id)
    if not permission:
        raise BusinessException(CODE_NOT_FOUND, "权限不存在")
    data = payload.model_dump(exclude_unset=True)
    if "perm_type" in data:
        _require(
            data["perm_type"] in _PERM_TYPES,
            CODE_INVALID_PARAM,
            f"权限类型不合法：{data['perm_type']}",
        )
    if "status" in data:
        _validate_status(data["status"])
    if "parent_id" in data and data["parent_id"] is not None:
        if data["parent_id"] == permission.id:
            raise BusinessException(CODE_INVALID_PARAM, "上级权限不能是自身")
        if not repo.get_permission(db, data["parent_id"]):
            raise BusinessException(CODE_NOT_FOUND, "上级权限不存在")
    for field, value in data.items():
        setattr(permission, field, value)
    log_operation(
        db,
        module="system",
        action="UPDATE",
        target_type="sys_permission",
        target_id=permission.id,
        detail=f"修改权限 {permission.perm_code}",
    )
    return permission


def login(db: Session, username: str, password: str) -> Dict[str, object]:
    """登录校验（简化版：无 JWT / Token）。

    校验 `sha256(password)` 是否匹配 `sys_user.password_hash`，
    成功则刷新 `last_login_at` 并返回用户、角色、权限集合。
    """
    user = repo.get_user_by_username(db, username)
    if not user or user.status != RecordStatus.ACTIVE.value:
        raise BusinessException(CODE_LOGIN_FAILED, "用户名或密码错误")
    if user.password_hash != _hash_password(password):
        raise BusinessException(CODE_LOGIN_FAILED, "用户名或密码错误")

    user.last_login_at = datetime.now()
    roles = list(user.roles)
    permissions = repo.list_role_permissions(db, [role.id for role in roles])
    log_operation(
        db,
        module="system",
        action="LOGIN",
        target_type="sys_user",
        target_id=user.id,
        detail=f"用户 {user.username} 登录成功",
    )
    return {"user": user, "roles": roles, "permissions": permissions}


# ==================== 操作日志 ====================


def list_operation_logs(
    db: Session,
    *,
    page: int,
    page_size: int,
    module: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
):
    """分页查询操作日志。"""
    return repo.list_operation_logs(
        db,
        page=page,
        page_size=page_size,
        module=module,
        action=action,
        target_type=target_type,
        target_id=target_id,
    )


# ==================== 统计 ====================


def get_stats(db: Session) -> Dict[str, int]:
    """基础数据统计，供首页 / Dashboard 使用。"""
    return {
        "material_count": repo.count_all(db, models.SysMaterial),
        "active_material_count": repo.count_where(
            db, models.SysMaterial, models.SysMaterial.status == RecordStatus.ACTIVE.value
        ),
        "bom_count": repo.count_all(db, models.SysBom),
        "routing_count": repo.count_all(db, models.SysRouting),
        "personnel_count": repo.count_all(db, models.SysPersonnel),
        "user_count": repo.count_all(db, models.SysUser),
        "role_count": repo.count_all(db, models.SysRole),
        "dictionary_count": repo.count_all(db, models.SysDictionary),
    }


# ==================== 课程数据导入（规格 §37 / §9） ====================

#: 仓库根目录：`backend/app/modules/system/service.py` 上溯 4 层即为仓库根。
_REPO_ROOT = Path(__file__).resolve().parents[4]

#: 支持的数据源 → 权威种子文件（相对仓库根）。
_SEED_FILES = {
    "course_chair_case": _REPO_ROOT / "data" / "seed" / "course_chair_case.json",
}

#: 课程文件未提供 BOM 子项的提前期偏置与损耗率，统一默认 0。
_IMPORT_LEAD_TIME_OFFSET = 0
_IMPORT_SCRAP_RATE = Decimal("0")

#: BOM 默认版本（节点未提供 `bom_version` 时使用）。
_DEFAULT_BOM_VERSION = "V1.0"

#: 物料编码可解析性判定规则，随预览出参返回，便于前端展示与核对。
_RESOLUTION_RULE = (
    "母件/子件编码必须存在于数据库，或包含在本次导入的物料集合内"
    "（即先执行物料导入即可满足）"
)


def _safe_int(value: Any) -> Optional[int]:
    """尽力把值转为 int，失败返回 None（用于逐行错误提示而非中断）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_decimal(value: Any) -> Optional[Decimal]:
    """尽力把值转为 Decimal，失败返回 None。"""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _load_course_seed(source: str) -> Dict[str, Any]:
    """读取课程权威种子文件并返回解析后的字典。

    - 仅支持 `source == "course_chair_case"`，其余取值抛 1011；
    - 文件缺失或缺少 `course_data.product` 同样抛 1011；
    - **只读取、不写入**，供预览与确认共用。
    """
    path = _SEED_FILES.get(source)
    if path is None:
        raise BusinessException(CODE_UNSUPPORTED_SOURCE, f"不支持的数据源：{source}")
    if not path.exists():
        raise BusinessException(CODE_UNSUPPORTED_SOURCE, f"课程种子文件不存在：{path}")
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    product = (data.get("course_data") or {}).get("product")
    if not isinstance(product, dict):
        raise BusinessException(CODE_UNSUPPORTED_SOURCE, "课程种子文件缺少 course_data.product")
    return data


def _walk_product(product: Dict[str, Any]) -> List[Tuple[int, Dict[str, Any]]]:
    """前序遍历物料树，返回 `[(level, node), ...]`，根节点 level=1。

    对任意深度都成立，不假设固定层数。
    """
    result: List[Tuple[int, Dict[str, Any]]] = []

    def visit(node: Dict[str, Any], level: int) -> None:
        result.append((level, node))
        for child in node.get("children") or []:
            if isinstance(child, dict):
                visit(child, level + 1)

    visit(product, 1)
    return result


def _validate_material_node(node: Dict[str, Any]) -> List[str]:
    """校验单个物料节点，返回错误信息列表（空表示合法）。"""
    messages: List[str] = []
    if not node.get("material_code"):
        messages.append("缺少 material_code")
    if not node.get("material_name"):
        messages.append("缺少 material_name")
    if node.get("material_type") not in _MATERIAL_TYPES:
        messages.append(f"物料类型不合法：{node.get('material_type')}")
    if node.get("supply_type") not in _SUPPLY_TYPES:
        messages.append(f"供应类型不合法：{node.get('supply_type')}")

    lead_time_days = _safe_int(node.get("lead_time_days", 0))
    if lead_time_days is None:
        messages.append("提前期格式不合法")
    elif lead_time_days < 0:
        messages.append("提前期不能为负数")

    safety_stock = _safe_decimal(node.get("safety_stock", 0))
    if safety_stock is None:
        messages.append("安全库存格式不合法")
    elif safety_stock < 0:
        messages.append("安全库存不能为负数")
    return messages


def _build_material_preview(
    db: Session, product: Dict[str, Any]
) -> Tuple[List[MaterialPreviewItemOut], List[ImportErrorOut], int]:
    """遍历物料树生成预览行、错误列表与最大层级（只读）。"""
    items: List[MaterialPreviewItemOut] = []
    errors: List[ImportErrorOut] = []
    max_level = 0
    seen_codes: set = set()

    for level, node in _walk_product(product):
        max_level = max(max_level, level)
        code = node.get("material_code") or ""
        node_errors = _validate_material_node(node)
        if code and code in seen_codes:
            node_errors.append(f"物料编码重复：{code}")
        seen_codes.add(code)

        if node_errors:
            status = "INVALID"
            for message in node_errors:
                errors.append(ImportErrorOut(material_code=code or None, message=message))
        elif repo.get_material_by_code(db, code):
            status = "EXISTING"
        else:
            status = "TO_CREATE"

        items.append(
            MaterialPreviewItemOut(
                material_code=code,
                material_name=node.get("material_name") or "",
                material_type=node.get("material_type"),
                supply_type=node.get("supply_type"),
                status=status,
            )
        )
    return items, errors, max_level


def preview_materials_import(db: Session, source: str) -> MaterialPreviewOut:
    """物料导入预览（规格 §37）：读取课程文件并逐节点校验，**不写任何数据**。

    字段来源：

    - `material_code / material_name / material_type / supply_type / unit_code`：
      直接取自课程文件节点；
    - `lead_time_days` / `safety_stock`：课程文件已给出系统默认值的节点直接采用，
      文件未给出的节点（多为采购件）按系统默认 0 处理。
    """
    data = _load_course_seed(source)
    product = data["course_data"]["product"]
    items, errors, max_level = _build_material_preview(db, product)
    summary = MaterialImportSummaryOut(
        total=len(items),
        to_create=sum(1 for item in items if item.status == "TO_CREATE"),
        existing=sum(1 for item in items if item.status == "EXISTING"),
        invalid=sum(1 for item in items if item.status == "INVALID"),
        max_level=max_level,
        source_counts={
            str(key): int(value) for key, value in (data.get("counts") or {}).items()
        },
    )
    return MaterialPreviewOut(source=source, materials=items, errors=errors, summary=summary)


def confirm_materials_import(db: Session, source: str) -> MaterialConfirmOut:
    """确认导入物料（规格 §37）：重新校验后仅创建缺失的编码。

    幂等：已存在 `material_code` 一律跳过，不重复、不覆盖。
    """
    data = _load_course_seed(source)
    product = data["course_data"]["product"]
    errors: List[ImportErrorOut] = []
    created = 0
    skipped = 0
    seen_codes: set = set()

    for level, node in _walk_product(product):
        code = node.get("material_code") or ""
        node_errors = _validate_material_node(node)
        if code and code in seen_codes:
            node_errors.append(f"物料编码重复：{code}")
        seen_codes.add(code)

        if node_errors:
            for message in node_errors:
                errors.append(ImportErrorOut(material_code=code or None, message=message))
            continue
        if repo.get_material_by_code(db, code):
            skipped += 1
            continue

        repo.add_material(
            db,
            models.SysMaterial(
                material_code=code,
                material_name=node.get("material_name") or "",
                material_type=node["material_type"],
                supply_type=node["supply_type"],
                unit_code=node.get("unit_code") or "PCS",
                lead_time_days=_safe_int(node.get("lead_time_days", 0)) or 0,
                safety_stock=_safe_decimal(node.get("safety_stock", 0)) or Decimal("0"),
                standard_cost=Decimal("0"),
                status=RecordStatus.ACTIVE.value,
            ),
        )
        created += 1

    log_operation(
        db,
        module="system",
        action="IMPORT_CREATE",
        target_type="sys_material",
        target_id=None,
        detail=f"课程数据导入物料：新建 {created}，跳过 {skipped}，错误 {len(errors)}",
    )
    return MaterialConfirmOut(source=source, created=created, skipped=skipped, errors=errors)


def preview_bom_import(db: Session, source: str) -> BomPreviewOut:
    """BOM 导入预览（规格 §9 / §37）：递归构建候选 BOM 结构，**不写任何数据**。

    校验规则：

    - 母件/子件编码可解析：`_RESOLUTION_RULE`（数据库或本次导入物料集合）；
    - `quantity > 0`；同一母件下子件不重复；沿路径检测循环引用。

    字段来源与默认值：

    - `quantity`：取自课程文件；
    - `lead_time_offset` / `scrap_rate`：课程文件未提供，**统一默认 0**（见 summary 字段）。
    """
    data = _load_course_seed(source)
    product = data["course_data"]["product"]
    all_nodes = _walk_product(product)
    all_codes = {node.get("material_code") for _, node in all_nodes if node.get("material_code")}

    def resolvable(code: Optional[str]) -> bool:
        if not code:
            return False
        return code in all_codes or repo.get_material_by_code(db, code) is not None

    materials_items, errors, _ = _build_material_preview(db, product)
    bom_items: List[BomItemPreviewOut] = []
    levels = 0

    def visit(node: Dict[str, Any], level: int, path_codes: frozenset) -> None:
        nonlocal levels
        levels = max(levels, level)
        parent_code = node.get("material_code") or ""
        seen_children: set = set()

        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            child_code = child.get("material_code") or ""
            child_level = level + 1

            if not child_code or child_code == parent_code or child_code in path_codes:
                message = "子件不能与母件相同" if child_code == parent_code else "BOM 存在循环引用或缺少编码"
                errors.append(ImportErrorOut(material_code=child_code or None, message=message))
                continue
            if not resolvable(child_code):
                errors.append(
                    ImportErrorOut(
                        material_code=child_code,
                        message="物料编码无法解析（数据库中不存在且不在本次导入集合内）",
                    )
                )
                continue
            if child_code in seen_children:
                errors.append(
                    ImportErrorOut(
                        material_code=child_code,
                        message=f"同一母件 {parent_code} 下子件重复",
                    )
                )
                continue
            seen_children.add(child_code)

            quantity = _safe_decimal(child.get("quantity"))
            if quantity is None or quantity <= 0:
                errors.append(ImportErrorOut(material_code=child_code, message="用量必须大于 0"))
                continue

            bom_items.append(
                BomItemPreviewOut(
                    parent_material_code=parent_code,
                    child_material_code=child_code,
                    quantity=quantity,
                    lead_time_offset=_IMPORT_LEAD_TIME_OFFSET,
                    scrap_rate=_IMPORT_SCRAP_RATE,
                    level=child_level,
                )
            )
            visit(child, child_level, path_codes | {parent_code})

    visit(product, 1, frozenset())

    summary = BomImportSummaryOut(
        total_nodes=len(all_nodes),
        levels=levels,
        bom_headers=sum(
            1
            for _, node in all_nodes
            if (node.get("children") or []) and not _validate_material_node(node)
        ),
        bom_items=len(bom_items),
        lead_time_offset_default=_IMPORT_LEAD_TIME_OFFSET,
        scrap_rate_default=_IMPORT_SCRAP_RATE,
        resolution_rule=_RESOLUTION_RULE,
        source_counts={
            str(key): int(value) for key, value in (data.get("counts") or {}).items()
        },
    )
    return BomPreviewOut(
        source=source, materials=materials_items, bom_items=bom_items, errors=errors, summary=summary
    )


def confirm_bom_import(db: Session, source: str) -> BomConfirmOut:
    """确认导入 BOM（规格 §9 / §37）：创建 `sys_bom` 头与 `sys_bom_item` 行。

    规则与约定：

    - **物料必须已存在于数据库**；若有缺失则抛 `BusinessException(1012, "请先导入物料…")`
      （即要求先执行物料导入确认，本实现不在 BOM 导入阶段自动补建物料）；
    - 每层含子件的节点生成一个 BOM 头，版本取节点的 `bom_version` 或默认 `V1.0`，
      `is_active=True`、`status=ACTIVE`；
    - 幂等：`(material_id, bom_version)` 已存在则复用该头，`(bom_id, child_material_id)`
      已存在则跳过，均不重复创建；
    - 子项 `quantity` 来自课程文件，`lead_time_offset` / `scrap_rate` 统一默认 0。
    """
    data = _load_course_seed(source)
    product = data["course_data"]["product"]
    all_nodes = _walk_product(product)
    errors: List[ImportErrorOut] = []

    material_by_code: Dict[str, models.SysMaterial] = {}
    missing: List[str] = []
    for _, node in all_nodes:
        code = node.get("material_code")
        if not code:
            errors.append(ImportErrorOut(material_code=None, message="缺少 material_code，已跳过"))
            continue
        material = repo.get_material_by_code(db, code)
        if material:
            material_by_code[code] = material
        else:
            missing.append(code)
    if missing:
        raise BusinessException(
            CODE_MATERIAL_MISSING_FOR_BOM, "请先导入物料：" + "、".join(missing[:8])
        )

    headers_created = 0
    items_created = 0
    skipped = 0

    def visit(node: Dict[str, Any], path_codes: frozenset) -> None:
        nonlocal headers_created, items_created, skipped
        parent_code = node.get("material_code")
        parent = material_by_code.get(parent_code)
        children = node.get("children") or []
        if parent is None or not children:
            return

        version = node.get("bom_version") or _DEFAULT_BOM_VERSION
        bom = repo.get_bom_by_material_version(db, parent.id, version)
        if bom:
            skipped += 1
        else:
            bom = models.SysBom(
                bom_code=repo.next_no(db, models.SysBom, "BOM"),
                material_id=parent.id,
                bom_version=version,
                is_active=True,
                status=RecordStatus.ACTIVE.value,
            )
            repo.add_bom(db, bom)
            headers_created += 1

        seen_children: set = set()
        for child in children:
            if not isinstance(child, dict):
                continue
            child_code = child.get("material_code")
            if not child_code or child_code == parent_code or child_code in path_codes:
                errors.append(
                    ImportErrorOut(material_code=child_code or None, message="循环引用或缺少编码，已跳过")
                )
                continue
            if child_code in seen_children:
                errors.append(
                    ImportErrorOut(material_code=child_code, message="同一母件下子件重复，已跳过")
                )
                continue
            seen_children.add(child_code)

            child_material = material_by_code.get(child_code)
            quantity = _safe_decimal(child.get("quantity"))
            if child_material is None or quantity is None or quantity <= 0:
                errors.append(
                    ImportErrorOut(material_code=child_code, message="子件物料缺失或用量不合法，已跳过")
                )
                continue

            if repo.get_bom_item_by_material(db, bom.id, child_material.id):
                skipped += 1
            else:
                repo.add_bom_item(
                    db,
                    models.SysBomItem(
                        bom_id=bom.id,
                        material_id=child_material.id,
                        quantity=quantity,
                        lead_time_offset=_IMPORT_LEAD_TIME_OFFSET,
                        scrap_rate=_IMPORT_SCRAP_RATE,
                        sequence_no=len(seen_children),
                    ),
                )
                items_created += 1

            visit(child, path_codes | {parent_code})

    visit(product, frozenset())

    log_operation(
        db,
        module="system",
        action="IMPORT_CREATE",
        target_type="sys_bom",
        target_id=None,
        detail=(
            f"课程数据导入 BOM：新建头 {headers_created}，新建子项 {items_created}，"
            f"跳过 {skipped}，错误 {len(errors)}"
        ),
    )
    return BomConfirmOut(
        source=source,
        bom_headers_created=headers_created,
        bom_items_created=items_created,
        skipped=skipped,
        errors=errors,
    )