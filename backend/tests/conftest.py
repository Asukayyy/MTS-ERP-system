"""pytest 公共 fixture：共享库事务隔离。

所有用例运行在一个**外层事务**里：API 经 ``get_db`` 依赖覆盖，与测试直连的
``db`` 会话共用同一条连接、同一个事务。用例结束统一 ``rollback``，因此共享库
``bh_erp`` 不会残留任何测试数据（无需再手工清理）。

要点：

- ``join_transaction_mode="create_savepoint"``：测试内 ``db.commit()`` 只释放
  保存点，外层事务仍在，最终回滚可撤销全部写入；
- 无 MySQL 时自动降级为不隔离，健康检查等不访问数据库的用例仍可跑通。
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """全测试共享的 TestClient。"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def _db_transaction() -> Iterator[Session | None]:
    """每用例一条外层事务 + 绑定其上的会话；结束统一回滚。无 MySQL 时返回 None。"""
    try:
        connection = engine.connect()
    except Exception:  # noqa: BLE001 - 无数据库时降级，不阻断测试
        yield None
        return

    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def db(_db_transaction: Session | None) -> Session:
    """测试直连会话：与 API 共用同一外层事务，用例结束整体回滚。"""
    if _db_transaction is None:
        pytest.skip("本机无可用 MySQL")
    return _db_transaction


@pytest.fixture(autouse=True)
def _isolate_shared_db(_db_transaction: Session | None) -> Iterator[None]:
    """把 API 的数据库会话重定向到用例事务，保证共享库零残留。"""
    if _db_transaction is None:
        yield
        return

    def _override_get_db() -> Iterator[Session]:
        yield _db_transaction

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)