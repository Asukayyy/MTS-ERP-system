"""sales 模块核心业务测试（使用本机真实 MySQL）。

覆盖：
1. 客户新增（含编码唯一冲突 2001）
2. 订单新增自动计算行金额 / 总金额，确认订单
3. 确认订单拒绝非成品物料
4. 发货单确认：扣减库存 + 写 SALES_SHIPMENT 流水 + 回写订单行已发数量
5. 发货数量超过未发数量抛 2003
6. 退货单确认：回增库存 + 写 SALES_RETURN 流水
7. contract 未交付需求行可被其它模块读取

所有业务编码均带随机后缀，保证可重复运行。
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.inventory import contract as inventory_contract
from app.modules.sales import contract as sales_contract

SALES = "/api/v1/sales"
INVENTORY = "/api/v1/inventory"


@pytest.fixture()
def db() -> Session:
    """真实 MySQL 会话；测试结束回滚残留。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _tag() -> str:
    """生成短随机后缀，避免编码冲突。"""
    return uuid.uuid4().hex[:10].upper()


def _refresh(db: Session) -> None:
    """结束当前事务，确保后续查询能看到接口已提交的数据。"""
    db.rollback()


def _create_material(
    db: Session, *, material_type: str = "FINISHED", status: str = "ACTIVE"
) -> int:
    """直接写入统一物料主数据 `sys_material`，返回物料ID。"""
    code = f"MAT{_tag()}"
    supply_type = "MAKE" if material_type in ("FINISHED", "SEMI") else "BUY"
    db.execute(
        text(
            "INSERT INTO sys_material (material_code, material_name, material_type, "
            "supply_type, unit_code, lead_time_days, safety_stock, standard_cost, status, "
            "created_at, updated_at) "
            "VALUES (:code, :name, :mtype, :supply, 'PCS', 0, 0, 0, :status, NOW(), NOW())"
        ),
        {
            "code": code,
            "name": f"销售测试物料{code}",
            "mtype": material_type,
            "supply": supply_type,
            "status": status,
        },
    )
    db.commit()
    return int(
        db.execute(
            text("SELECT id FROM sys_material WHERE material_code = :c"), {"c": code}
        ).scalar()
    )


def _create_warehouse(client: TestClient) -> int:
    """经 inventory 接口建仓库，返回仓库ID。"""
    response = client.post(
        f"{INVENTORY}/warehouses",
        json={"warehouse_code": f"WH{_tag()}", "warehouse_name": "销售测试仓"},
    )
    assert response.json()["code"] == 0
    return int(response.json()["data"]["id"])


def _create_customer(client: TestClient, code: str | None = None) -> dict:
    """经 sales 接口建客户，返回客户数据。"""
    response = client.post(
        f"{SALES}/customers",
        json={"customer_code": code or f"CUS{_tag()}", "customer_name": "销售测试客户"},
    )
    assert response.json()["code"] == 0, response.json()
    return response.json()["data"]


def _set_stock(db: Session, material_id: int, warehouse_id: int, qty: str) -> None:
    """经库存契约入库，构造初始库存。"""
    _refresh(db)  # 结束旧事务快照，确保能看到接口刚创建的仓库
    inventory_contract.increase_stock(
        db,
        material_id=material_id,
        quantity=Decimal(qty),
        warehouse_id=warehouse_id,
        source_module="sales",
        source_type="MANUAL",
    )
    db.commit()


def _create_confirmed_order(
    client: TestClient,
    customer_id: int,
    material_id: int,
    *,
    quantity: str = "30",
    unit_price: str = "10",
) -> dict:
    """建订单并确认，返回订单详情。"""
    response = client.post(
        f"{SALES}/orders",
        json={
            "customer_id": customer_id,
            "order_date": date.today().isoformat(),
            "delivery_date": date.today().isoformat(),
            "items": [
                {"material_id": material_id, "quantity": quantity, "unit_price": unit_price}
            ],
        },
    )
    assert response.json()["code"] == 0, response.json()
    order_id = response.json()["data"]["id"]
    confirmed = client.patch(
        f"{SALES}/orders/{order_id}/status", json={"status": "CONFIRMED"}
    )
    assert confirmed.json()["code"] == 0, confirmed.json()
    return confirmed.json()["data"]


