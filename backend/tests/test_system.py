"""system 模块业务接口测试。

覆盖：物料新增与编码唯一、BOM 新增 / 子项、多层 BOM 树展开、BOM 版本激活 / 停用、
循环引用拒绝、员工挂靠组织、以及简化版登录。

全部走真实 MySQL（TestClient → 路由 → service → repository），
并使用 `uuid` 生成唯一编码，保证用例可重复执行。
"""

import json
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi.testclient import TestClient

from app.modules.system import service

BASE = "/api/v1/system"

#: 课程权威种子文件（仓库根/data/seed/...）。
_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed" / "course_chair_case.json"


def _code(prefix: str) -> str:
    """生成唯一业务编码，避免重复执行时冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _create_material(
    client: TestClient,
    material_type: str,
    supply_type: str,
    prefix: str = "MAT",
) -> int:
    """创建物料并返回其 ID。"""
    payload = {
        "material_code": _code(prefix),
        "material_name": "测试物料",
        "material_type": material_type,
        "supply_type": supply_type,
    }
    response = client.post(f"{BASE}/materials", json=payload)
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]["id"]


# ==================== 物料 ====================


def test_material_create_and_duplicate_code_rejected(client: TestClient) -> None:
    """物料可新增；相同编码再次新增应返回 1001。"""
    code = _code("MAT")
    payload = {
        "material_code": code,
        "material_name": "转椅成品",
        "material_type": "FINISHED",
        "supply_type": "MAKE",
        "lead_time_days": 3,
        "safety_stock": 10,
    }

    response = client.post(f"{BASE}/materials", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["material_code"] == code
    assert body["data"]["material_type"] == "FINISHED"

    duplicate = client.post(f"{BASE}/materials", json=payload)
    assert duplicate.json()["code"] == 1001


def test_material_invalid_type_rejected(client: TestClient) -> None:
    """非法物料类型应被业务校验拒绝。"""
    payload = {
        "material_code": _code("BAD"),
        "material_name": "非法类型",
        "material_type": "UNKNOWN",
        "supply_type": "MAKE",
    }
    response = client.post(f"{BASE}/materials", json=payload)
    assert response.json()["code"] == 1006


# ==================== BOM ====================


def test_bom_create_and_add_item(client: TestClient) -> None:
    """BOM 头可新增，随后可追加子项。"""
    parent_id = _create_material(client, "FINISHED", "MAKE", "BOM-P")
    child_id = _create_material(client, "RAW", "BUY", "BOM-C")

    created = client.post(
        f"{BASE}/boms",
        json={"material_id": parent_id, "bom_version": "V1.0"},
    ).json()
    assert created["code"] == 0, created
    bom_id = created["data"]["id"]

    added = client.post(
        f"{BASE}/boms/{bom_id}/items",
        json={"material_id": child_id, "quantity": 4, "lead_time_offset": 1, "scrap_rate": 0.02},
    ).json()
    assert added["code"] == 0, added
    assert Decimal(added["data"]["quantity"]) == Decimal("4")

    detail = client.get(f"{BASE}/boms/{bom_id}").json()
    assert detail["code"] == 0
    assert len(detail["data"]["items"]) == 1


def test_bom_duplicate_version_rejected(client: TestClient) -> None:
    """同一物料相同 BOM 版本应返回 1002。"""
    material_id = _create_material(client, "SEMI", "MAKE", "BOM-V")
    payload = {"material_id": material_id, "bom_version": "V9.9"}
    assert client.post(f"{BASE}/boms", json=payload).json()["code"] == 0
    assert client.post(f"{BASE}/boms", json=payload).json()["code"] == 1002


def test_bom_tree_three_levels(client: TestClient) -> None:
    """多层 BOM 树应真实递归展开三层。"""
    root_id = _create_material(client, "FINISHED", "MAKE", "TREE-A")
    mid_id = _create_material(client, "SEMI", "MAKE", "TREE-B")
    leaf_id = _create_material(client, "RAW", "BUY", "TREE-C")

    # A -> B
    root_bom = client.post(
        f"{BASE}/boms",
        json={
            "material_id": root_id,
            "bom_version": "V1.0",
            "items": [{"material_id": mid_id, "quantity": 1}],
        },
    ).json()
    assert root_bom["code"] == 0, root_bom

    # B -> C
    mid_bom = client.post(
        f"{BASE}/boms",
        json={
            "material_id": mid_id,
            "bom_version": "V1.0",
            "items": [{"material_id": leaf_id, "quantity": 6}],
        },
    ).json()
    assert mid_bom["code"] == 0, mid_bom

    tree = client.get(
        f"{BASE}/boms/tree", params={"material_id": root_id, "max_level": 5}
    ).json()
    assert tree["code"] == 0, tree

    root_node = tree["data"][0]
    assert root_node["material_id"] == root_id
    assert root_node["level"] == 1

    level2 = root_node["children"][0]
    assert level2["material_id"] == mid_id
    assert level2["level"] == 2

    level3 = level2["children"][0]
    assert level3["material_id"] == leaf_id
    assert level3["level"] == 3
    assert level3["children"] == []


def test_bom_activate_switches_version(client: TestClient) -> None:
    """激活某版本后，同物料的其它版本应被置为非激活。"""
    material_id = _create_material(client, "FINISHED", "MAKE", "ACT")

    v1 = client.post(
        f"{BASE}/boms",
        json={"material_id": material_id, "bom_version": "V1.0", "is_active": True},
    ).json()["data"]["id"]
    v2 = client.post(
        f"{BASE}/boms",
        json={"material_id": material_id, "bom_version": "V2.0", "is_active": False},
    ).json()["data"]["id"]

    activated = client.post(f"{BASE}/boms/{v2}/activate").json()
    assert activated["code"] == 0, activated
    assert activated["data"]["is_active"] is True

    listed = client.get(
        f"{BASE}/boms", params={"material_id": material_id, "page_size": 50}
    ).json()
    by_id = {item["id"]: item for item in listed["data"]["items"]}
    assert by_id[v1]["is_active"] is False
    assert by_id[v2]["is_active"] is True

    # 停用激活版本后 is_active 应同步置 False
    off = client.patch(f"{BASE}/boms/{v2}/status", json={"status": "INACTIVE"}).json()
    assert off["code"] == 0
    assert off["data"]["status"] == "INACTIVE"
    assert off["data"]["is_active"] is False


def test_bom_cycle_rejected(client: TestClient) -> None:
    """新增子项若形成父→…→父的闭环，应返回 1003。"""
    material_a = _create_material(client, "SEMI", "MAKE", "CYC-A")
    material_b = _create_material(client, "SEMI", "MAKE", "CYC-B")

    # B -> A
    b_bom = client.post(
        f"{BASE}/boms",
        json={
            "material_id": material_b,
            "bom_version": "V1.0",
            "items": [{"material_id": material_a, "quantity": 1}],
        },
    ).json()
    assert b_bom["code"] == 0, b_bom

    # A 的 BOM 试图包含 B，会构成 A -> B -> A 的环
    a_bom_id = client.post(
        f"{BASE}/boms",
        json={"material_id": material_a, "bom_version": "V1.0"},
    ).json()["data"]["id"]

    cyclic = client.post(
        f"{BASE}/boms/{a_bom_id}/items",
        json={"material_id": material_b, "quantity": 1},
    ).json()
    assert cyclic["code"] == 1003


# ==================== 组织 / 人员 ====================


def test_personnel_created_against_organization(client: TestClient) -> None:
    """员工必须挂靠到已存在的组织；工号唯一。"""
    org = client.post(
        f"{BASE}/organizations",
        json={
            "org_code": _code("ORG"),
            "org_name": "总装车间",
            "org_type": "WORKSHOP",
        },
    ).json()
    assert org["code"] == 0, org
    org_id = org["data"]["id"]

    employee_no = _code("EMP")
    payload = {
        "employee_no": employee_no,
        "person_name": "张三",
        "org_id": org_id,
        "position": "装配工",
    }
    created = client.post(f"{BASE}/personnel", json=payload).json()
    assert created["code"] == 0, created
    assert created["data"]["org_id"] == org_id
    assert created["data"]["status"] == "ACTIVE"

    duplicate = client.post(f"{BASE}/personnel", json=payload).json()
    assert duplicate["code"] == 1004

    missing_org = client.post(
        f"{BASE}/personnel",
        json={
            "employee_no": _code("EMP"),
            "person_name": "李四",
            "org_id": 999999999,
        },
    ).json()
    assert missing_org["code"] == 1005


def test_organization_tree_and_cycle_guard(client: TestClient) -> None:
    """组织树应反映父子层级，且修改父级不得形成环。"""
    root = client.post(
        f"{BASE}/organizations",
        json={"org_code": _code("ORG-R"), "org_name": "公司", "org_type": "COMPANY"},
    ).json()["data"]["id"]
    child = client.post(
        f"{BASE}/organizations",
        json={
            "org_code": _code("ORG-C"),
            "org_name": "工厂",
            "org_type": "FACTORY",
            "parent_id": root,
        },
    ).json()["data"]["id"]

    tree = client.get(f"{BASE}/organizations").json()
    assert tree["code"] == 0
    root_node = next(node for node in tree["data"] if node["id"] == root)
    assert child in [node["id"] for node in root_node["children"]]

    # 把根的父级设为子节点 → 形成环，应被拒绝
    cyclic = client.put(f"{BASE}/organizations/{root}", json={"parent_id": child}).json()
    assert cyclic["code"] == 1006


# ==================== RBAC / 登录 ====================


def test_role_and_user_login(client: TestClient) -> None:
    """创建角色 / 权限 / 用户并授权后，应能使用 sha256 密码登录。"""
    role = client.post(
        f"{BASE}/roles", json={"role_code": _code("ROLE"), "role_name": "计划员"}
    ).json()
    assert role["code"] == 0, role
    role_id = role["data"]["id"]

    permission = client.post(
        f"{BASE}/permissions",
        json={"perm_code": _code("PERM"), "perm_name": "查看 BOM", "perm_type": "PAGE"},
    ).json()
    assert permission["code"] == 0, permission
    permission_id = permission["data"]["id"]

    granted = client.post(
        f"{BASE}/roles/{role_id}/permissions", json={"permission_ids": [permission_id]}
    ).json()
    assert granted["code"] == 0, granted
    assert permission_id in [p["id"] for p in granted["data"]["permissions"]]

    username = _code("user")
    password = "secret-123"
    user = client.post(
        f"{BASE}/users",
        json={"username": username, "password": password, "display_name": "计划员账号"},
    ).json()
    assert user["code"] == 0, user
    user_id = user["data"]["id"]

    assigned = client.post(
        f"{BASE}/users/{user_id}/roles", json={"role_ids": [role_id]}
    ).json()
    assert assigned["code"] == 0, assigned
    assert role_id in [r["id"] for r in assigned["data"]["roles"]]

    ok = client.post(
        f"{BASE}/auth/login", json={"username": username, "password": password}
    ).json()
    assert ok["code"] == 0, ok
    assert ok["data"]["user"]["username"] == username
    assert role_id in [r["id"] for r in ok["data"]["roles"]]
    assert permission_id in [p["id"] for p in ok["data"]["permissions"]]

    bad = client.post(
        f"{BASE}/auth/login", json={"username": username, "password": "wrong"}
    ).json()
    assert bad["code"] == 1010


# ==================== 统计 / 日志 ====================


def test_stats_and_operation_logs(client: TestClient) -> None:
    """统计接口可用，且写操作已落操作日志。"""
    stats = client.get(f"{BASE}/stats").json()
    assert stats["code"] == 0
    for key in (
        "material_count",
        "active_material_count",
        "bom_count",
        "routing_count",
        "personnel_count",
        "user_count",
        "role_count",
        "dictionary_count",
    ):
        assert key in stats["data"]

    logs = client.get(
        f"{BASE}/operation-logs", params={"module": "system", "action": "CREATE"}
    ).json()
    assert logs["code"] == 0
    assert logs["data"]["total"] >= 1


# ==================== 课程数据导入（规格 §37） ====================


def _load_seed() -> Dict[str, Any]:
    """读取课程权威种子文件。"""
    return json.loads(_SEED_PATH.read_text(encoding="utf-8"))


def _walk_seed_stats(product: Dict[str, Any]) -> Tuple[int, int, int, int]:
    """遍历文件中的物料树，返回 (节点数, 最大层级, 含子件的节点数, 子项边数)。"""
    stats = {"nodes": 0, "levels": 0, "headers": 0, "edges": 0}

    def visit(node: Dict[str, Any], level: int) -> None:
        stats["nodes"] += 1
        stats["levels"] = max(stats["levels"], level)
        children = node.get("children") or []
        if children:
            stats["headers"] += 1
        for child in children:
            stats["edges"] += 1
            visit(child, level + 1)

    visit(product, 1)
    return stats["nodes"], stats["levels"], stats["headers"], stats["edges"]


def _material_id(client: TestClient, material_code: str) -> int:
    """按编码精确查出物料 ID（走真实列表接口）。"""
    items = client.get(
        f"{BASE}/materials", params={"keyword": material_code, "page_size": 200}
    ).json()["data"]["items"]
    for item in items:
        if item["material_code"] == material_code:
            return item["id"]
    raise AssertionError(f"物料不存在：{material_code}")


def _tree_depth(node: Dict[str, Any]) -> int:
    """计算 BOM 树的深度（单节点为 1）。"""
    return 1 + max((_tree_depth(child) for child in node["children"]), default=0)


def _collect_levels(node: Dict[str, Any], levels: List[int]) -> None:
    """收集 BOM 树中所有节点的层级值。"""
    levels.append(node["level"])
    for child in node["children"]:
        _collect_levels(child, levels)


def test_materials_import_preview_writes_nothing(client: TestClient) -> None:
    """物料预览只读：物料总数不变，且汇总与源文件 counts 一致。"""
    before = client.get(f"{BASE}/stats").json()["data"]["material_count"]

    preview = client.post(
        f"{BASE}/import/materials/preview", json={"source": "course_chair_case"}
    ).json()
    assert preview["code"] == 0, preview

    after = client.get(f"{BASE}/stats").json()["data"]["material_count"]
    assert after == before, "预览不应写入任何物料"

    seed = _load_seed()
    counts = seed["counts"]
    data = preview["data"]
    assert data["summary"]["total"] == counts["total_nodes"]
    assert data["summary"]["max_level"] == counts["levels"]
    assert data["summary"]["invalid"] == 0
    assert data["summary"]["source_counts"] == counts
    assert len(data["materials"]) == counts["total_nodes"]
    assert data["errors"] == []


def test_materials_import_confirm_is_idempotent(client: TestClient) -> None:
    """物料确认导入按预览的 to_create 创建；重复执行不再新增。"""
    preview = client.post(
        f"{BASE}/import/materials/preview", json={"source": "course_chair_case"}
    ).json()["data"]
    to_create_before = preview["summary"]["to_create"]
    total = preview["summary"]["total"]

    first = client.post(
        f"{BASE}/import/materials/confirm", json={"source": "course_chair_case"}
    ).json()
    assert first["code"] == 0, first
    assert first["data"]["created"] == to_create_before
    assert first["data"]["created"] + first["data"]["skipped"] == total
    assert first["data"]["errors"] == []

    second = client.post(
        f"{BASE}/import/materials/confirm", json={"source": "course_chair_case"}
    ).json()["data"]
    assert second["created"] == 0
    assert second["skipped"] == total

    seed = _load_seed()
    root_code = seed["course_data"]["product"]["material_code"]
    assert _material_id(client, root_code) > 0


def test_bom_import_preview_counts_match_file(client: TestClient) -> None:
    """BOM 预览的节点 / 层级 / 头 / 子项数量应与源文件逐一对应。"""
    seed = _load_seed()
    product = seed["course_data"]["product"]
    _, expected_levels, expected_headers, expected_edges = _walk_seed_stats(product)

    preview = client.post(
        f"{BASE}/import/bom/preview", json={"source": "course_chair_case"}
    ).json()
    assert preview["code"] == 0, preview
    data = preview["data"]
    summary = data["summary"]

    assert data["errors"] == []
    assert summary["total_nodes"] == seed["counts"]["total_nodes"]
    assert summary["levels"] == expected_levels == seed["counts"]["levels"]
    assert summary["bom_headers"] == expected_headers
    assert summary["bom_items"] == expected_edges
    assert len(data["bom_items"]) == expected_edges
    assert summary["source_counts"] == seed["counts"]

    # 课程文件未提供提前期偏置 / 损耗率，统一默认 0
    assert summary["lead_time_offset_default"] == 0
    for item in data["bom_items"]:
        assert item["lead_time_offset"] == 0
        assert Decimal(str(item["scrap_rate"])) == Decimal("0")

    # 最深子件层级应等于树的最大层级
    assert max(item["level"] for item in data["bom_items"]) == expected_levels


def test_bom_import_confirm_multilevel_readable_by_tree(client: TestClient) -> None:
    """BOM 确认导入应生成多层（≥3）BOM，且能被 GET /boms/tree 还原；重复执行幂等。"""
    # BOM 导入要求物料先存在
    client.post(f"{BASE}/import/materials/confirm", json={"source": "course_chair_case"})

    first = client.post(
        f"{BASE}/import/bom/confirm", json={"source": "course_chair_case"}
    ).json()
    assert first["code"] == 0, first
    assert first["data"]["errors"] == []

    second = client.post(
        f"{BASE}/import/bom/confirm", json={"source": "course_chair_case"}
    ).json()["data"]
    assert second["bom_headers_created"] == 0
    assert second["bom_items_created"] == 0

    seed = _load_seed()
    product = seed["course_data"]["product"]
    root_id = _material_id(client, product["material_code"])

    tree = client.get(
        f"{BASE}/boms/tree", params={"material_id": root_id, "max_level": 10}
    ).json()
    assert tree["code"] == 0, tree
    root_node = tree["data"][0]
    assert root_node["material_code"] == product["material_code"]
    assert _tree_depth(root_node) >= 3
    assert len(root_node["children"]) == len(product["children"])

    levels: List[int] = []
    _collect_levels(root_node, levels)
    assert max(levels) == seed["counts"]["levels"]


def test_import_invalid_or_missing_code_lands_in_errors(
    client: TestClient, monkeypatch
) -> None:
    """非法 / 缺码节点应进入 errors，确认时不会被导入。"""
    root_code = _code("IMP-ROOT")
    bad_type_code = _code("IMP-BAD")
    crafted = {
        "course_data": {
            "product": {
                "material_code": root_code,
                "material_name": "导入测试根",
                "material_type": "FINISHED",
                "supply_type": "MAKE",
                "children": [
                    {
                        "material_code": "",
                        "material_name": "缺码",
                        "material_type": "RAW",
                        "supply_type": "BUY",
                        "quantity": 1,
                    },
                    {
                        "material_code": bad_type_code,
                        "material_name": "类型非法",
                        "material_type": "BOGUS",
                        "supply_type": "BUY",
                        "quantity": 1,
                    },
                ],
            }
        },
        "counts": {"levels": 2, "semi_components": 0, "purchased_parts": 2, "total_nodes": 3},
    }
    monkeypatch.setattr(service, "_load_course_seed", lambda source: crafted)

    preview = client.post(
        f"{BASE}/import/materials/preview", json={"source": "course_chair_case"}
    ).json()["data"]
    assert preview["summary"]["invalid"] == 2
    assert preview["summary"]["to_create"] == 1
    assert len(preview["errors"]) >= 2

    # BOM 预览：缺码子件应进入 errors
    bom_preview = client.post(
        f"{BASE}/import/bom/preview", json={"source": "course_chair_case"}
    ).json()["data"]
    assert bom_preview["errors"]

    confirm = client.post(
        f"{BASE}/import/materials/confirm", json={"source": "course_chair_case"}
    ).json()["data"]
    assert confirm["errors"]
    assert _material_id(client, root_code) > 0  # 合法根节点已导入

    # 非法节点未被导入
    missing = client.get(
        f"{BASE}/materials", params={"keyword": bad_type_code}
    ).json()["data"]
    assert missing["total"] == 0


def test_import_bom_without_materials_raises_1012(
    client: TestClient, monkeypatch
) -> None:
    """BOM 确认导入时若物料缺失，应抛 1012 要求先导入物料。"""
    crafted = {
        "course_data": {
            "product": {
                "material_code": _code("IMP-MISS"),
                "material_name": "缺失物料根",
                "material_type": "FINISHED",
                "supply_type": "MAKE",
                "children": [
                    {
                        "material_code": _code("IMP-MISS-CHILD"),
                        "material_name": "缺失子件",
                        "material_type": "RAW",
                        "supply_type": "BUY",
                        "quantity": 1,
                    }
                ],
            }
        },
        "counts": {},
    }
    monkeypatch.setattr(service, "_load_course_seed", lambda source: crafted)

    result = client.post(
        f"{BASE}/import/bom/confirm", json={"source": "course_chair_case"}
    ).json()
    assert result["code"] == 1012