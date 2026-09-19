"""sales 模块 Pydantic Schema。

命名约定：

- `XxxCreate` 新增入参、`XxxUpdate` 修改入参、`XxxStatusUpdate` 状态流转入参
- `XxxOut` 出参（单个 / 列表项）
- 所有接口统一用 `ApiResponse[...]` 包装，分页统一使用 `PageData[...]`

销售模块错误码区段：`2000~2999`。
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


# ==================== 客户 ====================


class CustomerCreate(BaseModel):
    """客户新增入参。"""

    customer_code: str = Field(max_length=50, description="客户编码")
    customer_name: str = Field(max_length=100, description="客户名称")
    contact_person: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = Field(default=None, max_length=200)
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0, description="信用额度")
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class CustomerUpdate(BaseModel):
    """客户修改入参。"""

    customer_name: Optional[str] = Field(default=None, max_length=100)
    contact_person: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = Field(default=None, max_length=200)
    credit_limit: Optional[Decimal] = Field(default=None, ge=0)
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class CustomerOut(_IdOut):
    customer_code: str
    customer_name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    credit_limit: Decimal
    status: str
    remark: Optional[str] = None


# ==================== 销售产品（只读 system 物料） ====================


class ProductOut(BaseModel):
    """可销售成品（来自 `sys_material`，不建销售产品表）。"""

    id: int
    material_code: str
    material_name: str
    material_type: str
    supply_type: Optional[str] = None
    unit_code: Optional[str] = None
    lead_time_days: Optional[int] = None
    safety_stock: Optional[Decimal] = None
    status: str


# ==================== 销售预测 ====================


class ForecastCreate(BaseModel):
    """销售预测新增入参。"""

    forecast_no: Optional[str] = Field(default=None, max_length=50, description="预测单号，留空自动生成")
    customer_id: Optional[int] = Field(default=None, description="客户ID")
    material_id: int = Field(description="物料ID")
    forecast_month: str = Field(min_length=7, max_length=7, description="预测月份 YYYY-MM")
    forecast_qty: Decimal = Field(gt=0, description="预测数量")
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class ForecastUpdate(BaseModel):
    """销售预测修改入参。"""

    customer_id: Optional[int] = None
    material_id: Optional[int] = None
    forecast_month: Optional[str] = Field(default=None, min_length=7, max_length=7)
    forecast_qty: Optional[Decimal] = Field(default=None, gt=0)
    remark: Optional[str] = None
    operator_id: Optional[int] = None


class ForecastOut(_IdOut):
    forecast_no: str
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    forecast_month: str
    forecast_qty: Decimal
    status: str
    remark: Optional[str] = None


# ==================== 销售订单 ====================


class OrderItemCreate(BaseModel):
    """订单行新增入参。"""

    material_id: int = Field(description="物料ID")
    quantity: Decimal = Field(gt=0, description="订单数量")
    unit_price: Decimal = Field(default=Decimal("0"), ge=0, description="单价")
    remark: Optional[str] = Field(default=None, max_length=200)


class OrderCreate(BaseModel):
    """销售订单新增入参（单头 + 行明细）。"""

    order_no: Optional[str] = Field(default=None, max_length=50, description="订单号，留空自动生成")
    customer_id: int = Field(description="客户ID")
    order_date: date = Field(description="订单日期")
    delivery_date: date = Field(description="要求交货日期")
    salesperson_id: Optional[int] = Field(default=None, description="销售员（sys_personnel.id）")
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: List[OrderItemCreate] = Field(default_factory=list, description="订单行明细")


class OrderUpdate(BaseModel):
    """销售订单修改入参（仅 DRAFT 可改；items 传入时整单替换）。"""

    customer_id: Optional[int] = None
    order_date: Optional[date] = None
    delivery_date: Optional[date] = None
    salesperson_id: Optional[int] = None
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: Optional[List[OrderItemCreate]] = None


class OrderItemOut(_IdOut):
    order_id: int
    line_no: int
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    quantity: Decimal
    delivered_qty: Decimal
    unit_price: Decimal
    amount: Decimal
    remark: Optional[str] = None


class OrderOut(_IdOut):
    order_no: str
    customer_id: int
    customer_name: Optional[str] = None
    order_date: date
    delivery_date: date
    salesperson_id: Optional[int] = None
    salesperson_name: Optional[str] = None
    total_amount: Decimal
    status: str
    remark: Optional[str] = None
    items: List[OrderItemOut] = Field(default_factory=list)


# ==================== 销售发货 ====================


class ShipmentItemCreate(BaseModel):
    """发货行新增入参。物料由订单行带出，`material_id` 无需传入。"""

    order_item_id: int = Field(description="销售订单行ID")
    warehouse_id: int = Field(description="发货仓库ID")
    location_id: Optional[int] = Field(default=None, description="发货库位ID")
    quantity: Decimal = Field(gt=0, description="发货数量")
    remark: Optional[str] = Field(default=None, max_length=200)


class ShipmentCreate(BaseModel):
    """销售发货单新增入参（单头 + 行明细）。"""

    shipment_no: Optional[str] = Field(default=None, max_length=50, description="发货单号，留空自动生成")
    order_id: int = Field(description="销售订单ID")
    shipment_date: date = Field(description="发货日期")
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: List[ShipmentItemCreate] = Field(default_factory=list, description="发货行明细")


class ShipmentItemOut(_IdOut):
    shipment_id: int
    order_item_id: int
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    warehouse_id: int
    location_id: Optional[int] = None
    quantity: Decimal
    remark: Optional[str] = None


class ShipmentOut(_IdOut):
    shipment_no: str
    order_id: int
    order_no: Optional[str] = None
    customer_id: int
    customer_name: Optional[str] = None
    shipment_date: date
    status: str
    remark: Optional[str] = None
    items: List[ShipmentItemOut] = Field(default_factory=list)


# ==================== 销售退货 ====================


class ReturnItemCreate(BaseModel):
    """退货行新增入参。"""

    material_id: int = Field(description="物料ID")
    warehouse_id: int = Field(description="退回仓库ID")
    location_id: Optional[int] = Field(default=None, description="退回库位ID")
    quantity: Decimal = Field(gt=0, description="退货数量")
    quality_status: str = Field(default="QUALIFIED", description="质量状态 QUALIFIED/DEFECTIVE/SCRAP")
    reason: Optional[str] = Field(default=None, max_length=200)
    remark: Optional[str] = Field(default=None, max_length=200)


class ReturnCreate(BaseModel):
    """销售退货单新增入参（单头 + 行明细）。"""

    return_no: Optional[str] = Field(default=None, max_length=50, description="退货单号，留空自动生成")
    order_id: Optional[int] = Field(default=None, description="原销售订单ID（可选）")
    customer_id: int = Field(description="客户ID")
    return_date: date = Field(description="退货日期")
    reason: Optional[str] = Field(default=None, max_length=200)
    remark: Optional[str] = None
    operator_id: Optional[int] = None
    items: List[ReturnItemCreate] = Field(default_factory=list, description="退货行明细")


class ReturnItemOut(_IdOut):
    return_id: int
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    warehouse_id: int
    location_id: Optional[int] = None
    quantity: Decimal
    quality_status: str
    reason: Optional[str] = None
    remark: Optional[str] = None


class ReturnOut(_IdOut):
    return_no: str
    order_id: Optional[int] = None
    order_no: Optional[str] = None
    customer_id: int
    customer_name: Optional[str] = None
    return_date: date
    reason: Optional[str] = None
    status: str
    remark: Optional[str] = None
    items: List[ReturnItemOut] = Field(default_factory=list)


# ==================== 报表 / 统计 ====================


class OrderStatusReportOut(BaseModel):
    """订单执行状态行。"""

    order_no: str
    customer_name: Optional[str] = None
    order_date: date
    status: str
    total_qty: Decimal
    delivered_qty: Decimal
    fulfillment_rate: Decimal = Field(description="交付完成率，0~1")


class ShipmentReportOut(BaseModel):
    """发货记录行（行级）。"""

    shipment_no: str
    order_no: Optional[str] = None
    customer_name: Optional[str] = None
    shipment_date: date
    status: str
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    warehouse_id: int
    quantity: Decimal


class ReturnReportOut(BaseModel):
    """退货记录行（行级）。"""

    return_no: str
    order_no: Optional[str] = None
    customer_name: Optional[str] = None
    return_date: date
    status: str
    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    warehouse_id: int
    quantity: Decimal
    quality_status: str


class SalesVolumeOut(BaseModel):
    """销售量按物料汇总行。"""

    material_id: int
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    total_quantity: Decimal


class SalesStatsOut(BaseModel):
    """销售模块统计（供 dashboard 使用）。"""

    customer_count: int
    order_count: int
    order_counts: Dict[str, int] = Field(default_factory=dict, description="按状态分组的订单数")
    pending_shipment_order_count: int = Field(description="未发完的订单数")
    shipment_count: int
    return_count: int