# ==================== 客户 ====================


def test_create_customer_and_duplicate_code(client: TestClient) -> None:
    """客户新增成功；重复编码返回 2001，停用后状态为 INACTIVE。"""
    code = f"CUS{_tag()}"
    customer = _create_customer(client, code)
    assert customer["status"] == "ACTIVE"
    assert customer["customer_code"] == code

    duplicated = client.post(
        f"{SALES}/customers",
        json={"customer_code": code, "customer_name": "重复客户"},
    )
    assert duplicated.json()["code"] == 2001

    deactivated = client.patch(
        f"{SALES}/customers/{customer['id']}/status", json={"status": "INACTIVE"}
    )
    assert deactivated.json()["code"] == 0
    assert deactivated.json()["data"]["status"] == "INACTIVE"


# ==================== 订单 ====================


def test_order_create_and_confirm_computes_amounts(
    client: TestClient, db: Session
) -> None:
    """订单新增按 quantity*unit_price 计算行金额与总金额，确认后状态为 CONFIRMED。"""
    material_id = _create_material(db)
    customer = _create_customer(client)

    response = client.post(
        f"{SALES}/orders",
        json={
            "customer_id": customer["id"],
            "order_date": date.today().isoformat(),
            "delivery_date": date.today().isoformat(),
            "items": [
                {"material_id": material_id, "quantity": "10", "unit_price": "12.50"},
                {"material_id": material_id, "quantity": "2", "unit_price": "100"},
            ],
        },
    )
    body = response.json()
    assert body["code"] == 0, body
    order = body["data"]
    assert Decimal(str(order["total_amount"])) == Decimal("325.00")
    amounts = sorted(Decimal(str(item["amount"])) for item in order["items"])
    assert amounts == [Decimal("125.00"), Decimal("200.00")]

    confirmed = client.patch(
        f"{SALES}/orders/{order['id']}/status", json={"status": "CONFIRMED"}
    )
    assert confirmed.json()["code"] == 0
    assert confirmed.json()["data"]["status"] == "CONFIRMED"


def test_confirm_order_rejects_non_finished_material(
    client: TestClient, db: Session
) -> None:
    """确认订单时，采购件（非成品）物料被拒绝，订单保持 DRAFT。"""
    material_id = _create_material(db, material_type="PURCHASED")
    customer = _create_customer(client)
    response = client.post(
        f"{SALES}/orders",
        json={
            "customer_id": customer["id"],
            "order_date": date.today().isoformat(),
            "delivery_date": date.today().isoformat(),
            "items": [{"material_id": material_id, "quantity": "5", "unit_price": "3"}],
        },
    )
    order_id = response.json()["data"]["id"]

    confirmed = client.patch(
        f"{SALES}/orders/{order_id}/status", json={"status": "CONFIRMED"}
    )
    assert confirmed.json()["code"] == 2000
    detail = client.get(f"{SALES}/orders/{order_id}").json()["data"]
    assert detail["status"] == "DRAFT"


# ==================== 发货 ====================


