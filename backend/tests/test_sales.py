"""sales 模块核心业务测试（使用本机真实 MySQL）。

覆盖：
1. 客户新增（含编码唯一冲突 2001）
2. 订单新增自动计算行金额 / 总金额，确认订单
3. 确认订单拒绝非成品物料
4. 发货单确认：扣减库存 + 写 SALES_SHIPMENT 流水 + 回写订单行已发数量
5. 发货数量超过未发数量抛 2003
6. 退货单确认：回增库存 + 写 SALES_RETURN 流水
7. contract 未交付需求行可被其它模块读取
8. 退货数量超过可退额度抛 2007（草稿占用额度、取消后释放）
9. 预测状态机与"DRAFT 才可编辑"
10. 业务单号取 MAX+1，删单后不重号
11. 报表接口日期参数可省

所有业务编码均带随机后缀，保证可重复运行。
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.inventory import contract as inventory_contract
from app.modules.inventory import service as inventory_service
from app.modules.sales import contract as sales_contract

SALES = "/api/v1/sales"
INVENTORY = "/api/v1/inventory"


def _tag() -> str:
    """生成短随机后缀，避免编码冲突。"""
    return uuid.uuid4().hex[:10].upper()


def _refresh(db: Session) -> None:
    """结束当前事务，确保后续查询能看到接口已提交的数据。"""
    db.rollback()


def _create_material(
    db: Session,
    *,
    material_type: str = "FINISHED",
    status: str = "ACTIVE",
    sales_category: str | None = None,
) -> int:
    """直接写入统一物料主数据 `sys_material`，返回物料ID。

    `sales_category` 默认按物料类型推导：成品视为可售整机（MACHINE），
    其余视为内部件（INTERNAL）——销售订单确认只接受 MACHINE / SPARE。
    """
    code = f"MAT{_tag()}"
    supply_type = "MAKE" if material_type in ("FINISHED", "SEMI") else "BUY"
    if sales_category is None:
        sales_category = "MACHINE" if material_type == "FINISHED" else "INTERNAL"
    db.execute(
        text(
            "INSERT INTO sys_material (material_code, material_name, material_type, "
            "supply_type, unit_code, lead_time_days, safety_stock, standard_cost, "
            "sales_category, status, created_at, updated_at) "
            "VALUES (:code, :name, :mtype, :supply, 'PCS', 0, 0, 0, :category, :status, NOW(), NOW())"
        ),
        {
            "code": code,
            "name": f"销售测试物料{code}",
            "mtype": material_type,
            "supply": supply_type,
            "category": sales_category,
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


def _create_draft_order(client: TestClient, customer_id: int, material_id: int) -> dict:
    """建一张 DRAFT 订单，返回订单详情（用于单号 / 删单相关用例）。"""
    response = client.post(
        f"{SALES}/orders",
        json={
            "customer_id": customer_id,
            "order_date": date.today().isoformat(),
            "delivery_date": date.today().isoformat(),
            "items": [{"material_id": material_id, "quantity": "1", "unit_price": "1"}],
        },
    )
    assert response.json()["code"] == 0, response.json()
    return response.json()["data"]


def _ship_and_confirm(
    client: TestClient, order: dict, warehouse_id: int, quantity: str
) -> int:
    """对订单首行发货并确认，返回发货单ID。"""
    created = client.post(
        f"{SALES}/shipments",
        json={
            "order_id": order["id"],
            "shipment_date": date.today().isoformat(),
            "items": [
                {
                    "order_item_id": order["items"][0]["id"],
                    "warehouse_id": warehouse_id,
                    "quantity": quantity,
                }
            ],
        },
    )
    assert created.json()["code"] == 0, created.json()
    shipment_id = created.json()["data"]["id"]
    confirmed = client.post(f"{SALES}/shipments/{shipment_id}/confirm")
    assert confirmed.json()["code"] == 0, confirmed.json()
    return int(shipment_id)


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


def test_confirm_order_allocates_stock_and_creates_shipment(
    client: TestClient, db: Session
) -> None:
    """库存充足：确认订单自动生成发货草稿，且不产生计划需求。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    _set_stock(db, material_id, warehouse_id, "50")
    customer = _create_customer(client)

    order = _create_confirmed_order(client, customer["id"], material_id, quantity="30")
    allocation = order["allocation"]
    assert allocation is not None
    assert Decimal(str(allocation["stock_qty"])) == Decimal("30")
    assert Decimal(str(allocation["shortage_qty"])) == Decimal("0")
    assert allocation["demand_nos"] == []

    shipment = client.get(f"{SALES}/shipments/{allocation['shipment_id']}").json()["data"]
    assert shipment["status"] == "DRAFT"
    assert Decimal(str(shipment["items"][0]["quantity"])) == Decimal("30")
    assert shipment["items"][0]["warehouse_id"] == warehouse_id

    _refresh(db)
    demand_count = db.execute(
        text(
            "SELECT COUNT(*) FROM pln_demand "
            "WHERE source_type='SALES' AND source_reference_id=:o"
        ),
        {"o": order["id"]},
    ).scalar()
    assert int(demand_count) == 0


