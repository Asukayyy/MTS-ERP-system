"""inventory 模块核心业务测试（使用本机真实 MySQL）。

覆盖：
1. 入库+出库 同时改变结存并写流水，`quantity_after` 正确
2. 超量出库抛 5001，且结存不变
3. 移库原子写 TRANSFER_OUT + TRANSFER_IN
4. 盘点确认写 ADJUST 流水
5. 低于订货点触发补库建议
6. 创建补库需求单
7. 契约 `get_replenishment_request` 返回纯字典
8. 期初库存导入预览不写库、确认写结存与流水、未知编码进入 errors

所有业务编码均带随机后缀，保证可重复运行。
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.core.database import SessionLocal
from app.modules.inventory import contract as inventory_contract
from app.modules.inventory import service


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
    """生成短随机后缀，避免编码冲突。"""
    return uuid.uuid4().hex[:10].upper()


def _create_material_with_code(
    db: Session, safety_stock: Decimal = Decimal("0")
) -> tuple[int, str]:
    """直接写入物料主数据，返回 (物料ID, 物料编码)。"""
    code = f"ITM{_tag()}"
    db.execute(
        text(
            "INSERT INTO sys_material (material_code, material_name, material_type, "
            "supply_type, unit_code, lead_time_days, safety_stock, standard_cost, status, "
            "created_at, updated_at) "
            "VALUES (:code, :name, 'PURCHASED', 'BUY', 'PCS', 0, :safety, 0, 'ACTIVE', "
            "NOW(), NOW())"
        ),
        {"code": code, "name": f"库存测试物料{code}", "safety": safety_stock},
    )
    db.commit()
    material_id = int(
        db.execute(text("SELECT id FROM sys_material WHERE material_code = :c"), {"c": code}).scalar()
    )
    return material_id, code


def _create_material(db: Session, safety_stock: Decimal = Decimal("0")) -> int:
    """直接写入物料主数据，返回物料ID（避免跨模块 import system 的 models）。"""
    return _create_material_with_code(db, safety_stock)[0]


def _create_warehouse(db: Session) -> int:
    warehouse = service.create_warehouse(
        db, warehouse_code=f"WH{_tag()}", warehouse_name=f"测试仓库{_tag()}"
    )
    db.commit()
    return warehouse.id


def test_increase_then_decrease_updates_balance_and_writes_ledger(db: Session) -> None:
    """入库 → 出库：结存正确，流水各一条且 quantity_after 正确。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)

    inc = service.increase_stock(
        db,
        material_id=material_id,
        quantity=Decimal("100"),
        warehouse_id=warehouse_id,
        source_module="inventory",
        source_type="MANUAL",
    )
    db.commit()
    assert inc["quantity_after"] == Decimal("100.0000")
    assert inc["transaction_no"].startswith("INV")

    dec = service.decrease_stock(
        db,
        material_id=material_id,
        quantity=Decimal("30"),
        warehouse_id=warehouse_id,
        source_module="inventory",
        source_type="MANUAL",
    )
    db.commit()
    assert dec["quantity_after"] == Decimal("70.0000")
    assert service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("70.0000")

    rows, total = service.list_transactions(
        db, material_id=material_id, warehouse_id=warehouse_id, page_size=10
    )
    assert total == 2
    by_type = {row["transaction_type"]: row for row in rows}
    assert by_type["IN"]["quantity_change"] == Decimal("100.0000")
    assert by_type["IN"]["quantity_after"] == Decimal("100.0000")
    assert by_type["OUT"]["quantity_change"] == Decimal("-30.0000")
    assert by_type["OUT"]["quantity_after"] == Decimal("70.0000")


