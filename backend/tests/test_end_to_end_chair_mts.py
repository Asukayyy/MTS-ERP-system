"""转椅 MTS ERP 全系统核心业务链端到端验收测试（规格 §17 / §43 Phase 7–9）。

本用例是验收核心产物：它**不是 mock**，而是通过真实 HTTP API
（`fastapi.testclient.TestClient` → `app.main.app` → router → service → repository）
在本机真实 MySQL 上把整条业务链跑通：

    课程数据导入 → MPS → MRP 多层运算 → BUY/MAKE 分流
        → 采购闭环（供应商 / 采购计划 / 采购订单 / 到货入库）
        → 生产闭环（作业计划 / 派工 / 领料 / 完工入库）
        → 销售闭环（客户 / 订单 / 发货 / 退货）
        → 库存主动发起计划（订货点 → 补库需求 → 采购 / 生产）
        → 负库存保护

设计要点：

- 所有期望值均从权威种子文件 ``data/seed/course_chair_case.json`` 推导，
  **绝不硬编码 BOM 数量**；
- 数据库随多次运行持续累积，因此所有断言都针对**本次创建的文档**与**增量**，
  绝不对全局绝对条数做断言；
- 所有业务编码使用 ``uuid`` 后缀，保证用例可重复执行。
"""

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient

# 各模块统一前缀（由 app/main.py 注入）
SYSTEM = "/api/v1/system"
SALES = "/api/v1/sales"
PLANNING = "/api/v1/planning"
PROCUREMENT = "/api/v1/procurement"
INVENTORY = "/api/v1/inventory"

#: 课程权威种子文件（仓库根 /data/seed/course_chair_case.json）
_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed" / "course_chair_case.json"


# ==================== 基础工具 ====================


def _tag() -> str:
    """生成短随机后缀，避免多次运行编码冲突。"""
    return uuid.uuid4().hex[:10].upper()


def _seed() -> Dict[str, Any]:
    """读取课程权威种子文件。"""
    return json.loads(_SEED_PATH.read_text(encoding="utf-8"))


def _d(value: Any) -> Decimal:
    """把接口返回的数字（str/int/Decimal）统一转成 Decimal。"""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _expect_code(
    client: TestClient, method: str, path: str, expected: int, **kwargs: Any
) -> Dict[str, Any]:
    """请求接口并断言统一响应体中的业务码，返回完整响应体。"""
    response = client.request(method, path, **kwargs)
    assert response.status_code == 200, f"{method} {path} HTTP {response.status_code}: {response.text}"
    body = response.json()
    assert body.get("code") == expected, f"{method} {path} 期望 code={expected}，实际：{body}"
    return body


def _ok(client: TestClient, method: str, path: str, **kwargs: Any) -> Any:
    """请求接口，断言业务码为 0，返回 ``data``。"""
    return _expect_code(client, method, path, 0, **kwargs)["data"]


def _material_id(client: TestClient, material_code: str) -> int:
    """按编码精确查出物料 ID（走真实列表接口）。"""
    data = _ok(
        client,
        "GET",
        f"{SYSTEM}/materials",
        params={"keyword": material_code, "page_size": 200},
    )
    for item in data["items"]:
        if item["material_code"] == material_code:
            return int(item["id"])
    raise AssertionError(f"物料不存在：{material_code}")


def _on_hand(client: TestClient, material_id: int, warehouse_id: int) -> Decimal:
    """读取某物料在某仓库的现存量（结存合计）。"""
    data = _ok(
        client,
        "GET",
        f"{INVENTORY}/balances",
        params={"material_id": material_id, "warehouse_id": warehouse_id, "page_size": 200},
    )
    return sum((_d(item["on_hand"]) for item in data["items"]), Decimal("0"))


def _on_hand_global(client: TestClient, material_id: int) -> Decimal:
    """读取某物料在**全部仓库**的现存量合计（MRP 可用量也是全局口径）。"""
    data = _ok(
        client,
        "GET",
        f"{INVENTORY}/balances",
        params={"material_id": material_id, "page_size": 200},
    )
    return sum((_d(item["on_hand"]) for item in data["items"]), Decimal("0"))


