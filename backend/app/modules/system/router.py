"""system 模块路由。

统一前缀 `/api/v1/system` 由 `app/main.py` 注入。
约定：

- 每个接口都返回 `ApiResponse[...]`，用 `success(...)` 构造；
- service 成功后由本层调用 `db.commit()`（service 自身不提交）；
- 业务校验失败由 `BusinessException` 统一转换为标准错误响应。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.pagination import PageData, PageParams
from app.common.response import ApiResponse, success
from app.core.database import get_db
from app.modules.system import schemas, service
from app.modules.system.schemas import (
    BomConfirmOut,
    BomCreate,
    BomItemCreate,
    BomItemOut,
    BomItemUpdate,
    BomOut,
    BomPreviewOut,
    BomTreeNode,
    BomUpdate,
    DictionaryCreate,
    DictionaryItemCreate,
    DictionaryItemOut,
    DictionaryItemUpdate,
    DictionaryOut,
    DictionaryUpdate,
    HealthResponse,
    ImportSourceIn,
    LoginIn,
    LoginOut,
    MaterialConfirmOut,
    MaterialCreate,
    MaterialOut,
    MaterialPreviewOut,
    MaterialUpdate,
    OperationLogOut,
    OrganizationCreate,
    OrganizationOut,
    OrganizationTreeNode,
    OrganizationUpdate,
    PermissionCreate,
    PermissionIdsUpdate,
    PermissionOut,
    PermissionTreeNode,
    PermissionUpdate,
    PersonnelCreate,
    PersonnelOut,
    PersonnelUpdate,
    RoleCreate,
    RoleIdsUpdate,
    RoleOut,
    RoleUpdate,
    RoutingCreate,
    RoutingOperationCreate,
    RoutingOperationOut,
    RoutingOperationUpdate,
    RoutingOut,
    RoutingUpdate,
    StatsResponse,
    StatusUpdate,
    SystemStatsOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.shared.enums import ModuleName, ModuleStatus
from app.shared.types import HealthData

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="system 模块健康检查")
def health() -> HealthResponse:
    """健康检查：只返回模块标识与状态，不访问数据库。"""
    return HealthResponse(
        data=HealthData(module=ModuleName.SYSTEM.value, status=ModuleStatus.UP.value)
    )


def _page(
    params: PageParams,
    total: int,
    items: List,
    out_cls,
) -> ApiResponse[PageData]:
    """构造统一分页响应。"""
    return success(
        PageData(
            page=params.page,
            page_size=params.page_size,
            total=total,
            items=[out_cls.model_validate(item) for item in items],
        )
    )


# ==================== 物料 ====================


@router.get("/materials", response_model=ApiResponse[PageData[MaterialOut]], summary="物料分页查询")
def list_materials(
    params: PageParams = Depends(PageParams.as_dependency),
    material_type: Optional[str] = None,
    supply_type: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[MaterialOut]]:
    """按类型 / 供应类型 / 状态 / 关键字分页查询物料。"""
    items, total = service.list_materials(
        db,
        page=params.page,
        page_size=params.page_size,
        material_type=material_type,
        supply_type=supply_type,
        status=status,
        keyword=keyword,
    )
    return _page(params, total, items, MaterialOut)


@router.post("/materials", response_model=ApiResponse[MaterialOut], summary="新增物料")
def create_material(
    payload: MaterialCreate, db: Session = Depends(get_db)
) -> ApiResponse[MaterialOut]:
    """新增物料，编码唯一。"""
    material = service.create_material(db, payload)
    db.commit()
    return success(MaterialOut.model_validate(material))


@router.get("/materials/{material_id}", response_model=ApiResponse[MaterialOut], summary="物料详情")
def get_material(
    material_id: int, db: Session = Depends(get_db)
) -> ApiResponse[MaterialOut]:
    """按 ID 查询物料。"""
    return success(MaterialOut.model_validate(service.get_material(db, material_id)))


@router.put("/materials/{material_id}", response_model=ApiResponse[MaterialOut], summary="修改物料")
def update_material(
    material_id: int, payload: MaterialUpdate, db: Session = Depends(get_db)
) -> ApiResponse[MaterialOut]:
    """修改物料。"""
    material = service.update_material(db, material_id, payload)
    db.commit()
    return success(MaterialOut.model_validate(material))


@router.patch(
    "/materials/{material_id}/status",
    response_model=ApiResponse[MaterialOut],
    summary="物料状态流转",
)
def change_material_status(
    material_id: int, payload: StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[MaterialOut]:
    """物料启用 / 停用（停用只置 INACTIVE）。"""
    material = service.change_material_status(db, material_id, payload.status)
    db.commit()
    return success(MaterialOut.model_validate(material))


# ==================== BOM ====================


@router.get("/boms", response_model=ApiResponse[PageData[BomOut]], summary="BOM 分页查询")
def list_boms(
    params: PageParams = Depends(PageParams.as_dependency),
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[BomOut]]:
    """按母件 / 状态 / 激活标记分页查询 BOM。"""
    items, total = service.list_boms(
        db,
        page=params.page,
        page_size=params.page_size,
        material_id=material_id,
        status=status,
        is_active=is_active,
    )
    return _page(params, total, items, BomOut)


@router.post("/boms", response_model=ApiResponse[BomOut], summary="新增 BOM")
def create_bom(payload: BomCreate, db: Session = Depends(get_db)) -> ApiResponse[BomOut]:
    """新增 BOM 头（可含子项）。"""
    bom = service.create_bom(db, payload)
    db.commit()
    return success(BomOut.model_validate(bom))


@router.get(
    "/boms/tree",
    response_model=ApiResponse[List[BomTreeNode]],
    summary="多层 BOM 展开",
)
def get_bom_tree(
    material_id: int = Query(description="根物料ID"),
    max_level: int = Query(default=10, ge=1, description="最大展开层数"),
    db: Session = Depends(get_db),
) -> ApiResponse[List[BomTreeNode]]:
    """对 `sys_bom_item` 做真实递归，返回多层 BOM 树。"""
    return success([service.get_bom_tree(db, material_id, max_level)])


@router.get("/boms/{bom_id}", response_model=ApiResponse[BomOut], summary="BOM 详情")
def get_bom(bom_id: int, db: Session = Depends(get_db)) -> ApiResponse[BomOut]:
    """按 ID 查询 BOM（含子项）。"""
    return success(BomOut.model_validate(service.get_bom(db, bom_id)))


@router.put("/boms/{bom_id}", response_model=ApiResponse[BomOut], summary="修改 BOM")
def update_bom(
    bom_id: int, payload: BomUpdate, db: Session = Depends(get_db)
) -> ApiResponse[BomOut]:
    """修改 BOM 头。"""
    bom = service.update_bom(db, bom_id, payload)
    db.commit()
    return success(BomOut.model_validate(bom))


@router.delete("/boms/{bom_id}", response_model=ApiResponse[None], summary="删除 BOM")
def delete_bom(bom_id: int, db: Session = Depends(get_db)) -> ApiResponse[None]:
    """删除 BOM 头（子项级联删除）。"""
    service.delete_bom(db, bom_id)
    db.commit()
    return success()


@router.post("/boms/{bom_id}/activate", response_model=ApiResponse[BomOut], summary="激活 BOM 版本")
def activate_bom(bom_id: int, db: Session = Depends(get_db)) -> ApiResponse[BomOut]:
    """激活指定版本，同物料其它版本置为非激活。"""
    bom = service.activate_bom(db, bom_id)
    db.commit()
    return success(BomOut.model_validate(bom))


@router.patch("/boms/{bom_id}/status", response_model=ApiResponse[BomOut], summary="BOM 状态流转")
def change_bom_status(
    bom_id: int, payload: StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[BomOut]:
    """BOM 启用 / 停用。"""
    bom = service.change_bom_status(db, bom_id, payload.status)
    db.commit()
    return success(BomOut.model_validate(bom))


@router.post(
    "/boms/{bom_id}/items",
    response_model=ApiResponse[BomItemOut],
    summary="新增 BOM 子项",
)
def add_bom_item(
    bom_id: int, payload: BomItemCreate, db: Session = Depends(get_db)
) -> ApiResponse[BomItemOut]:
    """向 BOM 追加子项（含循环引用校验）。"""
    item = service.add_bom_item(db, bom_id, payload)
    db.commit()
    return success(BomItemOut.model_validate(item))


@router.put("/bom-items/{item_id}", response_model=ApiResponse[BomItemOut], summary="修改 BOM 子项")
def update_bom_item(
    item_id: int, payload: BomItemUpdate, db: Session = Depends(get_db)
) -> ApiResponse[BomItemOut]:
    """修改 BOM 子项。"""
    item = service.update_bom_item(db, item_id, payload)
    db.commit()
    return success(BomItemOut.model_validate(item))


@router.delete("/bom-items/{item_id}", response_model=ApiResponse[None], summary="删除 BOM 子项")
def delete_bom_item(item_id: int, db: Session = Depends(get_db)) -> ApiResponse[None]:
    """删除 BOM 子项。"""
    service.delete_bom_item(db, item_id)
    db.commit()
    return success()


# ==================== 工艺路线 ====================


@router.get("/routings", response_model=ApiResponse[PageData[RoutingOut]], summary="工艺路线分页查询")
def list_routings(
    params: PageParams = Depends(PageParams.as_dependency),
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[RoutingOut]]:
    """按物料 / 状态分页查询工艺路线。"""
    items, total = service.list_routings(
        db, page=params.page, page_size=params.page_size, material_id=material_id, status=status
    )
    return _page(params, total, items, RoutingOut)


@router.post("/routings", response_model=ApiResponse[RoutingOut], summary="新增工艺路线")
def create_routing(
    payload: RoutingCreate, db: Session = Depends(get_db)
) -> ApiResponse[RoutingOut]:
    """新增工艺路线（可含工序明细）。"""
    routing = service.create_routing(db, payload)
    db.commit()
    return success(RoutingOut.model_validate(routing))


@router.get("/routings/{routing_id}", response_model=ApiResponse[RoutingOut], summary="工艺路线详情")
def get_routing(
    routing_id: int, db: Session = Depends(get_db)
) -> ApiResponse[RoutingOut]:
    """按 ID 查询工艺路线（含工序）。"""
    return success(RoutingOut.model_validate(service.get_routing(db, routing_id)))


@router.put("/routings/{routing_id}", response_model=ApiResponse[RoutingOut], summary="修改工艺路线")
def update_routing(
    routing_id: int, payload: RoutingUpdate, db: Session = Depends(get_db)
) -> ApiResponse[RoutingOut]:
    """修改工艺路线头。"""
    routing = service.update_routing(db, routing_id, payload)
    db.commit()
    return success(RoutingOut.model_validate(routing))


@router.patch(
    "/routings/{routing_id}/status",
    response_model=ApiResponse[RoutingOut],
    summary="工艺路线状态流转",
)
def change_routing_status(
    routing_id: int, payload: StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[RoutingOut]:
    """工艺路线启用 / 停用。"""
    routing = service.change_routing_status(db, routing_id, payload.status)
    db.commit()
    return success(RoutingOut.model_validate(routing))


@router.post(
    "/routings/{routing_id}/operations",
    response_model=ApiResponse[RoutingOperationOut],
    summary="新增工序",
)
def add_routing_operation(
    routing_id: int, payload: RoutingOperationCreate, db: Session = Depends(get_db)
) -> ApiResponse[RoutingOperationOut]:
    """向工艺路线追加工序。"""
    operation = service.add_routing_operation(db, routing_id, payload)
    db.commit()
    return success(RoutingOperationOut.model_validate(operation))


@router.put(
    "/routing-operations/{operation_id}",
    response_model=ApiResponse[RoutingOperationOut],
    summary="修改工序",
)
def update_routing_operation(
    operation_id: int, payload: RoutingOperationUpdate, db: Session = Depends(get_db)
) -> ApiResponse[RoutingOperationOut]:
    """修改工序行。"""
    operation = service.update_routing_operation(db, operation_id, payload)
    db.commit()
    return success(RoutingOperationOut.model_validate(operation))


@router.delete(
    "/routing-operations/{operation_id}",
    response_model=ApiResponse[None],
    summary="删除工序",
)
def delete_routing_operation(
    operation_id: int, db: Session = Depends(get_db)
) -> ApiResponse[None]:
    """删除工序行。"""
    service.delete_routing_operation(db, operation_id)
    db.commit()
    return success()


# ==================== 组织 ====================


@router.get(
    "/organizations",
    response_model=ApiResponse[List[OrganizationTreeNode]],
    summary="组织树查询",
)
def get_organization_tree(
    db: Session = Depends(get_db),
) -> ApiResponse[List[OrganizationTreeNode]]:
    """返回组织树。"""
    return success(service.get_organization_tree(db))


@router.get(
    "/organizations/flat",
    response_model=ApiResponse[List[OrganizationOut]],
    summary="组织平铺查询",
)
def list_organizations_flat(
    db: Session = Depends(get_db),
) -> ApiResponse[List[OrganizationOut]]:
    """返回组织平铺列表。"""
    return success(
        [OrganizationOut.model_validate(org) for org in service.list_organizations_flat(db)]
    )


@router.get(
    "/organizations/{org_id}", response_model=ApiResponse[OrganizationOut], summary="组织详情"
)
def get_organization(
    org_id: int, db: Session = Depends(get_db)
) -> ApiResponse[OrganizationOut]:
    """按 ID 查询组织。"""
    return success(OrganizationOut.model_validate(service.get_organization(db, org_id)))


@router.post("/organizations", response_model=ApiResponse[OrganizationOut], summary="新增组织")
def create_organization(
    payload: OrganizationCreate, db: Session = Depends(get_db)
) -> ApiResponse[OrganizationOut]:
    """新增组织。"""
    org = service.create_organization(db, payload)
    db.commit()
    return success(OrganizationOut.model_validate(org))


@router.put(
    "/organizations/{org_id}", response_model=ApiResponse[OrganizationOut], summary="修改组织"
)
def update_organization(
    org_id: int, payload: OrganizationUpdate, db: Session = Depends(get_db)
) -> ApiResponse[OrganizationOut]:
    """修改组织（父级不得形成环）。"""
    org = service.update_organization(db, org_id, payload)
    db.commit()
    return success(OrganizationOut.model_validate(org))


@router.patch(
    "/organizations/{org_id}/status",
    response_model=ApiResponse[OrganizationOut],
    summary="组织状态流转",
)
def change_organization_status(
    org_id: int, payload: StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[OrganizationOut]:
    """组织启用 / 停用。"""
    org = service.change_organization_status(db, org_id, payload.status)
    db.commit()
    return success(OrganizationOut.model_validate(org))


# ==================== 人员 ====================


@router.get("/personnel", response_model=ApiResponse[PageData[PersonnelOut]], summary="人员分页查询")
def list_personnel(
    params: PageParams = Depends(PageParams.as_dependency),
    org_id: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[PersonnelOut]]:
    """按组织 / 状态 / 关键字分页查询员工。"""
    items, total = service.list_personnel(
        db,
        page=params.page,
        page_size=params.page_size,
        org_id=org_id,
        status=status,
        keyword=keyword,
    )
    return _page(params, total, items, PersonnelOut)


@router.get("/personnel/{personnel_id}", response_model=ApiResponse[PersonnelOut], summary="人员详情")
def get_personnel(
    personnel_id: int, db: Session = Depends(get_db)
) -> ApiResponse[PersonnelOut]:
    """按 ID 查询员工。"""
    return success(PersonnelOut.model_validate(service.get_personnel(db, personnel_id)))


@router.post("/personnel", response_model=ApiResponse[PersonnelOut], summary="新增人员")
def create_personnel(
    payload: PersonnelCreate, db: Session = Depends(get_db)
) -> ApiResponse[PersonnelOut]:
    """新增员工，工号唯一。"""
    personnel = service.create_personnel(db, payload)
    db.commit()
    return success(PersonnelOut.model_validate(personnel))


@router.put("/personnel/{personnel_id}", response_model=ApiResponse[PersonnelOut], summary="修改人员")
def update_personnel(
    personnel_id: int, payload: PersonnelUpdate, db: Session = Depends(get_db)
) -> ApiResponse[PersonnelOut]:
    """修改员工。"""
    personnel = service.update_personnel(db, personnel_id, payload)
    db.commit()
    return success(PersonnelOut.model_validate(personnel))


@router.patch(
    "/personnel/{personnel_id}/status",
    response_model=ApiResponse[PersonnelOut],
    summary="人员状态流转",
)
def change_personnel_status(
    personnel_id: int, payload: StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[PersonnelOut]:
    """员工启用 / 停用。"""
    personnel = service.change_personnel_status(db, personnel_id, payload.status)
    db.commit()
    return success(PersonnelOut.model_validate(personnel))


# ==================== 字典 ====================


@router.get("/dictionaries", response_model=ApiResponse[List[DictionaryOut]], summary="字典查询")
def list_dictionaries(db: Session = Depends(get_db)) -> ApiResponse[List[DictionaryOut]]:
    """返回全部字典（含字典项）。"""
    return success(
        [DictionaryOut.model_validate(d) for d in service.list_dictionaries(db)]
    )


@router.post("/dictionaries", response_model=ApiResponse[DictionaryOut], summary="新增字典")
def create_dictionary(
    payload: DictionaryCreate, db: Session = Depends(get_db)
) -> ApiResponse[DictionaryOut]:
    """新增字典，编码唯一。"""
    dictionary = service.create_dictionary(db, payload)
    db.commit()
    return success(DictionaryOut.model_validate(dictionary))


@router.put("/dictionaries/{dict_id}", response_model=ApiResponse[DictionaryOut], summary="修改字典")
def update_dictionary(
    dict_id: int, payload: DictionaryUpdate, db: Session = Depends(get_db)
) -> ApiResponse[DictionaryOut]:
    """修改字典。"""
    dictionary = service.update_dictionary(db, dict_id, payload)
    db.commit()
    return success(DictionaryOut.model_validate(dictionary))


@router.post(
    "/dictionaries/{dict_id}/items",
    response_model=ApiResponse[DictionaryItemOut],
    summary="新增字典项",
)
def add_dictionary_item(
    dict_id: int, payload: DictionaryItemCreate, db: Session = Depends(get_db)
) -> ApiResponse[DictionaryItemOut]:
    """向字典追加字典项。"""
    item = service.add_dictionary_item(db, dict_id, payload)
    db.commit()
    return success(DictionaryItemOut.model_validate(item))


@router.put(
    "/dictionary-items/{item_id}",
    response_model=ApiResponse[DictionaryItemOut],
    summary="修改字典项",
)
def update_dictionary_item(
    item_id: int, payload: DictionaryItemUpdate, db: Session = Depends(get_db)
) -> ApiResponse[DictionaryItemOut]:
    """修改字典项。"""
    item = service.update_dictionary_item(db, item_id, payload)
    db.commit()
    return success(DictionaryItemOut.model_validate(item))


@router.delete(
    "/dictionary-items/{item_id}",
    response_model=ApiResponse[None],
    summary="删除字典项",
)
def delete_dictionary_item(
    item_id: int, db: Session = Depends(get_db)
) -> ApiResponse[None]:
    """删除字典项。"""
    service.delete_dictionary_item(db, item_id)
    db.commit()
    return success()


# ==================== RBAC ====================


@router.get("/users", response_model=ApiResponse[PageData[UserOut]], summary="用户分页查询")
def list_users(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[UserOut]]:
    """按状态 / 关键字分页查询用户。"""
    items, total = service.list_users(
        db, page=params.page, page_size=params.page_size, status=status, keyword=keyword
    )
    return _page(params, total, items, UserOut)


@router.post("/users", response_model=ApiResponse[UserOut], summary="新增用户")
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> ApiResponse[UserOut]:
    """新增用户账号（密码 sha256 入库）。"""
    user = service.create_user(db, payload)
    db.commit()
    return success(UserOut.model_validate(user))


@router.put("/users/{user_id}", response_model=ApiResponse[UserOut], summary="修改用户")
def update_user(
    user_id: int, payload: UserUpdate, db: Session = Depends(get_db)
) -> ApiResponse[UserOut]:
    """修改用户账号。"""
    user = service.update_user(db, user_id, payload)
    db.commit()
    return success(UserOut.model_validate(user))


@router.patch("/users/{user_id}/status", response_model=ApiResponse[UserOut], summary="用户状态流转")
def change_user_status(
    user_id: int, payload: StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[UserOut]:
    """用户启用 / 停用。"""
    user = service.change_user_status(db, user_id, payload.status)
    db.commit()
    return success(UserOut.model_validate(user))


@router.post("/users/{user_id}/roles", response_model=ApiResponse[UserOut], summary="设置用户角色")
def set_user_roles(
    user_id: int, payload: RoleIdsUpdate, db: Session = Depends(get_db)
) -> ApiResponse[UserOut]:
    """全量替换用户角色集合。"""
    user = service.set_user_roles(db, user_id, payload.role_ids)
    db.commit()
    return success(UserOut.model_validate(user))


@router.get("/roles", response_model=ApiResponse[List[RoleOut]], summary="角色查询")
def list_roles(
    status: Optional[str] = None, db: Session = Depends(get_db)
) -> ApiResponse[List[RoleOut]]:
    """返回角色列表（含权限）。"""
    return success([RoleOut.model_validate(r) for r in service.list_roles(db, status)])


@router.post("/roles", response_model=ApiResponse[RoleOut], summary="新增角色")
def create_role(payload: RoleCreate, db: Session = Depends(get_db)) -> ApiResponse[RoleOut]:
    """新增角色，编码唯一。"""
    role = service.create_role(db, payload)
    db.commit()
    return success(RoleOut.model_validate(role))


@router.put("/roles/{role_id}", response_model=ApiResponse[RoleOut], summary="修改角色")
def update_role(
    role_id: int, payload: RoleUpdate, db: Session = Depends(get_db)
) -> ApiResponse[RoleOut]:
    """修改角色。"""
    role = service.update_role(db, role_id, payload)
    db.commit()
    return success(RoleOut.model_validate(role))


@router.post(
    "/roles/{role_id}/permissions",
    response_model=ApiResponse[RoleOut],
    summary="设置角色权限",
)
def set_role_permissions(
    role_id: int, payload: PermissionIdsUpdate, db: Session = Depends(get_db)
) -> ApiResponse[RoleOut]:
    """全量替换角色权限集合。"""
    role = service.set_role_permissions(db, role_id, payload.permission_ids)
    db.commit()
    return success(RoleOut.model_validate(role))


@router.get(
    "/permissions",
    response_model=ApiResponse[List[PermissionTreeNode]],
    summary="权限树查询",
)
def get_permission_tree(
    db: Session = Depends(get_db),
) -> ApiResponse[List[PermissionTreeNode]]:
    """返回权限树。"""
    return success(service.get_permission_tree(db))


@router.post(
    "/permissions", response_model=ApiResponse[PermissionOut], summary="新增权限点"
)
def create_permission(
    payload: PermissionCreate, db: Session = Depends(get_db)
) -> ApiResponse[PermissionOut]:
    """新增权限点，编码唯一。"""
    permission = service.create_permission(db, payload)
    db.commit()
    return success(PermissionOut.model_validate(permission))


@router.put(
    "/permissions/{permission_id}",
    response_model=ApiResponse[PermissionOut],
    summary="修改权限点",
)
def update_permission(
    permission_id: int, payload: PermissionUpdate, db: Session = Depends(get_db)
) -> ApiResponse[PermissionOut]:
    """修改权限点。"""
    permission = service.update_permission(db, permission_id, payload)
    db.commit()
    return success(PermissionOut.model_validate(permission))


@router.post("/auth/login", response_model=ApiResponse[LoginOut], summary="登录（简化版）")
def login(payload: LoginIn, db: Session = Depends(get_db)) -> ApiResponse[LoginOut]:
    """校验用户名密码，刷新最近登录时间并返回用户 / 角色 / 权限。

    简化说明：本接口**不签发 JWT / Token**。
    """
    result = service.login(db, payload.username, payload.password)
    db.commit()
    return success(
        LoginOut(
            user=UserOut.model_validate(result["user"]),
            roles=[RoleOut.model_validate(role) for role in result["roles"]],
            permissions=[
                PermissionOut.model_validate(perm) for perm in result["permissions"]
            ],
        )
    )


# ==================== 操作日志 ====================


@router.get(
    "/operation-logs",
    response_model=ApiResponse[PageData[OperationLogOut]],
    summary="操作日志分页查询",
)
def list_operation_logs(
    params: PageParams = Depends(PageParams.as_dependency),
    module: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[OperationLogOut]]:
    """按模块 / 动作 / 目标分页查询操作日志。"""
    items, total = service.list_operation_logs(
        db,
        page=params.page,
        page_size=params.page_size,
        module=module,
        action=action,
        target_type=target_type,
        target_id=target_id,
    )
    return _page(params, total, items, OperationLogOut)


# ==================== 统计 ====================


@router.get("/stats", response_model=StatsResponse, summary="系统基础数据统计")
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    """返回物料 / BOM / 工艺 / 人员 / 用户 / 角色 / 字典统计，供首页使用。"""
    return StatsResponse(data=SystemStatsOut(**service.get_stats(db)))


# ==================== 课程数据导入（规格 §37） ====================


@router.post(
    "/import/materials/preview",
    response_model=ApiResponse[MaterialPreviewOut],
    summary="课程物料导入预览",
)
def preview_materials_import(
    payload: ImportSourceIn, db: Session = Depends(get_db)
) -> ApiResponse[MaterialPreviewOut]:
    """读取课程种子文件并逐节点校验，返回待创建 / 已存在 / 非法清单，**不写库**。"""
    return success(service.preview_materials_import(db, payload.source))


@router.post(
    "/import/materials/confirm",
    response_model=ApiResponse[MaterialConfirmOut],
    summary="课程物料导入确认",
)
def confirm_materials_import(
    payload: ImportSourceIn, db: Session = Depends(get_db)
) -> ApiResponse[MaterialConfirmOut]:
    """重新校验后仅创建缺失物料（幂等：已存在的编码跳过）。"""
    result = service.confirm_materials_import(db, payload.source)
    db.commit()
    return success(result)


@router.post(
    "/import/bom/preview",
    response_model=ApiResponse[BomPreviewOut],
    summary="课程 BOM 导入预览",
)
def preview_bom_import(
    payload: ImportSourceIn, db: Session = Depends(get_db)
) -> ApiResponse[BomPreviewOut]:
    """递归构建候选 BOM 结构并校验（编码可解析 / 用量 / 无环 / 不重复），**不写库**。"""
    return success(service.preview_bom_import(db, payload.source))


@router.post(
    "/import/bom/confirm",
    response_model=ApiResponse[BomConfirmOut],
    summary="课程 BOM 导入确认",
)
def confirm_bom_import(
    payload: ImportSourceIn, db: Session = Depends(get_db)
) -> ApiResponse[BomConfirmOut]:
    """创建 BOM 头与子项（幂等：已存在的版本 / 子项跳过）；物料缺失时抛 1012。"""
    result = service.confirm_bom_import(db, payload.source)
    db.commit()
    return success(result)