def test_decrease_beyond_stock_raises_5001_and_keeps_balance(db: Session) -> None:
    """超量出库：抛 5001，结存与流水都不变（禁止负库存）。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)
    service.increase_stock(
        db,
        material_id=material_id,
        quantity=Decimal("5"),
        warehouse_id=warehouse_id,
        source_module="inventory",
        source_type="MANUAL",
    )
    db.commit()

    with pytest.raises(BusinessException) as exc:
        service.decrease_stock(
            db,
            material_id=material_id,
            quantity=Decimal("6"),
            warehouse_id=warehouse_id,
            source_module="inventory",
            source_type="MANUAL",
        )
    assert exc.value.code == 5001
    db.rollback()

    assert service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("5.0000")
    _, total = service.list_transactions(
        db, material_id=material_id, warehouse_id=warehouse_id, page_size=10
    )
    assert total == 1


def test_transfer_writes_transfer_out_and_in_atomically(db: Session) -> None:
    """移库确认：源写 TRANSFER_OUT、目标写 TRANSFER_IN，两侧结存同步变化。"""
    material_id = _create_material(db)
    source_wh = _create_warehouse(db)
    target_wh = _create_warehouse(db)
    service.increase_stock(
        db,
        material_id=material_id,
        quantity=Decimal("20"),
        warehouse_id=source_wh,
        source_module="inventory",
        source_type="MANUAL",
    )
    db.commit()

    transfer = service.create_transfer(
        db,
        from_warehouse_id=source_wh,
        to_warehouse_id=target_wh,
        transfer_date=date.today(),
        items=[{"material_id": material_id, "quantity": Decimal("8")}],
    )
    db.commit()
    transfer = service.confirm_transfer(db, transfer.id)
    db.commit()

    assert transfer.status == "COMPLETED"
    assert service.get_on_hand_qty(db, material_id, source_wh) == Decimal("12.0000")
    assert service.get_on_hand_qty(db, material_id, target_wh) == Decimal("8.0000")
    rows, _ = service.list_transactions(
        db, material_id=material_id, source_type="TRANSFER", page_size=10
    )
    assert sorted(row["transaction_type"] for row in rows) == [
        "TRANSFER_IN",
        "TRANSFER_OUT",
    ]

    # 原子性：库存不足时整单不落流水、不改任何结存
    failing = service.create_transfer(
        db,
        from_warehouse_id=source_wh,
        to_warehouse_id=target_wh,
        transfer_date=date.today(),
        items=[{"material_id": material_id, "quantity": Decimal("999")}],
    )
    db.commit()
    with pytest.raises(BusinessException) as exc:
        service.confirm_transfer(db, failing.id)
    assert exc.value.code == 5001
    db.rollback()
    assert service.get_on_hand_qty(db, material_id, source_wh) == Decimal("12.0000")
    assert service.get_on_hand_qty(db, material_id, target_wh) == Decimal("8.0000")


def test_stocktake_confirm_writes_adjust(db: Session) -> None:
    """盘点确认：差异写 ADJUST 流水，结存调整到实盘数。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)
    service.increase_stock(
        db,
        material_id=material_id,
        quantity=Decimal("10"),
        warehouse_id=warehouse_id,
        source_module="inventory",
        source_type="MANUAL",
    )
    db.commit()

    stocktake = service.create_stocktake(
        db,
        warehouse_id=warehouse_id,
        stocktake_date=date.today(),
        items=[{"material_id": material_id, "actual_qty": Decimal("7")}],
    )
    db.commit()

    stocktake = service.get_stocktake(db, stocktake.id)
    assert stocktake.items[0].book_qty == Decimal("10.0000")

    stocktake = service.confirm_stocktake(db, stocktake.id)
    db.commit()
    assert stocktake.status == "COMPLETED"
    assert stocktake.items[0].difference == Decimal("-3.0000")
    assert service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("7.0000")

    rows, _ = service.list_transactions(
        db, material_id=material_id, transaction_type="ADJUST", page_size=10
    )
    assert len(rows) == 1
    assert rows[0]["quantity_change"] == Decimal("-3.0000")
    assert rows[0]["quantity_after"] == Decimal("7.0000")


def test_reorder_rule_suggestion_triggers_below_point(db: Session) -> None:
    """现存量为 3、订货点为 10：应产生一条补库建议。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)
    service.increase_stock(
        db,
        material_id=material_id,
        quantity=Decimal("3"),
        warehouse_id=warehouse_id,
        source_module="inventory",
        source_type="MANUAL",
    )
    service.create_reorder_rule(
        db,
        material_id=material_id,
        warehouse_id=warehouse_id,
        reorder_point=Decimal("10"),
        reorder_quantity=Decimal("20"),
    )
    db.commit()

    suggestions = [
        item
        for item in service.list_reorder_suggestions(db)
        if item["material_id"] == material_id and item["warehouse_id"] == warehouse_id
    ]
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion["current_qty"] == Decimal("3.0000")
    assert suggestion["reorder_point"] == Decimal("10.0000")
    assert suggestion["suggested_qty"] == Decimal("20.0000")
    assert suggestion["target_qty"] == Decimal("23.0000")


def test_create_replenishment_request(db: Session) -> None:
    """创建补库需求单：状态 DRAFT，数量与来源正确，单号自动生成。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)

    result = service.create_replenishment_request(
        db,
        material_id=material_id,
        warehouse_id=warehouse_id,
        request_qty=Decimal("15"),
        required_date=date.today(),
        source_type="REORDER",
        current_qty=Decimal("3"),
        target_qty=Decimal("18"),
    )
    db.commit()

    assert result["request_no"].startswith("RPL")
    request = service.get_replenishment_request(db, result["id"])
    assert request.status == "DRAFT"
    assert request.request_qty == Decimal("15.0000")
    assert request.current_qty == Decimal("3.0000")
    assert request.source_type == "REORDER"


