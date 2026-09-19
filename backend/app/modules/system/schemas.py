"""system 模块 Pydantic Schema。

命名约定：

- `XxxCreate` 新增入参、`XxxUpdate` 修改入参
- `XxxOut` 出参（单个）；列表接口统一返回 `ApiResponse[PageData[XxxOut]]`
- 所有接口统一用 `ApiResponse[...]` 包装（见 `app.common.response`）
- 分页统一使用 `PageData[...]`（见 `app.common.pagination`）

system 模块错误码区段：`1000~1999`。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.common.response import ApiResponse
from app.shared.types import HealthData

HealthResponse = ApiResponse[HealthData]


class _OrmBase(BaseModel):
    """允许从 ORM 对象直接构造的出参基类。"""

    model_config = ConfigDict(from_attributes=True)


class _IdOut(_OrmBase):
    id: int = Field(description="主键")


class StatusUpdate(BaseModel):
    """通用状态流转入参（仅 ACTIVE / INACTIVE）。"""

    status: str = Field(description="目标状态 ACTIVE/INACTIVE")


# ==================== 物料 ====================


class MaterialCreate(BaseModel):
    """物料新增入参。"""

    material_code: str = Field(max_length=50, description="物料编码（唯一）")
    material_name: str = Field(max_length=100, description="物料名称")
    material_type: str = Field(description="物料类型 RAW/PURCHASED/SEMI/FINISHED")
    supply_type: str = Field(description="供应类型 MAKE/BUY")
    unit_code: str = Field(default="PCS", max_length=20, description="计量单位")
    specification: Optional[str] = Field(default=None, max_length=200, description="规格型号")
    material_group: Optional[str] = Field(default=None, max_length=50, description="物料分组")
    lead_time_days: int = Field(default=0, description="提前期（天）")
    safety_stock: Decimal = Field(default=Decimal("0"), description="安全库存")
    standard_cost: Decimal = Field(default=Decimal("0"), description="标准成本")
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")
    remark: Optional[str] = None


class MaterialUpdate(BaseModel):
    """物料修改入参（编码不可改）。"""

    material_name: Optional[str] = Field(default=None, max_length=100)
    material_type: Optional[str] = None
    supply_type: Optional[str] = None
    unit_code: Optional[str] = Field(default=None, max_length=20)
    specification: Optional[str] = Field(default=None, max_length=200)
    material_group: Optional[str] = Field(default=None, max_length=50)
    lead_time_days: Optional[int] = None
    safety_stock: Optional[Decimal] = None
    standard_cost: Optional[Decimal] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class MaterialOut(_IdOut):
    material_code: str
    material_name: str
    material_type: str
    supply_type: str
    unit_code: str
    specification: Optional[str] = None
    material_group: Optional[str] = None
    lead_time_days: int
    safety_stock: Decimal
    standard_cost: Decimal
    status: str
    remark: Optional[str] = None


# ==================== BOM ====================


class BomItemCreate(BaseModel):
    """BOM 子项新增入参。"""

    material_id: int = Field(description="子件物料ID")
    quantity: Decimal = Field(description="单位用量（>0）")
    lead_time_offset: int = Field(default=0, description="提前期偏置（天，>=0）")
    scrap_rate: Decimal = Field(default=Decimal("0"), description="损耗率 [0,1)")
    sequence_no: int = Field(default=1, description="序号")
    remark: Optional[str] = Field(default=None, max_length=200)


class BomItemUpdate(BaseModel):
    """BOM 子项修改入参。"""

    material_id: Optional[int] = None
    quantity: Optional[Decimal] = None
    lead_time_offset: Optional[int] = None
    scrap_rate: Optional[Decimal] = None
    sequence_no: Optional[int] = None
    remark: Optional[str] = Field(default=None, max_length=200)


class BomCreate(BaseModel):
    """BOM 头新增入参（可含子项明细）。"""

    bom_code: Optional[str] = Field(default=None, max_length=50, description="BOM编码，留空自动生成")
    material_id: int = Field(description="母件物料ID")
    bom_version: str = Field(default="V1.0", max_length=20, description="BOM版本")
    effective_date: Optional[date] = Field(default=None, description="生效日期")
    expiry_date: Optional[date] = Field(default=None, description="失效日期")
    is_active: bool = Field(default=True, description="是否当前激活版本")
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")
    remark: Optional[str] = None
    items: List[BomItemCreate] = Field(default_factory=list, description="BOM子项")


class BomUpdate(BaseModel):
    """BOM 头修改入参。"""

    bom_version: Optional[str] = Field(default=None, max_length=20)
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class BomItemOut(_IdOut):
    bom_id: int
    material_id: int
    quantity: Decimal
    lead_time_offset: int
    scrap_rate: Decimal
    sequence_no: int
    remark: Optional[str] = None


class BomOut(_IdOut):
    bom_code: str
    material_id: int
    bom_version: str
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    is_active: bool
    status: str
    remark: Optional[str] = None
    items: List[BomItemOut] = Field(default_factory=list)


class BomTreeNode(BaseModel):
    """多层 BOM 展开节点（递归结构）。"""

    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    quantity: Decimal
    lead_time_offset: int
    scrap_rate: Decimal
    level: int
    children: List["BomTreeNode"] = Field(default_factory=list)


BomTreeNode.model_rebuild()


# ==================== 工艺路线 ====================


class RoutingOperationCreate(BaseModel):
    """工序行新增入参。"""

    sequence_no: int = Field(description="工序顺序号")
    operation_code: str = Field(max_length=50, description="工序编码")
    operation_name: str = Field(max_length=100, description="工序名称")
    work_center: Optional[str] = Field(default=None, max_length=50)
    setup_time: Decimal = Field(default=Decimal("0"), description="准备工时（分钟，>=0）")
    run_time: Decimal = Field(default=Decimal("0"), description="单件加工工时（分钟，>=0）")
    remark: Optional[str] = Field(default=None, max_length=200)


class RoutingOperationUpdate(BaseModel):
    """工序行修改入参。"""

    sequence_no: Optional[int] = None
    operation_code: Optional[str] = Field(default=None, max_length=50)
    operation_name: Optional[str] = Field(default=None, max_length=100)
    work_center: Optional[str] = Field(default=None, max_length=50)
    setup_time: Optional[Decimal] = None
    run_time: Optional[Decimal] = None
    remark: Optional[str] = Field(default=None, max_length=200)


class RoutingCreate(BaseModel):
    """工艺路线新增入参（可含工序明细）。"""

    routing_code: Optional[str] = Field(
        default=None, max_length=50, description="工艺路线编码，留空自动生成"
    )
    material_id: int = Field(description="自制件物料ID")
    routing_version: str = Field(default="V1.0", max_length=20, description="工艺版本")
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")
    remark: Optional[str] = None
    operations: List[RoutingOperationCreate] = Field(default_factory=list, description="工序明细")


class RoutingUpdate(BaseModel):
    """工艺路线头修改入参。"""

    routing_version: Optional[str] = Field(default=None, max_length=20)
    status: Optional[str] = None
    remark: Optional[str] = None


class RoutingOperationOut(_IdOut):
    routing_id: int
    sequence_no: int
    operation_code: str
    operation_name: str
    work_center: Optional[str] = None
    setup_time: Decimal
    run_time: Decimal
    remark: Optional[str] = None


class RoutingOut(_IdOut):
    routing_code: str
    material_id: int
    routing_version: str
    status: str
    remark: Optional[str] = None
    operations: List[RoutingOperationOut] = Field(default_factory=list)


# ==================== 组织 ====================


class OrganizationCreate(BaseModel):
    """组织新增入参。"""

    org_code: str = Field(max_length=50, description="组织编码（唯一）")
    org_name: str = Field(max_length=100, description="组织名称")
    parent_id: Optional[int] = Field(default=None, description="上级组织ID")
    org_type: str = Field(default="DEPARTMENT", description="COMPANY/FACTORY/DEPARTMENT/WORKSHOP/WAREHOUSE")
    manager_id: Optional[int] = Field(default=None, description="负责人ID（sys_personnel.id）")
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")
    remark: Optional[str] = None


class OrganizationUpdate(BaseModel):
    """组织修改入参。"""

    org_name: Optional[str] = Field(default=None, max_length=100)
    parent_id: Optional[int] = None
    org_type: Optional[str] = None
    manager_id: Optional[int] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class OrganizationOut(_IdOut):
    org_code: str
    org_name: str
    parent_id: Optional[int] = None
    org_type: str
    manager_id: Optional[int] = None
    status: str
    remark: Optional[str] = None


class OrganizationTreeNode(OrganizationOut):
    """组织树节点（递归结构）。"""

    children: List["OrganizationTreeNode"] = Field(default_factory=list)


OrganizationTreeNode.model_rebuild()


# ==================== 人员 ====================


class PersonnelCreate(BaseModel):
    """人员新增入参。"""

    employee_no: str = Field(max_length=50, description="员工工号（唯一）")
    person_name: str = Field(max_length=100, description="姓名")
    org_id: int = Field(description="所属组织ID")
    position: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=100)
    hire_date: Optional[date] = None
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")
    remark: Optional[str] = None


class PersonnelUpdate(BaseModel):
    """人员修改入参。"""

    person_name: Optional[str] = Field(default=None, max_length=100)
    org_id: Optional[int] = None
    position: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=100)
    hire_date: Optional[date] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class PersonnelOut(_IdOut):
    employee_no: str
    person_name: str
    org_id: int
    position: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    hire_date: Optional[date] = None
    status: str
    remark: Optional[str] = None


# ==================== 字典 ====================


class DictionaryItemCreate(BaseModel):
    """字典项新增入参。"""

    item_code: str = Field(max_length=50, description="字典项编码")
    item_name: str = Field(max_length=100, description="字典项名称")
    item_value: Optional[str] = Field(default=None, max_length=200)
    sort_no: int = Field(default=0, description="排序号")
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")


class DictionaryItemUpdate(BaseModel):
    """字典项修改入参。"""

    item_name: Optional[str] = Field(default=None, max_length=100)
    item_value: Optional[str] = Field(default=None, max_length=200)
    sort_no: Optional[int] = None
    status: Optional[str] = None


class DictionaryCreate(BaseModel):
    """字典新增入参。"""

    dict_code: str = Field(max_length=50, description="字典编码（唯一）")
    dict_name: str = Field(max_length=100, description="字典名称")
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")
    remark: Optional[str] = None


class DictionaryUpdate(BaseModel):
    """字典修改入参。"""

    dict_name: Optional[str] = Field(default=None, max_length=100)
    status: Optional[str] = None
    remark: Optional[str] = None


class DictionaryItemOut(_IdOut):
    dict_id: int
    item_code: str
    item_name: str
    item_value: Optional[str] = None
    sort_no: int
    status: str


class DictionaryOut(_IdOut):
    dict_code: str
    dict_name: str
    status: str
    remark: Optional[str] = None
    items: List[DictionaryItemOut] = Field(default_factory=list)


# ==================== RBAC ====================


class UserCreate(BaseModel):
    """用户账号新增入参。"""

    username: str = Field(max_length=50, description="登录名（唯一）")
    password: str = Field(description="明文密码（服务端 sha256 后入库）")
    display_name: str = Field(max_length=100, description="显示名")
    personnel_id: Optional[int] = Field(default=None, description="关联员工ID（可为空，1:1）")
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")
    remark: Optional[str] = None


class UserUpdate(BaseModel):
    """用户账号修改入参。"""

    display_name: Optional[str] = Field(default=None, max_length=100)
    password: Optional[str] = Field(default=None, description="新密码，留空不改")
    personnel_id: Optional[int] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class UserOut(_IdOut):
    username: str
    display_name: str
    personnel_id: Optional[int] = None
    status: str
    last_login_at: Optional[datetime] = None
    remark: Optional[str] = None
    roles: List["RoleOut"] = Field(default_factory=list)


class RoleCreate(BaseModel):
    """角色新增入参。"""

    role_code: str = Field(max_length=50, description="角色编码（唯一）")
    role_name: str = Field(max_length=100, description="角色名称")
    description: Optional[str] = Field(default=None, max_length=255)
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")


class RoleUpdate(BaseModel):
    """角色修改入参。"""

    role_name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)
    status: Optional[str] = None


class RoleOut(_IdOut):
    role_code: str
    role_name: str
    description: Optional[str] = None
    status: str
    permissions: List["PermissionOut"] = Field(default_factory=list)


class PermissionCreate(BaseModel):
    """权限点新增入参。"""

    perm_code: str = Field(max_length=50, description="权限编码（唯一）")
    perm_name: str = Field(max_length=100, description="权限名称")
    perm_type: str = Field(description="权限类型 MENU/PAGE/ACTION")
    parent_id: Optional[int] = Field(default=None, description="上级权限ID")
    path: Optional[str] = Field(default=None, max_length=200, description="前端路由/接口路径")
    module: Optional[str] = Field(default=None, max_length=20, description="所属模块")
    sort_no: int = Field(default=0, description="排序号")
    status: str = Field(default="ACTIVE", description="状态 ACTIVE/INACTIVE")


class PermissionUpdate(BaseModel):
    """权限点修改入参。"""

    perm_name: Optional[str] = Field(default=None, max_length=100)
    perm_type: Optional[str] = None
    parent_id: Optional[int] = None
    path: Optional[str] = Field(default=None, max_length=200)
    module: Optional[str] = Field(default=None, max_length=20)
    sort_no: Optional[int] = None
    status: Optional[str] = None


class PermissionOut(_IdOut):
    perm_code: str
    perm_name: str
    perm_type: str
    parent_id: Optional[int] = None
    path: Optional[str] = None
    module: Optional[str] = None
    sort_no: int
    status: str


class PermissionTreeNode(PermissionOut):
    """权限树节点（递归结构）。"""

    children: List["PermissionTreeNode"] = Field(default_factory=list)


PermissionTreeNode.model_rebuild()


class RoleIdsUpdate(BaseModel):
    """替换用户角色集合入参。"""

    role_ids: List[int] = Field(default_factory=list, description="角色ID集合（全量替换）")


class PermissionIdsUpdate(BaseModel):
    """替换角色权限集合入参。"""

    permission_ids: List[int] = Field(default_factory=list, description="权限ID集合（全量替换）")


class LoginIn(BaseModel):
    """登录入参。"""

    username: str = Field(description="登录名")
    password: str = Field(description="明文密码")


class LoginOut(BaseModel):
    """登录返回体（简化版：不含 JWT / Token，见模块说明）。"""

    user: UserOut
    roles: List[RoleOut] = Field(default_factory=list)
    permissions: List[PermissionOut] = Field(default_factory=list)


UserOut.model_rebuild()
RoleOut.model_rebuild()


# ==================== 操作日志 ====================


class OperationLogOut(_IdOut):
    module: str
    action: str
    target_type: str
    target_id: Optional[int] = None
    operator_id: Optional[int] = None
    detail: Optional[str] = None
    created_at: datetime


# ==================== 统计 ====================


class SystemStatsOut(BaseModel):
    """系统基础数据统计（供首页 / Dashboard 使用）。"""

    material_count: int = Field(description="物料总数")
    active_material_count: int = Field(description="启用物料数")
    bom_count: int = Field(description="BOM 总数")
    routing_count: int = Field(description="工艺路线总数")
    personnel_count: int = Field(description="员工总数")
    user_count: int = Field(description="用户账号总数")
    role_count: int = Field(description="角色总数")
    dictionary_count: int = Field(description="字典总数")


StatsResponse = ApiResponse[SystemStatsOut]


# ==================== 课程数据导入（规格 §37） ====================


class ImportSourceIn(BaseModel):
    """导入请求入参：只指定数据源标识。

    `course_chair_case` 表示读取仓库根目录下 `data/seed/course_chair_case.json`
    的课程权威数据；其余取值一律拒绝（1011）。
    """

    source: str = Field(
        default="course_chair_case", description="数据源标识，当前仅支持 course_chair_case"
    )


class ImportErrorOut(BaseModel):
    """单条导入错误（错误提示，规格 §37）。"""

    material_code: Optional[str] = Field(default=None, description="相关物料编码")
    message: str = Field(description="错误原因")


class MaterialPreviewItemOut(BaseModel):
    """物料导入预览行。"""

    material_code: str = Field(description="物料编码")
    material_name: str = Field(description="物料名称")
    material_type: Optional[str] = Field(default=None, description="物料类型")
    supply_type: Optional[str] = Field(default=None, description="供应类型")
    status: str = Field(description="TO_CREATE / EXISTING / INVALID")


class MaterialImportSummaryOut(BaseModel):
    """物料导入预览汇总。"""

    total: int = Field(description="树中物料节点总数")
    to_create: int = Field(description="待创建数量")
    existing: int = Field(description="已存在数量")
    invalid: int = Field(description="校验不通过数量")
    max_level: int = Field(description="树的最大层级（根为 1）")
    source_counts: Dict[str, int] = Field(
        default_factory=dict, description="源文件 counts（levels/semi_components/purchased_parts/total_nodes），用于交叉核对"
    )


class MaterialPreviewOut(BaseModel):
    """物料导入预览出参（预览不写库）。"""

    source: str = Field(description="数据源标识")
    materials: List[MaterialPreviewItemOut] = Field(default_factory=list)
    errors: List[ImportErrorOut] = Field(default_factory=list)
    summary: MaterialImportSummaryOut


class MaterialConfirmOut(BaseModel):
    """物料导入确认出参（幂等：已存在的编码跳过）。"""

    source: str = Field(description="数据源标识")
    created: int = Field(description="新建物料数")
    skipped: int = Field(description="已存在而跳过的物料数")
    errors: List[ImportErrorOut] = Field(default_factory=list)


class BomItemPreviewOut(BaseModel):
    """BOM 子项导入预览行。"""

    parent_material_code: str = Field(description="母件物料编码")
    child_material_code: str = Field(description="子件物料编码")
    quantity: Decimal = Field(description="单位用量（来自课程文件）")
    lead_time_offset: int = Field(description="提前期偏置（课程文件未提供，默认 0）")
    scrap_rate: Decimal = Field(description="损耗率（课程文件未提供，默认 0）")
    level: int = Field(description="子件所在层级（根为 1）")


class BomImportSummaryOut(BaseModel):
    """BOM 导入预览汇总。"""

    total_nodes: int = Field(description="树中物料节点总数")
    levels: int = Field(description="树的最大层级（根为 1）")
    bom_headers: int = Field(description="将生成/复用的 BOM 头数量（含子件的节点数）")
    bom_items: int = Field(description="有效的 BOM 子项行数")
    lead_time_offset_default: int = Field(default=0, description="课程文件未提供，统一默认 0")
    scrap_rate_default: Decimal = Field(default=Decimal("0"), description="课程文件未提供，统一默认 0")
    resolution_rule: str = Field(description="物料编码可解析性判定规则说明")
    source_counts: Dict[str, int] = Field(default_factory=dict, description="源文件 counts，用于交叉核对")


class BomPreviewOut(BaseModel):
    """BOM 导入预览出参（预览不写库）。"""

    source: str = Field(description="数据源标识")
    materials: List[MaterialPreviewItemOut] = Field(default_factory=list)
    bom_items: List[BomItemPreviewOut] = Field(default_factory=list)
    errors: List[ImportErrorOut] = Field(default_factory=list)
    summary: BomImportSummaryOut


class BomConfirmOut(BaseModel):
    """BOM 导入确认出参（幂等：已存在的版本/子项跳过）。"""

    source: str = Field(description="数据源标识")
    bom_headers_created: int = Field(description="新建 BOM 头数")
    bom_items_created: int = Field(description="新建 BOM 子项数")
    skipped: int = Field(description="已存在而跳过的 BOM 头 + 子项数量")
    errors: List[ImportErrorOut] = Field(default_factory=list)