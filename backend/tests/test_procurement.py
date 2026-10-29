"""procurement 模块核心业务测试（使用本机真实 MySQL）。

覆盖规格 §14 / §16.5 / §21 / §24 / §42 的关键要求：

1. 供应商新增 + 编码唯一冲突（4001）
2. 供应商-物料关系 `(supplier_id, material_id)` 唯一（4002）
3. **从 MRP `BUY` 结果生成采购计划**（`procurement.contract.create_purchase_plan_from_mrp`，幂等）
4. **从库存订货点补库需求生成采购计划**（`procurement.contract.create_purchase_plan_from_replenishment`）
5. 由采购计划生成采购订单，并回写计划行 `ordered_qty`
6. **到货确认：调用库存入库 → 增加结存 + 写 `PURCHASE_RECEIPT` 流水 + 回写 `received_qty`**
7. 到货数量超过未到货数量拒绝（4004）
8. 供应商评价综合分 = 三项评分简单平均（4 位小数）

所有业务编码均带随机后缀，保证测试可重复运行。
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.modules.inventory import contract as inventory_contract
from app.modules.inventory import service as inventory_service
from app.modules.procurement import contract as procurement_contract
from app.modules.procurement import service


def _tag() -> str:
    return uuid.uuid4().hex[:10].upper()


# ==================== 造数辅助 ====================


def _create_material(
    db: Session,
    *,
    supply_type: str = "BUY",
    material_type: str = "PURCHASED",
    lead_time_days: int = 0,
) -> int:
    """直接写入物料主数据，返回物料ID（避免跨模块 import system 的 models）。"""
    code = f"PG{_tag()}"
    db.execute(
        text(
            "INSERT INTO sys_material (material_code, material_name, material_type, supply_type, "
            "unit_code, lead_time_days, safety_stock, standard_cost, status, created_at, updated_at) "
            "VALUES (:code, :name, :mt, :st, 'PCS', :lt, 0, 0, 'ACTIVE', NOW(), NOW())"
        ),
        {"code": code, "name": f"采购测试物料{code}", "mt": material_type, "st": supply_type, "lt": lead_time_days},
    )
    db.commit()
    return int(
        db.execute(text("SELECT id FROM sys_material WHERE material_code = :c"), {"c": code}).scalar()
    )


def _create_warehouse(db: Session) -> int:
    warehouse = inventory_service.create_warehouse(
        db, warehouse_code=f"WH{_tag()}", warehouse_name=f"采购测试仓{_tag()}"
    )
    db.commit()
    return warehouse.id


def _create_personnel(db: Session) -> int:
    """写入组织 + 员工，返回员工ID（采购员 / 评价人）。"""
    org_code = f"ORG{_tag()}"
    db.execute(
        text(
            "INSERT INTO sys_organization (org_code, org_name, org_type, status, created_at, updated_at) "
            "VALUES (:c, :n, 'DEPARTMENT', 'ACTIVE', NOW(), NOW())"
        ),
        {"c": org_code, "n": f"采购测试部门{org_code}"},
    )
    db.commit()
    org_id = int(
        db.execute(text("SELECT id FROM sys_organization WHERE org_code = :c"), {"c": org_code}).scalar()
    )
    no = f"EMP{_tag()}"
    db.execute(
        text(
            "INSERT INTO sys_personnel (employee_no, person_name, org_id, status, created_at, updated_at) "
            "VALUES (:no, :n, :org, 'ACTIVE', NOW(), NOW())"
        ),
        {"no": no, "n": f"采购测试员工{no}", "org": org_id},
    )
    db.commit()
    return int(
        db.execute(text("SELECT id FROM sys_personnel WHERE employee_no = :c"), {"c": no}).scalar()
    )


def _create_supplier(db: Session, *, name: str = "测试供应商") -> dict:
    supplier = service.create_supplier(
        db, supplier_code=f"SUP{_tag()}", supplier_name=name
    )
    db.commit()
    return supplier


# ==================== 1. 供应商 ====================


def test_supplier_create_and_duplicate_code_rejected(client: TestClient) -> None:
    """新增供应商成功；重复编码返回 4001。"""
    code = f"SUP{_tag()}"
    payload = {"supplier_code": code, "supplier_name": "接口测试供应商"}

    created = client.post("/api/v1/procurement/suppliers", json=payload)
    assert created.status_code == 200
    assert created.json()["code"] == 0
    assert created.json()["data"]["status"] == "ACTIVE"

    duplicated = client.post("/api/v1/procurement/suppliers", json=payload)
    assert duplicated.status_code == 200
    assert duplicated.json()["code"] == 4001


# ==================== 2. 供应商-物料唯一 ====================


def test_supplier_material_unique_rejected(db: Session) -> None:
    """同一供应商与物料的供货关系唯一，重复返回 4002。"""
    supplier = _create_supplier(db)
    material_id = _create_material(db)

    service.create_supplier_material(
        db,
        supplier_id=supplier["id"],
        material_id=material_id,
        supply_price=Decimal("12.5"),
    )
    db.commit()

    with pytest.raises(BusinessException) as exc:
        service.create_supplier_material(
            db, supplier_id=supplier["id"], material_id=material_id
        )
    assert exc.value.code == 4002
    db.rollback()


# ==================== 3. 从 MRP BUY 结果生成采购计划 ====================


def test_purchase_plan_from_mrp_results(db: Session) -> None:
    """MRP BUY 结果 → 采购计划（行 source_type=MRP），重复调用幂等不重复建单。"""
    material_id = _create_material(db, supply_type="BUY")
    run_no = f"MRP{_tag()}"
    db.execute(
        text(
            "INSERT INTO pln_mrp_run (run_no, status, material_count, run_at, created_at, updated_at) "
            "VALUES (:no, 'COMPLETED', 1, NOW(), NOW(), NOW())"
        ),
        {"no": run_no},
    )
    db.commit()
    run_id = int(
        db.execute(text("SELECT id FROM pln_mrp_run WHERE run_no = :c"), {"c": run_no}).scalar()
    )
    required_date = date.today() + timedelta(days=14)
    db.execute(
        text(
            "INSERT INTO pln_mrp_result (run_id, material_id, bom_level, gross_requirement, on_hand, "
            "available_quantity, safety_stock, net_requirement, order_qty, supply_type, lead_time_days, "
            "requirement_date, status, created_at, updated_at) "
            "VALUES (:run, :m, 1, 30, 0, 0, 0, 30, 30, 'BUY', 3, :rd, 'DRAFT', NOW(), NOW())"
        ),
        {"run": run_id, "m": material_id, "rd": required_date},
    )
    db.commit()
    result_id = int(
        db.execute(
            text("SELECT id FROM pln_mrp_result WHERE run_id = :r AND material_id = :m"),
            {"r": run_id, "m": material_id},
        ).scalar()
    )

    first = procurement_contract.create_purchase_plan_from_mrp(db, [result_id])
    db.commit()
    assert first["plan_no"].startswith("PP")

    plan = service.get_plan(db, first["plan_id"])
    # 按 source_reference_id 精确定位本次生成的明细，不依赖计划总条数
    items = [
        it
        for it in plan["items"]
        if it["source_type"] == "MRP" and it["source_reference_id"] == result_id
    ]
    assert len(items) == 1
    item = items[0]
    assert item["material_id"] == material_id
    assert item["required_qty"] == Decimal("30.0000")
    assert item["required_date"] == required_date

    # 幂等：再次受理同一结果，复用同一计划且不新增行
    second = procurement_contract.create_purchase_plan_from_mrp(db, [result_id])
    db.commit()
    assert second["plan_id"] == first["plan_id"]
    items2 = [
        it
        for it in service.get_plan(db, first["plan_id"])["items"]
        if it["source_type"] == "MRP" and it["source_reference_id"] == result_id
    ]
    assert len(items2) == 1


# ==================== 4. 从库存补库需求生成采购计划 ====================


def test_purchase_plan_from_replenishment(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """库存 REORDER 补库需求 → 采购计划（行 source_type=REORDER），重复受理幂等。"""
    material_id = _create_material(db, supply_type="BUY")
    warehouse_id = _create_warehouse(db)
    request_no = f"RPL{_tag()}"
    required_date = date.today() + timedelta(days=7)
    db.execute(
        text(
            "INSERT INTO inv_replenishment_request (request_no, material_id, warehouse_id, request_qty, "
            "current_qty, target_qty, required_date, source_type, status, created_at, updated_at) "
            "VALUES (:no, :m, :w, 25, 5, 30, :rd, 'REORDER', 'DRAFT', NOW(), NOW())"
        ),
        {"no": request_no, "m": material_id, "w": warehouse_id, "rd": required_date},
    )
    db.commit()
    request_id = int(
        db.execute(
            text("SELECT id FROM inv_replenishment_request WHERE request_no = :c"), {"c": request_no}
        ).scalar()
    )

    # 并行契约 `inventory.contract.get_replenishment_request` 尚未导出时，
    # 测试内临时补一个等价读取器，保证本模块逻辑仍被完整验证。
    if not hasattr(inventory_contract, "get_replenishment_request"):

        def _reader(_db: Session, rid: int):
            row = _db.execute(
                text("SELECT * FROM inv_replenishment_request WHERE id = :i"), {"i": rid}
            ).mappings().one()
            return dict(row)

        monkeypatch.setattr(
            inventory_contract, "get_replenishment_request", _reader, raising=False
        )

    first = procurement_contract.create_purchase_plan_from_replenishment(db, request_id)
    db.commit()
    plan = service.get_plan(db, first["plan_id"])
    # 按 source_reference_id 精确定位本次生成的明细，不依赖计划总条数
    # （共享库基线可能存在其他 DRAFT 计划明细，按来源精筛使断言不受基线影响）
    items = [
        it
        for it in plan["items"]
        if it["source_type"] == "REORDER" and it["source_reference_id"] == request_id
    ]
    assert len(items) == 1
    item = items[0]
    assert item["required_qty"] == Decimal("25.0000")
    assert item["material_id"] == material_id

    second = procurement_contract.create_purchase_plan_from_replenishment(db, request_id)
    db.commit()
    assert second["plan_id"] == first["plan_id"]
    # 幂等：重复受理同一来源不新增明细
    items2 = [
        it
        for it in service.get_plan(db, first["plan_id"])["items"]
        if it["source_type"] == "REORDER" and it["source_reference_id"] == request_id
    ]
    assert len(items2) == 1


# ==================== 5. 由计划生成订单 + 回写 ordered_qty ====================


def test_order_from_plan_writes_back_ordered_qty(db: Session) -> None:
    """按计划生成 DRAFT 订单：单价取供货价，预计到货日=下单日期+物料提前期，回写计划行已下单数量。"""
    material_id = _create_material(db, lead_time_days=7)
    supplier = _create_supplier(db)
    service.create_supplier_material(
        db,
        supplier_id=supplier["id"],
        material_id=material_id,
        supply_price=Decimal("7.50"),
    )
    plan = service.create_plan(
        db,
        items=[
            {
                "material_id": material_id,
                "required_qty": Decimal("20"),
                "required_date": date.today() + timedelta(days=10),
                "source_type": "MANUAL",
            }
        ],
    )
    db.commit()
    service.set_plan_status(db, plan["id"], "CONFIRMED")
    db.commit()

    order = service.create_order_from_plan(
        db, plan_id=plan["id"], supplier_id=supplier["id"]
    )
    db.commit()

    assert order["status"] == "DRAFT"
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == Decimal("20.0000")
    assert order["items"][0]["unit_price"] == Decimal("7.50")
    assert order["total_amount"] == Decimal("150.00")
    assert order["expected_date"] == order["order_date"] + timedelta(days=7)

    refreshed = service.get_plan(db, plan["id"])
    assert refreshed["items"][0]["ordered_qty"] == Decimal("20.0000")


def test_order_from_plan_uses_max_material_lead_time(db: Session) -> None:
    """多物料计划：预计到货日取各行物料提前期的最大值（来自 sys_material，非供货关系）。"""
    m_short = _create_material(db, lead_time_days=3)
    m_long = _create_material(db, lead_time_days=10)
    supplier = _create_supplier(db)
    plan = service.create_plan(
        db,
        items=[
            {
                "material_id": m_short,
                "required_qty": Decimal("5"),
                "required_date": date.today() + timedelta(days=20),
                "source_type": "MANUAL",
            },
            {
                "material_id": m_long,
                "required_qty": Decimal("8"),
                "required_date": date.today() + timedelta(days=20),
                "source_type": "MANUAL",
            },
        ],
    )
    db.commit()
    service.set_plan_status(db, plan["id"], "CONFIRMED")
    db.commit()

    order = service.create_order_from_plan(db, plan_id=plan["id"], supplier_id=supplier["id"])
    db.commit()

    assert order["expected_date"] == order["order_date"] + timedelta(days=10)


def test_order_from_plan_explicit_expected_date_wins(db: Session) -> None:
    """显式传入预计到货日时优先使用，不用提前期推算。"""
    material_id = _create_material(db, lead_time_days=10)
    supplier = _create_supplier(db)
    plan = service.create_plan(
        db,
        items=[
            {
                "material_id": material_id,
                "required_qty": Decimal("5"),
                "required_date": date.today() + timedelta(days=20),
                "source_type": "MANUAL",
            }
        ],
    )
    db.commit()
    service.set_plan_status(db, plan["id"], "CONFIRMED")
    db.commit()

    explicit = date.today() + timedelta(days=2)
    order = service.create_order_from_plan(
        db, plan_id=plan["id"], supplier_id=supplier["id"], expected_date=explicit
    )
    db.commit()

    assert order["expected_date"] == explicit


# ==================== 6. 到货确认（调用库存入库） ====================


def test_receipt_confirm_pushes_inbound_then_warehouse_confirm_increases_stock(
    db: Session,
) -> None:
    """到货确认：只推送待入库单（不改结存）、回写 received_qty、订单转 IN_PROGRESS；
    仓库管理人员指定仓库并确认后结存才增加。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)
    supplier = _create_supplier(db)
    order = service.create_order(
        db,
        supplier_id=supplier["id"],
        order_date=date.today(),
        expected_date=date.today() + timedelta(days=5),
        items=[{"material_id": material_id, "quantity": Decimal("100"), "unit_price": Decimal("5")}],
    )
    db.commit()
    service.set_order_status(db, order["id"], "CONFIRMED")
    db.commit()
    order_item_id = order["items"][0]["id"]

    receipt = service.create_receipt(
        db,
        purchase_order_id=order["id"],
        receipt_date=date.today(),
        items=[{"order_item_id": order_item_id, "quantity": Decimal("40")}],
    )
    db.commit()
    assert receipt["status"] == "DRAFT"

    confirmed = service.confirm_receipt(db, receipt["id"])
    db.commit()

    assert confirmed["status"] == "COMPLETED"
    # 业务确认不改结存，只登记待入库单（合格数量 = 到货数量）
    assert inventory_service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("0")
    pending = inventory_service.get_inout_status_map(
        db, [("procurement", "PURCHASE_RECEIPT", receipt["id"])]
    )[("procurement", "PURCHASE_RECEIPT", receipt["id"])]
    assert pending["op_type"] == "INBOUND"
    assert pending["status"] == "DRAFT"

    # 采购订单行已到货数量回写（直接读库校验）
    db.expire_all()
    received_qty = db.execute(
        text("SELECT received_qty FROM pur_order_item WHERE id = :i"), {"i": order_item_id}
    ).scalar()
    assert Decimal(str(received_qty)) == Decimal("40.0000")
    # 订单状态 → IN_PROGRESS
    assert service.get_order(db, order["id"])["status"] == "IN_PROGRESS"

    inventory_service.confirm_stock_operation(
        db, pending["operation_id"], warehouse_id=warehouse_id
    )
    db.commit()
    assert inventory_service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("40.0000")