def test_warehouse_api_create_and_list(client: TestClient) -> None:
    """接口层：新增仓库后可按关键字查询到。"""
    code = f"WH{_tag()}"
    response = client.post(
        "/api/v1/inventory/warehouses",
        json={"warehouse_code": code, "warehouse_name": "接口测试仓"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    warehouse_id = body["data"]["id"]

    listed = client.get("/api/v1/inventory/warehouses", params={"keyword": code})
    assert listed.json()["code"] == 0
    assert any(item["id"] == warehouse_id for item in listed.json()["data"]["items"])


def test_stock_increase_api(client: TestClient, db: Session) -> None:
    """接口层：手工入库返回统一响应且结存正确。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)
    response = client.post(
        "/api/v1/inventory/stock/increase",
        json={
            "material_id": material_id,
            "warehouse_id": warehouse_id,
            "quantity": "20",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert Decimal(str(body["data"]["quantity_after"])) == Decimal("20.0000")


# ==================== 契约：补库需求只读读取 ====================


def test_contract_get_replenishment_request_returns_dict(db: Session) -> None:
    """契约 `get_replenishment_request` 返回纯字典且字段齐全；不存在返回 None。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(db)
    created = service.create_replenishment_request(
        db,
        material_id=material_id,
        warehouse_id=warehouse_id,
        request_qty=Decimal("9"),
        required_date=date.today(),
        source_type="REORDER",
        current_qty=Decimal("1"),
        target_qty=Decimal("10"),
    )
    db.commit()

    data = inventory_contract.get_replenishment_request(db, created["id"])
    assert isinstance(data, dict)
    assert set(data) == {
        "id",
        "request_no",
        "material_id",
        "warehouse_id",
        "request_qty",
        "current_qty",
        "target_qty",
        "required_date",
        "source_type",
        "status",
    }
    assert data["id"] == created["id"]
    assert data["request_no"] == created["request_no"]
    assert data["material_id"] == material_id
    assert data["warehouse_id"] == warehouse_id
    assert data["request_qty"] == Decimal("9.0000")
    assert data["current_qty"] == Decimal("1.0000")
    assert data["target_qty"] == Decimal("10.0000")
    assert data["required_date"] == date.today()
    assert data["source_type"] == "REORDER"
    assert data["status"] == "DRAFT"

    assert inventory_contract.get_replenishment_request(db, -1) is None


# ==================== 期初库存导入（规格 §37） ====================


def test_initial_stock_preview_writes_nothing(client: TestClient, db: Session) -> None:
    """预览接口只校验不写库：未知编码进入 errors，且结存/流水两张表行数不变。"""
    _material_id, code = _create_material_with_code(db)
    warehouse_id = _create_warehouse(db)
    unknown_code = f"UNKNOWN{_tag()}"

    db.rollback()
    balance_before = int(db.execute(text("SELECT COUNT(*) FROM inv_balance")).scalar())
    txn_before = int(db.execute(text("SELECT COUNT(*) FROM inv_transaction")).scalar())

    response = client.post(
        "/api/v1/inventory/import/initial-stock/preview",
        json={
            "warehouse_id": warehouse_id,
            "rows": [
                {"material_code": code, "quantity": "25"},
                {"material_code": unknown_code, "quantity": "5"},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["summary"] == {"total": 2, "valid": 1, "invalid": 1}
    statuses = {row["material_code"]: row["status"] for row in data["rows"]}
    assert statuses[code] == "VALID"
    assert statuses[unknown_code] == "INVALID"
    assert any(err["material_code"] == unknown_code for err in data["errors"])

    db.rollback()
    assert int(db.execute(text("SELECT COUNT(*) FROM inv_balance")).scalar()) == balance_before
    assert int(db.execute(text("SELECT COUNT(*) FROM inv_transaction")).scalar()) == txn_before


def test_initial_stock_confirm_creates_balance_and_ledger(client: TestClient, db: Session) -> None:
    """确认导入：有效行写结存 + 真实流水；未知编码只报错不导入。"""
    material_id, code = _create_material_with_code(db)
    warehouse_id = _create_warehouse(db)
    unknown_code = f"UNKNOWN{_tag()}"

    response = client.post(
        "/api/v1/inventory/import/initial-stock/confirm",
        json={
            "warehouse_id": warehouse_id,
            "rows": [
                {"material_code": code, "quantity": "3000"},
                {"material_code": unknown_code, "quantity": "5"},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["imported"] == 1
    assert any(err["material_code"] == unknown_code for err in body["data"]["errors"])

    assert service.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("3000.0000")
    assert (
        int(
            db.execute(
                text("SELECT COUNT(*) FROM inv_balance WHERE warehouse_id = :w"),
                {"w": warehouse_id},
            ).scalar()
        )
        == 1
    )

    rows, total = service.list_transactions(
        db, material_id=material_id, warehouse_id=warehouse_id, page_size=10
    )
    assert total == 1
    assert rows[0]["transaction_type"] == "IN"
    assert rows[0]["source_module"] == "inventory"
    assert rows[0]["source_type"] == "MANUAL"
    assert rows[0]["quantity_change"] == Decimal("3000.0000")
    assert rows[0]["remark"] == "课程附录1期初库存导入"