def _walk(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    """深度优先遍历课程 BOM 树，返回全部节点。"""
    nodes = [node]
    for child in node.get("children", []):
        nodes.extend(_walk(child))
    return nodes


def _ledger(
    client: TestClient,
    *,
    source_type: str,
    source_reference_id: int,
    material_id: int | None = None,
    warehouse_id: int | None = None,
) -> List[Dict[str, Any]]:
    """查询某来源单据对应的库存流水行（走真实流水接口）。"""
    params: Dict[str, Any] = {"source_type": source_type, "page_size": 200}
    if material_id is not None:
        params["material_id"] = material_id
    if warehouse_id is not None:
        params["warehouse_id"] = warehouse_id
    rows = _ok(client, "GET", f"{INVENTORY}/transactions", params=params)["items"]
    return [row for row in rows if row.get("source_reference_id") == source_reference_id]


def _depth(node: Dict[str, Any]) -> int:
    """计算 BOM 树节点深度（单节点为 1）。"""
    return 1 + max((_depth(child) for child in node["children"]), default=0)


# ==================== 端到端主用例 ====================


def test_end_to_end_chair_mts(client: TestClient) -> None:
    """全链路真实运行：MPS → MRP → BUY/MAKE → 采购/生产 → 库存 → 发货/退货。"""
    summary: List[str] = []

    def note(text: str) -> None:
        summary.append(text)

    seed = _seed()
    counts = seed["counts"]
    course = seed["course_data"]
    product = course["product"]
    root_code = product["material_code"]
    today = date.today()

    # ------------------------------------------------------------------
    # Step 0 — 基础准备：仓库 + 库位 + 组织 + 人员
    # ------------------------------------------------------------------
    warehouse = _ok(
        client,
        "POST",
        f"{INVENTORY}/warehouses",
        json={"warehouse_code": f"WH-{_tag()}", "warehouse_name": "转椅全链路验收仓"},
    )
    warehouse_id = int(warehouse["id"])

    location = _ok(
        client,
        "POST",
        f"{INVENTORY}/locations",
        json={
            "location_code": f"LOC-{_tag()}",
            "location_name": "验收库位 A1",
            "warehouse_id": warehouse_id,
        },
    )
    location_id = int(location["id"])

    org = _ok(
        client,
        "POST",
        f"{SYSTEM}/organizations",
        json={"org_code": f"ORG-{_tag()}", "org_name": "转椅总装车间", "org_type": "WORKSHOP"},
    )
    org_id = int(org["id"])

    def create_personnel(name: str, position: str) -> int:
        data = _ok(
            client,
            "POST",
            f"{SYSTEM}/personnel",
            json={
                "employee_no": f"EMP-{_tag()}",
                "person_name": name,
                "org_id": org_id,
                "position": position,
            },
        )
        return int(data["id"])

    salesperson_id = create_personnel("销售员-张", "销售员")
    buyer_id = create_personnel("采购员-李", "采购员")
    worker_id = create_personnel("装配工-王", "装配工")

    note(
        f"[0] 基础准备：仓库#{warehouse_id} 库位#{location_id} 组织#{org_id} "
        f"人员（销售#{salesperson_id}/采购#{buyer_id}/装配#{worker_id}）"
    )

    # ------------------------------------------------------------------
    # Step 1 — 课程数据导入（规格 §37）
    # ------------------------------------------------------------------
    # 1.1 物料导入预览：汇总必须与种子文件 counts 一致
    material_preview = _ok(
        client, "POST", f"{SYSTEM}/import/materials/preview", json={"source": "course_chair_case"}
    )
    m_summary = material_preview["summary"]
    assert m_summary["total"] == counts["total_nodes"], m_summary
    assert m_summary["max_level"] == counts["levels"], m_summary
    assert m_summary["invalid"] == 0, material_preview["errors"]
    assert m_summary["source_counts"] == counts, m_summary["source_counts"]
    assert len(material_preview["materials"]) == counts["total_nodes"]

    # 1.2 物料确认导入（幂等：重复运行只跳过）
    material_confirm = _ok(
        client, "POST", f"{SYSTEM}/import/materials/confirm", json={"source": "course_chair_case"}
    )
    assert material_confirm["created"] + material_confirm["skipped"] == counts["total_nodes"]
    assert material_confirm["errors"] == []

    # 1.3 BOM 导入预览：节点 / 层级与文件一致
    bom_preview = _ok(
        client, "POST", f"{SYSTEM}/import/bom/preview", json={"source": "course_chair_case"}
    )
    b_summary = bom_preview["summary"]
    assert b_summary["total_nodes"] == counts["total_nodes"], b_summary
    assert b_summary["levels"] == counts["levels"], b_summary
    assert b_summary["source_counts"] == counts, b_summary["source_counts"]
    assert bom_preview["errors"] == []

    # 1.4 BOM 确认导入
    bom_confirm = _ok(
        client, "POST", f"{SYSTEM}/import/bom/confirm", json={"source": "course_chair_case"}
    )
    assert bom_confirm["errors"] == []

    # 1.5 BOM 树必须真实多层（≥3 层）
    root_id = _material_id(client, root_code)
    tree = _ok(
        client,
        "GET",
        f"{SYSTEM}/boms/tree",
        params={"material_id": root_id, "max_level": 10},
    )
    root_node = tree[0]
    tree_depth = _depth(root_node)
    assert root_node["material_code"] == root_code
    assert tree_depth >= 3, f"BOM 树深度应 ≥3，实际 {tree_depth}"
    assert len(root_node["children"]) == len(product["children"])

    # 1.6 期初库存导入预览 + 确认（导入到本次新建仓库）
    stock_preview = _ok(
        client,
        "POST",
        f"{INVENTORY}/import/initial-stock/preview",
        json={"source": "course_chair_case", "warehouse_id": warehouse_id},
    )
    assert stock_preview["summary"]["total"] == counts["total_nodes"], stock_preview["summary"]
    assert stock_preview["summary"]["invalid"] == 0, stock_preview["errors"]
    assert stock_preview["summary"]["valid"] == counts["total_nodes"]

    stock_confirm = _ok(
        client,
        "POST",
        f"{INVENTORY}/import/initial-stock/confirm",
        json={"source": "course_chair_case", "warehouse_id": warehouse_id},
    )
    assert stock_confirm["imported"] == counts["total_nodes"], stock_confirm
    assert stock_confirm["errors"] == []

    # 1.7 MPS 导入预览 + 确认
    mps_preview = _ok(
        client, "POST", f"{PLANNING}/mps/import/preview", json={"source": "course_chair_case"}
    )
    assert mps_preview["summary"]["valid_count"] == course["mps"]["month_count"]
    assert mps_preview["summary"]["error_count"] == 0
    mps = _ok(
        client, "POST", f"{PLANNING}/mps/import/confirm", json={"source": "course_chair_case"}
    )
    mps_id = int(mps["id"])
    assert len(mps["items"]) == course["mps"]["month_count"]

    note(
        f"[1] 课程导入：物料 {counts['total_nodes']} 个 / BOM {counts['levels']} 层（树深 {tree_depth}）"
        f" / 期初库存 {stock_confirm['imported']} 行 / MPS#{mps_id} {len(mps['items'])} 行"
    )

    # ------------------------------------------------------------------
    # Step 1.8 — 构造「确定性需求」的验收 MPS
    # ------------------------------------------------------------------
    # 课程原始 MPS（12 × 10000）是**一次性**需求，而本用例运行在共享 MySQL 上、
    # 每次运行都会再导入一次期初库存，因此课程物料的可用量会随运行次数累积，
    # 最终可能大于课程 MPS 的毛需求，使净需求归零、多层展开自然停止
    # （这是**正确**的 MRP 行为，不是缺陷）。
    #
    # 为了让「多层展开 + MAKE/BUY 分流」在任何运行次数下都被真实触发，
    # 这里按**当前全局现存量**反推需求：`计划量 = 全部课程物料现存量 × 10 + 1000000`，
    # 保证每层净需求恒大于 0，且该值随库存增长自动放大，不依赖任何魔法常量。
    course_nodes = _walk(product)
    total_on_hand = sum(
        (_on_hand_global(client, _material_id(client, node["material_code"])) for node in course_nodes),
        Decimal("0"),
    )
    acceptance_qty = total_on_hand * 10 + Decimal("1000000")
    acceptance_mps = _ok(
        client,
        "POST",
        f"{PLANNING}/mps",
        json={
            "mps_name": f"转椅验收需求-{_tag()}",
            "plan_year": today.year,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
            "items": [
                {
                    "material_id": root_id,
                    "period_label": "验收期",
                    "planned_qty": str(acceptance_qty),
                    "start_date": today.isoformat(),
                    "end_date": (today + timedelta(days=30)).isoformat(),
                }
            ],
        },
    )
    acceptance_mps_id = int(acceptance_mps["id"])
    assert len(acceptance_mps["items"]) == 1

    note(
        f"[1.8] 验收 MPS#{acceptance_mps_id}：当前课程物料全局现存合计 {total_on_hand}，"
        f"计划量取 {acceptance_qty}（×10 + 1000000）以保证各层净需求恒 > 0"
    )

    # ------------------------------------------------------------------
    # Step 2 — 运行 MRP（两次独立批次，不覆盖历史）
    # ------------------------------------------------------------------
    run1 = _ok(client, "POST", f"{PLANNING}/mrp/run", json={"mps_id": acceptance_mps_id})
    run2 = _ok(client, "POST", f"{PLANNING}/mrp/run", json={"mps_id": acceptance_mps_id})
    assert run1["id"] != run2["id"], "两次 MRP 运算必须是不同批次"
    assert run1["run_no"] != run2["run_no"]
    run1_id = int(run1["id"])
    run2_id = int(run2["id"])

    # 两个批次各自保留结果
    detail1 = _ok(client, "GET", f"{PLANNING}/mrp/runs/{run1_id}")
    detail2 = _ok(client, "GET", f"{PLANNING}/mrp/runs/{run2_id}")
    assert detail1["status"] == "COMPLETED"
    assert detail2["status"] == "COMPLETED"

    results = _ok(
        client,
        "GET",
        f"{PLANNING}/mrp/runs/{run1_id}/results",
        params={"page_size": 200},
    )["items"]
    assert results, "MRP 批次必须有结果"
    assert all(int(row["run_id"]) == run1_id for row in results)

    levels = {int(row["bom_level"]) for row in results}
    assert levels == {0, 1, 2}, f"课程 BOM 为 3 层，MRP 应展开出 {0,1,2} 层，实际 {levels}"
    assert len(results) == counts["total_nodes"], (
        f"各层净需求均 > 0 时应展开出全部 {counts['total_nodes']} 个节点，实际 {len(results)}"
    )
    supply_types = {row["supply_type"] for row in results}
    assert "MAKE" in supply_types, "应存在自制（MAKE）需求"
    assert "BUY" in supply_types, "应存在采购（BUY）需求"

    # 逐层展开不变量：净需求 > 0 且存在生效 BOM 的行，必须展开出下一层子件
    level_by_material = {int(row["material_id"]): int(row["bom_level"]) for row in results}
    for row in results:
        children = _ok(
            client,
            "GET",
            f"{SYSTEM}/boms",
            params={"material_id": int(row["material_id"]), "is_active": True, "page_size": 50},
        )["items"]
        active_children = [bom for bom in children if bom["is_active"]]
        if _d(row["net_requirement"]) > 0 and active_children:
            for child in active_children[0]["items"]:
                child_id = int(child["material_id"])
                assert child_id in level_by_material, (
                    f"物料#{row['material_id']} 净需求 > 0 且有生效 BOM，"
                    f"子件#{child_id} 未出现在 MRP 结果中"
                )
                assert level_by_material[child_id] == int(row["bom_level"]) + 1, (
                    f"子件#{child_id} 的层级应为 {int(row['bom_level']) + 1}"
                )

    root_rows = [row for row in results if row["material_id"] == root_id and row["bom_level"] == 0]
    assert len(root_rows) == 1, "根成品应有且仅有一条第 0 层结果"

    # 逐行校验净需求公式与建议下达日期
    for row in results:
        gross = _d(row["gross_requirement"])
        safety = _d(row["safety_stock"])
        available = _d(row["available_quantity"])
        net = _d(row["net_requirement"])
        expected_net = max(gross + safety - available, Decimal("0"))
        assert net == expected_net, f"净需求公式不符：{row}"

        requirement_date = date.fromisoformat(row["requirement_date"])
        release_date = date.fromisoformat(row["planned_release_date"])
        assert release_date == requirement_date - timedelta(days=int(row["lead_time_days"])), (
            f"建议下达日期不符：{row}"
        )

    # MRP 计算明细（explain）：取一条第 2 层的采购件
    explain_row = next(
        row for row in results if row["supply_type"] == "BUY" and row["bom_level"] >= 2
    )
    explain = _ok(
        client,
        "GET",
        f"{PLANNING}/mrp/runs/{run1_id}/explain",
        params={"material_id": explain_row["material_id"]},
    )
    assert explain["mrp_result_id"] == explain_row["id"]
    assert _d(explain["net_requirement"]) == _d(explain_row["net_requirement"])
    assert "净需求" in explain["formula"], explain["formula"]

    note(
        f"[2] MRP：批次 #{run1_id} 与 #{run2_id}，各 {len(results)} 条结果；"
        f"层集合 {sorted(levels)}，MAKE/BUY 分流齐全，净需求与下达日期逐行自洽"
    )

    # ------------------------------------------------------------------
    # Step 3 — MRP BUY → 采购闭环
    # ------------------------------------------------------------------
    plan_wrap = _ok(
        client, "POST", f"{PLANNING}/mrp/runs/{run1_id}/create-purchase-plan"
    )
    assert plan_wrap["released_count"] > 0
    purchase_plan_id = int(plan_wrap["purchase_plan"]["plan_id"])
    purchase_plan = _ok(client, "GET", f"{PROCUREMENT}/purchase-plans/{purchase_plan_id}")
    assert len(purchase_plan["items"]) >= 1

    supplier = _ok(
        client,
        "POST",
        f"{PROCUREMENT}/suppliers",
        json={"supplier_code": f"SUP-{_tag()}", "supplier_name": "转椅验收供应商"},
    )
    supplier_id = int(supplier["id"])

    po = _ok(
        client,
        "POST",
        f"{PROCUREMENT}/orders/from-plan",
        json={"plan_id": purchase_plan_id, "supplier_id": supplier_id, "buyer_id": buyer_id},
    )
    assert po["status"] == "DRAFT"
    assert len(po["items"]) >= 1
    _ok(
        client,
        "PATCH",
        f"{PROCUREMENT}/orders/{po['id']}/status",
        json={"status": "CONFIRMED"},
    )

    # 到货确认：库存恰好增加「到货数量」，并写 PURCHASE_RECEIPT 流水
    order_item = po["items"][0]
    material_id = int(order_item["material_id"])
    received_qty = min(_d(order_item["quantity"]), Decimal("100"))
    balance_before = _on_hand(client, material_id, warehouse_id)

    receipt = _ok(
        client,
        "POST",
        f"{PROCUREMENT}/receipts",
        json={
            "purchase_order_id": po["id"],
            "warehouse_id": warehouse_id,
            "receipt_date": today.isoformat(),
            "items": [{"order_item_id": order_item["id"], "quantity": str(received_qty)}],
        },
    )
    _ok(client, "POST", f"{PROCUREMENT}/receipts/{receipt['id']}/confirm")

    balance_after = _on_hand(client, material_id, warehouse_id)
    assert balance_after - balance_before == received_qty, (
        f"采购入库结存增量应为 {received_qty}，实际 {balance_after - balance_before}"
    )
    receipt_ledger = _ledger(
        client,
        source_type="PURCHASE_RECEIPT",
        source_reference_id=int(receipt["id"]),
        warehouse_id=warehouse_id,
    )
    assert len(receipt_ledger) == 1, receipt_ledger
    assert _d(receipt_ledger[0]["quantity_change"]) == received_qty

    note(
        f"[3] 采购闭环：采购计划#{purchase_plan_id} → 订单 {po['order_no']} → 到货 {receipt['receipt_no']}"
        f" 入库 {received_qty}（物料#{material_id}），流水 PURCHASE_RECEIPT 已落账"
    )

    # ------------------------------------------------------------------
    # Step 4 — MRP MAKE → 生产闭环
    # ------------------------------------------------------------------
    plans = _ok(client, "POST", f"{PLANNING}/mrp/runs/{run1_id}/create-production-plans")
    assert len(plans) >= 1, "应由 MAKE 结果生成生产作业计划"
    make_plan = next(plan for plan in plans if int(plan["material_id"]) == root_id)
    plan_id = int(make_plan["id"])
    planned_qty = _d(make_plan["planned_qty"])
    assert planned_qty > 0

    # 派工单（引用 Step 0 的装配工）
    dispatch = _ok(
        client,
        "POST",
        f"{PLANNING}/dispatch-orders",
        json={
            "plan_id": plan_id,
            "operation": "总装",
            "planned_qty": str(planned_qty),
            "worker_id": worker_id,
            "planned_start": today.isoformat(),
            "planned_end": (today + timedelta(days=3)).isoformat(),
        },
    )

    # 领料：按生效 BOM 取该作业计划的直接组件
    boms = _ok(
        client,
        "GET",
        f"{SYSTEM}/boms",
        params={"material_id": root_id, "is_active": True, "page_size": 50},
    )["items"]
    active_bom = next(bom for bom in boms if bom["is_active"])
    components = active_bom["items"]
    assert len(components) == len(product["children"])

    req_items = [
        {"material_id": int(comp["material_id"]), "required_qty": str(_d(comp["quantity"]))}
        for comp in components
    ]
    before_components = {
        int(comp["material_id"]): _on_hand(client, int(comp["material_id"]), warehouse_id)
        for comp in components
    }
    requisition = _ok(
        client,
        "POST",
        f"{PLANNING}/requisitions",
        json={
            "plan_id": plan_id,
            "warehouse_id": warehouse_id,
            "req_date": today.isoformat(),
            "items": req_items,
        },
    )
    _ok(client, "POST", f"{PLANNING}/requisitions/{requisition['id']}/confirm")

    for comp in components:
        comp_id = int(comp["material_id"])
        expected = _d(comp["quantity"])
        after = _on_hand(client, comp_id, warehouse_id)
        assert before_components[comp_id] - after == expected, (
            f"领料后组件#{comp_id} 库存应减少 {expected}"
        )
    req_ledger = _ledger(
        client,
        source_type="MATERIAL_REQUISITION",
        source_reference_id=int(requisition["id"]),
        warehouse_id=warehouse_id,
    )
    assert len(req_ledger) == len(components), req_ledger
    assert all(_d(row["quantity_change"]) < 0 for row in req_ledger)

    # 完工入库
    complete_qty = min(planned_qty, Decimal("50"))
    before_finished = _on_hand(client, root_id, warehouse_id)
    report = _ok(
        client,
        "POST",
        f"{PLANNING}/completion-reports",
        json={
            "plan_id": plan_id,
            "dispatch_id": dispatch["id"],
            "material_id": root_id,
            "completed_qty": str(complete_qty),
            "qualified_qty": str(complete_qty),
            "warehouse_id": warehouse_id,
            "report_date": today.isoformat(),
        },
    )
    _ok(client, "POST", f"{PLANNING}/completion-reports/{report['id']}/confirm")

    after_finished = _on_hand(client, root_id, warehouse_id)
    assert after_finished - before_finished == complete_qty, (
        f"完工入库结存增量应为 {complete_qty}，实际 {after_finished - before_finished}"
    )
    completion_ledger = _ledger(
        client,
        source_type="PRODUCTION_COMPLETION",
        source_reference_id=int(report["id"]),
        warehouse_id=warehouse_id,
    )
    assert len(completion_ledger) == 1, completion_ledger
    assert _d(completion_ledger[0]["quantity_change"]) == complete_qty

    plan_after = _ok(client, "GET", f"{PLANNING}/production-plans/{plan_id}")
    assert _d(plan_after["completed_qty"]) == complete_qty, plan_after

    note(
        f"[4] 生产闭环：作业计划#{plan_id}（{planned_qty}）→ 派工 {dispatch['dispatch_no']}"
        f" → 领料 {requisition['req_no']}（{len(components)} 组件出库）"
        f" → 完工 {report['report_no']} 入库 {complete_qty}，completed_qty 已回写"
    )

    # ------------------------------------------------------------------
    # Step 5 — 销售 → 库存（发货）
    # ------------------------------------------------------------------
    customer = _ok(
        client,
        "POST",
        f"{SALES}/customers",
        json={"customer_code": f"CUS-{_tag()}", "customer_name": "转椅验收客户"},
    )
    customer_id = int(customer["id"])

    order_qty = Decimal("100")
    sales_order = _ok(
        client,
        "POST",
        f"{SALES}/orders",
        json={
            "customer_id": customer_id,
            "order_date": today.isoformat(),
            "delivery_date": (today + timedelta(days=7)).isoformat(),
            "salesperson_id": salesperson_id,
            "items": [{"material_id": root_id, "quantity": str(order_qty), "unit_price": "10"}],
        },
    )
    _ok(
        client,
        "PATCH",
        f"{SALES}/orders/{sales_order['id']}/status",
        json={"status": "CONFIRMED"},
    )
    sales_order_item_id = int(sales_order["items"][0]["id"])

    ship_qty = Decimal("40")
    before_ship = _on_hand(client, root_id, warehouse_id)
    shipment = _ok(
        client,
        "POST",
        f"{SALES}/shipments",
        json={
            "order_id": sales_order["id"],
            "shipment_date": today.isoformat(),
            "items": [
                {
                    "order_item_id": sales_order_item_id,
                    "warehouse_id": warehouse_id,
                    "quantity": str(ship_qty),
                }
            ],
        },
    )
    _ok(client, "POST", f"{SALES}/shipments/{shipment['id']}/confirm")

    after_ship = _on_hand(client, root_id, warehouse_id)
    assert before_ship - after_ship == ship_qty, (
        f"发货后结存应减少 {ship_qty}，实际 {before_ship - after_ship}"
    )
    shipment_ledger = _ledger(
        client,
        source_type="SALES_SHIPMENT",
        source_reference_id=int(shipment["id"]),
        warehouse_id=warehouse_id,
    )
    assert len(shipment_ledger) == 1, shipment_ledger

    order_detail = _ok(client, "GET", f"{SALES}/orders/{sales_order['id']}")
    assert _d(order_detail["items"][0]["delivered_qty"]) == ship_qty

    # 超量发货必须被拒绝（2003）
    over = _expect_code(
        client,
        "POST",
        f"{SALES}/shipments",
        2003,
        json={
            "order_id": sales_order["id"],
            "shipment_date": today.isoformat(),
            "items": [
                {
                    "order_item_id": sales_order_item_id,
                    "warehouse_id": warehouse_id,
                    "quantity": str(order_qty + Decimal("999")),
                }
            ],
        },
    )
    assert over["code"] == 2003

    note(
        f"[5] 销售发货：订单 {sales_order['order_no']}（{order_qty}）确认 → 发货 {shipment['shipment_no']}"
        f" 出库 {ship_qty}，delivered_qty 已回写，超量发货正确返回 2003"
    )

    # ------------------------------------------------------------------
    # Step 6 — 退货 → 库存
    # ------------------------------------------------------------------
    return_qty = Decimal("10")
    before_return = _on_hand(client, root_id, warehouse_id)
    sales_return = _ok(
        client,
        "POST",
        f"{SALES}/returns",
        json={
            "order_id": sales_order["id"],
            "customer_id": customer_id,
            "return_date": today.isoformat(),
            "reason": "客户抽检退货",
            "items": [
                {
                    "material_id": root_id,
                    "warehouse_id": warehouse_id,
                    "quantity": str(return_qty),
                    "quality_status": "DEFECTIVE",
                }
            ],
        },
    )
    _ok(client, "POST", f"{SALES}/returns/{sales_return['id']}/confirm")

    after_return = _on_hand(client, root_id, warehouse_id)
    assert after_return - before_return == return_qty, (
        f"退货后结存应增加 {return_qty}，实际 {after_return - before_return}"
    )
    return_ledger = _ledger(
        client,
        source_type="SALES_RETURN",
        source_reference_id=int(sales_return["id"]),
        warehouse_id=warehouse_id,
    )
    assert len(return_ledger) == 1, return_ledger

    note(
        f"[6] 销售退货：退货单 {sales_return['return_no']} 确认 → 回增库存 {return_qty}，"
        f"流水 SALES_RETURN 已落账"
    )

    # ------------------------------------------------------------------
    # Step 7 — 库存主动发起计划（订货点 → 补库需求 → 采购 / 生产）
    # ------------------------------------------------------------------
    reorder_material_id = int(
        next(row for row in results if row["supply_type"] == "BUY")["material_id"]
    )
    current_qty = _on_hand(client, reorder_material_id, warehouse_id)
    reorder_point = current_qty + Decimal("500")
    reorder_quantity = Decimal("100")

    _ok(
        client,
        "POST",
        f"{INVENTORY}/reorder-rules",
        json={
            "material_id": reorder_material_id,
            "warehouse_id": warehouse_id,
            "reorder_point": str(reorder_point),
            "reorder_quantity": str(reorder_quantity),
        },
    )
    suggestions = _ok(client, "GET", f"{INVENTORY}/reorder-rules/suggestions")
    suggestion = next(
        item
        for item in suggestions
        if int(item["material_id"]) == reorder_material_id
        and int(item["warehouse_id"]) == warehouse_id
    )
    assert _d(suggestion["suggested_qty"]) == reorder_quantity
    assert _d(suggestion["current_qty"]) == current_qty

    # 7.1 REORDER → 采购计划
    reorder_request = _ok(
        client,
        "POST",
        f"{INVENTORY}/replenishment-requests",
        json={
            "material_id": reorder_material_id,
            "warehouse_id": warehouse_id,
            "request_qty": str(reorder_quantity),
            "required_date": today.isoformat(),
            "source_type": "REORDER",
            "current_qty": str(current_qty),
            "target_qty": str(reorder_point),
        },
    )
    reorder_confirmed = _ok(
        client, "POST", f"{INVENTORY}/replenishment-requests/{reorder_request['id']}/confirm"
    )
    assert reorder_confirmed["status"] == "RELEASED"
    assert reorder_confirmed["handled_module"] == "procurement"
    assert reorder_confirmed["handled_ref_id"], "应回写生成的采购计划ID"
    reorder_plan = _ok(
        client, "GET", f"{PROCUREMENT}/purchase-plans/{reorder_confirmed['handled_ref_id']}"
    )
    assert any(item["source_type"] == "REORDER" for item in reorder_plan["items"])

    # 7.2 PRODUCTION → 生产作业计划（由 planning 创建，库存不直接建计划）
    semi_code = product["children"][0]["material_code"]
    semi_id = _material_id(client, semi_code)
    production_request = _ok(
        client,
        "POST",
        f"{INVENTORY}/replenishment-requests",
        json={
            "material_id": semi_id,
            "warehouse_id": warehouse_id,
            "request_qty": "10",
            "required_date": today.isoformat(),
            "source_type": "PRODUCTION",
            "current_qty": "0",
            "target_qty": "10",
        },
    )
    production_confirmed = _ok(
        client,
        "POST",
        f"{INVENTORY}/replenishment-requests/{production_request['id']}/confirm",
    )
    assert production_confirmed["status"] == "RELEASED"
    assert production_confirmed["handled_module"] == "planning"
    assert production_confirmed["handled_ref_id"]
    replenishment_plan = _ok(
        client,
        "GET",
        f"{PLANNING}/production-plans/{production_confirmed['handled_ref_id']}",
    )
    assert replenishment_plan["source_type"] == "REPLENISHMENT"
    assert int(replenishment_plan["material_id"]) == semi_id

    note(
        f"[7] 库存主动补库：订货点规则（物料#{reorder_material_id}，点 {reorder_point}）→ "
        f"REORDER 补库 → 采购计划#{reorder_confirmed['handled_ref_id']}；"
        f"PRODUCTION 补库 → 生产计划#{production_confirmed['handled_ref_id']}（source=REPLENISHMENT）"
    )

    # ------------------------------------------------------------------
    # Step 8 — 负库存保护（规格 §36）
    # ------------------------------------------------------------------
    guarded_material_id = reorder_material_id
    guard_before = _on_hand(client, guarded_material_id, warehouse_id)
    guard = _expect_code(
        client,
        "POST",
        f"{INVENTORY}/stock/decrease",
        5001,
        json={
            "material_id": guarded_material_id,
            "warehouse_id": warehouse_id,
            "quantity": str(guard_before + Decimal("1000000")),
        },
    )
    assert guard["code"] == 5001
    guard_after = _on_hand(client, guarded_material_id, warehouse_id)
    assert guard_after == guard_before, "负库存请求被拒后结存必须保持不变"

    note(
        f"[8] 负库存保护：超量出库被拒（5001），物料#{guarded_material_id} 结存 "
        f"{guard_before} 保持不变"
    )

    # ------------------------------------------------------------------
    # 汇总打印（配合 -s 供人工阅读整条链路）
    # ------------------------------------------------------------------
    print("")
    print("=" * 72)
    print("转椅 MTS ERP 全系统核心业务链端到端验收（真实 MySQL / 真实 HTTP API）")
    print("=" * 72)
    for line in summary:
        print(line)
    print("-" * 72)
    print("链路：MPS → MRP → BUY/MAKE → 采购/生产 → 库存 → 发货/退货 → 主动补库 → 负库存保护 全部 PASS")
    print("=" * 72)