def test_confirm_order_sends_available_stock_and_converts_shortage(
    client: TestClient, db: Session
) -> None:
    """库存不足：可用部分生成发货草稿，缺口触发计划需求。

    需求数量登记**订单未交付总量**（50）而不是缺口（30）：库存已分配的 20 由
    MRP 净算抵扣，需求侧若只记 30，同一批库存会被抵扣两次。
    """
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    _set_stock(db, material_id, warehouse_id, "20")
    customer = _create_customer(client)

    order = _create_confirmed_order(client, customer["id"], material_id, quantity="50")
    allocation = order["allocation"]
    assert allocation is not None
    assert Decimal(str(allocation["stock_qty"])) == Decimal("20")
    assert Decimal(str(allocation["shortage_qty"])) == Decimal("30")
    assert allocation["shipment_no"].startswith("SH")
    assert len(allocation["demand_nos"]) == 1

    shipment = client.get(f"{SALES}/shipments/{allocation['shipment_id']}").json()["data"]
    assert Decimal(str(shipment["items"][0]["quantity"])) == Decimal("20")

    _refresh(db)
    row = db.execute(
        text(
            "SELECT quantity, status FROM pln_demand "
            "WHERE source_type='SALES' AND source_reference_id=:o AND material_id=:m"
        ),
        {"o": order["id"], "m": material_id},
    ).one()
    assert Decimal(str(row[0])) == Decimal("50")
    assert row[1] == "CONFIRMED"


def test_contract_open_order_demand_includes_stock_allocated(
    client: TestClient, db: Session
) -> None:
    """未交付需求取订单未交付总量，已分配库存的发货草稿不扣减（由 MRP 净算抵扣）。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    _set_stock(db, material_id, warehouse_id, "20")
    customer = _create_customer(client)
    order = _create_confirmed_order(client, customer["id"], material_id, quantity="50")

    _refresh(db)
    rows = [
        row
        for row in sales_contract.get_open_order_demand(db)
        if row["order_id"] == order["id"]
    ]
    assert len(rows) == 1
    assert Decimal(str(rows[0]["quantity"])) == Decimal("50")


def test_confirm_order_does_not_double_allocate_stock(
    client: TestClient, db: Session
) -> None:
    """两张订单先后确认：草稿发货占用的库存不会被第二张订单重复分配。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    _set_stock(db, material_id, warehouse_id, "30")
    customer = _create_customer(client)

    first = _create_confirmed_order(client, customer["id"], material_id, quantity="20")
    assert Decimal(str(first["allocation"]["stock_qty"])) == Decimal("20")

    second = _create_confirmed_order(client, customer["id"], material_id, quantity="20")
    assert Decimal(str(second["allocation"]["stock_qty"])) == Decimal("10")
    assert Decimal(str(second["allocation"]["shortage_qty"])) == Decimal("10")