def test_create_receipt_api_without_warehouse(
    client: TestClient, db: Session
) -> None:
    """回归：采购订单「生成到货单」不再传仓库，接口仍应成功（warehouse_id 为空）。"""
    material_id = _create_material(db)
    supplier = _create_supplier(db)
    order = service.create_order(
        db,
        supplier_id=supplier["id"],
        order_date=date.today(),
        expected_date=date.today() + timedelta(days=5),
        items=[{"material_id": material_id, "quantity": Decimal("10"), "unit_price": Decimal("1")}],
    )
    db.commit()
    service.set_order_status(db, order["id"], "CONFIRMED")
    db.commit()
    order_item_id = order["items"][0]["id"]

    created = client.post(
        "/api/v1/procurement/receipts",
        json={
            "purchase_order_id": order["id"],
            "receipt_date": date.today().isoformat(),
            "items": [{"order_item_id": order_item_id, "quantity": "10", "qualified_qty": "10"}],
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["code"] == 0, body
    assert body["data"]["warehouse_id"] is None

    # 确认到货：仍不改结存，只推送待入库单
    confirmed = client.post(
        f"/api/v1/procurement/receipts/{body['data']['id']}/confirm"
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["status"] == "COMPLETED"

    # 列表 / 详情接口遇到空仓库也不能报错
    listed = client.get("/api/v1/procurement/receipts?page=1&page_size=20")
    assert listed.status_code == 200, listed.text
    hit = [row for row in listed.json()["data"]["items"] if row["id"] == body["data"]["id"]]
    assert hit and hit[0]["warehouse_id"] is None
    detail = client.get(f"/api/v1/procurement/receipts/{body['data']['id']}")
    assert detail.status_code == 200, detail.text


# ==================== 7. 到货超量拒绝 ====================


def test_receipt_over_quantity_rejected(db: Session) -> None:
    """到货数量超过未到货数量：创建即拒绝（4004）。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)
    supplier = _create_supplier(db)
    order = service.create_order(
        db,
        supplier_id=supplier["id"],
        order_date=date.today(),
        expected_date=date.today() + timedelta(days=5),
        items=[{"material_id": material_id, "quantity": Decimal("10"), "unit_price": Decimal("1")}],
    )
    db.commit()
    service.set_order_status(db, order["id"], "CONFIRMED")
    db.commit()
    order_item_id = order["items"][0]["id"]

    with pytest.raises(BusinessException) as exc:
        service.create_receipt(
            db,
            purchase_order_id=order["id"],
            warehouse_id=warehouse_id,
            receipt_date=date.today(),
            items=[{"order_item_id": order_item_id, "quantity": Decimal("11")}],
        )
    assert exc.value.code == 4004
    db.rollback()


# ==================== 8. 供应商评价综合分 ====================


def test_supplier_evaluation_total_score(db: Session) -> None:
    """综合分 = (质量 + 交期 + 价格) / 3，四舍五入 4 位小数。"""
    supplier = _create_supplier(db)
    evaluator_id = _create_personnel(db)

    evaluation = service.create_evaluation(
        db,
        supplier_id=supplier["id"],
        quality_score=Decimal("90"),
        delivery_score=Decimal("80"),
        price_score=Decimal("70"),
        evaluator_id=evaluator_id,
    )
    db.commit()

    assert evaluation["total_score"] == Decimal("80.0000")
    assert evaluation["evaluator_name"] is not None

    # 分数越界返回 4000
    with pytest.raises(BusinessException) as exc:
        service.create_evaluation(
            db,
            supplier_id=supplier["id"],
            quality_score=Decimal("101"),
            delivery_score=Decimal("80"),
            price_score=Decimal("70"),
        )
    assert exc.value.code == 4000
    db.rollback()


# ==================== 9. 自动供应商评价 ====================


def test_auto_evaluation_computes_three_scores(db: Session) -> None:
    """自动评价：交期=按时到货率×100，质量=检验合格率×100，价格=100-偏离均价%。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)
    supplier_a = _create_supplier(db, name="自动评价供应商A")
    supplier_b = _create_supplier(db, name="自动评价供应商B")
    today = date.today()

    # 供应商A：订单单价 12，预计 today+5 到货
    order_a = service.create_order(
        db,
        supplier_id=supplier_a["id"],
        order_date=today,
        expected_date=today + timedelta(days=5),
        items=[{"material_id": material_id, "quantity": Decimal("200"), "unit_price": Decimal("12")}],
    )
    db.commit()
    service.set_order_status(db, order_a["id"], "CONFIRMED")
    db.commit()
    order_item_a = order_a["items"][0]["id"]

    # 到货1：提前 3 天（按时），到货 100 合格 90
    r1 = service.create_receipt(
        db,
        purchase_order_id=order_a["id"],
        warehouse_id=warehouse_id,
        receipt_date=today + timedelta(days=3),
        items=[{"order_item_id": order_item_a, "quantity": Decimal("100"), "qualified_qty": Decimal("90")}],
    )
    db.commit()
    service.confirm_receipt(db, r1["id"])
    db.commit()
    # 到货2：逾期 5 天（不按时），到货 100 合格 100
    r2 = service.create_receipt(
        db,
        purchase_order_id=order_a["id"],
        warehouse_id=warehouse_id,
        receipt_date=today + timedelta(days=10),
        items=[{"order_item_id": order_item_a, "quantity": Decimal("100"), "qualified_qty": Decimal("100")}],
    )
    db.commit()
    service.confirm_receipt(db, r2["id"])
    db.commit()

    # 供应商B：同物料订单单价 8（市场参照价），仅确认订单即可参与价格统计
    order_b = service.create_order(
        db,
        supplier_id=supplier_b["id"],
        order_date=today,
        expected_date=today + timedelta(days=5),
        items=[{"material_id": material_id, "quantity": Decimal("50"), "unit_price": Decimal("8")}],
    )
    db.commit()
    service.set_order_status(db, order_b["id"], "CONFIRMED")
    db.commit()

    result = service.auto_evaluate_supplier(db, supplier_id=supplier_a["id"])
    db.commit()

    # 交期：2 单到货 1 单按时 → 0.5 × 100 = 50
    assert result["delivery_score"] == Decimal("50.0000")
    assert result["receipt_total"] == 2
    assert result["receipt_on_time"] == 1
    # 质量：(90+100)/200 = 0.95 × 100 = 95
    assert result["quality_score"] == Decimal("95.0000")
    # 价格：市场均价 (12+8)/2=10，A 偏离 (12-10)/10=+20% → 100-20 = 80
    assert result["price_deviation_pct"] == Decimal("20.0000")
    assert result["price_score"] == Decimal("80.0000")
    # 综合：(50+95+80)/3 = 75
    assert result["total_score"] == Decimal("75.0000")
    assert result["scored_dimensions"] == 3
    assert result["remark"].startswith("[自动评价]")


def test_auto_evaluation_without_business_data_rejected(db: Session) -> None:
    """无任何到货/订单数据的供应商：自动评价返回 4000。"""
    supplier = _create_supplier(db, name="无业务供应商")
    with pytest.raises(BusinessException) as exc:
        service.auto_evaluate_supplier(db, supplier_id=supplier["id"])
    assert exc.value.code == 4000
    db.rollback()


def test_auto_evaluation_api(client: TestClient, db: Session) -> None:
    """自动评价接口：POST /evaluations/auto 返回三项得分与计算依据。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)
    supplier = _create_supplier(db, name="接口自动评价供应商")
    today = date.today()
    order = service.create_order(
        db,
        supplier_id=supplier["id"],
        order_date=today,
        expected_date=today + timedelta(days=5),
        items=[{"material_id": material_id, "quantity": Decimal("10"), "unit_price": Decimal("9")}],
    )
    db.commit()
    service.set_order_status(db, order["id"], "CONFIRMED")
    db.commit()
    receipt = service.create_receipt(
        db,
        purchase_order_id=order["id"],
        warehouse_id=warehouse_id,
        receipt_date=today + timedelta(days=4),
        items=[{"order_item_id": order["items"][0]["id"], "quantity": Decimal("10")}],
    )
    db.commit()
    service.confirm_receipt(db, receipt["id"])
    db.commit()

    resp = client.post(
        "/api/v1/procurement/evaluations/auto", json={"supplier_id": supplier["id"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["delivery_score"] == "100.0000"  # 唯一一单按时
    assert data["quality_score"] == "100.0000"  # qualified_qty 默认 = quantity
    assert data["remark"].startswith("[自动评价]")
    assert data["on_time_rate"] is not None
    assert data["receipt_total"] == 1