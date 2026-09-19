"""procurement 模块 Pydantic Schema。

命名约定：

- `XxxCreate` 新增入参、`XxxUpdate` 修改入参、`XxxOut` 出参（单个 / 列表项）
- 所有接口统一用 `ApiResponse[...]` 包装，分页统一使用 `PageData[...]`

采购模块错误码区段：`4000~4999`。
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.common.response import ApiResponse
from app.shared.types import HealthData

# 占位健康检查响应，与其它四个模块保持完全一致的返回结构
HealthResponse = ApiResponse[HealthData]


class _OrmBase(BaseModel):
    """允许从 ORM 对象 / 字典直接构造的出参基类。"""

    model_config = ConfigDict(from_attributes=True)


class _IdOut(_OrmBase):
    id: int = Field(description="主键")


class StatusUpdate(BaseModel):
    """通用状态流转入参。"""

    status: str = Field(description="目标状态")
    operator_id: Optional[int] = Field(default=None, description="操作人ID")


# ==================== 供应商 ====================


class SupplierCreate(BaseModel):
    """供应商新增入参。"""

    supplier_code: str = Field(max_length=50, description="供应商编码（唯一）")
    supplier_name: str = Field(max_length=100, description="供应商名称")
    contact_person: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = Field(default=None, max_length=200)
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class SupplierUpdate(BaseModel):
    """供应商修改入参。"""

    supplier_name: Optional[str] = Field(default=None, max_length=100)
    contact_person: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = Field(default=None, max_length=200)
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class SupplierOut(_IdOut):
    supplier_code: str
    supplier_name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    status: str
    remark: Optional[str] = None


# ==================== 供应商-物料关系 ====================


class SupplierMaterialCreate(BaseModel):
    """供应商-物料关系新增入参。"""

    supplier_id: int = Field(description="供应商ID")
    material_id: int = Field(description="物料ID")
    is_primary: bool = Field(default=False, description="是否主供应商")
    supply_price: Decimal = Field(default=Decimal("0"), ge=0, description="供货单价")
    lead_time_days: int = Field(default=0, ge=0, description="供货提前期（天）")
    min_order_qty: Decimal = Field(default=Decimal("0"), ge=0, description="最小起订量")
    status: Optional[str] = Field(default=None, description="状态 ACTIVE/INACTIVE")
    operator_id: Optional[int] = None


class SupplierMaterialUpdate(BaseModel):
    """供应商-物料关系修改入参。"""

    is_primary: Optional[bool] = None
    supply_price: Optional[Decimal] = Field(default=None, ge=0)
    lead_time_days: Optional[int] = Field(default=None, ge=0)
    min_order_qty: Optional[Decimal] = Field(default=None, ge=0)
    status: Optional[str] = None
    operator_id: Optional[int] = None


class SupplierMaterialOut(_IdOut):
    supplier_id: int
    supplier_name: Optional[str] = None
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    is_primary: bool
    supply_price: Decimal
    lead_time_days: int
    min_order_qty: Decimal
    status: str


# ==================== 采购材料（只读 system 物料） ====================


class PurchaseMaterialOut(BaseModel):
    """可采购物料（来自 `sys_material` 且 `supply_type == BUY`，不建采购物料表）。"""

    id: int
    material_code: str
    material_name: str
    material_type: str
    supply_type: Optional[str] = None
    unit_code: Optional[str] = None
    lead_time_days: Optional[int] = None
    safety_stock: Optional[Decimal] = None
    status: str


# ==================== 采购计划 ====================


class PlanItemCreate(BaseModel):
    """采购计划行新增入参。"""

    material_id: int = Field(description="物料ID")
    required_qty: Decimal = Field(gt=0, description="需求数量")
    required_date: date = Field(description="需求日期")
    source_type: str = Field(default="MANUAL", description="来源类型 MRP/REORDER/MANUAL")
    source_reference_id: Optional[int] = Field(default=None, description="来源单据ID")
    supplier_id: Optional[int] = Field(default=None, description="建议供应商ID")
    remark: Optional[str] = Field(default=None, max_length=200)


class PlanCreate(BaseModel):
    """采购计划新增入参（单头 + 行明细）。"""

    plan_no: Optional[str] = Field(default=None, max_length=50, description="计划编号，留空自动生成")
    plan_date: Optional[date] = Field(default=None, description="计划日期，默认今天")
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: List[PlanItemCreate] = Field(default_factory=list, description="计划行明细")


class PlanUpdate(BaseModel):
    """采购计划修改入参（仅 DRAFT；items 传入时整单替换）。"""

    plan_date: Optional[date] = None
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: Optional[List[PlanItemCreate]] = None


class PlanItemOut(_IdOut):
    plan_id: int
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    required_qty: Decimal
    ordered_qty: Decimal
    required_date: date
    source_type: str
    source_reference_id: Optional[int] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    status: str
    remark: Optional[str] = None


class PlanOut(_IdOut):
    plan_no: str
    plan_date: date
    status: str
    remark: Optional[str] = None
    items: List[PlanItemOut] = Field(default_factory=list)


# ==================== 采购订单 ====================


class OrderItemCreate(BaseModel):
    """采购订单行新增入参。"""

    material_id: int = Field(description="物料ID")
    quantity: Decimal = Field(gt=0, description="采购数量")
    unit_price: Decimal = Field(default=Decimal("0"), ge=0, description="单价")
    remark: Optional[str] = Field(default=None, max_length=200)


class OrderCreate(BaseModel):
    """采购订单新增入参（单头 + 行明细）。"""

    order_no: Optional[str] = Field(default=None, max_length=50, description="订单号，留空自动生成")
    supplier_id: int = Field(description="供应商ID")
    order_date: date = Field(description="下单日期")
    expected_date: date = Field(description="预计到货日期")
    buyer_id: Optional[int] = Field(default=None, description="采购员（sys_personnel.id）")
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: List[OrderItemCreate] = Field(default_factory=list, description="订单行明细")


class OrderUpdate(BaseModel):
    """采购订单修改入参（仅 DRAFT；items 传入时整单替换）。"""

    supplier_id: Optional[int] = None
    order_date: Optional[date] = None
    expected_date: Optional[date] = None
    buyer_id: Optional[int] = None
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: Optional[List[OrderItemCreate]] = None


class OrderFromPlanRequest(BaseModel):
    """由采购计划生成采购订单的入参。"""

    plan_id: int = Field(description="采购计划ID")
    supplier_id: int = Field(description="供应商ID")
    order_date: Optional[date] = Field(default=None, description="下单日期，默认今天")
    expected_date: Optional[date] = Field(default=None, description="预计到货日期，默认按供货提前期推算")
    buyer_id: Optional[int] = Field(default=None, description="采购员（sys_personnel.id）")
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class OrderItemOut(_IdOut):
    order_id: int
    line_no: int
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    quantity: Decimal
    received_qty: Decimal
    unit_price: Decimal
    amount: Decimal
    remark: Optional[str] = None


class OrderOut(_IdOut):
    order_no: str
    supplier_id: int
    supplier_name: Optional[str] = None
    order_date: date
    expected_date: date
    buyer_id: Optional[int] = None
    buyer_name: Optional[str] = None
    total_amount: Decimal
    status: str
    remark: Optional[str] = None
    items: List[OrderItemOut] = Field(default_factory=list)


# ==================== 到货登记 ====================


class ReceiptItemCreate(BaseModel):
    """到货行新增入参。物料由订单行带出，`material_id` 无需传入。"""

    order_item_id: int = Field(description="采购订单行ID")
    quantity: Decimal = Field(gt=0, description="到货数量")
    qualified_qty: Optional[Decimal] = Field(default=None, ge=0, description="合格数量，默认等于到货数量")
    location_id: Optional[int] = Field(default=None, description="收货库位ID")
    remark: Optional[str] = Field(default=None, max_length=200)


class ReceiptCreate(BaseModel):
    """到货单新增入参（单头 + 行明细）。"""

    receipt_no: Optional[str] = Field(default=None, max_length=50, description="到货单号，留空自动生成")
    purchase_order_id: int = Field(description="采购订单ID")
    warehouse_id: int = Field(description="收货仓库ID")
    receipt_date: date = Field(description="到货日期")
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: List[ReceiptItemCreate] = Field(default_factory=list, description="到货行明细")


class ReceiptItemOut(_IdOut):
    receipt_id: int
    order_item_id: int
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    location_id: Optional[int] = None
    quantity: Decimal
    qualified_qty: Decimal
    remark: Optional[str] = None


class ReceiptOut(_IdOut):
    receipt_no: str
    purchase_order_id: int
    order_no: Optional[str] = None
    supplier_id: int
    supplier_name: Optional[str] = None
    warehouse_id: int
    receipt_date: date
    status: str
    remark: Optional[str] = None
    items: List[ReceiptItemOut] = Field(default_factory=list)


# ==================== 供应商评价 ====================


class EvaluationCreate(BaseModel):
    """供应商评价新增入参。综合分 = 三项简单平均（四舍五入 4 位小数）。"""

    supplier_id: int = Field(description="供应商ID")
    quality_score: Decimal = Field(ge=0, le=100, description="质量评分（0~100）")
    delivery_score: Decimal = Field(ge=0, le=100, description="交期评分（0~100）")
    price_score: Decimal = Field(ge=0, le=100, description="价格评分（0~100）")
    evaluate_date: Optional[date] = Field(default=None, description="评价日期，默认今天")
    evaluator_id: Optional[int] = Field(default=None, description="评价人（sys_personnel.id）")
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class EvaluationOut(_IdOut):
    supplier_id: int
    supplier_name: Optional[str] = None
    evaluate_date: date
    quality_score: Decimal
    delivery_score: Decimal
    price_score: Decimal
    total_score: Decimal
    evaluator_id: Optional[int] = None
    evaluator_name: Optional[str] = None
    remark: Optional[str] = None


# ==================== 报表 / 统计 ====================


class PlanReportOut(BaseModel):
    """采购计划执行报表行（计划行级）。"""

    plan_id: int
    plan_no: str
    plan_date: date
    status: str
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    required_qty: Decimal
    ordered_qty: Decimal
    remaining_qty: Decimal
    required_date: date
    source_type: str


class OrderReportOut(BaseModel):
    """采购订单到货进度报表行（订单行级）。"""

    order_id: int
    order_no: str
    supplier_id: int
    supplier_name: Optional[str] = None
    order_date: date
    expected_date: date
    status: str
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    quantity: Decimal
    received_qty: Decimal
    remaining_qty: Decimal
    receipt_rate: Decimal = Field(description="到货完成率，0~1")
    unit_price: Decimal
    amount: Decimal


class ReceiptReportOut(BaseModel):
    """到货记录报表行（到货行级）。"""

    receipt_no: str
    receipt_date: date
    status: str
    order_no: Optional[str] = None
    supplier_id: int
    supplier_name: Optional[str] = None
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    warehouse_id: int
    location_id: Optional[int] = None
    quantity: Decimal
    qualified_qty: Decimal


class PendingReceiptOut(BaseModel):
    """未到货报表行：`received_qty < quantity` 的采购订单行。"""

    order_id: int
    order_no: str
    supplier_id: int
    supplier_name: Optional[str] = None
    expected_date: date
    status: str
    order_item_id: int
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    quantity: Decimal
    received_qty: Decimal
    remaining_qty: Decimal


class SupplierEvaluationOut(BaseModel):
    """供应商评分汇总行。"""

    supplier_id: int
    supplier_name: Optional[str] = None
    evaluation_count: int
    avg_total_score: Decimal
    avg_quality_score: Decimal
    avg_delivery_score: Decimal
    avg_price_score: Decimal


class ProcurementStatsOut(BaseModel):
    """采购模块统计（供 dashboard 使用）。"""

    supplier_count: int
    supplier_material_count: int
    plan_count: int
    plan_counts: Dict[str, int] = Field(default_factory=dict, description="按状态分组的计划数")
    order_count: int
    order_counts: Dict[str, int] = Field(default_factory=dict, description="按状态分组的订单数")
    pending_receipt_line_count: int = Field(description="未到货订单行数")
    receipt_count: int
    evaluation_count: int