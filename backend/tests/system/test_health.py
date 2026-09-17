"""system 模块占位健康检查测试。"""

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["data"] == {"module": "system", "status": "up"}
