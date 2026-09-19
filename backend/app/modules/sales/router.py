"""sales 模块路由（统一前缀 `/api/v1/sales`，由 `app/main.py` 注入）。

约定：

- 路由层只做参数绑定、调用 service、提交事务，不写业务规则。
- 每个改状态的动作在 service 内写操作日志，二者同一事务；本层成功后才 `db.commit()`。
- 出参统一 `ApiResponse[...]`，分页统一 `PageData[...]`。
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.pagination import PageData, PageParams
from app.common.response import ApiResponse, success
from app.core.database import get_db
from app.modules.sales import schemas, service
from app.shared.enums import ModuleName, ModuleStatus
from app.shared.types import HealthData

router = APIRouter(tags=["sales"])


# ==================== 健康检查（占位） ====================


@router.get("/health", response_model=schemas.HealthResponse, summary="sales 模块健康检查（占位）")
def health() -> schemas.HealthResponse:
    """占位接口：只返回模块标识与状态，不含任何业务逻辑。"""
    return schemas.HealthResponse(
        data=HealthData(module=ModuleName.SALES.value, status=ModuleStatus.UP.value)
    )


# ==================== 客户 ====================


@router.get(
    "/customers",
    response_model=ApiResponse[PageData[schemas.CustomerOut]],
    summary="客户列表",
)
def list_customers(
    params: PageParams = Depends(PageParams.as_dependency),
    keyword: Optional[str] = Query(default=None, description="编码/名称关键字"),
    status: Optional[str] = Query(default=None, description="状态 ACTIVE/INACTIVE"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.CustomerOut]]:
    """分页查询客户。"""
    rows, total = service.list_customers(db, params.page, params.page_size, keyword, status)
    return success(
        PageData[schemas.CustomerOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/customers", response_model=ApiResponse[schemas.CustomerOut], summary="新增客户")
def create_customer(
    payload: schemas.CustomerCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.CustomerOut]:
    """新增客户；`customer_code` 唯一，冲突返回 2001。"""
    customer = service.create_customer(
        db,
        customer_code=payload.customer_code,
        customer_name=payload.customer_name,
        contact_person=payload.contact_person,
        phone=payload.phone,
        email=payload.email,
        address=payload.address,
        credit_limit=payload.credit_limit,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(customer)


@router.get(
    "/customers/{customer_id}",
    response_model=ApiResponse[schemas.CustomerOut],
    summary="客户详情",
)
def get_customer(
    customer_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.CustomerOut]:
    """按 ID 查询客户。"""
    return success(service.get_customer(db, customer_id))


@router.put(
    "/customers/{customer_id}",
    response_model=ApiResponse[schemas.CustomerOut],
    summary="修改客户",
)
def update_customer(
    customer_id: int,
    payload: schemas.CustomerUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.CustomerOut]:
    """修改客户基础信息。"""
    customer = service.update_customer(
        db,
        customer_id,
        customer_name=payload.customer_name,
        contact_person=payload.contact_person,
        phone=payload.phone,
        email=payload.email,
        address=payload.address,
        credit_limit=payload.credit_limit,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(customer)


@router.patch(
    "/customers/{customer_id}/status",
    response_model=ApiResponse[schemas.CustomerOut],
    summary="客户启用/停用（不物理删除）",
)
def set_customer_status(
    customer_id: int,
    payload: schemas.StatusUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.CustomerOut]:
    """客户停用 = 置 INACTIVE，从不物理删除。"""
    customer = service.set_customer_status(
        db, customer_id, payload.status, payload.operator_id
    )
    db.commit()
    return success(customer)


# ==================== 销售产品查询（只读成品物料） ====================


@router.get(
    "/products",
    response_model=ApiResponse[List[schemas.ProductOut]],
    summary="销售产品查询（FINISHED + ACTIVE 物料）",
)
def list_products(
    keyword: Optional[str] = Query(default=None, description="编码/名称关键字"),
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.ProductOut]]:
    """直接读取 `system.contract.get_finished_materials`，不建销售产品表。"""
    return success(service.list_products(db, keyword))


# ==================== 销售预测 ====================


@router.get(
    "/forecasts",
    response_model=ApiResponse[PageData[schemas.ForecastOut]],
    summary="销售预测列表",
)
def list_forecasts(
    params: PageParams = Depends(PageParams.as_dependency),
    material_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    forecast_month: Optional[str] = Query(default=None, description="预测月份 YYYY-MM"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.ForecastOut]]:
    """分页查询销售预测。"""
    rows, total = service.list_forecasts(
        db, params.page, params.page_size, material_id, status, forecast_month
    )
    return success(
        PageData[schemas.ForecastOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/forecasts", response_model=ApiResponse[schemas.ForecastOut], summary="新增销售预测")
def create_forecast(
    payload: schemas.ForecastCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ForecastOut]:
    """新增销售预测（DRAFT）。"""
    forecast = service.create_forecast(
        db,
        material_id=payload.material_id,
        forecast_month=payload.forecast_month,
        forecast_qty=payload.forecast_qty,
        customer_id=payload.customer_id,
        forecast_no=payload.forecast_no,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(forecast)


@router.put(
    "/forecasts/{forecast_id}",
    response_model=ApiResponse[schemas.ForecastOut],
    summary="修改销售预测",
)
def update_forecast(
    forecast_id: int,
    payload: schemas.ForecastUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ForecastOut]:
    """修改销售预测（COMPLETED/CANCELLED 不可改，返回 2002）。"""
    forecast = service.update_forecast(
        db,
        forecast_id,
        material_id=payload.material_id,
        forecast_month=payload.forecast_month,
        forecast_qty=payload.forecast_qty,
        customer_id=payload.customer_id,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(forecast)


@router.patch(
    "/forecasts/{forecast_id}/status",
    response_model=ApiResponse[schemas.ForecastOut],
    summary="销售预测状态流转",
)
def set_forecast_status(
    forecast_id: int,
    payload: schemas.StatusUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ForecastOut]:
    """预测状态流转（DRAFT/CONFIRMED/COMPLETED/CANCELLED）。"""
    forecast = service.set_forecast_status(
        db, forecast_id, payload.status, payload.operator_id
    )
    db.commit()
    return success(forecast)


@router.delete(
    "/forecasts/{forecast_id}",
    response_model=ApiResponse[None],
    summary="删除销售预测（仅 DRAFT）",
)
def delete_forecast(
    forecast_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """删除销售预测，仅 DRAFT 允许。"""
    service.delete_forecast(db, forecast_id, operator_id)
    db.commit()
    return success()


# ==================== 销售订单 ====================


@router.get(
    "/orders",
    response_model=ApiResponse[PageData[schemas.OrderOut]],
    summary="销售订单列表",
)
def list_orders(
    params: PageParams = Depends(PageParams.as_dependency),
    customer_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None, description="订单日期起"),
    date_to: Optional[date] = Query(default=None, description="订单日期止"),
    keyword: Optional[str] = Query(default=None, description="订单号关键字"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.OrderOut]]:
    """分页查询销售订单（含行明细）。"""
    rows, total = service.list_orders(
        db, params.page, params.page_size, customer_id, status, date_from, date_to, keyword
    )
    return success(
        PageData[schemas.OrderOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/orders", response_model=ApiResponse[schemas.OrderOut], summary="新增销售订单")
def create_order(
    payload: schemas.OrderCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.OrderOut]:
    """新增销售订单：自动计算行金额与订单总金额。"""
    order = service.create_order(
        db,
        customer_id=payload.customer_id,
        order_date=payload.order_date,
        delivery_date=payload.delivery_date,
        salesperson_id=payload.salesperson_id,
        order_no=payload.order_no,
        remark=payload.remark,
        operator_id=payload.operator_id,
        items=[item.model_dump() for item in payload.items],
    )
    db.commit()
    return success(order)


@router.get(
    "/orders/{order_id}",
    response_model=ApiResponse[schemas.OrderOut],
    summary="销售订单详情",
)
def get_order(order_id: int, db: Session = Depends(get_db)) -> ApiResponse[schemas.OrderOut]:
    """按 ID 查询订单（头 + 行）。"""
    return success(service.get_order(db, order_id))


@router.put(
    "/orders/{order_id}",
    response_model=ApiResponse[schemas.OrderOut],
    summary="修改销售订单（仅 DRAFT）",
)
def update_order(
    order_id: int,
    payload: schemas.OrderUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.OrderOut]:
    """修改销售订单，仅 DRAFT 允许；传入 items 时整单替换行。"""
    order = service.update_order(
        db,
        order_id,
        customer_id=payload.customer_id,
        order_date=payload.order_date,
        delivery_date=payload.delivery_date,
        salesperson_id=payload.salesperson_id,
        remark=payload.remark,
        operator_id=payload.operator_id,
        items=(
            [item.model_dump() for item in payload.items]
            if payload.items is not None
            else None
        ),
    )
    db.commit()
    return success(order)


@router.delete(
    "/orders/{order_id}",
    response_model=ApiResponse[None],
    summary="删除销售订单（仅 DRAFT）",
)
def delete_order(
    order_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """删除销售订单，仅 DRAFT 允许。"""
    service.delete_order(db, order_id, operator_id)
    db.commit()
    return success()


@router.patch(
    "/orders/{order_id}/status",
    response_model=ApiResponse[schemas.OrderOut],
    summary="销售订单状态流转",
)
def set_order_status(
    order_id: int,
    payload: schemas.StatusUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.OrderOut]:
    """订单状态机：DRAFT → CONFIRMED → IN_PROGRESS → COMPLETED，可自 DRAFT/CONFIRMED 取消。"""
    order = service.set_order_status(db, order_id, payload.status, payload.operator_id)
    db.commit()
    return success(order)


# ==================== 销售发货 ====================


@router.get(
    "/shipments",
    response_model=ApiResponse[PageData[schemas.ShipmentOut]],
    summary="销售发货列表",
)
def list_shipments(
    params: PageParams = Depends(PageParams.as_dependency),
    order_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.ShipmentOut]]:
    """分页查询发货单（含明细）。"""
    rows, total = service.list_shipments(db, params.page, params.page_size, order_id, status)
    return success(
        PageData[schemas.ShipmentOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/shipments", response_model=ApiResponse[schemas.ShipmentOut], summary="新增发货单")
def create_shipment(
    payload: schemas.ShipmentCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ShipmentOut]:
    """新增发货单（DRAFT）；校验订单状态与未发数量（超过返回 2003）。"""
    shipment = service.create_shipment(
        db,
        order_id=payload.order_id,
        shipment_date=payload.shipment_date,
        shipment_no=payload.shipment_no,
        remark=payload.remark,
        operator_id=payload.operator_id,
        items=[item.model_dump() for item in payload.items],
    )
    db.commit()
    return success(shipment)


@router.get(
    "/shipments/{shipment_id}",
    response_model=ApiResponse[schemas.ShipmentOut],
    summary="发货单详情",
)
def get_shipment(
    shipment_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ShipmentOut]:
    """按 ID 查询发货单。"""
    return success(service.get_shipment(db, shipment_id))


@router.post(
    "/shipments/{shipment_id}/confirm",
    response_model=ApiResponse[schemas.ShipmentOut],
    summary="确认发货（调用库存出库）",
)
def confirm_shipment(
    shipment_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ShipmentOut]:
    """确认发货：调用 `inventory.contract.decrease_stock` 扣减库存并回写已发数量。"""
    shipment = service.confirm_shipment(db, shipment_id, operator_id)
    db.commit()
    return success(shipment)


@router.post(
    "/shipments/{shipment_id}/cancel",
    response_model=ApiResponse[schemas.ShipmentOut],
    summary="取消发货单（仅 DRAFT）",
)
def cancel_shipment(
    shipment_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ShipmentOut]:
    """取消发货单，仅 DRAFT 允许。"""
    shipment = service.cancel_shipment(db, shipment_id, operator_id)
    db.commit()
    return success(shipment)


# ==================== 销售退货 ====================


@router.get(
    "/returns",
    response_model=ApiResponse[PageData[schemas.ReturnOut]],
    summary="销售退货列表",
)
def list_returns(
    params: PageParams = Depends(PageParams.as_dependency),
    order_id: Optional[int] = Query(default=None),
    customer_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.ReturnOut]]:
    """分页查询退货单（含明细）。"""
    rows, total = service.list_returns(
        db, params.page, params.page_size, order_id, customer_id, status
    )
    return success(
        PageData[schemas.ReturnOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/returns", response_model=ApiResponse[schemas.ReturnOut], summary="新增退货单")
def create_return(
    payload: schemas.ReturnCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ReturnOut]:
    """新增退货单（DRAFT）；校验订单归属客户（不一致返回 2004）。"""
    sales_return = service.create_return(
        db,
        customer_id=payload.customer_id,
        return_date=payload.return_date,
        order_id=payload.order_id,
        return_no=payload.return_no,
        reason=payload.reason,
        remark=payload.remark,
        operator_id=payload.operator_id,
        items=[item.model_dump() for item in payload.items],
    )
    db.commit()
    return success(sales_return)


@router.get(
    "/returns/{return_id}",
    response_model=ApiResponse[schemas.ReturnOut],
    summary="退货单详情",
)
def get_return(return_id: int, db: Session = Depends(get_db)) -> ApiResponse[schemas.ReturnOut]:
    """按 ID 查询退货单。"""
    return success(service.get_return(db, return_id))


@router.post(
    "/returns/{return_id}/confirm",
    response_model=ApiResponse[schemas.ReturnOut],
    summary="确认退货（调用库存入库）",
)
def confirm_return(
    return_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ReturnOut]:
    """确认退货：调用 `inventory.contract.increase_stock` 回增库存。"""
    sales_return = service.confirm_return(db, return_id, operator_id)
    db.commit()
    return success(sales_return)


@router.post(
    "/returns/{return_id}/cancel",
    response_model=ApiResponse[schemas.ReturnOut],
    summary="取消退货单（仅 DRAFT）",
)
def cancel_return(
    return_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ReturnOut]:
    """取消退货单，仅 DRAFT 允许。"""
    sales_return = service.cancel_return(db, return_id, operator_id)
    db.commit()
    return success(sales_return)


# ==================== 报表 / 统计 ====================


@router.get(
    "/reports/order-status",
    response_model=ApiResponse[List[schemas.OrderStatusReportOut]],
    summary="报表：订单执行状态",
)
def order_status_report(db: Session = Depends(get_db)) -> ApiResponse[List[schemas.OrderStatusReportOut]]:
    """订单执行状态报表（订单号 / 客户 / 日期 / 状态 / 总量 / 已发 / 完成率）。"""
    return success(service.order_status_report(db))


@router.get(
    "/reports/shipments",
    response_model=ApiResponse[List[schemas.ShipmentReportOut]],
    summary="报表：发货记录",
)
def shipments_report(
    date_from: date = Query(description="发货日期起"),
    date_to: date = Query(description="发货日期止"),
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.ShipmentReportOut]]:
    """发货记录报表（行级）。"""
    return success(service.shipments_report(db, date_from, date_to))


@router.get(
    "/reports/returns",
    response_model=ApiResponse[List[schemas.ReturnReportOut]],
    summary="报表：退货记录",
)
def returns_report(
    date_from: date = Query(description="退货日期起"),
    date_to: date = Query(description="退货日期止"),
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.ReturnReportOut]]:
    """退货记录报表（行级）。"""
    return success(service.returns_report(db, date_from, date_to))


@router.get(
    "/reports/sales-volume",
    response_model=ApiResponse[List[schemas.SalesVolumeOut]],
    summary="报表：销售量按物料汇总",
)
def sales_volume_report(
    date_from: date = Query(description="发货日期起"),
    date_to: date = Query(description="发货日期止"),
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.SalesVolumeOut]]:
    """销售量按物料汇总（已确认发货单）。"""
    return success(service.sales_volume_report(db, date_from, date_to))


@router.get("/stats", response_model=ApiResponse[schemas.SalesStatsOut], summary="销售统计")
def stats(db: Session = Depends(get_db)) -> ApiResponse[schemas.SalesStatsOut]:
    """销售模块统计（供 dashboard 使用）。"""
    return success(service.stats(db))