"""system 模块路由。

当前**仅提供占位健康检查接口**，用于证明模块路由注册成功。
业务路由请在本文件中继续添加，统一前缀 `/api/v1/system` 由 `app/main.py` 注入。
"""

from fastapi import APIRouter

from app.modules.system.schemas import HealthResponse
from app.shared.enums import ModuleName, ModuleStatus
from app.shared.types import HealthData

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="system 模块健康检查（占位）")
def health() -> HealthResponse:
    """占位接口：只返回模块标识与状态，不含任何业务逻辑。"""
    return HealthResponse(
        data=HealthData(module=ModuleName.SYSTEM.value, status=ModuleStatus.UP.value)
    )
