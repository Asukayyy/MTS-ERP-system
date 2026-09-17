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
