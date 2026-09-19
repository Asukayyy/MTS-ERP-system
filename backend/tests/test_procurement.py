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
from app.core.database import SessionLocal
from app.modules.inventory import contract as inventory_contract
from app.modules.inventory import service as inventory_service
from app.modules.procurement import contract as procurement_contract
from app.modules.procurement import service


@pytest.fixture()
def db() -> Session:
    """真实 MySQL 会话；测试内自行 commit，结束回滚残留。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


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
        lead_time_days=5,
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
    assert len(plan["items"]) == 1
    item = plan["items"][0]
    assert item["material_id"] == material_id
    assert item["required_qty"] == Decimal("30.0000")
    assert item["required_date"] == required_date
    assert item["source_type"] == "MRP"
    assert item["source_reference_id"] == result_id

    # 幂等：再次受理同一结果，复用同一计划且不新增行
    second = procurement_contract.create_purchase_plan_from_mrp(db, [result_id])
    db.commit()
    assert second["plan_id"] == first["plan_id"]
    assert len(service.get_plan(db, first["plan_id"])["items"]) == 1


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
    assert len(plan["items"]) == 1
    item = plan["items"][0]
    assert item["source_type"] == "REORDER"
    assert item["source_reference_id"] == request_id
    assert item["required_qty"] == Decimal("25.0000")
    assert item["material_id"] == material_id

    second = procurement_contract.create_purchase_plan_from_replenishment(db, request_id)
    db.commit()
    assert second["plan_id"] == first["plan_id"]
    assert len(service.get_plan(db, first["plan_id"])["items"]) == 1


# ==================== 5. 由计划生成订单 + 回写 ordered_qty ====================


def test_order_from_plan_writes_back_ordered_qty(db: Session) -> None:
    """按计划生成 DRAFT 订单：单价取供货价，回写计划行已下单数量。"""
    material_id = _create_material(db)
    supplier = _create_supplier(db)
    service.create_supplier_material(
        db,
        supplier_id=supplier["id"],
        material_id=material_id,
        supply_price=Decimal("7.50"),
        lead_time_days=3,
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
    assert order["expected_date"] == order["order_date"] + timedelta(days=3)

    refreshed = service.get_plan(db, plan["id"])
    assert refreshed["items"][0]["ordered_qty"] == Decimal("20.0000")


# ==================== 6. 到货确认（调用库存入库） ====================


def test_receipt_confirm_increases_stock_and_writes_ledger(db: Session) -> None:
    """到货确认：库存增加、写 PURCHASE_RECEIPT 流水、回写 received_qty、订单转 IN_PROGRESS。"""
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
        warehouse_id=warehouse_id,
        receipt_date=date.today(),
        items=[{"order_item_id": order_item_id, "quantity": Decimal("40")}],
    )
    db.commit()
    assert receipt["status"] == "DRAFT"

    confirmed = service.confirm_receipt(db, receipt["id"])
    db.commit()

    assert confirmed["status"] == "COMPLETED"
    # 库存增加（qualified_qty 默认 = quantity）
    assert inventory_service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("40.0000")
    # 采购订单行已到货数量回写（直接读库校验）
    db.expire_all()
    received_qty = db.execute(
        text("SELECT received_qty FROM pur_order_item WHERE id = :i"), {"i": order_item_id}
    ).scalar()
    assert Decimal(str(received_qty)) == Decimal("40.0000")
    # 订单状态 → IN_PROGRESS
    assert service.get_order(db, order["id"])["status"] == "IN_PROGRESS"

    ledger = db.execute(
        text(
            "SELECT source_module, source_type, quantity_change, quantity_after, unit_cost, source_no "
            "FROM inv_transaction WHERE source_reference_id = :rid AND source_type = 'PURCHASE_RECEIPT'"
        ),
        {"rid": receipt["id"]},
    ).mappings().all()
    assert len(ledger) == 1
    assert ledger[0]["source_module"] == "procurement"
    assert Decimal(str(ledger[0]["quantity_change"])) == Decimal("40.0000")
    assert Decimal(str(ledger[0]["quantity_after"])) == Decimal("40.0000")
    assert Decimal(str(ledger[0]["unit_cost"])) == Decimal("5.00")
    assert ledger[0]["source_no"] == receipt["receipt_no"]


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