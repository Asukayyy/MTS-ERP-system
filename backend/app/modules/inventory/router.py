"""inventory 模块路由（统一前缀 `/api/v1/inventory`，由 `app/main.py` 注入）。

约定：
- 路由层只做参数绑定、调用 service、提交事务，不写业务规则。
- 每个改状态的动作在 service 内写操作日志，二者同一事务；本层成功后才 `db.commit()`。
- 出参统一 `ApiResponse[...]`，分页统一 `PageData[...]`。

5 张物理表：仓库（含库位文本字段）/ 结存（含订货点字段）/ 补库需求 /
库存操作单 + 操作单明细（op_type 区分 TRANSFER / STOCKTAKE）。
库存变动一律直接更新结存，不维护独立流水表。
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.pagination import PageData, PageParams
from app.common.response import ApiResponse, success
from app.core.database import get_db
from app.modules.inventory import schemas, service
from app.shared.enums import ModuleName, ModuleStatus
from app.shared.types import HealthData

router = APIRouter(tags=["inventory"])


# ==================== 健康检查（占位） ====================


@router.get("/health", response_model=schemas.HealthResponse, summary="inventory 模块健康检查（占位）")
def health() -> schemas.HealthResponse:
    """占位接口：只返回模块标识与状态，不含任何业务逻辑。"""
    return schemas.HealthResponse(
        data=HealthData(module=ModuleName.INVENTORY.value, status=ModuleStatus.UP.value)
    )


# ==================== 仓库 ====================


@router.get("/warehouses", response_model=ApiResponse[PageData[schemas.WarehouseOut]], summary="仓库列表")
def list_warehouses(
    params: PageParams = Depends(PageParams.as_dependency),
    keyword: Optional[str] = Query(default=None, description="编码/名称关键字"),
    status: Optional[str] = Query(default=None, description="状态 ACTIVE/INACTIVE"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.WarehouseOut]]:
    """分页查询仓库。"""
    rows, total = service.list_warehouses(db, params.page, params.page_size, keyword, status)
    return success(
        PageData[schemas.WarehouseOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/warehouses", response_model=ApiResponse[schemas.WarehouseOut], summary="新增仓库")
def create_warehouse(
    payload: schemas.WarehouseCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.WarehouseOut]:
    """新增仓库（库位编码/名称为文本字段，直接并入仓库表）。"""
    warehouse = service.create_warehouse(
        db,
        warehouse_code=payload.warehouse_code,
        warehouse_name=payload.warehouse_name,
        org_id=payload.org_id,
        manager_id=payload.manager_id,
        address=payload.address,
        location_code=payload.location_code,
        location_name=payload.location_name,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(warehouse)


@router.get(
    "/warehouses/{warehouse_id}",
    response_model=ApiResponse[schemas.WarehouseOut],
    summary="仓库详情",
)
def get_warehouse(
    warehouse_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.WarehouseOut]:
    """按 ID 查询仓库详情。"""
    return success(service.get_warehouse(db, warehouse_id))


@router.put(
    "/warehouses/{warehouse_id}",
    response_model=ApiResponse[schemas.WarehouseOut],
    summary="修改仓库",
)
def update_warehouse(
    warehouse_id: int, payload: schemas.WarehouseUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.WarehouseOut]:
    """修改仓库基本信息（含库位文本字段）。"""
    warehouse = service.update_warehouse(
        db,
        warehouse_id,
        warehouse_name=payload.warehouse_name,
        org_id=payload.org_id,
        manager_id=payload.manager_id,
        address=payload.address,
        location_code=payload.location_code,
        location_name=payload.location_name,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(warehouse)


@router.patch(
    "/warehouses/{warehouse_id}/status",
    response_model=ApiResponse[schemas.WarehouseOut],
    summary="启用/停用仓库",
)
def set_warehouse_status(
    warehouse_id: int, payload: schemas.StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.WarehouseOut]:
    """仓库状态流转（ACTIVE/INACTIVE，不物理删除）。"""
    warehouse = service.set_warehouse_status(
        db, warehouse_id, payload.status, payload.operator_id
    )
    db.commit()
    return success(warehouse)


# ==================== 实时库存 ====================


@router.get(
    "/balances", response_model=ApiResponse[PageData[schemas.BalanceOut]], summary="实时库存列表"
)
def list_balances(
    params: PageParams = Depends(PageParams.as_dependency),
    material_id: Optional[int] = Query(default=None, description="物料ID过滤"),
    warehouse_id: Optional[int] = Query(default=None, description="仓库ID过滤"),
    keyword: Optional[str] = Query(default=None, description="物料编码/名称关键字"),
    has_reorder_point: bool = Query(default=False, description="仅返回已配置订货点的结存"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.BalanceOut]]:
    """分页查询实时库存（含现存量/锁定量/可用量/订货点）。"""
    rows, total = service.list_balances(
        db,
        page=params.page,
        page_size=params.page_size,
        material_id=material_id,
        warehouse_id=warehouse_id,
        keyword=keyword,
        has_reorder_point=has_reorder_point,
    )
    return success(
        PageData[schemas.BalanceOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.get(
    "/balances/available",
    response_model=ApiResponse[schemas.AvailableStockOut],
    summary="可用量查询",
)
def get_available_stock(
    material_id: int = Query(..., description="物料ID"),
    warehouse_id: Optional[int] = Query(default=None, description="仓库ID，缺省为全部仓库"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.AvailableStockOut]:
    """按物料（可选仓库）查询可用量。"""
    return success(service.get_available_stock(db, material_id, warehouse_id))


@router.get(
    "/balances/reorder-suggestions",
    response_model=ApiResponse[List[schemas.ReorderSuggestionOut]],
    summary="补库建议",
)
def list_reorder_suggestions(
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.ReorderSuggestionOut]]:
    """对现存量低于订货点的结存给出补库建议。"""
    return success(service.list_reorder_suggestions(db))


@router.patch(
    "/balances/{balance_id}/reorder",
    response_model=ApiResponse[schemas.BalanceOut],
    summary="更新结存订货点",
)
def update_balance_reorder(
    balance_id: int, payload: schemas.BalanceReorderUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.BalanceOut]:
    """直接维护结存上的订货点 / 建议订货量。"""
    result = service.update_balance_reorder(
        db,
        balance_id,
        reorder_point=payload.reorder_point,
        reorder_quantity=payload.reorder_quantity,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(result)


# ==================== 库存流水（已删除独立流水表，变动记录见库存操作单） ====================
# inv_transaction 表已删除，库存变动记录通过 /stock-operations 查询移库/盘点单据。


# ==================== 手工入 / 出库 ====================


@router.post(
    "/stock/increase", response_model=ApiResponse[schemas.StockChangeOut], summary="手工入库"
)
def stock_increase(
    payload: schemas.StockIncreaseCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.StockChangeOut]:
    """手工入库（source_type=MANUAL）。"""
    result = service.increase_stock(
        db,
        material_id=payload.material_id,
        quantity=payload.quantity,
        warehouse_id=payload.warehouse_id,
        source_module="inventory",
        source_type="MANUAL",
        unit_cost=payload.unit_cost,
        biz_date=payload.biz_date,
        operator_id=payload.operator_id,
        remark=payload.remark,
    )
    db.commit()
    return success(result)


@router.post(
    "/stock/decrease", response_model=ApiResponse[schemas.StockChangeOut], summary="手工出库"
)
def stock_decrease(
    payload: schemas.StockDecreaseCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.StockChangeOut]:
    """手工出库（source_type=MANUAL，库存不足返回 5001）。"""
    result = service.decrease_stock(
        db,
        material_id=payload.material_id,
        quantity=payload.quantity,
        warehouse_id=payload.warehouse_id,
        source_module="inventory",
        source_type="MANUAL",
        unit_cost=payload.unit_cost,
        biz_date=payload.biz_date,
        operator_id=payload.operator_id,
        remark=payload.remark,
    )
    db.commit()
    return success(result)


# ==================== 库存操作单（移库 / 盘点） ====================


@router.get(
    "/stock-operations",
    response_model=ApiResponse[PageData[schemas.StockOperationOut]],
    summary="库存操作单列表（op_type=TRANSFER/STOCKTAKE）",
)
def list_stock_operations(
    params: PageParams = Depends(PageParams.as_dependency),
    op_type: Optional[str] = Query(default=None, description="TRANSFER/STOCKTAKE"),
    status: Optional[str] = Query(default=None, description="DRAFT/COMPLETED/CANCELLED"),
    warehouse_id: Optional[int] = Query(default=None, description="涉及仓库ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.StockOperationOut]]:
    """分页查询库存操作单（移库与盘点合并，按 op_type 区分）。"""
    rows, total = service.list_stock_operations(
        db, params.page, params.page_size, op_type, status, warehouse_id
    )
    return success(
        PageData[schemas.StockOperationOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/stock-operations",
    response_model=ApiResponse[schemas.StockOperationOut],
    summary="新增库存操作单",
)
def create_stock_operation(
    payload: schemas.StockOperationCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.StockOperationOut]:
    """新增库存操作单：op_type=TRANSFER 需源/目标仓库；STOCKTAKE 需仓库。

    盘点明细的 book_qty 留空时按当前结存自动带出。
    """
    operation = service.create_stock_operation(
        db,
        op_type=payload.op_type,
        op_date=payload.op_date,
        items=[item.model_dump() for item in payload.items],
        operation_no=payload.operation_no,
        from_warehouse_id=payload.from_warehouse_id,
        to_warehouse_id=payload.to_warehouse_id,
        warehouse_id=payload.warehouse_id,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(operation)


@router.get(
    "/stock-operations/{operation_id}",
    response_model=ApiResponse[schemas.StockOperationOut],
    summary="库存操作单详情",
)
def get_stock_operation(
    operation_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.StockOperationOut]:
    """按 ID 查询库存操作单（含明细）。"""
    return success(service.get_stock_operation(db, operation_id))


@router.post(
    "/stock-operations/{operation_id}/confirm",
    response_model=ApiResponse[schemas.StockOperationOut],
    summary="确认库存操作单",
)
def confirm_stock_operation(
    operation_id: int,
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.StockOperationOut]:
    """确认执行：TRANSFER 更新调出/调入两边结存；STOCKTAKE 按盘盈/盘亏差异调整结存。

    状态 → COMPLETED；库存不足返回 5001，整单不改动任何结存。
    """
    operation = service.confirm_stock_operation(db, operation_id, operator_id)
    db.commit()
    return success(operation)


@router.post(
    "/stock-operations/{operation_id}/cancel",
    response_model=ApiResponse[schemas.StockOperationOut],
    summary="取消库存操作单",
)
def cancel_stock_operation(
    operation_id: int,
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.StockOperationOut]:
    """取消库存操作单（仅 DRAFT 可取消）。"""
    operation = service.cancel_stock_operation(db, operation_id, operator_id)
    db.commit()
    return success(operation)


# ==================== 补库需求 ====================


@router.get(
    "/replenishment-requests",
    response_model=ApiResponse[PageData[schemas.ReplenishmentRequestOut]],
    summary="补库需求列表",
)
def list_replenishment_requests(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = Query(default=None, description="状态"),
    source_type: Optional[str] = Query(default=None, description="来源 REORDER/PRODUCTION"),
    material_id: Optional[int] = Query(default=None, description="物料ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.ReplenishmentRequestOut]]:
    """分页查询补库需求单。"""
    rows, total = service.list_replenishment_requests(
        db,
        page=params.page,
        page_size=params.page_size,
        status=status,
        source_type=source_type,
        material_id=material_id,
    )
    return success(
        PageData[schemas.ReplenishmentRequestOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post(
    "/replenishment-requests/generate-from-reorder-rules",
    response_model=ApiResponse[schemas.GenerateFromRulesOut],
    summary="按订货点批量生成补库需求",
)
def generate_from_reorder_rules(
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.GenerateFromRulesOut]:
    """按订货点建议批量创建 DRAFT 的 REORDER 补库需求。"""
    result = service.generate_from_reorder_rules(db, operator_id)
    db.commit()
    return success(result)


@router.post(
    "/replenishment-requests",
    response_model=ApiResponse[schemas.ReplenishmentRequestOut],
    summary="新增补库需求",
)
def create_replenishment_request(
    payload: schemas.ReplenishmentRequestCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ReplenishmentRequestOut]:
    """新增补库需求单（不直接创建正式计划）。"""
    created = service.create_replenishment_request(
        db,
        material_id=payload.material_id,
        warehouse_id=payload.warehouse_id,
        request_qty=payload.request_qty,
        required_date=payload.required_date,
        source_type=payload.source_type,
        current_qty=payload.current_qty,
        target_qty=payload.target_qty,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(service.get_replenishment_request(db, created["id"]))


@router.get(
    "/replenishment-requests/{request_id}",
    response_model=ApiResponse[schemas.ReplenishmentRequestOut],
    summary="补库需求详情",
)
def get_replenishment_request(
    request_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ReplenishmentRequestOut]:
    """按 ID 查询补库需求。"""
    return success(service.get_replenishment_request(db, request_id))


@router.post(
    "/replenishment-requests/{request_id}/confirm",
    response_model=ApiResponse[schemas.ReplenishmentRequestOut],
    summary="确认补库需求",
)
def confirm_replenishment_request(
    request_id: int,
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ReplenishmentRequestOut]:
    """确认补库需求：转交 procurement / planning 契约创建正式计划。"""
    request = service.confirm_replenishment_request(db, request_id, operator_id)
    db.commit()
    return success(request)


@router.post(
    "/replenishment-requests/{request_id}/cancel",
    response_model=ApiResponse[schemas.ReplenishmentRequestOut],
    summary="取消补库需求",
)
def cancel_replenishment_request(
    request_id: int,
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.ReplenishmentRequestOut]:
    """取消补库需求（DRAFT/CONFIRMED 可取消）。"""
    request = service.cancel_replenishment_request(db, request_id, operator_id)
    db.commit()
    return success(request)


# ==================== 报表 / 统计 ====================


@router.get(
    "/reports/stock-summary",
    response_model=ApiResponse[List[schemas.StockSummaryOut]],
    summary="库存汇总报表",
)
def stock_summary_report(
    warehouse_id: Optional[int] = Query(default=None, description="仓库ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.StockSummaryOut]]:
    """按物料汇总库存并与安全库存对比。"""
    return success(service.stock_summary(db, warehouse_id))


@router.get(
    "/reports/low-stock",
    response_model=ApiResponse[List[schemas.LowStockOut]],
    summary="低库存/缺料报表",
)
def low_stock_report(db: Session = Depends(get_db)) -> ApiResponse[List[schemas.LowStockOut]]:
    """可用量低于安全库存的物料（缺料预警）。"""
    return success(service.low_stock_report(db))


@router.get(
    "/reports/flow-summary",
    response_model=ApiResponse[List[schemas.FlowSummaryOut]],
    summary="出入库汇总报表",
)
def flow_summary_report(
    date_from: date = Query(..., description="业务日期起"),
    date_to: date = Query(..., description="业务日期止"),
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.FlowSummaryOut]]:
    """按操作类型 + 物料统计出入库数量（数据源为库存操作单）。"""
    return success(service.flow_summary(db, date_from, date_to))


@router.get("/stats", response_model=ApiResponse[schemas.InventoryStatsOut], summary="库存模块统计")
def inventory_stats(db: Session = Depends(get_db)) -> ApiResponse[schemas.InventoryStatsOut]:
    """库存模块统计（dashboard 使用）。"""
    return success(service.stats(db))


# ==================== 课程期初库存导入（规格 §37） ====================


@router.post(
    "/import/initial-stock/preview",
    response_model=ApiResponse[schemas.InitialStockPreviewOut],
    summary="期初库存导入预览",
)
def preview_initial_stock_import(
    payload: schemas.InitialStockImportRequest, db: Session = Depends(get_db)
) -> ApiResponse[schemas.InitialStockPreviewOut]:
    """期初库存导入预览：只校验并返回逐行状态与错误，**不写任何数据**。"""
    result = service.preview_initial_stock_import(
        db,
        source=payload.source,
        warehouse_id=payload.warehouse_id,
        warehouse_code=payload.warehouse_code,
        rows=[row.model_dump() for row in payload.rows],
    )
    return success(result)


@router.post(
    "/import/initial-stock/confirm",
    response_model=ApiResponse[schemas.InitialStockConfirmOut],
    summary="期初库存导入确认",
)
def confirm_initial_stock_import(
    payload: schemas.InitialStockImportRequest, db: Session = Depends(get_db)
) -> ApiResponse[schemas.InitialStockConfirmOut]:
    """确认期初库存导入：重新校验后逐行走 `increase_stock` 直接更新结存，同一事务提交。"""
    result = service.confirm_initial_stock_import(
        db,
        source=payload.source,
        warehouse_id=payload.warehouse_id,
        warehouse_code=payload.warehouse_code,
        rows=[row.model_dump() for row in payload.rows],
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(result)