def test_shipment_confirm_decreases_stock_and_updates_delivered(
    client: TestClient, db: Session
) -> None:
    """发货确认：库存减少、写 SALES_SHIPMENT 流水、订单行已发数量回写、订单转 IN_PROGRESS。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    _set_stock(db, material_id, warehouse_id, "100")
    customer = _create_customer(client)
    order = _create_confirmed_order(client, customer["id"], material_id, quantity="30")
    order_item_id = order["items"][0]["id"]

    created = client.post(
        f"{SALES}/shipments",
        json={
            "order_id": order["id"],
            "shipment_date": date.today().isoformat(),
            "items": [
                {
                    "order_item_id": order_item_id,
                    "warehouse_id": warehouse_id,
                    "quantity": "20",
                }
            ],
        },
    )
    assert created.json()["code"] == 0, created.json()
    shipment = created.json()["data"]
    assert shipment["status"] == "DRAFT"

    confirmed = client.post(f"{SALES}/shipments/{shipment['id']}/confirm")
    assert confirmed.json()["code"] == 0, confirmed.json()
    assert confirmed.json()["data"]["status"] == "COMPLETED"

    _refresh(db)
    assert inventory_contract.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("80.0000")

    ledger = db.execute(
        text(
            "SELECT COUNT(*) FROM inv_transaction "
            "WHERE source_type = 'SALES_SHIPMENT' AND source_reference_id = :sid"
        ),
        {"sid": shipment["id"]},
    ).scalar()
    assert ledger == 1

    detail = client.get(f"{SALES}/orders/{order['id']}").json()["data"]
    assert Decimal(str(detail["items"][0]["delivered_qty"])) == Decimal("20")
    assert detail["status"] == "IN_PROGRESS"


def test_shipment_over_quantity_rejected(client: TestClient, db: Session) -> None:
    """发货数量超过未发数量时返回 2003。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    customer = _create_customer(client)
    order = _create_confirmed_order(client, customer["id"], material_id, quantity="30")

    response = client.post(
        f"{SALES}/shipments",
        json={
            "order_id": order["id"],
            "shipment_date": date.today().isoformat(),
            "items": [
                {
                    "order_item_id": order["items"][0]["id"],
                    "warehouse_id": warehouse_id,
                    "quantity": "999",
                }
            ],
        },
    )
    assert response.json()["code"] == 2003


# ==================== 退货 ====================


def test_return_confirm_increases_stock_and_writes_ledger(
    client: TestClient, db: Session
) -> None:
    """退货确认：库存回增、写 SALES_RETURN 流水，状态置 COMPLETED。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    customer = _create_customer(client)

    created = client.post(
        f"{SALES}/returns",
        json={
            "customer_id": customer["id"],
            "return_date": date.today().isoformat(),
            "reason": "质量不达标",
            "items": [
                {
                    "material_id": material_id,
                    "warehouse_id": warehouse_id,
                    "quantity": "5",
                    "quality_status": "DEFECTIVE",
                }
            ],
        },
    )
    assert created.json()["code"] == 0, created.json()
    sales_return = created.json()["data"]
    assert sales_return["status"] == "DRAFT"

    confirmed = client.post(f"{SALES}/returns/{sales_return['id']}/confirm")
    assert confirmed.json()["code"] == 0, confirmed.json()
    assert confirmed.json()["data"]["status"] == "COMPLETED"
    assert confirmed.json()["data"]["items"][0]["quality_status"] == "DEFECTIVE"

    _refresh(db)
    assert inventory_contract.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("5.0000")
    ledger = db.execute(
        text(
            "SELECT COUNT(*) FROM inv_transaction "
            "WHERE source_type = 'SALES_RETURN' AND source_reference_id = :rid"
        ),
        {"rid": sales_return["id"]},
    ).scalar()
    assert ledger == 1


# ==================== 跨模块契约 ====================


def test_contract_open_order_demand(client: TestClient, db: Session) -> None:
    """契约：已确认订单的未交付需求行可被 Planning 读取。"""
    material_id = _create_material(db)
    customer = _create_customer(client)
    order = _create_confirmed_order(client, customer["id"], material_id, quantity="7")

    _refresh(db)
    demands = sales_contract.get_open_order_demand(db)
    matched = [d for d in demands if d["order_id"] == order["id"]]
    assert matched, "已确认订单应出现在未交付需求中"
    assert matched[0]["material_id"] == material_id
    assert matched[0]["quantity"] == Decimal("7.0000")
    assert sales_contract.get_open_order_qty(db, material_id) >= Decimal("7")
    assert sales_contract.get_customer_name(db, customer["id"]) == "销售测试客户"