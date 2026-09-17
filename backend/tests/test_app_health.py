"""应用级健康检查与统一响应规范测试。"""

from fastapi.testclient import TestClient

from app.core.config import settings


def test_app_health(client: TestClient) -> None:
    """根健康检查应返回统一响应结构。"""
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "success"
    assert body["data"]["name"] == settings.APP_NAME
    assert body["data"]["status"] == "ok"


def test_api_prefix_constant() -> None:
    """统一 API 前缀必须为 /api/v1。"""
    assert settings.API_V1_PREFIX == "/api/v1"


def test_not_found_returns_http_error_envelope(client: TestClient) -> None:
    """不存在的路径返回统一错误结构。"""
    response = client.get("/api/v1/not-exist")
    assert response.status_code == 404

    body = response.json()
    assert body["code"] != 0
    assert body["data"] is None