def test_cancel_order_releases_auto_shipment_and_demand(
    client: TestClient, db: Session
) -> None:
    """订单取消：自动发货草稿取消、未进入 MPS 的缺口需求作废，库存释放。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    _set_stock(db, material_id, warehouse_id, "20")
    customer = _create_customer(client)
    order = _create_confirmed_order(client, customer["id"], material_id, quantity="50")

    cancelled = client.patch(
        f"{SALES}/orders/{order['id']}/status", json={"status": "CANCELLED"}
    )
    assert cancelled.json()["code"] == 0, cancelled.json()

    shipment = client.get(
        f"{SALES}/shipments/{order['allocation']['shipment_id']}"
    ).json()["data"]
    assert shipment["status"] == "CANCELLED"

    _refresh(db)
    demand_status = db.execute(
        text(
            "SELECT status FROM pln_demand "
            "WHERE source_type='SALES' AND source_reference_id=:o"
        ),
        {"o": order["id"]},
    ).scalar()
    assert demand_status == "CANCELLED"

    # 库存释放：后续订单可以重新分配这 20 个
    again = _create_confirmed_order(client, customer["id"], material_id, quantity="20")
    assert Decimal(str(again["allocation"]["stock_qty"])) == Decimal("20")


# ==================== 发货 ====================


def test_shipment_confirm_pushes_outbound_then_warehouse_confirm_decreases_stock(
    client: TestClient, db: Session
) -> None:
    """发货确认：只推送待出库单（不改结存）、订单行已发数量回写、订单转 IN_PROGRESS；
    仓库管理人员指定仓库并确认后库存才减少。"""
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    _set_stock(db, material_id, warehouse_id, "100")
    customer = _create_customer(client)
    order = _create_confirmed_order(client, customer["id"], material_id, quantity="30")
    order_item_id = order["items"][0]["id"]

    # 发货单不再要求选择仓库
    created = client.post(
        f"{SALES}/shipments",
        json={
            "order_id": order["id"],
            "shipment_date": date.today().isoformat(),
            "items": [{"order_item_id": order_item_id, "quantity": "20"}],
        },
    )
    assert created.json()["code"] == 0, created.json()
    shipment = created.json()["data"]
    assert shipment["status"] == "DRAFT"

    confirmed = client.post(f"{SALES}/shipments/{shipment['id']}/confirm")
    assert confirmed.json()["code"] == 0, confirmed.json()
    assert confirmed.json()["data"]["status"] == "COMPLETED"

    _refresh(db)
    # 业务确认不改结存，只登记待出库单
    assert inventory_contract.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("100.0000")
    pending = inventory_service.get_inout_status_map(
        db, [("sales", "SALES_SHIPMENT", shipment["id"])]
    )[("sales", "SALES_SHIPMENT", shipment["id"])]
    assert pending["op_type"] == "OUTBOUND"
    assert pending["status"] == "DRAFT"

    # 库存「出库管理」待办列表可见该单据，且来源与物料快照完整
    listed = client.get(
        "/api/v1/inventory/stock-operations",
        params={"op_type": "OUTBOUND", "status": "DRAFT", "source_type": "SALES_SHIPMENT"},
    ).json()
    assert listed["code"] == 0, listed
    rows = [item for item in listed["data"]["items"] if item["id"] == pending["operation_id"]]
    assert len(rows) == 1
    row = rows[0]
    assert row["source_module"] == "sales"
    assert row["source_no"] == shipment["shipment_no"]
    assert row["warehouse_id"] is None
    assert row["items"][0]["material_id"] == material_id
    assert row["items"][0]["material_code"]
    assert row["items"][0]["quantity"] is not None
    assert "销售发货单" in row["remark"]

    inventory_service.confirm_stock_operation(
        db, pending["operation_id"], warehouse_id=warehouse_id
    )
    db.commit()
    assert inventory_contract.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("80.0000")

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


def test_return_confirm_pushes_inbound_then_warehouse_confirm_increases_stock(
    client: TestClient, db: Session
) -> None:
    """退货确认：只推送待入库单（不改结存），仓库确认后才回增库存。"""
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
    # 业务确认不改结存，只登记待入库单
    assert inventory_contract.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("0")
    pending = inventory_service.get_inout_status_map(
        db, [("sales", "SALES_RETURN", sales_return["id"])]
    )[("sales", "SALES_RETURN", sales_return["id"])]
    assert pending["op_type"] == "INBOUND"
    assert pending["status"] == "DRAFT"

    inventory_service.confirm_stock_operation(
        db, pending["operation_id"], warehouse_id=warehouse_id
    )
    db.commit()
    assert inventory_contract.get_on_hand_qty(db, material_id, warehouse_id) == Decimal("5.0000")


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


# ==================== 退货额度 ====================


def test_return_over_shipped_qty_rejected(client: TestClient, db: Session) -> None:
    """可退额度 = 已发 - 已占用退货；草稿退货单也占用额度，取消后释放。

    草稿必须计入占用，否则同一订单的多张草稿会各自通过校验、把可退数量用超。
    """
    material_id = _create_material(db)
    warehouse_id = _create_warehouse(client)
    _set_stock(db, material_id, warehouse_id, "100")
    customer = _create_customer(client)
    order = _create_confirmed_order(client, customer["id"], material_id, quantity="30")
    _ship_and_confirm(client, order, warehouse_id, "20")

    payload = {
        "order_id": order["id"],
        "customer_id": customer["id"],
        "return_date": date.today().isoformat(),
        "items": [
            {
                "material_id": material_id,
                "warehouse_id": warehouse_id,
                "quantity": "25",
            }
        ],
    }
    exceeded = client.post(f"{SALES}/returns", json=payload)
    assert exceeded.json()["code"] == 2007, exceeded.json()

    payload["items"][0]["quantity"] = "20"  # 恰好等于已发数量，可退
    first = client.post(f"{SALES}/returns", json=payload)
    assert first.json()["code"] == 0, first.json()
    first_id = first.json()["data"]["id"]

    payload["items"][0]["quantity"] = "5"  # 额度已被草稿占满
    reserved = client.post(f"{SALES}/returns", json=payload)
    assert reserved.json()["code"] == 2007, reserved.json()

    cancelled = client.post(f"{SALES}/returns/{first_id}/cancel")
    assert cancelled.json()["code"] == 0, cancelled.json()
    after_cancel = client.post(f"{SALES}/returns", json=payload)
    assert after_cancel.json()["code"] == 0, after_cancel.json()


# ==================== 销售预测 ====================


def _create_forecast(client: TestClient, material_id: int, qty: str = "100") -> dict:
    """经 sales 接口建预测单（DRAFT），返回预测数据。"""
    response = client.post(
        f"{SALES}/forecasts",
        json={
            "material_id": material_id,
            "forecast_month": "2026-12",
            "forecast_qty": qty,
        },
    )
    assert response.json()["code"] == 0, response.json()
    return response.json()["data"]


def test_forecast_status_machine(client: TestClient, db: Session) -> None:
    """预测状态机：DRAFT → CONFIRMED → COMPLETED，终态不可再流转、不可删除。"""
    material_id = _create_material(db)
    forecast = _create_forecast(client, material_id)
    url = f"{SALES}/forecasts/{forecast['id']}/status"

    skipped = client.patch(url, json={"status": "COMPLETED"})
    assert skipped.json()["code"] == 2006, skipped.json()

    confirmed = client.patch(url, json={"status": "CONFIRMED"})
    assert confirmed.json()["code"] == 0
    assert confirmed.json()["data"]["status"] == "CONFIRMED"

    # 不回退 DRAFT：Planning 是按 CONFIRMED 拉需求的，回退会让需求与状态对不上
    back = client.patch(url, json={"status": "DRAFT"})
    assert back.json()["code"] == 2006, back.json()

    completed = client.patch(url, json={"status": "COMPLETED"})
    assert completed.json()["code"] == 0
    assert completed.json()["data"]["status"] == "COMPLETED"

    terminal = client.patch(url, json={"status": "CANCELLED"})
    assert terminal.json()["code"] == 2006, terminal.json()

    deleted = client.delete(f"{SALES}/forecasts/{forecast['id']}")
    assert deleted.json()["code"] == 2006, deleted.json()


def test_forecast_editable_only_in_draft(client: TestClient, db: Session) -> None:
    """预测单仅 DRAFT 可修改；确认后再改返回 2006。"""
    material_id = _create_material(db)
    forecast = _create_forecast(client, material_id, qty="10")
    url = f"{SALES}/forecasts/{forecast['id']}"

    updated = client.put(url, json={"forecast_qty": "20"})
    assert updated.json()["code"] == 0, updated.json()
    assert Decimal(str(updated.json()["data"]["forecast_qty"])) == Decimal("20")

    client.patch(f"{url}/status", json={"status": "CONFIRMED"})
    blocked = client.put(url, json={"forecast_qty": "30"})
    assert blocked.json()["code"] == 2006, blocked.json()


# ==================== 单号生成 ====================


def test_order_no_not_reused_after_delete(client: TestClient, db: Session) -> None:
    """单号取同前缀最大序号 +1：删掉中间一张单后，新单号不与既有单号重复。"""
    material_id = _create_material(db)
    customer = _create_customer(client)

    first = _create_draft_order(client, customer["id"], material_id)
    second = _create_draft_order(client, customer["id"], material_id)

    deleted = client.delete(f"{SALES}/orders/{first['id']}")
    assert deleted.json()["code"] == 0, deleted.json()

    third = _create_draft_order(client, customer["id"], material_id)
    assert third["order_no"] not in {first["order_no"], second["order_no"]}


def test_orders_list_filters_by_date_range(client: TestClient, db: Session) -> None:
    """订单列表按订单日期区间过滤，未落在区间内的订单不出现。"""
    material_id = _create_material(db)
    customer = _create_customer(client)
    order = _create_draft_order(client, customer["id"], material_id)

    today = date.today().isoformat()
    matched = client.get(
        f"{SALES}/orders",
        params={"page": 1, "page_size": 20, "date_from": today, "date_to": today},
    )
    assert matched.json()["code"] == 0, matched.json()
    assert order["id"] in [row["id"] for row in matched.json()["data"]["items"]]

    next_year = date.today().replace(year=date.today().year + 1).isoformat()
    missed = client.get(
        f"{SALES}/orders",
        params={"page": 1, "page_size": 20, "date_from": next_year, "date_to": next_year},
    )
    assert missed.json()["code"] == 0, missed.json()
    assert order["id"] not in [row["id"] for row in missed.json()["data"]["items"]]


# ==================== 报表接口健壮性 ====================


def test_reports_work_without_date_range(client: TestClient) -> None:
    """报表接口的日期区间可省，不传时不过滤、不报 422。"""
    for path in ("shipments", "returns", "sales-volume", "order-status"):
        response = client.get(f"{SALES}/reports/{path}")
        assert response.status_code == 200, response.text
        assert response.json()["code"] == 0, response.text