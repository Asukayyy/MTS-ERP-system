"""inventory 模块路由（统一前缀 `/api/v1/inventory`，由 `app/main.py` 注入）。

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
    """新增仓库。"""
    warehouse = service.create_warehouse(
        db,
        warehouse_code=payload.warehouse_code,
        warehouse_name=payload.warehouse_name,
        org_id=payload.org_id,
        manager_id=payload.manager_id,
        address=payload.address,
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
    """按 ID 查询仓库详情（含库位）。"""
    return success(service.get_warehouse(db, warehouse_id))


@router.put(
    "/warehouses/{warehouse_id}",
    response_model=ApiResponse[schemas.WarehouseOut],
    summary="修改仓库",
)
def update_warehouse(
    warehouse_id: int, payload: schemas.WarehouseUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.WarehouseOut]:
    """修改仓库基本信息。"""
    warehouse = service.update_warehouse(
        db,
        warehouse_id,
        warehouse_name=payload.warehouse_name,
        org_id=payload.org_id,
        manager_id=payload.manager_id,
        address=payload.address,
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


# ==================== 库位 ====================


@router.get("/locations", response_model=ApiResponse[PageData[schemas.LocationOut]], summary="库位列表")
def list_locations(
    params: PageParams = Depends(PageParams.as_dependency),
    warehouse_id: Optional[int] = Query(default=None, description="仓库ID过滤"),
    keyword: Optional[str] = Query(default=None, description="编码/名称关键字"),
    status: Optional[str] = Query(default=None, description="状态"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.LocationOut]]:
    """分页查询库位。"""
    rows, total = service.list_locations(
        db, params.page, params.page_size, warehouse_id, keyword, status
    )
    return success(
        PageData[schemas.LocationOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/locations", response_model=ApiResponse[schemas.LocationOut], summary="新增库位")
def create_location(
    payload: schemas.LocationCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.LocationOut]:
    """新增库位（同一仓库下编码唯一）。"""
    location = service.create_location(
        db,
        location_code=payload.location_code,
        location_name=payload.location_name,
        warehouse_id=payload.warehouse_id,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(location)


@router.put(
    "/locations/{location_id}", response_model=ApiResponse[schemas.LocationOut], summary="修改库位"
)
def update_location(
    location_id: int, payload: schemas.LocationUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.LocationOut]:
    """修改库位。"""
    location = service.update_location(
        db,
        location_id,
        location_name=payload.location_name,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(location)


@router.delete(
    "/locations/{location_id}", response_model=ApiResponse[dict], summary="删除库位"
)
def delete_location(
    location_id: int,
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """删除库位（已被库存引用的库位禁止删除）。"""
    service.delete_location(db, location_id, operator_id)
    db.commit()
    return success({"deleted": location_id})


@router.patch(
    "/locations/{location_id}/status",
    response_model=ApiResponse[schemas.LocationOut],
    summary="启用/停用库位",
)
def set_location_status(
    location_id: int, payload: schemas.StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.LocationOut]:
    """库位状态流转。"""
    location = service.set_location_status(db, location_id, payload.status, payload.operator_id)
    db.commit()
    return success(location)


# ==================== 实时库存 ====================


@router.get(
    "/balances", response_model=ApiResponse[PageData[schemas.BalanceOut]], summary="实时库存列表"
)
def list_balances(
    params: PageParams = Depends(PageParams.as_dependency),
    material_id: Optional[int] = Query(default=None, description="物料ID过滤"),
    warehouse_id: Optional[int] = Query(default=None, description="仓库ID过滤"),
    keyword: Optional[str] = Query(default=None, description="物料编码/名称关键字"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.BalanceOut]]:
    """分页查询实时库存（含现存量/锁定量/可用量）。"""
    rows, total = service.list_balances(
        db,
        page=params.page,
        page_size=params.page_size,
        material_id=material_id,
        warehouse_id=warehouse_id,
        keyword=keyword,
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


# ==================== 库存流水 ====================


@router.get(
    "/transactions",
    response_model=ApiResponse[PageData[schemas.TransactionOut]],
    summary="库存流水列表",
)
def list_transactions(
    params: PageParams = Depends(PageParams.as_dependency),
    transaction_type: Optional[str] = Query(default=None, description="IN/OUT/TRANSFER_IN/TRANSFER_OUT/ADJUST"),
    material_id: Optional[int] = Query(default=None, description="物料ID"),
    warehouse_id: Optional[int] = Query(default=None, description="仓库ID"),
    source_type: Optional[str] = Query(default=None, description="来源业务类型"),
    date_from: Optional[date] = Query(default=None, description="业务日期起"),
    date_to: Optional[date] = Query(default=None, description="业务日期止"),
    source_no: Optional[str] = Query(default=None, description="来源单号（模糊）"),
    keyword: Optional[str] = Query(default=None, description="物料编码/名称关键字"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.TransactionOut]]:
    """分页查询库存流水。"""
    rows, total = service.list_transactions(
        db,
        page=params.page,
        page_size=params.page_size,
        transaction_type=transaction_type,
        material_id=material_id,
        warehouse_id=warehouse_id,
        source_type=source_type,
        date_from=date_from,
        date_to=date_to,
        source_no=source_no,
        keyword=keyword,
    )
    return success(
        PageData[schemas.TransactionOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.get(
    "/transactions/{transaction_id}",
    response_model=ApiResponse[schemas.TransactionOut],
    summary="库存流水详情",
)
def get_transaction(
    transaction_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.TransactionOut]:
    """按 ID 查询库存流水。"""
    return success(service.get_transaction(db, transaction_id))


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
        location_id=payload.location_id,
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
        location_id=payload.location_id,
        source_module="inventory",
        source_type="MANUAL",
        unit_cost=payload.unit_cost,
        biz_date=payload.biz_date,
        operator_id=payload.operator_id,
        remark=payload.remark,
    )
    db.commit()
    return success(result)


# ==================== 移库 ====================


@router.get(
    "/transfers", response_model=ApiResponse[PageData[schemas.TransferOut]], summary="移库单列表"
)
def list_transfers(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = Query(default=None, description="状态"),
    from_warehouse_id: Optional[int] = Query(default=None, description="源仓库ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.TransferOut]]:
    """分页查询移库单。"""
    rows, total = service.list_transfers(
        db, params.page, params.page_size, status, from_warehouse_id
    )
    return success(
        PageData[schemas.TransferOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/transfers", response_model=ApiResponse[schemas.TransferOut], summary="新增移库单")
def create_transfer(
    payload: schemas.TransferCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.TransferOut]:
    """新增移库单（单头 + 明细，状态 DRAFT）。"""
    transfer = service.create_transfer(
        db,
        from_warehouse_id=payload.from_warehouse_id,
        to_warehouse_id=payload.to_warehouse_id,
        transfer_date=payload.transfer_date,
        items=[item.model_dump() for item in payload.items],
        transfer_no=payload.transfer_no,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(transfer)


@router.get(
    "/transfers/{transfer_id}",
    response_model=ApiResponse[schemas.TransferOut],
    summary="移库单详情",
)
def get_transfer(transfer_id: int, db: Session = Depends(get_db)) -> ApiResponse[schemas.TransferOut]:
    """按 ID 查询移库单（含明细）。"""
    return success(service.get_transfer(db, transfer_id))


@router.post(
    "/transfers/{transfer_id}/confirm",
    response_model=ApiResponse[schemas.TransferOut],
    summary="确认移库",
)
def confirm_transfer(
    transfer_id: int,
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.TransferOut]:
    """确认移库：写 TRANSFER_OUT + TRANSFER_IN 两条流水，状态 → COMPLETED。"""
    transfer = service.confirm_transfer(db, transfer_id, operator_id)
    db.commit()
    return success(transfer)


@router.post(
    "/transfers/{transfer_id}/cancel",
    response_model=ApiResponse[schemas.TransferOut],
    summary="取消移库",
)
def cancel_transfer(
    transfer_id: int,
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.TransferOut]:
    """取消移库单（仅 DRAFT 可取消）。"""
    transfer = service.cancel_transfer(db, transfer_id, operator_id)
    db.commit()
    return success(transfer)


# ==================== 盘点 ====================


@router.get(
    "/stocktakes", response_model=ApiResponse[PageData[schemas.StocktakeOut]], summary="盘点单列表"
)
def list_stocktakes(
    params: PageParams = Depends(PageParams.as_dependency),
    warehouse_id: Optional[int] = Query(default=None, description="仓库ID"),
    status: Optional[str] = Query(default=None, description="状态"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.StocktakeOut]]:
    """分页查询盘点单。"""
    rows, total = service.list_stocktakes(db, params.page, params.page_size, warehouse_id, status)
    return success(
        PageData[schemas.StocktakeOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.post("/stocktakes", response_model=ApiResponse[schemas.StocktakeOut], summary="新增盘点单")
def create_stocktake(
    payload: schemas.StocktakeCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.StocktakeOut]:
    """新增盘点单（明细的 book_qty 留空时按当前结存自动带出）。"""
    stocktake = service.create_stocktake(
        db,
        warehouse_id=payload.warehouse_id,
        stocktake_date=payload.stocktake_date,
        items=[item.model_dump() for item in payload.items],
        stocktake_no=payload.stocktake_no,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(stocktake)


@router.get(
    "/stocktakes/{stocktake_id}",
    response_model=ApiResponse[schemas.StocktakeOut],
    summary="盘点单详情",
)
def get_stocktake(
    stocktake_id: int, db: Session = Depends(get_db)
) -> ApiResponse[schemas.StocktakeOut]:
    """按 ID 查询盘点单（含明细）。"""
    return success(service.get_stocktake(db, stocktake_id))


@router.post(
    "/stocktakes/{stocktake_id}/confirm",
    response_model=ApiResponse[schemas.StocktakeOut],
    summary="确认盘点",
)
def confirm_stocktake(
    stocktake_id: int,
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.StocktakeOut]:
    """确认盘点：按差异写 ADJUST 流水，状态 → COMPLETED。"""
    stocktake = service.confirm_stocktake(db, stocktake_id, operator_id)
    db.commit()
    return success(stocktake)


@router.post(
    "/stocktakes/{stocktake_id}/cancel",
    response_model=ApiResponse[schemas.StocktakeOut],
    summary="取消盘点",
)
def cancel_stocktake(
    stocktake_id: int,
    operator_id: Optional[int] = Query(default=None, description="操作人ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[schemas.StocktakeOut]:
    """取消盘点单（仅 DRAFT 可取消）。"""
    stocktake = service.cancel_stocktake(db, stocktake_id, operator_id)
    db.commit()
    return success(stocktake)


# ==================== 订货点规则 ====================


@router.get(
    "/reorder-rules",
    response_model=ApiResponse[PageData[schemas.ReorderRuleOut]],
    summary="订货点规则列表",
)
def list_reorder_rules(
    params: PageParams = Depends(PageParams.as_dependency),
    status: Optional[str] = Query(default=None, description="状态"),
    material_id: Optional[int] = Query(default=None, description="物料ID"),
    warehouse_id: Optional[int] = Query(default=None, description="仓库ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[PageData[schemas.ReorderRuleOut]]:
    """分页查询订货点规则。"""
    rows, total = service.list_reorder_rules(
        db,
        page=params.page,
        page_size=params.page_size,
        status=status,
        material_id=material_id,
        warehouse_id=warehouse_id,
    )
    return success(
        PageData[schemas.ReorderRuleOut](
            page=params.page, page_size=params.page_size, total=total, items=rows
        )
    )


@router.get(
    "/reorder-rules/suggestions",
    response_model=ApiResponse[List[schemas.ReorderSuggestionOut]],
    summary="补库建议",
)
def list_reorder_suggestions(
    db: Session = Depends(get_db),
) -> ApiResponse[List[schemas.ReorderSuggestionOut]]:
    """对现存量低于订货点的 ACTIVE 规则给出补库建议。"""
    return success(service.list_reorder_suggestions(db))


@router.post(
    "/reorder-rules", response_model=ApiResponse[schemas.ReorderRuleOut], summary="新增订货点规则"
)
def create_reorder_rule(
    payload: schemas.ReorderRuleCreate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ReorderRuleOut]:
    """新增订货点规则（物料+仓库唯一）。"""
    rule = service.create_reorder_rule(
        db,
        material_id=payload.material_id,
        warehouse_id=payload.warehouse_id,
        reorder_point=payload.reorder_point,
        reorder_quantity=payload.reorder_quantity,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(rule)


@router.put(
    "/reorder-rules/{rule_id}",
    response_model=ApiResponse[schemas.ReorderRuleOut],
    summary="修改订货点规则",
)
def update_reorder_rule(
    rule_id: int, payload: schemas.ReorderRuleUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ReorderRuleOut]:
    """修改订货点与建议订货量。"""
    rule = service.update_reorder_rule(
        db,
        rule_id,
        reorder_point=payload.reorder_point,
        reorder_quantity=payload.reorder_quantity,
        remark=payload.remark,
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(rule)


@router.patch(
    "/reorder-rules/{rule_id}/status",
    response_model=ApiResponse[schemas.ReorderRuleOut],
    summary="启用/停用订货点规则",
)
def set_reorder_rule_status(
    rule_id: int, payload: schemas.StatusUpdate, db: Session = Depends(get_db)
) -> ApiResponse[schemas.ReorderRuleOut]:
    """订货点规则状态流转。"""
    rule = service.set_reorder_rule_status(db, rule_id, payload.status, payload.operator_id)
    db.commit()
    return success(rule)


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
    """按流水类型 + 物料统计出入库数量。"""
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
        location_id=payload.location_id,
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
    """确认期初库存导入：重新校验后逐行走 `increase_stock`，写真实流水与结存，同一事务提交。"""
    result = service.confirm_initial_stock_import(
        db,
        source=payload.source,
        warehouse_id=payload.warehouse_id,
        warehouse_code=payload.warehouse_code,
        location_id=payload.location_id,
        rows=[row.model_dump() for row in payload.rows],
        operator_id=payload.operator_id,
    )
    db.commit()
    return success(result)