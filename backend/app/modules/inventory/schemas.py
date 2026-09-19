"""inventory 模块 Pydantic Schema。

命名约定：

- `XxxCreate` 新增入参、`XxxUpdate` 修改入参、`XxxStatusUpdate` 状态流转入参
- `XxxOut` 出参（单个 / 列表项）
- 所有接口统一用 `ApiResponse[...]` 包装，分页统一使用 `PageData[...]`

库存模块错误码区段：`5000~5999`。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.common.response import ApiResponse
from app.shared.types import HealthData

# 占位健康检查响应，与其它四个模块保持完全一致的返回结构
HealthResponse = ApiResponse[HealthData]


class _OrmBase(BaseModel):
    """允许从 ORM 对象直接构造的出参基类。"""

    model_config = ConfigDict(from_attributes=True)


class _IdOut(_OrmBase):
    id: int = Field(description="主键")


# ==================== 仓库 ====================


class WarehouseCreate(BaseModel):
    """仓库新增入参。"""

    warehouse_code: str = Field(max_length=50, description="仓库编码")
    warehouse_name: str = Field(max_length=100, description="仓库名称")
    org_id: Optional[int] = Field(default=None, description="所属组织ID")
    manager_id: Optional[int] = Field(default=None, description="仓库负责人ID（sys_personnel.id）")
    address: Optional[str] = Field(default=None, max_length=200, description="地址")
    remark: Optional[str] = None
    operator_id: Optional[int] = Field(default=None, description="操作人ID")


class WarehouseUpdate(BaseModel):
    """仓库修改入参。"""

    warehouse_name: Optional[str] = Field(default=None, max_length=100)
    org_id: Optional[int] = None
    manager_id: Optional[int] = None
    address: Optional[str] = Field(default=None, max_length=200)
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class StatusUpdate(BaseModel):
    """通用状态流转入参。"""

    status: str = Field(description="目标状态")
    operator_id: Optional[int] = Field(default=None, description="操作人ID")


class LocationOut(_IdOut):
    location_code: str
    location_name: str
    warehouse_id: int
    status: str
    remark: Optional[str] = None


class WarehouseOut(_IdOut):
    warehouse_code: str
    warehouse_name: str
    org_id: Optional[int] = None
    manager_id: Optional[int] = None
    address: Optional[str] = None
    status: str
    remark: Optional[str] = None
    locations: List[LocationOut] = Field(default_factory=list)


# ==================== 库位 ====================


class LocationCreate(BaseModel):
    """库位新增入参。"""

    location_code: str = Field(max_length=50, description="库位编码")
    location_name: str = Field(max_length=100, description="库位名称")
    warehouse_id: int = Field(description="所属仓库ID")
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class LocationUpdate(BaseModel):
    """库位修改入参。"""

    location_name: Optional[str] = Field(default=None, max_length=100)
    remark: Optional[str] = None
    operator_id: Optional[int] = None


# ==================== 实时库存 ====================


class BalanceOut(_IdOut):
    """库存结存出参：`available_quantity = on_hand - locked_quantity`（计算得出，不落库）。"""

    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    warehouse_id: int
    warehouse_name: Optional[str] = None
    location_id: Optional[int] = None
    on_hand: Decimal
    locked_quantity: Decimal
    available_quantity: Decimal


class AvailableStockOut(BaseModel):
    """可用量查询出参（按物料/仓库汇总）。"""

    material_id: int
    warehouse_id: Optional[int] = None
    on_hand: Decimal
    locked_quantity: Decimal
    available_quantity: Decimal


# ==================== 库存流水 ====================


class TransactionOut(_IdOut):
    transaction_no: str
    transaction_type: str
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    warehouse_id: int
    location_id: Optional[int] = None
    quantity_change: Decimal
    quantity_after: Decimal
    unit_cost: Decimal
    biz_date: date
    source_module: str
    source_type: str
    source_reference_id: Optional[int] = None
    source_no: Optional[str] = None
    operator_id: Optional[int] = None
    remark: Optional[str] = None
    created_at: datetime


# ==================== 手工入 / 出库 ====================


class StockIncreaseCreate(BaseModel):
    """手工入库入参。"""

    material_id: int = Field(description="物料ID")
    warehouse_id: int = Field(description="仓库ID")
    location_id: Optional[int] = Field(default=None, description="库位ID")
    quantity: Decimal = Field(gt=0, description="入库数量（正数）")
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0, description="单位成本")
    biz_date: Optional[date] = Field(default=None, description="业务日期，缺省为当天")
    operator_id: Optional[int] = None
    remark: Optional[str] = None


class StockDecreaseCreate(BaseModel):
    """手工出库入参。"""

    material_id: int = Field(description="物料ID")
    warehouse_id: int = Field(description="仓库ID")
    location_id: Optional[int] = Field(default=None, description="库位ID")
    quantity: Decimal = Field(gt=0, description="出库数量（正数）")
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0, description="单位成本")
    biz_date: Optional[date] = Field(default=None, description="业务日期，缺省为当天")
    operator_id: Optional[int] = None
    remark: Optional[str] = None


class StockChangeOut(BaseModel):
    """库存变动结果出参。"""

    transaction_id: int
    transaction_no: str
    quantity_after: Decimal


# ==================== 移库 ====================


class TransferItemCreate(BaseModel):
    """移库明细行入参。"""

    material_id: int
    from_location_id: Optional[int] = Field(default=None, description="源库位ID")
    to_location_id: Optional[int] = Field(default=None, description="目标库位ID")
    quantity: Decimal = Field(gt=0, description="移库数量")
    remark: Optional[str] = None


class TransferCreate(BaseModel):
    """移库单新增入参（单头 + 明细）。"""

    transfer_no: Optional[str] = Field(default=None, description="移库单号，留空自动生成")
    from_warehouse_id: int = Field(description="源仓库ID")
    to_warehouse_id: int = Field(description="目标仓库ID")
    transfer_date: date = Field(description="移库日期")
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: List[TransferItemCreate] = Field(default_factory=list, description="移库明细")


class TransferItemOut(_IdOut):
    transfer_id: int
    material_id: int
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    quantity: Decimal
    remark: Optional[str] = None


class TransferOut(_IdOut):
    transfer_no: str
    from_warehouse_id: int
    to_warehouse_id: int
    transfer_date: date
    status: str
    remark: Optional[str] = None
    items: List[TransferItemOut] = Field(default_factory=list)


# ==================== 盘点 ====================


class StocktakeItemCreate(BaseModel):
    """盘点明细行入参。`book_qty` 留空时按当前结存自动带出。"""

    material_id: int
    location_id: Optional[int] = Field(default=None, description="库位ID")
    book_qty: Optional[Decimal] = Field(default=None, ge=0, description="账面数量，留空自动取当前结存")
    actual_qty: Decimal = Field(ge=0, description="实盘数量")
    remark: Optional[str] = None


class StocktakeCreate(BaseModel):
    """盘点单新增入参（单头 + 明细）。"""

    stocktake_no: Optional[str] = Field(default=None, description="盘点单号，留空自动生成")
    warehouse_id: int = Field(description="盘点仓库ID")
    stocktake_date: date = Field(description="盘点日期")
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: List[StocktakeItemCreate] = Field(default_factory=list, description="盘点明细")


class StocktakeItemOut(_IdOut):
    stocktake_id: int
    material_id: int
    location_id: Optional[int] = None
    book_qty: Decimal
    actual_qty: Decimal
    difference: Decimal
    remark: Optional[str] = None


class StocktakeOut(_IdOut):
    stocktake_no: str
    warehouse_id: int
    stocktake_date: date
    status: str
    remark: Optional[str] = None
    items: List[StocktakeItemOut] = Field(default_factory=list)


# ==================== 订货点规则 ====================


class ReorderRuleCreate(BaseModel):
    """订货点规则新增入参。"""

    material_id: int
    warehouse_id: int
    reorder_point: Decimal = Field(ge=0, description="订货点")
    reorder_quantity: Decimal = Field(ge=0, description="建议订货量")
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class ReorderRuleUpdate(BaseModel):
    """订货点规则修改入参。"""

    reorder_point: Optional[Decimal] = Field(default=None, ge=0)
    reorder_quantity: Optional[Decimal] = Field(default=None, ge=0)
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class ReorderRuleOut(_IdOut):
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    warehouse_id: int
    reorder_point: Decimal
    reorder_quantity: Decimal
    status: str
    remark: Optional[str] = None


class ReorderSuggestionOut(BaseModel):
    """补库建议：当前库存低于订货点时的建议。"""

    material_id: int
    warehouse_id: int
    reorder_point: Decimal
    current_qty: Decimal
    suggested_qty: Decimal
    target_qty: Decimal


# ==================== 补库需求 ====================


class ReplenishmentRequestCreate(BaseModel):
    """补库需求新增入参。"""

    material_id: int
    warehouse_id: int
    request_qty: Decimal = Field(gt=0, description="补库数量")
    required_date: date = Field(description="需求日期")
    source_type: str = Field(description="来源 REORDER/PRODUCTION")
    current_qty: Decimal = Field(default=Decimal("0"), ge=0, description="触发时库存量")
    target_qty: Decimal = Field(default=Decimal("0"), ge=0, description="目标库存量")
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class ReplenishmentRequestOut(_IdOut):
    request_no: str
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    warehouse_id: int
    request_qty: Decimal
    current_qty: Decimal
    target_qty: Decimal
    required_date: date
    source_type: str
    status: str
    handled_module: Optional[str] = None
    handled_ref_id: Optional[int] = None
    remark: Optional[str] = None


class GenerateFromRulesOut(BaseModel):
    """由订货点规则批量生成补库需求的结果。"""

    created_count: int = Field(description="新建补库需求单数量")
    request_ids: List[int] = Field(default_factory=list, description="新建的补库需求ID列表")
    skipped_count: int = Field(default=0, description="已存在待处理需求而跳过的数量")


# ==================== 报表 / 统计 ====================


class StockSummaryOut(BaseModel):
    """物料库存汇总（含安全库存对比）。"""

    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    on_hand: Decimal
    available_quantity: Decimal
    safety_stock: Decimal
    below_safety: bool


class LowStockOut(BaseModel):
    """低库存 / 缺料行。"""

    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    available_quantity: Decimal
    safety_stock: Decimal
    shortage_qty: Decimal


class FlowSummaryOut(BaseModel):
    """出入库汇总行。"""

    transaction_type: str
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    total_quantity: Decimal


class InventoryStatsOut(BaseModel):
    """库存模块统计（供 dashboard 使用）。"""

    warehouse_count: int
    location_count: int
    balance_count: int
    transaction_count: int
    transfer_count: int
    stocktake_count: int
    reorder_rule_count: int
    replenishment_request_count: int
    low_stock_count: int


# ==================== 课程期初库存导入（规格 §37） ====================


class InitialStockRowCreate(BaseModel):
    """期初库存导入明细行入参（数量是否合法由预览/确认统一校验并汇总为 errors）。"""

    material_code: str = Field(max_length=50, description="物料编码")
    quantity: Decimal = Field(description="导入数量（正数）")


class InitialStockImportRequest(BaseModel):
    """期初库存导入入参（显式 rows 优先；否则按 source 读取课程数据文件）。"""

    source: Optional[str] = Field(default=None, description="数据来源，如 course_chair_case")
    warehouse_id: Optional[int] = Field(default=None, description="导入仓库ID")
    warehouse_code: Optional[str] = Field(default=None, max_length=50, description="导入仓库编码")
    location_id: Optional[int] = Field(default=None, description="导入库位ID")
    rows: List[InitialStockRowCreate] = Field(default_factory=list, description="显式导入行")
    operator_id: Optional[int] = Field(default=None, description="操作人ID")


class InitialStockPreviewRowOut(BaseModel):
    """预览行：含校验状态 VALID/INVALID。"""

    material_code: str
    material_name: Optional[str] = None
    quantity: Decimal
    status: str


class InitialStockErrorOut(BaseModel):
    """导入错误行。"""

    material_code: str
    message: str


class InitialStockPreviewSummaryOut(BaseModel):
    """预览汇总：总数 / 有效 / 无效。"""

    total: int
    valid: int
    invalid: int


class InitialStockPreviewOut(BaseModel):
    """期初库存导入预览出参（不写任何数据）。"""

    rows: List[InitialStockPreviewRowOut] = Field(default_factory=list)
    errors: List[InitialStockErrorOut] = Field(default_factory=list)
    summary: InitialStockPreviewSummaryOut


class InitialStockConfirmOut(BaseModel):
    """期初库存导入确认出参：成功写入行数 + 错误行。"""

    imported: int
    errors: List[InitialStockErrorOut] = Field(default_factory=list)