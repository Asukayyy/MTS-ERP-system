"""procurement 模块路由（统一前缀 `/api/v1/procurement`，由 `app/main.py` 注入）。

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
from app.modules.procurement import schemas, service
from app.shared.enums import ModuleName, ModuleStatus
from app.shared.types import HealthData

router = APIRouter(tags=["procurement"])


# ==================== 健康检查（占位） ====================


@router.get("/health", response_model=schemas.HealthResponse, summary="procurement 模块健康检查")
def health() -> schemas.HealthResponse:
    """占位接口：只返回模块标识与状态，不含任何业务逻辑。"""
    return schemas.HealthResponse(
        data=HealthData(module=ModuleName.PROCUREMENT.value, status=ModuleStatus.UP.value)
    )


# ==================== 供应商 ====================


@router.get(
    "/suppliers",
    response_model=ApiResponse[PageData[schemas.SupplierOut]],
    summary="供应商列表",
)
def list_suppliers(
    params: PageParams = Depends(PageParams.as_dependency),
    keyword: Optional[str] = Query(default=None, description="编码/名称关键字"),
    status: Optional[str] = Query(default=None, description="状态 ACTIVE/INACTIVE"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.SupplierOut]]:
    """分页查询供应商。"""
    rows, total = service.list_suppliers(db, params.page, params.page_size, keyword, status)
    return success(
        PageData[schemas.SupplierOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/suppliers", response_model=ApiResponse[schemas.SupplierOut], summary="新增供应商"
)
def create_supplier(
    payload: schemas.SupplierCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.SupplierOut]:
    """新增供应商；`supplier_code` 唯一，冲突返回 4001。"""
    supplier = service.create_supplier(
        db,
        supplier_code=payload.supplier_code,
        supplier_name=payload.supplier_name,
        contact_person=payload.contact_person,
        phone=payload.phone,
        email=payload.email,
        address=payload.address,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(supplier)


@router.get(
    "/suppliers/{supplier_id}",
    response_model=ApiResponse[schemas.SupplierOut],
    summary="供应商详情",
)
def get_supplier(
    supplier_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.SupplierOut]:
    """按 ID 查询供应商。"""
    return success(service.get_supplier(db, supplier_id))


@router.put(
    "/suppliers/{supplier_id}",
    response_model=ApiResponse[schemas.SupplierOut],
    summary="修改供应商",
)
def update_supplier(
    supplier_id: int,
    payload: schemas.SupplierUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.SupplierOut]:
    """修改供应商基础信息。"""
    supplier = service.update_supplier(
        db,
        supplier_id,
        supplier_name=payload.supplier_name,
        contact_person=payload.contact_person,
        phone=payload.phone,
        email=payload.email,
        address=payload.address,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(supplier)


@router.patch(
    "/suppliers/{supplier_id}/status",
    response_model=ApiResponse[schemas.SupplierOut],
    summary="供应商启用/停用（不物理删除）",
)
def set_supplier_status(
    supplier_id: int,
    payload: schemas.StatusUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.SupplierOut]:
    """供应商停用 = 置 INACTIVE，从不物理删除。"""
    supplier = service.set_supplier_status(
        db, supplier_id, payload.status, payload.operator_id
    )
    db.commit()
    return success(supplier)


# ==================== 供应商-物料关系 ====================


@router.get(
    "/supplier-materials",
    response_model=ApiResponse[PageData[schemas.SupplierMaterialOut]],
    summary="供应商-物料关系列表",
)
def list_supplier_materials(
    params: PageParams = Depends(PageParams.as_dependency),
    supplier_id: Optional[int] = Query(default=None),
    material_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.SupplierMaterialOut]]:
    """分页查询供应商-物料供货关系。"""
    rows, total = service.list_supplier_materials(
        db, params.page, params.page_size, supplier_id, material_id
    )
    return success(
        PageData[schemas.SupplierMaterialOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/supplier-materials",
    response_model=ApiResponse[schemas.SupplierMaterialOut],
    summary="新增供应商-物料关系",
)
def create_supplier_material(
    payload: schemas.SupplierMaterialCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.SupplierMaterialOut]:
    """新增供应商-物料关系；`(supplier_id, material_id)` 唯一，冲突返回 4002。"""
    link = service.create_supplier_material(
        db,
        supplier_id=payload.supplier_id,
        material_id=payload.material_id,
        is_primary=payload.is_primary,
        supply_price=payload.supply_price,
        lead_time_days=payload.lead_time_days,
        min_order_qty=payload.min_order_qty,
        status=payload.status,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(link)


@router.put(
    "/supplier-materials/{link_id}",
    response_model=ApiResponse[schemas.SupplierMaterialOut],
    summary="修改供应商-物料关系",
)
def update_supplier_material(
    link_id: int,
    payload: schemas.SupplierMaterialUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.SupplierMaterialOut]:
    """修改供货价 / 提前期 / 主供应商等。"""
    link = service.update_supplier_material(
        db,
        link_id,
        is_primary=payload.is_primary,
        supply_price=payload.supply_price,
        lead_time_days=payload.lead_time_days,
        min_order_qty=payload.min_order_qty,
        status=payload.status,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(link)


@router.delete(
    "/supplier-materials/{link_id}",
    response_model=ApiResponse[None],
    summary="删除供应商-物料关系",
)
def delete_supplier_material(
    link_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """删除供应商-物料关系。"""
    service.delete_supplier_material(db, link_id, operator_id)
    db.commit()
    return success()


# ==================== 采购材料查询（只读物料主数据） ====================


@router.get(
    "/materials",
    response_model=ApiResponse[List[schemas.PurchaseMaterialOut]],
    summary="采购材料查询（supply_type = BUY 的物料）",
)
def list_purchase_materials(
    keyword: Optional[str] = Query(default=None, description="编码/名称关键字"),
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.PurchaseMaterialOut]]:
    """直接读取 `system.contract.search_materials` 并过滤 `supply_type == BUY`。"""
    return success(service.list_purchase_materials(db, keyword))


# ==================== 采购计划 ====================


@router.get(
    "/purchase-plans",
    response_model=ApiResponse[PageData[schemas.PlanOut]],
    summary="采购计划列表",
)
def list_plans(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None, description="计划日期起"),
    date_to: Optional[date] = Query(default=None, description="计划日期止"),
    keyword: Optional[str] = Query(default=None, description="计划编号关键字"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.PlanOut]]:
    """分页查询采购计划（含行明细）。"""
    rows, total = service.list_plans(
        db, params.page, params.page_size, status, date_from, date_to, keyword
    )
    return success(
        PageData[schemas.PlanOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/purchase-plans",
    response_model=ApiResponse[schemas.PlanOut],
    summary="新增采购计划（头 + 行）",
)
def create_plan(
    payload: schemas.PlanCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.PlanOut]:
    """新增采购计划；行来源 MRP/REORDER/MANUAL。"""
    plan = service.create_plan(
        db,
        plan_date=payload.plan_date,
        plan_no=payload.plan_no,
        remark=payload.remark,
        operator_id=payload.operator_id,
        items=[item.model_dump() for item in payload.items],
    )
    db.commit()
    return success(plan)


@router.get(
    "/purchase-plans/{plan_id}",
    response_model=ApiResponse[schemas.PlanOut],
    summary="采购计划详情",
)
def get_plan(plan_id: int, db: Session = Depends(get_db)) -> ApiResponse[schemas.PlanOut]:
    """按 ID 查询采购计划（头 + 行）。"""
    return success(service.get_plan(db, plan_id))


@router.put(
    "/purchase-plans/{plan_id}",
    response_model=ApiResponse[schemas.PlanOut],
    summary="修改采购计划（仅 DRAFT）",
)
def update_plan(
    plan_id: int,
    payload: schemas.PlanUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.PlanOut]:
    """修改采购计划，仅 DRAFT 允许；已确认/已下达计划只读（4003）。"""
    plan = service.update_plan(
        db,
        plan_id,
        plan_date=payload.plan_date,
        remark=payload.remark,
        operator_id=payload.operator_id,
        items=(
            [item.model_dump() for item in payload.items]
            if payload.items is not None
            else None
        ),
    )
    db.commit()
    return success(plan)


@router.delete(
    "/purchase-plans/{plan_id}",
    response_model=ApiResponse[None],
    summary="删除采购计划（仅 DRAFT）",
)
def delete_plan(
    plan_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """删除采购计划，仅 DRAFT 允许。"""
    service.delete_plan(db, plan_id, operator_id)
    db.commit()
    return success()


@router.patch(
    "/purchase-plans/{plan_id}/status",
    response_model=ApiResponse[schemas.PlanOut],
    summary="采购计划状态流转",
)
def set_plan_status(
    plan_id: int,
    payload: schemas.StatusUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.PlanOut]:
    """计划状态机：DRAFT → CONFIRMED → RELEASED → COMPLETED，可自非终态取消。"""
    plan = service.set_plan_status(db, plan_id, payload.status, payload.operator_id)
    db.commit()
    return success(plan)


# ==================== 采购订单 ====================


@router.get(
    "/orders",
    response_model=ApiResponse[PageData[schemas.OrderOut]],
    summary="采购订单列表",
)
def list_orders(
    params: PageParams = Depends(PageParams.as_dependency),
    supplier_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None, description="下单日期起"),
    date_to: Optional[date] = Query(default=None, description="下单日期止"),
    keyword: Optional[str] = Query(default=None, description="订单号关键字"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.OrderOut]]:
    """分页查询采购订单（含行明细）。"""
    rows, total = service.list_orders(
        db, params.page, params.page_size, supplier_id, status, date_from, date_to, keyword
    )
    return success(
        PageData[schemas.OrderOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/orders", response_model=ApiResponse[schemas.OrderOut], summary="新增采购订单"
)
def create_order(
    payload: schemas.OrderCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.OrderOut]:
    """新增采购订单：自动计算行金额 `quantity × unit_price` 与订单总金额。"""
    order = service.create_order(
        db,
        supplier_id=payload.supplier_id,
        order_date=payload.order_date,
        expected_date=payload.expected_date,
        buyer_id=payload.buyer_id,
        order_no=payload.order_no,
        remark=payload.remark,
        operator_id=payload.operator_id,
        items=[item.model_dump() for item in payload.items],
    )
    db.commit()
    return success(order)


@router.post(
    "/orders/from-plan",
    response_model=ApiResponse[schemas.OrderOut],
    summary="由采购计划生成采购订单",
)
def create_order_from_plan(
    payload: schemas.OrderFromPlanRequest, db: Session = Depends(get_db)
) -> ApiResponse[schemas.OrderOut]:
    """按计划行生成 DRAFT 订单（单价取供应商供货价），并回写计划行已下单数量。"""
    order = service.create_order_from_plan(
        db,
        plan_id=payload.plan_id,
        supplier_id=payload.supplier_id,
        order_date=payload.order_date,
        expected_date=payload.expected_date,
        buyer_id=payload.buyer_id,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(order)


@router.get(
    "/orders/{order_id}",
    response_model=ApiResponse[schemas.OrderOut],
    summary="采购订单详情",
)
def get_order(order_id: int, db: Session = Depends(get_db)) -> ApiResponse[schemas.OrderOut]:
    """按 ID 查询采购订单（头 + 行）。"""
    return success(service.get_order(db, order_id))


@router.put(
    "/orders/{order_id}",
    response_model=ApiResponse[schemas.OrderOut],
    summary="修改采购订单（仅 DRAFT）",
)
def update_order(
    order_id: int,
    payload: schemas.OrderUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.OrderOut]:
    """修改采购订单，仅 DRAFT 允许；传入 items 时整单替换行。"""
    order = service.update_order(
        db,
        order_id,
        supplier_id=payload.supplier_id,
        order_date=payload.order_date,
        expected_date=payload.expected_date,
        buyer_id=payload.buyer_id,
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
    summary="删除采购订单（仅 DRAFT）",
)
def delete_order(
    order_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """删除采购订单，仅 DRAFT 允许。"""
    service.delete_order(db, order_id, operator_id)
    db.commit()
    return success()


@router.patch(
    "/orders/{order_id}/status",
    response_model=ApiResponse[schemas.OrderOut],
    summary="采购订单状态流转",
)
def set_order_status(
    order_id: int,
    payload: schemas.StatusUpdate,
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.OrderOut]:
    """订单状态机：DRAFT → CONFIRMED → RELEASED → IN_PROGRESS → COMPLETED，可自非终态取消。"""
    order = service.set_order_status(db, order_id, payload.status, payload.operator_id)
    db.commit()
    return success(order)


# ==================== 到货登记 ====================


@router.get(
    "/receipts",
    response_model=ApiResponse[PageData[schemas.ReceiptOut]],
    summary="到货登记列表",
)
def list_receipts(
    params: PageParams = Depends(PageParams.as_dependency),
    purchase_order_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.ReceiptOut]]:
    """分页查询到货单（含明细）。"""
    rows, total = service.list_receipts(
        db, params.page, params.page_size, purchase_order_id, status
    )
    return success(
        PageData[schemas.ReceiptOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/receipts", response_model=ApiResponse[schemas.ReceiptOut], summary="新增到货登记"
)
def create_receipt(
    payload: schemas.ReceiptCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ReceiptOut]:
    """新增到货单（DRAFT）；到货数量超过未到货数量返回 4004。"""
    receipt = service.create_receipt(
        db,
        purchase_order_id=payload.purchase_order_id,
        warehouse_id=payload.warehouse_id,
        receipt_date=payload.receipt_date,
        receipt_no=payload.receipt_no,
        remark=payload.remark,
        operator_id=payload.operator_id,
        items=[item.model_dump() for item in payload.items],
    )
    db.commit()
    return success(receipt)


@router.get(
    "/receipts/{receipt_id}",
    response_model=ApiResponse[schemas.ReceiptOut],
    summary="到货单详情",
)
def get_receipt(
    receipt_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ReceiptOut]:
    """按 ID 查询到货单。"""
    return success(service.get_receipt(db, receipt_id))


@router.post(
    "/receipts/{receipt_id}/confirm",
    response_model=ApiResponse[schemas.ReceiptOut],
    summary="确认到货（调用库存入库）",
)
def confirm_receipt(
    receipt_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ReceiptOut]:
    """确认到货：调用 `inventory.contract.increase_stock` 写 PURCHASE_RECEIPT 流水并回写已到货数量。"""
    receipt = service.confirm_receipt(db, receipt_id, operator_id)
    db.commit()
    return success(receipt)


@router.post(
    "/receipts/{receipt_id}/cancel",
    response_model=ApiResponse[schemas.ReceiptOut],
    summary="取消到货单（仅 DRAFT）",
)
def cancel_receipt(
    receipt_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ReceiptOut]:
    """取消到货单，仅 DRAFT 允许。"""
    receipt = service.cancel_receipt(db, receipt_id, operator_id)
    db.commit()
    return success(receipt)


# ==================== 供应商评价 ====================


@router.get(
    "/evaluations",
    response_model=ApiResponse[PageData[schemas.EvaluationOut]],
    summary="供应商评价列表",
)
def list_evaluations(
    params: PageParams = Depends(PageParams.as_dependency),
    supplier_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.EvaluationOut]]:
    """分页查询供应商评价。"""
    rows, total = service.list_evaluations(db, params.page, params.page_size, supplier_id)
    return success(
        PageData[schemas.EvaluationOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/evaluations",
    response_model=ApiResponse[schemas.EvaluationOut],
    summary="新增供应商评价",
)
def create_evaluation(
    payload: schemas.EvaluationCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.EvaluationOut]:
    """新增评价；`total_score` = 三项评分简单平均（四舍五入 4 位小数）。"""
    evaluation = service.create_evaluation(
        db,
        supplier_id=payload.supplier_id,
        quality_score=payload.quality_score,
        delivery_score=payload.delivery_score,
        price_score=payload.price_score,
        evaluate_date=payload.evaluate_date,
        evaluator_id=payload.evaluator_id,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(evaluation)


@router.get(
    "/evaluations/supplier/{supplier_id}",
    response_model=ApiResponse[List[schemas.EvaluationOut]],
    summary="某供应商的评价记录",
)
def list_evaluations_by_supplier(
    supplier_id: int, db: Session = Depends(get_db)
) -> ApiResponse[List[schemas.EvaluationOut]]:
    """按供应商查询全部评价记录。"""
    return success(service.list_evaluations_by_supplier(db, supplier_id))


@router.delete(
    "/evaluations/{evaluation_id}",
    response_model=ApiResponse[None],
    summary="删除供应商评价",
)
def delete_evaluation(
    evaluation_id: int,
    operator_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """删除供应商评价。"""
    service.delete_evaluation(db, evaluation_id, operator_id)
    db.commit()
    return success()


# ==================== 报表 / 统计 ====================


@router.get(
    "/reports/plans",
    response_model=ApiResponse[List[schemas.PlanReportOut]],
    summary="报表：采购计划及执行",
)
def plan_report(db: Session = Depends(get_db)) -> ApiResponse[List[schemas.PlanReportOut]]:
    """采购计划执行报表（required_qty vs ordered_qty）。"""
    return success(service.plan_report(db))


@router.get(
    "/reports/orders",
    response_model=ApiResponse[List[schemas.OrderReportOut]],
    summary="报表：采购订单及到货进度",
)
def order_report(db: Session = Depends(get_db)) -> ApiResponse[List[schemas.OrderReportOut]]:
    """采购订单到货进度报表（行级）。"""
    return success(service.order_report(db))


@router.get(
    "/reports/receipts",
    response_model=ApiResponse[List[schemas.ReceiptReportOut]],
    summary="报表：到货记录",
)
def receipt_report(
    date_from: date = Query(description="到货日期起"),
    date_to: date = Query(description="到货日期止"),
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.ReceiptReportOut]]:
    """到货记录报表（行级）。"""
    return success(service.receipt_report(db, date_from, date_to))


@router.get(
    "/reports/pending",
    response_model=ApiResponse[List[schemas.PendingReceiptOut]],
    summary="报表：未到货",
)
def pending_receipt_report(
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.PendingReceiptOut]]:
    """未到货报表：`received_qty < quantity` 的采购订单行。"""
    return success(service.pending_receipt_report(db))


@router.get(
    "/reports/supplier-evaluation",
    response_model=ApiResponse[List[schemas.SupplierEvaluationOut]],
    summary="报表：供应商评分汇总",
)
def supplier_evaluation_report(
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.SupplierEvaluationOut]]:
    """供应商评分汇总报表。"""
    return success(service.supplier_evaluation_report(db))


@router.get("/stats", response_model=ApiResponse[schemas.ProcurementStatsOut], summary="采购统计")
def stats(db: Session = Depends(get_db)) -> ApiResponse[schemas.ProcurementStatsOut]:
    """采购模块统计（供 dashboard 使用）。"""
    return success(service.stats(db))