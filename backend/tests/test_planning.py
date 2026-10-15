"""planning 模块核心业务测试（使用本机真实 MySQL）。

覆盖规格 §34 的关键要求：

1. 单层 MRP：毛需求 → 净需求 → 建议下达
2. **多层 MRP**：测试内自建 3 层 BOM，逐层展开数量与需求日期正确
3. 安全库存 + 可用库存净算：`净需求 = max(毛需求 + 安全库存 − 可用库存, 0)`
4. 净需求下限为 0（库存充足时不下达）
5. MAKE / BUY 供应类型分流
6. `建议下达日期 = 需求日期 − 提前期`
7. **同一物料被多个父件引用时可用库存只抵扣一次**（本批次内）
8. 两次 MRP 运算各自独立保留（批次ID不同，历史结果不被覆盖）
9. 领料确认：写 `MATERIAL_REQUISITION` 真实流水并扣减库存；缺料整单回滚
10. 完工确认：写 `PRODUCTION_COMPLETION` 真实流水并增加库存，回写作业计划

所有业务编码均带随机后缀，保证测试可重复运行。
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.inventory import service as inventory_service
from app.modules.planning import schemas, service


def _tag() -> str:
    return uuid.uuid4().hex[:10].upper()


# ==================== 造数辅助 ====================


def _create_material(
    db: Session,
    *,
    supply_type: str = "BUY",
    material_type: str = "PURCHASED",
    lead_time_days: int = 0,
    safety_stock: Decimal = Decimal("0"),
):
    """直接写入物料主数据，返回 (material_id, material_code)。"""
    code = f"PL{_tag()}"
    db.execute(
        text(
            "INSERT INTO sys_material (material_code, material_name, material_type, supply_type, "
            "unit_code, lead_time_days, safety_stock, standard_cost, status, created_at, updated_at) "
            "VALUES (:code, :name, :mt, :st, 'PCS', :lt, :ss, 0, 'ACTIVE', NOW(), NOW())"
        ),
        {
            "code": code,
            "name": f"计划测试物料{code}",
            "mt": material_type,
            "st": supply_type,
            "lt": lead_time_days,
            "ss": safety_stock,
        },
    )
    db.commit()
    material_id = int(
        db.execute(
            text("SELECT id FROM sys_material WHERE material_code = :c"), {"c": code}
        ).scalar()
    )
    return material_id, code


def _create_bom(db: Session, parent_id: int, children) -> int:
    """写入生效 BOM 头 + 明细。`children` = [(child_id, qty, lead_time_offset, scrap_rate)]。"""
    bom_code = f"BOM{_tag()}"
    db.execute(
        text(
            "INSERT INTO sys_bom (bom_code, material_id, bom_version, is_active, status, "
            "created_at, updated_at) VALUES (:c, :m, 'V1.0', 1, 'ACTIVE', NOW(), NOW())"
        ),
        {"c": bom_code, "m": parent_id},
    )
    db.commit()
    bom_id = int(
        db.execute(text("SELECT id FROM sys_bom WHERE bom_code = :c"), {"c": bom_code}).scalar()
    )
    for seq, (child_id, qty, offset, scrap) in enumerate(children, start=1):
        db.execute(
            text(
                "INSERT INTO sys_bom_item (bom_id, material_id, quantity, lead_time_offset, "
                "scrap_rate, sequence_no, created_at, updated_at) "
                "VALUES (:b, :m, :q, :o, :s, :seq, NOW(), NOW())"
            ),
            {
                "b": bom_id,
                "m": child_id,
                "q": Decimal(str(qty)),
                "o": offset,
                "s": Decimal(str(scrap)),
                "seq": seq,
            },
        )
    db.commit()
    return bom_id


def _create_warehouse(db: Session) -> int:
    warehouse = inventory_service.create_warehouse(
        db, warehouse_code=f"WH{_tag()}", warehouse_name=f"计划测试仓{_tag()}"
    )
    db.commit()
    return warehouse.id


def _add_stock(db: Session, material_id: int, warehouse_id: int, qty) -> None:
    inventory_service.increase_stock(
        db,
        material_id=material_id,
        quantity=Decimal(str(qty)),
        warehouse_id=warehouse_id,
        source_module="inventory",
        source_type="MANUAL",
    )
    db.commit()


def _create_mps(db: Session, material_id: int, qty, end_date: date) -> int:
    """通过真实 service 建立 MPS（头 + 行）。"""
    payload = schemas.MpsCreate(
        plan_year=end_date.year,
        start_date=end_date - timedelta(days=30),
        end_date=end_date,
        items=[
            schemas.MpsItemCreate(
                material_id=material_id,
                period_label=end_date.strftime("%Y-%m"),
                planned_qty=Decimal(str(qty)),
                start_date=end_date - timedelta(days=30),
                end_date=end_date,
            )
        ],
    )
    mps = service.create_mps(db, payload)
    db.commit()
    return mps.id


def _create_confirmed_demand(db: Session, material_id: int, qty, due_date: date) -> int:
    demand = service.create_demand(
        db,
        source_type="MPS",
        material_id=material_id,
        quantity=Decimal(str(qty)),
        due_date=due_date,
    )
    service.set_demand_status(db, demand.id, "CONFIRMED")
    db.commit()
    return demand.id


def _results_of_run(db: Session, run_id: int):
    rows, _ = service.list_mrp_results(db, page=1, page_size=200, run_id=run_id)
    return {row.material_id: row for row in rows}


# ==================== 1. 单层 MRP + MAKE/BUY + 下达日期 ====================


def test_mrp_single_level_explosion_net_and_release_date(db: Session) -> None:
    """单层展开：成品 100 → 采购件 200，净需求含安全库存，下达日期 = 需求日期 − 提前期。"""
    finished_id, _ = _create_material(
        db, supply_type="MAKE", material_type="FINISHED", lead_time_days=5
    )
    part_id, _ = _create_material(db, supply_type="BUY", lead_time_days=2, safety_stock=Decimal("10"))
    _create_bom(db, finished_id, [(part_id, 2, 0, 0)])

    end_date = date.today() + timedelta(days=30)
    mps_id = _create_mps(db, finished_id, 100, end_date)

    run = service.run_mrp(db, mps_id=mps_id)
    db.commit()

    assert run.status == "COMPLETED"
    assert run.material_count == 2
    results = _results_of_run(db, run.id)

    finished = results[finished_id]
    assert finished.bom_level == 0
    assert finished.gross_requirement == Decimal("100.0000")
    assert finished.net_requirement == Decimal("100.0000")
    assert finished.supply_type == "MAKE"
    assert finished.requirement_date == end_date
    assert finished.planned_release_date == end_date - timedelta(days=5)

    part = results[part_id]
    assert part.bom_level == 1
    assert part.gross_requirement == Decimal("200.0000")
    assert part.safety_stock == Decimal("10.0000")
    assert part.available_quantity == Decimal("0.0000")
    assert part.net_requirement == Decimal("210.0000")
    assert part.supply_type == "BUY"
    assert part.parent_material_id == finished_id
    assert part.planned_release_date == end_date - timedelta(days=2)


# ==================== 2. 多层（3 层）BOM 展开 ====================


def test_mrp_multilevel_three_level_bom(db: Session) -> None:
    """测试内自建 3 层 BOM，验证逐层数量与需求日期回推。"""
    l0, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED", lead_time_days=1)
    l1, _ = _create_material(db, supply_type="MAKE", material_type="SEMI", lead_time_days=2)
    l2, _ = _create_material(db, supply_type="BUY", lead_time_days=3)
    # l1 需要 2 个 l0 的子件；l2 需要 3 个 l1（并带 1 天提前期偏置）
    _create_bom(db, l0, [(l1, 2, 0, 0)])
    _create_bom(db, l1, [(l2, 3, 1, 0)])

    end_date = date.today() + timedelta(days=40)
    mps_id = _create_mps(db, l0, 10, end_date)

    run = service.run_mrp(db, mps_id=mps_id)
    db.commit()
    results = _results_of_run(db, run.id)

    assert set(results) == {l0, l1, l2}
    assert results[l0].bom_level == 0
    assert results[l1].bom_level == 1
    assert results[l2].bom_level == 2

    assert results[l1].gross_requirement == Decimal("20.0000")  # 10 × 2
    assert results[l1].requirement_date == end_date
    assert results[l2].gross_requirement == Decimal("60.0000")  # 20 × 3
    # l2 需求日期 = l1 需求日期 − lead_time_offset(1)
    assert results[l2].requirement_date == end_date - timedelta(days=1)
    assert results[l2].planned_release_date == end_date - timedelta(days=1) - timedelta(days=3)
    # 父件关系可回溯
    assert results[l1].parent_material_id == l0
    assert results[l2].parent_material_id == l1


# ==================== 3/4. 安全库存 + 可用库存净算 ====================


def test_available_stock_and_safety_stock_netting(db: Session) -> None:
    """净需求 = max(毛需求 + 安全库存 − 可用库存, 0)。"""
    material_id, _ = _create_material(
        db, supply_type="BUY", lead_time_days=3, safety_stock=Decimal("10")
    )
    warehouse_id = _create_warehouse(db)
    _add_stock(db, material_id, warehouse_id, 30)

    due_date = date.today() + timedelta(days=20)
    demand_id = _create_confirmed_demand(db, material_id, 100, due_date)

    run = service.run_mrp(db, demand_ids=[demand_id])
    db.commit()
    result = _results_of_run(db, run.id)[material_id]

    assert result.on_hand == Decimal("30.0000")
    assert result.available_quantity == Decimal("30.0000")
    assert result.safety_stock == Decimal("10.0000")
    assert result.net_requirement == Decimal("80.0000")  # 100 + 10 − 30
    assert result.order_qty == Decimal("80.0000")
    assert result.requirement_date == due_date
    assert result.planned_release_date == due_date - timedelta(days=3)


def test_net_requirement_never_negative(db: Session) -> None:
    """库存充足时净需求取下限 0（不下达计划）。"""
    material_id, _ = _create_material(db, supply_type="BUY", lead_time_days=1)
    warehouse_id = _create_warehouse(db)
    _add_stock(db, material_id, warehouse_id, 500)

    demand_id = _create_confirmed_demand(db, material_id, 5, date.today() + timedelta(days=7))

    run = service.run_mrp(db, demand_ids=[demand_id])
    db.commit()
    result = _results_of_run(db, run.id)[material_id]
    assert result.gross_requirement == Decimal("5.0000")
    assert result.net_requirement == Decimal("0.0000")
    assert result.order_qty == Decimal("0.0000")


# ==================== 7. 可用库存只抵扣一次 ====================


def test_shared_material_available_stock_consumed_once(db: Session) -> None:
    """同一物料在两层出现（菱形 BOM）时，可用库存仅在本批次内抵扣一次。"""
    l0, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    mid, _ = _create_material(db, supply_type="MAKE", material_type="SEMI")
    shared, _ = _create_material(db, supply_type="BUY", material_type="PURCHASED")
    # l0 → mid(1) 且 l0 → shared(10)；mid → shared(5)
    _create_bom(db, l0, [(mid, 1, 0, 0), (shared, 10, 0, 0)])
    _create_bom(db, mid, [(shared, 5, 0, 0)])

    warehouse_id = _create_warehouse(db)
    _add_stock(db, shared, warehouse_id, 4)

    mps_id = _create_mps(db, l0, 1, date.today() + timedelta(days=15))
    run = service.run_mrp(db, mps_id=mps_id)
    db.commit()

    rows = [
        r for r in service.list_mrp_results(db, page=1, page_size=200, run_id=run.id)[0]
        if r.material_id == shared
    ]
    # shared 分别来自 l0（10）与 mid（5），合计 15；可用库存 4 只能抵扣一次 → 净需求合计 11
    assert len(rows) == 2
    assert sum(r.gross_requirement for r in rows) == Decimal("15.0000")
    assert sum(r.net_requirement for r in rows) == Decimal("11.0000")
    # 第二层出现的 shared 复用剩余可用（4 已在第一层用尽），因此净需求为全额 5
    assert sorted(r.net_requirement for r in rows) == [Decimal("5.0000"), Decimal("6.0000")]


# ==================== 8. 两次 MRP 结果独立保留 ====================


def test_two_mrp_runs_are_preserved_separately(db: Session) -> None:
    """每次 MRP 运算独立批次，历史结果不被覆盖。"""
    finished_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    part_id, _ = _create_material(db, supply_type="BUY")
    _create_bom(db, finished_id, [(part_id, 1, 0, 0)])
    mps_id = _create_mps(db, finished_id, 50, date.today() + timedelta(days=10))

    run1 = service.run_mrp(db, mps_id=mps_id)
    db.commit()
    run1_results_before = _results_of_run(db, run1.id)

    run2 = service.run_mrp(db, mps_id=mps_id)
    db.commit()

    assert run1.id != run2.id
    assert run1.run_no != run2.run_no

    # 第一次批次的结果仍可查询，且行数与内容未被覆盖
    again = _results_of_run(db, run1.id)
    assert set(again) == set(run1_results_before)
    for material_id, row in again.items():
        assert row.gross_requirement == run1_results_before[material_id].gross_requirement
        assert row.run_id == run1.id

    assert len(_results_of_run(db, run2.id)) == 2


# ==================== 9. 领料确认 ====================


def test_requisition_confirm_writes_ledger_and_decreases_stock(db: Session) -> None:
    """领料确认：写 MATERIAL_REQUISITION 流水、扣减库存、回写已领数量。"""
    material_id, code = _create_material(db, supply_type="BUY")
    warehouse_id = _create_warehouse(db)
    _add_stock(db, material_id, warehouse_id, 100)

    req = service.create_requisition(
        db,
        req_date=date.today(),
        warehouse_id=warehouse_id,
        items=[{"material_id": material_id, "required_qty": Decimal("40")}],
    )
    db.commit()

    confirmed = service.confirm_requisition(db, req.id)
    db.commit()

    assert confirmed.status == "COMPLETED"
    assert inventory_service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("60.0000")
    assert confirmed.items[0].issued_qty == Decimal("40.0000")


def test_requisition_confirm_insufficient_stock_rolls_back(db: Session) -> None:
    """库存不足（5001）时整单回滚：状态与库存都不变。"""
    material_id, _ = _create_material(db, supply_type="BUY")
    warehouse_id = _create_warehouse(db)
    _add_stock(db, material_id, warehouse_id, 5)

    req = service.create_requisition(
        db,
        req_date=date.today(),
        warehouse_id=warehouse_id,
        items=[{"material_id": material_id, "required_qty": Decimal("50")}],
    )
    db.commit()

    with pytest.raises(BusinessException) as exc:
        service.confirm_requisition(db, req.id)
    assert exc.value.code == 5001
    db.rollback()

    assert inventory_service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("5.0000")
    assert service.get_requisition(db, req.id).status == "DRAFT"


# ==================== 10. 完工确认 ====================


def test_completion_confirm_writes_ledger_and_increases_stock(db: Session) -> None:
    """完工确认：写 PRODUCTION_COMPLETION 流水、增加库存并回写作业计划已完工数量。"""
    material_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    warehouse_id = _create_warehouse(db)
    today = date.today()

    plan = service.create_production_plan(
        db,
        material_id=material_id,
        planned_qty=Decimal("10"),
        plan_date=today,
        start_date=today,
        end_date=today + timedelta(days=3),
    )
    db.commit()

    report = service.create_completion_report(
        db,
        material_id=material_id,
        completed_qty=Decimal("10"),
        qualified_qty=Decimal("10"),
        warehouse_id=warehouse_id,
        report_date=today,
        plan_id=plan.id,
    )
    db.commit()

    confirmed = service.confirm_completion_report(db, report.id)
    db.commit()

    assert confirmed.status == "COMPLETED"
    assert inventory_service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("10.0000")
    assert service.get_production_plan(db, plan.id).completed_qty == Decimal("10.0000")


# ==================== 附加：MPS 只读与导入预览 ====================


def test_confirmed_mps_is_read_only(db: Session) -> None:
    """已确认 MPS 不允许修改（报 3002）。"""
    material_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    mps_id = _create_mps(db, material_id, 10, date.today() + timedelta(days=5))
    service.set_mps_status(db, mps_id, "CONFIRMED")
    db.commit()

    with pytest.raises(BusinessException) as exc:
        service.update_mps(db, mps_id, schemas.MpsUpdate(mps_name="禁止修改"))
    assert exc.value.code == 3002
    db.rollback()


def test_mps_import_preview_does_not_write(db: Session) -> None:
    """导入预览只读：返回行/汇总但不落库。"""
    _, code = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    payload = schemas.MpsImportRequest(
        rows=[
            schemas.MpsImportRow(
                material_code=code,
                period_label="2026-01",
                planned_qty=Decimal("100"),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
            )
        ],
        plan_year=2026,
    )
    total_before = service.stats(db)["mps_count"]
    preview = service.preview_mps_import(db, payload)
    assert preview["summary"]["valid_count"] == 1
    assert preview["summary"]["error_count"] == 0
    assert preview["summary"]["total_rows"] == 1
    assert service.stats(db)["mps_count"] == total_before


def test_mps_import_preview_reports_unknown_material(db: Session) -> None:
    """导入预览：未知物料编码归入错误行。"""
    payload = schemas.MpsImportRequest(
        rows=[
            schemas.MpsImportRow(
                material_code="NOT-EXIST-CODE",
                planned_qty=Decimal("10"),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
            )
        ],
        plan_year=2026,
    )
    preview = service.preview_mps_import(db, payload)
    assert preview["summary"]["valid_count"] == 0
    assert preview["summary"]["error_count"] == 1
    assert "不存在" in preview["errors"][0]["message"]


# ==================== 附加：补库需求导入只受理转计划 ====================


def _create_replenishment_request(
    db: Session, material_id: int, warehouse_id: int, source_type: str
) -> tuple[int, str]:
    """直接写入已下达的补库需求单，返回 (ID, 单号)。"""
    request_no = f"RPL{_tag()}"
    db.execute(
        text(
            "INSERT INTO inv_replenishment_request (request_no, material_id, warehouse_id, "
            "request_qty, current_qty, target_qty, required_date, source_type, status, "
            "created_at, updated_at) "
            "VALUES (:no, :m, :w, 8, 0, 8, :rd, :st, 'RELEASED', NOW(), NOW())"
        ),
        {
            "no": request_no,
            "m": material_id,
            "w": warehouse_id,
            "rd": date.today(),
            "st": source_type,
        },
    )
    db.commit()
    request_id = int(
        db.execute(
            text("SELECT id FROM inv_replenishment_request WHERE request_no = :c"),
            {"c": request_no},
        ).scalar()
    )
    return request_id, request_no


def test_import_demands_from_replenishment_only_takes_production(db: Session) -> None:
    """批量导入补库需求：只受理转计划（PRODUCTION），转采购（REORDER）不得进入计划模块。"""
    material_id, _ = _create_material(db)
    warehouse_id = _create_warehouse(db)
    production_id, production_no = _create_replenishment_request(
        db, material_id, warehouse_id, "PRODUCTION"
    )
    reorder_id, _ = _create_replenishment_request(db, material_id, warehouse_id, "REORDER")

    result = service.import_demands_from_replenishment(db)
    db.commit()

    imported = {
        int(demand.source_reference_id): demand
        for demand in (service.get_demand(db, demand_id) for demand_id in result["demand_ids"])
    }
    assert production_id in imported, "转计划的补库需求应生成计划需求"
    assert reorder_id not in imported, "转采购的补库需求不应生成计划需求"

    production_demand = imported[production_id]
    assert production_demand.source_type == "STOCKFILL"
    assert production_demand.source_no == production_no

    # 单条导入同样拒绝转采购的补库需求
    with pytest.raises(BusinessException) as exc:
        service.create_demand_from_replenishment(db, reorder_id)
    assert exc.value.code == 3000
    db.rollback()


# ==================== 附加：按生产作业计划生成派工单 / 领料单 ====================


def _create_routing(db: Session, material_id: int, operations) -> int:
    """写入生效工艺路线头 + 工序行。`operations` = [(seq, code, name, work_center)]。"""
    routing_code = f"RT{_tag()}"
    db.execute(
        text(
            "INSERT INTO sys_routing (routing_code, material_id, routing_version, status, "
            "created_at, updated_at) VALUES (:c, :m, 'V1.0', 'ACTIVE', NOW(), NOW())"
        ),
        {"c": routing_code, "m": material_id},
    )
    db.commit()
    routing_id = int(
        db.execute(
            text("SELECT id FROM sys_routing WHERE routing_code = :c"),
            {"c": routing_code},
        ).scalar()
    )
    for seq, code, name, work_center in operations:
        _add_routing_operation(db, routing_id, seq, code, name, work_center)
    return routing_id


def _add_routing_operation(
    db: Session,
    routing_id: int,
    sequence_no: int,
    operation_code: str,
    operation_name: str,
    work_center: str = "WC1",
) -> None:
    db.execute(
        text(
            "INSERT INTO sys_routing_operation (routing_id, sequence_no, operation_code, "
            "operation_name, work_center, setup_time, run_time, created_at, updated_at) "
            "VALUES (:r, :seq, :oc, :on, :wc, 0, 0, NOW(), NOW())"
        ),
        {
            "r": routing_id,
            "seq": sequence_no,
            "oc": operation_code,
            "on": operation_name,
            "wc": work_center,
        },
    )
    db.commit()


def _make_make_plan(db: Session, material_id: int, qty=10, days: int = 2):
    """建一张 DRAFT 生产作业计划（自制件），返回 plan。"""
    today = date.today()
    plan = service.create_production_plan(
        db,
        material_id=material_id,
        planned_qty=Decimal(str(qty)),
        plan_date=today,
        start_date=today,
        end_date=today + timedelta(days=days),
    )
    db.commit()
    return plan


def test_generate_dispatch_orders_one_per_operation(db: Session) -> None:
    """按工艺路线逐工序生成：工序数 = 派工单数，日期与人员留空待人工填写。"""
    material_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    _create_routing(
        db,
        material_id,
        [
            (10, "OP10", "下料", "WC1"),
            (20, "OP20", "焊接", "WC2"),
            (30, "OP30", "喷涂", "WC3"),
        ],
    )
    plan = _make_make_plan(db, material_id, qty=10, days=2)

    result = service.create_dispatch_orders_from_plans(db, [plan.id])
    db.commit()

    assert result["created_count"] == 3
    assert result["skipped_count"] == 0
    assert result["errors"] == []
    assert len(result["ids"]) == 3

    rows, _total = service.list_dispatch_orders(db, plan_id=plan.id)
    assert len(rows) == 3
    assert {row.operation for row in rows} == {"下料", "焊接", "喷涂"}
    for row in rows:
        assert row.status == "DRAFT"
        assert row.source_type == "PLAN"
        assert row.source_reference_id == plan.id
        assert row.planned_qty == Decimal("10.0000")
        assert row.completed_qty == Decimal("0.0000")
        # 需人工指定的字段留空：日期与作业人员
        assert row.worker_id is None
        assert row.planned_start is None
        assert row.planned_end is None


def test_generate_dispatch_orders_blank_dates_block_confirm(db: Session) -> None:
    """留空日期的预填草稿不能直接确认；补齐日期后即可流转。"""
    material_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    _create_routing(db, material_id, [(10, "OP10", "下料", "WC1")])
    plan = _make_make_plan(db, material_id, qty=5, days=1)
    service.create_dispatch_orders_from_plans(db, [plan.id])
    db.commit()
    rows, _total = service.list_dispatch_orders(db, plan_id=plan.id)
    dispatch = rows[0]

    with pytest.raises(BusinessException) as exc:
        service.set_dispatch_order_status(db, dispatch.id, "CONFIRMED")
    assert exc.value.code == 3006
    db.rollback()

    service.update_dispatch_order(
        db,
        dispatch.id,
        schemas.DispatchOrderUpdate(
            planned_start=plan.start_date, planned_end=plan.end_date
        ),
    )
    db.commit()
    confirmed = service.set_dispatch_order_status(db, dispatch.id, "CONFIRMED")
    db.commit()
    assert confirmed.status == "CONFIRMED"
    assert confirmed.planned_start == plan.start_date
    assert confirmed.planned_end == plan.end_date


def test_generate_dispatch_orders_is_idempotent(db: Session) -> None:
    """重放同一请求：不新增派工单，计入 skipped。"""
    material_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    _create_routing(
        db,
        material_id,
        [(10, "OP10", "下料", "WC1"), (20, "OP20", "焊接", "WC2")],
    )
    plan = _make_make_plan(db, material_id)

    first = service.create_dispatch_orders_from_plans(db, [plan.id])
    db.commit()
    replay = service.create_dispatch_orders_from_plans(db, [plan.id])
    db.commit()

    assert first["created_count"] == 2
    assert replay["created_count"] == 0
    assert replay["ids"] == []
    assert replay["skipped_count"] == 1
    assert replay["skipped"][0]["plan_id"] == plan.id
    rows, _total = service.list_dispatch_orders(db, plan_id=plan.id)
    assert len(rows) == 2


def test_generate_dispatch_orders_only_adds_new_operation(db: Session) -> None:
    """工艺路线新增工序后再生成：只补新增那一道，已存在的工序精准跳过。"""
    material_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    routing_id = _create_routing(
        db,
        material_id,
        [(10, "OP10", "下料", "WC1"), (20, "OP20", "焊接", "WC2")],
    )
    plan = _make_make_plan(db, material_id)
    service.create_dispatch_orders_from_plans(db, [plan.id])
    db.commit()

    _add_routing_operation(db, routing_id, 30, "OP30", "喷涂", "WC3")
    result = service.create_dispatch_orders_from_plans(db, [plan.id])
    db.commit()

    assert result["created_count"] == 1
    assert result["skipped_count"] == 0
    rows, _total = service.list_dispatch_orders(db, plan_id=plan.id)
    assert len(rows) == 3
    assert {row.operation for row in rows} == {"下料", "焊接", "喷涂"}


def test_generate_dispatch_orders_without_routing_reports_error(db: Session) -> None:
    """无生效工艺路线：该计划不建单，errors 带计划号与物料编码。"""
    material_id, code = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    plan = _make_make_plan(db, material_id)

    result = service.create_dispatch_orders_from_plans(db, [plan.id, 999999999])
    db.commit()

    assert result["created_count"] == 0
    assert len(result["errors"]) == 2
    reasons = {error["plan_id"]: error for error in result["errors"]}
    assert reasons[plan.id]["plan_no"] == plan.plan_no
    assert reasons[plan.id]["material_code"] == code
    assert "工艺路线" in reasons[plan.id]["reason"]
    assert "不存在" in reasons[999999999]["reason"]
    rows, _total = service.list_dispatch_orders(db, plan_id=plan.id)
    assert rows == []


def test_generate_requisitions_quantity_and_aggregation(db: Session) -> None:
    """领料数量 = 子件用量 × 计划量 × (1+损耗)。

    注：`sys_bom_item` 唯一键为 (bom_id, material_id)，同一子件在同一层 BOM 只会出现一行，
    故此处按两个子件断言；service 侧的按物料聚合是为多行场景预留的兜底。
    """
    parent_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    child_a, _ = _create_material(db)
    child_b, _ = _create_material(db)
    _create_bom(
        db,
        parent_id,
        [
            (child_a, Decimal("2"), 0, Decimal("0.1")),
            (child_b, Decimal("5"), 0, Decimal("0")),
        ],
    )
    warehouse_id = _create_warehouse(db)
    plan = _make_make_plan(db, parent_id, qty=10, days=2)

    result = service.create_requisitions_from_plans(
        db, [plan.id], warehouse_id=warehouse_id
    )
    db.commit()

    assert result["created_count"] == 1
    req = service.get_requisition(db, result["ids"][0])
    assert req.source_type == "PLAN"
    assert req.source_reference_id == plan.id
    assert req.warehouse_id == warehouse_id
    assert req.status == "DRAFT"
    # 领料日期留空，交由人工指定
    assert req.req_date is None

    by_material = {item.material_id: item.required_qty for item in req.items}
    assert len(by_material) == 2
    # 2×10×1.1 = 22
    assert by_material[child_a] == Decimal("22.0000")
    # 5×10×1 = 50
    assert by_material[child_b] == Decimal("50.0000")


def test_generate_requisitions_skips_without_bom_and_existing(db: Session) -> None:
    """领料生成：无 BOM 计 errors，已生成过计 skipped。"""
    no_bom_id, no_bom_code = _create_material(
        db, supply_type="MAKE", material_type="FINISHED"
    )
    plan_no_bom = _make_make_plan(db, no_bom_id)
    result = service.create_requisitions_from_plans(db, [plan_no_bom.id])
    db.commit()
    assert result["created_count"] == 0
    assert result["skipped_count"] == 0
    assert result["errors"][0]["material_code"] == no_bom_code
    assert "BOM" in result["errors"][0]["reason"]

    parent_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    child_id, _ = _create_material(db)
    _create_bom(db, parent_id, [(child_id, Decimal("1"), 0, Decimal("0"))])
    plan = _make_make_plan(db, parent_id, qty=3)

    first = service.create_requisitions_from_plans(db, [plan.id])
    db.commit()
    replay = service.create_requisitions_from_plans(db, [plan.id])
    db.commit()

    assert first["created_count"] == 1
    assert replay["created_count"] == 0
    assert replay["skipped_count"] == 1
    assert replay["skipped"][0]["plan_id"] == plan.id


def test_update_dispatch_order_and_requisition_draft_only(db: Session) -> None:
    """人工审核调整：DRAFT 可改，非 DRAFT 报 3006；领料明细整表替换。"""
    material_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    today = date.today()
    dispatch = service.create_dispatch_order(
        db,
        planned_qty=Decimal("5"),
        planned_start=today,
        planned_end=today + timedelta(days=1),
        operation="下料",
    )
    db.commit()

    updated = service.update_dispatch_order(
        db,
        dispatch.id,
        schemas.DispatchOrderUpdate(
            operation="精加工",
            planned_qty=Decimal("8"),
            planned_end=today + timedelta(days=3),
        ),
    )
    db.commit()
    assert updated.operation == "精加工"
    assert updated.planned_qty == Decimal("8.0000")
    assert updated.planned_end == today + timedelta(days=3)

    # 作业人员不存在 → 3003
    with pytest.raises(BusinessException) as exc:
        service.update_dispatch_order(
            db, dispatch.id, schemas.DispatchOrderUpdate(worker_id=999999999)
        )
    assert exc.value.code == 3003
    db.rollback()

    # 非 DRAFT 不可改 → 3006
    service.set_dispatch_order_status(db, dispatch.id, "CONFIRMED")
    db.commit()
    with pytest.raises(BusinessException) as exc:
        service.update_dispatch_order(
            db, dispatch.id, schemas.DispatchOrderUpdate(planned_qty=Decimal("9"))
        )
    assert exc.value.code == 3006
    db.rollback()

    # 领料单：明细整表替换
    child_a, _ = _create_material(db)
    child_b, _ = _create_material(db)
    warehouse_id = _create_warehouse(db)
    req = service.create_requisition(
        db,
        req_date=today,
        items=[{"material_id": child_a, "required_qty": Decimal("4")}],
    )
    db.commit()
    assert len(req.items) == 1

    replaced = service.update_requisition(
        db,
        req.id,
        schemas.RequisitionUpdate(
            warehouse_id=warehouse_id,
            req_date=today + timedelta(days=1),
            items=[
                schemas.RequisitionItemUpdate(material_id=child_a, required_qty=Decimal("7")),
                schemas.RequisitionItemUpdate(material_id=child_b, required_qty=Decimal("2")),
            ],
        ),
    )
    db.commit()
    assert replaced.warehouse_id == warehouse_id
    assert replaced.req_date == today + timedelta(days=1)
    assert len(replaced.items) == 2
    assert {item.material_id: item.required_qty for item in replaced.items}[child_a] == Decimal(
        "7.0000"
    )

    # 非 DRAFT 领料单不可改 → 3006
    _add_stock(db, child_a, warehouse_id, 20)
    _add_stock(db, child_b, warehouse_id, 20)
    service.confirm_requisition(db, req.id)
    db.commit()
    with pytest.raises(BusinessException) as exc:
        service.update_requisition(
            db, req.id, schemas.RequisitionUpdate(remark="禁止修改")
        )
    assert exc.value.code == 3006
    db.rollback()


def test_generate_requisition_blank_warehouse_blocks_confirm(db: Session) -> None:
    """预填草稿未指定仓库/日期不能确认；人工补填后可确认出库。"""
    parent_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    child_id, _ = _create_material(db)
    _create_bom(db, parent_id, [(child_id, Decimal("2"), 0, Decimal("0"))])
    warehouse_id = _create_warehouse(db)
    plan = _make_make_plan(db, parent_id, qty=4)

    # 生成时不传仓库：仓库与日期均留空
    result = service.create_requisitions_from_plans(db, [plan.id])
    db.commit()
    req = service.get_requisition(db, result["ids"][0])
    assert req.warehouse_id is None
    assert req.req_date is None

    with pytest.raises(BusinessException) as exc:
        service.confirm_requisition(db, req.id)
    assert exc.value.code == 3000
    db.rollback()

    # 人工补填仓库（日期仍缺）→ 仍不能确认
    service.update_requisition(
        db, req.id, schemas.RequisitionUpdate(warehouse_id=warehouse_id)
    )
    db.commit()
    with pytest.raises(BusinessException) as exc:
        service.confirm_requisition(db, req.id)
    assert exc.value.code == 3000
    db.rollback()

    # 补齐日期后确认成功
    _add_stock(db, child_id, warehouse_id, 20)
    service.update_requisition(db, req.id, schemas.RequisitionUpdate(req_date=date.today()))
    db.commit()
    confirmed = service.confirm_requisition(db, req.id)
    db.commit()
    assert confirmed.status == "COMPLETED"
    assert confirmed.req_date == date.today()


def test_generate_completion_reports_prefilled_blank_manual_fields(db: Session) -> None:
    """按计划生成完工报告：产出物料与剩余数量预填，报工日期/入库仓库留空，且幂等。"""
    material_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    plan = _make_make_plan(db, material_id, qty=6)

    result = service.create_completion_reports_from_plans(db, [plan.id])
    db.commit()

    assert result["created_count"] == 1
    assert result["skipped_count"] == 0
    assert result["errors"] == []

    report = service.get_completion_report(db, result["ids"][0])
    assert report.plan_id == plan.id
    assert report.dispatch_id is None
    assert report.material_id == material_id
    assert report.completed_qty == Decimal("6.0000")
    assert report.qualified_qty == Decimal("6.0000")
    assert report.scrap_qty == Decimal("0.0000")
    assert report.warehouse_id is None
    assert report.report_date is None
    assert report.status == "DRAFT"

    # 幂等：同一计划再次生成只跳过，不新增报告
    again = service.create_completion_reports_from_plans(db, [plan.id])
    db.commit()
    assert again["created_count"] == 0
    assert again["skipped"][0]["reason"] == "该计划已生成完工报告"


def test_generate_completion_report_blank_fields_block_confirm(db: Session) -> None:
    """预填草稿未指定报工日期/入库仓库不能确认；人工补填后确认入库并回写计划。"""
    material_id, _ = _create_material(db, supply_type="MAKE", material_type="FINISHED")
    warehouse_id = _create_warehouse(db)
    plan = _make_make_plan(db, material_id, qty=3)

    result = service.create_completion_reports_from_plans(db, [plan.id])
    db.commit()
    report = service.get_completion_report(db, result["ids"][0])
    assert report.warehouse_id is None
    assert report.report_date is None

    with pytest.raises(BusinessException) as exc:
        service.confirm_completion_report(db, report.id)
    assert exc.value.code == 3000
    db.rollback()

    # 人工只补仓库（日期仍缺）→ 仍不能确认
    service.update_completion_report(
        db, report.id, schemas.CompletionReportUpdate(warehouse_id=warehouse_id)
    )
    db.commit()
    with pytest.raises(BusinessException) as exc:
        service.confirm_completion_report(db, report.id)
    assert exc.value.code == 3000
    db.rollback()

    # 补齐报工日期后确认成功：合格数量入库，并回写作业计划已完工数量
    service.update_completion_report(
        db, report.id, schemas.CompletionReportUpdate(report_date=date.today())
    )
    db.commit()
    confirmed = service.confirm_completion_report(db, report.id)
    db.commit()
    assert confirmed.status == "COMPLETED"
    assert confirmed.report_date == date.today()

    db.refresh(plan)
    assert plan.completed_qty == Decimal("3.0000")
