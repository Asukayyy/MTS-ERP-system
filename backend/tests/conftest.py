"""pytest 公共 fixture。"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """全测试共享的 TestClient。

    健康检查接口不访问数据库，因此即使本机没有 MySQL 也能正常跑通。
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def _isolate_test_mps() -> Iterator[None]:
    """会话级隔离：测试结束后清理本会话新建的 MPS，避免污染共享库。

    做法：会话开始记录 ``pln_mps`` 当前最大 ID 作为基线，结束后删除所有
    ID 大于基线的 MPS（含行明细）。删除前先把引用它们的 ``pln_mrp_run.mps_id``
    置空以绕过 RESTRICT 外键（保留 MRP 历史）。基线方式只清理本会话产生的
    数据，不会误删人工创建或应用运行中产生的计划。

    本机无 MySQL 时（例如只跑健康检查用例）自动跳过，不阻断测试。
    """
    from sqlalchemy import text

    from app.core.database import engine

    baseline: int | None
    try:
        with engine.begin() as conn:
            baseline = int(
                conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM pln_mps")).scalar() or 0
            )
    except Exception:  # noqa: BLE001 - 无数据库时静默跳过清理
        baseline = None

    try:
        yield
    finally:
        if baseline is None:
            return
        with engine.begin() as conn:
            ids = [
                row[0]
                for row in conn.execute(
                    text("SELECT id FROM pln_mps WHERE id > :baseline"),
                    {"baseline": baseline},
                ).fetchall()
            ]
            if not ids:
                return
            id_list = ",".join(str(i) for i in ids)
            conn.execute(text(f"UPDATE pln_mrp_run SET mps_id = NULL WHERE mps_id IN ({id_list})"))
            conn.execute(text(f"DELETE FROM pln_mps_item WHERE mps_id IN ({id_list})"))
            conn.execute(text(f"DELETE FROM pln_mps WHERE id IN ({id_list})"))
